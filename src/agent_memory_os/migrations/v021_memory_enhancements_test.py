"""Direct timestamp contract for the v21 stale-link test shape.

The active stale-link test carries the v22 canonical stamp contract. This
test preserves its v21 offset-seconds input shape at the migration boundary.
"""

import re
import sqlite3
from datetime import datetime, timedelta, timezone

from agent_memory_os.migrations.v022_timestamp_ubiquity import migrate

BACKDATED = "2020-01-01T00:00:00+00:00"
_V21_CLOCK = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+00:00"
)
_V22_CLOCK = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z"
)
_V21_FRACTIONAL_CLOCK = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"\.[0-9]{6}\+00:00"
)


def _v21_input() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE memory_links (updated_at TEXT, last_activated_at TEXT)"
    )
    return conn


def test_v21_stale_link_timestamp_shape_crosses_into_v22() -> None:
    """Execution contract: stale-link timestamp input crossing v21 -> v22.

    Provenance: active behavior introduced at ea0faea3.
    Input scope: the v21 ``updated_at`` and ``last_activated_at`` values used
    to backdate a memory link in the stale-link resonance test.
    """
    conn = _v21_input()
    conn.execute(
        "INSERT INTO memory_links(updated_at, last_activated_at) VALUES (?, ?)",
        (BACKDATED, BACKDATED),
    )

    assert _V21_CLOCK.fullmatch(BACKDATED)

    migrate(conn)
    migrate(conn)

    row = conn.execute(
        "SELECT updated_at, last_activated_at FROM memory_links"
    ).fetchone()
    assert row is not None
    assert _V22_CLOCK.fullmatch(row["updated_at"])
    assert _V22_CLOCK.fullmatch(row["last_activated_at"])
    assert row["updated_at"] == "2020-01-01T00:00:00.000000Z"
    assert row["last_activated_at"] == "2020-01-01T00:00:00.000000Z"
    conn.close()


def test_v21_dashboard_cutoff_timestamp_shape_crosses_into_v22() -> None:
    """Execution contract: dashboard cutoff input crossing v21 -> v22.

    Provenance: active precision test introduced at aa259661 and a8a56ca2.
    Input scope: the v21 fractional ``last_activated_at`` value immediately
    before the dashboard's stale-link cutoff.
    """
    fixed_now = datetime(
        2026,
        8,
        10,
        12,
        0,
        0,
        500000,
        tzinfo=timezone.utc,  # noqa: UP017 - preserve the v21 test spelling
    )
    true_cutoff = fixed_now - timedelta(days=90)
    v21_last_activated_at = (
        true_cutoff - timedelta(microseconds=1)
    ).isoformat()
    conn = _v21_input()
    conn.execute(
        "INSERT INTO memory_links(updated_at, last_activated_at) VALUES (?, ?)",
        (BACKDATED, v21_last_activated_at),
    )

    assert _V21_FRACTIONAL_CLOCK.fullmatch(v21_last_activated_at)

    migrate(conn)
    migrate(conn)

    migrated = conn.execute(
        "SELECT last_activated_at FROM memory_links"
    ).fetchone()[0]
    assert migrated == "2026-05-12T12:00:00.499999Z"
    conn.close()
