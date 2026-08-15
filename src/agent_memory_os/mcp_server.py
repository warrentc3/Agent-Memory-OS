"""MCP server for Agent Memory OS.

Exposes the memory engine as Model Context Protocol tools so an MCP client
(Claude Code, Codex, or any MCP host) can persist and recall knowledge across
sessions. Run with `agent-memory-os[mcp]` installed; the core package keeps no
hard MCP dependency so the SDK and CLI stay lightweight.

Identity: set `AGENT_MEMORY_AGENT_ID` in the environment so every read/write is
attributed to that agent and gated by its team/project ACL. When configured,
the identity is taken only from the environment; an optional legacy owner
argument may match it but cannot override it. An unset identity retains the
legacy administrative/default compatibility behavior and is not isolated.
"""

from typing import Annotated, Literal

from .client import MemoryClient


def _share_to_visibility(share: str | None, *, teams: list[str], projects: list[str]) -> list[str]:
    """Map a friendly `share` string to a visibility (ACL) grant list.

    'private'/'' -> [] (owner only); 'global' -> everyone; 'team'/'project' ->
    the caller's own team/project when unambiguous (given `teams`/`projects`);
    'team:<id>', 'project:<id>', 'agent:<id>' -> that exact grant. Raises
    ValueError with a helpful message for ambiguous/invalid input.
    """
    s = (share or "private").strip()
    if s in ("", "private"):
        return []
    if s == "global":
        return ["global"]
    if s in ("team", "project"):
        ids = teams if s == "team" else projects
        if len(ids) == 1:
            return [f"{s}:{ids[0]}"]
        if not ids:
            raise ValueError(
                f"cannot share to '{s}': this agent belongs to no {s}. "
                f"Pass an explicit '{s}:<id>' or ask an admin to add you."
            )
        raise ValueError(
            f"this agent is in multiple {s}s {ids}; pass an explicit '{s}:<id>'."
        )
    if s.startswith(("team:", "project:", "agent:")) and len(s.split(":", 1)[1]) > 0:
        return [s]
    raise ValueError(
        f"invalid share target {share!r}; use 'private', 'global', "
        f"'team' or 'team:<id>', 'project' or 'project:<id>', or 'agent:<id>'."
    )


