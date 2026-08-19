"""Direct migration contract for the schema v19 to v20 boundary.

These tests construct only the predecessor columns consumed by migration v20;
they do not claim to instantiate the complete historical v19 application.
"""

import sqlite3

from agent_memory_os.migrations.v020_canonicalize_expiry_timestamps import migrate


def _v19_input() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE memories (id TEXT PRIMARY KEY, expires_at TEXT);
        CREATE TABLE memories_archive (id TEXT PRIMARY KEY, expires_at TEXT);
        """
    )
    return conn


def test_v020_normalizes_only_expiry_values_inside_its_historical_iso_contract() -> None:
    """Execution contract: direct migration boundary v19 -> v20.

    Provenance: migration introduced at 1287c647 and bound to the ISO parser
    introduced at bd659853.
    Input scope: the v19 ``id`` and ``expires_at`` columns consumed in both
    active and archived memory tables.
    """
    conn = _v19_input()
    conn.executescript(
        """
        INSERT INTO memories VALUES ('basic', '20990101T000000+00:00');
        INSERT INTO memories VALUES ('offset', '2099-01-01T01:00:00+01:00');
        INSERT INTO memories VALUES ('naive', '2099-01-01T00:00:00');
        INSERT INTO memories VALUES ('invalid', 'someday');
        INSERT INTO memories VALUES ('absent', NULL);
        INSERT INTO memories_archive VALUES (
          'archived', '2000-01-01T01:00:00+01:00'
        );
        """
    )

    migrate(conn)
    migrate(conn)

    assert {
        row["id"]: row["expires_at"]
        for row in conn.execute("SELECT id, expires_at FROM memories")
    } == {
        "basic": "2099-01-01T00:00:00+00:00",
        "offset": "2099-01-01T00:00:00+00:00",
        "naive": "2099-01-01T00:00:00+00:00",
        "invalid": "someday",
        "absent": None,
    }
    assert conn.execute(
        "SELECT expires_at FROM memories_archive WHERE id = 'archived'"
    ).fetchone()[0] == "2000-01-01T00:00:00+00:00"
    conn.close()


def test_v020_preserves_non_text_values_outside_the_historical_parser_contract() -> None:
    """Execution contract: direct migration boundary v19 -> v20.

    Provenance: the non-fatal ValueError boundary was introduced at 1287c647.
    Input scope: a legacy value whose SQLite TEXT affinity presents it as text
    outside the accepted Python ISO grammar.
    """
    conn = _v19_input()
    conn.execute("INSERT INTO memories VALUES ('non-text', ?)", (123,))

    migrate(conn)

    assert conn.execute(
        "SELECT expires_at FROM memories WHERE id = 'non-text'"
    ).fetchone()[0] == "123"
    conn.close()
