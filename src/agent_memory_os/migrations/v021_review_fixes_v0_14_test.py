"""Direct timestamp contracts for v21 team-sync test shapes.

The active team-sync tests carry the v22 canonical stamp contract. These tests
preserve their distinct v21 offset-seconds inputs at the migration boundary.
"""

import re
import sqlite3
from datetime import datetime, timezone

from agent_memory_os.migrations.v022_timestamp_ubiquity import migrate

_V21_CLOCK = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+00:00"
)


def _v21_team(updated_at: str) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE teams (id TEXT PRIMARY KEY, updated_at TEXT)")
    conn.execute(
        "INSERT INTO teams(id, updated_at) VALUES ('team', ?)",
        (updated_at,),
    )
    return conn


def test_v21_team_scope_local_clock_crosses_into_v22() -> None:
    """Execution contract: team-scope local clock crossing v21 -> v22.

    Provenance: active behavior introduced at bc2608c9 during schema v14.
    Input scope: the fixed v21 ``teams.updated_at`` value used to ensure an
    authorized incoming team record wins on timestamp merit.
    """
    v21_updated_at = "2020-01-01T00:00:00+00:00"
    conn = _v21_team(v21_updated_at)

    assert _V21_CLOCK.fullmatch(v21_updated_at)

    migrate(conn)
    migrate(conn)

    migrated = conn.execute("SELECT updated_at FROM teams").fetchone()[0]
    assert migrated == "2020-01-01T00:00:00.000000Z"
    conn.close()


def test_v21_equal_membership_clock_crosses_into_v22() -> None:
    """Execution contract: equal-membership clock crossing v21 -> v22.

    Provenance: active behavior introduced at bc2608c9 during schema v14.
    Input scope: the v21 seconds-precision ``teams.updated_at`` helper output
    shared by both sides of the convergence test.
    """
    v21_updated_at = datetime.now(timezone.utc).isoformat(  # noqa: UP017
        timespec="seconds"
    )
    conn = _v21_team(v21_updated_at)

    assert _V21_CLOCK.fullmatch(v21_updated_at)

    migrate(conn)
    migrate(conn)

    migrated = conn.execute("SELECT updated_at FROM teams").fetchone()[0]
    assert migrated is not None
    assert migrated.endswith(".000000Z")
    conn.close()


def test_v21_archive_restore_expiry_crosses_into_v22() -> None:
    """Execution contract: archive-restore expiry crossing v21 -> v22.

    Provenance: active behavior introduced at c3f6b6e2 during schema v15.
    Input scope: the v21 ``memories.expires_at`` value used to archive a
    memory before verifying its restored ACL clock.
    """
    v21_expiry = "2000-01-01T00:00:00+00:00"
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE memories (id TEXT PRIMARY KEY, expires_at TEXT)")
    conn.execute(
        "INSERT INTO memories(id, expires_at) VALUES ('archivable', ?)",
        (v21_expiry,),
    )

    assert _V21_CLOCK.fullmatch(v21_expiry)

    migrate(conn)
    migrate(conn)

    migrated = conn.execute("SELECT expires_at FROM memories").fetchone()[0]
    assert migrated == "2000-01-01T00:00:00.000000Z"
    conn.close()
