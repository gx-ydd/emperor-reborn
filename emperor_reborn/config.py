from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    workspace: Path
    memory_dir: Path
    provider: str
    model: str
    alibaba_base_url: str
    permission_mode: str


def load_settings() -> Settings:
    load_dotenv()

    workspace = Path(os.getenv("EMPEROR_WORKSPACE", ".")).expanduser().resolve()
    memory_dir = Path(os.getenv("EMPEROR_MEMORY_DIR", "memory")).expanduser()

    if not memory_dir.is_absolute():
        memory_dir = (workspace / memory_dir).resolve()

    return Settings(
        host=os.getenv("EMPEROR_HOST", "127.0.0.1"),
        port=int(os.getenv("EMPEROR_PORT", "8765")),
        workspace=workspace,
        memory_dir=memory_dir,
        provider=os.getenv("EMPEROR_PROVIDER", "alibaba"),
        model=os.getenv("EMPEROR_MODEL", "qwen-plus"),
        alibaba_base_url=os.getenv(
            "EMPEROR_ALIBABA_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
        permission_mode=os.getenv("EMPEROR_PERMISSION_MODE", "ask_before_edit"),
    )