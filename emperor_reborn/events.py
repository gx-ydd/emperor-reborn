from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RuntimeEvent(BaseModel):
    seq: int
    turn_id: str
    event: str
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=now_iso)


class EventSink:
    def __init__(self, turn_id: str | None = None):
        self.turn_id = turn_id or f"turn_{uuid4().hex}"
        self.seq = 0

    def make(self, event: str, **payload: Any) -> RuntimeEvent:
        self.seq += 1
        return RuntimeEvent(
            seq=self.seq,
            turn_id=self.turn_id,
            event=event,
            payload=payload,
        )
