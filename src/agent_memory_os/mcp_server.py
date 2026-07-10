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
        link = client.link(src_id, dst_id, relation=relation, weight=weight)
        return {"src_id": link.src_id, "dst_id": link.dst_id, "relation": link.relation, "weight": link.weight}

    @mcp.tool()
    def memory_recall_feedback(memory_ids: list[str], create_colinks: bool = False, helpful: bool = True) -> dict:
        return client.record_recall(memory_ids, create_colinks=create_colinks, helpful=helpful)

    @mcp.tool()
    def memory_consolidate(owner: str | None = None, scope: str | None = None) -> dict:
        return client.consolidate(owner=owner, scope=scope)

    return mcp


def main() -> None:  # pragma: no cover
    create_server().run()


if __name__ == "__main__":
    main()
