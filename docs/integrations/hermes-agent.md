# Using AgentMemoryOS with Hermes Agent

AgentMemoryOS ships a native **memory-provider plugin** for
[NousResearch Hermes Agent](https://github.com/NousResearch/hermes-agent)
(v0.18+). Installed in the Hermes environment, it plugs into Hermes's
`MemoryProvider` interface: relevant memories are recalled into context
automatically every turn, durable facts are saved through `amos_*` tools, and
Hermes's built-in MEMORY.md writes are mirrored into the store.

Why this instead of a cloud memory provider? **No API key, no LLM, no
network** — recall is local SQLite — and every write carries the visibility
ACL, so multiple Hermes profiles (and Claude Code / Codex over MCP) share one
store with private/team/project boundaries enforced.

## 1. Install & enable (three steps)

```bash
# 1. Install into the Hermes environment (same Python that runs `hermes`)
pip install agent-memory-os

# 2. Register the provider with Hermes (writes a shim into
#    $HERMES_HOME/plugins/agent-memory-os/ so `hermes memory` can see it)
agent-memory hermes install        # --hermes-home for non-default profiles

# 3. Pick it in the interactive wizard (or pass the name directly)
hermes memory setup agent-memory-os
hermes memory status               # verify: provider agent-memory-os active
```

> Why step 2? `hermes memory setup|status` discovers providers from plugin
> *directories* only — a pip install alone is invisible to the picker. The
> shim is a two-file loader that re-exports the provider from the installed
> package, so `pip install -U agent-memory-os` keeps upgrading the real
> implementation; re-run `agent-memory hermes install` only to refresh the
> version stamp. `agent-memory hermes uninstall` removes it.

The wizard (`hermes memory setup`) walks through the provider's config
(all non-secret, stored in `$HERMES_HOME/agent-memory-os.json`):

| key | default | meaning |
|---|---|---|
| `home` | `~/.agent-memory` | store location — point profiles/agents at the same home to share team memory |
| `agent_id` | `hermes-<profile>` | ACL identity for this profile's reads/writes |
| `share_default` | `private` | ACL when `amos_add` omits `share` |
| `mirror_builtin` | `true` | mirror built-in MEMORY.md/USER.md writes (idempotent) |
| `capture_delegations` | `true` | store subagent task/result pairs as episodic notes |

## 2. What the agent gets

- **Automatic recall**: each turn, an ACL-filtered context pack for the user's
  message is injected (Hermes `prefetch`), so the model doesn't have to
  remember to search.
- **Tools**: `amos_search` (keyword + associative recall), `amos_add`
  (with `share: private|team|project|agent:<id>|global`), `amos_share`
  (owner-only re-sharing; propagates over federation sync).
- **Passive capture**: built-in memory writes are mirrored (dedup by content
  hash); completed subagent delegations are stored as low-importance notes
  that decay unless they prove useful.
- **Safety**: cron/subagent contexts are read-only; hook failures degrade to
  "no memory this turn", never a broken agent loop; `hermes backup` picks up
  the store via `backup_paths()`.

Profiles map to identities automatically: profile `bastet` reads/writes as
`hermes-bastet`. Put both profiles' identities in one AgentMemoryOS team
(`agent-memory teams add ...`) and `share: team` memories flow between them —
and to any other agent (Claude Code, Codex) attached to the same home.

## 3. Import existing Hermes memory

Bring each profile's historical `MEMORY.md` / `USER.md` into the store
(idempotent — safe to re-run):

```bash
agent-memory import-hermes \
  --profile mizuki \
  --profile-home ~/.hermes/profiles/mizuki \
  --json
```

Each profile becomes an `owner`, so requester-aware ACL maps directly onto
Hermes profile boundaries.

## 4. Shadow mode & activation gates (optional, for production fleets)

For governed rollouts, run AgentMemoryOS **beside** the incumbent memory path
first: log recall comparisons without injecting, then flip `memory.provider`
once the gates pass (zero ACL leakage in shadow evidence, importer
idempotency, golden recall at target — see `docs/hermes-activation-gates.md`).

```bash
agent-memory shadow-summary --log agent_memory_os_shadow.jsonl --json
agent-memory golden-recall --cases golden_queries.json --json
```

## 5. Per-profile personas

Give each profile a recall profile so retrieval matches its role:

```python
from agent_memory_os import MemoryClient, RecallProfile

client = MemoryClient()
client.save_profile(RecallProfile(agent_id="hermes-mizuki",
                                  type_weights={"preference": 1.4, "note": 1.1}))
client.save_profile(RecallProfile(agent_id="hermes-neo",
                                  type_weights={"procedure": 1.5, "decision": 1.3}))
```

## Alternative: MCP instead of the plugin

Hermes also speaks MCP. If you prefer explicit tool calls without automatic
recall/capture, register the MCP server in Hermes's MCP config instead:

```bash
uvx --from "agent-memory-os[mcp]" agent-memory-mcp
```

The plugin and MCP server share the same store and ACL — you can even run the
plugin in Hermes and MCP in Claude Code against one home.
