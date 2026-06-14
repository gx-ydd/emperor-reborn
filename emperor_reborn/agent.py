from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import httpx
from pydantic_ai import Agent, RunContext

from emperor_reborn.memory import MemoryStore
from emperor_reborn.security import SecurityError, safe_path, validate_command


@dataclass
class EmperorDeps:
    workspace: Path
    memory: MemoryStore
    permission_mode: str = "ask_before_edit"


agent = Agent(
    deps_type=EmperorDeps,
    instructions=(
        "你是一个本地个人 Agent，名字叫 Emperor Reborn。"
        "你可以使用工具读取项目文件、列目录、抓取网页、运行少量安全命令。"
        "回答要清楚、直接。使用工具后要总结你做了什么。"
        "写文件或高风险操作必须谨慎；如果工具返回需要审批，就向用户说明需要批准。"
    ),
)


@agent.tool
async def read_file(ctx: RunContext[EmperorDeps], path: str, max_chars: int = 12000) -> str:
    try:
        target = safe_path(ctx.deps.workspace, path)
        if not target.exists():
            return f"File not found: {path}"
        if not target.is_file():
            return f"Not a file: {path}"
        text = target.read_text(encoding="utf-8", errors="replace")
        return text[:max_chars]
    except SecurityError as e:
        return f"Permission denied: {e}"


@agent.tool
async def list_file(ctx: RunContext[EmperorDeps], pattern: str = "**/*", limit: int = 80) -> list[str]:
    try:
        files: list[str] = []
        for path in ctx.deps.workspace.glob(pattern):
            if path.is_file():
                files.append(str(path.relative_to(ctx.deps.workspace)))
            if len(files) >= limit:
                break
        return files
    except Exception as e:
        return [f"Error: {e}"]


@agent.tool_plain
async def web_fetch(url: str, max_chars: int = 12000) -> str:
    """Fetch a web page as text.

    Args:
        url: URL to fetch. Must start with http:// or https://.
        max_chars: Maximum characters to return.
    """
    if not url.startswith(("http://", "https://")):
        return "Only http:// and https:// URLs are allowed."

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text[:max_chars]
    except Exception as exc:
        return f"Fetch failed: {exc}"


@agent.tool
async def run_command(ctx: RunContext[EmperorDeps], command: str, timeout_seconds: int = 20) -> str:
    try:
        parts = validate_command(command)
        proc = await asyncio.create_subprocess_exec(
            *parts,
            cwd=str(ctx.deps.workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
        output = stdout.decode(errors="replace")
        error = stdout.decode(errors="replace")
        return (output + ("\nSTDERR:\n" + error if error else ""))[:12000]
    except Exception as e:
        return f"Error: {e}"


@agent.tool
async def write_file(ctx: RunContext[EmperorDeps], path: str, content: str) -> str:
    if ctx.deps.permission_mode != "auto":
        return (
            "Permission required: write_file is blocked because EMPEROR_PERMISSION_MODE "
            "is not 'auto'. Ask the user to review the path and content, then set "
            "EMPEROR_PERMISSION_MODE=auto only when they accept the risk."
        )
    try:
        target = safe_path(ctx.deps.workspace, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Wrote file:{path}"
    except SecurityError as e:
        return f"Permission denied: {e}"
    except Exception as e:
        return f"Error: {e}"
