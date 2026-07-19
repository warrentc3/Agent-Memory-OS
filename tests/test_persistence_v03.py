import sqlite3

import pytest
from fastapi.testclient import TestClient

from agent_memory_os import MemoryClient
from agent_memory_os.db import MIGRATIONS, MemoryStore
from agent_memory_os.embedding import HashingEmbedder
from agent_memory_os.web_app import create_app

BACKDATED = "2020-01-01T00:00:00+00:00"


def test_migrations_recorded_and_versioned(tmp_path):
    client = MemoryClient(home=tmp_path)
    assert client.store.schema_version() == len(MIGRATIONS)
    rows = client.store.conn.execute(
        "SELECT version, description FROM schema_migrations ORDER BY version"
    ).fetchall()
    assert [row["version"] for row in rows] == [version for version, _, _ in MIGRATIONS]


def test_migration_version_description_mismatch_fails_closed(tmp_path):
    client = MemoryClient(home=tmp_path)
    client.close()

    db_path = tmp_path / "memories.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE schema_migrations SET description = ? WHERE version = 17",
        ("requester-scoped session recall delivery log",),
    )
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError, match="migration 17 history mismatch"):
        MemoryStore(db_path)


def test_legacy_database_upgrades_in_place(tmp_path):
    db_path = tmp_path / "memories.db"
    legacy = sqlite3.connect(db_path)
    legacy.executescript(
        """
        CREATE TABLE memories (
          id TEXT PRIMARY KEY, owner TEXT NOT NULL, scope TEXT NOT NULL,
          type TEXT NOT NULL, content TEXT NOT NULL, summary TEXT NOT NULL,
          tags TEXT NOT NULL DEFAULT '[]', visibility TEXT NOT NULL DEFAULT '[]',
          source TEXT NOT NULL DEFAULT '{}', confidence REAL NOT NULL DEFAULT 0.8,
          importance REAL NOT NULL DEFAULT 0.5, created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL, expires_at TEXT
        );
        INSERT INTO memories VALUES ('mem_legacy', 'a', 'user', 'note', 'old row',
          'old row', '[]', '[]', '{}', 0.8, 0.5, '2026-01-01T00:00:00+00:00',
          '2026-01-01T00:00:00+00:00', NULL);
        """
    )
    legacy.close()

    store = MemoryStore(db_path)

    assert store.schema_version() == len(MIGRATIONS)
    columns = {row["name"] for row in store.conn.execute("PRAGMA table_info(memories)")}
    assert {"pinned", "decay_policy", "access_count"} <= columns
    record = store.get("mem_legacy")
    assert record.content == "old row" and record.pinned is False
    store.close()


def test_integrity_check_detects_fts_drift(tmp_path):
    client = MemoryClient(home=tmp_path)
    memory = client.add("Integrity probe memory.", visibility=["global"])
    assert client.integrity_check()["ok"] is True

    client.store.conn.execute("DELETE FROM memories_fts WHERE id = ?", (memory.id,))
    client.store.conn.commit()
    report = client.integrity_check()

    assert report["ok"] is False
    assert report["fts_in_sync"] is False
    # rebuild_indexes is the documented repair path
    client.rebuild_indexes()
    assert client.integrity_check()["ok"] is True


def test_retention_archives_expired_and_restore_revives(tmp_path):
    client = MemoryClient(home=tmp_path)
    expired = client.add(
        "Expired runbook.", visibility=["global"], expires_at="2020-01-01T00:00:00+00:00"
    )
    keeper = client.add("Active memory.", visibility=["global"])
    client.link(expired.id, keeper.id, weight=0.5)

    result = client.run_retention()

    assert result["archived_expired"] == 1
    assert client.get(expired.id) is None
    assert client.stats()["links"] == 0
    archived = client.list_archived()
    assert archived[0]["id"] == expired.id and archived[0]["archive_reason"] == "expired"
    assert client.dashboard_stats()["archived"] == 1

    restored = client.restore_archived(expired.id)
    assert restored.expires_at is None
    assert client.get(expired.id) is not None
    assert client.list_archived() == []
    with pytest.raises(KeyError):
        client.restore_archived(expired.id)


def test_retention_decay_archiving_protects_pinned_and_authority(tmp_path):
    client = MemoryClient(home=tmp_path)
    stale = client.add("Ordinary stale note.", visibility=["global"])
    pinned = client.add("Pinned stale note.", visibility=["global"], pinned=True)
    authority = client.add(
        "Authority stale note.", visibility=["global"],
        source={"permanence": True, "weight": 10},
    )
    for memory in (stale, pinned, authority):
        client.store.conn.execute(
            "UPDATE memories SET updated_at = ?, created_at = ? WHERE id = ?",
            (BACKDATED, BACKDATED, memory.id),
        )
    client.store.conn.commit()
    client.cache.clear()

    result = client.run_retention(decayed_half_lives=4)

    assert result["archived_decayed"] == 1
    assert client.get(stale.id) is None
    assert client.get(pinned.id) is not None
    assert client.get(authority.id) is not None


def test_hashing_embedder_is_deterministic_and_normalized():
    embedder = HashingEmbedder(dim=64)
    a1 = embedder("Kubernetes cluster restart procedure")
    a2 = embedder("Kubernetes cluster restart procedure")
    b = embedder("banana bread recipe")

    assert a1 == a2
    assert abs(sum(v * v for v in a1) - 1.0) < 1e-9
    assert a1 != b


def test_auto_semantic_index_recalls_and_refreshes(tmp_path):
    pytest.importorskip("turbovec")
    client = MemoryClient(home=tmp_path, semantic="auto")
    assert client.semantic_enabled is True
    target = client.add("Kubernetes cluster restart procedure steps.", visibility=["global"])
    client.add("Banana bread baking recipe with walnuts.", visibility=["global"])

    provider = client.store.candidate_providers[0]
    top = list(provider.candidates("restart the kubernetes cluster", limit=1))
    assert top[0].memory_id == target.id

    fresh = client.add("Kubernetes pod restart troubleshooting guide.", visibility=["global"])
    ids = {c.memory_id for c in provider.candidates("kubernetes restart", limit=3)}
    assert fresh.id in ids  # index rebuilt after the write

    hits = client.search("kubernetes restart", requester_agent_id="neo")
    assert any("semantic:turbovec-auto" in hit.reason for hit in hits)


def test_web_api_retention_archive_and_integrity(tmp_path):
    app = create_app(home=tmp_path)
    web = TestClient(app)
    expired = web.post(
        "/api/memories",
        json={"content": "Expired via API.", "visibility": ["global"],
              "expires_at": "2020-01-01T00:00:00+00:00"},
    ).json()

    run = web.post("/api/retention")
    assert run.status_code == 200
    assert run.json()["archived_expired"] == 1

    listed = web.get("/api/archive").json()["archived"]
    assert listed[0]["id"] == expired["id"]

    restored = web.post(f"/api/archive/{expired['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["expires_at"] is None
    assert web.post("/api/archive/mem_missing/restore").status_code == 404

    integrity = web.get("/api/integrity").json()
    from agent_memory_os.db import MIGRATIONS as _m
    assert integrity["ok"] is True and integrity["schema_version"] == len(_m)
