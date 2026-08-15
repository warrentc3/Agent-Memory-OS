import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    # A human-friendly name for a peer, shown instead of the bare URL during
    # sync (auto-filled from the peer's advertised node_name when available).
    cols = {row[1] for row in conn.execute("PRAGMA table_info(sync_peers)")}
    if "name" not in cols:
        conn.execute("ALTER TABLE sync_peers ADD COLUMN name TEXT NOT NULL DEFAULT ''")
