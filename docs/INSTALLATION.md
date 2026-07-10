# Installation & Deployment

Current for v0.9.x. Requirements: Python 3.11+ with SQLite FTS5 (standard
CPython builds include it); Linux, macOS, or Windows.

## Install

```bash
pip install 'agent-memory-os[full]'   # Web console + MCP + turbovec
agent-memory doctor                   # verify (add --install to auto-fix)
```

Minimal alternatives: `agent-memory-os` (zero-dependency core), `[api]`,
`[mcp]`, `[semantic]`.

## First-run setup

```bash
agent-memory token create      # bearer token for the Web API (mode 600)
agent-memory service install   # start at login; launchd/systemd/schtasks
```

Console: http://127.0.0.1:8000/ — bind localhost, or rely on the token.
Keep the memory home (default `~/.agent-memory`) on a **local disk**;
NFS/SMB homes can fail FTS5 with `database is locked`.

## Declare your fleet (optional, recommended for multi-agent)

`~/.agent-memory/agents.toml`:

```toml
[agents.cc-main]
kind = "claude-code"
teams = ["apollo"]
```

Then set `AGENT_MEMORY_AGENT_ID` in each agent's MCP config — see the
[integration guides](integrations/claude-code.md).

## Operations

```bash
agent-memory backup ~/backups/memories-$(date +%F).db
agent-memory retention          # archive expired / deeply idle; tune decay
agent-memory check              # integrity + schema version
agent-memory sync auto          # converge the federation mesh
```

Upgrades: `pip install -U 'agent-memory-os[full]'` — databases self-migrate
forward. Full reference: [User Guide](USER_GUIDE.md).
