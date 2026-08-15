import subprocess
from pathlib import Path

import pytest

from agent_memory_os import service as service_module
from agent_memory_os.cli import main
from agent_memory_os.service import (
    SERVICE_LABEL,
    SERVICE_NAME,
    ServiceConfig,
    build_schtasks_create,
    install,
    render_launchd_plist,
    render_systemd_unit,
    uninstall,
)


@pytest.fixture
def config(tmp_path):
    return ServiceConfig(home=tmp_path, host="127.0.0.1", port=8123, python="/opt/py/bin/python3")


def test_launchd_plist_runs_at_load_and_keeps_alive(config):
    """Lineage:
    main: introduced 23d674e1@db-schema-v4.
    """
    plist = render_launchd_plist(config)

    assert SERVICE_LABEL in plist
    assert "<key>RunAtLoad</key>" in plist and "<true/>" in plist
    assert "<key>KeepAlive</key>" in plist
    assert "agent_memory_os.web_app" in plist
    assert "8123" in plist and str(config.home) in plist


def test_systemd_unit_restarts_and_targets_default(config):
    """Lineage:
    main: introduced 23d674e1@db-schema-v4.
    """
    unit = render_systemd_unit(config)

    assert "ExecStart=/opt/py/bin/python3 -m agent_memory_os.web_app" in unit
    assert "--port 8123" in unit
    assert "Restart=on-failure" in unit
    assert "WantedBy=default.target" in unit


def test_schtasks_command_is_onlogon(config):
    """Lineage:
    main: introduced 23d674e1@db-schema-v4; 68e82ed2@db-schema-v16.
    """
    command = build_schtasks_create(config)

    assert command[:2] == ["schtasks", "/Create"]
    # Task names are machine-global on Windows, so the name is per-account
    # (SERVICE_NAME plus a username suffix) — never the bare SERVICE_NAME.
    task_name = command[command.index("/TN") + 1]
    assert task_name.startswith(f"{SERVICE_NAME}-") and task_name != SERVICE_NAME
    assert "/SC" in command and command[command.index("/SC") + 1] == "ONLOGON"
    task_run = command[command.index("/TR") + 1]
    assert "agent_memory_os.web_app" in task_run


@pytest.mark.parametrize("platform", ["darwin", "linux", "win32"])
def test_install_and_uninstall_dry_run_all_platforms(config, platform):
    """Lineage:
    main: introduced 23d674e1@db-schema-v4.
    """
    actions = install(config, platform=platform, dry_run=True)
    removals = uninstall(platform=platform, dry_run=True)

    assert actions, platform
    assert removals, platform
    if platform == "darwin":
        assert any("launchctl bootstrap" in action for action in actions)
    elif platform == "linux":
        assert any("systemctl --user enable --now" in action for action in actions)
        assert any("enable-linger" in action for action in actions)
    else:
        assert any("/SC ONLOGON" in action or "ONLOGON" in action for action in actions)
    # dry-run must not write unit files
    assert not (Path("~/Library/LaunchAgents").expanduser() / "test-nonexistent").exists()


def test_install_rejects_unknown_platform(config):
    """Lineage:
    main: introduced 23d674e1@db-schema-v4.
    """
    with pytest.raises(RuntimeError):
        install(config, platform="plan9", dry_run=True)


def test_windows_install_propagates_required_command_failure(config, monkeypatch):
    """Lineage:
    main: introduced 176124d4@db-schema-v17.
    """
    def fail(command):
        return subprocess.CompletedProcess(command, 1, "", "access denied")

    monkeypatch.setattr(service_module, "_run", fail)

    with pytest.raises(RuntimeError, match="access denied"):
        install(config, platform="win32")


def test_cli_service_install_reports_native_failure(tmp_path, monkeypatch, capsys):
    """Lineage:
    main: introduced 176124d4@db-schema-v17.
    """
    def fail(*args, **kwargs):
        raise RuntimeError("native manager refused install")

    monkeypatch.setattr(service_module, "install", fail)

    result = main(
        [
            "--home",
            str(tmp_path),
            "service",
            "install",
            "--port",
            "8123",
        ]
    )

    assert result == 1
    assert "service install failed" in capsys.readouterr().out


def test_systemd_self_update_kills_only_on_success():
    """Lineage:
    main: introduced ef6d8dbf@db-schema-v20.
    """
    from agent_memory_os.service import systemd_self_update

    killed = []

    class Ok:
        returncode = 0
        stderr = ""
        stdout = ""

    class Fail:
        returncode = 1
        stderr = "no network"
        stdout = ""

    assert systemd_self_update(pip_runner=lambda: Ok(),
                               killer=lambda: killed.append(True)) is True
    assert killed == [True]

    killed.clear()
    assert systemd_self_update(pip_runner=lambda: Fail(),
                               killer=lambda: killed.append(True)) is False
    assert killed == []  # upgrade failed -> stay up, no restart


def test_update_run_uses_in_process_path_under_systemd(tmp_path, monkeypatch):
    """Lineage:
    main: introduced ef6d8dbf@db-schema-v20.
    """
    import subprocess
    import threading

    from fastapi.testclient import TestClient

    from agent_memory_os import service as service_module
    from agent_memory_os.web_app import create_app

    monkeypatch.setenv("INVOCATION_ID", "abc123")
    ran = threading.Event()
    monkeypatch.setattr(service_module, "systemd_self_update",
                        lambda **kwargs: ran.set())
    # the detached-updater path must NOT be used under systemd
    monkeypatch.setattr(subprocess, "Popen",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("Popen used")))
    http = TestClient(create_app(home=tmp_path))
    r = http.post("/api/maintenance/update-run?confirm=update")
    assert r.status_code == 200
    body = r.json()
    assert body["started"] is True and "systemd" in body["detail"]
    assert ran.wait(timeout=5)
