"""Federation trust model (v0.11) — per-peer scope, tombstones, provenance,
timestamp convergence."""

import pytest

from agent_memory_os import MemoryClient
from agent_memory_os import sync as sync_module


def test_shared_export_excludes_private(tmp_path):
    host = MemoryClient(home=tmp_path / "h")
    host.add("public knowledge", owner="a", visibility=["global"])
    host.add("team thing", owner="a", visibility=["team:apollo"])
    priv = host.add("private secret", owner="a", visibility=[])

    bundle = tmp_path / "shared.jsonl"
    counts = host.export_bundle(bundle, include_private=False)
    assert counts["memories"] == 2  # private excluded

    target = MemoryClient(home=tmp_path / "t")
    target.import_bundle(bundle)
    assert target.get(priv.id) is None  # never left the machine


def test_full_export_includes_private(tmp_path):
    host = MemoryClient(home=tmp_path / "h")
    priv = host.add("private secret", owner="a", visibility=[])
    bundle = tmp_path / "full.jsonl"
    host.export_bundle(bundle, include_private=True)
    target = MemoryClient(home=tmp_path / "t")
    target.import_bundle(bundle)
    assert target.get(priv.id) is not None


def test_add_peer_policy_default_is_shared_and_validated(tmp_path):
    host = MemoryClient(home=tmp_path)
    info = host.store.add_peer("http://peer:8000")
    assert info["policy"] == "shared"
    host.store.add_peer("http://peer2:8000", policy="full")
    assert host.store.peer_policy("http://peer2:8000") == "full"
    host.store.add_peer("http://peer3:8000", policy="team:apollo")
    assert host.store.peer_policy("http://peer3:8000") == "team:apollo"
    with pytest.raises(ValueError):
        host.store.add_peer("http://peer4:8000", policy="whatever")


def test_tombstone_propagates_deletion(tmp_path):
    a = MemoryClient(home=tmp_path / "a")
    b = MemoryClient(home=tmp_path / "b")
    mem = a.add("ephemeral note", owner="x", visibility=["global"])

    bundle = tmp_path / "b1.jsonl"
    a.export_bundle(bundle, include_private=False)
    b.import_bundle(bundle)
    assert b.get(mem.id) is not None

    # A deletes; the tombstone must travel and remove it on B.
    a.delete(mem.id)
    bundle2 = tmp_path / "b2.jsonl"
    a.export_bundle(bundle2, include_private=False)
    stats = b.import_bundle(bundle2)
    assert stats["tombstones_applied"] == 1
    assert b.get(mem.id) is None


def test_deleted_memory_does_not_resurrect(tmp_path):
    a = MemoryClient(home=tmp_path / "a")
    b = MemoryClient(home=tmp_path / "b")
    mem = b.add("lives on B", owner="x", visibility=["global"])

    # A learns then deletes it (tombstone on A).
    bundle_b = tmp_path / "fromb.jsonl"
    b.export_bundle(bundle_b, include_private=False)
    a.import_bundle(bundle_b)
    a.delete(mem.id)

    # B still has it; A re-imports B's bundle — the tombstone must win.
    stats = a.import_bundle(bundle_b)
    assert a.get(mem.id) is None
    assert stats["memories_added"] == 0


def test_semi_trusted_peer_cannot_impersonate_local_agent(tmp_path):
    target = MemoryClient(home=tmp_path / "t")
    target.register_agent("alice", kind="hermes", teams=["apollo"])

    # A bundle forging a memory authored by local agent "alice".
    forged = tmp_path / "forged.jsonl"
    forged.write_text(
        '{"kind": "bundle", "version": 2}\n'
        '{"kind": "memory", "id": "mem_forged_1", "owner": "alice", '
        '"scope": "user", "type": "note", "content": "trust me", "summary": "", '
        '"tags": "[]", "visibility": "[\\"global\\"]", "source": "{}", '
        '"confidence": 0.8, "importance": 0.5, "created_at": "2026-01-01T00:00:00+00:00", '
        '"updated_at": "2026-01-01T00:00:00+00:00", "decay_policy": "exponential", '
        '"decay_half_life_days": 30.0, "access_count": 0, "pinned": 0, '
        '"helpful_count": 0, "unhelpful_count": 0}\n',
        encoding="utf-8",
    )
    stats = target.import_bundle(forged, source_peer="http://evil:8000", trusted=False)
    assert stats["memories_skipped"] == 1
    assert target.get("mem_forged_1") is None

    # A full-trust import (own node) is allowed to carry any owner.
    stats2 = target.import_bundle(forged, trusted=True)
    assert target.get("mem_forged_1") is not None


