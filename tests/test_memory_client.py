from agent_memory_os import MemoryClient


def test_add_search_and_context_pack(tmp_path):
    """Lineage:
    main: introduced d02c22b5@pre-migration-registry.
    """
    client = MemoryClient(home=tmp_path)
    rec = client.add(
        "User prefers Traditional Chinese responses.",
        owner="bastet-agent",
        scope="user",
        type="preference",
        tags=["language"],
        importance=0.9,
    )

    assert rec.id.startswith("mem_")
    hits = client.search("Traditional Chinese", owner="bastet-agent")
    assert hits
    assert hits[0].record.content == "User prefers Traditional Chinese responses."

    pack = client.context_pack("How should I answer this user? Traditional Chinese", owner="bastet-agent", max_tokens=120)
    assert "MEMORY CONTEXT PACK" in pack
    assert "Traditional Chinese" in pack


def test_owner_filter(tmp_path):
    """Lineage:
    main: introduced d02c22b5@pre-migration-registry.
    """
    client = MemoryClient(home=tmp_path)
    client.add("Neo memory about NAS", owner="neo", tags=["nas"])
    client.add("Mizuki memory about NAS", owner="mizuki", tags=["nas"])

    hits = client.search("NAS", owner="neo")
    assert len(hits) == 1
    assert hits[0].record.owner == "neo"


def test_stats_and_cache(tmp_path):
    """Lineage:
    main: introduced d02c22b5@pre-migration-registry.
    """
    client = MemoryClient(home=tmp_path, cache_items=2)
    client.add("A fact about reports", owner="bastet-agent", scope="project", type="fact")
    assert client.stats()["total"] == 1
    client.search("reports", owner="bastet-agent")
    assert client.stats()["cache_items"] >= 1
