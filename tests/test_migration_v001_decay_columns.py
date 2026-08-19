"""Direct migration contract for schema migration v1."""

import sqlite3

from agent_memory_os.migrations.v001_decay_columns import migrate


def test_v001_preserves_its_original_decay_half_life_default() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE memories (id TEXT PRIMARY KEY)")

    migrate(conn)

    columns = {
        row["name"]: row for row in conn.execute("PRAGMA table_info(memories)")
    }
    assert columns["decay_half_life_days"]["dflt_value"] == "30.0"
