"""Direct timestamp contract for v21 pairing-invite rows.

The active pairing tests carry the v22 datetime/stamp clock seams. This test
preserves pairing-invite timestamp text that v22 must canonicalize in place.
"""

import re
import sqlite3

from agent_memory_os.migrations.v022_timestamp_ubiquity import migrate

_V21_CLOCK = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"\.[0-9]{6}\+00:00"
)


def _v21_input() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE pairing_invites (
          id TEXT PRIMARY KEY,
          created_at TEXT NOT NULL,
          expires_at TEXT NOT NULL,
          used_at TEXT
        )
        """
    )
    return conn


def test_v21_pairing_invite_timestamp_shapes_cross_into_v22() -> None:
    """Execution contract: pairing-invite timestamps crossing v21 -> v22.

    Provenance: pairing invites introduced at schema v16; their clock-boundary
    tests were introduced at 4279c380 during schema v21.
    Input scope: ``created_at``, ``expires_at``, and nullable ``used_at``.
    """
    conn = _v21_input()
    values = (
        "2026-08-11T12:00:00.500000+00:00",
        "2026-08-11T12:01:00.500000+00:00",
        "2026-08-11T12:00:30.500000+00:00",
    )
    conn.execute(
        "INSERT INTO pairing_invites(id, created_at, expires_at, used_at) "
        "VALUES ('used', ?, ?, ?)",
        values,
    )
    conn.execute(
        "INSERT INTO pairing_invites(id, created_at, expires_at, used_at) "
        "VALUES ('unused', ?, ?, NULL)",
        values[:2],
    )

    assert all(_V21_CLOCK.fullmatch(value) for value in values)

    migrate(conn)
    migrate(conn)

    assert [
        tuple(row)
        for row in conn.execute(
            "SELECT id, created_at, expires_at, used_at "
            "FROM pairing_invites ORDER BY id"
        )
    ] == [
        (
            "unused",
            "2026-08-11T12:00:00.500000Z",
            "2026-08-11T12:01:00.500000Z",
            None,
        ),
        (
            "used",
            "2026-08-11T12:00:00.500000Z",
            "2026-08-11T12:01:00.500000Z",
            "2026-08-11T12:00:30.500000Z",
        ),
    ]
    conn.close()
