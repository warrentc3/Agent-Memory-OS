"""Encrypted federation transport + the sync-scoped token tier.

Covers the two things added for secure multi-node sharing:
  1. `crypto` — app-layer bundle encryption (Fernet envelope) keyed by a mesh
     secret that never crosses the wire.
  2. The `sync` token tier — a federation-only credential that authorizes only
     `/api/node` + `/api/sync/*`, so joining the mesh does not hand over the
     full admin token.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent_memory_os import crypto, tokens
from agent_memory_os.web_app import create_app


# ---------- crypto unit ----------

def test_encrypt_round_trip_and_detection():
    ct = crypto.encrypt_bundle("line1\nline2\n", "mesh-secret")
    assert crypto.is_encrypted(ct)
    assert ct.startswith(crypto.ENVELOPE_PREFIX)
    assert crypto.decrypt_bundle(ct, "mesh-secret") == "line1\nline2\n"


def test_wrong_key_is_rejected():
    ct = crypto.encrypt_bundle("secret payload", "key-a")
    with pytest.raises(crypto.SyncCryptoError):
        crypto.decrypt_bundle(ct, "key-b")


def test_plaintext_passes_through():
    assert not crypto.is_encrypted('{"kind":"bundle"}')
    assert crypto.decrypt_bundle('{"kind":"bundle"}', "any") == '{"kind":"bundle"}'


def test_sync_secret_env_beats_file(tmp_path, monkeypatch):
    crypto.save_sync_secret(tmp_path, "from-file")
    monkeypatch.delenv("AGENT_MEMORY_SYNC_KEY", raising=False)
    assert crypto.load_sync_secret(tmp_path) == "from-file"
    monkeypatch.setenv("AGENT_MEMORY_SYNC_KEY", "from-env")
    assert crypto.load_sync_secret(tmp_path) == "from-env"


# ---------- sync token tier ----------

def test_sync_token_tier_file_and_prefix(tmp_path):
    full = tokens.create_token(tmp_path)
    sync = tokens.create_token(tmp_path, tier="sync")
    assert sync.startswith("amos_sync_")
    assert sync != full
    assert tokens.token_path(tmp_path, tier="sync").name == "web_sync_token"
    assert tokens.load_token(tmp_path, tier="sync") == sync


def test_sync_token_authorizes_only_federation_routes(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENT_MEMORY_SYNC_KEY", raising=False)
    tokens.create_token(tmp_path)                       # full (admin)
    sync = tokens.create_token(tmp_path, tier="sync")   # federation-only
    client = TestClient(create_app(home=tmp_path))
    h = {"Authorization": f"Bearer {sync}"}

    # allowed: node identity + sync export/import
    assert client.get("/api/node", headers=h).status_code == 200
    assert client.get("/api/sync/export", headers=h).status_code == 200
    # denied: ordinary memory API and the local mesh trigger
    assert client.get("/api/usage", headers=h).status_code == 403
    assert client.post("/api/sync/run", headers=h).status_code == 403
    # denied entirely without a token
    assert client.get("/api/node").status_code == 401


# ---------- encrypted export/import over the API ----------

def test_export_is_encrypted_and_import_decrypts_with_shared_key(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_MEMORY_SYNC_KEY", "shared-mesh-key")
    sync = tokens.create_token(tmp_path, tier="sync")
    client = TestClient(create_app(home=tmp_path))
    h = {"Authorization": f"Bearer {sync}"}

    exported = client.get("/api/sync/export", headers=h)
    assert exported.status_code == 200
    assert crypto.is_encrypted(exported.text)            # ciphertext on the wire
    assert '"bundle"' in crypto.decrypt_bundle(exported.text, "shared-mesh-key")

    # the same node (shares the key) accepts its own encrypted bundle back
    back = client.post("/api/sync/import", headers=h, content=exported.text)
    assert back.status_code == 200


def test_push_encrypts_payload_when_key_set(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_MEMORY_SYNC_KEY", "mesh-key")
    from agent_memory_os import sync as syncmod
    from agent_memory_os.client import MemoryClient

    captured: dict[str, str] = {}

    def fake_http(url, *, token=None, post=None):
        captured["post"] = post
        return "{}"

    monkeypatch.setattr(syncmod, "_http", fake_http)
    client = MemoryClient(home=tmp_path)
    try:
        syncmod.push_to_peer(client, "http://peer:8000", peer_token="t")
    finally:
        client.close()
    assert captured["post"].startswith(crypto.ENVELOPE_PREFIX)     # ciphertext left the node


def test_pull_decrypts_payload_when_key_matches(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_MEMORY_SYNC_KEY", "mesh-key")
    from agent_memory_os import sync as syncmod
    from agent_memory_os.client import MemoryClient

    enc = crypto.encrypt_bundle('{"kind":"bundle","version":3,"node_name":"peer"}\n', "mesh-key")
    monkeypatch.setattr(syncmod, "_http", lambda *a, **k: enc)
    client = MemoryClient(home=tmp_path)
    try:
        stats = syncmod.pull_from_peer(client, "http://peer:8000", peer_token="t")
    finally:
        client.close()
    assert isinstance(stats, dict)                                  # decrypted + merged cleanly


def test_import_rejects_encrypted_bundle_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENT_MEMORY_SYNC_KEY", raising=False)
    sync = tokens.create_token(tmp_path, tier="sync")
    client = TestClient(create_app(home=tmp_path))       # no mesh key configured
    h = {"Authorization": f"Bearer {sync}"}

    ciphertext = crypto.encrypt_bundle('{"kind":"bundle","version":3}\n', "some-key")
    resp = client.post("/api/sync/import", headers=h, content=ciphertext)
    assert resp.status_code == 400
    assert "AGENT_MEMORY_SYNC_KEY" in resp.json()["detail"]
