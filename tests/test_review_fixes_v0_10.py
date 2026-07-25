"""Regression tests for the v0.10.x code-review / security-review fixes.

Each test pins a specific finding from docs/reviews/20260711-v0.10.0-review.md
so the bug cannot silently return.
"""

import pytest

from agent_memory_os import MemoryClient


def test_purge_owner_also_destroys_archive_and_logs(tmp_path):
    """Right-to-forget must reach the cold archive, not just active memories."""
    client = MemoryClient(home=tmp_path)
    rec = client.add(
        "secret onboarding note",
        owner="alice",
        visibility=[],
        expires_at="2000-01-01T00:00:00+00:00",  # already expired -> archivable
    )
    client.run_retention()  # moves the expired row into memories_archive
    assert any(a["id"] == rec.id for a in client.list_archived()), "precondition: archived"

    result = client.purge_owner("alice")

    assert result["archived_deleted"] >= 1
    assert not any(a["id"] == rec.id for a in client.list_archived())
    with pytest.raises((KeyError, ValueError)):
        client.restore_archived(rec.id)  # gone for good, not resurrectable


def test_share_and_revoke_do_not_reset_freshness_clock(tmp_path):
    """A pure ACL change is not a content edit; updated_at must not move."""
    client = MemoryClient(home=tmp_path)
    rec = client.add("stable fact", owner="alice", visibility=[])
    before = client.get(rec.id).updated_at

    client.share_memory(rec.id, actor="alice", to_team="apollo")
    assert client.get(rec.id).updated_at == before

    client.revoke_share(rec.id, actor="alice", to_team="apollo")
    assert client.get(rec.id).updated_at == before


def test_get_visible_enforces_acl(tmp_path):
    """The single-memory fetch used by the web API honours the ACL gate."""
    client = MemoryClient(home=tmp_path)
    rec = client.add("alice private", owner="alice", visibility=[])

    # Owner sees it; a different agent never does — same gate as /api/search.
    assert client.get_visible(rec.id, requester_agent_id="alice") is not None
    assert client.get_visible(rec.id, requester_agent_id="mallory") is None
    # No requester == unrestricted operator/admin view, identical to a
    # requester-less /api/search (documented local trust model).
    assert client.get_visible(rec.id) is not None


def test_semantic_signature_changes_on_in_place_edit(tmp_path):
    """Same-second content edit must change the rebuild signature."""
    client = MemoryClient(home=tmp_path)
    a = client.add("first", visibility=["global"])
    client.add("second", visibility=["global"])
    sig_before = client.store.semantic_signature()

    client.update(a.id, content="totally different content of another length")
    assert client.store.semantic_signature() != sig_before


def test_semantic_signature_changes_on_same_length_same_second_edit(tmp_path):
    client = MemoryClient(home=tmp_path)
    memory = client.add("alpha", visibility=["global"])
    sig_before = client.store.semantic_signature()

    client.update(memory.id, content="bravo")

    assert client.store.semantic_signature() != sig_before


def test_semantic_signature_stable_under_reinforcement(tmp_path):
    """Reinforcement writes must NOT trigger a spurious index rebuild."""
    client = MemoryClient(home=tmp_path)
    a = client.add("reinforce me", visibility=["global"])
    sig_before = client.store.semantic_signature()
    client.record_recall([a.id], helpful=True, requester_agent_id="neo")
    assert client.store.semantic_signature() == sig_before


def test_rotate_snapshots_never_archives_pinned(tmp_path):
    client = MemoryClient(home=tmp_path)
    keep = []
    for i in range(4):
        sid = client.offload_context({"i": i}, session_id="S")
        keep.append(sid)
    pinned = client.offload_context({"i": "pinned"}, session_id="S")
    client.update(pinned, pinned=True)
    for i in range(4, 9):
        client.offload_context({"i": i}, session_id="S")

    client.store.rotate_snapshots(keep_per_session=2)

    assert client.get(pinned) is not None
    assert not any(a["id"] == pinned for a in client.list_archived())


def test_resonance_search_returns_seeds(tmp_path):
    """resonance_search must not raise AttributeError once a seed is found."""
    client = MemoryClient(home=tmp_path)
    client.add("database migration rollback plan", visibility=["global"])
    results = client.resonance_search("database migration")
    assert isinstance(results, list)
    assert results, "a matching seed should be returned"


def test_agents_config_rejects_string_teams(tmp_path):
    (tmp_path / "agents.toml").write_text(
        '[agents.cc-main]\nkind = "claude-code"\nteams = "apollo"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="teams must be a list"):
        MemoryClient(home=tmp_path)


def test_agents_config_invalid_entry_applies_nothing(tmp_path):
    """A bad entry aborts before any write: no half-registered fleet."""
    (tmp_path / "agents.toml").write_text(
        '[agents.good]\nkind = "hermes"\nteams = ["apollo"]\n'
        '[agents.bad]\nkind = "clade-code"\n',  # typo -> invalid kind
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        MemoryClient(home=tmp_path)

    # Reopen with a clean config; the earlier failure left no 'good' agent.
    (tmp_path / "agents.toml").unlink()
    client = MemoryClient(home=tmp_path)
    assert client.store.get_agent("good") is None


def test_llm_extractor_survives_non_string_reply(tmp_path):
    """A completion returning None must degrade to zero links, not crash."""
    from agent_memory_os.extractors import make_llm_link_extractor
    from agent_memory_os.schema import MemoryRecord

    extractor = make_llm_link_extractor(lambda prompt: None)
    records = [MemoryRecord(content="a"), MemoryRecord(content="b")]
    assert extractor(records) == []


def test_import_bundle_rolls_back_on_corrupt_line(tmp_path):
    """A truncated bundle must not leave half-merged rows behind."""
    client = MemoryClient(home=tmp_path)
    bundle = tmp_path / "corrupt.jsonl"
    bundle.write_text(
        '{"kind": "bundle", "version": 1}\n'
        '{"kind": "memory", "id": "mem_imported_1", "owner": "peer", '
        '"scope": "user", "type": "note", "content": "ok", "summary": "", '
        '"tags": "[]", "visibility": "[\\"global\\"]", "source": "{}", '
        '"confidence": 0.8, "importance": 0.5, "created_at": "2026-01-01T00:00:00+00:00", '
        '"updated_at": "2026-01-01T00:00:00+00:00", "decay_policy": "exponential", '
        '"decay_half_life_days": 30.0, "access_count": 0, "pinned": 0, '
        '"helpful_count": 0, "unhelpful_count": 0}\n'
        '{"kind": "memory", TRUNCATED-NOT-JSON\n'
    )
    with pytest.raises(Exception):
        client.import_bundle(bundle)

    # The valid line before the corrupt one must have been rolled back.
    assert client.get("mem_imported_1") is None
