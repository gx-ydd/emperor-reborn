from __future__ import annotations

import shlex
from pathlib import Path
from sys import executable


class SecurityError(RuntimeError):
    pass


def safe_path(workspace: Path, user_path: str) -> Path:
    base = workspace.resolve()
    target = (base / user_path).expanduser().resolve()
    if target != base and base not in target.parents:
        raise SecurityError(f"Path is outside workspace:{user_path}")
    return target


ALLOWED_COMMANDS = {
    "pwd",
    "ls",
    "cat",
    "python",
    "python3",
    "git",
    "grep",
}

DANGEROUS_TOKENS = {
    "rm",
    "sudo",
    "chmod",
    "chown",
    "curl",
    "wget",
    "powershell",
    "bash",
    "sh",
}


def validate_command(command: str) -> list[str]:
    parts = shlex.split(command)
    if not parts:
        raise SecurityError("Empty command")
    executable = parts[0]
    if executable not in ALLOWED_COMMANDS:
        raise SecurityError(f"Command not allowed: {executable}")
    if any(token in DANGEROUS_TOKENS for token in parts):
        raise SecurityError(f"Dangerous token found in:{command}")
    if executable == "git" and len(parts) >= 2:
        allowed_git = {"status", "diff", "log", "branch"}
        if parts[1] not in allowed_git:
            raise SecurityError(f"Git command not allowed: {parts[1]}")

    return parts
