import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    # Cold-archive the association edges alongside the memory, so restore
    # brings a memory back with its graph instead of at degree 0. No FK to
    # memories: an endpoint may itself be archived/absent.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_links_archive (
          src_id TEXT NOT NULL,
          dst_id TEXT NOT NULL,
          relation TEXT NOT NULL DEFAULT 'related_to',
          weight REAL NOT NULL DEFAULT 0.5,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          last_activated_at TEXT,
          activation_count INTEGER NOT NULL DEFAULT 0,
          source TEXT NOT NULL DEFAULT '{}',
          archived_at TEXT NOT NULL,
          PRIMARY KEY (src_id, dst_id, relation)
        )
        """
    )
