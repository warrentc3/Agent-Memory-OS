import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memories_archive (
          id TEXT PRIMARY KEY,
          owner TEXT NOT NULL,
          scope TEXT NOT NULL,
          type TEXT NOT NULL,
          content TEXT NOT NULL,
          summary TEXT NOT NULL,
          tags TEXT NOT NULL DEFAULT '[]',
          visibility TEXT NOT NULL DEFAULT '[]',
          source TEXT NOT NULL DEFAULT '{}',
          confidence REAL NOT NULL DEFAULT 0.8,
          importance REAL NOT NULL DEFAULT 0.5,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          expires_at TEXT,
          decay_policy TEXT NOT NULL DEFAULT 'exponential',
          decay_half_life_days REAL NOT NULL DEFAULT 30.0,
          last_accessed_at TEXT,
          access_count INTEGER NOT NULL DEFAULT 0,
          pinned INTEGER NOT NULL DEFAULT 0,
          archived_at TEXT NOT NULL,
          archive_reason TEXT NOT NULL
        )
        """
    )