def test_semi_trusted_import_records_provenance(tmp_path):
    target = MemoryClient(home=tmp_path / "t")
    bundle = tmp_path / "peer.jsonl"
    bundle.write_text(
        '{"kind": "bundle", "version": 2}\n'
        '{"kind": "memory", "id": "mem_peer_1", "owner": "peerbot", '
        '"scope": "user", "type": "note", "content": "shared insight", "summary": "", '
        '"tags": "[]", "visibility": "[\\"global\\"]", "source": "{}", '
        '"confidence": 0.8, "importance": 0.5, "created_at": "2026-01-01T00:00:00+00:00", '
        '"updated_at": "2026-01-01T00:00:00+00:00", "decay_policy": "exponential", '
        '"decay_half_life_days": 30.0, "access_count": 0, "pinned": 0, '
        '"helpful_count": 0, "unhelpful_count": 0}\n',
        encoding="utf-8",
    )
    target.import_bundle(bundle, source_peer="http://peer:8000", trusted=False)
    rec = target.get("mem_peer_1")
    assert rec is not None
    assert rec.source.get("synced_from") == "http://peer:8000"


def test_same_second_edit_converges_by_content_tiebreak(tmp_path):
    a = MemoryClient(home=tmp_path / "a")
    b = MemoryClient(home=tmp_path / "b")
    mem = a.add("origin", owner="x", visibility=["global"])
    seed = tmp_path / "seed.jsonl"
    a.export_bundle(seed, include_private=False)
    b.import_bundle(seed)

    # Force identical updated_at on both, different content.
    ts = "2026-05-05T05:05:05+00:00"
    a.store.conn.execute("UPDATE memories SET content='aaa', updated_at=? WHERE id=?", (ts, mem.id))
    a.store.conn.commit()
    b.store.conn.execute("UPDATE memories SET content='zzz', updated_at=? WHERE id=?", (ts, mem.id))
    b.store.conn.commit()

    # Cross-import both directions; both must land on the same winner ('zzz').
    ba = tmp_path / "ba.jsonl"; b.export_bundle(ba, include_private=False); a.import_bundle(ba)
    ab = tmp_path / "ab.jsonl"; a.export_bundle(ab, include_private=False); b.import_bundle(ab)
    assert a.get(mem.id).content == b.get(mem.id).content == "zzz"


def test_mesh_sync_does_not_leak_private(tmp_path, monkeypatch):
    from agent_memory_os.web_app import create_app
    from fastapi.testclient import TestClient

    host_a = MemoryClient(home=tmp_path / "a")
    peer_app = TestClient(create_app(home=tmp_path / "b"))
    host_a.add("A public", owner="a", visibility=["global"])
    host_a.add("A private", owner="a", visibility=[])
    host_a.store.add_peer("http://peer-b:8000", policy="shared")

    def fake_http(url, *, token, post=None):
        path = url.replace("http://peer-b:8000", "")
        if post is None:
            return peer_app.get(path).text
        return peer_app.post(path, content=post,
                             headers={"content-type": "application/x-ndjson"}).text

    monkeypatch.setattr(sync_module, "_http", fake_http)
    sync_module.sync_all_peers(host_a)

    # Peer B received the public memory but never the private one.
    exported = peer_app.get("/api/sync/export").text
    assert "A public" in exported
    assert "A private" not in exported
    host_a.close()
