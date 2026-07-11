# Promotion / listing drafts

Ready-to-submit copy for getting AgentMemoryOS discovered. **These are drafts for
a maintainer to submit** — they involve opening PRs / posts on third-party
properties, so they are intentionally not automated.

## awesome-mcp-servers (punkpeye/awesome-mcp-servers)

Fork the repo, add one bullet under the most fitting category (e.g. **Knowledge
& Memory**), keep the list's alphabetical/format conventions:

```markdown
- [AgentMemoryOS](https://github.com/yamantaka520/Agent-Memory-OS) 🐍 🏠 - Local-first memory engine for AI-agent teams: private/team/project ACL, associative recall, and federated sync across nodes. One SQLite file, no LLM required.
```

(Legend per that repo: 🐍 = Python, 🏠 = local service. Check the current legend before submitting.)

## modelcontextprotocol/servers (community servers list)

The official servers repo lists community servers in `README.md`. Add, alphabetically:

```markdown
- **[AgentMemoryOS](https://github.com/yamantaka520/Agent-Memory-OS)** - Local-first, team-scoped memory for agents (ACL, resonance recall, federation) exposed as MCP tools.
```

Follow their CONTRIBUTING (server must be installable and documented — ours is:
`pip install 'agent-memory-os[mcp]'` then `python -m agent_memory_os.mcp_server`).

## MCP registry (registry.modelcontextprotocol.io), if publishing

If you want a formal registry entry, follow the registry's publish flow. Suggested
metadata:

- **name**: `io.github.yamantaka520/agent-memory-os` (or the namespace you own)
- **description**: Local-first memory engine for AI-agent teams — ACL, resonance recall, federated sync.
- **install**: `pip install 'agent-memory-os[mcp]'`
- **command**: `python -m agent_memory_os.mcp_server`
- **env**: `AGENT_MEMORY_AGENT_ID` (per-agent identity), `AGENT_MEMORY_HOME`

## Short blurbs (Show HN / Reddit r/LocalLLaMA / X)

> **AgentMemoryOS** — a local-first memory engine for *teams* of AI agents. One
> SQLite file, no LLM required. Private/team/project memories behind a hard ACL,
> associative recall, and federated sync where revocation actually propagates.
> MCP server + web console included. Apache-2.0.
> https://github.com/yamantaka520/Agent-Memory-OS

Tips: lead with the differentiator (local-first + team ACL + federation, vs
hosted/LLM-driven single-user tools), link the README (it has the badges,
comparison table, and the console GIF), and be around to answer questions.
