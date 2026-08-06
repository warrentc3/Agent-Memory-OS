"""MCP Python SDK v2 worker-thread regression tests."""

from __future__ import annotations

from importlib.metadata import version
import threading

import pytest

from agent_memory_os.client import MemoryClient
from agent_memory_os.mcp_server import create_server


def test_mcp_v2_serializes_shared_sqlite_client(monkeypatch, tmp_path):
    """Two v2 worker handlers must not enter one MemoryClient concurrently."""
    pytest.importorskip("mcp")
    if int(version("mcp").split(".", 1)[0]) < 2:
        pytest.skip("MCP SDK v2-only concurrency gate")

    import anyio
    import mcp

    Client = getattr(mcp, "Client")

    monkeypatch.setenv("AGENT_MEMORY_HOME", str(tmp_path))
    monkeypatch.setenv("AGENT_MEMORY_AGENT_ID", "thread-gate")

    original_search = MemoryClient.search
    state_lock = threading.Lock()
    first_entered = threading.Event()
    second_entered = threading.Event()
    state = {"active": 0, "max_active": 0, "thread_ids": set()}
    caller_thread_id = threading.get_ident()

    def observed_search(self, *args, **kwargs):
        with state_lock:
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
            state["thread_ids"].add(threading.get_ident())
            ordinal = state["active"]
        try:
            if ordinal == 1:
                first_entered.set()
                second_entered.wait(timeout=0.25)
            else:
                second_entered.set()
            return original_search(self, *args, **kwargs)
        finally:
            with state_lock:
                state["active"] -= 1

    monkeypatch.setattr(MemoryClient, "search", observed_search)
    server = create_server()

    async def run() -> None:
        async with Client(server) as first, Client(server) as second:
            async with anyio.create_task_group() as group:
                group.start_soon(first.call_tool, "memory_search", {"query": "alpha"})
                group.start_soon(second.call_tool, "memory_search", {"query": "beta"})

    anyio.run(run)

    assert first_entered.is_set()
    assert state["max_active"] == 1
    assert caller_thread_id not in state["thread_ids"]
    assert len(state["thread_ids"]) == 2
