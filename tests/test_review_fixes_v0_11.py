"""Regression tests for the batch-2 review fixes (D5, D7, D8, D10, D12, D13, D14)."""

import os
import sys

import pytest

from agent_memory_os import MemoryClient
from agent_memory_os.context_pack import approx_tokens


def test_authority_track_does_not_double_penalize_metadata(tmp_path):
    """D5: a low-confidence authority memory that matches the query still
    surfaces via the authority track (its lexical score isn't squared away)."""
    client = MemoryClient(home=tmp_path)
    a = client.add(
        "deployment rollback runbook procedure",
        owner="ops", visibility=["global"], type="procedure",
        confidence=0.2, importance=0.3,
        source={"permanence": 1, "weight": 10},
    )
    hits = client.search("deployment rollback", requester_agent_id="neo")
    by_id = {h.record.id: h for h in hits}
    assert a.id in by_id, "authority memory must still surface"
    assert by_id[a.id].reason.startswith("authority_track")
    assert by_id[a.id].score > 0.0


def test_archived_memory_restores_with_its_links(tmp_path):
    """D7: restore brings the memory back WITH its association edges."""
    client = MemoryClient(home=tmp_path)
    hub = client.add("hub memory about migrations", visibility=["global"],
                     expires_at="2000-01-01T00:00:00+00:00")
    neighbor = client.add("neighbor memory about migrations", visibility=["global"])
    client.link(hub.id, neighbor.id, relation="related_to", weight=0.9)

    client.run_retention()  # archives the expired hub, deleting its live links
    assert client.get(hub.id) is None
    assert client.links(neighbor.id) == []  # edge went to the archive

    client.restore_archived(hub.id)
    restored_links = client.links(hub.id)
    assert any(
        {l.src_id, l.dst_id} == {hub.id, neighbor.id} and l.weight == 0.9
        for l in restored_links
    ), "the association edge must return with the memory"


def test_deidentified_share_does_not_leak_owner_via_audit_or_tags(tmp_path):
    """D10: the recipient-visible copy carries neither the owner's id nor tags."""
    client = MemoryClient(home=tmp_path)
    mem = client.add("secret plan by alice", owner="alice", visibility=[],
                     tags=["alice-personal", "confidential"])
    result = client.share_memory(mem.id, actor="alice", to_team="apollo", deidentify=True)
    copy_id = result["shared_as"]

    copy = client.get(copy_id)
    assert copy.tags == []  # owner-identifying tags dropped
    # The copy's audit (readable by recipients) must not name the owner.
    for row in client.audit_log(copy_id):
        assert row["actor"] != "alice"


def test_approx_tokens_counts_cjk_densely():
    """D12: CJK text is not undercounted 4x."""
    latin = "the quick brown fox jumps over"      # ~30 chars
    cjk = "这是一段中文记忆内容需要正确估算长度"       # 18 CJK chars
    assert approx_tokens(cjk) >= 18                # ~1 token/char, not /4
    assert approx_tokens(latin) <= len(latin)      # latin still ~4 chars/token


def test_token_file_is_created_private(tmp_path):
    """D13: the token file is never world-readable, even briefly."""
    from agent_memory_os.tokens import create_token, token_path
    create_token(tmp_path)
    path = token_path(tmp_path)
    assert path.exists()
    if os.name == "posix":
        assert (path.stat().st_mode & 0o777) == 0o600


def test_supersedes_pair_gets_no_corecall_colink(tmp_path):
    """D14: a pair joined only by supersedes is never re-associated by a
    co_recalled colink."""
    client = MemoryClient(home=tmp_path)
    old = client.add("old deploy target is port 8000", visibility=["global"])
    new = client.add("new deploy target is port 9000", visibility=["global"])
    client.link(new.id, old.id, relation="supersedes", weight=1.0)

    client.record_recall([old.id, new.id], helpful=True, create_colinks=True,
                         requester_agent_id="neo")

    relations = {l.relation for l in client.links(old.id)}
    assert "co_recalled" not in relations
    assert "supersedes" in relations


