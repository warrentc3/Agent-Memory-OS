"""Direct timestamp contract for the v21 Mem0 importer test shape.

The active importer test carries Mem0's documented ISO timestamp input and
the v22 canonical persisted stamp. This test preserves the prior date-only
``source.created_at`` shape at the migration boundary.
"""

import json
import re
import sqlite3

from agent_memory_os.migrations.v022_timestamp_ubiquity import migrate

V21_MEM0_CREATED_AT = "2026-01-01"
_V21_DATE_ONLY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def test_v21_mem0_source_created_at_crosses_into_v22() -> None:
    """Execution contract: Mem0 provenance timestamp crossing v21 -> v22.

    Provenance: active importer behavior introduced at 14023040 before the
    migration registry.
    Input scope: the v21 date-only ``created_at`` value in the Mem0 import and
    idempotency test fixture.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE memories (id TEXT PRIMARY KEY, source TEXT NOT NULL)"
    )
    source = {
        "system": "mem0-import",
        "source_key": "m1",
        "created_at": V21_MEM0_CREATED_AT,
        "metadata": {"topic": "ui"},
        "user_id": "alice",
    }
    conn.execute(
        "INSERT INTO memories(id, source) VALUES ('mem0_m1', ?)",
        (json.dumps(source),),
    )

    assert _V21_DATE_ONLY.fullmatch(V21_MEM0_CREATED_AT)

    migrate(conn)
    migrate(conn)

    migrated = json.loads(
        conn.execute("SELECT source FROM memories").fetchone()[0]
    )
    assert migrated == {
        **source,
        "created_at": "2026-01-01T00:00:00.000000Z",
    }
    conn.close()


def test_v21_mem0_unix_source_created_at_crosses_into_v22() -> None:
    """Execution contract: numeric Mem0 provenance crossing v21 -> v22."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE memories (id TEXT PRIMARY KEY, source TEXT NOT NULL)"
    )
    source = {
        "system": "mem0-import",
        "source_key": "epoch",
        "created_at": 1767225600,
    }
    conn.execute(
        "INSERT INTO memories(id, source) VALUES ('mem0_epoch', ?)",
        (json.dumps(source),),
    )

    migrate(conn)
    migrate(conn)

    migrated = json.loads(
        conn.execute("SELECT source FROM memories").fetchone()[0]
    )
    assert migrated == {
        **source,
        "created_at": "2026-01-01T00:00:00.000000Z",
    }
    conn.close()
