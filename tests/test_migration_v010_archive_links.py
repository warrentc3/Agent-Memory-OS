import sqlite3

import pytest

from agent_memory_os.migrations.v010_archive_links import migrate


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    yield connection
    connection.close()


def test_migration_creates_archive_link_table(conn: sqlite3.Connection) -> None:
    migrate(conn)
    migrate(conn)

    columns = {
        row[1]: (row[2], row[3], row[4], row[5])
        for row in conn.execute("PRAGMA table_info(memory_links_archive)")
    }
    assert columns == {
        "src_id": ("TEXT", 1, None, 1),
        "dst_id": ("TEXT", 1, None, 2),
        "relation": ("TEXT", 1, "'related_to'", 3),
        "weight": ("REAL", 1, "0.5", 0),
        "created_at": ("TEXT", 1, None, 0),
        "updated_at": ("TEXT", 1, None, 0),
        "last_activated_at": ("TEXT", 0, None, 0),
        "activation_count": ("INTEGER", 1, "0", 0),
        "source": ("TEXT", 1, "'{}'", 0),
        "archived_at": ("TEXT", 1, None, 0),
    }
    assert conn.execute("PRAGMA foreign_key_list(memory_links_archive)").fetchall() == []


def test_migration_preserves_existing_archive_links(conn: sqlite3.Connection) -> None:
    migrate(conn)
    conn.execute(
        """
        INSERT INTO memory_links_archive (
          src_id, dst_id, relation, created_at, updated_at, archived_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "source",
            "target",
            "supports",
            "created",
            "updated",
            "archived",
        ),
    )

    migrate(conn)

    row = conn.execute(
        """
        SELECT src_id, dst_id, relation, weight, last_activated_at,
               activation_count, source
        FROM memory_links_archive
        """
    ).fetchone()
    assert row == ("source", "target", "supports", 0.5, None, 0, "{}")