def test_custom_half_life_survives_feedback_tuning(tmp_path):
    """D6: feedback scales the CONFIGURED base, not the type default."""
    client = MemoryClient(home=tmp_path)
    # 'note' type-base is 30d; user pins 365d.
    m = client.add("note with a custom half-life", type="note",
                   visibility=["global"], decay_half_life_days=365.0)
    client.record_recall([m.id], helpful=True, requester_agent_id="x")
    client.run_retention()
    tuned = client.get(m.id).decay_half_life_days
    assert tuned > 300, f"custom base clobbered to type default: {tuned}"

    # A default-created memory still tunes from its type base (unchanged behaviour).
    d = client.add("default fact", type="fact", visibility=["global"])  # base 90
    for _ in range(8):
        client.record_recall([d.id], helpful=True, requester_agent_id="x")
    client.run_retention()
    assert client.get(d.id).decay_half_life_days == 270.0  # 90*sqrt(9)


def test_orchestrator_falls_back_dropped_section_hit_to_task(tmp_path):
    """D11: a warning-type top hit that doesn't fit the warnings cap still
    appears in the task section instead of vanishing."""
    client = MemoryClient(home=tmp_path)
    # ~34 tokens: over the 14% warnings cap (~18) but within the 46% task cap
    # (+surplus) at max_tokens=128.
    big = "deployment outage rollback " * 5
    w = client.add(big + " zqx", type="warning", visibility=["global"])

    result = client.orchestrate_context("deployment rollback zqx",
                                        requester_agent_id="neo", max_tokens=128)
    placed = {mid for sec in result.sections.values() for mid in sec.get("memory_ids", [])}
    assert w.id in placed, "the dropped warning hit should reappear in task"


def test_agents_toml_reapply_preserves_unspecified_fields(tmp_path):
    """D15: a partial agents.toml entry keeps console-set metadata."""
    from agent_memory_os.agents_config import apply_agents_config
    client = MemoryClient(home=tmp_path)
    client.register_agent("cc-main", kind="claude-code",
                          display_name="Claude Code", notes="primary dev agent",
                          teams=["apollo"])

    # A file that only pins teams must not wipe display_name/notes/kind.
    (tmp_path / "agents.toml").write_text(
        '[agents.cc-main]\nteams = ["apollo", "ops"]\n', encoding="utf-8"
    )
    apply_agents_config(client.store, tmp_path)

    agent = client.store.get_agent("cc-main")
    assert agent["display_name"] == "Claude Code"
    assert agent["notes"] == "primary dev agent"
    assert agent["kind"] == "claude-code"
    assert set(agent["teams"]) == {"apollo", "ops"}


def test_sync_all_peers_accepts_a_lock(tmp_path, monkeypatch):
    """D9: sync runs with the shared lock passed in (held only around DB ops)."""
    import threading

    from agent_memory_os import sync as sync_module

    client = MemoryClient(home=tmp_path)
    client.add("local global", owner="a", visibility=["global"])
    client.store.add_peer("http://peer:8000", policy="shared")
    lock = threading.Lock()

    def fake_http(url, *, token, post=None):
        # The app lock must NOT be held while we're out doing HTTP.
        assert lock.acquire(blocking=False), "lock held across peer HTTP"
        lock.release()
        return '{"kind": "bundle", "version": 2}\n' if post is None else "{}"

    monkeypatch.setattr(sync_module, "_http", fake_http)
    results = sync_module.sync_all_peers(client, lock=lock)
    assert results and results[0]["ok"] is True


def test_teams_cache_has_a_ttl(tmp_path):
    """D8: the team-ACL cache is time-bounded, not pinned until restart."""
    client = MemoryClient(home=tmp_path)
    assert client.store._TEAMS_CACHE_TTL_SECONDS > 0
    client.register_agent("neo", kind="hermes", teams=["apollo"])
    # same-process membership change is visible immediately (invalidation)
    client.add("apollo shared", owner="other", visibility=["team:apollo"])
    assert client.search("apollo", requester_agent_id="neo")
    client.register_agent("neo", kind="hermes", teams=[])  # leaves apollo
    assert not any(
        "apollo shared" in h.record.content
        for h in client.search("apollo", requester_agent_id="neo")
    )
