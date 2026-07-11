# Agent Memory OS — User Guide

Complete reference for v0.9.x. For a five-minute start, see the
[README](../README.md); for integration recipes, see
[docs/integrations/](integrations/claude-code.md).

---

## 1. Concepts

| Concept | What it is |
|---|---|
| **Memory** | One durable fact/preference/procedure/decision/warning/note, owned by an agent, with `scope`, `visibility`, `importance`, `confidence`, decay policy, optional expiry. |
| **Owner & visibility (ACL)** | `visibility: []` = owner-only (private). `["global"]` = everyone. `["agent:<id>"]` = one agent. `["team:<id>"]` = a team/project. ACL is a **hard gate** applied before ranking on every read path. |
| **Agent** | A registered identity (`kind`: claude-code / codex / openclaw / hermes / custom) with team memberships. Team members automatically see `team:<id>` memories. |
| **Team = project** | A team id doubles as a project id. One agent may belong to many teams (multi-project). |
| **Links & resonance** | Authoritative association edges (`related_to`, `caused_by`, `supersedes`, `derived_from`, `co_recalled`). Search expands through them: related memories surface even without keyword overlap, ACL-safe. |
| **Reinforcement** | Helpful co-recall strengthens memories and links (Hebbian); `helpful=False` weakens them and speeds forgetting. |
| **Decay & retention** | Soft freshness decay by half-life (tuned by feedback telemetry); hard expiry; retention archives expired/idle memories into a restorable cold archive. |
| **Context pack / orchestration** | Token-budgeted prompt-ready recall. `orchestrate_context` splits the budget into session / bedrock / warnings / procedures / task buckets with proactive recall and session dedup. |
| **Federation** | Deterministic memory merging across hosts: file bundles, peer HTTP endpoints, or an auto-converging multi-peer mesh. |

**Design invariants** (see [SPEC.md](../SPEC.md)): SQLite is the single source
of truth; FTS/vector indexes are disposable; candidate providers return ids
only and every candidate rejoins SQLite behind the ACL/expiry hard gates.

---

## 2. Installation & setup

```bash
pip install 'agent-memory-os[full]'   # core + Web console + MCP + turbovec
agent-memory doctor                   # verify FTS5/extras (--install to fix)
agent-memory token create             # protect the Web API (stored mode 600)
agent-memory service install          # start at login: launchd/systemd/schtasks
```

Everything lives under one home (default `~/.agent-memory`, override with
`--home` or `AGENT_MEMORY_HOME`):

| File | Purpose |
|---|---|
| `memories.db` | The database (memories, links, agents, peers, archive…). Keep on local disk, not NFS/SMB. |
| `web_token` | Web API bearer token (`agent-memory token …`). |
| `agents.toml` | Declarative fleet config (see §5). |
| `logs/web.log` | Service logs. |

---

## 3. CLI reference (`agent-memory`)

Global flag: `--home <dir>`.

