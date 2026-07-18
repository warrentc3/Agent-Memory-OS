# Deployment topologies

AgentMemoryOS is designed around four deployment shapes. Identify yours, then
follow that recipe. Two concepts to keep straight everywhere:

- **Agent ID = identity.** Owns private memories, carries the ACL, belongs to
  teams. Stable; rename only via `agent-memory agent rename` (migrates
  ownership, `agent:<id>` grants, memberships, and profiles atomically).
- **Node name = display.** What peers see for an instance. Rename freely
  (`agent-memory node --set-name`, or WebUI → Tools → Rename node); peers
  refresh it automatically on their next sync.

After any install, run `agent-memory doctor` — it verifies FTS5/extras, warns
if the scripts directory is missing from PATH (`agent-memory path install`
fixes it), and reports other nodes it finds on the host.

## 1. One machine, one account, one agent

The default. Nothing to configure:

```bash
pip install 'agent-memory-os[full]'
agent-memory doctor && agent-memory token create
agent-memory service install        # console at login
```

The agent connects over MCP with `AGENT_MEMORY_AGENT_ID=<its id>`. Everything
lives in `~/.agent-memory`.

## 2. One machine, one account, many agents

Point every agent at the **same home** — one store, one ACL, shared teams:

- Each MCP server env sets its own `AGENT_MEMORY_AGENT_ID` (cc-main, codex-1,
  hermes-bastet, …) — identity comes from the env, never from tool arguments.
- Register agents + teams in the console's Agents/Teams tabs (the node's own
  default agent is pre-seeded on first run). Team members see `team:<id>`
  memory immediately; private stays private.
- No sync involved: it is one database.

## 3. One machine, many accounts (each with agents)

Each account runs its **own node** (own home, own console, own service —
per-account launchd/systemd units; on Windows tasks are auto-named
`agent-memory-web-<username>`). Separate accounts are separate trust domains;
sharing is explicit:

```bash
# each account, once:
agent-memory service install        # picks & persists a free port automatically

# discover and pair (consent on both sides):
agent-memory neighbors                        # account B sees account A's node
agent-memory team invite apollo               # on A → one-time code
agent-memory join <code> --url http://127.0.0.1:<A-port>   # on B
```

The pairing exchange wires sync-scoped tokens, team-scoped peers, the mesh
encryption key, and a first sync. `agent-memory status` shows the service,
console, and every peer's live state.

## 4. Many machines (any number of accounts/agents)

Same pairing flow, over the network instead of loopback:

- Use `https://` peer URLs (verified TLS), or set the shared mesh key
  (`agent-memory sync genkey` → same `AGENT_MEMORY_SYNC_KEY` everywhere) so
  bundle content stays encrypted even over plain HTTP.
- Scope every peer to the narrowest policy that works (`team:<id>` — the
  default the pairing flow sets), never `full` for machines you don't own.
- Schedule `agent-memory sync auto` (cron or the built-in service) for
  continuous convergence; memories, org structure, and revocations propagate.
- Keep the fleet on one version: `agent-memory update --team` triggers
  self-update on every peer whose console was started with
  `AGENT_MEMORY_ALLOW_TEAM_UPDATE=1` (explicit per-node opt-in; a sync token
  gains no other power from it). `agent-memory status` flags version drift.

## Quick matrix

| Topology | Stores | Sharing mechanism | Extra setup |
|---|---|---|---|
| 1 machine / 1 account / 1 agent | one | — | none |
| 1 machine / 1 account / N agents | **one** | same home + per-agent `AGENT_MEMORY_AGENT_ID` | register agents/teams |
| 1 machine / N accounts | one per account | `neighbors` → `team invite`/`join` (loopback) | per-account service; ports auto-assigned |
| N machines | one per node | `team invite`/`join` (network) + `sync auto` | TLS or mesh key; `update --team` opt-in |
