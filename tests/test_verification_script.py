from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_acl_identities.py"
DOWNGRADE_SCRIPT = REPO_ROOT / "scripts" / "verify_downgrade_compatibility.py"


def run_verifier(tmp_path: Path, *args: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--home", str(tmp_path), *args],
        cwd=REPO_ROOT,
        env={"PYTHONPATH": str(REPO_ROOT / "src")},
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(proc.stdout)


def test_verification_script_switches_identities_without_leaking_private_memory(tmp_path):
    """Lineage:
    main: introduced c8b5cc42@pre-migration-registry.
    """
    report = run_verifier(tmp_path)

    by_identity = {item["identity"]: item for item in report["pulls"]}

    mizuki = by_identity["mizuki"]
    assert mizuki["requester_agent_id"] == "mizuki"
    assert "private_emotional_preference" in mizuki["search_visible_labels"]
    assert "private_emotional_preference" in mizuki["context_pack_visible_labels"]

    neo = by_identity["neo"]
    assert "team_memory" in neo["search_visible_labels"]
    assert "global_memory" in neo["search_visible_labels"]
    assert "private_emotional_preference" not in neo["search_visible_labels"]
    assert "private_emotional_preference" not in neo["context_pack_visible_labels"]

    guest = by_identity["guest"]
    assert guest["search_visible_labels"] == ["global_memory"]
    assert guest["context_pack_visible_labels"] == ["global_memory"]

    assert report["leak_check"]["passed"] is True


def test_verification_script_can_focus_one_identity(tmp_path):
    """Lineage:
    main: introduced c8b5cc42@pre-migration-registry.
    """
    report = run_verifier(tmp_path, "--identity", "neo")

    assert [item["identity"] for item in report["pulls"]] == ["neo"]
    assert report["pulls"][0]["search_visible_labels"] == ["team_memory", "global_memory"]


def test_downgrade_compatibility_script_clears_local_fixture_matrix(tmp_path):
    """Lineage:
    main: introduced b9c26be5@pre-migration-registry.
    """
    proc = subprocess.run(
        [sys.executable, str(DOWNGRADE_SCRIPT), "--home", str(tmp_path), "--matrix", "all"],
        cwd=REPO_ROOT,
        env={"PYTHONPATH": str(REPO_ROOT / "src")},
        text=True,
        capture_output=True,
        check=True,
    )
    report = json.loads(proc.stdout)

    assert report["status"] == "PASS"
    assert report["summary"] == {
        "acl_matrix_passed": True,
        "index_rebuild_passed": True,
        "memory_ids_preserved": True,
        "rollback_restore_passed": True,
        "unknown_metadata_safe": True,
    }
    assert report["matrix"]["old_schema_to_current_runtime"]["row_count_before"] == 4
    assert report["matrix"]["old_schema_to_current_runtime"]["row_count_after"] == 4
    assert report["matrix"]["current_database_to_stable_field_exporter"]["private_leaked"] is False
