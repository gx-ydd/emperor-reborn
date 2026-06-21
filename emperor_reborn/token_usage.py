from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cache_write_tokens",
    "cache_read_tokens",
    "input_audio_tokens",
    "output_audio_tokens",
    "cache_audio_read_tokens",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def local_day(ts: str | None = None) -> str:
    """Return YYYY-MM-DD in the server's local timezone."""
    if ts:
        try:
            value = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return value.astimezone().date().isoformat()
        except Exception:
            pass
    return datetime.now().astimezone().date().isoformat()


def estimate_tokens(text: str) -> int:
    """本地模型不返回 usage 时的粗略估算。

      注意：这是 fallback，不是精确 tokenizer。
      中文大致按 1 字 1 token，英文/代码大致按 3.6 字符 1 token。
      """
    if not text:
        return 0
    total = 0.0
    ascii_run = 0

    def flush_ascii() -> None:
        nonlocal total, ascii_run
        if ascii_run:
            total += max(1, round(ascii_run / 3.6))
            ascii_run = 0

    for ch in text:
        code = ord(ch)
        if ch.isspace():
            flush_ascii()
            continue
        if code < 128:
            ascii_run += 1
        else:
            flush_ascii()
            total += 1
    flush_ascii()
    return int(total)


def usage_to_dict(usage: Any) -> dict[str, int]:
    """兼容 pydantic-ai RunUsage 以及旧字段命名。"""
    data: dict[str, int] = {}

    for field in TOKEN_FIELDS:
        value = getattr(usage, field, 0)
        try:
            data[field] = int(value or 0)
        except Exception:
            data[field] = 0
    if not data["input_tokens"]:
        data["input_tokens"] = int(getattr(usage, "request_tokens", 0) or 0)

    if not data["output_tokens"]:
        data["output_tokens"] = int(getattr(usage, "response_tokens", 0) or 0)

    total = getattr(usage, "total_tokens", None)
    if total is None:
        total = data["input_tokens"] + data["output_tokens"]
    data["total_tokens"] = int(total or 0)
    data["requests"] = int(getattr(usage, "requests", 0) or 0)
    data["tool_calls"] = int(getattr(usage, "tool_calls", 0) or 0)
    return data


def empty_usage() -> dict[str, int]:
    data = {field: 0 for field in TOKEN_FIELDS}
    data["requests"] = 0
    data["tool_calls"] = 0
    return data


def empty_daily_summary(day: str | None = None) -> dict[str, Any]:
    return {
        "day": day or local_day(),
        "runs": 0,
        "ok_runs": 0,
        "failed_runs": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "requests": 0,
        "tool_calls": 0,
    }


@dataclass
class TokenUsageStore:
    root: Path

    @property
    def usage_path(self) -> Path:
        return self.root / "token_usage.jsonl"

    def init(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.usage_path.touch(exist_ok=True)

    async def append(self, row: dict[str, Any]) -> dict[str, Any]:
        self.init()
        with self.usage_path.open("a", encoding="utf-8") as f:
            json.dump(row, f, ensure_ascii=False)
            f.write("\n")
        return row

    async def record_success(
            self,
            *,
            turn_id: str,
            provider: str,
            model: str,
            usage: Any,
            prompt: str,
            output: str,
    ) -> dict[str, Any]:
        usage_data = usage_to_dict(usage) if usage is not None else empty_usage()
        source = "pydantic_ai"
        # 很多本地 OpenAI-compatible 服务不会返回 usage，
        # 此时 total_tokens 会是 0，这里改用估算。
        if usage_data["total_tokens"] <= 0:
            input_tokens = estimate_tokens(prompt)
            output_tokens = estimate_tokens(output)
            usage_data.update(
                {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                }
            )
            source = "estimated"

        ts = now_iso()

        return await self.append(
            {
                "turn_id": turn_id,
                "timestamp": ts,
                "day": local_day(ts),
                "provider": provider,
                "model": model,
                "status": "ok",
                "source": source,
                **usage_data,
            }
        )

    async def record_failed(
            self,
            *,
            turn_id: str,
            provider: str,
            model: str,
            prompt: str,
            partial_output: str = "",
            status: str = "error",
            error_type: str | None = None,
            error_message: str | None = None,
    ) -> dict[str, Any]:
        input_tokens = estimate_tokens(prompt)
        output_tokens = estimate_tokens(partial_output)

        ts = now_iso()

        return await self.append(
            {
                "turn_id": turn_id,
                "timestamp": ts,
                "day": local_day(ts),
                "provider": provider,
                "model": model,
                "status": status,
                "source": "estimated",
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "cache_write_tokens": 0,
                "cache_read_tokens": 0,
                "input_audio_tokens": 0,
                "output_audio_tokens": 0,
                "cache_audio_read_tokens": 0,
                "requests": 0,
                "tool_calls": 0,
                "error_type": error_type,
                "error_message": error_message,
            }
        )

    async def list_records(
            self,
            *,
            limit: int = 200,
            day: str | None = None,
    ) -> list[dict[str, Any]]:
        self.init()

        rows: list[dict[str, Any]] = []

        with self.usage_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    row = json.loads(line)
                except Exception:
                    continue

                if day and row.get("day") != day:
                    continue

                rows.append(row)

        if limit > 0:
            return rows[-limit:]

        return rows

    async def daily_summary(self, *, days: int = 14) -> list[dict[str, Any]]:
        self.init()

        buckets: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "day": "",
                "runs": 0,
                "ok_runs": 0,
                "failed_runs": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "requests": 0,
                "tool_calls": 0,
            }
        )

        for row in await self.list_records(limit=0):
            day = str(row.get("day") or local_day(row.get("timestamp")))
            bucket = buckets[day]

            bucket["day"] = day
            bucket["runs"] += 1

            if row.get("status") == "ok":
                bucket["ok_runs"] += 1
            else:
                bucket["failed_runs"] += 1

            for key in (
                    "input_tokens",
                    "output_tokens",
                    "total_tokens",
                    "requests",
                    "tool_calls",
            ):
                bucket[key] += int(row.get(key) or 0)

        rows = sorted(buckets.values(), key=lambda item: item["day"])

        if days > 0:
            return rows[-days:]

        return rows

    async def today_summary(self) -> dict[str, Any]:
        today = local_day()
        rows = [row for row in await self.daily_summary(days=0) if row["day"] == today]

        if rows:
            return rows[0]

        return empty_daily_summary(today)