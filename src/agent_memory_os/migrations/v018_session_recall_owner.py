import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    """Scope iterative-delivery state by requester identity.

    Existing rows predate requester-aware orchestration and remain under the
    empty owner, which preserves the legacy/admin SDK view.
    """
    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if "session_recall_log" not in tables and "session_recall_log_v2" in tables:
        conn.execute("ALTER TABLE session_recall_log_v2 RENAME TO session_recall_log")
        return
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(session_recall_log)").fetchall()
    }
    if "owner" in columns:
        return
    conn.execute("DROP TABLE IF EXISTS session_recall_log_v2")
    conn.execute(
        """
        CREATE TABLE session_recall_log_v2 (
          owner TEXT NOT NULL DEFAULT '',
          session_id TEXT NOT NULL,
          memory_id TEXT NOT NULL,
          delivered_at TEXT NOT NULL,
          PRIMARY KEY (owner, session_id, memory_id)
        )
        """
    )
    conn.execute(
        """
        INSERT INTO session_recall_log_v2(owner, session_id, memory_id, delivered_at)
        SELECT '', session_id, memory_id, delivered_at FROM session_recall_log
        """
    )
    conn.execute("DROP TABLE session_recall_log")
    conn.execute("ALTER TABLE session_recall_log_v2 RENAME TO session_recall_log")
