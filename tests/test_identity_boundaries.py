from __future__ import annotations

import pytest

from agent_memory_os.client import MemoryClient


def test_update_requires_matching_owner(tmp_path):
    client = MemoryClient(home=tmp_path)
    alice = client.add("Alice owns this memory.", owner="alice")

    with pytest.raises(KeyError) as exc_info:
        client.update(alice.id, requester_agent_id="bob", content="Bob changed it.")
    assert exc_info.value.args == (alice.id,)

    updated = client.update(
        alice.id,
        requester_agent_id="alice",
        content="Alice changed it.",
    )
    assert updated.content == "Alice changed it."


def test_link_requires_both_memories_to_be_owned(tmp_path):
    client = MemoryClient(home=tmp_path)
    alice = client.add("Alice's decision.", owner="alice", visibility=["global"])
    alice_detail = client.add("Alice's supporting detail.", owner="alice")
    bob = client.add("Bob's shared note.", owner="bob", visibility=["global"])

    own_link = client.link(
        alice.id,
        alice_detail.id,
        requester_agent_id="alice",
    )
    assert own_link.src_id == alice.id

    with pytest.raises(KeyError) as exc_info:
        client.link(alice.id, bob.id, requester_agent_id="alice")
    assert exc_info.value.args == (bob.id,)


def test_context_offload_preserves_an_existing_transaction(tmp_path):
    client = MemoryClient(home=tmp_path)
    client.store.conn.execute("BEGIN")

    with pytest.raises(RuntimeError, match="active database transaction"):
        client.offload_context({"step": 1}, "busy-session", owner="alice")

    assert client.store.conn.in_transaction is True
    client.store.conn.rollback()


def test_recall_feedback_does_not_mutate_shared_foreign_memory(tmp_path):
    client = MemoryClient(home=tmp_path)
    alice = client.add(
        "Alice's shared checklist.",
        owner="alice",
        visibility=["global"],
        confidence=0.8,
    )
    bob = client.add(
        "Bob's own checklist.",
        owner="bob",
        visibility=["global"],
        confidence=0.8,
    )

    result = client.record_recall(
        [alice.id, bob.id],
        helpful=False,
        requester_agent_id="bob",
        owner="bob",
    )

    assert result["weakened_memories"] == 1
    assert client.get(alice.id).confidence == 0.8
    assert client.get(bob.id).confidence < 0.8


def test_auto_reinforcement_does_not_mutate_shared_foreign_memory(tmp_path):
    client = MemoryClient(home=tmp_path)
    alice = client.add(
        "Alice's shared reinforcement sentinel.",
        owner="alice",
        visibility=["global"],
    )
    bob = client.add(
        "Bob's reinforcement sentinel.",
        owner="bob",
    )

    report = client.context_pack_report(
        "reinforcement sentinel",
        requester_agent_id="bob",
        auto_reinforce=True,
    )

    assert {decision.memory_id for decision in report.decisions if decision.selected} >= {
        alice.id,
        bob.id,
    }
    assert client.get(alice.id).helpful_count == 0
    assert client.get(bob.id).helpful_count == 1


def test_consolidation_is_restricted_to_requester_owner(tmp_path):
    client = MemoryClient(home=tmp_path)
    for owner in ("alice", "bob"):
        client.add("Duplicate owned memory.", owner=owner)
        client.add("Duplicate owned memory.", owner=owner)

    with pytest.raises(PermissionError, match="only the owner may consolidate"):
        client.consolidate(owner="alice", requester_agent_id="bob")

    result = client.consolidate(requester_agent_id="alice")

    assert result["duplicates_merged"] == 1
    assert len(client.list_recent(owner="alice")) == 1
    assert len(client.list_recent(owner="bob")) == 2


def test_snapshots_are_isolated_by_owner_session_and_record_type(tmp_path):
    client = MemoryClient(home=tmp_path)
    session_id = "shared-session-label"
    alice_first = client.offload_context(
        {"step": 1, "actor": "alice"},
        session_id,
        owner="alice",
    )
    client.offload_context(
        {"step": 2, "actor": "alice"},
        session_id,
        owner="alice",
    )
    bob_snapshot = client.offload_context(
        {"step": 7, "actor": "bob"},
        session_id,
        owner="bob",
    )
    ordinary = client.add(
        "This is not a context snapshot.",
        owner="alice",
        source={"session_id": session_id},
    )

    assert client.reload_context(
        session_id,
        requester_agent_id="alice",
    ) == {"step": 2, "actor": "alice"}
    assert client.reload_context(
        session_id,
        requester_agent_id="bob",
    ) == {"step": 7, "actor": "bob"}

    diff = client.snapshot_diff(session_id, requester_agent_id="alice")
    assert diff["snapshots_compared"] == 2
    assert diff["changed"]["step"] == {"from": 1, "to": 2}

    with pytest.raises(ValueError, match=f"Snapshot {alice_first} not found"):
        client.reload_context(
            "different-session",
            snapshot_id=alice_first,
            requester_agent_id="alice",
        )
    with pytest.raises(ValueError, match=f"Snapshot {bob_snapshot} not found"):
        client.reload_context(
            session_id,
            snapshot_id=bob_snapshot,
            requester_agent_id="alice",
        )
    with pytest.raises(ValueError, match=f"Snapshot {ordinary.id} not found"):
        client.reload_context(
            session_id,
            snapshot_id=ordinary.id,
            requester_agent_id="alice",
        )


def test_orchestration_isolates_snapshot_pointer_and_delivery_state(tmp_path):
    client = MemoryClient(home=tmp_path)
    session_id = "same-harness-session-label"
    shared = client.add(
        "Deployment marker visible to both agents.",
        owner="alice",
        visibility=["global"],
    )
    alice_snapshot = client.offload_context(
        {"actor": "alice"},
        session_id,
        owner="alice",
    )

    alice_context = client.orchestrate_context(
        "deployment marker",
        session_id=session_id,
        requester_agent_id="alice",
    )
    bob_context = client.orchestrate_context(
        "deployment marker",
        session_id=session_id,
        requester_agent_id="bob",
    )

    assert alice_snapshot in alice_context.text
    assert shared.id in alice_context.delivered_ids
    assert alice_snapshot not in bob_context.text
    assert shared.id in bob_context.delivered_ids

    bob_snapshot = client.offload_context(
        {"actor": "bob"},
        session_id,
        owner="bob",
    )
    bob_context = client.orchestrate_context(
        "unrelated follow-up",
        session_id=session_id,
        requester_agent_id="bob",
    )
    assert bob_snapshot in bob_context.text
    assert alice_snapshot not in bob_context.text


def test_snapshot_rotation_keeps_limit_per_owner_and_session(tmp_path):
    client = MemoryClient(home=tmp_path)
    session_id = "shared-rotation-label"
    for step in range(6):
        client.offload_context(
            {"actor": "alice", "step": step},
            session_id,
            owner="alice",
        )
    for step in range(5):
        client.offload_context(
            {"actor": "bob", "step": step},
            session_id,
            owner="bob",
        )

    assert client.store.rotate_snapshots(keep_per_session=5) == 1
    alice_records = client.store.recent_snapshot_records(
        session_id,
        owner="alice",
        limit=10,
    )
    bob_records = client.store.recent_snapshot_records(
        session_id,
        owner="bob",
        limit=10,
    )
    assert len(alice_records) == 5
    assert len(bob_records) == 5
