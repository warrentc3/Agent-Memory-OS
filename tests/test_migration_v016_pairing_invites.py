import sqlite3

import pytest

from agent_memory_os.migrations.v016_pairing_invites import migrate


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    yield connection
    connection.close()


def test_migration_creates_pairing_invites_table(conn: sqlite3.Connection) -> None:
    migrate(conn)
    migrate(conn)

    columns = {
        row[1]: (row[2], row[3], row[4], row[5])
        for row in conn.execute("PRAGMA table_info(pairing_invites)")
    }
    assert columns == {
        "id": ("TEXT", 0, None, 1),
        "code_hash": ("TEXT", 1, None, 0),
        "team_id": ("TEXT", 1, None, 0),
        "created_at": ("TEXT", 1, None, 0),
        "expires_at": ("TEXT", 1, None, 0),
        "used_at": ("TEXT", 0, None, 0),
        "redeemed_by": ("TEXT", 0, None, 0),
    }


def test_migration_enforces_unique_code_hash(conn: sqlite3.Connection) -> None:
    migrate(conn)
    values = (
        "hash",
        "team",
        "created",
        "expires",
    )
    conn.execute(
        """
        INSERT INTO pairing_invites (
          id, code_hash, team_id, created_at, expires_at
        ) VALUES ('first', ?, ?, ?, ?)
        """,
        values,
    )

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO pairing_invites (
              id, code_hash, team_id, created_at, expires_at
            ) VALUES ('second', ?, ?, ?, ?)
            """,
            values,
        )

    row = conn.execute(
        "SELECT used_at, redeemed_by FROM pairing_invites WHERE id = 'first'"
    ).fetchone()
    assert row == (None, None)
