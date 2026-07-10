from agent_memory_os import MemoryClient, RecallProfile
from agent_memory_os.db import RESONANCE_MAX_EDGES_PER_NODE
from agent_memory_os.memory_resonance import ERATripletIndex, MemoryChunk

BACKDATED = "2020-01-01T00:00:00+00:00"


def test_stale_link_resonates_weaker_than_fresh_link(tmp_path):
    client = MemoryClient(home=tmp_path)
    seed = client.add("Staging deploy failed with database lock.", visibility=["global"])
    fresh = client.add("Snapshot procedure for safe rollbacks.", visibility=["global"])
    stale = client.add("Old mitigation writeup kept for reference.", visibility=["global"])
    client.link(seed.id, fresh.id, weight=0.8)
    client.link(seed.id, stale.id, weight=0.8)
    client.store.conn.execute(
        "UPDATE memory_links SET updated_at = ?, last_activated_at = ? WHERE dst_id = ?",
        (BACKDATED, BACKDATED, stale.id),
    )
    client.store.conn.commit()
    client.cache.clear()

    hits = {hit.record.id: hit for hit in client.search("deploy staging", requester_agent_id="neo")}

    assert hits[fresh.id].score > hits[stale.id].score


def test_hub_node_expands_only_top_k_edges(tmp_path):
    client = MemoryClient(home=tmp_path)
    hub = client.add("Hub anchor memory about releases.", visibility=["global"])
    neighbors = []
    total = RESONANCE_MAX_EDGES_PER_NODE + 3
    for i in range(total):
        neighbor = client.add(f"Satellite fact number {i} kept for context.", visibility=["global"])
        client.link(hub.id, neighbor.id, weight=0.9 - i * 0.02)
        neighbors.append(neighbor)

    hits = client.search("hub anchor releases", requester_agent_id="neo", limit=total + 5)
    hit_ids = {hit.record.id for hit in hits}

    surfaced = [n for n in neighbors if n.id in hit_ids]
    assert len(surfaced) == RESONANCE_MAX_EDGES_PER_NODE
    # The strongest edges win; the weakest three never surface.
    assert {n.id for n in neighbors[RESONANCE_MAX_EDGES_PER_NODE:]} & hit_ids == set()


def test_supersedes_demotes_stale_memory(tmp_path):
    client = MemoryClient(home=tmp_path)
    old = client.add(
        "Deploy target is port 8765.", visibility=["global"], importance=0.9, confidence=0.9
    )
    new = client.add(
        "Deploy target is port 8000.", visibility=["global"], importance=0.5, confidence=0.7
    )
    client.link(new.id, old.id, relation="supersedes", weight=1.0)

    hits = client.search("deploy target port", requester_agent_id="neo")
    by_id = {hit.record.id: hit for hit in hits}

    assert by_id[new.id].score > by_id[old.id].score
    assert f"superseded_by:{new.id}" in by_id[old.id].reason


def test_resonance_reason_carries_audit_path(tmp_path):
    client = MemoryClient(home=tmp_path)
    seed = client.add("Staging deploy failed with database lock.", visibility=["global"])
    neighbor = client.add("Snapshot procedure for safe rollbacks.", visibility=["global"])
    client.link(seed.id, neighbor.id, relation="caused_by", weight=0.9)

    hits = {hit.record.id: hit for hit in client.search("deploy staging", requester_agent_id="neo")}

    assert f"via:{seed.id}:caused_by" in hits[neighbor.id].reason


def test_negative_feedback_weakens_links_and_confidence(tmp_path):
    client = MemoryClient(home=tmp_path)
    a = client.add("Deploy checklist for staging.", visibility=["global"])
    b = client.add("Rollback snapshot rule.", visibility=["global"])
    client.link(a.id, b.id, weight=0.5)

    result = client.record_recall([a.id, b.id], helpful=False)

    assert result["weakened_memories"] == 2
    assert result["weakened_links"] == 1
    assert result["reinforced_memories"] == 0
    link = client.links(a.id)[0]
    assert round(link.weight, 2) == 0.4
    assert client.get(a.id).confidence < 0.8
    assert client.get(a.id).access_count == 0


