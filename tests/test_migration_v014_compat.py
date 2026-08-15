"""Database migration v14 compatibility contract."""

import re
import sqlite3

from agent_memory_os.migrations.v014_compat import _iso_now_for_migration
from agent_memory_os.migrations.v014_org_federation import migrate


def test_v014_clock_retains_its_historical_offset_spelling():
    """Database binding: v14.

    Lineage:
    main: absent at 2f7a859; historical behavior originates at 7ebc3daf.
    time-helper: introduced working-tree@db-schema-v22.
    """
    conn = sqlite3.connect(":memory:")

    value = _iso_now_for_migration(conn)

    assert re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+00:00",
        value,
    )
    conn.close()


def test_v014_backfill_preserves_existing_v13_spelling():
    """Database binding: v14 over a v13 database.

    Lineage:
    main: absent at 2f7a859; historical behavior originates at 7ebc3daf.
    time-helper: introduced working-tree@db-schema-v22.
    """
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE teams (id TEXT PRIMARY KEY, created_at TEXT);
        CREATE TABLE projects (id TEXT PRIMARY KEY, created_at TEXT);
        INSERT INTO teams VALUES ('ops', '2026-01-02T03:04:05+00:00');
        INSERT INTO projects VALUES ('amos', '2026-01-02T03:04:05+00:00');
        """
    )

    migrate(conn)

    assert conn.execute(
        "SELECT updated_at FROM teams WHERE id = 'ops'"
    ).fetchone()[0] == "2026-01-02T03:04:05+00:00"
    assert conn.execute(
        "SELECT updated_at FROM projects WHERE id = 'amos'"
    ).fetchone()[0] == "2026-01-02T03:04:05+00:00"
    conn.close()
