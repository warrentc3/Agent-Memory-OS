"""Direct timestamp contract for the v21 expired-neighbor test shape.

The active resonance test carries the v22 canonical stamp contract. This test
preserves its v21 offset-seconds expiry at the migration boundary.
"""

import re
import sqlite3

from agent_memory_os.migrations.v022_timestamp_ubiquity import migrate

V21_EXPIRY = "2020-01-01T00:00:00+00:00"
_V21_CLOCK = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+00:00"
)


def _v21_input() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE memories (id TEXT PRIMARY KEY, expires_at TEXT)")
    return conn


def test_v21_expired_neighbor_timestamp_shape_crosses_into_v22() -> None:
    """Execution contract: expired-neighbor input crossing v21 -> v22.

    Provenance: active behavior introduced at ea0faea3.
    Input scope: the v21 ``expires_at`` value used by the resonance test.
    """
    conn = _v21_input()
    conn.execute(
        "INSERT INTO memories(id, expires_at) VALUES (?, ?)",
        ("expired-neighbor", V21_EXPIRY),
    )

    assert _V21_CLOCK.fullmatch(V21_EXPIRY)

    migrate(conn)
    migrate(conn)

    migrated = conn.execute(
        "SELECT expires_at FROM memories WHERE id = 'expired-neighbor'"
    ).fetchone()[0]
    assert migrated == "2020-01-01T00:00:00.000000Z"
    conn.close()
