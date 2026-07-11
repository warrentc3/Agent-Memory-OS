"""Importers from Mem0 / Zep / ChatGPT exports."""

from __future__ import annotations

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
    c = _client(tmp_path)
    export = {"results": [
        {"id": "m1", "memory": "User prefers dark mode", "user_id": "alice",
         "metadata": {"topic": "ui"}, "created_at": "2026-01-01"},
        {"id": "m2", "text": "Deploy target is port 8000"},
        {"id": "m3", "memory": ""},  # empty -> skipped
    ]}
    path = _write(tmp_path, "mem0.json", export)
    r1 = import_export(c, "mem0", path, owner="alice")
    assert r1.inserted == 2 and r1.scanned == 2
    hit = c.search("dark mode", requester_agent_id="alice")
    assert hit and hit[0].record.owner == "alice"
    # private by default
    assert c.search("dark mode", requester_agent_id="stranger") == []
    # re-run: unchanged -> all skipped, no duplicates
    r2 = import_export(c, "mem0", path, owner="alice")
    assert r2.inserted == 0 and r2.skipped == 2
    assert c.stats()["total"] == 2


def test_mem0_bare_list_and_change_updates(tmp_path):
    c = _client(tmp_path)
    p1 = _write(tmp_path, "a.json", [{"id": "x", "memory": "old text"}])
    import_export(c, "mem0", p1, owner="o")
    p2 = _write(tmp_path, "b.json", [{"id": "x", "memory": "new text"}])
    r = import_export(c, "mem0", p2, owner="o")
    assert r.updated == 1 and r.inserted == 0
    assert c.search("new text", requester_agent_id="o")
    assert c.stats()["total"] == 1  # same deterministic id -> updated in place


# ---------- Zep / Graphiti ----------

def test_zep_facts_and_messages(tmp_path):
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


# ---------- ChatGPT ----------

def test_chatgpt_explicit_memory_entries(tmp_path):
    c = _client(tmp_path)
    export = {"memories": ["I live in Taipei", {"id": "e2", "content": "I use vim"}]}
    path = _write(tmp_path, "cg.json", export)
    r = import_export(c, "chatgpt", path, owner="me")
    assert r.inserted == 2
    assert c.search("Taipei", requester_agent_id="me")


def test_chatgpt_conversations_extracts_user_turns(tmp_path):
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


# ---------- errors ----------

def test_unknown_source_rejected(tmp_path):
    c = _client(tmp_path)
    p = _write(tmp_path, "x.json", [])
    with pytest.raises(ValueError, match="unknown source"):
        import_export(c, "notreal", p)


def test_invalid_json_rejected(tmp_path):
    c = _client(tmp_path)
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        import_export(c, "mem0", str(p))
