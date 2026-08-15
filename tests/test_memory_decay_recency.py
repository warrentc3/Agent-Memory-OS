from datetime import timedelta

import pytest

from agent_memory_os import MemoryClient, MemoryRecord
from agent_memory_os.timestamp_converters import dt_to_stamp, utc_now_dt


def iso_days_ago(days: int) -> str:
    return dt_to_stamp(utc_now_dt() - timedelta(days=days))


def iso_days_from_now(days: int) -> str:
    return dt_to_stamp(utc_now_dt() + timedelta(days=days))


def test_decay_fields_default_to_safe_values():
    """Lineage:
    main: introduced 7231a70d@pre-migration-registry.
    """
    rec = MemoryRecord(content="Default decay metadata")

    assert rec.decay_policy == "exponential"
    assert rec.decay_half_life_days > 0
    assert rec.last_accessed_at is None
    assert rec.access_count == 0
    assert rec.pinned is False


def test_invalid_decay_policy_is_rejected():
    """Lineage:
    main: introduced 7231a70d@pre-migration-registry.
    """
    with pytest.raises(ValueError, match="decay_policy"):
        MemoryRecord(content="bad", decay_policy="forever")


def test_non_positive_decay_half_life_is_rejected():
    """Lineage:
    main: introduced 7231a70d@pre-migration-registry.
    """
    with pytest.raises(ValueError, match="decay_half_life_days"):
        MemoryRecord(content="bad", decay_policy="linear", decay_half_life_days=0)


def test_recent_memory_ranks_above_stale_similar_memory(tmp_path):
    """Lineage:
    main: introduced 7231a70d@pre-migration-registry.
    """
    client = MemoryClient(home=tmp_path)
    client.add(
        "ranking-token deployment fact recent",
        owner="neo",
        visibility=["global"],
        importance=0.5,
        confidence=0.8,
        updated_at=iso_days_ago(1),
        decay_policy="exponential",
        decay_half_life_days=30,
    )
    client.add(
        "ranking-token deployment fact stale",
        owner="neo",
        visibility=["global"],
        importance=0.5,
        confidence=0.8,
        updated_at=iso_days_ago(180),
        decay_policy="exponential",
        decay_half_life_days=30,
    )

    hits = client.search("ranking-token deployment", requester_agent_id="guest")

    assert [hit.record.content for hit in hits][:2] == [
        "ranking-token deployment fact recent",
        "ranking-token deployment fact stale",
    ]
    assert hits[0].score > hits[1].score


def test_important_old_memory_can_beat_recent_low_importance_memory(tmp_path):
    """Lineage:
    main: introduced 7231a70d@pre-migration-registry.
    """
    client = MemoryClient(home=tmp_path)
    client.add(
        "priority-token architectural decision",
        owner="neo",
        visibility=["global"],
        importance=1.0,
        confidence=1.0,
        updated_at=iso_days_ago(120),
        decay_policy="exponential",
        decay_half_life_days=365,
    )
    client.add(
        "priority-token architectural trivia",
        owner="neo",
        visibility=["global"],
        importance=0.0,
        confidence=0.2,
        updated_at=iso_days_ago(1),
        decay_policy="exponential",
        decay_half_life_days=30,
    )

    hits = client.search("priority-token architectural", requester_agent_id="guest")

    assert hits[0].record.content == "priority-token architectural decision"
    assert hits[0].score > hits[1].score


def test_expired_memory_is_never_returned_even_if_important(tmp_path):
    """Lineage:
    main: introduced 7231a70d@pre-migration-registry.
    """
    client = MemoryClient(home=tmp_path)
    client.add(
        "expiry-token active fact",
        owner="neo",
        visibility=["global"],
        importance=0.1,
        expires_at=iso_days_from_now(1),
    )
    client.add(
        "expiry-token expired important fact",
        owner="neo",
        visibility=["global"],
        importance=1.0,
        pinned=True,
        expires_at=iso_days_ago(1),
    )

    hits = client.search("expiry-token", requester_agent_id="guest")

    assert [hit.record.content for hit in hits] == ["expiry-token active fact"]
