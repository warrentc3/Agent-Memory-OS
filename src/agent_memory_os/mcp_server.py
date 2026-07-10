"""Optional MCP server scaffold.

Run with an environment that has the `mcp` package installed. The core package has no hard MCP dependency so the SDK and CLI stay lightweight.
"""

from __future__ import annotations

from .client import MemoryClient


def create_server():  # pragma: no cover - optional integration scaffold
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("Install agent-memory-os[mcp] to run the MCP server") from exc

    mcp = FastMCP("agent-memory-os")
    client = MemoryClient()

    @mcp.tool()
    def memory_add(content: str, owner: str = "default", scope: str = "user", type: str = "note") -> dict:
        rec = client.add(content, owner=owner, scope=scope, type=type)
        return {"id": rec.id, "content": rec.content}

    @mcp.tool()
    def memory_search(query: str, owner: str | None = None, limit: int = 10) -> list[dict]:
        return [
            {"id": r.record.id, "score": r.score, "content": r.record.content, "scope": r.record.scope, "type": r.record.type}
            for r in client.search(query, owner=owner, limit=limit)
        ]

    @mcp.tool()
    def memory_context_pack(query: str, owner: str | None = None, max_tokens: int = 1200) -> str:
        return client.context_pack(query, owner=owner, max_tokens=max_tokens)

    @mcp.tool()
    def memory_link(src_id: str, dst_id: str, relation: str = "related_to", weight: float = 0.5) -> dict:
        try:
            link = client.link(src_id, dst_id, relation=relation, weight=weight)
        except KeyError as exc:
            return {"error": f"memory not found: {exc.args[0]}"}
        except ValueError as exc:
            return {"error": str(exc)}
        return {"src_id": link.src_id, "dst_id": link.dst_id, "relation": link.relation, "weight": link.weight}

    @mcp.tool()
    def memory_recall_feedback(
        memory_ids: list[str],
        create_colinks: bool = False,
        helpful: bool = True,
        requester_agent_id: str | None = None,
    ) -> dict:
        return client.record_recall(
            memory_ids,
            create_colinks=create_colinks,
            helpful=helpful,
            requester_agent_id=requester_agent_id,
        )

    @mcp.tool()
    def memory_update(memory_id: str, content: str | None = None, importance: float | None = None,
                      confidence: float | None = None, pinned: bool | None = None) -> dict:
        fields = {k: v for k, v in {"content": content, "importance": importance,
                                    "confidence": confidence, "pinned": pinned}.items() if v is not None}
        try:
            rec = client.update(memory_id, **fields)
        except KeyError:
            return {"error": f"memory not found: {memory_id}"}
        except ValueError as exc:
            return {"error": str(exc)}
        return {"id": rec.id, "content": rec.content, "updated_at": rec.updated_at}

    @mcp.tool()
    def memory_consolidate(owner: str | None = None, scope: str | None = None) -> dict:
        return client.consolidate(owner=owner, scope=scope)

    @mcp.tool()
    def memory_offload_context(session_id: str, snapshot_data: dict, trigger: str = "manual") -> dict:
        """Save the agent's working context as a snapshot memory (DCO offload)."""
        snapshot_id = client.offload_context(snapshot_data, session_id=session_id, trigger=trigger)
        return {"snapshot_id": snapshot_id, "session_id": session_id}

    @mcp.tool()
    def memory_reload_context(session_id: str, snapshot_id: str | None = None) -> dict:
        """Reload the latest (or a specific) context snapshot for a session (DCO reload)."""
        try:
            return client.reload_context(session_id, snapshot_id=snapshot_id)
        except ValueError as exc:
            return {"error": str(exc)}

    return mcp


def main() -> None:  # pragma: no cover
    create_server().run()


if __name__ == "__main__":
    main()
