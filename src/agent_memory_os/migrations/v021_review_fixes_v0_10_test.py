"""Direct timestamp contract for the v21 right-to-forget test shape.

The active right-to-forget test carries the v22 canonical stamp contract. This
test preserves its v21 offset-seconds expiry at the migration boundary.
"""

import re
import sqlite3

from agent_memory_os.migrations.v022_timestamp_ubiquity import migrate

V21_EXPIRY = "2000-01-01T00:00:00+00:00"
_V21_CLOCK = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+00:00"
)


def _v21_input() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE memories (id TEXT PRIMARY KEY, expires_at TEXT)")
    return conn


def test_v21_right_to_forget_expiry_shape_crosses_into_v22() -> None:
    """Execution contract: right-to-forget expiry crossing v21 -> v22.

    Provenance: active behavior introduced at 9dfab3ad during schema v8.
    Input scope: the v21 ``expires_at`` value used to make the memory
    immediately eligible for archival before owner purge.
    """
    conn = _v21_input()
    conn.execute(
        "INSERT INTO memories(id, expires_at) VALUES (?, ?)",
        ("archivable", V21_EXPIRY),
    )

    assert _V21_CLOCK.fullmatch(V21_EXPIRY)

    migrate(conn)
    migrate(conn)

    migrated = conn.execute(
        "SELECT expires_at FROM memories WHERE id = 'archivable'"
    ).fetchone()[0]
    assert migrated == "2000-01-01T00:00:00.000000Z"
    conn.close()
