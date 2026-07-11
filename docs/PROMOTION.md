# Promotion / listing

Status of each channel, plus ready-to-use copy.

| Channel | Status |
|---|---|
| **awesome-mcp-servers** | ✅ PR opened — [punkpeye/awesome-mcp-servers#9876](https://github.com/punkpeye/awesome-mcp-servers/pull/9876) (Knowledge & Memory) |
| **modelcontextprotocol/servers** (official) | N/A — no longer accepts third-party PRs; it redirects to the MCP Registry |
| **MCP Registry** | ⚙️ Wired — `server.json` + `mcp-name:` marker + OIDC workflow; **auto-publishes on the next release** (see below) |
| Show HN / Reddit / X | ✍️ Drafts below — post when you're ready |

## MCP Registry (registry.modelcontextprotocol.io)

Publishing is fully set up and requires **no credentials from you**:

- `server.json` (name `io.github.yamantaka520/agent-memory-os`, PyPI package `agent-memory-os`).
- A `<!-- mcp-name: io.github.yamantaka520/agent-memory-os -->` marker in `README.md`
  (invisible on GitHub; PyPI preserves it in the rendered description, which is how
  the registry verifies package ownership).
- `.github/workflows/mcp-registry.yml` — on a published GitHub Release, it stamps the
  release version into `server.json`, authenticates via **GitHub OIDC** (the owner's
  repo auto-verifies the `io.github.yamantaka520/*` namespace), and publishes.

**Why it isn't live yet:** the registry checks the marker in the *published PyPI
description*, and 1.0.1 predates the marker (PyPI descriptions are frozen per
version). It will publish automatically on the next release (`vX.Y.Z`), or you can
run the **Publish to MCP Registry** workflow manually once a marked version is on
PyPI. The registry is in preview (data may reset before GA).

---

Below: ready-to-use copy for the remaining channels. **The third-party PRs/posts
are for a maintainer to submit** — they publish on external properties.

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
