"""Web UI bearer-token storage.

The token lives next to the memory database (`<home>/web_token`, mode 600) so
one `--home` carries both the data and its access credential. Resolution order
in the web app: explicit --token > AGENT_MEMORY_WEB_TOKEN > this file.

Three token tiers share this machinery, each in its own file with its own
prefix so they are never confused:

- ``full``     (``web_token``,          ``amos_``)      — admin: every API route.
- ``readonly`` (``web_readonly_token``, ``amos_ro_``)   — GET/HEAD/OPTIONS only.
- ``sync``     (``web_sync_token``,     ``amos_sync_``) — federation only: the
  ``/api/sync/*`` and ``/api/node`` routes. Hand THIS to a peer instead of the
  admin token so joining the mesh does not grant full API access.

The legacy ``readonly=`` keyword is still accepted everywhere for backward
compatibility; new callers should pass ``tier=``.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

TOKEN_FILENAME = "web_token"
READONLY_TOKEN_FILENAME = "web_readonly_token"
SYNC_TOKEN_FILENAME = "web_sync_token"

_TIER_FILENAME = {
    "full": TOKEN_FILENAME,
    "readonly": READONLY_TOKEN_FILENAME,
    "sync": SYNC_TOKEN_FILENAME,
}
_TIER_PREFIX = {"full": "amos_", "readonly": "amos_ro_", "sync": "amos_sync_"}


def _resolve_tier(readonly: bool, tier: str | None) -> str:
    if tier is not None:
        if tier not in _TIER_FILENAME:
            raise ValueError(f"unknown token tier: {tier!r}")
        return tier
    return "readonly" if readonly else "full"


def resolve_home(home: str | Path | None) -> Path:
    return Path(home or os.getenv("AGENT_MEMORY_HOME", "~/.agent-memory")).expanduser()


def token_path(home: str | Path | None, *, readonly: bool = False,
               tier: str | None = None) -> Path:
    return resolve_home(home) / _TIER_FILENAME[_resolve_tier(readonly, tier)]


def load_token(home: str | Path | None, *, readonly: bool = False,
               tier: str | None = None) -> str | None:
    path = token_path(home, readonly=readonly, tier=tier)
    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return token or None


def save_token(home: str | Path | None, token: str, *, readonly: bool = False,
               tier: str | None = None) -> Path:
    path = token_path(home, readonly=readonly, tier=tier)
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


def create_token(home: str | Path | None, *, readonly: bool = False,
                  tier: str | None = None) -> str:
    token = _TIER_PREFIX[_resolve_tier(readonly, tier)] + secrets.token_urlsafe(32)
    save_token(home, token, readonly=readonly, tier=tier)
    return token


def delete_token(home: str | Path | None, *, readonly: bool = False,
                 tier: str | None = None) -> bool:
    path = token_path(home, readonly=readonly, tier=tier)
    if not path.exists():
        return False
    path.unlink()
    return True
