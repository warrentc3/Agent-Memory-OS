import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    # Fleet admin trust anchors (v1.6). Each row is an Ed25519 PUBLIC key this
    # node accepts signed cross-node operations from, with the capabilities the
    # local operator granted it. Grants arrive ONLY via the local CLI/trusted
    # pairing channel — never from a peer's sync bundle — so an untrusted peer
    # can never mint itself admin access (the D1–D4 trust boundary).
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fleet_admins (
          key_id TEXT PRIMARY KEY,
          public_key TEXT NOT NULL,
          caps TEXT NOT NULL,
          granted_at TEXT NOT NULL,
          granted_by TEXT NOT NULL DEFAULT 'local',
          revoked_at TEXT
        )
        """
    )
    # Replay guard for signed fleet requests: each nonce is accepted exactly
    # once (INSERT is the atomic check). Durable so a service restart within
    # the signature-freshness window cannot be replayed against.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fleet_nonces (
          nonce TEXT PRIMARY KEY,
          seen_at TEXT NOT NULL
        )
        """
    )
