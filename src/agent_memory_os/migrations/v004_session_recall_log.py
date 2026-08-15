import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS session_recall_log (
          session_id TEXT NOT NULL,
          memory_id TEXT NOT NULL,
          delivered_at TEXT NOT NULL,
          PRIMARY KEY (session_id, memory_id)
        )
        """
    )
