import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from agent_memory_os import MemoryClient
from agent_memory_os.tokens import load_token, token_path
from agent_memory_os.web_app import create_app


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "agent_memory_os.cli", *args],
        capture_output=True, text=True,
    )


def test_token_lifecycle(tmp_path):
    """Lineage:
    main: introduced d35750c0@pre-migration-registry; 23d674e1@db-schema-v4.
    """
    home = str(tmp_path)
    created = run_cli("--home", home, "token", "create")
    assert created.returncode == 0
    token = load_token(home)
    assert token and token.startswith("amos_")
    if sys.platform != "win32":  # Windows has no POSIX mode bits
        assert oct(token_path(home).stat().st_mode)[-3:] == "600"

    # create refuses to overwrite; rotate replaces
    assert run_cli("--home", home, "token", "create").returncode == 1
    assert run_cli("--home", home, "token", "show").stdout.strip() == token
    run_cli("--home", home, "token", "rotate")
    assert load_token(home) != token

    run_cli("--home", home, "token", "disable")
    assert load_token(home) is None
    assert run_cli("--home", home, "token", "show").returncode == 1


def test_web_app_auto_loads_token_file(tmp_path):
    """Lineage:
    main: introduced d35750c0@pre-migration-registry.
    """
    run_cli("--home", str(tmp_path), "token", "create")
    token = load_token(tmp_path)

    app = create_app(home=tmp_path)
    client = TestClient(app)

    assert client.get("/api/stats").status_code == 401
    assert client.get(
        "/api/stats", headers={"Authorization": f"Bearer {token}"}
    ).status_code == 200


def test_backup_and_restore_roundtrip(tmp_path):
    """Lineage:
    main: introduced d35750c0@pre-migration-registry.
    """
    home = tmp_path / "live"
    writer = MemoryClient(home=home)
    kept = writer.add("Survives the backup.", visibility=["global"])
    other = writer.add("Also survives.", visibility=["global"])
    writer.link(kept.id, other.id, weight=0.7)
    writer.close()

    backup_file = tmp_path / "backups" / "memories-backup.db"
    assert run_cli("--home", str(home), "backup", str(backup_file)).returncode == 0
    assert backup_file.exists()

    restored_home = tmp_path / "restored"
    assert run_cli("--home", str(restored_home), "restore", str(backup_file)).returncode == 0
    reader = MemoryClient(home=restored_home)
    assert reader.get(kept.id).content == "Survives the backup."
    assert reader.stats() == {"total": 2, "by_scope": {"user": 2}, "by_type": {"note": 2},
                              "links": 1, "cache_items": 0}
    reader.close()

    # restore refuses to clobber without --force
    assert run_cli("--home", str(restored_home), "restore", str(backup_file)).returncode == 1
    assert run_cli("--home", str(restored_home), "restore", str(backup_file), "--force").returncode == 0


def test_doctor_reports_status(tmp_path):
    """Lineage:
    main: introduced d35750c0@pre-migration-registry.
    """
    result = run_cli("--home", str(tmp_path), "doctor")
    assert "SQLite FTS5" in result.stdout
    assert "semantic" in result.stdout
    assert "Web UI token" in result.stdout
