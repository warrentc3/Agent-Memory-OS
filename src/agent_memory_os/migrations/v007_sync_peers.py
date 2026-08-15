import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sync_peers (
          url TEXT PRIMARY KEY,
          token TEXT,
          added_at TEXT NOT NULL,
          last_synced_at TEXT,
          last_result TEXT NOT NULL DEFAULT ''
        )
        """
    )
