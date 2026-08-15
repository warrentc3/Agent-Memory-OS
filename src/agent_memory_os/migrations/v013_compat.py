"""Frozen compatibility surface for database migration v13.

Lineage:
- ``_iso_now_for_migration`` entered v13 with commit 2136c163 in ``db.py``.
- Commit d6884ee extracted v13 and replaced this behavior with the v22
  ``utc_now_stamp`` policy.
- The v22 stamp policy supersedes live timestamp writes; it does not supersede
  the historical v13 migration contract.
"""

import sqlite3


def _iso_now_for_migration(conn: sqlite3.Connection) -> str:
    """Return the second-resolution offset spelling used by migration v13."""
    row = conn.execute(
        "SELECT strftime('%Y-%m-%dT%H:%M:%S+00:00','now')"
    ).fetchone()
    return row[0]