| Command | Purpose |
|---|---|
| `add <content> [--owner --scope --type --tag --confidence --importance]` | Store a memory. |
| `search <query> [--owner --scope --limit --json]` | Search (admin view; use the SDK/API for requester-gated recall). |
| `pack <query> [--max-tokens]` | Prompt-ready context pack. |
| `stats` | Database statistics. |
| `check` | SQLite + FTS + link-graph integrity, schema version. |
| `doctor [--install]` | Dependency/FTS5/token/agents.toml health; auto-install extras. |
| `token create\|show\|rotate\|disable` | Web API bearer token. |
| `service install\|uninstall\|start\|stop\|status [--host --port --dry-run]` | Native login service. |
| `backup <dest>` / `restore <src> [--force]` | WAL-safe online backup / restore. |
| `retention [--half-lives N]` | Archive expired (+ optionally idle ≥N half-lives); rotates session snapshots; retunes decay from feedback. `--half-lives 0` = expired only. |
| `peers add\|remove\|list [url] [--peer-token] [--policy shared\|full\|team:<id>] [--name <n>]` | Federation peer registry; `--policy` scopes what syncs to the peer, `--name` labels it (auto-fetched if omitted). |
| `node [--set-name <n>] [--set-host <h>] [--set-port <p>]` | Show or set this instance's sync identity and Web UI host/port (`<home>/instance.toml`). |
| `team list\|create\|delete\|add-member\|remove-member [id] [agent] [--name]` | Manage teams and their node members. |
| `project list\|create\|delete\|add-member\|remove-member [id] [agent] [--team] [--name]` | Manage projects under a team (members ⊆ team). |
| `maintenance scan\|orphans [--delete]\|reindex\|vacuum` | Ops: health scan, clean orphan memories (scoped to an empty group), rebuild the index, reclaim disk. |
| `update [--check] [--yes]` | Detect host/Docker deployment, check PyPI, and upgrade (pip) or print the `docker pull` steps. |
| `sync export <file> [--since --team]` | Write a bundle (optionally one project's memory). |
| `sync import <file>` | Merge a bundle (last-writer-wins / strongest-wins). |
| `sync pull\|push <peer-url> [--peer-token]` | One peer over HTTP. |
| `sync auto` | Converge with every registered peer. |
| `import-hermes --profile --profile-home` | Import Hermes `MEMORY.md`/`USER.md` (idempotent). |
| `golden-recall --cases <file>` | Recall-quality evaluation gate. |
| `shadow-summary --log <jsonl>` | Shadow-mode evidence summary. |

---

## 4. Web console & HTTP API

```bash
agent-memory-web --host 127.0.0.1 --port 8000 [--token …]
```

Console tabs: **Dashboard** (stats, activity, resonance health) · **Search** ·
**Browse** (filters, in-place edit) · **Graph** (interactive link graph) ·
**Agents** (fleet management) · **Add memory** · **Tools** (context pack,
orchestrator, links, consolidate, retention & archive, federation, danger
zone). UI languages: English, 繁體中文, 简体中文, 日本語, 한국어.

Requests without `requester_agent_id` run in **admin view**; bind to
localhost or require the bearer token. All `/api/` routes honor the token
gate when one is configured.

| Endpoint | Purpose |
|---|---|
| `GET /health`, `GET /api/stats`, `GET /api/dashboard`, `GET /api/integrity` | Health & metrics. |
| `GET/POST /api/memories`, `GET/PATCH/DELETE /api/memories/{id}` | CRUD + recency browse (`?scope=&type=&owner=&requester_agent_id=`). |
| `GET /api/search`, `GET /api/context-pack`, `GET /api/orchestrate` | Recall (requester-gated; orchestrate supports `session_id`, `max_tokens`). |
| `POST /api/links`, `GET /api/memories/{id}/links`, `GET /api/graph` | Associations (graph is requester-gated). |
| `POST /api/recall` | Helpful/misleading feedback (`requester_agent_id` restricts effect to visible memories). |
| `POST /api/memories/{id}/share\|revoke`, `GET /api/memories/{id}/audit` | Owner-only sharing / de-identified copies / audit trail. |
| `POST /api/consolidate`, `POST /api/retention`, `GET /api/archive`, `POST /api/archive/{id}/restore` | Hygiene & lifecycle. |
| `GET/POST/DELETE /api/agents[…]` | Agent registry. |
| `GET/POST/DELETE /api/peers`, `POST /api/sync/run`, `GET /api/sync/export`, `POST /api/sync/import` | Federation. |
| `DELETE /api/owners/{owner}/memories?confirm=<owner>` | Forget an agent entirely (double confirmation). |

---

## 5. Multi-agent projects

Register the fleet — console **Agents** tab, `POST /api/agents`, or as code:

```toml
# ~/.agent-memory/agents.toml   (re-applied on every open; file-authoritative)
[agents.cc-main]
kind = "claude-code"
teams = ["apollo", "shared-infra"]

[agents.hermes-neo]
kind = "hermes"
teams = ["apollo", "ops"]
```

Give each MCP server its identity:

```json
"env": { "AGENT_MEMORY_HOME": "~/.agent-memory", "AGENT_MEMORY_AGENT_ID": "cc-main" }
```

Then:
- writes default to that agent as owner;
- recalls carry its identity **and all of its teams** — `team:apollo`
  memories are visible to every apollo member with no extra wiring;
- private (`visibility: []`) memories stay private inside the fleet;
- owners can `share`/`revoke` (optionally de-identified) with full audit.

MCP tools (11): `memory_add`, `memory_search`, `memory_context_pack`,
`memory_orchestrate_context`, `memory_link`, `memory_update`,
`memory_recall_feedback`, `memory_consolidate`, `memory_offload_context`,
`memory_reload_context`, `memory_snapshot_diff`.

---

## 6. Federation & project sync

```bash
# each host: register the others (their web token authenticates you)
# --policy controls what leaves for this peer:
agent-memory peers add http://host-b:8000 --peer-token <b-token>            # 'shared' (default)
agent-memory peers add http://my-laptop:8000 --peer-token <t> --policy full # own trusted node
agent-memory peers add http://team-hub:8000 --peer-token <t> --policy team:apollo
agent-memory sync auto            # pull + push with every peer

# ship one project's memory as a file
agent-memory sync export apollo.jsonl --team apollo
```

**Peer policy** decides what a peer receives: `shared` (default — everything
except private `visibility=[]` memories), `full` (the whole store *including
private* — use only for your own trusted replica nodes), or `team:<id>` (one
project). Private memories never leave under `shared`/`team`, and the HTTP
`/api/sync/export` a peer pulls is always `shared`-scoped — full private
replication travels only over the push leg between your own `full` nodes.

### Multiple instances on one machine

Each instance is a separate `--home`. Give each a name and let the console pick
a free port:

```bash
agent-memory --home ~/mem-a node --set-name mizuki-laptop
agent-memory --home ~/mem-b node --set-name codex-box
agent-memory-web --home ~/mem-a          # binds 8000
agent-memory-web --home ~/mem-b          # 8000 taken → auto-binds 8001
```

Settings live in `<home>/instance.toml`:

```toml
[instance]
node_name = "mizuki-laptop"   # shown to peers during sync
host = "127.0.0.1"
port = 8000                   # taken? the launcher advances to a free port
```

`--port` overrides the file; `--strict-port` fails instead of advancing. When
you register a peer, its name is auto-fetched from `GET /api/node` (or set it
with `peers add --name`), so peer lists and sync results read
`mizuki-laptop · http://host:8000` instead of a bare URL.

### Teams & projects

A **team** is a set of node members. A team can hold multiple **projects**, and
each project's members are a **subset** of the team's members. Team memory
(`visibility: ["team:<id>"]`) reaches every team member; project memory
(`visibility: ["project:<id>"]`) reaches only that project's members.

```bash
agent-memory team create apollo --name Apollo
agent-memory team add-member apollo alice
agent-memory team add-member apollo bob
agent-memory project create apollo-web --team apollo --name "Apollo Web"
agent-memory project add-member apollo-web alice     # must already be on the team
agent-memory team list ; agent-memory project list --team apollo
```

Or manage it visually in the console's **Teams** tab (create a team → pick node
members; create a project under it → pick members from the team). Invariants are
enforced everywhere: a project member must be a team member; leaving a team
removes the agent from that team's projects; deleting a team removes its
projects.

