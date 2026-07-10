from agent_memory_os import MemoryClient, RecallProfile


def test_link_crud_and_index_rebuild_survival(tmp_path):
    client = MemoryClient(home=tmp_path)
    a = client.add("Staging deploy failed with database lock.", visibility=["global"])
    b = client.add("Snapshot rule: create a rollback snapshot before schema changes.", visibility=["global"])

    client.link(a.id, b.id, relation="caused_by", weight=0.8)

    links = client.links(a.id)
    assert len(links) == 1
    assert links[0].relation == "caused_by"
    assert links[0].weight == 0.8

    client.rebuild_indexes()
    assert len(client.links(a.id)) == 1
    assert client.stats()["links"] == 1

    assert client.unlink(a.id, b.id) is True
    assert client.links(a.id) == []


def test_resonance_surfaces_linked_memory_missing_query_terms(tmp_path):
    client = MemoryClient(home=tmp_path)
    a = client.add("Staging deploy failed with database lock.", visibility=["global"])
    b = client.add("Snapshot rule: create a rollback backup before schema changes.", visibility=["global"])
    client.link(a.id, b.id, relation="caused_by", weight=0.9)

    hits = client.search("deploy staging", requester_agent_id="neo")

    by_id = {hit.record.id: hit for hit in hits}
    assert a.id in by_id
    assert b.id in by_id
    assert by_id[b.id].reason.startswith("resonance:hop1")
    assert by_id[b.id].score < by_id[a.id].score


def test_resonance_private_neighbor_not_returned_and_not_traversable(tmp_path):
    client = MemoryClient(home=tmp_path, resonance_hops=2)
    a = client.add(
        "Team deploy checklist for staging releases.",
        owner="mizuki",
        visibility=["global"],
    )
    private = client.add(
        "Private emotional journal entry about release-night anxiety.",
        owner="mizuki",
        visibility=[],
    )
    c = client.add(
        "Retro notes on incident response coordination.",
        owner="mizuki",
        visibility=["global"],
    )
    client.link(a.id, private.id, weight=0.9)
    client.link(private.id, c.id, weight=0.9)

    neo_hits = client.search("deploy checklist staging", requester_agent_id="neo")
    neo_ids = {hit.record.id for hit in neo_hits}
    assert a.id in neo_ids
    assert private.id not in neo_ids
    # The public memory behind the private node must stay unreachable: an
    # invisible node cannot bridge two visible ones for an unauthorized requester.
    assert c.id not in neo_ids

    mizuki_hits = client.search("deploy checklist staging", requester_agent_id="mizuki")
    mizuki_ids = {hit.record.id for hit in mizuki_hits}
    assert {a.id, private.id, c.id} <= mizuki_ids


def test_resonance_excludes_expired_neighbor(tmp_path):
    client = MemoryClient(home=tmp_path)
    a = client.add("Staging deploy failed with database lock.", visibility=["global"])
    expired = client.add(
        "Old mitigation runbook that no longer applies.",
        visibility=["global"],
        expires_at="2020-01-01T00:00:00+00:00",
    )
    client.link(a.id, expired.id, weight=0.9)

    hits = client.search("deploy staging", requester_agent_id="neo")

    assert expired.id not in {hit.record.id for hit in hits}


def test_record_recall_reinforces_links_and_creates_colinks(tmp_path):
    client = MemoryClient(home=tmp_path)
    a = client.add("Deploy checklist for staging.", visibility=["global"])
    b = client.add("Rollback snapshot rule.", visibility=["global"])
    c = client.add("Incident escalation contact list.", visibility=["global"])
    client.link(a.id, b.id, weight=0.3)

    result = client.record_recall([a.id, b.id, c.id], create_colinks=True)

    assert result["reinforced_memories"] == 3
    assert result["reinforced_links"] == 1
    assert result["created_links"] == 2
    ab = [link for link in client.links(a.id) if {link.src_id, link.dst_id} == {a.id, b.id}]
    assert ab[0].weight > 0.3
    assert ab[0].activation_count == 1
    colinks = [link for link in client.links(c.id)]
    assert len(colinks) == 2
    assert all(link.relation == "co_recalled" for link in colinks)
    assert client.get(a.id).access_count == 1

    # Repeated recall keeps strengthening the same edge.
    client.record_recall([a.id, b.id])
    ab_after = [link for link in client.links(a.id) if {link.src_id, link.dst_id} == {a.id, b.id}]
    assert ab_after[0].weight > ab[0].weight
    assert client.get(a.id).access_count == 2


def test_recall_profile_reorders_types_per_agent_persona(tmp_path):
    client = MemoryClient(home=tmp_path)
    client.add(
        "Coffee brewing procedure: 92C water, 1:15 ratio, 3 minute steep.",
        type="procedure",
        visibility=["global"],
    )
    client.add(
        "Coffee brewing preference: user likes it strong in the morning.",
        type="preference",
        visibility=["global"],
    )

    engineer = RecallProfile(agent_id="neo", type_weights={"procedure": 1.5, "preference": 0.5})
    companion = RecallProfile(agent_id="mizuki", type_weights={"procedure": 0.5, "preference": 1.5})

    engineer_hits = client.search("coffee brewing", requester_agent_id="neo", profile=engineer)
    companion_hits = client.search("coffee brewing", requester_agent_id="mizuki", profile=companion)

    assert engineer_hits[0].record.type == "procedure"
    assert companion_hits[0].record.type == "preference"
    assert "+profile:" in engineer_hits[0].reason


def test_profile_never_reveals_hidden_memories(tmp_path):
    client = MemoryClient(home=tmp_path)
    client.add(
        "Private preference only for owner.",
        owner="mizuki",
        type="preference",
        visibility=[],
    )
    greedy = RecallProfile(agent_id="neo", type_weights={"preference": 100.0})

    hits = client.search("private preference", requester_agent_id="neo", profile=greedy)

    assert hits == []
