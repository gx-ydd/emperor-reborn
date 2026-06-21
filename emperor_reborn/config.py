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
    openai_base_url: str
    openai_key: str
    local_base_url: str
    local_api_key: str
    permission_mode: str


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def load_settings() -> Settings:
    load_dotenv()

    workspace = Path(_env("EMPEROR_WORKSPACE", ".")).expanduser().resolve()
    memory_dir = Path(_env("EMPEROR_MEMORY_DIR", "memory")).expanduser()

    if not memory_dir.is_absolute():
        memory_dir = (workspace / memory_dir).resolve()

    return Settings(
        host=_env("EMPEROR_HOST", "127.0.0.1"),
        port=int(_env("EMPEROR_PORT", "8765")),
        workspace=workspace,
        memory_dir=memory_dir,
        provider=_env("EMPEROR_PROVIDER", "alibaba"),
        model=_env("EMPEROR_MODEL", "qwen-plus"),
        alibaba_base_url=_env(
            "EMPEROR_ALIBABA_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
        openai_base_url=_env("OPENAI_BASE_URL"),
        openai_key=_env("OPENAI_API_KEY"),
        local_base_url=_env("EMPEROR_LOCAL_BASE_URL"),
        local_api_key=_env("EMPEROR_LOCAL_API_KEY", "local-no-key"),
        permission_mode=_env("EMPEROR_PERMISSION_MODE", "ask_before_edit"),
    )
