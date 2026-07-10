#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agent_memory_os import MemoryClient

QUERY = "downgrade_probe"
STABLE_FIELDS = [
    "id",
    "owner",
    "scope",
    "type",
    "content",
    "summary",
    "tags",
    "visibility",
    "source",
    "confidence",
    "importance",
    "created_at",
    "updated_at",
    "expires_at",
]
NEW_COLUMNS = {
    "decay_policy": "exponential",
    "decay_half_life_days": 30.0,
    "last_accessed_at": None,
    "access_count": 0,
    "pinned": 0,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def expired_at() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")


def future_at() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(timespec="seconds")


def old_schema_sql() -> str:
    return """
    CREATE TABLE memories (
      id TEXT PRIMARY KEY,
      owner TEXT NOT NULL,
      scope TEXT NOT NULL,
      type TEXT NOT NULL,
      content TEXT NOT NULL,
      summary TEXT NOT NULL,
      tags TEXT NOT NULL DEFAULT '[]',
      visibility TEXT NOT NULL DEFAULT '[]',
      source TEXT NOT NULL DEFAULT '{}',
      confidence REAL NOT NULL DEFAULT 0.8,
      importance REAL NOT NULL DEFAULT 0.5,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      expires_at TEXT
    );
    """


def create_old_schema_fixture(home: Path) -> dict[str, Any]:
    home.mkdir(parents=True, exist_ok=True)
    db_path = home / "memories.db"
    now = utc_now()
    fixtures = [
        {
            "id": "old_private_mizuki",
            "owner": "mizuki",
            "scope": "agent",
            "type": "preference",
            "content": "DOWNGRADE_LABEL=old_private_mizuki downgrade_probe private Mizuki memory",
            "summary": "private Mizuki memory",
            "tags": [QUERY],
            "visibility": ["agent"],
            "source": {"team_id": "bastet", "fixture": "old_schema", "unknown_key": "ignored"},
            "confidence": 0.95,
            "importance": 0.95,
            "created_at": now,
            "updated_at": now,
            "expires_at": None,
        },
        {
            "id": "old_team_bastet",
            "owner": "mizuki",
            "scope": "team",
            "type": "note",
            "content": "DOWNGRADE_LABEL=old_team_bastet downgrade_probe team memory",
            "summary": "team memory",
            "tags": [QUERY],
            "visibility": ["team:bastet"],
            "source": {"team_id": "bastet", "fixture": "old_schema"},
            "confidence": 0.9,
            "importance": 0.75,
            "created_at": now,
            "updated_at": now,
            "expires_at": None,
        },
        {
            "id": "old_global",
            "owner": "mizuki",
            "scope": "global",
            "type": "procedure",
            "content": "DOWNGRADE_LABEL=old_global downgrade_probe global memory",
            "summary": "global memory",
            "tags": [QUERY],
            "visibility": ["global"],
            "source": {"fixture": "old_schema"},
            "confidence": 0.9,
            "importance": 0.6,
            "created_at": now,
            "updated_at": now,
            "expires_at": None,
        },
        {
            "id": "old_expired",
            "owner": "mizuki",
            "scope": "global",
            "type": "note",
            "content": "DOWNGRADE_LABEL=old_expired downgrade_probe expired memory",
            "summary": "expired memory",
            "tags": [QUERY],
            "visibility": ["global"],
            "source": {"fixture": "old_schema"},
            "confidence": 0.9,
            "importance": 0.9,
            "created_at": now,
            "updated_at": now,
            "expires_at": expired_at(),
        },
    ]
    with sqlite3.connect(db_path) as conn:
        conn.executescript(old_schema_sql())
        for row in fixtures:
            conn.execute(
                """
                INSERT INTO memories(id, owner, scope, type, content, summary, tags, visibility, source,
                                     confidence, importance, created_at, updated_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["owner"],
                    row["scope"],
                    row["type"],
                    row["content"],
                    row["summary"],
                    json.dumps(row["tags"]),
                    json.dumps(row["visibility"]),
                    json.dumps(row["source"], sort_keys=True),
                    row["confidence"],
                    row["importance"],
                    row["created_at"],
                    row["updated_at"],
                    row["expires_at"],
                ),
            )
    return {"db_path": str(db_path), "ids": [row["id"] for row in fixtures]}


def label_from_content(content: str) -> str | None:
    marker = "DOWNGRADE_LABEL="
    if marker not in content:
        return None
    return content.split(marker, 1)[1].split()[0]


def labels(results: list[Any]) -> list[str]:
    found: list[str] = []
    for result in results:
        label = label_from_content(result.record.content)
        if label:
            found.append(label)
    return found


def verify_acl_matrix(client: MemoryClient) -> dict[str, Any]:
    identities = {
        "mizuki": {"requester_agent_id": "mizuki", "requester_team_id": "bastet", "expected": ["old_private_mizuki", "old_team_bastet", "old_global"]},
        "neo": {"requester_agent_id": "neo", "requester_team_id": "bastet", "expected": ["old_team_bastet", "old_global"]},
        "guest": {"requester_agent_id": "guest", "requester_team_id": None, "expected": ["old_global"]},
    }
    pulls = {}
    for identity, cfg in identities.items():
        hits = client.search(
            QUERY,
            requester_agent_id=cfg["requester_agent_id"],
            requester_team_id=cfg["requester_team_id"],
            limit=10,
        )
        report = client.context_pack_report(
            QUERY,
            requester_agent_id=cfg["requester_agent_id"],
            requester_team_id=cfg["requester_team_id"],
            limit=10,
            max_tokens=800,
        )
        records_by_id = {hit.record.id: hit.record for hit in hits}
        selected_labels = [
            label
            for decision in report.decisions
            if decision.selected
            for label in [label_from_content(records_by_id[decision.memory_id].content)]
            if label
        ]
        search_labels = labels(hits)
        pulls[identity] = {
            "search_visible_labels": search_labels,
            "context_selected_labels": selected_labels,
            "expected_visible_labels": cfg["expected"],
            "search_passed": search_labels == cfg["expected"],
            "context_pack_passed": selected_labels == cfg["expected"],
            "selected_reasons": [decision.reason for decision in report.decisions if decision.selected],
            "rejected_reasons": [decision.reason for decision in report.decisions if not decision.selected],
        }
    return {"pulls": pulls, "passed": all(p["search_passed"] and p["context_pack_passed"] for p in pulls.values())}


def table_columns(db_path: Path) -> dict[str, Any]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return {row["name"]: dict(row) for row in conn.execute("PRAGMA table_info(memories)")}


def row_snapshot(db_path: Path) -> dict[str, Any]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM memories ORDER BY id").fetchall()
        return {row["id"]: {key: row[key] for key in row.keys()} for row in rows}


def verify_old_to_new(home: Path) -> dict[str, Any]:
    fixture = create_old_schema_fixture(home)
    before = row_snapshot(home / "memories.db")
    before_ids = sorted(before)
    client = MemoryClient(home=home)
    try:
        after = row_snapshot(home / "memories.db")
        columns = table_columns(home / "memories.db")
        defaults_ok = True
        for row in after.values():
            defaults_ok = defaults_ok and row["decay_policy"] == "exponential"
            defaults_ok = defaults_ok and float(row["decay_half_life_days"]) == 30.0
            defaults_ok = defaults_ok and row["last_accessed_at"] is None
            defaults_ok = defaults_ok and int(row["access_count"]) == 0
            defaults_ok = defaults_ok and int(row["pinned"]) == 0
        acl = verify_acl_matrix(client)
        rebuild = client.rebuild_indexes()
    finally:
        client.close()
    after_ids = sorted(after)
    content_preserved = all(before[memory_id]["content"] == after[memory_id]["content"] for memory_id in before_ids)
    return {
        "fixture": fixture,
        "row_count_before": len(before),
        "row_count_after": len(after),
        "memory_ids_preserved": before_ids == after_ids,
        "content_preserved": content_preserved,
        "new_columns_present": all(col in columns for col in NEW_COLUMNS),
        "deterministic_defaults_ok": defaults_ok,
        "acl_matrix": acl,
        "index_rebuild": rebuild,
        "passed": before_ids == after_ids and content_preserved and defaults_ok and acl["passed"] and rebuild["memories_total"] == len(after),
    }


def create_current_fixture(home: Path) -> dict[str, Any]:
    client = MemoryClient(home=home)
    ids: list[str] = []
    try:
        ids.append(client.add(
            "DOWNGRADE_LABEL=current_pinned downgrade_probe current pinned authority",
            id="current_pinned",
            owner="mizuki",
            scope="global",
            type="procedure",
            visibility=["global"],
            tags=[QUERY],
            source={"permanence": 1, "weight": 10, "claim_key": "authority", "claim": "current pinned", "unknown_key": "ignored"},
            importance=0.95,
            confidence=0.95,
            pinned=True,
        ).id)
        ids.append(client.add(
            "DOWNGRADE_LABEL=current_team downgrade_probe current team memory",
            id="current_team",
            owner="mizuki",
            scope="team",
            type="note",
            visibility=["team:bastet"],
            tags=[QUERY],
            source={"team_id": "bastet", "claim_key": "team"},
            importance=0.75,
            confidence=0.9,
            decay_half_life_days=14.0,
        ).id)
        ids.append(client.add(
            "DOWNGRADE_LABEL=current_private downgrade_probe current private memory",
            id="current_private",
            owner="mizuki",
            scope="agent",
            type="preference",
            visibility=["agent"],
            tags=[QUERY],
            source={"team_id": "bastet", "claim_key": "private", "grant_visibility": "global"},
            importance=0.8,
            confidence=0.9,
        ).id)
    finally:
        client.close()
    return {"ids": sorted(ids)}


def older_reader_export(db_path: Path, requester_agent_id: str, requester_team_id: str | None) -> list[dict[str, Any]]:
    now = utc_now()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT {', '.join(STABLE_FIELDS)} FROM memories WHERE expires_at IS NULL OR expires_at > ? ORDER BY id", (now,)).fetchall()
    visible: list[dict[str, Any]] = []
    for row in rows:
        visibility = json.loads(row["visibility"] or "[]")
        source = json.loads(row["source"] or "{}")
        allowed = (
            row["owner"] == requester_agent_id
            or "global" in visibility
            or f"agent:{requester_agent_id}" in visibility
            or (requester_team_id is not None and "team" in visibility and source.get("team_id") == requester_team_id)
            or (requester_team_id is not None and f"team:{requester_team_id}" in visibility)
        )
        if allowed:
            visible.append({field: row[field] for field in STABLE_FIELDS})
    return visible


def verify_new_to_old(home: Path) -> dict[str, Any]:
    fixture = create_current_fixture(home)
    db_path = home / "memories.db"
    neo_rows = older_reader_export(db_path, "neo", "bastet")
    guest_rows = older_reader_export(db_path, "guest", None)
    neo_ids = [row["id"] for row in neo_rows]
    guest_ids = [row["id"] for row in guest_rows]
    stable_fields_readable = all(set(STABLE_FIELDS) == set(row) for row in neo_rows + guest_rows)
    private_leaked = "current_private" in neo_ids or "current_private" in guest_ids
    unknown_metadata_granted_visibility = "current_private" in guest_ids
    return {
        "fixture": fixture,
        "stable_fields_readable": stable_fields_readable,
        "neo_visible_ids": neo_ids,
        "guest_visible_ids": guest_ids,
        "private_leaked": private_leaked,
        "unknown_metadata_granted_visibility": unknown_metadata_granted_visibility,
        "passed": stable_fields_readable and not private_leaked and not unknown_metadata_granted_visibility and "current_pinned" in guest_ids,
    }


def verify_rollback(home: Path) -> dict[str, Any]:
    create_current_fixture(home)
    db_path = home / "memories.db"
    before = row_snapshot(db_path)
    backup = home / "memories.db.pre_migration_backup"
    shutil.copy2(db_path, backup)
    # Simulate a failed migration after backup creation.
    with sqlite3.connect(db_path) as conn:
        conn.execute("ALTER TABLE memories ADD COLUMN simulated_new_column TEXT")
        # Simulate an interrupted migration that changed schema shape after the
        # backup point. The restore below must return to the pre-migration file.
        conn.commit()
    shutil.copy2(backup, db_path)
    client = MemoryClient(home=home)
    try:
        rebuild = client.rebuild_indexes()
        acl = {
            "neo": labels(client.search(QUERY, requester_agent_id="neo", requester_team_id="bastet", limit=10)),
            "guest": labels(client.search(QUERY, requester_agent_id="guest", requester_team_id=None, limit=10)),
        }
    finally:
        client.close()
    after = row_snapshot(db_path)
    return {
        "backup_path": str(backup),
        "row_count_before": len(before),
        "row_count_after_restore": len(after),
        "memory_ids_preserved": sorted(before) == sorted(after),
        "content_preserved": all(before[memory_id]["content"] == after[memory_id]["content"] for memory_id in before),
        "index_rebuild": rebuild,
        "acl_after_restore": acl,
        "passed": sorted(before) == sorted(after) and all(before[memory_id]["content"] == after[memory_id]["content"] for memory_id in before) and rebuild["memories_total"] == len(after) and "current_private" not in acl["neo"] and "current_private" not in acl["guest"],
    }


def verify_disposable_index_rebuild(home: Path) -> dict[str, Any]:
    create_current_fixture(home)
    db_path = home / "memories.db"
    before = row_snapshot(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executescript("DROP TRIGGER IF EXISTS memories_ai; DROP TRIGGER IF EXISTS memories_ad; DROP TRIGGER IF EXISTS memories_au; DROP TABLE IF EXISTS memories_fts;")
        conn.commit()
    client = MemoryClient(home=home)
    try:
        rebuild = client.rebuild_indexes()
        after = row_snapshot(db_path)
        neo = labels(client.search(QUERY, requester_agent_id="neo", requester_team_id="bastet", limit=10))
        guest = labels(client.search(QUERY, requester_agent_id="guest", requester_team_id=None, limit=10))
    finally:
        client.close()
    return {
        "row_count_before": len(before),
        "row_count_after_rebuild": len(after),
        "memory_ids_preserved": sorted(before) == sorted(after),
        "content_preserved": all(before[memory_id]["content"] == after[memory_id]["content"] for memory_id in before),
        "index_rebuild": rebuild,
        "neo_visible_labels": neo,
        "guest_visible_labels": guest,
        "passed": sorted(before) == sorted(after) and rebuild["memories_total"] == len(after) and "current_private" not in neo and "current_private" not in guest and "current_pinned" in guest,
    }


def build_report(home: Path, *, reset: bool) -> dict[str, Any]:
    if reset and home.exists():
        shutil.rmtree(home)
    home.mkdir(parents=True, exist_ok=True)
    sections = {
        "old_schema_to_current_runtime": verify_old_to_new(home / "old-to-new"),
        "current_database_to_stable_field_exporter": verify_new_to_old(home / "new-to-old"),
        "migration_failure_rollback": verify_rollback(home / "rollback"),
        "disposable_index_rebuild": verify_disposable_index_rebuild(home / "index-rebuild"),
    }
    passed = all(section["passed"] for section in sections.values())
    return {
        "status": "PASS" if passed else "FAIL",
        "home": str(home),
        "matrix": sections,
        "summary": {
            "memory_ids_preserved": all(
                section.get("memory_ids_preserved", True) for section in sections.values()
            ),
            "acl_matrix_passed": sections["old_schema_to_current_runtime"]["acl_matrix"]["passed"],
            "unknown_metadata_safe": sections["current_database_to_stable_field_exporter"]["passed"],
            "rollback_restore_passed": sections["migration_failure_rollback"]["passed"],
            "index_rebuild_passed": sections["disposable_index_rebuild"]["passed"],
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify AgentMemoryOS downgrade, migration, rollback, ACL, and index-rebuild safety against temporary fixtures.")
    parser.add_argument("--home", default="/tmp/agent-memory-os-downgrade-qa", help="Temporary AgentMemoryOS verification directory.")
    parser.add_argument("--matrix", choices=["all"], default="all")
    parser.add_argument("--no-reset", action="store_true", help="Do not delete --home before running.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(Path(args.home), reset=not args.no_reset)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
