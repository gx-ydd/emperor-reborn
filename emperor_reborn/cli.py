from __future__ import annotations

import os
from pathlib import Path

import typer
import uvicorn
from rich.console import Console

from emperor_reborn.config import load_settings

app = typer.Typer(help="Emperor Reborn command line")
console = Console()


@app.command()
def init() -> None:
    """Create local memory directory and .env file if missing."""
    settings = load_settings()
    settings.memory_dir.mkdir(parents=True, exist_ok=True)
    (settings.memory_dir / "chat.jsonl").touch(exist_ok=True)
    (settings.memory_dir / "model_messages.jsonl").touch(exist_ok=True)

    env_path = Path(".env")
    if not env_path.exists() and Path(".env.example").exists():
        env_path.write_text(Path(".env.example").read_text(encoding="utf-8"), encoding="utf-8")
        console.print("[green]Created .env from .env.example[/green]")

    console.print(f"[green]Memory ready:[/green] {settings.memory_dir}")


@app.command()
def doctor() -> None:
    """Check whether the local app is configured."""
    settings = load_settings()

    console.print(f"Provider: [cyan]{settings.provider}[/cyan]")
    console.print(f"Model: [cyan]{settings.model}[/cyan]")
    console.print(f"Workspace: [cyan]{settings.workspace}[/cyan]")
    console.print(f"Memory: [cyan]{settings.memory_dir}[/cyan]")
    console.print(f"Permission mode: [cyan]{settings.permission_mode}[/cyan]")

    if settings.provider == "alibaba":
        if not os.getenv("DASHSCOPE_API_KEY") and not os.getenv("ALIBABA_API_KEY"):
            console.print("[yellow]DASHSCOPE_API_KEY or ALIBABA_API_KEY is missing.[/yellow]")
        else:
            console.print("[green]Alibaba DashScope key looks present.[/green]")

        console.print(f"Alibaba base URL: [cyan]{settings.alibaba_base_url}[/cyan]")

    elif settings.provider == "openai-compatible":
        if not os.getenv("OPENAI_API_KEY"):
            console.print("[yellow]OPENAI_API_KEY is missing.[/yellow]")
        if not os.getenv("OPENAI_BASE_URL"):
            console.print("[yellow]OPENAI_BASE_URL is missing.[/yellow]")
    elif settings.provider in {"local", "local-openai"}:
        console.print("[green]Local OpenAI-compatible mode enabled.[/green]")
        console.print(f"Local base URL: [cyan]{settings.local_base_url}[/cyan]")
        console.print("[green]No real API key is required.[/green]")

@app.command()
def web(debug: bool = typer.Option(False, "--debug", help="Enable debug log.")) -> None:
    """Start the local web server."""
    settings = load_settings()
    console.print(f"Starting on http://{settings.host}:{settings.port}")
    uvicorn.run(
        "emperor_reborn.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level="debug" if debug else "info",
    )
