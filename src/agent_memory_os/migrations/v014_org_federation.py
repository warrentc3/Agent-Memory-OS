import sqlite3

from .v014_compat import _iso_now_for_migration


def migrate(conn: sqlite3.Connection) -> None:
    # Federate the org structure: each team/project carries an updated_at that
    # bumps on any membership change, so a bundle can carry the full member set
    # and importers converge by last-writer-wins. Deletions propagate via
    # org_tombstones; membership changes are recorded in org_audit.
    now = _iso_now_for_migration(conn)
    for table in ("teams", "projects"):
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if "updated_at" not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN updated_at TEXT")
            conn.execute(f"UPDATE {table} SET updated_at = COALESCE(created_at, ?)", (now,))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS org_tombstones (
          kind TEXT NOT NULL,          -- 'team' | 'project'
          id TEXT NOT NULL,
          deleted_at TEXT NOT NULL,
          PRIMARY KEY (kind, id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS org_audit (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          at TEXT NOT NULL,
          actor TEXT NOT NULL DEFAULT 'local',
          action TEXT NOT NULL,        -- create_team|delete_team|add_team_member|...
          detail TEXT NOT NULL DEFAULT ''
        )
        """
    )
