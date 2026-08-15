"""Database migration v13 compatibility contract."""

import re
import sqlite3

from agent_memory_os.migrations.v013_compat import _iso_now_for_migration
from agent_memory_os.migrations.v013_teams_projects import migrate


def test_v013_clock_retains_its_historical_offset_spelling():
    """Database binding: v13.

    Lineage:
    main: absent at 2f7a859; historical behavior originates at 2136c163.
    time-helper: introduced working-tree@db-schema-v22.
    """
    conn = sqlite3.connect(":memory:")

    value = _iso_now_for_migration(conn)

    assert re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+00:00",
        value,
    )
    conn.close()


def test_v013_backfill_uses_the_v013_compatibility_clock():
    """Database binding: v13; protects the extracted migration contract.

    Lineage:
    main: absent at 2f7a859; historical behavior originates at 2136c163.
    time-helper: introduced working-tree@db-schema-v22.
    """
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE agents (id TEXT PRIMARY KEY, teams TEXT NOT NULL)")
    conn.execute("INSERT INTO agents VALUES ('neo', '[\"ops\"]')")

    migrate(conn)

    created_at = conn.execute(
        "SELECT created_at FROM teams WHERE id = 'ops'"
    ).fetchone()[0]
    assert re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+00:00",
        created_at,
    )
    conn.close()
