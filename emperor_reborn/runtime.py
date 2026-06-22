from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, AsyncIterator
from contextlib import suppress

from pydantic_ai import (
    AgentStreamEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartStartEvent,
    RunContext,
    TextPartDelta,
    ToolCallPartDelta,
)

from emperor_reborn.agent import EmperorDeps, agent
from emperor_reborn.config import Settings
from emperor_reborn.events import EventSink, RuntimeEvent
from emperor_reborn.llm import build_model
from emperor_reborn.memory import MemoryStore
from emperor_reborn.runtime_store import RuntimeEventStore
from emperor_reborn.token_usage import TokenUsageStore, estimate_tokens


class AgentRuntime:
    def __init__(self, setting: Settings):
        self.settings = setting
        self.memory = MemoryStore(self.settings.memory_dir)
        self.memory.init()

        self.event_store = RuntimeEventStore(self.settings.memory_dir)
        self.event_store.init()

        self.token_usage = TokenUsageStore(self.settings.memory_dir)
        self.token_usage.init()

        self.model = build_model(self.settings)

        self.active_task: asyncio.Task[None] | None = None
        self.active_turn_id: str | None = None

    def is_busy(self) -> bool:
        return self.active_task is not None and not self.active_task.done()

    def cancel_active_task(self) -> bool:
        if not self.active_task or self.active_task.done():
            return False
        self.active_task.cancel()
        return True

    async def get_status(self) -> dict[str, object]:
        today_usage = await self.token_usage.today_summary()
        return {
            "busy": self.is_busy(),
            "active_turn_id": self.active_turn_id,
            "provider": self.settings.provider,
            "model": self.settings.model,
            "workspace": str(self.settings.workspace),
            "memory_dic": str(self.settings.memory_dir),
            "permission_mode": str(self.settings.permission_mode),
            "token_usage_today": today_usage,
        }

    async def _record_success_usage(
            self,
            *,
            turn_id: str,
            prompt: str,
            output: str,
            result: object,
    ) -> dict[str, object]:
        """记录成功请求的 token 用量。

        本地模型不稳定时，统计系统不能反过来影响主流程。
        所以这里全部兜底，失败也返回一个可展示的 usage dict。
        """
        usage_obj = None

        try:
            result_usage = getattr(result, "usage", None)
            if callable(result_usage):
                usage_obj = result_usage()
        except Exception:
            usage_obj = None

        try:
            return await self.token_usage.record_success(
                turn_id=turn_id,
                provider=self.settings.provider,
                model=self.settings.model,
                usage=usage_obj,
                prompt=prompt,
                output=output,
            )
        except Exception as exc:
            input_tokens = estimate_tokens(prompt)
            output_tokens = estimate_tokens(output)

            return {
                "turn_id": turn_id,
                "provider": self.settings.provider,
                "model": self.settings.model,
                "status": "usage_record_error",
                "source": "estimated",
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "requests": 0,
                "tool_calls": 0,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }

    async def _record_failed_usage(
            self,
            *,
            turn_id: str,
            prompt: str,
            partial_output: str,
            status: str,
            error_type: str,
            error_message: str,
    ) -> dict[str, object]:
        """记录失败或取消请求的估算 token 用量。"""
        try:
            return await self.token_usage.record_failed(
                turn_id=turn_id,
                provider=self.settings.provider,
                model=self.settings.model,
                prompt=prompt,
                partial_output=partial_output,
                status=status,
                error_type=error_type,
                error_message=error_message,
            )
        except Exception as exc:
            input_tokens = estimate_tokens(prompt)
            output_tokens = estimate_tokens(partial_output)

            return {
                "turn_id": turn_id,
                "provider": self.settings.provider,
                "model": self.settings.model,
                "status": "usage_record_error",
                "source": "estimated",
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "requests": 0,
                "tool_calls": 0,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }

    async def stream_chat(self, prompt: str) -> AsyncIterator[RuntimeEvent]:
        sink = EventSink()

        deps = EmperorDeps(
            workspace=self.settings.workspace,
            memory=self.memory,
            permission_mode=self.settings.permission_mode,
        )

        async def emit(event: RuntimeEvent) -> RuntimeEvent:
            await self.event_store.append(event)
            return event

        await self.memory.add_display_message("user", prompt)

        yield await emit(sink.make("assistant_message"))
        yield await emit(sink.make(
            "assistant_start",
            provider=self.settings.provider,
            model=self.settings.model,
        ))

        queue: asyncio.Queue[RuntimeEvent | None] = asyncio.Queue()
        final_text_holder = {"text": ""}

        async def push(event: RuntimeEvent) -> None:
            await queue.put(event)

        async def handle_agent_event(
                ctx: RunContext[EmperorDeps],
                event_stream: AsyncIterable[AgentStreamEvent],
        ) -> None:
            async for event in event_stream:
                if isinstance(event, PartStartEvent):
                    part = event.part

                    if getattr(part, "content", None):
                        content = str(part.content)
                        final_text_holder["text"] += content
                        await push(sink.make("message_delta", content=content))

                elif isinstance(event, PartDeltaEvent):
                    delta = event.delta

                    if isinstance(delta, TextPartDelta):
                        content = delta.content_delta
                        if content:
                            final_text_holder["text"] += content
                            await push(sink.make("message_delta", content=content))

                    elif isinstance(delta, ToolCallPartDelta):
                        await push(
                            sink.make(
                                "tool_call_delta",
                                args_delta=str(delta.args_delta),
                            )
                        )

                elif isinstance(event, FunctionToolCallEvent):
                    await push(
                        sink.make(
                            "tool_call",
                            tool_name=event.part.tool_name,
                            args=event.part.args,
                            tool_call_id=event.part.tool_call_id,
                        )
                    )

                elif isinstance(event, FunctionToolResultEvent):
                    await push(
                        sink.make(
                            "tool_result",
                            tool_call_id=event.tool_call_id,
                            content=str(event.part.content),
                        )
                    )

        async def run_agent() -> None:
            try:
                message_history = await self.memory.get_model_messages(max_turns=24)

                result = await agent.run(
                    prompt,
                    deps=deps,
                    model=self.model,
                    message_history=message_history,
                    event_stream_handler=handle_agent_event,
                )

                final_output = str(result.output or "")
                final_text = final_text_holder["text"]

                if not final_text and final_output:
                    final_text = final_output
                    await push(sink.make("message_delta", content=final_output))
                usage_row = await self._record_success_usage(
                    turn_id=sink.turn_id,
                    prompt=prompt,
                    output=final_text,
                    result=result,
                )
                await self.memory.add_model_messages_json(result.new_messages_json())
                await self.memory.add_display_message("assistant", final_text)

                await push(sink.make("token_usage", usage=usage_row))
                await push(sink.make("assistant_done", content=final_text))
            except asyncio.CancelledError:
                usage_row = await self._record_failed_usage(
                    turn_id=sink.turn_id,
                    prompt=prompt,
                    partial_output=final_text_holder["text"],
                    status="cancelled",
                    error_type="CancelledError",
                    error_message="user_cancelled",
                )
                await push(
                    sink.make(
                        "runtime_task_cancelled",
                        reason="user_cancelled",
                        usage=usage_row,
                    )
                )
            except Exception as e:
                usage_row = await self._record_failed_usage(
                    turn_id=sink.turn_id,
                    prompt=prompt,
                    partial_output=final_text_holder["text"],
                    status="error",
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
                await push(
                    sink.make(
                        "error",
                        message=str(e),
                        error_type=type(e).__name__,
                        usage=usage_row,
                    )
                )
            finally:
                await queue.put(None)

        task = asyncio.create_task(run_agent())
        self.active_task = task

        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                await self.event_store.append(event)
                yield event
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            if self.active_task is task:
                self.active_task = None
                self.active_turn_id = None
