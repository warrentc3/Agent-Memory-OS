from agent_memory_os import MemoryClient

SECRET = "Private Lo-fi pressure-relief preference for dear user."


def test_agent_visibility_blocks_cross_agent_semantic_search(tmp_path):
    """Lineage:
    main: introduced ac8ad376@pre-migration-registry.
    """
    client = MemoryClient(home=tmp_path)
    client.add(
        SECRET,
        owner="agent-a",
        visibility=["agent"],
        tags=["lofi", "stress"],
        importance=0.95,
    )
    client.add(
        "Public Lo-fi playlist recommendation.",
        owner="agent-a",
        visibility=["global"],
        tags=["lofi"],
    )

    hits = client.search("Lo-fi pressure", requester_agent_id="agent-b")

    contents = [hit.record.content for hit in hits]
    assert SECRET not in contents
    assert "Public Lo-fi playlist recommendation." in contents


def test_agent_visibility_allows_owner_search(tmp_path):
    """Lineage:
    main: introduced ac8ad376@pre-migration-registry.
    """
    client = MemoryClient(home=tmp_path)
    client.add(
        SECRET,
        owner="agent-a",
        visibility=["agent"],
        tags=["lofi", "stress"],
    )

    hits = client.search("Lo-fi pressure", requester_agent_id="agent-a")

    assert [hit.record.content for hit in hits] == [SECRET]


def test_context_pack_reapplies_visibility_filter(tmp_path):
    """Lineage:
    main: introduced ac8ad376@pre-migration-registry.
    """
    client = MemoryClient(home=tmp_path)
    client.add(
        SECRET,
        owner="agent-a",
        visibility=["agent"],
        tags=["lofi", "stress"],
    )
    client.add(
        "Global stress handling guideline.",
        owner="agent-a",
        visibility=["global"],
        tags=["stress"],
    )

    pack = client.context_pack("stress Lo-fi", requester_agent_id="agent-b", max_tokens=160)

    assert SECRET not in pack
    assert "Global stress handling guideline." in pack


def test_scoped_agent_allowlist_visibility(tmp_path):
    """Lineage:
    main: introduced ac8ad376@pre-migration-registry.
    """
    client = MemoryClient(home=tmp_path)
    client.add(
        "Scoped deployment preference for Neo only.",
        owner="mizuki",
        visibility=["agent:neo"],
        tags=["deployment"],
    )

    neo_hits = client.search("deployment preference", requester_agent_id="neo")
    generic_hits = client.search("deployment preference", requester_agent_id="generic-subagent")

    assert [hit.record.content for hit in neo_hits] == ["Scoped deployment preference for Neo only."]
    assert generic_hits == []


def test_pinned_private_memory_still_hidden_from_other_agent(tmp_path):
    """Lineage:
    main: introduced 7231a70d@pre-migration-registry.
    """
    client = MemoryClient(home=tmp_path)
    client.add(
        SECRET,
        owner="agent-a",
        visibility=["agent"],
        tags=["lofi", "stress"],
        importance=1.0,
        confidence=1.0,
        pinned=True,
    )
    client.add(
        "Global visible fallback for pressure relief.",
        owner="agent-a",
        visibility=["global"],
        tags=["lofi", "stress"],
    )

    hits = client.search("Lo-fi pressure", requester_agent_id="agent-b")

    contents = [hit.record.content for hit in hits]
    assert SECRET not in contents
    assert "Global visible fallback for pressure relief." in contents


def test_fresh_private_memory_still_hidden_from_context_pack(tmp_path):
    """Lineage:
    main: introduced 7231a70d@pre-migration-registry.
    """
    client = MemoryClient(home=tmp_path)
    client.add(
        SECRET,
        owner="agent-a",
        visibility=["agent"],
        tags=["lofi", "stress"],
        decay_policy="none",
        pinned=True,
    )
    client.add(
        "Global stress guideline survives private freshness.",
        owner="agent-a",
        visibility=["global"],
        tags=["stress"],
    )

    pack = client.context_pack("stress Lo-fi", requester_agent_id="agent-b", max_tokens=160)

    assert SECRET not in pack
    assert "Global stress guideline survives private freshness." in pack
