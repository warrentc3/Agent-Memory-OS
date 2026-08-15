"""Importers from Mem0 / Zep / ChatGPT exports."""

from __future__ import annotations

import hashlib
import json

import pytest

from agent_memory_os import MemoryClient
from agent_memory_os.importers import import_export


def _client(tmp_path):
    return MemoryClient(home=tmp_path / "amos")


def _write(tmp_path, name, obj):
    p = tmp_path / name
    p.write_text(json.dumps(obj), encoding="utf-8")
    return str(p)


# ---------- Mem0 ----------

def test_mem0_import_and_idempotency(tmp_path):
    """Lineage:
    main: introduced 14023040@db-schema-v15.
    """
    c = _client(tmp_path)
    export = {"results": [
        {"id": "m1", "memory": "User prefers dark mode", "user_id": "alice",
         "metadata": {"topic": "ui"}, "created_at": "2026-01-01T00:00:00Z"},
        {"id": "m2", "text": "Deploy target is port 8000"},
        {"id": "m3", "memory": ""},  # empty -> skipped
    ]}
    path = _write(tmp_path, "mem0.json", export)
    r1 = import_export(c, "mem0", path, owner="alice")
    assert r1.inserted == 2 and r1.scanned == 2
    hit = c.search("dark mode", requester_agent_id="alice")
    assert hit and hit[0].record.owner == "alice"
    assert hit[0].record.source["created_at"] == "2026-01-01T00:00:00.000000Z"
    # private by default
    assert c.search("dark mode", requester_agent_id="stranger") == []
    # re-run: unchanged -> all skipped, no duplicates
    r2 = import_export(c, "mem0", path, owner="alice")
    assert r2.inserted == 0 and r2.skipped == 2
    assert c.stats()["total"] == 2


def test_mem0_bare_list_and_change_updates(tmp_path):
    """Lineage:
    main: introduced 14023040@db-schema-v15.
    """
    c = _client(tmp_path)
    p1 = _write(tmp_path, "a.json", [{"id": "x", "memory": "old text"}])
    import_export(c, "mem0", p1, owner="o")
    p2 = _write(tmp_path, "b.json", [{"id": "x", "memory": "new text"}])
    r = import_export(c, "mem0", p2, owner="o")
    assert r.updated == 1 and r.inserted == 0
    assert c.search("new text", requester_agent_id="o")
    assert c.stats()["total"] == 1  # same deterministic id -> updated in place


def test_mem0_partial_failures_are_reported(tmp_path):
    c = _client(tmp_path)
    export = {
        "results": [
            {"id": "good", "memory": "valid memory"},
            "not-an-object",
            {"id": "empty", "memory": ""},
            {
                "id": "bad-clock",
                "memory": "memory with malformed provenance",
                "created_at": "2026-01-01",
            },
            {"id": "blank", "memory": "   "},
        ]
    }

    report = import_export(c, "mem0", _write(tmp_path, "partial.json", export))

    assert report.inserted == 2
    assert report.warnings == [
        "mem0 record 1: expected an object; skipped",
        "mem0 record 2: missing memory content; skipped",
        (
            "mem0 record 3 (bad-clock): created_at has an unsupported or invalid "
            "timestamp shape; ignored"
        ),
        "mem0 record (blank): content is blank after trimming; skipped",
    ]
    imported = c.get(
        "mem0_" + hashlib.sha256(b"mem0:bad-clock").hexdigest()[:32]
    )
    assert imported is not None
    assert "created_at" not in imported.source


def test_mem0_unix_timestamp_is_canonicalized(tmp_path):
    c = _client(tmp_path)
    export = {
        "results": [
            {
                "id": "epoch",
                "memory": "memory with custom timestamp",
                "timestamp": 1767225600,
            }
        ]
    }

    report = import_export(c, "mem0", _write(tmp_path, "epoch.json", export))

    assert report.warnings == []
    imported = c.get("mem0_" + hashlib.sha256(b"mem0:epoch").hexdigest()[:32])
    assert imported is not None
    assert imported.source["created_at"] == "2026-01-01T00:00:00.000000Z"


