"""Declarative fleet configuration: `<home>/agents.toml`.

Register the whole multi-agent, multi-project fleet as infrastructure-as-code
instead of clicking through the console:

    # ~/.agent-memory/agents.toml
    [agents.cc-main]
    display_name = "Claude Code"
    kind = "claude-code"                 # claude-code|codex|openclaw|hermes|agy|custom
    teams = ["apollo", "shared-infra"]   # multiple teams = multiple projects

    [agents.hermes-neo]
    kind = "hermes"
    teams = ["apollo", "ops"]

    [agents.hermes-mizuki]
    kind = "hermes"
    teams = ["apollo"]

Entries are (re)applied every time a MemoryClient opens the home, so the file
is authoritative for the agents it lists: edit + restart = fleet updated.
Agents registered manually (console/API) and not listed here are untouched.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from .tokens import resolve_home

CONFIG_FILENAME = "agents.toml"


def config_path(home: str | Path | None) -> Path:
    return resolve_home(home) / CONFIG_FILENAME


def load_agents_config(home: str | Path | None) -> list[dict]:
    path = config_path(home)
    if not path.exists():
        return []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"invalid {path}: {exc}") from exc
    agents = data.get("agents", {})
    if not isinstance(agents, dict):
        raise ValueError(f"invalid {path}: [agents.<id>] tables expected")
    entries = []
    for agent_id, fields in agents.items():
        if not isinstance(fields, dict):
            raise ValueError(f"invalid {path}: [agents.{agent_id}] must be a table")
        teams = fields.get("teams", [])
        if isinstance(teams, str) or not isinstance(teams, (list, tuple)):
            raise ValueError(
                f"invalid {path}: [agents.{agent_id}] teams must be a list, "
                f'e.g. teams = ["apollo", "ops"]'
            )
        entries.append(
            {
                "id": agent_id,
                "display_name": str(fields.get("display_name", "")),
                "kind": str(fields.get("kind", "custom")),
                "teams": [str(team) for team in teams],
                "notes": str(fields.get("notes", "")),
                # Which fields the file actually set — apply overrides only
                # these, so a partial entry never wipes console-set metadata.
                "_specified": {
                    name for name in ("display_name", "kind", "teams", "notes")
                    if name in fields
                },
            }
        )
    return entries


def apply_agents_config(store, home: str | Path | None) -> list[str]:
    """Upsert every configured agent; returns the applied agent ids.

    Every entry is validated up front, so a single malformed entry aborts the
    whole apply before any write — the file never lands the fleet half-registered.
    """
    entries = load_agents_config(home)
    valid_kinds = getattr(store, "AGENT_KINDS", None)
    for entry in entries:
        if not entry["id"].strip():
            raise ValueError(f"{config_path(home)}: an [agents.<id>] table has an empty id")
        if valid_kinds is not None and entry["kind"] not in valid_kinds:
            raise ValueError(
                f"{config_path(home)}: agent {entry['id']!r}: "
                f"kind must be one of {sorted(valid_kinds)}"
            )
    applied: list[str] = []
    for entry in entries:
        # Fields the file didn't set keep the existing (console-set) value
        # instead of being reset to a default on every open.
        existing = store.get_agent(entry["id"]) or {}
        specified = entry["_specified"]

        def field(name, default):
            return entry[name] if name in specified else existing.get(name, default)

        store.register_agent(
            entry["id"],
            display_name=field("display_name", ""),
            kind=field("kind", "custom"),
            teams=field("teams", []),
            notes=field("notes", ""),
        )
        applied.append(entry["id"])
    return applied
