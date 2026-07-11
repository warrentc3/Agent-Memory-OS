"""Native service installation for the Web UI: run at login/boot on all three OSes.

- macOS: launchd LaunchAgent (`~/Library/LaunchAgents/<label>.plist`)
- Linux: systemd user unit (`~/.config/systemd/user/<name>.service`)
- Windows: Task Scheduler logon task (`schtasks /SC ONLOGON`)

All variants run `<current python> -m agent_memory_os.web_app` so the service
uses exactly the environment it was installed from (venvs included). Nothing
here needs admin rights; units are per-user. On Linux, add
`loginctl enable-linger $USER` if the service must start at boot without a
login session.
"""

from __future__ import annotations

import plistlib
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .tokens import resolve_home

SERVICE_LABEL = "com.agent-memory-os.web"
SERVICE_NAME = "agent-memory-web"


@dataclass
class ServiceConfig:
    home: Path
    host: str = "127.0.0.1"
    port: int = 8000
    python: str = field(default_factory=lambda: sys.executable)

    @property
    def arguments(self) -> list[str]:
        return [
            self.python, "-m", "agent_memory_os.web_app",
            "--host", self.host, "--port", str(self.port),
            "--home", str(self.home),
        ]

    @property
    def log_path(self) -> Path:
        return self.home / "logs" / "web.log"


def render_launchd_plist(config: ServiceConfig) -> str:
    payload = {
        "Label": SERVICE_LABEL,
        "ProgramArguments": config.arguments,
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(config.log_path),
        "StandardErrorPath": str(config.log_path),
    }
    return plistlib.dumps(payload).decode()


def render_systemd_unit(config: ServiceConfig) -> str:
    exec_start = " ".join(config.arguments)
    return f"""[Unit]
Description=Agent Memory OS Web console
After=network.target

[Service]
ExecStart={exec_start}
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
"""


def build_schtasks_create(config: ServiceConfig) -> list[str]:
    pythonw = Path(config.python).with_name("pythonw.exe")
    launcher = str(pythonw) if pythonw.exists() else config.python
    command = " ".join(
        [f'"{launcher}"'] + [f'"{part}"' if " " in part else part for part in config.arguments[1:]]
    )
    return [
        "schtasks", "/Create", "/TN", SERVICE_NAME, "/TR", command,
        "/SC", "ONLOGON", "/F",
    ]


def _unit_path(platform: str) -> Path:
    if platform == "darwin":
        return Path("~/Library/LaunchAgents").expanduser() / f"{SERVICE_LABEL}.plist"
    return Path("~/.config/systemd/user").expanduser() / f"{SERVICE_NAME}.service"


def _run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True)


def install(config: ServiceConfig, *, platform: str = sys.platform, dry_run: bool = False) -> list[str]:
    """Install and start the login service; returns the actions performed."""
    actions: list[str] = []
    config.log_path.parent.mkdir(parents=True, exist_ok=True)
    if platform == "darwin":
        path = _unit_path(platform)
        actions.append(f"write {path}")
        commands = [
            ["launchctl", "bootout", f"gui/{_uid()}/{SERVICE_LABEL}"],  # replace quietly
            ["launchctl", "bootstrap", f"gui/{_uid()}", str(path)],
        ]
        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render_launchd_plist(config))
        for command in commands:
            actions.append(" ".join(command))
            if not dry_run:
                _run(command)
    elif platform.startswith("linux"):
        path = _unit_path(platform)
        actions.append(f"write {path}")
        commands = [
            ["systemctl", "--user", "daemon-reload"],
            ["systemctl", "--user", "enable", "--now", f"{SERVICE_NAME}.service"],
        ]
        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render_systemd_unit(config))
        for command in commands:
            actions.append(" ".join(command))
            if not dry_run:
                _run(command)
        actions.append("hint: loginctl enable-linger $USER  # start at boot without login")
    elif platform == "win32":
        create = build_schtasks_create(config)
        run_now = ["schtasks", "/Run", "/TN", SERVICE_NAME]
        for command in (create, run_now):
            actions.append(" ".join(command))
            if not dry_run:
                _run(command)
    else:
        raise RuntimeError(f"unsupported platform: {platform}")
    return actions


def uninstall(*, platform: str = sys.platform, dry_run: bool = False) -> list[str]:
    actions: list[str] = []
    if platform == "darwin":
        commands = [["launchctl", "bootout", f"gui/{_uid()}/{SERVICE_LABEL}"]]
        path = _unit_path(platform)
    elif platform.startswith("linux"):
        commands = [["systemctl", "--user", "disable", "--now", f"{SERVICE_NAME}.service"]]
        path = _unit_path(platform)
    elif platform == "win32":
        commands = [["schtasks", "/Delete", "/TN", SERVICE_NAME, "/F"]]
        path = None
    else:
        raise RuntimeError(f"unsupported platform: {platform}")
    for command in commands:
        actions.append(" ".join(command))
        if not dry_run:
            _run(command)
    if path is not None:
        actions.append(f"remove {path}")
        if not dry_run and path.exists():
            path.unlink()
    return actions


def control(action: str, *, platform: str = sys.platform) -> subprocess.CompletedProcess:
    """start / stop / restart / status for the installed service."""
    if platform == "darwin":
        commands = {
            "start": ["launchctl", "kickstart", f"gui/{_uid()}/{SERVICE_LABEL}"],
            "stop": ["launchctl", "bootout", f"gui/{_uid()}/{SERVICE_LABEL}"],
            "restart": ["launchctl", "kickstart", "-k", f"gui/{_uid()}/{SERVICE_LABEL}"],
            "status": ["launchctl", "print", f"gui/{_uid()}/{SERVICE_LABEL}"],
        }
    elif platform.startswith("linux"):
        commands = {
            "start": ["systemctl", "--user", "start", f"{SERVICE_NAME}.service"],
            "stop": ["systemctl", "--user", "stop", f"{SERVICE_NAME}.service"],
            "restart": ["systemctl", "--user", "restart", f"{SERVICE_NAME}.service"],
            "status": ["systemctl", "--user", "is-active", f"{SERVICE_NAME}.service"],
        }
    elif platform == "win32":
        commands = {
            "start": ["schtasks", "/Run", "/TN", SERVICE_NAME],
            "stop": ["schtasks", "/End", "/TN", SERVICE_NAME],
            "status": ["schtasks", "/Query", "/TN", SERVICE_NAME],
        }
        if action == "restart":
            _run(commands["stop"])
            return _run(commands["start"])
    else:
        raise RuntimeError(f"unsupported platform: {platform}")
    return _run(commands[action])


def make_config(home: str | Path | None, host: str, port: int) -> ServiceConfig:
    return ServiceConfig(home=resolve_home(home), host=host, port=port)


def _uid() -> int:
    import os

    # os.getuid does not exist on Windows; only reachable there in dry-run
    # previews of the darwin flow, where any stable placeholder is fine.
    return os.getuid() if hasattr(os, "getuid") else 0
