from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from emperor_reborn.config import load_settings
from emperor_reborn.runtime import AgentRuntime

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"

settings = load_settings()

runtime = AgentRuntime(settings)

app = FastAPI(title="Emperor Reborn MVP")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health() -> dict[str, object]:
    return {
        "ok": True,
        "provider": settings.provider,
        "mode": settings.model,
        "workspace": str(settings.workspace),
        "memory": str(settings.memory_dir),
        "permission_mode": settings.permission_mode,
    }


@app.get("/api/bootstrap")
async def bootstrap() -> dict[str, object]:
    history = await runtime.memory.get_display_messages()
    runtime_events = await runtime.event_store.list_events(limit=300)
    status = await runtime.get_status()

    return {
        "status": status,
        "history": history,
        "runtime_events": runtime_events,
    }


@app.get("/api/history")
async def history() -> JSONResponse:
    rows = await runtime.memory.get_display_messages()
    return JSONResponse(rows)


@app.get("/api/runtime/events")
async def runtime_events(
        limit: int = Query(default=500, ge=1, le=5000),
        turn_id: str | None = None,
) -> dict[str, object]:
    rows = await runtime.event_store.list_events(limit=limit, turn_id=turn_id)
    return {
        "events": rows,
        "limit": limit,
        "turn_id": turn_id,
    }


@app.post("/api/runtime/stop")
async def stop_runtime() -> dict[str, object]:
    cancelled = runtime.cancel_active_task()

    return {
        "cancelled": cancelled,
        "active_turn_id": runtime.active_turn_id,
    }


@app.get("/api/diagnostics")
async def diagnostics() -> dict[str, object]:
    status = await runtime.get_status()
    runtime_stats = await runtime.event_store.stats()

    return {
        "status": status,
        "runtime": runtime_stats,
        "paths": {
            "root": str(ROOT),
            "static_dir": str(STATIC_DIR),
            "memory_dir": str(settings.memory_dir),
        },
    }


@app.websocket("/ws")
async def websocket_chat(ws: WebSocket) -> None:
    await ws.accept()

    await ws.send_json(
        {
            "event": "ready",
            "payload": {
                "provider": settings.provider,
                "model": settings.model,
            },
        }
    )

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")

            if msg_type == "ping":
                await ws.send_json({"event": "pong", "payload": {}})
                continue

            if msg_type != "user_message":
                await ws.send_json(
                    {
                        "event": "error",
                        "payload": {
                            "message": f"Unknown message type: {msg_type}",
                        },
                    }
                )
                continue

            prompt = str(data.get("content", "")).strip()

            if not prompt:
                await ws.send_json(
                    {
                        "event": "error",
                        "payload": {
                            "message": "Empty message",
                        },
                    }
                )
                continue

            async for event in runtime.stream_chat(prompt):
                await ws.send_text(event.model_dump_json())

    except WebSocketDisconnect:
        return

    except Exception as exc:
        await ws.send_text(
            json.dumps(
                {
                    "event": "error",
                    "payload": {
                        "message": str(exc),
                        "error_type": type(exc).__name__,
                    },
                },
                ensure_ascii=False,
            )
        )
