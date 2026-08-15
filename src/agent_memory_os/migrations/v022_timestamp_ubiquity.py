import json
import re
import sqlite3

from ..timestamp_converters import (
    convert_iso_to_stamp,
    convert_unix_time_utc,
    detect_timestamp_shape,
)

_ISO_DATE_ONLY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

_STAMP_COLUMNS: dict[str, tuple[str, ...]] = {
    "memories": (
        "created_at",
        "updated_at",
        "acl_updated_at",
        "expires_at",
        "last_accessed_at",
    ),
    "memories_archive": (
        "created_at",
        "updated_at",
        "expires_at",
        "last_accessed_at",
        "archived_at",
    ),
    "memory_links": (
        "created_at",
        "updated_at",
        "last_activated_at",
    ),
    "memory_links_archive": (
        "created_at",
        "updated_at",
        "last_activated_at",
        "archived_at",
    ),
    "recall_profiles": ("updated_at",),
    "teams": ("created_at", "updated_at"),
    "projects": ("created_at", "updated_at"),
    "pairing_invites": ("created_at", "expires_at", "used_at"),
    "tombstones": ("deleted_at",),
    "org_tombstones": ("deleted_at",),
}


def _migrate_mem0_source_created_at(
    conn: sqlite3.Connection,
    table: str,
    columns: set[str],
) -> None:
    if "source" not in columns:
        return
    rows = conn.execute(
        f"SELECT rowid, source FROM {table} WHERE source IS NOT NULL"
    ).fetchall()
    for row in rows:
        try:
            source = json.loads(row["source"])
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(source, dict) or source.get("system") != "mem0-import":
            continue
        created_at = source.get("created_at")
        if isinstance(created_at, str):
            try:
                stamp = convert_iso_to_stamp(created_at)
            except ValueError:
                if _ISO_DATE_ONLY.fullmatch(created_at) is None:
                    continue
                stamp = convert_iso_to_stamp(f"{created_at}T00:00:00Z")
        elif isinstance(created_at, (int, float)) and not isinstance(
            created_at, bool
        ):
            created_at_text = str(created_at)
            try:
                shape = detect_timestamp_shape(created_at_text)
            except ValueError:
                continue
            if shape != "distance-from-epoch":
                continue
            stamp = convert_unix_time_utc(created_at_text)
        else:
            continue
        if stamp == created_at:
            continue
        source["created_at"] = stamp
        conn.execute(
            f"UPDATE {table} SET source = ? WHERE rowid = ?",
            (json.dumps(source, ensure_ascii=False, sort_keys=True), row["rowid"]),
        )


def migrate(conn: sqlite3.Connection) -> None:
    """Convert supported legacy record and link timestamp text to stamps."""
    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if "memories" in tables:
        memory_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(memories)").fetchall()
        }
        if {"updated_at", "acl_updated_at"} <= memory_columns:
            conn.execute(
                "UPDATE memories SET acl_updated_at = updated_at "
                "WHERE acl_updated_at IS NULL"
            )
    for table in ("memory_links", "memory_links_archive"):
        if table not in tables:
            continue
        columns = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if "last_activated_at" in columns:
            conn.execute(
                f"UPDATE {table} SET last_activated_at = NULL "
                "WHERE last_activated_at = ''"
            )
    for table, timestamp_columns in _STAMP_COLUMNS.items():
        if table not in tables:
            continue
        columns = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        for column in timestamp_columns:
            if column not in columns:
                continue
            rows = conn.execute(
                f"SELECT rowid, {column} FROM {table} WHERE {column} IS NOT NULL"
            ).fetchall()
            for row in rows:
                try:
                    stamp = convert_iso_to_stamp(row[column])
                except ValueError:
                    continue
                if stamp != row[column]:
                    conn.execute(
                        f"UPDATE {table} SET {column} = ? WHERE rowid = ?",
                        (stamp, row["rowid"]),
                    )
        if table in {"memories", "memories_archive"}:
            _migrate_mem0_source_created_at(conn, table, columns)
