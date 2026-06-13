import json
import subprocess
import sys

from agent_memory_os.shadow_mode import ShadowRecallMonitor, summarize_shadow_log


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
    assert summary["activation_gate"] == "NO_GO_HAS_BLOCKING_RECORDS"
    assert summary["acl_leakage_count"] == 0
    assert summary["production_injection_count"] == 0


def test_summarize_shadow_log_builds_evidence_pack_with_profiles_and_import_totals(tmp_path):
    log_path = tmp_path / "shadow_recall.jsonl"
    records = [
        {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "phase": "Phase 1: Silent Mirroring",
            "query": "neo query",
            "profile": "neo",
            "top_k_hit_rate": 1.0,
            "candidate_latency_ms": 25.0,
            "acl_zero_leakage": True,
            "production_injection": False,
            "go_no_go": "GO",
            "import_report": {"scanned": 2, "inserted": 2, "updated": 0, "skipped": 0},
        },
        {
            "timestamp": "2026-01-01T00:01:00+00:00",
            "phase": "Phase 1: Silent Mirroring",
            "query": "mizuki query",
            "profile": "mizuki",
            "top_k_hit_rate": 1.0,
            "candidate_latency_ms": 30.0,
            "acl_zero_leakage": True,
            "production_injection": False,
            "go_no_go": "GO",
            "import_report": {"scanned": 3, "inserted": 0, "updated": 1, "skipped": 2},
        },
    ]
    log_path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")

    summary = summarize_shadow_log(log_path)

    assert summary["activation_gate"] == "GO"
    assert summary["profile_distribution"] == {"mizuki": 1, "neo": 1}
    assert summary["import_totals"] == {"scanned": 5, "inserted": 2, "updated": 1, "skipped": 2}
    assert summary["p50_candidate_latency_ms"] == 27.5
    assert summary["latest"]["profile"] == "mizuki"


def test_cli_shadow_summary_outputs_json_evidence_pack(tmp_path):
    log_path = tmp_path / "shadow_recall.jsonl"
    log_path.write_text(
        json.dumps(
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "phase": "Phase 1: Silent Mirroring",
                "query": "q",
                "profile": "neo",
                "top_k_hit_rate": 0.0,
                "candidate_latency_ms": 5.0,
                "acl_zero_leakage": True,
                "production_injection": False,
                "go_no_go": "WATCH_RECALL_BELOW_TARGET",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "-m", "agent_memory_os.cli", "shadow-summary", "--log", str(log_path), "--json"],
        check=True,
        text=True,
        capture_output=True,
    )
    summary = json.loads(result.stdout)

    assert summary["records"] == 1
    assert summary["activation_gate"] == "WATCH_RECALL_BELOW_TARGET"
    assert summary["profile_distribution"] == {"neo": 1}
