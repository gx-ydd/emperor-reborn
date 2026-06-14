from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, AsyncIterator

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


class AgentRuntime:
    def __init__(self, setting: Settings):
        self.settings = setting
        self.memory = MemoryStore(self.settings.memory_dir)
        self.memory.init()
        self.model = build_model(self.settings)

    async def stream_chat(self, prompt: str) -> AsyncIterator[RuntimeEvent]:
        sink = EventSink()

        deps = EmperorDeps(
            workspace=self.settings.workspace,
            memory=self.memory,
            permission_mode=self.settings.permission_mode,
        )

        await self.memory.add_display_message("user", prompt)

        yield sink.make("user_message", content=prompt)
        yield sink.make(
            "assistant_start",
            provider=self.settings.provider,
            model=self.settings.model,
        )

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
                message_history = await self.memory.get_model_messages()

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

                await self.memory.add_model_messages_json(result.new_messages_json())
                await self.memory.add_display_message("assistant", final_text)

                await push(sink.make("assistant_done", content=final_text))

            except Exception as e:
                await push(
                    sink.make(
                        "error",
                        message=str(e),
                        error_type=type(e).__name__,
                    )
                )
            finally:
                await queue.put(None)

        task = asyncio.create_task(run_agent())

        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            if not task.done():
                task.cancel()