"""Hermes Agent memory-provider plugin (NousResearch hermes-agent >= 0.18).

Installing `agent-memory-os` in the Hermes environment makes this plugin
discoverable through the `hermes_agent.plugins` entry point. Enable it and
select the provider:

    pip install agent-memory-os          # inside the Hermes env
    hermes plugins                       # enable "agent-memory-os"
    # in ~/.hermes/config.yaml:
    #   memory:
    #     provider: agent-memory-os

No API key, no cloud, no LLM: recall and storage run against the local
SQLite store (default `~/.agent-memory`), so `is_available()` is true the
moment the package is installed. Unlike single-user cloud providers, every
write carries AgentMemoryOS's visibility ACL — the Hermes profile maps to an
agent identity, so several profiles (and other MCP agents like Claude Code or
Codex) can share one store with private/team/project boundaries intact.

Configuration (non-secret, `$HERMES_HOME/agent-memory-os.json`, written by
`hermes memory setup`; env vars override nothing — they are the fallback):
  home           — AgentMemoryOS data home (default: AGENT_MEMORY_HOME or
                   ~/.agent-memory). Shared with the MCP server and CLI.
  agent_id       — identity for reads/writes (default: AGENT_MEMORY_AGENT_ID,
                   else "hermes-<profile>" derived at initialize()).
  share_default  — default ACL for `amos_add` when the model omits `share`:
                   'private' (default), 'team', 'project', or 'global'.
  mirror_builtin — mirror Hermes built-in MEMORY.md/USER.md writes into the
                   store (default: true; idempotent per content hash).
  capture_delegations — store subagent task/result pairs as episodic notes
                   (default: true; private visibility, low importance).
  prefetch_limit / prefetch_max_tokens — recall budget per turn (8 / 900).

Every hook is wrapped so a store failure degrades to "no memory this turn"
instead of breaking the agent loop (Hermes also isolates hook exceptions).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:  # Only present inside a Hermes Agent runtime.
    from agent.memory_provider import MemoryProvider as _ProviderBase
    _HERMES_RUNTIME = True
except ImportError:  # pragma: no cover - exercised via stub in tests
    _ProviderBase = object  # type: ignore[assignment,misc]
    _HERMES_RUNTIME = False

PROVIDER_NAME = "agent-memory-os"
CONFIG_FILENAME = "agent-memory-os.json"
MIRROR_SYSTEM = "hermes-builtin-memory-mirror"
DELEGATION_SYSTEM = "hermes-delegation-capture"

_VALID_SHARE_DEFAULTS = ("private", "team", "project", "global")


def _load_config(hermes_home: str | None = None) -> Dict[str, Any]:
    """Env-var defaults overridden by `$HERMES_HOME/agent-memory-os.json`."""
    config: Dict[str, Any] = {
        "home": os.environ.get("AGENT_MEMORY_HOME", ""),
        "agent_id": os.environ.get("AGENT_MEMORY_AGENT_ID", ""),
        "share_default": "private",
        "mirror_builtin": True,
        "capture_delegations": True,
        "prefetch_limit": 8,
        "prefetch_max_tokens": 900,
    }
    home = hermes_home
    if home is None:
        try:  # pragma: no cover - hermes runtime only
            from hermes_constants import get_hermes_home
            home = str(get_hermes_home())
        except Exception:
            home = os.environ.get("HERMES_HOME", "")
    if home:
        path = Path(home) / CONFIG_FILENAME
        if path.exists():
            try:
                file_cfg = json.loads(path.read_text(encoding="utf-8"))
                config.update({k: v for k, v in file_cfg.items()
                               if v is not None and v != ""})
            except Exception:
                logger.warning("Unreadable %s; using defaults", path)
    if config.get("share_default") not in _VALID_SHARE_DEFAULTS:
        config["share_default"] = "private"
    return config


def _mirror_id(target: str, content: str) -> str:
    """Stable id for a mirrored built-in write, so replays are idempotent."""
    digest = hashlib.sha256(f"{target}\n{content}".encode("utf-8")).hexdigest()
    return f"hermes-mirror-{digest[:24]}"


class AgentMemoryOSProvider(_ProviderBase):  # type: ignore[misc]
    """Local-first, ACL-aware Hermes memory provider backed by AgentMemoryOS."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config or _load_config()
        self._client: Any = None
        self._lock = threading.Lock()
        self._agent_id: str = self._config.get("agent_id") or ""
        self._session_id: str = ""
        self._active = True  # False for subagent/cron contexts (read-only)
        self._mirrored: set[str] = set()

    # -- identity -----------------------------------------------------------

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    # -- availability & lifecycle -------------------------------------------

    def is_available(self) -> bool:
        """Local-first: no credentials, no network — installed means ready."""
        return True

    def initialize(self, session_id: str, **kwargs: Any) -> None:
        from .client import MemoryClient

        self._session_id = session_id
        hermes_home = kwargs.get("hermes_home") or ""
        # Re-read config now that the true HERMES_HOME is known (profile-scoped).
        self._config = _load_config(hermes_home or None)

        if not self._agent_id:
            self._agent_id = self._config.get("agent_id") or ""
        if not self._agent_id:
            identity = kwargs.get("agent_identity") or "default"
            self._agent_id = f"hermes-{identity}"

        # Cron/subagent/flush contexts observe but never write — a cron
        # system prompt must not pollute the durable store.
        self._active = (kwargs.get("agent_context") or "primary") == "primary"

        home = self._config.get("home") or None
        self._client = MemoryClient(home=home)
        try:
            self._client.store.touch_agent(self._agent_id)
        except Exception:  # noqa: BLE001 - registry is best-effort
            pass
        logger.info(
            "AgentMemoryOS provider ready (agent=%s home=%s active=%s)",
            self._agent_id, home or "~/.agent-memory", self._active,
        )

    def shutdown(self) -> None:
        with self._lock:
            if self._client is not None:
                try:
                    self._client.close()
                except Exception:  # noqa: BLE001
                    pass
                self._client = None

    def on_session_switch(self, new_session_id: str, **kwargs: Any) -> None:
        self._session_id = new_session_id

    # -- prompt & recall ------------------------------------------------------

    def system_prompt_block(self) -> str:
        return (
            "Persistent memory is provided by AgentMemoryOS (local SQLite, "
            "ACL-scoped). Relevant memories are recalled into your context "
            "automatically each turn. Use amos_add to save durable facts, "
            "preferences, decisions, or lessons — set share='team'/'project' "
            "for knowledge teammates should see; amos_search to look up more."
        )

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        """Recall a context pack for the turn. Local SQLite — fast enough sync."""
        if self._client is None or not (query or "").strip():
            return ""
        try:
            pack = self._client.context_pack(
                query,
                requester_agent_id=self._agent_id,
                limit=int(self._config.get("prefetch_limit", 8)),
                max_tokens=int(self._config.get("prefetch_max_tokens", 900)),
            )
        except Exception as exc:  # noqa: BLE001 - degrade to no recall
            logger.warning("AgentMemoryOS prefetch failed: %s", exc)
            return ""
        if not pack or not pack.strip():
            return ""
        return (
            "Recalled from AgentMemoryOS (ACL-filtered for you):\n" + pack.strip()
        )

    # -- tools ----------------------------------------------------------------

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "amos_search",
                "description": (
                    "Search persistent AgentMemoryOS memories by keyword and "
                    "association. Results are ACL-filtered to what this agent "
                    "may see (its own, team/project-shared, global). Use before "
                    "answering anything that may depend on stored preferences, "
                    "decisions, procedures, or past lessons."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural-language search query.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max results (default 8).",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "amos_add",
                "description": (
                    "Save a durable memory that survives across sessions: a "
                    "user preference, project fact, decision, procedure, or "
                    "lesson. Not for transient chat. `share` sets who may read "
                    "it: 'private' (default), 'team'/'team:<id>', "
                    "'project'/'project:<id>', 'agent:<id>', or 'global'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": (
                                "The fact, as a self-contained sentence that "
                                "makes sense in a future session."
                            ),
                        },
                        "type": {
                            "type": "string",
                            "description": (
                                "'preference', 'fact', 'procedure', "
                                "'environment', 'decision', 'warning', or 'note'."
                            ),
                        },
                        "share": {
                            "type": "string",
                            "description": (
                                "ACL grant; omit for the configured default "
                                "(usually private)."
                            ),
                        },
                    },
                    "required": ["content"],
                },
            },
            {
                "name": "amos_share",
                "description": (
                    "Change who may read an existing AgentMemoryOS memory "
                    "(owner-only). Use to promote a private note to "
                    "'team'/'project'/'global', or restrict it back to "
                    "'private'. The change propagates over federation sync."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "memory_id": {
                            "type": "string",
                            "description": "Id of the memory to re-share.",
                        },
                        "share": {
                            "type": "string",
                            "description": (
                                "'private', 'team[:<id>]', 'project[:<id>]', "
                                "'agent:<id>', or 'global'."
                            ),
                        },
                    },
                    "required": ["memory_id", "share"],
                },
            },
        ]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs: Any) -> str:
        if self._client is None:
            return json.dumps({"error": "AgentMemoryOS provider not initialized"})
        try:
            if tool_name == "amos_search":
                return self._tool_search(args)
            if tool_name == "amos_add":
                return self._tool_add(args)
            if tool_name == "amos_share":
                return self._tool_share(args)
        except ValueError as exc:  # share-resolution errors are user-facing
            return json.dumps({"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            logger.warning("AgentMemoryOS tool %s failed: %s", tool_name, exc)
            return json.dumps({"error": f"{tool_name} failed: {exc}"})
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    def _tool_search(self, args: Dict[str, Any]) -> str:
        query = (args.get("query") or "").strip()
        if not query:
            return json.dumps({"error": "Missing required parameter: query"})
        limit = int(args.get("limit") or 8)
        results = self._client.search(
            query, requester_agent_id=self._agent_id, limit=limit,
        )
        payload = [
            {
                "id": r.record.id,
                "content": r.record.content,
                "type": r.record.type,
                "score": round(r.score, 4),
                "visibility": list(r.record.visibility or []),
            }
            for r in results
        ]
        return json.dumps({"results": payload, "count": len(payload)})

    def _resolve_share(self, share: str | None) -> List[str]:
        from .mcp_server import _share_to_visibility

        store = self._client.store
        return _share_to_visibility(
            share,
            teams=store.teams_for(self._agent_id) if self._agent_id else [],
            projects=store.projects_for(self._agent_id) if self._agent_id else [],
        )

    def _tool_add(self, args: Dict[str, Any]) -> str:
        content = (args.get("content") or "").strip()
        if not content:
            return json.dumps({"error": "Missing required parameter: content"})
        if not self._active:
            return json.dumps({"error": "read-only context (cron/subagent); not stored"})
        share = args.get("share") or self._config.get("share_default", "private")
        visibility = self._resolve_share(share)
        record = self._client.add(
            content,
            owner=self._agent_id,
            type=(args.get("type") or "note"),
            visibility=visibility,
            source={"system": "hermes-plugin", "session_id": self._session_id},
            auto_link=True,
        )
        return json.dumps({
            "id": record.id,
            "content": record.content,
            "visibility": list(record.visibility or []),
        })

    def _tool_share(self, args: Dict[str, Any]) -> str:
        memory_id = (args.get("memory_id") or "").strip()
        share = args.get("share")
        if not memory_id:
            return json.dumps({"error": "Missing required parameter: memory_id"})
        if not self._active:
            return json.dumps({"error": "read-only context (cron/subagent); not changed"})
        existing = self._client.get(memory_id)
        if existing is None:
            return json.dumps({"error": f"Memory not found: {memory_id}"})
        if existing.owner != self._agent_id:
            return json.dumps({"error": "only the owner may change sharing"})
        visibility = self._resolve_share(share)
        record = self._client.update(memory_id, visibility=visibility)
        return json.dumps({
            "id": record.id,
            "visibility": list(record.visibility or []),
        })

    # -- passive capture ------------------------------------------------------

    def on_memory_write(
        self,
        action: str,
        target: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Mirror Hermes built-in MEMORY.md/USER.md writes into the store.

        Idempotent per (target, content) hash, so nudge-driven rewrites of the
        same entry do not duplicate. Only 'add'/'replace' are mirrored; removal
        stays manual — the store has its own decay/consolidation lifecycle.
        """
        if self._client is None or not self._active:
            return
        if not self._config.get("mirror_builtin", True):
            return
        if action not in ("add", "replace") or not (content or "").strip():
            return
        memory_id = _mirror_id(target, content.strip())
        if memory_id in self._mirrored:
            return
        try:
            if self._client.get(memory_id) is None:  # idempotent across restarts
                self._client.add(
                    content.strip(),
                    id=memory_id,
                    owner=self._agent_id,
                    type="preference" if target == "user" else "note",
                    visibility=[],
                    source={"system": MIRROR_SYSTEM, "target": target,
                            "action": action},
                )
            self._mirrored.add(memory_id)
        except Exception as exc:  # noqa: BLE001
            logger.debug("builtin-memory mirror skipped: %s", exc)

    def on_delegation(self, task: str, result: str, *,
                      child_session_id: str = "", **kwargs: Any) -> None:
        """Store what was delegated and what came back, as an episodic note."""
        if self._client is None or not self._active:
            return
        if not self._config.get("capture_delegations", True):
            return
        task = (task or "").strip()
        result = (result or "").strip()
        if not task or not result:
            return
        try:
            self._client.add(
                f"Delegated task: {task[:400]}\nOutcome: {result[:1200]}",
                owner=self._agent_id,
                type="note",
                visibility=[],
                importance=0.3,
                source={"system": DELEGATION_SYSTEM,
                        "child_session_id": child_session_id},
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("delegation capture skipped: %s", exc)

    # -- setup surface --------------------------------------------------------

    def get_config_schema(self) -> List[Dict[str, Any]]:
        return [
            {
                "key": "home",
                "description": (
                    "AgentMemoryOS data home (blank = ~/.agent-memory). Point "
                    "several profiles or MCP agents at the same home to share "
                    "team memory."
                ),
                "required": False,
                "default": "",
            },
            {
                "key": "agent_id",
                "description": (
                    "Identity for this profile's reads/writes (blank = "
                    "hermes-<profile>). Owns its private memories in the ACL."
                ),
                "required": False,
                "default": "",
            },
            {
                "key": "share_default",
                "description": "Default ACL when amos_add omits share.",
                "required": False,
                "default": "private",
                "choices": list(_VALID_SHARE_DEFAULTS),
            },
            {
                "key": "mirror_builtin",
                "description": "Mirror built-in MEMORY.md/USER.md writes into the store.",
                "required": False,
                "default": True,
            },
            {
                "key": "capture_delegations",
                "description": "Store subagent task/result pairs as episodic notes.",
                "required": False,
                "default": True,
            },
        ]

    def save_config(self, values: Dict[str, Any], hermes_home: str) -> None:
        path = Path(hermes_home) / CONFIG_FILENAME
        current: Dict[str, Any] = {}
        if path.exists():
            try:
                current = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                current = {}
        current.update({k: v for k, v in values.items() if v is not None})
        path.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")

    def backup_paths(self) -> List[str]:
        """The store lives outside HERMES_HOME — declare it for `hermes backup`."""
        home = _load_config().get("home") or os.path.expanduser("~/.agent-memory")
        return [str(Path(home).expanduser())]


def register(ctx: Any) -> None:
    """Hermes plugin entry point (`hermes_agent.plugins`)."""
    if not _HERMES_RUNTIME:  # pragma: no cover - defensive outside Hermes
        logger.warning(
            "agent-memory-os Hermes plugin loaded outside a Hermes runtime; "
            "provider not registered",
        )
        return
    ctx.register_memory_provider(AgentMemoryOSProvider())


# ---------------------------------------------------------------------------
# `agent-memory hermes install` — materialize the provider for `hermes memory`
# ---------------------------------------------------------------------------
# Hermes's `hermes memory setup|status` picker discovers providers ONLY from
# directories (bundled plugins/memory/ and $HERMES_HOME/plugins/), never from
# pip entry points. So a plain pip install is invisible to `hermes memory`
# until this shim directory exists. The shim just re-exports register() from
# the installed package; the implementation stays here and upgrades with pip.

# NOTE: the __init__.py body must literally contain the strings
# "register_memory_provider"/"MemoryProvider" — Hermes's
# _is_memory_provider_dir() heuristic text-scans for them.
_SHIM_INIT = '''"""AgentMemoryOS memory provider for Hermes Agent (shim).

Thin loader: the real MemoryProvider implementation lives in the installed
`agent-memory-os` pip package (agent_memory_os.hermes_plugin) and upgrades
with it. Installed by `agent-memory hermes install`; safe to delete.
"""


def register(ctx):
    from agent_memory_os.hermes_plugin import AgentMemoryOSProvider

    ctx.register_memory_provider(AgentMemoryOSProvider())
'''

_SHIM_YAML = """name: agent-memory-os
version: "{version}"
description: "AgentMemoryOS — local-first team memory: ACL-scoped recall (private/team/project), no API key, no LLM, one SQLite file; shared with MCP agents like Claude Code/Codex."
pip_dependencies:
  - agent-memory-os
"""


def _default_hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or "~/.hermes").expanduser()


def shim_dir(hermes_home: str | os.PathLike[str] | None = None) -> Path:
    base = Path(hermes_home).expanduser() if hermes_home else _default_hermes_home()
    return base / "plugins" / PROVIDER_NAME


def install_shim(hermes_home: str | os.PathLike[str] | None = None) -> Dict[str, Any]:
    """Write the provider shim into `$HERMES_HOME/plugins/agent-memory-os/`.

    Idempotent: re-running refreshes the files (e.g. after a pip upgrade
    bumps the version stamped into plugin.yaml).
    """
    try:
        from importlib.metadata import version as _pkg_version
        version = _pkg_version("agent-memory-os")
    except Exception:  # noqa: BLE001 - editable/dev installs
        version = "0.0.0+dev"

    target = shim_dir(hermes_home)
    target.mkdir(parents=True, exist_ok=True)
    (target / "__init__.py").write_text(_SHIM_INIT, encoding="utf-8")
    (target / "plugin.yaml").write_text(
        _SHIM_YAML.format(version=version), encoding="utf-8",
    )
    return {
        "installed": str(target),
        "version": version,
        "next_steps": [
            "hermes memory setup agent-memory-os   # or: hermes memory setup",
            "hermes memory status",
        ],
    }


def uninstall_shim(hermes_home: str | os.PathLike[str] | None = None) -> bool:
    """Remove the shim directory. Returns True if something was removed."""
    target = shim_dir(hermes_home)
    if not target.is_dir():
        return False
    for name in ("__init__.py", "plugin.yaml"):
        try:
            (target / name).unlink(missing_ok=True)
        except OSError:
            pass
    try:
        target.rmdir()  # only removes if empty — never clobbers user files
    except OSError:
        pass
    return True
