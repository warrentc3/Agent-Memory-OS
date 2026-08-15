"""Database migration v20 compatibility contract."""

import sqlite3

import pytest

from agent_memory_os.migrations.v020_canonicalize_expiry_timestamps import migrate
from agent_memory_os.migrations.v020_compat import normalize_iso_timestamp


def test_v020_normalizer_retains_lenient_iso_input_and_offset_output():
    """Database binding: v20.

    Lineage:
    main: absent at 2f7a859; behavior originates at bd659853 and binds at 1287c647.
    time-helper: introduced working-tree@db-schema-v22.
    """
    assert normalize_iso_timestamp(
        "20990101T000000+00:00",
        field_name="expires_at",
    ) == "2099-01-01T00:00:00+00:00"
    assert normalize_iso_timestamp(
        "2099-01-01T01:00:00+01:00",
        field_name="expires_at",
    ) == "2099-01-01T00:00:00+00:00"
    assert normalize_iso_timestamp(
        "2099-01-01T00:00:00",
        field_name="expires_at",
    ) == "2099-01-01T00:00:00+00:00"


def test_v020_normalizer_preserves_the_historical_value_error_boundary():
    """Database binding: v20; malformed stored values remain non-fatal.

    Lineage:
    main: absent at 2f7a859; behavior originates at bd659853 and binds at 1287c647.
    time-helper: introduced working-tree@db-schema-v22.
    """
    for value in ("", "someday", 123):
        with pytest.raises(ValueError, match="expires_at must be an ISO-8601 timestamp"):
            normalize_iso_timestamp(value, field_name="expires_at")


def test_v020_migration_preserves_values_outside_its_iso_contract():
    """Database binding: v20; rejected legacy values are left untouched.

    Lineage:
    main: absent at 2f7a859; historical migration originates at 1287c647.
    time-helper: introduced working-tree@db-schema-v22.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE memories (id TEXT PRIMARY KEY, expires_at TEXT);
        CREATE TABLE memories_archive (id TEXT PRIMARY KEY, expires_at TEXT);
        INSERT INTO memories VALUES ('basic', '20990101T000000+00:00');
        INSERT INTO memories VALUES ('unknown', 'someday');
        INSERT INTO memories VALUES ('non-text', 123);
        INSERT INTO memories_archive VALUES ('offset', '2000-01-01T01:00:00+01:00');
        """
    )

    migrate(conn)

    assert conn.execute(
        "SELECT expires_at FROM memories WHERE id = 'basic'"
    ).fetchone()[0] == "2099-01-01T00:00:00+00:00"
    assert conn.execute(
        "SELECT expires_at FROM memories WHERE id = 'unknown'"
    ).fetchone()[0] == "someday"
    assert conn.execute(
        "SELECT expires_at FROM memories WHERE id = 'non-text'"
    ).fetchone()[0] == "123"
    assert conn.execute(
        "SELECT expires_at FROM memories_archive WHERE id = 'offset'"
    ).fetchone()[0] == "2000-01-01T00:00:00+00:00"
    conn.close()
