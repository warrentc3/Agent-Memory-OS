"""MCP server for Agent Memory OS.

Exposes the memory engine as Model Context Protocol tools so an MCP client
(Claude Code, Codex, or any MCP host) can persist and recall knowledge across
sessions. Run with `agent-memory-os[mcp]` installed; the core package keeps no
hard MCP dependency so the SDK and CLI stay lightweight.

Identity: set `AGENT_MEMORY_AGENT_ID` in the environment so every read/write is
attributed to that agent and gated by its team/project ACL. The identity is
taken ONLY from the environment, never from tool arguments, so one agent can
never read or mutate another agent's private memories.
"""

from typing import Annotated

from .client import MemoryClient


def create_server():  # pragma: no cover - optional integration scaffold
    try:
        from mcp.server.fastmcp import FastMCP
        from pydantic import Field
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("Install agent-memory-os[mcp] to run the MCP server") from exc

    import os

    mcp = FastMCP("agent-memory-os")
    client = MemoryClient()
    # Each connected agent declares WHO it is via env, so a project can mix
    # Claude Code / Codex / OpenClaw / Hermes profiles against one store and
    # every read/write carries the right identity and team ACL.
    agent_id = os.getenv("AGENT_MEMORY_AGENT_ID") or None
    if agent_id:
        client.store.touch_agent(agent_id)

    @mcp.tool()
    def memory_add(
        content: Annotated[str, Field(description="The fact to remember, as a self-contained sentence (e.g. 'The user prefers dark mode.'). Write it so it makes sense on its own in a future session.")],
        owner: Annotated[str | None, Field(description="Owner id the memory belongs to. Defaults to this server's AGENT_MEMORY_AGENT_ID, else 'default'.")] = None,
        scope: Annotated[str, Field(description="Lifecycle label used for graph coloring and filtering: 'user', 'agent', 'project', 'team', or 'global'. Does NOT set access control (use visibility for that).")] = "user",
        type: Annotated[str, Field(description="Kind of memory: 'preference', 'fact', 'procedure', 'environment', 'decision', 'warning', or 'note'.")] = "note",
    ) -> dict:
        """Store a durable memory that will survive across sessions.

        Use this to remember a user preference, project fact, decision, procedure,
        or lesson worth recalling later — not transient chat. Content is de-duplicated
        softly by the engine and becomes searchable immediately. Returns the new
        memory's stable `id` and stored `content`.
        """
        rec = client.add(content, owner=owner or agent_id or "default", scope=scope, type=type)
        return {"id": rec.id, "content": rec.content}

    @mcp.tool()
    def memory_search(
        query: Annotated[str, Field(description="Natural-language search query. Matches by keyword AND by association (linked memories surface even without shared words).")],
        owner: Annotated[str | None, Field(description="Optional filter to a single owner id. Leave unset to search everything this agent may see.")] = None,
        limit: Annotated[int, Field(description="Maximum number of results to return, best-first.", ge=1, le=100)] = 10,
    ) -> list[dict]:
        """Recall memories relevant to a query, ranked best-first.

        Call this before answering to retrieve what you already know. Results are
        access-controlled: only memories this agent (AGENT_MEMORY_AGENT_ID) is
        allowed to see are returned — private, its own, its teams'/projects', and
        global. Each result has `id`, `score` (relevance), `content`, `scope`, and
        `type`. Returns an empty list if nothing relevant is visible.
        """
        return [
            {"id": r.record.id, "score": r.score, "content": r.record.content, "scope": r.record.scope, "type": r.record.type}
            for r in client.search(query, owner=owner, limit=limit, requester_agent_id=agent_id)
        ]

    @mcp.tool()
    def memory_context_pack(
        query: Annotated[str, Field(description="The task or question to gather relevant memories for.")],
        owner: Annotated[str | None, Field(description="Optional filter to a single owner id. Leave unset to include everything this agent may see.")] = None,
        max_tokens: Annotated[int, Field(description="Approximate token budget for the returned block; the most relevant memories are selected to fit.", ge=128, le=32000)] = 1200,
    ) -> str:
        """Build a prompt-ready, token-budgeted block of the most relevant memories.

        Prefer this over `memory_search` when you want text to paste straight into a
        prompt: it selects and formats the highest-value memories within `max_tokens`,
        de-duplicates, and flags contradictions. Access-controlled to this agent's
        identity. Returns a formatted string (empty if nothing relevant is visible).
        """
        return client.context_pack(
            query, owner=owner, max_tokens=max_tokens, requester_agent_id=agent_id
        )

    @mcp.tool()
    def memory_link(
        src_id: Annotated[str, Field(description="Id of the source memory (from memory_add/memory_search).")],
        dst_id: Annotated[str, Field(description="Id of the destination memory to associate with the source.")],
        relation: Annotated[str, Field(description="Relationship type: 'related_to', 'supersedes', 'caused_by', 'derived_from', or 'co_recalled'.")] = "related_to",
        weight: Annotated[float, Field(description="Association strength from 0.0 to 1.0; higher means the memories surface together more strongly.", ge=0.0, le=1.0)] = 0.5,
    ) -> dict:
        """Create a directed association between two existing memories.

        Linked memories reinforce each other in recall, so a search that hits one can
        surface the other even with no shared keywords. Use it to connect a decision to
        its cause, or a fix to the problem it solved. Returns the created link, or an
        `{"error": ...}` object if either memory id does not exist.
        """
        try:
            link = client.link(src_id, dst_id, relation=relation, weight=weight)
        except KeyError as exc:
            return {"error": f"memory not found: {exc.args[0]}"}
        except ValueError as exc:
            return {"error": str(exc)}
        return {"src_id": link.src_id, "dst_id": link.dst_id, "relation": link.relation, "weight": link.weight}

    @mcp.tool()
    def memory_recall_feedback(
        memory_ids: Annotated[list[str], Field(description="Ids of memories that were just recalled together, whose usefulness you are reporting.")],
        create_colinks: Annotated[bool, Field(description="If true, create weak 'co_recalled' links between the given memories that weren't already linked.")] = False,
        helpful: Annotated[bool, Field(description="True if the recalled memories helped (reinforce them); False if they misled you (weaken them and lower confidence).")] = True,
    ) -> dict:
        """Report whether recalled memories were helpful, to tune future ranking.

        This closes the learning loop: `helpful=True` strengthens the memories and the
        links between them (they will resurface more readily); `helpful=False` weakens
        them and lowers their confidence. Only memories visible to this agent are
        affected — you cannot influence another identity's memories. Returns a summary
        of what was reinforced or weakened.
        """
        # Identity is the env-declared agent, never caller-supplied: an agent
        # must not weaken/reinforce (or even name) memories under another
        # identity's ACL. This is the gate _recall_eligible_ids relies on.
        return client.record_recall(
            memory_ids,
            create_colinks=create_colinks,
            helpful=helpful,
            requester_agent_id=agent_id,
        )

    @mcp.tool()
    def memory_update(
        memory_id: Annotated[str, Field(description="Id of the memory to modify.")],
        content: Annotated[str | None, Field(description="New content text. Omit to leave unchanged.")] = None,
        importance: Annotated[float | None, Field(description="New importance 0.0-1.0 (boosts ranking). Omit to leave unchanged.", ge=0.0, le=1.0)] = None,
        confidence: Annotated[float | None, Field(description="New confidence 0.0-1.0 (how sure the fact is true). Omit to leave unchanged.", ge=0.0, le=1.0)] = None,
        pinned: Annotated[bool | None, Field(description="Pin (true) to exempt the memory from decay/forgetting, or unpin (false). Omit to leave unchanged.")] = None,
    ) -> dict:
        """Update fields of an existing memory in place (keeps the same id).

        Use it to correct content, re-weight importance/confidence, or pin a memory so
        it is never forgotten. Only the fields you pass are changed. Returns the updated
        `id`, `content`, and `updated_at`, or an `{"error": ...}` object if the id does
        not exist.
        """
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
    def memory_consolidate(
        owner: Annotated[str | None, Field(description="Restrict consolidation to one owner id. Omit to consolidate across all owners this agent may modify.")] = None,
        scope: Annotated[str | None, Field(description="Restrict consolidation to one scope (e.g. 'project'). Omit for all scopes.")] = None,
    ) -> dict:
        """Merge duplicate memories and synthesize concept memories (housekeeping).

        A periodic hygiene pass: it collapses exact/near duplicates and combines
        strongly co-recalled clusters into higher-level concept memories, keeping the
        store compact and recall sharp. Safe to run occasionally rather than per-write.
        Returns counts of what was merged and created.
        """
        return client.consolidate(owner=owner, scope=scope)

    @mcp.tool()
    def memory_offload_context(
        session_id: Annotated[str, Field(description="Stable id for the working session this snapshot belongs to (used to reload later).")],
        snapshot_data: Annotated[dict, Field(description="Arbitrary JSON object capturing the working context to park (open files, plan, decisions, TODOs, etc.).")],
        trigger: Annotated[str, Field(description="Why the snapshot was taken, e.g. 'manual', 'pre-compaction', 'checkpoint'.")] = "manual",
    ) -> dict:
        """Park the agent's working context as a restorable snapshot (offload).

        Use before context runs out or when switching tasks, so the work can be reloaded
        later with `memory_reload_context` instead of being lost. Snapshots are rotated
        per session. Returns the new `snapshot_id` and `session_id`.
        """
        snapshot_id = client.offload_context(snapshot_data, session_id=session_id, trigger=trigger)
        return {"snapshot_id": snapshot_id, "session_id": session_id}

    @mcp.tool()
    def memory_orchestrate_context(
        task: Annotated[str, Field(description="The task you are about to work on; drives which memories are gathered.")],
        session_id: Annotated[str | None, Field(description="Optional session id. Pass the same id across calls to skip memories already delivered this session (iterative deepening).")] = None,
        max_tokens: Annotated[int, Field(description="Approximate token budget for the whole assembled block.", ge=128, le=32000)] = 2000,
    ) -> dict:
        """Assemble a rich, budget-aware context block for a task.

        A higher-level alternative to `memory_context_pack`: it splits the budget into
        sections — bedrock constants, proactive warnings and procedures, and relevance
        recall — in one prompt-ready block. With a `session_id`, repeated calls omit
        memories already delivered (bedrock constants always repeat). Access-controlled
        to this agent. Returns `text`, `sections`, `used_tokens`, `max_tokens`, `emphasis`.
        """
        # Identity is the env-declared agent, never caller-supplied, so a tool
        # call cannot pull another identity's private context.
        result = client.orchestrate_context(
            task,
            session_id=session_id,
            max_tokens=max_tokens,
            requester_agent_id=agent_id,
        )
        return {
            "text": result.text,
            "sections": result.sections,
            "used_tokens": result.used_tokens,
            "max_tokens": result.max_tokens,
            "emphasis": result.emphasis,
        }

    @mcp.tool()
    def memory_snapshot_diff(
        session_id: Annotated[str, Field(description="Session id whose two most recent snapshots should be compared.")],
    ) -> dict:
        """Show what changed between a session's two most recent context snapshots.

        Answers "what did I change since I last parked this work?" — returns the
        top-level keys added, removed, and changed between the previous and latest
        snapshot, or an `{"error": ...}` object if the session has fewer than two.
        """
        try:
            return client.snapshot_diff(session_id)
        except ValueError as exc:
            return {"error": str(exc)}

    @mcp.tool()
    def memory_reload_context(
        session_id: Annotated[str, Field(description="Session id to restore working context for.")],
        snapshot_id: Annotated[str | None, Field(description="Specific snapshot to reload. Omit to reload the most recent snapshot for the session.")] = None,
    ) -> dict:
        """Restore a previously offloaded working-context snapshot (reload).

        The counterpart to `memory_offload_context`: rehydrates the parked context so
        the agent can resume where it left off. Returns the snapshot's stored data, or
        an `{"error": ...}` object if the session/snapshot is not found.
        """
        try:
            return client.reload_context(session_id, snapshot_id=snapshot_id)
        except ValueError as exc:
            return {"error": str(exc)}

    return mcp


def main() -> None:  # pragma: no cover
    create_server().run()


if __name__ == "__main__":
    main()
