import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(memories)")}
    for name in ("helpful_count", "unhelpful_count"):
        if name not in existing:
            conn.execute(f"ALTER TABLE memories ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0")
    archive_existing = {row["name"] for row in conn.execute("PRAGMA table_info(memories_archive)")}
    for name in ("helpful_count", "unhelpful_count"):
        if name not in archive_existing:
            conn.execute(f"ALTER TABLE memories_archive ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0")
