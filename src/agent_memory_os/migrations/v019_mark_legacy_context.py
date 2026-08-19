import sqlite3

LEGACY_CONTEXT_OWNER = "__legacy_unscoped_context__"


def migrate(conn: sqlite3.Connection) -> None:
    """Preserve pre-requester context as explicitly unscoped legacy state.

    No migration-time identity is authoritative for a shared database. Marking
    legacy rows avoids falsely assigning them while allowing requester-aware
    readers to retain the same session continuity the old unscoped model had.
    """
    conn.execute(
        "UPDATE memories SET owner = ? WHERE type = 'snapshot' AND owner = 'default'",
        (LEGACY_CONTEXT_OWNER,),
    )
    conn.execute(
        "UPDATE memories_archive SET owner = ? "
        "WHERE type = 'snapshot' AND owner = 'default'",
        (LEGACY_CONTEXT_OWNER,),
    )
    conn.execute(
        "UPDATE session_recall_log SET owner = ? WHERE owner = ''",
        (LEGACY_CONTEXT_OWNER,),
    )
