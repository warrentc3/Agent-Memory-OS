import sqlite3
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

import agent_memory_os.db as db_module
from agent_memory_os import MemoryClient, MemoryLink, MemoryRecord
from agent_memory_os.db import (
    LEGACY_CONTEXT_OWNER,
    MemoryStore,
    _validate_migration_plan,
)
from agent_memory_os.embedding import HashingEmbedder
from agent_memory_os.migrations import MIGRATIONS
from agent_memory_os.migrations.v018_session_recall_owner import (
    migrate as _migration_session_recall_owner,
)
from agent_memory_os.migrations.v019_mark_legacy_context import (
    migrate as _migration_mark_legacy_context,
)
from agent_memory_os.migrations.v020_canonicalize_expiry_timestamps import (
    migrate as _migration_canonicalize_expiry_timestamps,
)
from agent_memory_os.migrations.v022_timestamp_ubiquity import (
    migrate as migrate_timestamps_to_stamps,
)
from agent_memory_os.web_app import create_app

BACKDATED = "2020-01-01T00:00:00+00:00"


def test_store_add_requires_record_stamps(tmp_path):
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced d6884ee6@db-schema-v22.
    """
    store = MemoryStore(tmp_path / "memories.db")
    record = MemoryRecord(
        content="Canonical record timestamps.",
        created_at="2026-08-10T13:00:00.000000Z",
        updated_at="2026-08-10T13:00:01.000000Z",
        last_accessed_at="2026-08-10T13:00:02.000000Z",
    )
    record.expires_at = "2026-08-11T14:00:00+01:00"

    with pytest.raises(ValueError, match="expires_at must be a canonical stamp"):
        store.add(record)
    store.close()


def test_memory_link_requires_stamps(tmp_path):
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced d6884ee6@db-schema-v22.
    """
    store = MemoryStore(tmp_path / "memories.db")
    source = store.add(MemoryRecord(content="Source memory."))
    target = store.add(MemoryRecord(content="Target memory."))
    with pytest.raises(ValueError, match="created_at must be a canonical stamp"):
        MemoryLink(
            src_id=source.id,
            dst_id=target.id,
            created_at="2026-08-10T14:00:00+01:00",
        )
    store.close()


