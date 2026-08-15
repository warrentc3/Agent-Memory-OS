import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(memories)")}
    if "RecVersion" not in cols:
        conn.execute("ALTER TABLE memories ADD COLUMN RecVersion INTEGER NOT NULL DEFAULT 0")
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS memories_semantic_recversion_au
        AFTER UPDATE OF content, summary, tags ON memories
        WHEN new.content IS NOT old.content
          OR new.summary IS NOT old.summary
          OR new.tags IS NOT old.tags
        BEGIN
          UPDATE memories SET RecVersion = old.RecVersion + 1 WHERE id = old.id;
        END
        """
    )
