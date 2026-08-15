import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(memories)")}
    columns = {
        "decay_policy": "TEXT NOT NULL DEFAULT 'exponential'",
        "decay_half_life_days": "REAL NOT NULL DEFAULT 30.0",
        "last_accessed_at": "TEXT",
        "access_count": "INTEGER NOT NULL DEFAULT 0",
        "pinned": "INTEGER NOT NULL DEFAULT 0",
    }
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE memories ADD COLUMN {name} {definition}")
