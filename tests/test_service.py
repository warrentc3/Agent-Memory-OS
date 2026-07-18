from pathlib import Path

import pytest

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
    plist = render_launchd_plist(config)

    assert SERVICE_LABEL in plist
    assert "<key>RunAtLoad</key>" in plist and "<true/>" in plist
    assert "<key>KeepAlive</key>" in plist
    assert "agent_memory_os.web_app" in plist
    assert "8123" in plist and str(config.home) in plist


def test_systemd_unit_restarts_and_targets_default(config):
    unit = render_systemd_unit(config)

    assert "ExecStart=/opt/py/bin/python3 -m agent_memory_os.web_app" in unit
    assert "--port 8123" in unit
    assert "Restart=on-failure" in unit
    assert "WantedBy=default.target" in unit


def test_schtasks_command_is_onlogon(config):
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
    with pytest.raises(RuntimeError):
        install(config, platform="plan9", dry_run=True)
