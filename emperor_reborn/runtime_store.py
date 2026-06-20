from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from emperor_reborn.events import RuntimeEvent


@dataclass
class RuntimeEventStore:
    root: Path

    @property
    def runtime_dir(self) -> Path:
        return self.root / "runtime"

    @property
    def event_path(self) -> Path:
        return self.runtime_dir / "events.jsonl"

    @property
    def index_path(self) -> Path:
        return self.runtime_dir / "index.json"

    def init(self) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.event_path.touch(exist_ok=True)

        if not self.index_path.exists():
            self.index_path.write_text(
                json.dumps(
                    {
                        "total_events": 0,
                        "lastest_turn_id": None
                    },
                    ensure_ascii=False,
                    indent=2
                ),
                encoding="utf-8"
            )

    async def append(self, event: RuntimeEvent) -> None:
        self.init()
        with self.event_path.open("a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")
        self._update_index(event)

    def _update_index(self, event: RuntimeEvent) -> None:
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        data["total_events"] = int(data.get("total_events", 0)) + 1
        data["lastest_turn_id"] = event.turn_id
        data["lastest_event"] = event.event
        data["lastest_timestamp"] = event.timestamp

        self.index_path.write_text(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

    async def list_events(
            self,
            limit: int = 500,
            turn_id: str | None = None
    ) -> list[dict[str, Any]]:
        self.init()

        rows: list[dict[str, Any]] = []
        with self.event_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if turn_id and turn_id != row["turn_id"]:
                    continue
                rows.append(row)
        if limit > 0:
            rows = rows[-limit:]
        return rows

    async def stats(self) -> dict[str, Any]:
        self.init()
        try:
            index = json.loads(self.index_path.read_text(encoding="utf-8"))
        except Exception:
            index = {}

        size_bytes = self.event_path.stat().st_size if self.event_path.exists() else 0
        return {
            "runtime_dir": str(self.runtime_dir),
            "event_path": str(self.event_path),
            "index_path": str(self.index_path),
            "event_size_bytes": size_bytes,
            **index
        }

    async def clear(self) -> None:
        self.init()
        self.event_path.write_text("", encoding="utf-8")
        self.index_path.write_text(
            json.dumps(
                {
                    "total_events": 0,
                    "lastest_turn_id": None
                },
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )
