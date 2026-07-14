"""Application-layer encryption for federated sync bundles.

Sync speaks JSONL over HTTP(S). When a mesh shares a secret sync key, this
module wraps the bundle body in an authenticated-encryption envelope so the
memory content stays confidential even over plain HTTP or through a
TLS-terminating proxy. The sync key is a SEPARATE secret from the Web API
bearer token and is NEVER sent over the wire — so an eavesdropper who captures
the token still cannot read the payload.

Key resolution (mesh-wide — set the SAME value on every node):

    env AGENT_MEMORY_SYNC_KEY  >  <home>/sync_key file

Encryption uses Fernet (AES-128-CBC + HMAC-SHA256, authenticated) from the
`cryptography` package, installed via the ``secure-sync`` (or ``full``) extra.
The Fernet key is derived from the shared secret with SHA-256, so operators can
use any human-chosen passphrase or a generated key. The wire format is:

    AMOSENC1:<fernet-token>

The ``AMOSENC1:`` prefix lets the receiver auto-detect an encrypted body with
no out-of-band header, so it works for both the pull (GET response body) and
push (POST request body) directions.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from pathlib import Path

ENVELOPE_PREFIX = "AMOSENC1:"
SYNC_KEY_FILENAME = "sync_key"


class SyncCryptoError(RuntimeError):
    """An encrypted bundle could not be produced or opened."""


def resolve_home(home: str | Path | None) -> Path:
    return Path(home or os.getenv("AGENT_MEMORY_HOME", "~/.agent-memory")).expanduser()


def sync_key_path(home: str | Path | None) -> Path:
    return resolve_home(home) / SYNC_KEY_FILENAME


def load_sync_secret(home: str | Path | None = None) -> str | None:
    """Resolve the mesh sync secret: env AGENT_MEMORY_SYNC_KEY, else <home>/sync_key.

    Returns None when no key is configured — callers then send/accept plaintext
    (encryption is opportunistic: it turns on when, and only when, a key exists).
    """
    env = os.getenv("AGENT_MEMORY_SYNC_KEY")
    if env and env.strip():
        return env.strip()
    try:
        text = sync_key_path(home).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def save_sync_secret(home: str | Path | None, secret: str) -> Path:
    """Persist the sync secret to <home>/sync_key (mode 600, atomic replace)."""
    path = sync_key_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(secret.strip() + "\n")
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, path)
    if os.name == "posix":
        path.chmod(0o600)  # ensure mode survives if the file pre-existed
    return path


def generate_secret() -> str:
    """A fresh random mesh key to distribute to every node."""
    return "amos_sk_" + secrets.token_urlsafe(32)


def _fernet(secret: str):
    try:
        from cryptography.fernet import Fernet
    except ModuleNotFoundError as exc:  # pragma: no cover - hit only without the extra
        raise SyncCryptoError(
            "encrypted sync needs the 'cryptography' package — install it with "
            '`pip install "agent-memory-os[secure-sync]"` (or the [full] extra).'
        ) from exc
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def is_encrypted(body: str) -> bool:
    """True if a bundle body is one of our encryption envelopes."""
    return body.startswith(ENVELOPE_PREFIX)


def encrypt_bundle(plaintext: str, secret: str) -> str:
    """Wrap a plaintext JSONL bundle in an AMOSENC1 envelope."""
    token = _fernet(secret).encrypt(plaintext.encode("utf-8")).decode("ascii")
    return ENVELOPE_PREFIX + token


def decrypt_bundle(body: str, secret: str) -> str:
    """Open an AMOSENC1 envelope; pass a plaintext body through unchanged."""
    if not is_encrypted(body):
        return body
    fernet = _fernet(secret)
    from cryptography.fernet import InvalidToken

    token = body[len(ENVELOPE_PREFIX):].encode("ascii")
    try:
        return fernet.decrypt(token).decode("utf-8")
    except InvalidToken as exc:
        raise SyncCryptoError(
            "could not decrypt the sync bundle — the peer's AGENT_MEMORY_SYNC_KEY "
            "does not match this node's key."
        ) from exc
