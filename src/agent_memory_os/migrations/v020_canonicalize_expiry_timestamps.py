import sqlite3

from .v020_compat import normalize_iso_timestamp


def migrate(conn: sqlite3.Connection) -> None:
    """Canonicalize previously accepted ISO-8601 expiry spellings.

    Python accepts forms such as basic-format dates that SQLite julianday()
    does not. Rewriting parsable values keeps the instant-based SQL gates
    compatible with records written before canonical storage was enforced.
    """
    for table in ("memories", "memories_archive"):
        rows = conn.execute(
            f"SELECT id, expires_at FROM {table} WHERE expires_at IS NOT NULL"
        ).fetchall()
        for row in rows:
            try:
                normalized = normalize_iso_timestamp(
                    row["expires_at"],
                    field_name="expires_at",
                )
            except ValueError:
                # Preserve values outside the previously accepted Python ISO
                # contract; this migration must not invent expiry semantics.
                continue
            if normalized != row["expires_at"]:
                conn.execute(
                    f"UPDATE {table} SET expires_at = ? WHERE id = ?",
                    (normalized, row["id"]),
                )