Write scoped memory and sync it correctly:

```python
client.add("apollo-wide runbook", owner="neo", visibility=["team:apollo"])
client.add("apollo-web deploy key location", owner="neo", visibility=["project:apollo-web"])
# a peer that only replicates one project's shared memory:
agent-memory peers add http://web-box:8000 --peer-token <t> --policy project:apollo-web
```

The `project:apollo-web` peer bundle carries only that project's shared
memories (and its members' profiles), so project memory never reaches a node
whose agents aren't project members.

Merge rules (identical for files, HTTP, and mesh): memories & profiles —
last-writer-wins on normalized `updated_at` with a content tie-break so
same-second edits converge; links — strongest weight / highest activation /
latest activation. **Deletions propagate** via tombstones (a purged/deleted
memory will not resurrect from a peer). Imports from a non-`full` peer record
`source.synced_from` and cannot impersonate your local agents. Unreachable
peers fail individually. Pair `service install` with a cron/timer entry running
`sync auto` for a continuously converging federation.

---

## 7. SDK quick reference

```python
from agent_memory_os import MemoryClient, RecallProfile

client = MemoryClient(home="~/.agent-memory", semantic="auto")

m = client.add("…", owner="neo", type="procedure", visibility=["team:apollo"],
               auto_link=True)
hits = client.search("…", requester_agent_id="neo")
pack = client.context_pack("…", requester_agent_id="neo", auto_reinforce=True)
ctx  = client.orchestrate_context("deploy staging", session_id="s1",
                                  requester_agent_id="neo", max_tokens=2000)

client.link(a.id, b.id, relation="caused_by", weight=0.8)
client.record_recall([a.id, b.id])            # helpful=False to weaken
client.save_profile(RecallProfile(agent_id="neo",
                                  type_weights={"procedure": 1.5}))
client.consolidate(derive_links=True)          # or link_extractor=<LLM fn>
client.run_retention(); client.integrity_check()
client.share_memory(m.id, actor="neo", to_team="apollo", deidentify=True)
client.offload_context({...}, session_id="s1"); client.reload_context("s1")
client.snapshot_diff("s1")
client.export_bundle("out.jsonl", team="apollo"); client.import_bundle("in.jsonl")
```

For LLM-backed link extraction:
`agent_memory_os.extractors.make_llm_link_extractor(complete_fn)`.

---

## 8. Operations checklist

- **Daily**: nothing — the service self-restarts; auto semantic index
  self-syncs; feedback keeps tuning forgetting.
- **Periodic** (cron/timer): `agent-memory retention && agent-memory sync auto`
  and `agent-memory backup ~/backups/memories-$(date +%F).db`.
- **When suspicious**: `agent-memory check`; repair FTS drift with the SDK's
  `rebuild_indexes()` (indexes are disposable, the database is the truth).
- **Upgrades**: `agent-memory update` (since v0.14.0) — reports current vs
  PyPI latest, detects host-vs-Docker deployment, upgrades via pip after
  confirmation (`--yes` to skip, `--check` to only report), then handles the
  part a pip upgrade can never do: **processes that are already running keep
  the OLD code**. The tool restarts the web console for you (via the installed
  service, or by relaunching the process — the auth token persists, no
  re-login; `--no-restart` opts out) and lists MCP servers that need their
  host app (e.g. Claude Code) restarted — it never kills those itself.
  `update --check` also flags processes that started before the current
  install landed, i.e. "disk is new, memory is stale".
  - The database self-migrates forward on next open (schema version shown by
    `check`); take a backup first if you may need to roll back the package.
  - Installs older than v0.14.0 predate this command — the first hop is a
    manual `pip install -U 'agent-memory-os[full]'`.
  - In Docker, `update` prints the image-pull path instead (a container can't
    pip-upgrade itself): `docker pull` the new tag and recreate; `/data`
    persists.
