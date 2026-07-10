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


def resolve_home(home: str | Path | None) -> Path:
    return Path(home or os.getenv("AGENT_MEMORY_HOME", "~/.agent-memory")).expanduser()


def token_path(home: str | Path | None) -> Path:
    return resolve_home(home) / TOKEN_FILENAME


def load_token(home: str | Path | None) -> str | None:
    path = token_path(home)
    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return token or None


def save_token(home: str | Path | None, token: str) -> Path:
    path = token_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def create_token(home: str | Path | None) -> str:
    token = "amos_" + secrets.token_urlsafe(32)
    save_token(home, token)
    return token


def delete_token(home: str | Path | None) -> bool:
    path = token_path(home)
    if not path.exists():
        return False
    path.unlink()
    return True
