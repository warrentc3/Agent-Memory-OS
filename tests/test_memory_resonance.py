import pytest

from agent_memory_os.memory_resonance import (
    ERATripletIndex,
    MemoryChunk,
    ResonanceWeight,
)


def test_era_index_extracts_entities_relations_and_attributes_from_memory_chunks():
    """Lineage:
    main: introduced 246961e6@pre-migration-registry.
    time-helper: changed 0457965a@db-schema-v21; d6884ee6@db-schema-v22.
    """
    index = ERATripletIndex()

    chunk = MemoryChunk(
        id="m1",
        text="Neo uses Mem0 for persistent memory and evolves from v0.3 to v0.4.",
        timestamp="2026-06-05T04:00:00.000000Z",
    )
    index.add_chunk(chunk)

    triplets = index.triplets_for_chunk("m1")

    assert ("Neo", "uses", "Mem0") in triplets
    assert ("Neo", "evolves_from", "v0.3") in triplets
    assert ("Neo", "evolves_to", "v0.4") in triplets
    assert ("Neo", "timestamp", "2026-06-05T04:00:00.000000Z") in triplets


def test_era_index_rejects_non_stamp_string_timestamps():
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced d6884ee6@db-schema-v22.
    """
    index = ERATripletIndex()

    with pytest.raises(ValueError, match="timestamp must match"):
        index.add_chunk(MemoryChunk(id="m1", text="Neo uses Mem0.", timestamp="yesterday"))


@pytest.mark.parametrize("text", ["neo uses mem0.", "lowercase text only"])
def test_era_index_validates_string_timestamp_without_primary_entity(text: str):
    index = ERATripletIndex()
    index.add_chunk(MemoryChunk(id="m1", text="Neo uses Mem0."))
    original_triplets = index.triplets_for_chunk("m1")

    with pytest.raises(ValueError, match="timestamp must match"):
        index.add_chunk(MemoryChunk(id="m1", text=text, timestamp="yesterday"))

    assert index.triplets_for_chunk("m1") == original_triplets


def test_resonance_weight_preserves_no_decay_and_floor_policies():
    """Lineage:
    main: absent at 2f7a859.
    time-helper: introduced 0457965a@db-schema-v21.
    """
    assert ResonanceWeight.calculate(0.5, 100.0, current_time=100.0) == 0.5
    assert ResonanceWeight.calculate(0.5, 0.0, current_time=10_000_000.0) == 0.01


def test_era_index_expands_two_hop_resonance_cluster_from_seed():
    """Lineage:
    main: introduced 246961e6@pre-migration-registry.
    """
    index = ERATripletIndex()
    index.add_chunk(MemoryChunk(id="m1", text="Neo mentions Mem0 and Sovereign Mode."))
    index.add_chunk(MemoryChunk(id="m2", text="Mem0 relates to ACL hardening."))
    index.add_chunk(MemoryChunk(id="m3", text="ACL hardening supports zero leakage."))
    index.add_chunk(MemoryChunk(id="m4", text="Unrelated topic describes music generation."))

    cluster = index.resonance_cluster(["m1"], hops=2)

    assert cluster == ["m1", "m2", "m3"]


def test_era_index_ranks_resonance_by_seed_distance_then_overlap():
    """Lineage:
    main: introduced 246961e6@pre-migration-registry.
    """
    index = ERATripletIndex()
    index.add_chunk(MemoryChunk(id="seed", text="Neo mentions Mem0 and ACL."))
    index.add_chunk(MemoryChunk(id="near", text="Mem0 supports recall."))
    index.add_chunk(MemoryChunk(id="strong", text="Mem0 and ACL support recall."))
    index.add_chunk(MemoryChunk(id="far", text="Recall enables graph resonance."))

    cluster = index.resonance_cluster(["seed"], hops=2)

    assert cluster[:3] == ["seed", "strong", "near"]
    assert "far" in cluster
