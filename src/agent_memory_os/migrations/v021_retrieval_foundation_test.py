"""Direct timestamp contract for the v21 retrieval-foundation test shape.

The active fallback test carries the v22 canonical stamp contract. This test
preserves its v21 fractional-offset expiry inputs at the migration boundary.
"""

import re
import sqlite3
from datetime import datetime, timedelta, timezone

from agent_memory_os.migrations.v022_timestamp_ubiquity import migrate

_V21_CLOCK = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"\.[0-9]{6}\+00:00"
)


def _future_iso(days: int = 1) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()  # noqa: UP017


def _past_iso(days: int = 1) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()  # noqa: UP017


def _v21_input() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE memories (id TEXT PRIMARY KEY, expires_at TEXT)")
    return conn


def test_v21_fallback_expiry_shapes_cross_into_v22() -> None:
    """Execution contract: fallback expiry inputs crossing v21 -> v22.

    Provenance: active fallback behavior introduced at 06716fb0.
    Input scope: the v21 past and future ``expires_at`` helper outputs.
    """
    past = _past_iso()
    future = _future_iso()
    conn = _v21_input()
    conn.executemany(
        "INSERT INTO memories(id, expires_at) VALUES (?, ?)",
        (("past", past), ("future", future)),
    )

    assert _V21_CLOCK.fullmatch(past)
    assert _V21_CLOCK.fullmatch(future)

    migrate(conn)
    migrate(conn)

    migrated = [
        row["expires_at"]
        for row in conn.execute("SELECT expires_at FROM memories ORDER BY id")
    ]
    assert all(value.endswith("Z") for value in migrated)
    assert all("+00:00" not in value for value in migrated)
    conn.close()