def test_tombstone_cursors_require_stamps(tmp_path):
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced d6884ee6@db-schema-v22.
    """
    store = MemoryStore(tmp_path / "memories.db")
    deleted_at = "2026-08-10T12:00:00.000001Z"
    store.conn.execute(
        "INSERT INTO tombstones(id, deleted_at) VALUES (?, ?)",
        ("deleted-memory", deleted_at),
    )
    store.conn.execute(
        "INSERT INTO org_tombstones(kind, id, deleted_at) VALUES (?, ?, ?)",
        ("project", "deleted-project", deleted_at),
    )
    store.conn.commit()

    since = "2026-08-10T12:00:00.000000Z"

    assert store.list_tombstones(since=since) == [
        ("deleted-memory", deleted_at)
    ]
    assert store.list_org_tombstones(since=since) == [
        ("project", "deleted-project", deleted_at)
    ]
    with pytest.raises(ValueError, match="timestamp must match"):
        store.list_tombstones(since="2026-08-10T12:00:00+00:00")
    with pytest.raises(ValueError, match="timestamp must match"):
        store.list_org_tombstones(since="2026-08-10T12:00:00+00:00")
    store.close()


def test_migrations_recorded_and_versioned(tmp_path):
    """Lineage:
    main: introduced 34f95eac@db-schema-v3; c213e8b4@db-schema-v4; 512e2197@db-schema-v6.
    """
    client = MemoryClient(home=tmp_path)
    assert client.store.schema_version() == len(MIGRATIONS)
    rows = client.store.conn.execute(
        "SELECT version, description FROM schema_migrations ORDER BY version"
    ).fetchall()
    assert [row["version"] for row in rows] == [version for version, _, _ in MIGRATIONS]


def test_migration_plan_rejects_duplicate_versions():
    """Lineage:
    main: introduced f250538d@db-schema-v17.
    """
    with pytest.raises(RuntimeError, match="duplicate migration versions"):
        _validate_migration_plan([(1, "first", object()), (1, "second", object())])


def test_migration_plan_rejects_out_of_order_versions():
    """Lineage:
    main: introduced f250538d@db-schema-v17.
    """
    with pytest.raises(RuntimeError, match="strictly increasing"):
        _validate_migration_plan([(2, "second", object()), (1, "first", object())])


def test_migration_version_description_mismatch_fails_closed(tmp_path):
    """Lineage:
    main: introduced 7da7825b@db-schema-v17; f250538d@db-schema-v17.
    """
    client = MemoryClient(home=tmp_path)
    client.close()

    db_path = tmp_path / "memories.db"
    version, _, _ = MIGRATIONS[-1]
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE schema_migrations SET description = ? WHERE version = ?",
        ("a different migration", version),
    )
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError, match=rf"migration {version} history mismatch"):
        MemoryStore(db_path)


def test_legacy_database_upgrades_in_place(tmp_path):
    """Lineage:
    main: introduced 34f95eac@db-schema-v3; c213e8b4@db-schema-v4; 512e2197@db-schema-v6.
    time-helper: changed dc608742@db-schema-v21.
    """
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
    assert {"pinned", "decay_policy", "access_count", "RecVersion"} <= columns
    record = store.get("mem_legacy")
    assert record.content == "old row" and record.pinned is False
    assert store.conn.execute(
        "SELECT RecVersion FROM memories WHERE id = 'mem_legacy'"
    ).fetchone()[0] == 0

    store.update_memory("mem_legacy", content="new row")
    assert store.conn.execute(
        "SELECT RecVersion FROM memories WHERE id = 'mem_legacy'"
    ).fetchone()[0] == 1

    store.record_recall(["mem_legacy"], helpful=True)
    assert store.conn.execute(
        "SELECT RecVersion FROM memories WHERE id = 'mem_legacy'"
    ).fetchone()[0] == 1
    store.close()


def test_session_recall_owner_migration_preserves_legacy_rows_and_is_idempotent():
    """Lineage:
    main: introduced bd659853@db-schema-v18.
    direct migration binding: v18.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE session_recall_log (
          session_id TEXT NOT NULL,
          memory_id TEXT NOT NULL,
          delivered_at TEXT NOT NULL,
          PRIMARY KEY (session_id, memory_id)
        );
        INSERT INTO session_recall_log VALUES ('session-1', 'mem_1', '2026-01-01');
        """
    )

    _migration_session_recall_owner(conn)
    _migration_session_recall_owner(conn)

    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(session_recall_log)").fetchall()
    }
    row = conn.execute(
        "SELECT owner, session_id, memory_id FROM session_recall_log"
    ).fetchone()
    assert "owner" in columns
    assert tuple(row) == ("", "session-1", "mem_1")
    conn.close()


def test_legacy_context_migration_marks_unscoped_rows_and_is_idempotent():
    """Lineage:
    main: introduced dfc218f7@db-schema-v19.
    direct migration binding: v19.
    """
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE memories (id TEXT, owner TEXT, type TEXT);
        CREATE TABLE memories_archive (id TEXT, owner TEXT, type TEXT);
        CREATE TABLE session_recall_log (
          owner TEXT NOT NULL,
          session_id TEXT NOT NULL,
          memory_id TEXT NOT NULL,
          delivered_at TEXT NOT NULL,
          PRIMARY KEY (owner, session_id, memory_id)
        );
        INSERT INTO memories VALUES ('snapshot-live', 'default', 'snapshot');
        INSERT INTO memories VALUES ('ordinary', 'default', 'note');
        INSERT INTO memories_archive VALUES ('snapshot-archived', 'default', 'snapshot');
        INSERT INTO session_recall_log VALUES ('', 'session-1', 'ordinary', '2026-01-01');
        """
    )

    _migration_mark_legacy_context(conn)
    _migration_mark_legacy_context(conn)

    assert conn.execute(
        "SELECT owner FROM memories WHERE id = 'snapshot-live'"
    ).fetchone()[0] == LEGACY_CONTEXT_OWNER
    assert conn.execute(
        "SELECT owner FROM memories WHERE id = 'ordinary'"
    ).fetchone()[0] == "default"
    assert conn.execute(
        "SELECT owner FROM memories_archive WHERE id = 'snapshot-archived'"
    ).fetchone()[0] == LEGACY_CONTEXT_OWNER
    assert conn.execute(
        "SELECT owner FROM session_recall_log"
    ).fetchone()[0] == LEGACY_CONTEXT_OWNER
    conn.close()


