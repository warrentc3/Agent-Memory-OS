"""Direct timestamp contract for the v21 memory-decay test shape.

The active memory-decay tests carry the v22 canonical stamp contract. This
test preserves their v21 offset-seconds input shape at the migration boundary.
"""

import re
import sqlite3
from datetime import datetime, timedelta, timezone

from agent_memory_os.migrations.v022_timestamp_ubiquity import migrate

_V21_CLOCK = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+00:00"
)
_V22_CLOCK = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z"
)


def iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(  # noqa: UP017
        timespec="seconds"
    )


def iso_days_from_now(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(  # noqa: UP017
        timespec="seconds"
    )


def _v21_input() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE memories ("
        "id TEXT PRIMARY KEY, updated_at TEXT, expires_at TEXT"
        ")"
    )
    return conn


def test_v21_memory_decay_timestamp_shape_crosses_into_v22() -> None:
    """Execution contract: memory-decay timestamp inputs crossing v21 -> v22.

    Input scope: the v21 ``updated_at`` and ``expires_at`` values produced by
    the active test's prior ``iso_days_ago`` and ``iso_days_from_now`` helpers.
    """
    conn = _v21_input()
    v21_values = {
        "recent": (iso_days_ago(1), None),
        "stale": (iso_days_ago(180), None),
        "active": (iso_days_ago(1), iso_days_from_now(1)),
        "expired": (iso_days_ago(1), iso_days_ago(1)),
    }
    conn.executemany(
        "INSERT INTO memories(id, updated_at, expires_at) VALUES (?, ?, ?)",
        ((memory_id, *values) for memory_id, values in v21_values.items()),
    )

    assert all(
        _V21_CLOCK.fullmatch(value)
        for values in v21_values.values()
        for value in values
        if value is not None
    )

    migrate(conn)
    migrate(conn)

    migrated = conn.execute(
        "SELECT updated_at, expires_at FROM memories"
    ).fetchall()
    assert all(_V22_CLOCK.fullmatch(row["updated_at"]) for row in migrated)
    assert all(
        row["expires_at"] is None or _V22_CLOCK.fullmatch(row["expires_at"])
        for row in migrated
    )
    conn.close()
