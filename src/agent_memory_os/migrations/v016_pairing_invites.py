import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    # One-time pairing codes for the same-host / cross-node "join a team"
    # flow. Only a SHA-256 hash of the code is stored — the plaintext code is
    # shown once to the operator and is the sole credential for redemption.
    # Single-use (used_at) with a TTL (expires_at); consumption is atomic via
    # a conditional UPDATE so two concurrent redeems cannot both win.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pairing_invites (
          id TEXT PRIMARY KEY,
          code_hash TEXT NOT NULL UNIQUE,
          team_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          expires_at TEXT NOT NULL,
          used_at TEXT,
          redeemed_by TEXT
        )
        """
    )