def test_legacy_unscoped_context_remains_available_to_requesters(tmp_path):
    """Lineage:
    main: introduced dfc218f7@db-schema-v19.
    """
    client = MemoryClient(home=tmp_path)
    legacy_snapshot = client.offload_context(
        {"step": 1, "era": "legacy"},
        "upgrade-session",
        owner=LEGACY_CONTEXT_OWNER,
    )
    delivered = client.add("Legacy delivered marker.", owner="default")
    client.store.record_delivery(
        "upgrade-session",
        [delivered.id],
        owner=LEGACY_CONTEXT_OWNER,
    )

    assert client.reload_context(
        "upgrade-session",
        requester_agent_id="alice",
    ) == {"step": 1, "era": "legacy"}
    assert client.reload_context(
        "upgrade-session",
        snapshot_id=legacy_snapshot,
        requester_agent_id="bob",
    ) == {"step": 1, "era": "legacy"}
    assert delivered.id in client.store.delivered_ids(
        "upgrade-session",
        owner="alice",
    )

    current_snapshot = client.offload_context(
        {"step": 2, "era": "requester"},
        "upgrade-session",
        owner="alice",
    )
    assert client.get(current_snapshot).source["snapshot_index"] == 1
    assert client.reload_context(
        "upgrade-session",
        requester_agent_id="alice",
    ) == {"step": 2, "era": "requester"}


def test_database_at_migration_18_upgrades_legacy_context_in_place(tmp_path):
    """Lineage:
    main: introduced dfc218f7@db-schema-v19; 1287c647@db-schema-v20.
    direct migration binding: v18 -> v19.
    """
    client = MemoryClient(home=tmp_path)
    snapshot_id = client.offload_context(
        {"step": 1},
        "real-upgrade-session",
        owner="default",
    )
    delivered = client.add("Pre-upgrade delivered marker.", owner="default")
    client.store.record_delivery(
        "real-upgrade-session",
        [delivered.id],
        owner=None,
    )
    client.close()

    db_path = tmp_path / "memories.db"
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM schema_migrations WHERE version = 19")
    conn.commit()
    conn.close()

    upgraded = MemoryClient(home=tmp_path)
    assert upgraded.store.schema_version() == MIGRATIONS[-1][0]
    assert upgraded.get(snapshot_id).owner == LEGACY_CONTEXT_OWNER
    assert upgraded.reload_context(
        "real-upgrade-session",
        requester_agent_id="alice",
    ) == {"step": 1}
    assert delivered.id in upgraded.store.delivered_ids(
        "real-upgrade-session",
        owner="alice",
    )


def test_legacy_expiry_migration_canonicalizes_python_iso_forms():
    """Lineage:
    main: introduced 1287c647@db-schema-v20.
    direct migration binding: v20.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE memories (id TEXT PRIMARY KEY, expires_at TEXT);
        CREATE TABLE memories_archive (id TEXT PRIMARY KEY, expires_at TEXT);
        INSERT INTO memories VALUES ('future', '20990101T000000+00:00');
        INSERT INTO memories_archive VALUES ('past', '20000101T000000+00:00');
        INSERT INTO memories VALUES ('unknown', 'someday');
        """
    )

    _migration_canonicalize_expiry_timestamps(conn)
    _migration_canonicalize_expiry_timestamps(conn)

    assert conn.execute(
        "SELECT expires_at FROM memories WHERE id = 'future'"
    ).fetchone()[0] == "2099-01-01T00:00:00+00:00"
    assert conn.execute(
        "SELECT expires_at FROM memories_archive WHERE id = 'past'"
    ).fetchone()[0] == "2000-01-01T00:00:00+00:00"
    assert conn.execute(
        "SELECT expires_at FROM memories WHERE id = 'unknown'"
    ).fetchone()[0] == "someday"
    conn.close()


