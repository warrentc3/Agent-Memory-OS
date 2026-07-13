"""MCP tools can create and change SHARED memories (not just private).

Before 1.0.5 the MCP `memory_add` had no visibility control, so anything an agent
stored via MCP was private to its owner — the "team memory" value prop was
unreachable through the primary interface. These cover the `share` parameter's
mapping and the new `memory_share` tool end to end over stdio.
"""

from __future__ import annotations

import sys

import pytest

from agent_memory_os.mcp_server import _share_to_visibility


# ---------- pure mapping ----------

def test_share_private_and_global():
    assert _share_to_visibility("private", teams=[], projects=[]) == []
    assert _share_to_visibility("", teams=[], projects=[]) == []
    assert _share_to_visibility(None, teams=[], projects=[]) == []
    assert _share_to_visibility("global", teams=[], projects=[]) == ["global"]


def test_share_explicit_grants():
    assert _share_to_visibility("team:apollo", teams=[], projects=[]) == ["team:apollo"]
    assert _share_to_visibility("project:web", teams=[], projects=[]) == ["project:web"]
    assert _share_to_visibility("agent:bob", teams=[], projects=[]) == ["agent:bob"]


def test_share_bare_team_resolves_when_unambiguous():
    assert _share_to_visibility("team", teams=["apollo"], projects=[]) == ["team:apollo"]
    assert _share_to_visibility("project", teams=[], projects=["web"]) == ["project:web"]


def test_share_bare_team_errors_when_none_or_ambiguous():
    with pytest.raises(ValueError, match="belongs to no team"):
        _share_to_visibility("team", teams=[], projects=[])
    with pytest.raises(ValueError, match="multiple teams"):
        _share_to_visibility("team", teams=["a", "b"], projects=[])


def test_share_invalid_target():
    with pytest.raises(ValueError, match="invalid share target"):
        _share_to_visibility("everyone", teams=[], projects=[])
    with pytest.raises(ValueError, match="invalid share target"):
        _share_to_visibility("team:", teams=[], projects=[])


# ---------- live MCP round-trip ----------

def _extract(result):
    import json
    if getattr(result, "structuredContent", None):
        sc = result.structuredContent
        return sc.get("result", sc)
    return json.loads(result.content[0].text)


def test_mcp_add_shared_and_reshare_over_stdio(tmp_path):
    """memory_add(share=...) and memory_share change visibility through the MCP."""
    pytest.importorskip("mcp")
    import os

    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = {**os.environ, "AGENT_MEMORY_HOME": str(tmp_path), "AGENT_MEMORY_AGENT_ID": "tester"}
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "agent_memory_os.mcp_server"], env=env,
    )

    async def run():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                names = {t.name for t in (await session.list_tools()).tools}
                # add a globally-shared memory
                g = _extract(await session.call_tool(
                    "memory_add", {"content": "shared deploy note", "share": "global"}))
                # add a private one (default)
                p = _extract(await session.call_tool(
                    "memory_add", {"content": "personal scratch"}))
                # reshare the private one to global
                s = _extract(await session.call_tool(
                    "memory_share", {"memory_id": p["id"], "share": "global"}))
                return names, g, p, s

    names, g, p, s = anyio.run(run)
    assert "memory_share" in names                       # new tool is exposed
    assert g["visibility"] == ["global"]                 # share=global honored
    assert p["visibility"] == []                         # default stays private
    assert s["visibility"] == ["global"]                 # memory_share promoted it
