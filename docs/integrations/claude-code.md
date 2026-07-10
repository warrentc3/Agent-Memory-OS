# Using AgentMemoryOS with Claude Code

Claude Code speaks MCP natively, so the memory engine plugs in as a stdio MCP
server — no glue code required.

## 1. Install

```bash
pip install 'agent-memory-os[full]'
agent-memory doctor
```

## 2. Register the MCP server

Project-scoped (recommended — the whole team gets it via `.mcp.json`):

```bash
claude mcp add agent-memory --scope project \
  --env AGENT_MEMORY_HOME=$HOME/.agent-memory \
  --env AGENT_MEMORY_AGENT_ID=cc-main \
  -- python -m agent_memory_os.mcp_server
```

Or user-scoped (`--scope user`) to share one memory home across all projects.

Equivalent `.mcp.json` entry if you prefer editing the file directly:

```json
{
  "mcpServers": {
    "agent-memory": {
      "command": "python",
      "args": ["-m", "agent_memory_os.mcp_server"],
      "env": { "AGENT_MEMORY_HOME": "~/.agent-memory", "AGENT_MEMORY_AGENT_ID": "cc-main" }
    }
  }
}
```

## 3. Teach Claude when to use it

Add a short section to your `CLAUDE.md` so the model reaches for memory at the
right moments:

```markdown
## Memory
- At the start of a task, call `memory_context_pack` with a short description
  of the task to recall relevant facts, procedures, and warnings.
- When you learn a durable fact, preference, decision, or lesson, save it with
  `memory_add` (owner = this agent's id; use visibility ["global"] for
  team-wide knowledge, [] for private).
- When recalled memories were helpful or misleading, report it with
  `memory_recall_feedback` so ranking improves.
```

## 4. Available tools

`memory_add`, `memory_search`, `memory_context_pack`,
`memory_orchestrate_context`, `memory_link`, `memory_update`,
`memory_recall_feedback`, `memory_consolidate`, `memory_offload_context`,
`memory_reload_context`, `memory_snapshot_diff`.

## Tips

- Give each agent persona a stable `owner` id so private/team/global
  visibility boundaries mean something.
- Keep `AGENT_MEMORY_HOME` on a local disk (not NFS/SMB).
- Run the Web console (`agent-memory-web`) beside it to inspect what the
  agent remembers, browse the association graph, and prune.

## Agent identity (multi-agent projects)

Set `AGENT_MEMORY_AGENT_ID` in the MCP server env so this agent's reads and
writes carry its identity: memories default to it as owner, and searches
automatically include every team the agent belongs to (register agents and
teams in the Web console's **Agents** tab, or via `POST /api/agents`).
