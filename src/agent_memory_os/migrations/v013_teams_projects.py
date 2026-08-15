import json
import sqlite3

from .v013_compat import _iso_now_for_migration


def migrate(conn: sqlite3.Connection) -> None:
    # First-class teams and projects with explicit membership, so team-shared
    # vs project-shared memory can be scoped correctly. Membership join tables
    # are authoritative; a project's members must be a subset of its team's.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS teams (
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS team_members (
          team_id TEXT NOT NULL,
          agent_id TEXT NOT NULL,
          PRIMARY KEY (team_id, agent_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS projects (
          id TEXT PRIMARY KEY,
          team_id TEXT NOT NULL,
          name TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS project_members (
          project_id TEXT NOT NULL,
          agent_id TEXT NOT NULL,
          PRIMARY KEY (project_id, agent_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS team_members_agent ON team_members(agent_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS project_members_agent ON project_members(agent_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS projects_team ON projects(team_id)")
    # Backfill from the old flat agent.teams so existing memberships survive.
    now = _iso_now_for_migration(conn)
    for row in conn.execute("SELECT id, teams FROM agents").fetchall():
        for team_id in json.loads(row[1] or "[]"):
            team_id = str(team_id).strip()
            if not team_id:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO teams(id, name, created_at) VALUES (?, ?, ?)",
                (team_id, team_id, now),
            )
            conn.execute(
                "INSERT OR IGNORE INTO team_members(team_id, agent_id) VALUES (?, ?)",
                (team_id, row[0]),
            )