@pytest.mark.parametrize(
    ("field_name", "value", "expected"),
    [
        ("created_at", "2026-01-01T01:00:00+01:00", "2026-01-01T00:00:00.000000Z"),
        (
            "created_at",
            "2026-01-01T01:00:00.123456+01:00",
            "2026-01-01T00:00:00.123456Z",
        ),
        ("createdAt", "2026-01-01T00:00:00.123Z", "2026-01-01T00:00:00.123000Z"),
        ("createdAt", 1767225600, "2026-01-01T00:00:00.000000Z"),
        ("timestamp", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00.000000Z"),
    ],
)
def test_mem0_timestamp_fields_are_converted_by_shape(
    tmp_path, field_name, value, expected
):
    c = _client(tmp_path)
    export = {"results": [{"id": "shaped", "memory": "shaped clock", field_name: value}]}

    report = import_export(c, "mem0", _write(tmp_path, "shaped.json", export))

    assert report.warnings == []
    imported = c.get("mem0_" + hashlib.sha256(b"mem0:shaped").hexdigest()[:32])
    assert imported is not None
    assert imported.source["created_at"] == expected


def test_mem0_timestamp_field_precedence_degrades_to_next_valid_shape(tmp_path):
    c = _client(tmp_path)
    export = {
        "results": [
            {
                "id": "fallback",
                "memory": "fallback clock",
                "created_at": "2026-02-30T00:00:00Z",
                "createdAt": "2026-01-01T00:00:00.123Z",
                "timestamp": 0,
            }
        ]
    }

    report = import_export(c, "mem0", _write(tmp_path, "fallback.json", export))

    assert report.warnings == [
        (
            "mem0 record 0 (fallback): created_at has an unsupported or invalid "
            "timestamp shape; ignored"
        )
    ]
    imported = c.get("mem0_" + hashlib.sha256(b"mem0:fallback").hexdigest()[:32])
    assert imported is not None
    assert imported.source["created_at"] == "2026-01-01T00:00:00.123000Z"


# ---------- Zep / Graphiti ----------

def test_zep_facts_and_messages(tmp_path):
    """Lineage:
    main: introduced 14023040@db-schema-v15.
    """
    c = _client(tmp_path)
    export = {
        "facts": [{"uuid": "f1", "fact": "Alice manages the Apollo project"},
                  {"uuid": "f2", "name": "prefers async standups"}],
        "messages": [{"uuid": "msg1", "role": "user", "content": "remember my TZ is UTC+8"}],
    }
    path = _write(tmp_path, "zep.json", export)
    r = import_export(c, "zep", path, owner="alice", visibility=["global"])
    assert r.inserted == 3
    assert c.search("Apollo", requester_agent_id="anyone")  # global visibility honored


def test_zep_partial_failures_are_reported(tmp_path):
    c = _client(tmp_path)
    export = {
        "facts": [{"uuid": "good", "fact": "valid fact"}, {}],
        "messages": ["not-an-object", {"uuid": "empty"}],
    }

    report = import_export(c, "zep", _write(tmp_path, "zep-partial.json", export))

    assert report.inserted == 1
    assert report.warnings == [
        "zep fact 1: missing content; skipped",
        "zep message 0: expected an object; skipped",
        "zep message 1: missing content; skipped",
    ]


# ---------- ChatGPT ----------

def test_chatgpt_explicit_memory_entries(tmp_path):
    """Lineage:
    main: introduced 14023040@db-schema-v15.
    """
    c = _client(tmp_path)
    export = {"memories": ["I live in Taipei", {"id": "e2", "content": "I use vim"}]}
    path = _write(tmp_path, "cg.json", export)
    r = import_export(c, "chatgpt", path, owner="me")
    assert r.inserted == 2
    assert c.search("Taipei", requester_agent_id="me")


def test_chatgpt_conversations_extracts_user_turns(tmp_path):
    """Lineage:
    main: introduced 14023040@db-schema-v15.
    """
    c = _client(tmp_path)
    export = [{
        "title": "trip", "mapping": {
            "n1": {"message": {"id": "u1", "author": {"role": "user"},
                               "content": {"parts": ["Book me a flight to Osaka"]}}},
            "n2": {"message": {"id": "a1", "author": {"role": "assistant"},
                               "content": {"parts": ["Sure!"]}}},  # assistant -> skipped
        },
    }]
    path = _write(tmp_path, "conv.json", export)
    r = import_export(c, "chatgpt", path, owner="me")
    assert r.inserted == 1
    assert c.search("Osaka", requester_agent_id="me")


def test_chatgpt_partial_failures_are_reported(tmp_path):
    c = _client(tmp_path)
    export = [
        {
            "title": "partial",
            "mapping": {
                "broken": {},
                "empty-user": {
                    "message": {
                        "author": {"role": "user"},
                        "content": {"parts": []},
                    }
                },
            },
        },
        "not-an-object",
        {"title": "bad mapping", "mapping": []},
    ]

    report = import_export(c, "chatgpt", _write(tmp_path, "cg-partial.json", export))

    assert report.warnings == [
        "chatgpt conversation 0 node broken: message must be an object; skipped",
        "chatgpt conversation 0 node empty-user: user content is empty; skipped",
        "chatgpt conversation 1: expected an object; skipped",
        "chatgpt conversation 2: mapping must be an object; skipped",
    ]


# ---------- errors ----------

def test_unknown_source_rejected(tmp_path):
    """Lineage:
    main: introduced 14023040@db-schema-v15.
    """
    c = _client(tmp_path)
    p = _write(tmp_path, "x.json", [])
    with pytest.raises(ValueError, match="unknown source"):
        import_export(c, "notreal", p)


def test_invalid_json_rejected(tmp_path):
    """Lineage:
    main: introduced 14023040@db-schema-v15.
    """
    c = _client(tmp_path)
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        import_export(c, "mem0", str(p))
