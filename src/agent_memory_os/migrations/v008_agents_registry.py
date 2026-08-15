import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agents (
          id TEXT PRIMARY KEY,
          display_name TEXT NOT NULL DEFAULT '',
          kind TEXT NOT NULL DEFAULT 'custom',
          teams TEXT NOT NULL DEFAULT '[]',
          notes TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          last_seen_at TEXT
        )
        """
    )
