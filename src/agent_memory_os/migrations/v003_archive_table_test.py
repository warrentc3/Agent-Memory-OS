"""Direct migration contract for schema migration v3."""

import sqlite3

from agent_memory_os.migrations.v003_archive_table import migrate


def test_v003_preserves_its_original_decay_half_life_default() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    migrate(conn)

    columns = {
        row["name"]: row
        for row in conn.execute("PRAGMA table_info(memories_archive)")
    }
    assert columns["decay_half_life_days"]["dflt_value"] == "30.0"
