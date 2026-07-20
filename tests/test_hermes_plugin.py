"""Hermes memory-provider plugin behaves per the v0.18 MemoryProvider contract.

The real base class only exists inside a Hermes runtime, so these tests stub
`agent.memory_provider` into sys.modules BEFORE importing the plugin — the
same shape Hermes's PluginManager would provide — and exercise the provider
against a real (tmp) AgentMemoryOS store.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import types

import pytest


@pytest.fixture()
def hermes_plugin(monkeypatch):
    """Import agent_memory_os.hermes_plugin under a stubbed Hermes runtime."""
    agent_pkg = types.ModuleType("agent")
    provider_mod = types.ModuleType("agent.memory_provider")

    class MemoryProvider:  # minimal stand-in for the Hermes ABC
        pass

    provider_mod.MemoryProvider = MemoryProvider
    agent_pkg.memory_provider = provider_mod
    monkeypatch.setitem(sys.modules, "agent", agent_pkg)
    monkeypatch.setitem(sys.modules, "agent.memory_provider", provider_mod)

    for mod in ("agent_memory_os.hermes_plugin",):
        sys.modules.pop(mod, None)
    import agent_memory_os.hermes_plugin as hp

    assert hp._HERMES_RUNTIME is True
    yield hp
    sys.modules.pop("agent_memory_os.hermes_plugin", None)


@pytest.fixture()
def provider(hermes_plugin, tmp_path, monkeypatch):
    monkeypatch.delenv("AGENT_MEMORY_AGENT_ID", raising=False)
    monkeypatch.setenv("AGENT_MEMORY_HOME", str(tmp_path / "amos"))
    p = hermes_plugin.AgentMemoryOSProvider()
    p.initialize(
        "sess-1",
        hermes_home=str(tmp_path / "hermes"),
        platform="cli",
        agent_context="primary",
        agent_identity="bastet",
    )
    yield p
    p.shutdown()


def test_identity_and_availability(hermes_plugin, provider):
    assert provider.name == "agent-memory-os"
    assert provider.is_available() is True
    assert provider._agent_id == "hermes-bastet"  # derived from profile


def test_add_search_roundtrip_and_prefetch(provider):
    out = json.loads(provider.handle_tool_call(
        "amos_add", {"content": "Deploys use blue-green rollout.",
                     "type": "procedure"}))
    assert out["visibility"] == []  # share_default=private

    found = json.loads(provider.handle_tool_call(
        "amos_search", {"query": "blue-green"}))
    assert found["count"] >= 1
    assert any("blue-green" in r["content"] for r in found["results"])

    pack = provider.prefetch("how do we deploy? blue-green?")
    assert "blue-green" in pack
    assert pack.startswith("Recalled from AgentMemoryOS")
    assert provider.prefetch("") == ""  # empty query -> no injection


def test_acl_prefetch_excludes_other_agents_private(provider):
    # Another agent's PRIVATE memory in the same store must never surface.
    provider._client.add(
        "topsecret rotation password procedure",
        owner="someone-else", visibility=[],
    )
    assert "topsecret" not in provider.prefetch("topsecret rotation procedure")
    found = json.loads(provider.handle_tool_call(
        "amos_search", {"query": "topsecret rotation"}))
    assert all("topsecret" not in r["content"] for r in found["results"])


def test_share_and_reshare(provider):
    out = json.loads(provider.handle_tool_call(
        "amos_add", {"content": "team runbook lives in /ops",
                     "share": "global"}))
    assert out["visibility"] == ["global"]

    reshared = json.loads(provider.handle_tool_call(
        "amos_share", {"memory_id": out["id"], "share": "private"}))
    assert reshared["visibility"] == []

    # Owner-only: another agent's memory cannot be re-shared.
    other = provider._client.add("not yours", owner="someone-else")
    denied = json.loads(provider.handle_tool_call(
        "amos_share", {"memory_id": other.id, "share": "global"}))
    assert "owner" in denied["error"]


def test_invalid_share_is_reported_not_raised(provider):
    out = json.loads(provider.handle_tool_call(
        "amos_add", {"content": "x", "share": "everyone"}))
    assert "error" in out


def test_readonly_context_blocks_writes(hermes_plugin, tmp_path):
    p = hermes_plugin.AgentMemoryOSProvider()
    p.initialize(
        "sess-cron",
        hermes_home=str(tmp_path / "hermes"),
        agent_context="cron",
    )
    try:
        out = json.loads(p.handle_tool_call("amos_add", {"content": "spam"}))
        assert "read-only" in out["error"]
        p.on_memory_write("add", "memory", "cron noise")
        found = json.loads(p.handle_tool_call("amos_search", {"query": "spam OR noise"}))
        assert found["count"] == 0
    finally:
        p.shutdown()


def test_builtin_memory_mirror_is_idempotent(provider):
    provider.on_memory_write("add", "memory", "User prefers pnpm.")
    provider.on_memory_write("add", "memory", "User prefers pnpm.")  # replay
    provider._mirrored.clear()  # simulate process restart
    provider.on_memory_write("replace", "memory", "User prefers pnpm.")

    found = json.loads(provider.handle_tool_call(
        "amos_search", {"query": "pnpm"}))
    assert found["count"] == 1  # one stable record, not three

    # 'remove' actions and disabled mirroring are ignored. (Associative
    # recall may still surface OTHER records for an unmatched query, so
    # assert the specific content was not stored rather than count==0.)
    provider.on_memory_write("remove", "memory", "User prefers pnpm.")
    provider._config["mirror_builtin"] = False
    provider.on_memory_write("add", "memory", "Another fact entirely.")
    found = json.loads(provider.handle_tool_call(
        "amos_search", {"query": "Another fact"}))
    assert all("Another fact" not in r["content"] for r in found["results"])


def test_delegation_capture(provider):
    provider.on_delegation(
        "Audit the sync module for leaks", "No leaks found; 3 warnings.",
        child_session_id="sub-9",
    )
    found = json.loads(provider.handle_tool_call(
        "amos_search", {"query": "audit sync leaks"}))
    assert found["count"] == 1
    assert "No leaks found" in found["results"][0]["content"]

    provider._config["capture_delegations"] = False
    provider.on_delegation("task two", "result two")
    found = json.loads(provider.handle_tool_call(
        "amos_search", {"query": "task two"}))
    assert all("result two" not in r["content"] for r in found["results"])


def test_tool_schemas_shape_and_prefix(provider):
    schemas = provider.get_tool_schemas()
    names = {s["name"] for s in schemas}
    assert names == {"amos_search", "amos_add", "amos_share"}
    for s in schemas:
        assert s["name"].startswith("amos_")  # never shadow Hermes core tools
        assert s["description"]
        assert s["parameters"]["type"] == "object"


def test_config_file_overrides_and_save_config(hermes_plugin, tmp_path, monkeypatch):
    monkeypatch.delenv("AGENT_MEMORY_AGENT_ID", raising=False)
    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    (hermes_home / hermes_plugin.CONFIG_FILENAME).write_text(json.dumps({
        "agent_id": "bastet-prime",
        "share_default": "team",
        "home": str(tmp_path / "custom-home"),
    }))
    p = hermes_plugin.AgentMemoryOSProvider()
    p.initialize("s", hermes_home=str(hermes_home))
    try:
        assert p._agent_id == "bastet-prime"
        assert p._config["share_default"] == "team"
        # save_config merges without clobbering unrelated keys
        p.save_config({"share_default": "global"}, str(hermes_home))
        merged = json.loads((hermes_home / hermes_plugin.CONFIG_FILENAME).read_text())
        assert merged["share_default"] == "global"
        assert merged["agent_id"] == "bastet-prime"
    finally:
        p.shutdown()

    # invalid share_default falls back to private
    cfg = hermes_plugin._load_config(str(hermes_home))
    (hermes_home / hermes_plugin.CONFIG_FILENAME).write_text(
        json.dumps({"share_default": "bogus"}))
    cfg = hermes_plugin._load_config(str(hermes_home))
    assert cfg["share_default"] == "private"


def test_backup_paths_points_at_store_home(provider, tmp_path):
    paths = provider.backup_paths()
    assert str(tmp_path / "amos") in paths


def test_register_wires_provider(hermes_plugin):
    class Ctx:
        provider = None

        def register_memory_provider(self, p):
            self.provider = p

    ctx = Ctx()
    hermes_plugin.register(ctx)
    assert isinstance(ctx.provider, hermes_plugin.AgentMemoryOSProvider)


def test_entry_point_declared():
    import importlib.metadata as md
    eps = md.entry_points()
    group = eps.select(group="hermes_agent.plugins") if hasattr(eps, "select") else eps.get("hermes_agent.plugins", [])
    names = {ep.name: ep.value for ep in group}
    assert names.get("agent-memory-os") == "agent_memory_os.hermes_plugin"


# ---------- `agent-memory hermes install` shim ----------


def test_install_shim_passes_hermes_discovery_heuristic(hermes_plugin, tmp_path):
    """The shim must satisfy Hermes's `_is_memory_provider_dir` text scan
    and carry a plugin.yaml with name/description for the setup picker."""
    report = hermes_plugin.install_shim(tmp_path)
    shim = tmp_path / "plugins" / "agent-memory-os"
    assert report["installed"] == str(shim)

    init_src = (shim / "__init__.py").read_text()[:8192]
    # Hermes scans for these literal strings to classify the dir:
    assert "register_memory_provider" in init_src or "MemoryProvider" in init_src

    yaml_text = (shim / "plugin.yaml").read_text()
    assert "name: agent-memory-os" in yaml_text
    assert "description:" in yaml_text
    assert "agent-memory-os" in yaml_text  # pip_dependencies restore path

    # Idempotent: re-install refreshes without error.
    report2 = hermes_plugin.install_shim(tmp_path)
    assert report2["installed"] == report["installed"]


def test_shim_loads_like_hermes_loader(hermes_plugin, tmp_path, monkeypatch):
    """Load the shim the way Hermes's _load_provider_from_dir does:
    import __init__.py, call register(collector), expect a provider."""
    import importlib.util

    hermes_plugin.install_shim(tmp_path)
    init_file = tmp_path / "plugins" / "agent-memory-os" / "__init__.py"
    spec = importlib.util.spec_from_file_location("_shim_under_test", init_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    class Collector:
        provider = None

        def register_memory_provider(self, p):
            self.provider = p

    collector = Collector()
    mod.register(collector)
    assert isinstance(collector.provider, hermes_plugin.AgentMemoryOSProvider)


def test_uninstall_shim(hermes_plugin, tmp_path):
    hermes_plugin.install_shim(tmp_path)
    assert hermes_plugin.uninstall_shim(tmp_path) is True
    assert not (tmp_path / "plugins" / "agent-memory-os").exists()
    assert hermes_plugin.uninstall_shim(tmp_path) is False  # already gone


def test_cli_hermes_install_roundtrip(hermes_plugin, tmp_path, capsys):
    from agent_memory_os.cli import main

    rc = main(["hermes", "install", "--hermes-home", str(tmp_path), "--json"])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert Path(report["installed"]).parts[-2:] == ("plugins", "agent-memory-os")

    rc = main(["hermes", "uninstall", "--hermes-home", str(tmp_path), "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["removed"] is True
