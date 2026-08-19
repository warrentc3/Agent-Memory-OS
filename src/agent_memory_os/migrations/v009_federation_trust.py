import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    # Per-peer push policy. Existing peers keep today's behaviour ('full'
    # replication) so no deployment silently changes; new peers default to
    # 'shared' at the add_peer call site (private memories never leave).
    cols = {row[1] for row in conn.execute("PRAGMA table_info(sync_peers)")}
    if "policy" not in cols:
        conn.execute(
            "ALTER TABLE sync_peers ADD COLUMN policy TEXT NOT NULL DEFAULT 'full'"
        )
    # Tombstones let deletions propagate across a mesh instead of resurrecting
    # from any peer that still holds the row.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tombstones (
          id TEXT PRIMARY KEY,
          deleted_at TEXT NOT NULL
        )
        """
    )
