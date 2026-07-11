"""Web-console pidfile.

The running console writes `<home>/web.pid` with its pid and the EXACT command
line to relaunch it with. `agent-memory update` reads this to restart the
console it owns after an upgrade — without reconstructing a command from `ps`
output, which any local process could spoof into being re-executed (a local
code-execution vector). The argv here is written by the console about itself,
so it is trustworthy; `ps` strings are not.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .tokens import resolve_home

PIDFILE_NAME = "web.pid"


def pidfile_path(home: str | Path | None) -> Path:
    return resolve_home(home) / PIDFILE_NAME


def relaunch_argv() -> list[str]:
    """A deterministic command to re-run this console: the current interpreter
    running the web_app module with the same arguments. Independent of how the
    process was originally started (console script vs -m), so it always works."""
    return [sys.executable, "-m", "agent_memory_os.web_app", *sys.argv[1:]]


def write_web_pidfile(home: str | Path | None, *, argv: list[str] | None = None,
                      cwd: str | None = None) -> Path | None:
    data = {
        "pid": os.getpid(),
        "argv": list(argv) if argv is not None else relaunch_argv(),
        "cwd": cwd or os.getcwd(),
    }
    path = pidfile_path(home)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        return None
    return path


def read_web_pidfile(home: str | Path | None) -> dict | None:
    try:
        data = json.loads(pidfile_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("pid"), int):
        return None
    argv = data.get("argv")
    if not (isinstance(argv, list) and argv and all(isinstance(a, str) for a in argv)):
        return None
    return data


def clear_web_pidfile(home: str | Path | None) -> None:
    try:
        pidfile_path(home).unlink()
    except OSError:
        pass
