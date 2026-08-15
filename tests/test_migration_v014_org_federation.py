"""Direct migration contract for the schema v13 to v14 boundary.

These tests construct only the predecessor tables consumed by migration v14;
they do not claim to instantiate the complete historical v13 application.
"""

import re
import sqlite3

from agent_memory_os.migrations.v014_compat import _iso_now_for_migration
from agent_memory_os.migrations.v014_org_federation import migrate


def _v13_input() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE teams (
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL
        );
        CREATE TABLE projects (
          id TEXT PRIMARY KEY,
          team_id TEXT NOT NULL,
          name TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL
        );
        INSERT INTO teams VALUES ('ops', 'Operations', '2026-01-02T03:04:05+00:00');
        INSERT INTO projects VALUES (
          'amos', 'ops', 'Agent Memory OS', '2026-01-03T04:05:06+00:00'
        );
        """
    )
    return conn


def test_v014_adds_org_clocks_without_rewriting_v013_creation_text() -> None:
    """Execution contract: direct migration boundary v13 -> v14.

    Provenance: migration introduced at 7ebc3daf.
    Input scope: exact v13 ``teams`` and ``projects`` table shapes.
    """
    conn = _v13_input()

    migrate(conn)
    migrate(conn)

    assert [
        row["name"] for row in conn.execute("PRAGMA table_info(teams)")
    ] == ["id", "name", "created_at", "updated_at"]
    assert [
        row["name"] for row in conn.execute("PRAGMA table_info(projects)")
    ] == ["id", "team_id", "name", "created_at", "updated_at"]
    assert conn.execute(
        "SELECT created_at, updated_at FROM teams WHERE id = 'ops'"
    ).fetchone()[:] == (
        "2026-01-02T03:04:05+00:00",
        "2026-01-02T03:04:05+00:00",
    )
    assert conn.execute(
        "SELECT created_at, updated_at FROM projects WHERE id = 'amos'"
    ).fetchone()[:] == (
        "2026-01-03T04:05:06+00:00",
        "2026-01-03T04:05:06+00:00",
    )
    conn.close()


def test_v014_creates_tombstone_and_audit_tables_with_historical_shapes() -> None:
    """Execution contract: direct migration boundary v13 -> v14.

    Provenance: federation tombstone and audit tables introduced at 7ebc3daf.
    Input scope: exact v13 organization tables consumed by the migration.
    """
    conn = _v13_input()

    migrate(conn)

    assert [
        row["name"] for row in conn.execute("PRAGMA table_info(org_tombstones)")
    ] == ["kind", "id", "deleted_at"]
    assert [
        row["name"] for row in conn.execute("PRAGMA table_info(org_audit)")
    ] == ["id", "at", "actor", "action", "detail"]
    audit_columns = {
        row["name"]: row for row in conn.execute("PRAGMA table_info(org_audit)")
    }
    assert audit_columns["actor"]["dflt_value"] == "'local'"
    assert audit_columns["detail"]["dflt_value"] == "''"
    conn.close()


def test_v014_compatibility_clock_retains_its_offset_spelling() -> None:
    """Execution contract: frozen clock dependency consumed by migration v14.

    Provenance: helper behavior present at 7ebc3daf and originating at 2136c163.
    """
    conn = sqlite3.connect(":memory:")

    assert re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+00:00",
        _iso_now_for_migration(conn),
    )
    conn.close()
