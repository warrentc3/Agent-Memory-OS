# MCP directory submissions — ready-to-paste field data

Reuse these fields across directories. Canonical repo casing:
**https://github.com/yamantaka520/Agent-Memory-OS**

## Common fields

- **Name:** Agent Memory OS
- **Slug / id:** agent-memory-os
- **Tagline (≤80):** Local-first memory engine for AI-agent teams
- **Short description (≤160):**
  Local-first memory engine for AI-agent teams: private/team/project ACL,
  associative recall, and federated sync across nodes. One SQLite file, no LLM
  required.
- **Categories / tags:** memory, knowledge, ai-agent, mcp, sqlite, local-first,
  search, multi-agent
- **Repo:** https://github.com/yamantaka520/Agent-Memory-OS
- **PyPI:** https://pypi.org/project/agent-memory-os/
- **Docker:** https://hub.docker.com/r/yamantaka520/agent-memory-os
- **License:** Apache-2.0
- **Transport:** stdio
- **Install (MCP):** `pip install "agent-memory-os[mcp]"`
- **Run (MCP stdio):** `python -m agent_memory_os.mcp_server`
  (zero-install: `uv run --with "agent-memory-os[mcp]" python -m agent_memory_os.mcp_server`)
- **Env vars:**
  - `AGENT_MEMORY_AGENT_ID` — this agent's identity (owner + recall ACL)
  - `AGENT_MEMORY_HOME` — data home dir (default `~/.agent-memory`)

## Client config snippet (for listings that show one)

```json
{
  "mcpServers": {
    "agent-memory": {
      "command": "uv",
      "args": ["run", "--with", "agent-memory-os[mcp]", "python", "-m", "agent_memory_os.mcp_server"],
      "env": { "AGENT_MEMORY_AGENT_ID": "my-agent" }
    }
  }
}
```

## Per-directory notes

### PulseMCP — https://www.pulsemcp.com/
Has a "Submit a server" flow + a newsletter. Paste the common fields above.
Their crawler also picks up repos; a manual submit speeds it up.

### mcp.so — https://mcp.so/
"Submit" form. Same fields. Good for SEO/long-tail search.

### Smithery — https://smithery.ai/  (config already in repo: smithery.yaml)
Log in with GitHub → Add Server → point at the repo. List as **local stdio**,
NOT a hosted/remote deployment (local-first). Requires the pushed smithery.yaml.

### Cline MCP Marketplace — https://github.com/cline/mcp-marketplace
Open an issue/PR per their template. Needs: repo URL, logo (use
assets/logo-icon-512.png), short description, and that it runs via stdio.

### Continue Hub / Cursor directory
Both have MCP directories tied to their editors; submit the same fields when you
want editor-ecosystem reach.

## Not-just-MCP awesome lists (open a PR to each)
- awesome-ai-agents
- awesome-agents
- awesome-local-first-software
- awesome-llmops

Entry line to reuse:
`- [Agent Memory OS](https://github.com/yamantaka520/Agent-Memory-OS) — Local-first memory engine for AI-agent teams: per-memory ACL, associative recall, federated sync. One SQLite file, no LLM required. (Apache-2.0)`
