"""Verify the MCP Registry manifest (server.json) and the one-click run path.

- server.json is structurally valid and self-consistent with the PyPI package;
  if the live registry schema is reachable, validate against it too.
- `python -m agent_memory_os.mcp_server` (the exact command in server.json and the
  README's `claude mcp add`) actually starts an MCP server over stdio and lists
  the memory_* tools — the real proof that a registry one-click install works.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SERVER_JSON = ROOT / "server.json"


def _load():
    return json.loads(SERVER_JSON.read_text(encoding="utf-8"))


def test_server_json_structure_and_package_consistency():
    """Lineage:
    main: introduced 83016233@db-schema-v15.
    """
    m = _load()
    assert m["$schema"].startswith("https://static.modelcontextprotocol.io/schemas/")
    assert re.fullmatch(r"io\.github\.[\w-]+/[\w.-]+", m["name"]), m["name"]
    assert m["description"] and m["repository"]["source"] == "github"
    pkgs = m["packages"]
    assert len(pkgs) == 1
    pkg = pkgs[0]
    assert pkg["registryType"] == "pypi"
    assert pkg["identifier"] == "agent-memory-os"       # matches the published PyPI name
    assert pkg["transport"]["type"] == "stdio"


def test_readme_carries_ownership_marker():
    """Lineage:
    main: introduced 83016233@db-schema-v15.
    """
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    name = _load()["name"]
    # the registry verifies PyPI ownership via this marker in the description
    assert f"mcp-name: {name}" in readme


def test_server_json_matches_live_schema_if_reachable():
    """Lineage:
    main: introduced 83016233@db-schema-v15.
    """
    import urllib.request

    m = _load()
    try:
        with urllib.request.urlopen(m["$schema"], timeout=8) as r:
            schema = json.load(r)
    except Exception:  # noqa: BLE001 - offline CI shouldn't fail the suite
        pytest.skip("registry schema not reachable")
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(instance=m, schema=schema)


def test_mcp_server_starts_and_lists_tools(tmp_path):
    """Spawn the exact registry/README command and do a real MCP handshake.

    Lineage:
    main: introduced 83016233@db-schema-v15.
    """
    pytest.importorskip("mcp")
    import os

    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    # Inherit the current environment (venv / PYTHONPATH) so the module resolves
    # in an editable checkout as well as a real `pip install`.
    env = {**os.environ, "AGENT_MEMORY_HOME": str(tmp_path), "AGENT_MEMORY_AGENT_ID": "tester"}
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "agent_memory_os.mcp_server"],
        env=env,
    )

    async def run() -> list[str]:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                return [t.name for t in tools.tools]

    names = anyio.run(run)
    assert "memory_add" in names and "memory_search" in names
    assert "memory_context_pack" in names
