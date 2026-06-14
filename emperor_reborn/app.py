from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
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


@app.get("/api/heath")
async def health() -> dict[str, object]:
    return {
        "ok": True,
        "mode": settings.model,
        "workspace": str(settings.workspace),
        "memory": str(settings.memory_dir),
        "permission_mode": settings.permission_mode,
    }

@app.get("/api/history")
async def history() -> JSONResponse:
    rows = await runtime.memory.get_display_messages()
    return JSONResponse(rows)


@app.websocket("/ws")
async def websocket_chat(ws: WebSocket) -> None:
    await ws.accept()
    await ws.send_json({"event": "ready", "payload": {"model": settings.model}})

    try:
        while True:
            data = await ws.receive_json()
            if data.get("type") != "user_message":
                await ws.send_json({"event": "error", "payload": {"message": "Unknown message type"}})
                continue

            prompt = str(data.get("content", "")).strip()
            if not prompt:
                await ws.send_json({"event": "error", "payload": {"message": "Empty message"}})
                continue

            async for event in runtime.stream_chat(prompt):
                await ws.send_text(event.model_dump_json())
    except WebSocketDisconnect:
        return
    except Exception as exc:
        await ws.send_text(json.dumps({"event": "error", "payload": {"message": str(exc)}}))