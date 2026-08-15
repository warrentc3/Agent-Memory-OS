import json
import subprocess
import sys

from agent_memory_os.client import MemoryClient
from agent_memory_os.golden_recall import (
    evaluate_golden_queries,
    load_golden_query_cases,
)


def test_golden_recall_passes_expected_profile_scoped_results(tmp_path):
    """Lineage:
    main: introduced f1d603b4@pre-migration-registry.
    """
    client = MemoryClient(home=tmp_path / "memory-home")
    try:
        client.add(
            "Neo uses Mem0 and AgentMemoryOS for persistent memory with ACL hardening.",
            owner="neo",
            scope="profile",
            type="fact",
        )
        client.add(
            "Mizuki private voice-cache path must not be visible to Neo golden recall.",
            owner="mizuki",
            scope="profile",
            type="warning",
        )
        cases = load_golden_query_cases(_write_cases(tmp_path, [
            {
                "id": "neo-memory-core",
                "query": "persistent memory ACL",
                "owner": "neo",
                "scope": "profile",
                "expected": ["AgentMemoryOS", "ACL hardening"],
                "forbidden": ["Mizuki private voice-cache"],
            }
        ]))

        report = evaluate_golden_queries(client, cases)

        assert report["activation_gate"] == "GO"
        assert report["golden_recall_rate"] == 1.0
        assert report["forbidden_hit_count"] == 0
        assert report["results"][0]["passed"] is True
    finally:
        client.close()


def test_golden_recall_blocks_forbidden_matches(tmp_path):
    """Lineage:
    main: introduced f1d603b4@pre-migration-registry.
    """
    client = MemoryClient(home=tmp_path / "memory-home")
    try:
        client.add(
            "Neo result accidentally includes Mizuki private voice-cache path.",
            owner="neo",
            scope="profile",
            type="warning",
        )
        cases = [
            {
                "id": "forbidden-leak",
                "query": "voice-cache path",
                "owner": "neo",
                "scope": "profile",
                "expected": ["voice-cache path"],
                "forbidden": ["Mizuki private"],
            }
        ]

        report = evaluate_golden_queries(client, load_golden_query_cases(_write_cases(tmp_path, cases)))

        assert report["activation_gate"] == "NO_GO_GOLDEN_FORBIDDEN_MATCH"
        assert report["forbidden_hit_count"] == 1
        assert report["results"][0]["forbidden_hits"] == ["Mizuki private"]
    finally:
        client.close()


def test_cli_golden_recall_outputs_json_report(tmp_path):
    """Lineage:
    main: introduced f1d603b4@pre-migration-registry.
    """
    home = tmp_path / "memory-home"
    client = MemoryClient(home=home)
    try:
        client.add(
            "Bastet Protocol requires Evidence Pack before production cutover.",
            owner="neo",
            scope="profile",
            type="procedure",
        )
    finally:
        client.close()
    cases_path = _write_cases(tmp_path, [
        {
            "id": "bastet-gate",
            "query": "Evidence Pack production cutover",
            "owner": "neo",
            "scope": "profile",
            "expected": ["Bastet Protocol", "Evidence Pack"],
        }
    ])

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_memory_os.cli",
            "--home",
            str(home),
            "golden-recall",
            "--cases",
            str(cases_path),
            "--json",
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    report = json.loads(result.stdout)

    assert report["activation_gate"] == "GO"
    assert report["cases"] == 1
    assert report["passed"] == 1


def _write_cases(tmp_path, cases):
    path = tmp_path / "golden_cases.json"
    path.write_text(json.dumps({"cases": cases}, ensure_ascii=False), encoding="utf-8")
    return path