def test_timestamp_ubiquity_migrates_supported_columns():
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced working-tree@db-schema-v22.
    direct migration binding: v22.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE memories (
          created_at TEXT, updated_at TEXT, acl_updated_at TEXT,
          expires_at TEXT, last_accessed_at TEXT
        );
        CREATE TABLE memories_archive (
          created_at TEXT, updated_at TEXT, expires_at TEXT,
          last_accessed_at TEXT, archived_at TEXT
        );
        CREATE TABLE memory_links (
          created_at TEXT, updated_at TEXT, last_activated_at TEXT
        );
        CREATE TABLE memory_links_archive (
          created_at TEXT, updated_at TEXT, last_activated_at TEXT,
          archived_at TEXT
        );
        CREATE TABLE recall_profiles (
          agent_id TEXT PRIMARY KEY, updated_at TEXT NOT NULL
        );
        CREATE TABLE teams (
          id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT
        );
        CREATE TABLE projects (
          id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT
        );
        CREATE TABLE tombstones (
          id TEXT PRIMARY KEY, deleted_at TEXT NOT NULL
        );
        CREATE TABLE org_tombstones (
          kind TEXT NOT NULL, id TEXT NOT NULL, deleted_at TEXT NOT NULL,
          PRIMARY KEY (kind, id)
        );
        INSERT INTO memories VALUES (
          '2026-01-01T01:00:00+01:00', '2026-01-01T01:00:00+01:00',
          NULL, '2026-01-01T01:00:00+01:00',
          'someday'
        );
        INSERT INTO memories_archive VALUES (
          '2026-01-01T01:00:00+01:00', '2026-01-01T01:00:00+01:00',
          '2026-01-01T01:00:00+01:00', '2026-01-01T01:00:00+01:00',
          '2026-01-01T01:00:00+01:00'
        );
        INSERT INTO memory_links VALUES (
          '2026-01-01T01:00:00+01:00', '2026-01-01T01:00:00+01:00',
          ''
        );
        INSERT INTO memory_links_archive VALUES (
          '2026-01-01T01:00:00+01:00', '2026-01-01T01:00:00+01:00',
          '', '2026-01-01T01:00:00+01:00'
        );
        INSERT INTO recall_profiles VALUES (
          'profile-agent', '2026-01-01T01:00:00+01:00'
        );
        INSERT INTO teams VALUES (
          'apollo', '2026-01-01T01:00:00+01:00',
          '2026-01-01T01:00:00+01:00'
        );
        INSERT INTO projects VALUES (
          'landing', '2026-01-01T01:00:00+01:00',
          '2026-01-01T01:00:00+01:00'
        );
        INSERT INTO tombstones VALUES (
          'deleted-memory', '2026-01-01T01:00:00+01:00'
        );
        INSERT INTO org_tombstones VALUES (
          'team', 'retired-team', '2026-01-01T01:00:00+01:00'
        );
        """
    )

    migrate_timestamps_to_stamps(conn)
    migrate_timestamps_to_stamps(conn)

    stamp = "2026-01-01T00:00:00.000000Z"
    assert tuple(conn.execute("SELECT * FROM memories").fetchone()) == (
        stamp,
        stamp,
        stamp,
        stamp,
        "someday",
    )
    assert set(conn.execute("SELECT * FROM memories_archive").fetchone()) == {stamp}
    assert tuple(conn.execute("SELECT * FROM memory_links").fetchone()) == (
        stamp,
        stamp,
        None,
    )
    assert tuple(conn.execute("SELECT * FROM memory_links_archive").fetchone()) == (
        stamp,
        stamp,
        None,
        stamp,
    )
    assert conn.execute(
        "SELECT updated_at FROM recall_profiles WHERE agent_id = 'profile-agent'"
    ).fetchone()[0] == stamp
    assert tuple(
        conn.execute(
            "SELECT created_at, updated_at FROM teams WHERE id = 'apollo'"
        ).fetchone()
    ) == (stamp, stamp)
    assert tuple(
        conn.execute(
            "SELECT created_at, updated_at FROM projects WHERE id = 'landing'"
        ).fetchone()
    ) == (stamp, stamp)
    assert conn.execute(
        "SELECT deleted_at FROM tombstones WHERE id = 'deleted-memory'"
    ).fetchone()[0] == stamp
    assert conn.execute(
        "SELECT deleted_at FROM org_tombstones "
        "WHERE kind = 'team' AND id = 'retired-team'"
    ).fetchone()[0] == stamp
    conn.close()


def test_database_upgrade_keeps_basic_format_future_expiry_visible(tmp_path):
    """Lineage:
    main: introduced 1287c647@db-schema-v20.
    time-helper: changed dc608742@db-schema-v21.
    time-helper: restored working-tree@db-schema-v22 to the v20 contract.
    direct migration binding: v20.
    """
    client = MemoryClient(home=tmp_path)
    memory = client.add("Future basic-format expiry sentinel.")
    client.store.conn.execute(
        "UPDATE memories SET expires_at = ? WHERE id = ?",
        ("20990101T000000+00:00", memory.id),
    )
    client.store.conn.execute("DELETE FROM schema_migrations WHERE version = 20")
    client.store.conn.commit()
    client.close()

    upgraded = MemoryClient(home=tmp_path)
    assert upgraded.get(memory.id).expires_at == "2099-01-01T00:00:00+00:00"
    assert memory.id in {
        hit.record.id
        for hit in upgraded.search("future basic format expiry sentinel")
    }
    assert upgraded.dashboard_stats()["expired"] == 0


def test_microsecond_future_expiry_stays_live_across_store_paths(
    tmp_path,
    monkeypatch,
):
    fixed_now = datetime(2099, 1, 1, tzinfo=UTC)
    now_stamp = "2099-01-01T00:00:00.000000Z"
    future_stamp = "2099-01-01T00:00:00.000001Z"
    monkeypatch.setattr(db_module, "utc_now_dt", lambda: fixed_now)
    monkeypatch.setattr(db_module, "utc_now_stamp", lambda: now_stamp)
    client = MemoryClient(home=tmp_path)
    ordinary = client.add(
        "Microsecond future expiry probe.",
        visibility=["global"],
        expires_at=future_stamp,
    )

    assert client.get_visible(ordinary.id) is not None
    assert ordinary.id in {
        hit.record.id for hit in client.search("microsecond future expiry probe")
    }
    assert ordinary.id in {
        hit.record.id for hit in client.search("unmatched fallback query")
    }
    assert ordinary.id in {
        record.id for record in client.store.top_records_by_type("note")
    }

    authority = client.add(
        "Microsecond future authority probe.",
        visibility=["global"],
        source={"permanence": True, "weight": 10},
        expires_at=future_stamp,
    )
    boundary = client.add(
        "Exact expiry boundary probe.",
        visibility=["global"],
        expires_at=now_stamp,
    )
    assert authority.id in {record.id for record in client.store.bedrock_records()}
    assert client.get_visible(boundary.id) is None
    assert client.dashboard_stats()["expired"] == 1

    result = client.store.run_retention(decayed_half_lives=None)

    assert result["archived_expired"] == 1
    assert client.get(ordinary.id) is not None
    assert client.get(authority.id) is not None
    assert client.get(boundary.id) is None


def test_legacy_offset_future_expiry_stays_live_across_store_paths(
    tmp_path,
    monkeypatch,
):
    fixed_now = datetime(2099, 1, 1, tzinfo=UTC)
    now_stamp = "2099-01-01T00:00:00.000000Z"
    legacy_future = "2099-01-01T00:00:00-05:00"
    monkeypatch.setattr(db_module, "utc_now_dt", lambda: fixed_now)
    monkeypatch.setattr(db_module, "utc_now_stamp", lambda: now_stamp)
    client = MemoryClient(home=tmp_path)
    memory = client.add(
        "Legacy offset future expiry probe.",
        visibility=["global"],
        source={"permanence": True, "weight": 10},
        expires_at="2099-01-01T05:00:00.000000Z",
    )
    client.store.conn.execute(
        "UPDATE memories SET expires_at = ? WHERE id = ?",
        (legacy_future, memory.id),
    )
    client.store.conn.commit()

    assert client.get_visible(memory.id) is not None
    assert memory.id in {
        hit.record.id for hit in client.search("legacy offset future expiry probe")
    }
    assert memory.id in {
        hit.record.id for hit in client.search("unmatched legacy fallback query")
    }
    assert memory.id in {
        record.id for record in client.store.top_records_by_type("note")
    }
    assert memory.id in {record.id for record in client.store.bedrock_records()}
    assert client.dashboard_stats()["expired"] == 0

    result = client.store.run_retention(decayed_half_lives=None)

    assert result["archived_expired"] == 0
    assert client.get(memory.id) is not None


def test_integrity_check_detects_fts_drift(tmp_path):
    """Lineage:
    main: introduced 34f95eac@db-schema-v3.
    """
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
    """Lineage:
    main: introduced 34f95eac@db-schema-v3.
    time-helper: changed d6884ee6@db-schema-v22.
    """
    client = MemoryClient(home=tmp_path)
    expired = client.add(
        "Expired runbook.", visibility=["global"], expires_at="2020-01-01T00:00:00.000000Z"
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
    """Lineage:
    main: introduced 34f95eac@db-schema-v3.
    """
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
    """Lineage:
    main: introduced 34f95eac@db-schema-v3.
    """
    embedder = HashingEmbedder(dim=64)
    a1 = embedder("Kubernetes cluster restart procedure")
    a2 = embedder("Kubernetes cluster restart procedure")
    b = embedder("banana bread recipe")

    assert a1 == a2
    assert abs(sum(v * v for v in a1) - 1.0) < 1e-9
    assert a1 != b


def test_auto_semantic_index_recalls_and_refreshes(tmp_path):
    """Lineage:
    main: introduced 34f95eac@db-schema-v3.
    """
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
    """Lineage:
    main: introduced 34f95eac@db-schema-v3; c213e8b4@db-schema-v4; 512e2197@db-schema-v6.
    time-helper: changed d6884ee6@db-schema-v22.
    """
    app = create_app(home=tmp_path)
    web = TestClient(app)
    expired = web.post(
        "/api/memories",
        json={"content": "Expired via API.", "visibility": ["global"],
              "expires_at": "2020-01-01T00:00:00.000000Z"},
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
