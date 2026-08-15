"""Regression tests for FTS trigger consistency.

The original AFTER UPDATE / AFTER DELETE triggers used the FTS5 'delete'
command, which is only valid for external-content/contentless tables and
raised 'SQL logic error' on every memories UPDATE/DELETE.
"""

from agent_memory_os import MemoryClient


def test_update_content_refreshes_fts_index(tmp_path):
    """Lineage:
    main: introduced ea0faea3@pre-migration-registry.
    """
    client = MemoryClient(home=tmp_path)
    record = client.add("Original espresso tasting notes.", visibility=["global"])

    client.store.update_content(record.id, "Updated matcha tasting notes.")
    client.cache.clear()

    assert client.search("matcha", requester_agent_id="neo") != []
    espresso_hits = client.search("espresso", requester_agent_id="neo")
    assert record.id not in {hit.record.id for hit in espresso_hits if hit.reason.startswith("fts")}


def test_delete_removes_memory_from_fts_index(tmp_path):
    """Lineage:
    main: introduced ea0faea3@pre-migration-registry.
    """
    client = MemoryClient(home=tmp_path)
    record = client.add("Disposable reminder about espresso beans.", visibility=["global"])
    keeper = client.add("Keeper note about grinder settings.", visibility=["global"])

    assert client.store.delete(record.id) is True
    client.cache.clear()

    hits = client.search("espresso grinder", requester_agent_id="neo")
    ids = {hit.record.id for hit in hits}
    assert record.id not in ids
    assert keeper.id in ids


def test_legacy_broken_triggers_are_migrated(tmp_path):
    """Lineage:
    main: introduced ea0faea3@pre-migration-registry; 34f95eac@db-schema-v3.
    direct migration binding: v2.
    """
    client = MemoryClient(home=tmp_path)
    record = client.add("Migration probe memory.", visibility=["global"])
    conn = client.store.conn
    conn.executescript(
        """
        DROP TRIGGER IF EXISTS memories_au;
        CREATE TRIGGER memories_au AFTER UPDATE ON memories BEGIN
          INSERT INTO memories_fts(memories_fts, id, owner, scope, type, content, summary, tags)
          VALUES('delete', old.id, old.owner, old.scope, old.type, old.content, old.summary, old.tags);
          INSERT INTO memories_fts(id, owner, scope, type, content, summary, tags)
          VALUES (new.id, new.owner, new.scope, new.type, new.content, new.summary, new.tags);
        END;
        """
    )
    # A genuinely legacy database predates the migration record, so drop it
    # too — migrations are forward-only and run once per database.
    conn.execute("DELETE FROM schema_migrations WHERE version = 2")
    conn.commit()
    client.close()

    reopened = MemoryClient(home=tmp_path)
    reopened.store.update_content(record.id, "Migration probe memory updated.")
    reopened.cache.clear()
    assert reopened.search("probe updated", requester_agent_id="neo") != []
