"""Web UI bearer-token storage.

The token lives next to the memory database (`<home>/web_token`, mode 600) so
one `--home` carries both the data and its access credential. Resolution order
in the web app: explicit --token > AGENT_MEMORY_WEB_TOKEN > this file.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

TOKEN_FILENAME = "web_token"
READONLY_TOKEN_FILENAME = "web_readonly_token"


def resolve_home(home: str | Path | None) -> Path:
    return Path(home or os.getenv("AGENT_MEMORY_HOME", "~/.agent-memory")).expanduser()


def token_path(home: str | Path | None, *, readonly: bool = False) -> Path:
    return resolve_home(home) / (READONLY_TOKEN_FILENAME if readonly else TOKEN_FILENAME)


def load_token(home: str | Path | None, *, readonly: bool = False) -> str | None:
    path = token_path(home, readonly=readonly)
    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return token or None


def save_token(home: str | Path | None, token: str, *, readonly: bool = False) -> Path:
    path = token_path(home, readonly=readonly)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write to a private temp file created 0600 from the start (no
    # world-readable window between write and chmod), then atomically replace
    # so a concurrent rotate can never expose or interleave a half-written
    # token.
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(token + "\n")
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, path)
    if os.name == "posix":
        path.chmod(0o600)  # ensure mode survives if the file pre-existed
    return path


def create_token(home: str | Path | None, *, readonly: bool = False) -> str:
    token = ("amos_ro_" if readonly else "amos_") + secrets.token_urlsafe(32)
    save_token(home, token, readonly=readonly)
    return token


def delete_token(home: str | Path | None, *, readonly: bool = False) -> bool:
    path = token_path(home, readonly=readonly)
    if not path.exists():
        return False
    path.unlink()
    return True