def test_context_pack_auto_reinforce_closes_the_loop(tmp_path):
    client = MemoryClient(home=tmp_path)
    a = client.add("Deploy checklist for staging releases.", visibility=["global"])
    b = client.add("Deploy rollback snapshot rule.", visibility=["global"])
    client.link(a.id, b.id, weight=0.3)

    report = client.context_pack_report(
        "deploy staging rollback", requester_agent_id="neo", auto_reinforce=True
    )

    selected = [decision.memory_id for decision in report.decisions if decision.selected]
    assert set(selected) >= {a.id, b.id}
    assert client.get(a.id).access_count == 1
    assert client.get(b.id).access_count == 1
    link = client.links(a.id)[0]
    assert round(link.weight, 2) == 0.35
    assert link.activation_count == 1


def test_wal_mode_allows_two_clients_on_same_home(tmp_path):
    first = MemoryClient(home=tmp_path)
    second = MemoryClient(home=tmp_path)
    assert first.store.conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"

    first.add("Memory written by the first agent.", visibility=["global"])
    second.add("Memory written by the second agent.", visibility=["global"])

    contents = {hit.record.content for hit in second.search("memory agent", requester_agent_id="neo")}
    assert "Memory written by the first agent." in contents
    assert "Memory written by the second agent." in contents
    first.close()
    second.close()


def test_add_auto_link_creates_weak_related_edges(tmp_path):
    client = MemoryClient(home=tmp_path)
    existing = client.add("Turbovec semantic recall benchmark results.", visibility=["global"])
    unrelated = client.add("Pasta recipe with garlic and olive oil.", visibility=["global"])

    new = client.add(
        "Turbovec semantic recall latency findings.", visibility=["global"], auto_link=True
    )

    links = client.links(new.id)
    linked_ids = {link.dst_id for link in links} | {link.src_id for link in links}
    assert existing.id in linked_ids
    assert unrelated.id not in linked_ids
    assert all(link.relation == "related_to" for link in links)
    assert all(link.source.get("auto") == "fts_similarity" for link in links)


def test_era_derive_links_bridge_into_memory_links(tmp_path):
    client = MemoryClient(home=tmp_path)
    m1 = client.add("AgentMemoryOS uses Turbovec for semantic recall.", visibility=["global"])
    m2 = client.add("Turbovec semantic recall benchmark notes.", visibility=["global"])
    m3 = client.add("Cooking pasta with garlic tonight.", visibility=["global"])

    index = ERATripletIndex()
    for record in (m1, m2, m3):
        index.add_chunk(MemoryChunk(id=record.id, text=record.content))
    derived = index.derive_links(min_shared_terms=2)

    pair_ids = {frozenset((src, dst)) for src, dst, _ in derived}
    assert frozenset((m1.id, m2.id)) in pair_ids
    assert all(m3.id not in pair for pair in pair_ids)

    imported = client.import_links(derived, source={"auto": "era"})
    assert imported == len(derived)
    assert any({link.src_id, link.dst_id} == {m1.id, m2.id} for link in client.links(m1.id))


def test_saved_profile_auto_applies_across_client_instances(tmp_path):
    writer = MemoryClient(home=tmp_path)
    writer.add(
        "Coffee brewing procedure: 92C water, 1:15 ratio.",
        type="procedure",
        visibility=["global"],
    )
    writer.add(
        "Coffee brewing preference: strong in the morning.",
        type="preference",
        visibility=["global"],
    )
    writer.save_profile(
        RecallProfile(agent_id="neo", type_weights={"procedure": 1.5, "preference": 0.5})
    )
    writer.close()

    reader = MemoryClient(home=tmp_path)
    hits = reader.search("coffee brewing", requester_agent_id="neo")

    assert hits[0].record.type == "procedure"
    assert "+profile:" in hits[0].reason


