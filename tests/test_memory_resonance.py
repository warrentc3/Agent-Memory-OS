from agent_memory_os.memory_resonance import ERATripletIndex, MemoryChunk


def test_era_index_extracts_entities_relations_and_attributes_from_memory_chunks():
    index = ERATripletIndex()

    chunk = MemoryChunk(
        id="m1",
        text="Neo uses Mem0 for persistent memory and evolves from v0.3 to v0.4.",
        timestamp="2026-06-05T12:00:00+08:00",
    )
    index.add_chunk(chunk)

    triplets = index.triplets_for_chunk("m1")

    assert ("Neo", "uses", "Mem0") in triplets
    assert ("Neo", "evolves_from", "v0.3") in triplets
    assert ("Neo", "evolves_to", "v0.4") in triplets
    assert ("Neo", "timestamp", "2026-06-05T12:00:00+08:00") in triplets


def test_era_index_expands_two_hop_resonance_cluster_from_seed():
    index = ERATripletIndex()
    index.add_chunk(MemoryChunk(id="m1", text="Neo mentions Mem0 and Sovereign Mode."))
    index.add_chunk(MemoryChunk(id="m2", text="Mem0 relates to ACL hardening."))
    index.add_chunk(MemoryChunk(id="m3", text="ACL hardening supports zero leakage."))
    index.add_chunk(MemoryChunk(id="m4", text="Unrelated topic describes music generation."))

    cluster = index.resonance_cluster(["m1"], hops=2)

    assert cluster == ["m1", "m2", "m3"]


def test_era_index_ranks_resonance_by_seed_distance_then_overlap():
    index = ERATripletIndex()
    index.add_chunk(MemoryChunk(id="seed", text="Neo mentions Mem0 and ACL."))
    index.add_chunk(MemoryChunk(id="near", text="Mem0 supports recall."))
    index.add_chunk(MemoryChunk(id="strong", text="Mem0 and ACL support recall."))
    index.add_chunk(MemoryChunk(id="far", text="Recall enables graph resonance."))

    cluster = index.resonance_cluster(["seed"], hops=2)

    assert cluster[:3] == ["seed", "strong", "near"]
    assert "far" in cluster
