"""Owner-attribution tools (v1.5): owner_counts / reassign_owner / purge via API.

These back the WebUI/CLI "hidden memories" workflow — memories written under a
fallback owner (e.g. 'default') that no browsing identity can see, and the
tools to fold them into a real identity or delete them.
"""

from __future__ import annotations

import pytest

from agent_memory_os.client import MemoryClient
from agent_memory_os.db import LEGACY_CONTEXT_OWNER


def _seed(client, owner, n=1, visibility=None):
    for i in range(n):
        client.add(f"note {owner} {i}", owner=owner, visibility=visibility or [])


def test_owner_counts_lists_every_owner(tmp_path):
    client = MemoryClient(home=tmp_path)
    _seed(client, "default", 2)
    _seed(client, "mizuki", 1)
    counts = {r["owner"]: r for r in client.owner_counts()}
    assert counts["default"]["memories"] == 2
    assert counts["mizuki"]["memories"] == 1
    assert counts["default"]["registered_agent"] is False


def test_owner_counts_flags_registered_agents(tmp_path):
    client = MemoryClient(home=tmp_path)
    client.store.register_agent("mizuki", display_name="Mizuki", kind="custom")
    _seed(client, "mizuki", 1)
    counts = {r["owner"]: r for r in client.owner_counts()}
    assert counts["mizuki"]["registered_agent"] is True


def test_reassign_owner_merges_into_existing(tmp_path):
    """The gap rename_agent can't fill: fold 'default' into an EXISTING owner."""
    client = MemoryClient(home=tmp_path)
    _seed(client, "default", 3)
    _seed(client, "mizuki", 1)
    changed = client.reassign_owner("default", "mizuki")
    assert changed["memories_owner"] == 3
    counts = {r["owner"]: r for r in client.owner_counts()}
    assert "default" not in counts
    assert counts["mizuki"]["memories"] == 4


def test_legacy_context_is_surfaced_and_classified_with_delivery_history(tmp_path):
    client = MemoryClient(home=tmp_path)
    snapshot_id = client.offload_context(
        {"step": 1},
        "legacy-session",
        owner=LEGACY_CONTEXT_OWNER,
    )
    delivered = client.add("Legacy delivery marker.", owner="default")
    client.store.record_delivery(
        "legacy-session",
        [delivered.id],
        owner=LEGACY_CONTEXT_OWNER,
    )

    legacy = {row["owner"]: row for row in client.owner_counts()}[
        LEGACY_CONTEXT_OWNER
    ]
    assert legacy["classification_required"] is True
    assert legacy["context_deliveries"] == 1

    changed = client.reassign_owner(LEGACY_CONTEXT_OWNER, "alice")

    assert changed["memories_owner"] == 1
    assert changed["context_deliveries"] == 1
    assert client.get(snapshot_id).owner == "alice"
    assert delivered.id in client.store.delivered_ids(
        "legacy-session",
        owner="alice",
    )
    assert LEGACY_CONTEXT_OWNER not in {
        row["owner"] for row in client.owner_counts()
    }


def test_reassign_owner_moves_agent_grants_and_bumps_acl(tmp_path):
    client = MemoryClient(home=tmp_path)
    # a memory shared explicitly to agent:old
    client.add("shared note", owner="alice", visibility=["agent:old"])
    changed = client.reassign_owner("old", "new")
    assert changed["visibility_grants"] == 1
    # the grant token was rewritten
    rows = client.store.conn.execute(
        "SELECT visibility FROM memories WHERE visibility LIKE ?",
        ('%agent:new%',),
    ).fetchall()
    assert rows and '"agent:new"' in rows[0]["visibility"]


def test_reassign_owner_rejects_identical_or_empty(tmp_path):
    client = MemoryClient(home=tmp_path)
    with pytest.raises(ValueError):
        client.reassign_owner("x", "x")
    with pytest.raises(ValueError):
        client.reassign_owner("", "y")


def test_reassign_owner_renames_registry_row_when_target_free(tmp_path):
    client = MemoryClient(home=tmp_path)
    client.store.register_agent("old", display_name="Old", kind="custom")
    _seed(client, "old", 1)
    client.reassign_owner("old", "brandnew")
    ids = {a["id"] for a in client.list_agents()}
    assert "brandnew" in ids and "old" not in ids


def test_reassign_owner_drops_registry_row_when_target_taken(tmp_path):
    client = MemoryClient(home=tmp_path)
    client.store.register_agent("old", display_name="Old", kind="custom")
    client.store.register_agent("keep", display_name="Keep", kind="custom")
    _seed(client, "old", 1)
    client.reassign_owner("old", "keep")
    ids = {a["id"] for a in client.list_agents()}
    assert "keep" in ids and "old" not in ids


def test_purge_owner_removes_all_owned(tmp_path):
    client = MemoryClient(home=tmp_path)
    _seed(client, "mizuki", 3)
    result = client.purge_owner("mizuki")
    assert result["memories_deleted"] == 3
    assert client.owner_counts() == []


def test_reassign_registers_unrecognized_target_by_default(tmp_path):
    """Moving memories to a fresh owner must leave them under a RECOGNIZED
    identity, else they are hidden all over again (the original mizuki bug)."""
    client = MemoryClient(home=tmp_path)
    _seed(client, "default", 2)
    changed = client.reassign_owner("default", "brandnew")
    assert changed["target_registered"] == 1
    ids = {a["id"] for a in client.list_agents()}
    assert "brandnew" in ids
    counts = {r["owner"]: r for r in client.owner_counts()}
    assert counts["brandnew"]["registered_agent"] is True


def test_reassign_no_register_leaves_target_unregistered(tmp_path):
    client = MemoryClient(home=tmp_path)
    _seed(client, "default", 1)
    changed = client.reassign_owner("default", "loose", register_target=False)
    assert changed["target_registered"] == 0
    assert "loose" not in {a["id"] for a in client.list_agents()}


def test_reassign_into_existing_agent_does_not_reregister(tmp_path):
    client = MemoryClient(home=tmp_path)
    client.store.register_agent("mizuki", display_name="Mizuki", kind="custom")
    _seed(client, "default", 1)
    changed = client.reassign_owner("default", "mizuki")
    assert changed["target_registered"] == 0  # already registered


def test_private_memory_readable_by_new_identity_after_rename(tmp_path):
    """Regression for 'after moving, can the memory still be read?': a PRIVATE
    memory follows its owner and is readable by the new id, not the old."""
    client = MemoryClient(home=tmp_path)
    client.store.register_agent("old", display_name="Old", kind="custom")
    client.add("private to old", owner="old", visibility=[])
    client.store.rename_agent("old", "new")

    as_new = [m.content for m in client.list_recent(requester_agent_id="new", limit=50)]
    as_old = [m.content for m in client.list_recent(requester_agent_id="old", limit=50)]
    assert "private to old" in as_new
    assert "private to old" not in as_old


def test_rename_agent_still_refuses_existing_target(tmp_path):
    """reassign_owner merges; rename_agent must still refuse to merge."""
    client = MemoryClient(home=tmp_path)
    client.store.register_agent("keep", display_name="Keep", kind="custom")
    with pytest.raises(ValueError, match="already exists"):
        client.store.rename_agent("old", "keep")
