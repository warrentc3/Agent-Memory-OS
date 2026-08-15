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
    configured_home = home or os.getenv("AGENT_MEMORY_HOME") or "~/.agent-memory"
    return Path(configured_home).expanduser()


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
        from cryptography.fernet import Fernet  # type: ignore[import-not-found]
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
    from cryptography.fernet import InvalidToken  # type: ignore[import-not-found]

    token = body[len(ENVELOPE_PREFIX):].encode("ascii")
    try:
        return fernet.decrypt(token).decode("utf-8")
    except InvalidToken as exc:
        raise SyncCryptoError(
            "could not decrypt the sync bundle — the peer's AGENT_MEMORY_SYNC_KEY "
            "does not match this node's key."
        ) from exc


# --------------------------------------------------------------------------- #
# Fleet admin identity (v1.6): Ed25519 keypair + request signatures
# --------------------------------------------------------------------------- #
# A fleet admin holds an Ed25519 PRIVATE key on the console node; every other
# node stores only the PUBLIC key (granted over a local/trusted channel, never
# adopted from a sync bundle). Each cross-node operation is signed over a
# canonical digest of the request plus a timestamp and nonce, so no shared
# secret ever crosses the wire and revocation is per-node and immediate.

FLEET_KEY_FILENAME = "fleet_admin_key"


def fleet_key_path(home: str | Path | None) -> Path:
    return resolve_home(home) / FLEET_KEY_FILENAME


def _ed25519():
    try:
        from cryptography.hazmat.primitives.asymmetric import (  # type: ignore[import-not-found]
            ed25519,
        )
    except ModuleNotFoundError as exc:  # pragma: no cover - hit only without the extra
        raise SyncCryptoError(
            "fleet admin signatures need the 'cryptography' package — install it "
            'with `pip install "agent-memory-os[secure-sync]"` (or the [full] extra).'
        ) from exc
    return ed25519


def fleet_key_id(public_key_b64: str) -> str:
    """Stable short identifier for a public key (first 12 hex of SHA-256)."""
    raw = base64.urlsafe_b64decode(public_key_b64.encode("ascii"))
    return hashlib.sha256(raw).hexdigest()[:12]


def generate_fleet_keypair() -> dict[str, str]:
    """A fresh Ed25519 keypair as {key_id, private_key, public_key} (b64 raw)."""
    ed25519 = _ed25519()
    private = ed25519.Ed25519PrivateKey.generate()
    from cryptography.hazmat.primitives import (  # type: ignore[import-not-found]
        serialization,
    )

    priv_raw = private.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
        serialization.NoEncryption())
    pub_raw = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    public_b64 = base64.urlsafe_b64encode(pub_raw).decode("ascii")
    return {
        "key_id": fleet_key_id(public_b64),
        "private_key": base64.urlsafe_b64encode(priv_raw).decode("ascii"),
        "public_key": public_b64,
    }


def save_fleet_key(home: str | Path | None, keypair: dict[str, str]) -> Path:
    """Persist the console's fleet keypair (mode 600, atomic replace)."""
    import json

    path = fleet_key_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(keypair, handle)
            handle.write("\n")
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, path)
    if os.name == "posix":
        path.chmod(0o600)
    return path


def load_fleet_key(home: str | Path | None = None) -> dict[str, str] | None:
    """The console's fleet keypair from <home>/fleet_admin_key, or None."""
    import json

    try:
        data = json.loads(fleet_key_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or "private_key" not in data:
        return None
    return data


def fleet_canonical_message(
    method: str, path: str, body: bytes, timestamp: str, nonce: str
) -> bytes:
    """The exact bytes a fleet request signature covers.

    Binds the HTTP method, path, body digest, timestamp, and nonce so a
    captured signature cannot be replayed against a different route, payload,
    or point in time.
    """
    digest = hashlib.sha256(body or b"").hexdigest()
    return f"{method.upper()}\n{path}\n{digest}\n{timestamp}\n{nonce}".encode()


def fleet_sign(private_key_b64: str, message: bytes) -> str:
    ed25519 = _ed25519()
    raw = base64.urlsafe_b64decode(private_key_b64.encode("ascii"))
    private = ed25519.Ed25519PrivateKey.from_private_bytes(raw)
    return base64.urlsafe_b64encode(private.sign(message)).decode("ascii")


def fleet_verify(public_key_b64: str, message: bytes, signature_b64: str) -> bool:
    """True iff `signature_b64` is a valid signature over `message`. Never raises."""
    try:
        ed25519 = _ed25519()
        pub_raw = base64.urlsafe_b64decode(public_key_b64.encode("ascii"))
        sig = base64.urlsafe_b64decode(signature_b64.encode("ascii"))
        ed25519.Ed25519PublicKey.from_public_bytes(pub_raw).verify(sig, message)
        return True
    except SyncCryptoError:
        raise  # missing dependency is a config problem, not a bad signature
    except Exception:  # noqa: BLE001 - any parse/verify failure = invalid
        return False


def fleet_sign_headers(
    keypair: dict[str, str], method: str, target: str, body: bytes = b""
) -> dict[str, str]:
    """The four signed-request headers for one fleet operation.

    `target` is the path INCLUDING the query string exactly as sent (query
    params are covered by the signature, so they cannot be tampered with).
    Each call mints a fresh nonce — never reuse the returned headers.
    """
    import time

    timestamp = str(int(time.time()))
    nonce = secrets.token_urlsafe(16)
    message = fleet_canonical_message(method, target, body, timestamp, nonce)
    return {
        "x-amos-fleet-key-id": keypair["key_id"],
        "x-amos-fleet-timestamp": timestamp,
        "x-amos-fleet-nonce": nonce,
        "x-amos-fleet-signature": fleet_sign(keypair["private_key"], message),
    }
