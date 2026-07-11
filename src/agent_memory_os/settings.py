"""Per-instance settings: `<home>/instance.toml`.

When several Agent Memory OS instances run on one machine — each with its own
`--home` — this file gives each a stable identity and a fixed (or auto-chosen)
Web UI port:

    # <home>/instance.toml
    [instance]
    node_name = "mizuki-laptop"   # shown to peers during memory sync
    host = "127.0.0.1"
    port = 8000                   # taken port? the launcher advances to a free one

Everything has a sensible default, so the file is optional. `node_name`
defaults to a host+home derived label so two instances on the same machine
don't collide.
"""

from __future__ import annotations

import socket
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .tokens import resolve_home

SETTINGS_FILENAME = "instance.toml"
DEFAULT_PORT = 8000
DEFAULT_HOST = "127.0.0.1"


def settings_path(home: str | Path | None) -> Path:
    return resolve_home(home) / SETTINGS_FILENAME


def default_node_name(home: str | Path | None) -> str:
    """A stable, machine+home-derived name that disambiguates co-located instances."""
    host = socket.gethostname().split(".")[0] or "amos"
    base = resolve_home(home).name.lstrip(".") or "amos"
    return f"{host}-{base}"


@dataclass(slots=True)
class InstanceSettings:
    node_name: str
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT


def load_instance_settings(home: str | Path | None) -> InstanceSettings:
    path = settings_path(home)
    data: dict = {}
    if path.exists():
        try:
            parsed = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ValueError(f"invalid {path}: {exc}") from exc
        section = parsed.get("instance", parsed)
        if not isinstance(section, dict):
            raise ValueError(f"invalid {path}: [instance] table expected")
        data = section
    node_name = str(data.get("node_name") or "").strip() or default_node_name(home)
    host = str(data.get("host") or DEFAULT_HOST).strip() or DEFAULT_HOST
    port = data.get("port", DEFAULT_PORT)
    try:
        port = int(port)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {path}: port must be an integer") from exc
    if not (0 < port < 65536):
        raise ValueError(f"invalid {path}: port must be 1-65535")
    return InstanceSettings(node_name=node_name, host=host, port=port)


def save_instance_settings(home: str | Path | None, settings: InstanceSettings) -> Path:
    path = settings_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        "# Agent Memory OS instance settings\n"
        "[instance]\n"
        f'node_name = "{settings.node_name}"\n'
        f'host = "{settings.host}"\n'
        f"port = {settings.port}\n"
    )
    path.write_text(body, encoding="utf-8")
    return path


def update_instance_settings(
    home: str | Path | None,
    *,
    node_name: str | None = None,
    host: str | None = None,
    port: int | None = None,
) -> InstanceSettings:
    current = load_instance_settings(home)
    updated = InstanceSettings(
        node_name=(node_name.strip() if node_name and node_name.strip() else current.node_name),
        host=host or current.host,
        port=port if port is not None else current.port,
    )
    if updated.port <= 0 or updated.port >= 65536:
        raise ValueError("port must be 1-65535")
    save_instance_settings(home, updated)
    return updated


def port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def find_available_port(host: str, preferred: int, *, limit: int = 64) -> int:
    """Return `preferred` if free, otherwise the next free port above it.

    Lets several instances on one machine start without hand-assigning ports.
    """
    for candidate in range(preferred, min(preferred + limit, 65536)):
        if port_is_free(host, candidate):
            return candidate
    raise RuntimeError(
        f"no free port found in {preferred}-{preferred + limit - 1} on {host}"
    )