def test_consolidate_merges_exact_duplicates_and_repoints_links(tmp_path):
    client = MemoryClient(home=tmp_path)
    first = client.add("Docker deploy uses port 8000.", visibility=["global"])
    second = client.add("Docker deploy uses port 8000.", visibility=["global"])
    other = client.add("Rollback snapshot rule.", visibility=["global"])
    client.link(second.id, other.id, weight=0.7)

    result = client.consolidate()

    assert result["duplicates_merged"] == 1
    assert client.stats()["total"] == 2
    survivors = {first.id, second.id} & {
        row for row in (first.id, second.id) if client.get(row) is not None
    }
    assert len(survivors) == 1
    survivor = survivors.pop()
    other_links = client.links(other.id)
    assert len(other_links) == 1
    assert {other_links[0].src_id, other_links[0].dst_id} == {survivor, other.id}


def test_consolidate_synthesizes_concept_from_corecall_cluster(tmp_path):
    client = MemoryClient(home=tmp_path)
    members = [
        client.add(f"Release ritual step {i}: verified detail.", visibility=["global"])
        for i in range(3)
    ]
    client.store.add_link(
        _colink(members[0].id, members[1].id)
    )
    client.store.add_link(
        _colink(members[1].id, members[2].id)
    )

    result = client.consolidate()
    assert result["concepts_created"] == 1

    derived = [
        link for link in client.links(members[0].id) if link.relation == "derived_from"
    ]
    assert len(derived) == 1
    concept = client.get(derived[0].src_id)
    assert concept.source.get("auto") == "consolidation"
    assert set(concept.source["consolidated_from"]) == {member.id for member in members}
    assert concept.content.startswith("Consolidated insight from 3 related memories:")

    # Idempotent: a second pass must not stack more concepts.
    assert client.consolidate()["concepts_created"] == 0


def test_consolidate_never_blends_across_visibility(tmp_path):
    client = MemoryClient(home=tmp_path)
    public_a = client.add("Shared ritual step one.", owner="mizuki", visibility=["global"])
    public_b = client.add("Shared ritual step two.", owner="mizuki", visibility=["global"])
    private = client.add("Private ritual reflection.", owner="mizuki", visibility=[])
    client.store.add_link(_colink(public_a.id, public_b.id))
    client.store.add_link(_colink(public_b.id, private.id))
    client.store.add_link(_colink(public_a.id, private.id))

    result = client.consolidate()

    assert result["concepts_created"] == 0


def _colink(src_id: str, dst_id: str):
    from agent_memory_os import MemoryLink

    return MemoryLink(
        src_id=src_id,
        dst_id=dst_id,
        relation="co_recalled",
        weight=0.7,
        activation_count=3,
    )


# --- Regression tests for the code-review findings ---


def test_negative_feedback_never_boosts_stale_memory(tmp_path):
    client = MemoryClient(home=tmp_path)
    stale = client.add("Old server ip is 10.0.0.5 for deploy.", visibility=["global"])
    client.store.conn.execute(
        "UPDATE memories SET updated_at = ?, created_at = ? WHERE id = ?",
        (BACKDATED, BACKDATED, stale.id),
    )
    client.store.conn.commit()
    client.cache.clear()

    before = client.search("server ip deploy", requester_agent_id="neo")[0].score
    client.record_recall([stale.id], helpful=False)
    after = client.search("server ip deploy", requester_agent_id="neo")[0].score

    assert after <= before


def test_bm25_stronger_match_ranks_higher(tmp_path):
    client = MemoryClient(home=tmp_path)
    for i in range(10):
        client.add(f"Noise document {i} about cats and weather patterns.", visibility=["global"])
    strong = client.add(
        "Deploy deploy deploy target port configuration for deploy pipeline.",
        visibility=["global"],
    )
    weak = client.add(
        "One passing mention of deploy inside a very long unrelated document "
        + "filler words " * 40,
        visibility=["global"],
    )

    hits = client.search("deploy", requester_agent_id="neo")
    positions = {hit.record.id: index for index, hit in enumerate(hits)}

    assert positions[strong.id] < positions[weak.id]


