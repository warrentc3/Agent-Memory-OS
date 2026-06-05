from __future__ import annotations

from agent_memory_os import MemoryClient
from agent_memory_os.context_pack import approx_tokens, build_context_pack_report
from agent_memory_os.schema import MemoryRecord, SearchResult


def test_truth_arbitration_keeps_authoritative_core_under_budget_pressure():
    core = MemoryRecord(
        id="mem_core_truth",
        content="Core truth: ACL hard gate must run before ranking, reranking, dedupe, and context packing.",
        type="fact",
        tags=["core", "authoritative", "acl"],
        confidence=0.98,
        importance=0.98,
        pinned=True,
        source={"permanence": True, "weight": 10, "claim_key": "acl_pipeline"},
    )
    noisy_results = [
        SearchResult(
            MemoryRecord(
                id=f"mem_noise_{idx}",
                content="Noisy emotional reflection about ACL ranking aesthetics and beautiful memory philosophy. " * 4,
                tags=["acl", "noise"],
                confidence=0.25,
                importance=0.2,
                source={"claim_key": f"noise_{idx}"},
            ),
            score=1.5,
            reason="fts",
        )
        for idx in range(4)
    ]
    report = build_context_pack_report(
        noisy_results + [SearchResult(core, score=0.7, reason="fts")],
        max_tokens=88,
    )

    assert "Core truth: ACL hard gate" in report.text
    assert approx_tokens(report.text) <= 88
    selected_ids = [decision.memory_id for decision in report.decisions if decision.selected]
    assert selected_ids[0] == "mem_core_truth"
    core_decision = next(decision for decision in report.decisions if decision.memory_id == "mem_core_truth")
    assert {"authoritative", "permanent", "weight_gt_8", "core_reserved_budget", "fits_budget"}.issubset(
        set(core_decision.reason)
    )
    assert any("low_confidence" in decision.reason and not decision.selected for decision in report.decisions)


def test_truth_arbitration_suppresses_duplicate_clusters_with_rejection_reasons():
    first = MemoryRecord(
        id="mem_dup_a",
        content="Reports must use UTC+8 Taipei timestamps.",
        type="preference",
        tags=["reports"],
        confidence=0.95,
        importance=0.9,
        source={"claim_key": "report_tz"},
    )
    duplicate = MemoryRecord(
        id="mem_dup_b",
        content="Reports must use UTC+8 Taipei timestamps.",
        type="preference",
        tags=["reports"],
        confidence=0.9,
        importance=0.85,
        source={"claim_key": "report_tz"},
    )

    report = build_context_pack_report(
        [SearchResult(first, score=1.0), SearchResult(duplicate, score=0.99)],
        max_tokens=120,
    )

    assert report.text.count("Reports must use UTC+8 Taipei timestamps.") == 1
    rejected = next(decision for decision in report.decisions if decision.memory_id == "mem_dup_b")
    assert rejected.selected is False
    assert "duplicate_cluster_suppressed" in rejected.reason


def test_truth_arbitration_marks_contradictions_instead_of_silently_blending():
    official = MemoryRecord(
        id="mem_policy_official",
        content="Official policy: fallback must never bypass ACL.",
        type="fact",
        tags=["policy", "authoritative"],
        confidence=0.96,
        importance=0.95,
        source={"claim_key": "fallback_acl", "claim": "must_not_bypass", "permanence": True, "weight": 10},
    )
    contradiction = MemoryRecord(
        id="mem_policy_contradiction",
        content="Draft note: fallback may bypass ACL in emergencies.",
        type="note",
        tags=["policy"],
        confidence=0.45,
        importance=0.6,
        source={"claim_key": "fallback_acl", "claim": "may_bypass"},
    )

    report = build_context_pack_report(
        [SearchResult(contradiction, score=1.1), SearchResult(official, score=0.9)],
        max_tokens=160,
    )

    assert "Official policy: fallback must never bypass ACL." in report.text
    assert "CONFLICT" in report.text
    decisions_by_id = {decision.memory_id: decision for decision in report.decisions}
    assert "conflict_detected" in decisions_by_id["mem_policy_official"].reason
    assert "conflict_detected" in decisions_by_id["mem_policy_contradiction"].reason


def test_context_pack_report_keeps_private_memory_absent_for_peer_requester(tmp_path):
    client = MemoryClient(home=tmp_path)
    private = client.add(
        "Private high-score truth for Mizuki only.",
        owner="mizuki",
        visibility=["agent"],
        tags=["truth", "acl"],
        confidence=1.0,
        importance=1.0,
        pinned=True,
        source={"permanence": True, "weight": 10},
    )
    client.add(
        "Global truth: ACL hard gate is mandatory.",
        owner="mizuki",
        visibility=["global"],
        tags=["truth", "acl", "authoritative"],
        confidence=0.95,
        importance=0.95,
        pinned=True,
        source={"permanence": True, "weight": 9},
    )

    report = client.context_pack_report("truth ACL", requester_agent_id="neo", max_tokens=100)

    assert "Private high-score truth for Mizuki only." not in report.text
    assert "Global truth: ACL hard gate is mandatory." in report.text
    assert all(decision.memory_id != private.id for decision in report.decisions)


def test_case_01_noisy_truth_authority_track_survives_fts_noise(tmp_path):
    client = MemoryClient(home=tmp_path)
    core = client.add(
        "Core bedrock: ACL hard gate must run before any ranking or context packing.",
        owner="mizuki",
        visibility=["global"],
        type="fact",
        tags=["core", "authoritative", "acl"],
        confidence=0.99,
        importance=1.0,
        pinned=True,
        source={
            "authoritative": True,
            "permanence": True,
            "weight": 10,
            "claim_key": "acl_pipeline_bedrock",
        },
    )
    for idx in range(50):
        client.add(
            f"Truth Noise_{idx}: a similar but low-confidence reflection that repeats Truth and noisy retrieval bait. " * 2,
            owner="mizuki",
            visibility=["global"],
            type="note",
            tags=["truth", "noise"],
            confidence=0.25,
            importance=0.1,
            source={"weight": 1, "claim_key": f"noise_{idx}"},
        )

    results = client.search("Truth", requester_agent_id="neo", limit=12)
    report = client.context_pack_report("Truth", requester_agent_id="neo", limit=12, max_tokens=200)

    assert results[0].record.id == core.id
    assert "authority_track" in results[0].reason
    assert "Noise_" in "\n".join(result.record.content for result in results[1:])
    assert "Core bedrock: ACL hard gate" in report.text
    selected_ids = [decision.memory_id for decision in report.decisions if decision.selected]
    assert selected_ids == [core.id]
    core_decision = next(decision for decision in report.decisions if decision.memory_id == core.id)
    assert {"authoritative", "permanent", "weight_gt_8", "core_reserved_budget"}.issubset(
        set(core_decision.reason)
    )
    assert any("budget_exceeded" in decision.reason for decision in report.decisions if not decision.selected)
