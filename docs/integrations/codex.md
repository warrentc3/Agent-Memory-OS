# Using AgentMemoryOS with Codex

Codex CLI supports MCP servers declared in `~/.codex/config.toml`.

## 1. Install

```bash
pip install 'agent-memory-os[full]'
agent-memory doctor
```

## 2. Register the MCP server

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.agent-memory]
command = "python"
args = ["-m", "agent_memory_os.mcp_server"]

[mcp_servers.agent-memory.env]
AGENT_MEMORY_HOME = "/Users/you/.agent-memory"
```

Restart Codex; the `memory_*` tools appear in its tool list.

## 3. Guide the model

Add a note to your `AGENTS.md` (or project instructions):

```markdown
## Memory
- Recall first: call memory_context_pack with the task summary before
  starting non-trivial work.
- Persist durable knowledge with memory_add; report helpful/misleading
  recalls with memory_recall_feedback.
```

## Notes

- Use one `AGENT_MEMORY_HOME` across your agents if you want shared team
  memory; per-agent privacy still holds through owner/visibility ACL.
- The same home can be inspected live with `agent-memory-web`.
