from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic_ai import ModelMessage, ModelMessagesTypeAdapter
from collections import deque

Role = Literal["user", "assistant", "system"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class MemoryStore:
    root: Path

    @property
    def display_history_path(self) -> Path:
        return self.root / "chat.jsonl"

    @property
    def model_messages_path(self) -> Path:
        return self.root / "model_messages.jsonl"

    def init(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.display_history_path.touch(exist_ok=True)
        self.model_messages_path.touch(exist_ok=True)

    async def add_display_message(self, role: Role, content: str):
        self.init()
        row = {"role": role, "content": content, "timestamp": utc_now()}
        with self.display_history_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    async def get_display_messages(self) -> list[dict[str, str]]:
        self.init()
        rows: list[dict[str, str]] = []
        with self.display_history_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    async def add_model_messages_json(self, message_json: bytes):
        self.init()
        with self.model_messages_path.open("ab") as f:
            f.write(message_json)
            f.write(b"\n")

    async def get_model_messages(self, max_turns: int | None = 24) -> list[ModelMessage]:
        """读取要传给模型的历史消息。
            为什么要加 max_turns：
            1. model_messages.jsonl 会随着对话不断增长。
            2. 如果每次都把完整历史传给模型，token 消耗会越来越高。
            3. 历史太长时，模型可能超上下文窗口，导致请求失败。
            4. emperor-agent 的成熟做法是在调用模型前做上下文治理；
               这里先实现最小可用版本：只保留最近 N 轮模型历史。
            参数:
                max_turns:
                    - 默认 24：只读取最近 24 轮模型消息。
                    - None：读取全部历史，保留旧行为。
            返回:
                list[ModelMessage]：
                    pydantic-ai 的 Agent.run(message_history=...) 可以直接使用。
            """
        self.init()
        messages: list[ModelMessage] = []
        recent_lines: deque[bytes] = deque(maxlen=max_turns)
        with self.model_messages_path.open("rb") as f:
            for line in f:
                line = line.strip()
                if line:
                    recent_lines.append(line)
        lines = list(recent_lines)
        for line in lines:
            message = ModelMessagesTypeAdapter.from_json(line)
            messages.extend(message)
        return messages
