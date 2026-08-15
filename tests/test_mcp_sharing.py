"""MCP tools can create and change SHARED memories (not just private).

Before 1.0.5 the MCP `memory_add` had no visibility control, so anything an agent
stored via MCP was private to its owner — the "team memory" value prop was
unreachable through the primary interface. These cover the `share` parameter's
mapping and the new `memory_share` tool end to end over stdio.
"""

from __future__ import annotations

import sys

import pytest

from agent_memory_os.client import MemoryClient
from agent_memory_os.mcp_server import _share_to_visibility

# ---------- pure mapping ----------

def test_share_private_and_global():
    """Lineage:
    main: introduced 1bd4e557@db-schema-v15.
    """
    assert _share_to_visibility("private", teams=[], projects=[]) == []
    assert _share_to_visibility("", teams=[], projects=[]) == []
    assert _share_to_visibility(None, teams=[], projects=[]) == []
    assert _share_to_visibility("global", teams=[], projects=[]) == ["global"]


def test_share_explicit_grants():
    """Lineage:
    main: introduced 1bd4e557@db-schema-v15.
    """
    assert _share_to_visibility("team:apollo", teams=[], projects=[]) == ["team:apollo"]
    assert _share_to_visibility("project:web", teams=[], projects=[]) == ["project:web"]
    assert _share_to_visibility("agent:bob", teams=[], projects=[]) == ["agent:bob"]


def test_share_bare_team_resolves_when_unambiguous():
    """Lineage:
    main: introduced 1bd4e557@db-schema-v15.
    """
    assert _share_to_visibility("team", teams=["apollo"], projects=[]) == ["team:apollo"]
    assert _share_to_visibility("project", teams=[], projects=["web"]) == ["project:web"]


def test_share_bare_team_errors_when_none_or_ambiguous():
    """Lineage:
    main: introduced 1bd4e557@db-schema-v15.
    """
    with pytest.raises(ValueError, match="belongs to no team"):
        _share_to_visibility("team", teams=[], projects=[])
    with pytest.raises(ValueError, match="multiple teams"):
        _share_to_visibility("team", teams=["a", "b"], projects=[])


def test_share_invalid_target():
    """Lineage:
    main: introduced 1bd4e557@db-schema-v15.
    """
    with pytest.raises(ValueError, match="invalid share target"):
        _share_to_visibility("everyone", teams=[], projects=[])
    with pytest.raises(ValueError, match="invalid share target"):
        _share_to_visibility("team:", teams=[], projects=[])


# ---------- live MCP round-trip ----------

def _extract(result):
    import json
    # MCP SDK v2 exposes snake_case model fields; v1 used the wire-name
    # camelCase attribute. Accept both so the round-trip test pins behavior
    # across the migration boundary.
    sc = getattr(result, "structured_content", None)
    if sc is None:
        sc = getattr(result, "structuredContent", None)
    if sc:
        return sc.get("result", sc)
    return json.loads(result.content[0].text)


def test_mcp_add_shared_and_reshare_over_stdio(tmp_path):
    """memory_add(share=...) and memory_share change visibility through the MCP.

    Lineage:
    main: introduced 1bd4e557@db-schema-v15.
    """
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


def test_mcp_identity_owns_mutations_and_snapshots_over_stdio(tmp_path):
    """Sharing permits recall, but does not grant another MCP identity write access.

    Lineage:
    main: introduced bd659853@db-schema-v18.
    """
    pytest.importorskip("mcp")
    import os

    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def call_as(agent_id, requests):
        env = {
            **os.environ,
            "AGENT_MEMORY_HOME": str(tmp_path),
            "AGENT_MEMORY_AGENT_ID": agent_id,
        }
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "agent_memory_os.mcp_server"],
            env=env,
        )
        results = []
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                for name, arguments in requests:
                    results.append(_extract(await session.call_tool(name, arguments)))
        return results

    async def run():
        alice_memory, alice_snapshot, owner_override = await call_as(
            "alice",
            [
                (
                    "memory_add",
                    {
                        "content": "Alice shared deployment fact.",
                        "share": "global",
                    },
                ),
                (
                    "memory_offload_context",
                    {
                        "session_id": "same-label",
                        "snapshot_data": {"actor": "alice", "step": 1},
                    },
                ),
                (
                    "memory_add",
                    {"content": "Owner override attempt.", "owner": "bob"},
                ),
            ],
        )
        bob_memory = (
            await call_as(
                "bob",
                [("memory_add", {"content": "Bob's own deployment fact."})],
            )
        )[0]
        bob_results = await call_as(
            "bob",
            [
                (
                    "memory_update",
                    {
                        "memory_id": alice_memory["id"],
                        "content": "Bob overwrote Alice.",
                    },
                ),
                (
                    "memory_link",
                    {
                        "src_id": bob_memory["id"],
                        "dst_id": alice_memory["id"],
                    },
                ),
                (
                    "memory_recall_feedback",
                    {
                        "memory_ids": [alice_memory["id"], bob_memory["id"]],
                        "helpful": False,
                    },
                ),
                (
                    "memory_reload_context",
                    {
                        "session_id": "same-label",
                        "snapshot_id": alice_snapshot["snapshot_id"],
                    },
                ),
                ("memory_consolidate", {"owner": "alice"}),
            ],
        )
        alice_results = await call_as(
            "alice",
            [
                (
                    "memory_update",
                    {
                        "memory_id": alice_memory["id"],
                        "content": "Alice updated her own fact.",
                    },
                ),
                (
                    "memory_reload_context",
                    {
                        "session_id": "same-label",
                        "snapshot_id": alice_snapshot["snapshot_id"],
                    },
                ),
            ],
        )
        return alice_memory, bob_memory, owner_override, bob_results, alice_results

    alice_memory, bob_memory, owner_override, bob_results, alice_results = anyio.run(run)

    assert "error" in owner_override
    assert "error" in bob_results[0]
    assert "error" in bob_results[1]
    assert bob_results[2]["weakened_memories"] == 1
    assert "error" in bob_results[3]
    assert "error" in bob_results[4]
    assert alice_results[0]["content"] == "Alice updated her own fact."
    assert alice_results[1] == {"actor": "alice", "step": 1}

    client = MemoryClient(home=tmp_path)
    try:
        assert client.get(alice_memory["id"]).confidence == 0.8
        assert client.get(bob_memory["id"]).confidence < 0.8
    finally:
        client.close()
