import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    # An ACL clock independent of updated_at. Sharing/revoking must NOT restart
    # the freshness/decay clock, but it MUST still propagate over sync — the old
    # code updated visibility without bumping any clock, so a revoke never
    # reached peers (already-synced memory stayed visible). acl_updated_at gives
    # visibility its own last-writer-wins timeline. Backfill = updated_at so
    # existing rows converge unchanged.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(memories)")}
    if "acl_updated_at" not in cols:
        conn.execute("ALTER TABLE memories ADD COLUMN acl_updated_at TEXT")
        conn.execute("UPDATE memories SET acl_updated_at = updated_at WHERE acl_updated_at IS NULL")
