"""Team pairing: one-time invite codes that bootstrap a memory-sharing peer.

The problem this solves: connecting two nodes today means hand-carrying two
secrets (a sync-scoped bearer token and, for encrypted meshes, the shared
sync key) and running `peers add` on both sides. Pairing collapses that into
one explicit consent exchange:

  node A (existing):   agent-memory team invite apollo
                         → prints a one-time code (TTL, single-use)
  node B (joining):    agent-memory join <code> --url http://127.0.0.1:8001
                         → both sides end up with a team-scoped peer entry,
                           B's agent is added to the team, and B receives
                           A's sync key (if any) so encryption engages.

Security model:
- Only the SHA-256 hash of the code is stored; the code itself is shown once.
- The redeem HTTP exchange is end-to-end encrypted UNDER THE CODE using the
  same authenticated Fernet construction as sync bundles (crypto.py), so the
  tokens/sync-key crossing the wire are unreadable without the code — even
  over plain loopback HTTP, and even by the web tier's other middleware.
- Redemption is atomic and single-use (db.consume_pairing_invite); expired,
  used, and unknown codes are indistinguishable to the caller.
- Joining is never automatic: discovery (discovery.py) only *finds* nodes;
  membership always requires a code issued by the other node's operator.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import urllib.error
import urllib.request
from typing import Any

from . import crypto, tokens

CODE_PREFIX = "amos_join_"
DEFAULT_TTL_SECONDS = 600
REDEEM_PATH = "/api/pairing/redeem"


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def issue_invite(client: Any, team_id: str, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> dict:
    """Mint a one-time pairing code for `team_id` (store keeps only its hash)."""
    code = CODE_PREFIX + secrets.token_urlsafe(24)
    record = client.store.create_pairing_invite(
        team_id, _hash_code(code), ttl_seconds=ttl_seconds,
    )
    return {"code": code, "team_id": team_id, "expires_at": record["expires_at"]}


# --------------------------------------------------------------------------- #
# Server side (runs inside the inviter's web app)
# --------------------------------------------------------------------------- #

def redeem_invite(
    client: Any,
    envelope: str,
    code: str,
    *,
    home: str | None = None,
    self_node_name: str = "",
) -> dict:
    """Validate + consume an invite and swap credentials with the joiner.

    `envelope` is the joiner's request payload encrypted under the code:
      {node_name, agent_id, url, sync_token}   (their token, for us)
    Returns the response payload (NOT yet encrypted):
      {team_id, node_name, sync_token, sync_key?}  (our token/key, for them)

    Raises ValueError on any invalid/expired/used code or undecryptable
    envelope — callers map that to a single opaque 403.
    """
    invite = client.store.consume_pairing_invite(
        _hash_code(code), redeemed_by="pending",
    )
    if invite is None:
        raise ValueError("invalid, expired, or already-used pairing code")
    team_id = str(invite["team_id"])

    try:
        request = json.loads(crypto.decrypt_bundle(envelope, code))
    except Exception as exc:  # noqa: BLE001 - opaque failure to caller
        raise ValueError(f"undecryptable pairing envelope: {exc}") from exc

    agent_id = str(request.get("agent_id") or "").strip()
    joiner_url = str(request.get("url") or "").strip()
    joiner_name = str(request.get("node_name") or "").strip() or agent_id
    joiner_token = str(request.get("sync_token") or "").strip() or None
    if not agent_id:
        raise ValueError("pairing request missing agent_id")

    # 1. Team membership for the joining agent (registry + ACL authority).
    client.store.touch_agent(agent_id)
    client.store.add_team_member(team_id, agent_id, actor="pairing-invite")

    # 2. Register the joiner as OUR peer, scoped to the invited team only.
    if joiner_url:
        client.store.add_peer(
            joiner_url, token=joiner_token,
            policy=f"team:{team_id}", name=joiner_name,
        )

    # 3. Hand back OUR credentials: a sync-scoped token (mint on first use —
    #    never the admin token) and the mesh key so encryption engages.
    own_sync_token = tokens.load_token(home, tier="sync")
    if not own_sync_token:
        own_sync_token = tokens.create_token(home, tier="sync")
    response: dict[str, Any] = {
        "team_id": team_id,
        "node_name": self_node_name,
        "sync_token": own_sync_token,
    }
    sync_key = crypto.load_sync_secret(home)
    if sync_key:
        response["sync_key"] = sync_key
    return response


def encrypt_payload(payload: dict, code: str) -> str:
    return crypto.encrypt_bundle(json.dumps(payload, ensure_ascii=False), code)


def decrypt_payload(envelope: str, code: str) -> dict:
    return json.loads(crypto.decrypt_bundle(envelope, code))


# --------------------------------------------------------------------------- #
# Client side (the joining node)
# --------------------------------------------------------------------------- #

def _post_redeem(url: str, body: dict, *, timeout: int = 15) -> dict:
    """POST the redeem request. Module-level so tests can bridge to a TestClient."""
    request = urllib.request.Request(
        url.rstrip("/") + REDEEM_PATH,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def join_with_code(
    client: Any,
    code: str,
    url: str,
    *,
    agent_id: str,
    my_url: str = "",
    node_name: str = "",
    home: str | None = None,
) -> dict:
    """Redeem `code` against the inviter at `url` and wire up sharing locally.

    On success both sides hold a team-scoped peer entry for each other and
    this node has the inviter's sync token (and mesh key, when the inviter
    uses one). Returns a report dict; raises ValueError on refusal.
    """
    code = code.strip()
    if not code.startswith(CODE_PREFIX):
        raise ValueError(f"pairing codes start with {CODE_PREFIX!r}")

    own_sync_token = tokens.load_token(home, tier="sync")
    if not own_sync_token:
        own_sync_token = tokens.create_token(home, tier="sync")

    request_payload = {
        "agent_id": agent_id,
        "node_name": node_name or agent_id,
        "url": my_url,
        "sync_token": own_sync_token,
    }
    # The code identifies the invite server-side (it is single-use and dies
    # with this exchange); the envelope keeps both sides' tokens and the mesh
    # key out of access logs and proxy captures.
    try:
        reply = _post_redeem(
            url, {"code": code, "envelope": encrypt_payload(request_payload, code)},
        )
    except urllib.error.HTTPError as exc:  # type: ignore[attr-defined]
        raise ValueError(
            "pairing refused (invalid, expired, or already-used code)"
            if exc.code in (400, 403) else f"pairing failed: HTTP {exc.code}"
        ) from exc

    payload = decrypt_payload(str(reply.get("envelope") or ""), code)
    team_id = str(payload["team_id"])
    their_token = str(payload.get("sync_token") or "") or None
    their_name = str(payload.get("node_name") or "")

    client.store.touch_agent(agent_id)
    client.store.add_peer(
        url, token=their_token, policy=f"team:{team_id}", name=their_name,
    )

    key_installed = False
    their_key = str(payload.get("sync_key") or "")
    if their_key:
        local_key = crypto.load_sync_secret(home)
        if local_key is None:
            crypto.save_sync_secret(home, their_key)
            key_installed = True
        elif local_key != their_key:
            raise ValueError(
                "the inviter uses a different sync key than this node — "
                "meshes must share ONE key; resolve manually (agent-memory sync genkey docs)"
            )

    return {
        "team_id": team_id,
        "peer_url": url.rstrip("/"),
        "peer_name": their_name,
        "sync_key_installed": key_installed,
    }
