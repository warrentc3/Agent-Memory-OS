from __future__ import annotations

from datetime import timedelta

from agent_memory_os import MemoryClient
from agent_memory_os.timestamp_converters import dt_to_stamp, utc_now_dt


def _future_iso(days: int = 1) -> str:
    return dt_to_stamp(utc_now_dt() + timedelta(days=days))


def _past_iso(days: int = 1) -> str:
    return dt_to_stamp(utc_now_dt() - timedelta(days=days))


def test_zero_fts_hits_can_fallback_to_allowed_recent_core_memory(tmp_path):
    """Lineage:
    main: introduced 06716fb0@pre-migration-registry.
    """
    client = MemoryClient(home=tmp_path)
    client.add(
        "Warm cocoa is the authoritative comfort ritual.",
        owner="mizuki",
        visibility=["global"],
        type="preference",
        tags=["comfort", "core"],
        importance=1.0,
        confidence=1.0,
        pinned=True,
    )

    hits = client.search("暖心的東西", requester_agent_id="neo", limit=5)

    assert [hit.record.content for hit in hits] == ["Warm cocoa is the authoritative comfort ritual."]
    assert hits[0].reason.startswith("fallback:")


def test_fallback_does_not_leak_private_memory(tmp_path):
    """Lineage:
    main: introduced 06716fb0@pre-migration-registry.
    """
    client = MemoryClient(home=tmp_path)
    client.add(
        "Mizuki private comfort memory must never leak.",
        owner="mizuki",
        visibility=["agent"],
        type="preference",
        tags=["comfort", "core"],
        importance=1.0,
        confidence=1.0,
        pinned=True,
    )
    client.add(
        "Global comfort guideline is safe to share.",
        owner="mizuki",
        visibility=["global"],
        type="preference",
        tags=["comfort", "core"],
        importance=0.8,
        confidence=0.9,
        pinned=True,
    )

    hits = client.search("沒有詞彙重疊的安撫需求", requester_agent_id="neo", limit=5)

    contents = [hit.record.content for hit in hits]
    assert "Mizuki private comfort memory must never leak." not in contents
    assert contents == ["Global comfort guideline is safe to share."]


def test_fallback_excludes_expired_memories(tmp_path):
    """Lineage:
    main: introduced 06716fb0@pre-migration-registry.
    time-helper: changed working-tree@db-schema-v22.
    direct migration binding: v21.
    """
    client = MemoryClient(home=tmp_path)
    client.add(
        "Expired pinned comfort memory is invalid.",
        owner="mizuki",
        visibility=["global"],
        type="preference",
        tags=["comfort", "core"],
        importance=1.0,
        confidence=1.0,
        pinned=True,
        expires_at=_past_iso(),
    )
    client.add(
        "Current comfort memory remains valid.",
        owner="mizuki",
        visibility=["global"],
        type="preference",
        tags=["comfort", "core"],
        importance=0.9,
        confidence=1.0,
        pinned=True,
        expires_at=_future_iso(),
    )

    hits = client.search("沒有詞彙重疊的安撫需求", requester_agent_id="neo", limit=5)

    contents = [hit.record.content for hit in hits]
    assert "Expired pinned comfort memory is invalid." not in contents
    assert contents == ["Current comfort memory remains valid."]


def test_index_rebuild_preserves_memory_ids_and_records(tmp_path):
    """Lineage:
    main: introduced 06716fb0@pre-migration-registry.
    """
    client = MemoryClient(home=tmp_path)
    original = client.add(
        "Rebuild must preserve this source-of-truth record.",
        owner="neo",
        visibility=["global"],
        type="fact",
        tags=["rebuild"],
        source={"team_id": "engineering", "origin": "test"},
        importance=0.77,
        confidence=0.88,
        pinned=True,
    )

    before = client.get(original.id)
    rebuilt = client.rebuild_indexes()
    after = client.get(original.id)

    assert rebuilt["memories_indexed"] == 1
    assert after == before
    hits = client.search("source-of-truth", requester_agent_id="mizuki")
    assert [hit.record.id for hit in hits] == [original.id]
