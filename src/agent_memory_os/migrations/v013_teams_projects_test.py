"""Direct migration contract for the schema v12 to v13 boundary.

These tests construct only the predecessor columns consumed by migration v13;
they do not claim to instantiate the complete historical v12 application.
"""

import re
import sqlite3

from agent_memory_os.migrations.v013_teams_projects import migrate

_HISTORICAL_CLOCK = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+00:00"
)


def _v12_input() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE agents (id TEXT PRIMARY KEY, teams TEXT NOT NULL DEFAULT '[]')"
    )
    return conn


def test_v013_creates_the_organization_tables_and_indexes() -> None:
    """Execution contract: direct migration boundary v12 -> v13.

    Provenance: migration introduced at 2136c163.
    Input scope: the v12 ``agents.id`` and ``agents.teams`` columns consumed by
    this migration.
    """
    conn = _v12_input()

    migrate(conn)

    expected_columns = {
        "teams": ["id", "name", "created_at"],
        "team_members": ["team_id", "agent_id"],
        "projects": ["id", "team_id", "name", "created_at"],
        "project_members": ["project_id", "agent_id"],
    }
    for table, names in expected_columns.items():
        assert [row["name"] for row in conn.execute(f"PRAGMA table_info({table})")] == names

    indexes = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        )
    }
    assert {
        "team_members_agent",
        "project_members_agent",
        "projects_team",
    } <= indexes
    conn.close()


def test_v013_backfills_flat_agent_teams_with_historical_timestamp_text() -> None:
    """Execution contract: direct migration boundary v12 -> v13.

    Provenance: backfill and clock behavior introduced at 2136c163.
    Input scope: flat JSON team membership stored by schema v12.
    """
    conn = _v12_input()
    conn.executemany(
        "INSERT INTO agents(id, teams) VALUES (?, ?)",
        (
            ("neo", '[" ops ", "", 7]'),
            ("trinity", '["ops"]'),
        ),
    )

    migrate(conn)
    migrate(conn)

    teams = conn.execute(
        "SELECT id, name, created_at FROM teams ORDER BY id"
    ).fetchall()
    assert [(row["id"], row["name"]) for row in teams] == [("7", "7"), ("ops", "ops")]
    assert all(_HISTORICAL_CLOCK.fullmatch(row["created_at"]) for row in teams)
    assert [
        tuple(row)
        for row in conn.execute(
            "SELECT team_id, agent_id FROM team_members ORDER BY team_id, agent_id"
        )
    ] == [("7", "neo"), ("ops", "neo"), ("ops", "trinity")]
    conn.close()
