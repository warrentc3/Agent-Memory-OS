import json

from agent_memory_os.shadow_mode import ShadowRecallMonitor


def test_shadow_monitor_records_legacy_and_agent_memory_recall_comparison(tmp_path):
    log_path = tmp_path / "shadow_recall.jsonl"
    monitor = ShadowRecallMonitor(log_path=log_path)

    record = monitor.compare_recall(
        query="Who handles persistent memory?",
        legacy_results=["Neo uses Mem0 for persistent memory", "ACL hardening prevents leaks"],
        candidate_results=["Neo uses Mem0 for persistent memory", "Graph resonance expands recall"],
        legacy_latency_ms=120.5,
        candidate_latency_ms=88.0,
        acl_leakage=False,
    )

    assert record["top_k_hit_rate"] == 0.5
    assert record["latency_delta_ms"] == -32.5
    assert record["acl_zero_leakage"] is True
    assert record["phase"] == "Phase 1: Silent Mirroring"

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    persisted = json.loads(lines[0])
    assert persisted["query"] == "Who handles persistent memory?"
    assert persisted["legacy_count"] == 2
    assert persisted["candidate_count"] == 2


def test_shadow_monitor_flags_no_go_on_acl_leakage(tmp_path):
    monitor = ShadowRecallMonitor(log_path=tmp_path / "shadow_recall.jsonl")

    record = monitor.compare_recall(
        query="private fact",
        legacy_results=["allowed memory"],
        candidate_results=["allowed memory", "private unauthorized memory"],
        legacy_latency_ms=20,
        candidate_latency_ms=25,
        acl_leakage=True,
    )

    assert record["acl_zero_leakage"] is False
    assert record["go_no_go"] == "NO_GO_ACL_LEAKAGE"


def test_shadow_monitor_summarizes_kpis_from_jsonl(tmp_path):
    log_path = tmp_path / "shadow_recall.jsonl"
    monitor = ShadowRecallMonitor(log_path=log_path)
    monitor.compare_recall(
        query="q1",
        legacy_results=["a", "b"],
        candidate_results=["a", "b"],
        legacy_latency_ms=100,
        candidate_latency_ms=110,
    )
    monitor.compare_recall(
        query="q2",
        legacy_results=["a", "b"],
        candidate_results=["a"],
        legacy_latency_ms=100,
        candidate_latency_ms=600,
    )

    summary = monitor.summarize()

    assert summary["records"] == 2
    assert summary["mean_top_k_hit_rate"] == 0.75
    assert summary["p99_candidate_latency_ms"] == 600
    assert summary["no_go_count"] == 1
