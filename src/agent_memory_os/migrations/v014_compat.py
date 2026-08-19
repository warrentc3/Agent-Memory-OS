"""Frozen compatibility surface for database migration v14.

Lineage:
- v14 acquired ``_iso_now_for_migration`` with commit 7ebc3daf; the helper
  originated with v13 at commit 2136c163.
- Commit d6884ee extracted v14 and replaced this behavior with the v22
  ``utc_now_stamp`` policy.
- The v22 stamp policy supersedes live timestamp writes; it does not supersede
  the historical v14 migration contract.
"""

import sqlite3


def _iso_now_for_migration(conn: sqlite3.Connection) -> str:
    """Return the second-resolution offset spelling used by migration v14."""
    row = conn.execute(
        "SELECT strftime('%Y-%m-%dT%H:%M:%S+00:00','now')"
    ).fetchone()
    return row[0]
