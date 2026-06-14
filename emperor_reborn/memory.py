from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic_ai import ModelMessage, ModelMessagesTypeAdapter

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

    async def get_model_messages(self) -> list[ModelMessage]:
        self.init()
        messages: list[ModelMessage] = []
        with self.model_messages_path.open("rb") as f:
            for line in f:
                line = line.strip()
                if line:
                    messages.extend(ModelMessagesTypeAdapter.validate_json(line))
        return messages
