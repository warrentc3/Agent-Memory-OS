from fastapi.testclient import TestClient

from agent_memory_os import MemoryClient
from agent_memory_os.web_app import create_app


def seeded_client(tmp_path) -> tuple[MemoryClient, dict]:
    client = MemoryClient(home=tmp_path)
    records = {
        "bedrock": client.add(
            "Production deploys always require sign-off.",
            visibility=["global"], pinned=True,
            source={"permanence": True, "weight": 10},
        ),
        "warning": client.add(
            "Never run retention against a NAS-mounted database home.",
            type="warning", visibility=["global"], importance=0.9,
        ),
        "procedure": client.add(
            "Release procedure: bump version, tag, push tags.",
            type="procedure", visibility=["global"], importance=0.8,
        ),
        "relevant": client.add(
            "The staging deploy pipeline uses port 8000.",
            visibility=["global"],
        ),
        "noise": client.add(
            "Pasta recipe with garlic and olive oil.",
            visibility=["global"],
        ),
    }
    return client, records


def test_orchestrator_buckets_and_proactive_recall(tmp_path):
    client, records = seeded_client(tmp_path)

    result = client.orchestrate_context(
        "prepare the staging deploy", requester_agent_id="neo", max_tokens=2000
    )

    assert result.used_tokens <= result.max_tokens
    assert "## BEDROCK" in result.text
    assert records["bedrock"].id in result.sections["bedrock"]["memory_ids"]
    # warning/procedure wording does not match the task — proactive recall
    # must surface them anyway
    assert records["warning"].id in result.sections["warnings"]["memory_ids"]
    assert records["procedure"].id in result.sections["procedures"]["memory_ids"]
    assert records["relevant"].id in result.sections["task"]["memory_ids"]
    # bedrock/session never count as "delivered"
    assert records["bedrock"].id not in result.delivered_ids


def test_orchestrator_session_iterative_deepening(tmp_path):
    client, records = seeded_client(tmp_path)
    client.offload_context(
        {"step": 3, "notes": "mid-release"},
        session_id="rel-42",
        owner="neo",
    )

    first = client.orchestrate_context(
        "prepare the staging deploy", session_id="rel-42",
        requester_agent_id="neo", max_tokens=2000,
    )
    second = client.orchestrate_context(
        "prepare the staging deploy", session_id="rel-42",
        requester_agent_id="neo", max_tokens=2000,
    )

    assert "Context snapshot" in first.text
    assert records["relevant"].id in first.sections["task"]["memory_ids"]
    # already delivered -> excluded on the second pass
    second_task_ids = second.sections.get("task", {}).get("memory_ids", [])
    assert records["relevant"].id not in second_task_ids
    # bedrock constants repeat every time by design
    assert records["bedrock"].id in second.sections["bedrock"]["memory_ids"]
    assert records["relevant"].id in client.store.delivered_ids("rel-42", owner="neo")


def test_orchestrator_respects_small_budgets(tmp_path):
    client, _ = seeded_client(tmp_path)
    for i in range(20):
        client.add(f"Deploy detail number {i} for the staging pipeline.", visibility=["global"])

    result = client.orchestrate_context(
        "staging deploy details", requester_agent_id="neo", max_tokens=300
    )

    assert result.used_tokens <= 300


def test_retention_rotates_session_snapshots(tmp_path):
    client = MemoryClient(home=tmp_path)
    for step in range(7):
        client.offload_context({"step": step}, session_id="long-run")

    result = client.run_retention()

    assert result["archived_snapshots"] == 2
    reasons = {item["archive_reason"] for item in client.list_archived()}
    assert reasons == {"snapshot_rotation"}
    # the newest snapshot survives and still reloads
    assert client.reload_context("long-run") == {"step": 6}


def test_web_api_orchestrate_with_session_dedup(tmp_path):
    app = create_app(home=tmp_path)
    web = TestClient(app)
    relevant = web.post(
        "/api/memories",
        json={"content": "Staging deploy checklist for port 8000.", "visibility": ["global"]},
    ).json()

    first = web.get(
        "/api/orchestrate",
        params={"task": "staging deploy", "session_id": "web-s1", "requester_agent_id": "neo"},
    )
    assert first.status_code == 200
    assert relevant["id"] in first.json()["delivered_ids"]

    second = web.get(
        "/api/orchestrate",
        params={"task": "staging deploy", "session_id": "web-s1", "requester_agent_id": "neo"},
    ).json()
    assert relevant["id"] not in second["delivered_ids"]


def test_task_type_emphasis_shifts_budgets(tmp_path):
    from agent_memory_os.orchestrator import budget_split_for, DEFAULT_BUDGET_SPLIT

    risky, risky_emphasis = budget_split_for("delete the staging database and rollback")
    howto, howto_emphasis = budget_split_for("how to configure the deploy pipeline")
    neutral, neutral_emphasis = budget_split_for("summarize recent activity")

    assert risky_emphasis[0] == "risk"
    assert risky["warnings"] > DEFAULT_BUDGET_SPLIT["warnings"]
    assert "howto" in howto_emphasis
    assert howto["procedures"] > DEFAULT_BUDGET_SPLIT["procedures"]
    assert neutral_emphasis == [] and neutral == DEFAULT_BUDGET_SPLIT
    for split in (risky, howto, neutral):
        assert abs(sum(split.values()) - 1.0) < 1e-9

    client, _ = seeded_client(tmp_path)
    result = client.orchestrate_context(
        "delete stale rows and restart the service", requester_agent_id="neo"
    )
    assert "risk" in result.emphasis


def test_snapshot_diff_reports_state_changes(tmp_path):
    client = MemoryClient(home=tmp_path)
    client.offload_context(
        {"phase": "build", "attempts": 1, "worker": "neo"}, session_id="diff-1"
    )
    client.offload_context(
        {"phase": "canary", "attempts": 2, "queue": ["a", "b"]}, session_id="diff-1"
    )

    diff = client.snapshot_diff("diff-1")

    assert diff["snapshots_compared"] == 2
    assert diff["added"] == {"queue": ["a", "b"]}
    assert diff["removed"] == {"worker": "neo"}
    assert diff["changed"]["phase"] == {"from": "build", "to": "canary"}
    assert diff["changed"]["attempts"] == {"from": 1, "to": 2}

    import pytest as _pytest
    with _pytest.raises(ValueError):
        client.snapshot_diff("no-such-session")