def test_consolidate_does_not_merge_long_prefix_divergent_content(tmp_path):
    client = MemoryClient(home=tmp_path)
    preamble = "Deployment checklist for service X after the database migration completes " * 4
    client.add(preamble + "then restart nginx immediately.", visibility=["global"])
    client.add(preamble + "then do NOT restart nginx under any circumstances.", visibility=["global"])

    result = client.consolidate()

    assert result["duplicates_merged"] == 0
    assert client.stats()["total"] == 2


def test_consolidate_keeps_pinned_authority_canonical(tmp_path):
    client = MemoryClient(home=tmp_path)
    pinned = client.add(
        "Bedrock rule: production deploys require approval.",
        visibility=["global"],
        confidence=0.8,
        pinned=True,
        source={"permanence": True, "weight": 10},
    )
    casual = client.add(
        "Bedrock rule: production deploys require approval.",
        visibility=["global"],
        confidence=0.95,
    )

    result = client.consolidate()

    assert result["duplicates_merged"] == 1
    assert client.get(pinned.id) is not None
    assert client.get(casual.id) is None


def test_consolidate_merge_does_not_duplicate_edges(tmp_path):
    client = MemoryClient(home=tmp_path)
    anchor = client.add("Unrelated anchor memory xyz.", visibility=["global"])
    canonical = client.add("The deploy password rotation procedure.", visibility=["global"], confidence=0.9)
    duplicate = client.add("The deploy password rotation procedure.", visibility=["global"], confidence=0.5)
    client.link(anchor.id, canonical.id, weight=0.9)
    client.link(duplicate.id, anchor.id, weight=0.2)

    client.consolidate()

    edges = client.links(anchor.id)
    assert len(edges) == 1
    assert edges[0].weight == 0.9


def test_record_recall_never_touches_supersedes_edges(tmp_path):
    client = MemoryClient(home=tmp_path)
    new = client.add("Deploy target is port 8000.", visibility=["global"])
    old = client.add("Deploy target is port 8765.", visibility=["global"])
    client.link(new.id, old.id, relation="supersedes", weight=1.0)

    result = client.record_recall([new.id, old.id])

    assert result["reinforced_links"] == 0
    link = client.links(new.id)[0]
    assert link.weight == 1.0
    assert link.activation_count == 0


def test_record_recall_requester_cannot_affect_invisible_memories(tmp_path):
    client = MemoryClient(home=tmp_path)
    private = client.add("Private journal entry.", owner="mizuki", visibility=[], confidence=0.8)
    public = client.add("Public checklist entry.", owner="mizuki", visibility=["global"], confidence=0.8)

    result = client.record_recall(
        [private.id, public.id], helpful=False, requester_agent_id="neo"
    )

    assert result["weakened_memories"] == 1
    assert client.get(private.id).confidence == 0.8
    assert client.get(public.id).confidence < 0.8


def test_import_links_preserves_reinforced_weights(tmp_path):
    client = MemoryClient(home=tmp_path)
    a = client.add("Turbovec semantic recall notes.", visibility=["global"])
    b = client.add("Turbovec benchmark results.", visibility=["global"])
    client.link(a.id, b.id, weight=0.9)

    imported = client.import_links([(a.id, b.id, 0.3)])

    assert imported == 0
    assert client.links(a.id)[0].weight == 0.9


def test_load_profile_sees_profiles_saved_by_another_client(tmp_path):
    reader = MemoryClient(home=tmp_path)
    assert reader.load_profile("neo") is None

    writer = MemoryClient(home=tmp_path)
    writer.save_profile(RecallProfile(agent_id="neo", type_weights={"procedure": 1.5}))

    refreshed = reader.load_profile("neo")
    assert refreshed is not None
    assert refreshed.type_weights == {"procedure": 1.5}