def create_server():  # pragma: no cover - optional integration scaffold
    try:
        try:
            # MCP Python SDK v2 (current stable API). getattr keeps static
            # analysis compatible with development environments still on v1.
            from mcp import server as mcp_server  # type: ignore[import-not-found]
            MCPServer = getattr(mcp_server, "MCPServer")
        except (ImportError, AttributeError):
            # Keep source checkouts usable with the maintained v1 SDK line;
            # packaged installs require v2 through the `mcp` extra below.
            from mcp.server.fastmcp import (  # type: ignore[import-not-found]
                FastMCP as MCPServer,
            )
        from pydantic import Field  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("Install agent-memory-os[mcp] to run the MCP server") from exc

    import os
    import threading
    from functools import wraps

    mcp = MCPServer("agent-memory-os")
    # MCP SDK v2 executes synchronous handlers in AnyIO worker threads. Allow
    # that gateway-to-worker handoff, then serialize all tool access because a
    # single SQLite connection must never be used concurrently.
    client = MemoryClient(check_same_thread=False)
    client_lock = threading.Lock()

    def _serialized_tool(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            with client_lock:
                return func(*args, **kwargs)

        return wrapped
    # Each connected agent declares WHO it is via env, so a project can mix
    # Claude Code / Codex / OpenClaw / Hermes profiles against one store and
    # every read/write carries the right identity and team ACL.
    agent_id = os.getenv("AGENT_MEMORY_AGENT_ID") or None
    if agent_id:
        client.store.touch_agent(agent_id)

    def _resolve_share(share: str | None) -> list[str]:
        return _share_to_visibility(
            share,
            teams=client.store.teams_for(agent_id) if agent_id else [],
            projects=client.store.projects_for(agent_id) if agent_id else [],
        )

    @mcp.tool()
    @_serialized_tool
    def memory_add(
        content: Annotated[str, Field(description="The fact to remember, as a self-contained sentence (e.g. 'The user prefers dark mode.'). Write it so it makes sense on its own in a future session.")],
        owner: Annotated[
            str | None,
            Field(
                description="Legacy compatibility field. If supplied, it must match "
                "this server's AGENT_MEMORY_AGENT_ID when one is configured."
            ),
        ] = None,
        scope: Annotated[
            Literal["user", "agent", "project", "team", "global"],
            Field(
                description="Lifecycle label used for graph coloring and filtering. "
                "Does NOT set access control (use `share` for that)."
            ),
        ] = "user",
        type: Annotated[
            Literal[
                "preference",
                "fact",
                "procedure",
                "environment",
                "decision",
                "warning",
                "note",
            ],
            Field(description="Kind of memory."),
        ] = "note",
        share: Annotated[str, Field(description="Who may read this memory (the ACL). 'private' (default, owner only), 'global' (all agents), 'team' or 'team:<id>' (your team — teammates on the same node share it), 'project' or 'project:<id>', or 'agent:<id>'. Use 'team'/'project' to share with collaborators; leave 'private' for personal notes.")] = "private",
    ) -> dict:
        """Store a durable memory that will survive across sessions.

        Use this to remember a user preference, project fact, decision, procedure,
        or lesson worth recalling later — not transient chat. Set `share` to make it
        visible to teammates ('team'/'project') instead of just yourself; the default
        is private. Content is de-duplicated softly and becomes searchable immediately.
        Returns the new memory's `id`, `content`, and resolved `visibility`, or an
        `{"error": ...}` object if `share` names a team/project you can't resolve.
        """
        try:
            visibility = _resolve_share(share)
        except ValueError as exc:
            return {"error": str(exc)}
        if agent_id is not None and owner is not None and owner != agent_id:
            return {"error": "owner must match this MCP server's configured identity"}
        effective_owner = agent_id or owner or "default"
        rec = client.add(
            content,
            owner=effective_owner,
            scope=scope,
            type=type,
            visibility=visibility,
        )
        return {"id": rec.id, "content": rec.content, "visibility": rec.visibility}

    @mcp.tool()
    @_serialized_tool
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
    @_serialized_tool
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
    @_serialized_tool
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
        `{"error": ...}` object if either memory id does not exist or, when an
        identity is configured, is not owned by that agent.
        """
        try:
            link = client.link(
                src_id,
                dst_id,
                relation=relation,
                weight=weight,
                requester_agent_id=agent_id,
            )
        except KeyError as exc:
            return {"error": f"memory not found: {exc.args[0]}"}
        except ValueError as exc:
            return {"error": str(exc)}
        except PermissionError as exc:
            return {"error": str(exc)}
        return {
            "src_id": link.src_id,
            "dst_id": link.dst_id,
            "relation": link.relation,
            "weight": link.weight,
        }

    @mcp.tool()
    @_serialized_tool
    def memory_recall_feedback(
        memory_ids: Annotated[list[str], Field(description="Ids of memories that were just recalled together, whose usefulness you are reporting.")],
        create_colinks: Annotated[bool, Field(description="If true, create weak 'co_recalled' links between the given memories that weren't already linked.")] = False,
        helpful: Annotated[bool, Field(description="True if the recalled memories helped (reinforce them); False if they misled you (weaken them and lower confidence).")] = True,
    ) -> dict:
        """Report whether recalled memories were helpful, to tune future ranking.

        This closes the learning loop: `helpful=True` strengthens the memories and the
        links between them (they will resurface more readily); `helpful=False` weakens
        them and lowers their confidence. With a configured identity, only memories
        owned by that agent are affected; sharing grants recall access, not mutation
        authority. Returns a summary of what was reinforced or weakened.
        """
        # Identity is the env-declared agent, never caller-supplied: an agent
        # must not weaken/reinforce (or even name) memories under another
        # identity's ACL. This is the gate _recall_eligible_ids relies on.
        return client.record_recall(
            memory_ids,
            create_colinks=create_colinks,
            helpful=helpful,
            requester_agent_id=agent_id,
            owner=agent_id,
        )

    @mcp.tool()
    @_serialized_tool
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
        not exist or, when an identity is configured, is not owned by that agent.
        """
        fields = {k: v for k, v in {"content": content, "importance": importance,
                                    "confidence": confidence, "pinned": pinned}.items() if v is not None}
        try:
            rec = client.update(
                memory_id,
                requester_agent_id=agent_id,
                **fields,
            )
        except KeyError:
            return {"error": f"memory not found: {memory_id}"}
        except ValueError as exc:
            return {"error": str(exc)}
        except PermissionError as exc:
            return {"error": str(exc)}
        return {"id": rec.id, "content": rec.content, "updated_at": rec.updated_at}

    @mcp.tool()
    @_serialized_tool
    def memory_share(
        memory_id: Annotated[str, Field(description="Id of the memory whose visibility you want to change.")],
        share: Annotated[str, Field(description="New audience: 'private' (owner only), 'global' (all agents), 'team' or 'team:<id>', 'project' or 'project:<id>', or 'agent:<id>'.")] = "private",
    ) -> dict:
        """Change who can read an existing memory (share it, or make it private again).

        Use this to promote a note you already stored to your team/project so
        collaborators can recall it, or to lock it back down. Only the memory's OWNER
        may change its visibility. The change propagates over sync — sharing reaches
        teammates, and making it private retracts it. Returns the memory's `id` and new
        `visibility`, or an `{"error": ...}` object if it doesn't exist, isn't yours, or
        `share` is invalid.
        """
        existing = client.get_visible(memory_id, requester_agent_id=agent_id)
        if existing is None:
            return {"error": f"memory not found: {memory_id}"}
        if agent_id is not None and existing.owner != agent_id:
            return {
                "error": f"only the owner ({existing.owner}) can change this memory's visibility"
            }
        try:
            visibility = _resolve_share(share)
        except ValueError as exc:
            return {"error": str(exc)}
        rec = client.update(
            memory_id,
            requester_agent_id=agent_id,
            visibility=visibility,
        )
        return {"id": rec.id, "visibility": rec.visibility}

    @mcp.tool()
    @_serialized_tool
    def memory_consolidate(
        owner: Annotated[
            str | None,
            Field(
                description="Legacy compatibility filter. If supplied, it must match "
                "this server's configured identity when one exists. Omit to "
                "consolidate that identity's memories; an unset identity retains "
                "the legacy administrative view."
            ),
        ] = None,
        scope: Annotated[str | None, Field(description="Restrict consolidation to one scope (e.g. 'project'). Omit for all scopes.")] = None,
    ) -> dict:
        """Merge duplicate memories and synthesize concept memories (housekeeping).

        A periodic hygiene pass: it collapses exact/near duplicates and combines
        strongly co-recalled clusters into higher-level concept memories, keeping the
        store compact and recall sharp. Safe to run occasionally rather than per-write.
        Returns counts of what was merged and created.
        """
        try:
            return client.consolidate(
                owner=owner,
                scope=scope,
                requester_agent_id=agent_id,
            )
        except PermissionError as exc:
            return {"error": str(exc)}

    @mcp.tool()
    @_serialized_tool
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
        snapshot_id = client.offload_context(
            snapshot_data,
            session_id=session_id,
            trigger=trigger,
            owner=agent_id or "default",
        )
        return {"snapshot_id": snapshot_id, "session_id": session_id}

    @mcp.tool()
    @_serialized_tool
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
    @_serialized_tool
    def memory_snapshot_diff(
        session_id: Annotated[str, Field(description="Session id whose two most recent snapshots should be compared.")],
    ) -> dict:
        """Show what changed between a session's two most recent context snapshots.

        Answers "what did I change since I last parked this work?" — returns the
        top-level keys added, removed, and changed between the previous and latest
        snapshot, or an `{"error": ...}` object if the session has fewer than two.
        """
        try:
            return client.snapshot_diff(
                session_id,
                requester_agent_id=agent_id,
            )
        except ValueError as exc:
            return {"error": str(exc)}

    @mcp.tool()
    @_serialized_tool
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
            return client.reload_context(
                session_id,
                snapshot_id=snapshot_id,
                requester_agent_id=agent_id,
            )
        except ValueError as exc:
            return {"error": str(exc)}

    return mcp


def main() -> None:  # pragma: no cover
    create_server().run()


if __name__ == "__main__":
    main()
