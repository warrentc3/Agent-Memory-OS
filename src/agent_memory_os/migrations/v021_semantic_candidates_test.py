"""Direct timestamp contract for the v21 semantic-candidate test shape.

The active semantic-candidate test carries the v22 canonical stamp contract.
This test preserves its v21 fractional-offset expiry at the migration boundary.
"""

import re
import sqlite3
from datetime import datetime, timedelta, timezone

from agent_memory_os.migrations.v022_timestamp_ubiquity import migrate

_V21_CLOCK = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"\.[0-9]{6}\+00:00"
)


def _past_iso(days: int = 1) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()  # noqa: UP017


def test_v21_semantic_candidate_expiry_crosses_into_v22() -> None:
    """Execution contract: semantic-candidate expiry crossing v21 -> v22.

    Provenance: active behavior introduced at d75ae935 before the migration
    registry.
    Input scope: the v21 fractional-offset ``expires_at`` helper output used
    to make a semantic candidate ineligible for retrieval.
    """
    v21_expiry = _past_iso()
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE memories (id TEXT PRIMARY KEY, expires_at TEXT)")
    conn.execute(
        "INSERT INTO memories(id, expires_at) VALUES ('expired', ?)",
        (v21_expiry,),
    )

    assert _V21_CLOCK.fullmatch(v21_expiry)

    migrate(conn)
    migrate(conn)

    migrated = conn.execute("SELECT expires_at FROM memories").fetchone()[0]
    assert migrated.endswith("Z")
    assert "+00:00" not in migrated
    conn.close()
