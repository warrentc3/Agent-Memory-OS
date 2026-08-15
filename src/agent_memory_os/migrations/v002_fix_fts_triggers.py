import sqlite3

from ..database_schema import SCHEMA


def migrate(conn: sqlite3.Connection) -> None:
    # Legacy AFTER UPDATE/DELETE triggers used the FTS5 'delete' command,
    # which is invalid on regular FTS5 tables and raised 'SQL logic error'
    # on every update_content()/delete().
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type = 'trigger' AND name IN ('memories_ad', 'memories_au')"
    ).fetchall()
    broken = [row["name"] for row in rows if "'delete'" in (row["sql"] or "")]
    if not broken:
        return
    for name in broken:
        conn.execute(f"DROP TRIGGER IF EXISTS {name}")
    conn.executescript(SCHEMA)
