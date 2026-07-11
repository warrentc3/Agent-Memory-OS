<p align="center">
  <img src="https://raw.githubusercontent.com/yamantaka520/Agent-Memory-OS/main/assets/logo-header.png" alt="Agent Memory OS" width="560">
</p>

A **local-first memory engine for AI agents** — single or multi-agent, with shared and private memories, associative recall, and context-budgeted retrieval. One SQLite file, zero required dependencies, Apache-2.0.

## Why

Agents need durable facts, preferences, procedures, and lessons — but prompt-injected memory blocks are small and overflow fast, and cloud memory platforms add latency, cost, and privacy tradeoffs. AgentMemoryOS separates long-term memory from the context window: memories live in a local database, and each prompt receives only the relevant, budgeted slice.

## Features

- **Local-first, zero-dependency core** — one SQLite file (FTS5), no server required. `pip install` and go.
- **Requester-aware ACL** — every agent profile has private, team, and global memories; visibility is a hard gate enforced before ranking, never a soft score.
- **Dynamic context packs** — token-budgeted, auditable memory selection per prompt (`context_pack_report()` explains every include/exclude decision).
- **Truth arbitration** — duplicate suppression, contradiction detection (`CONFLICT` markers), and reserved budget for core memories.
- **Associative recall (resonance)** — an authoritative `memory_links` graph lets related memories surface even when they share no query terms; traversal is ACL-safe (invisible nodes are untraversable).
- **Hebbian reinforcement** — memories recalled together grow stronger links (`record_recall`, or `auto_reinforce=True` on context packs); unhelpful recalls weaken links and confidence (`helpful=False`).
- **Per-agent recall profiles** — different agent personas weight memory types differently (an engineer leans on `procedure`, a companion on `preference`); profiles persist in the database and re-weight ranking only, never bypassing ACL.
- **Memory lifecycle** — exponential/linear decay, pinning, hard expiry, and a write-side `consolidate()` pass that merges duplicates and synthesizes strongly co-recalled clusters into concept memories.
- **Optional sidecars** — semantic vector candidates (turbovec), MCP server, and a FastAPI Web UI, all behind extras; every candidate rejoins SQLite and passes hard gates before use.

## Install

```bash
pip install 'agent-memory-os[full]'    # recommended: everything (Web UI, MCP, turbovec)
```

Or pick pieces: `agent-memory-os` (core, zero dependencies), `[api]` (Web UI), `[mcp]` (MCP server), `[semantic]` (turbovec vector recall).

**Docker:** `docker run -p 8000:8000 -v amos-data:/data yamantaka520/agent-memory-os` (prebuilt, multi-arch) or `docker compose up -d`. Console at http://localhost:8000, memories persist in a volume. See the [Docker guide](docs/DOCKER.md) (Docker Hub image + a two-node sync mesh).

Requires Python 3.11+ with SQLite FTS5 (included in standard CPython builds).

After installing, run two commands:

```bash
agent-memory doctor          # verifies FTS5, turbovec, and the other extras
                             # (add --install to auto-install anything missing)
agent-memory token create    # protects the Web UI API with a bearer token
```

The token is stored at `<home>/web_token` (mode 600); `agent-memory-web` picks
it up automatically and the console prompts for it on first use. Manage it
later with `agent-memory token show|rotate|disable`.

## Quickstart

```python
from agent_memory_os import MemoryClient, RecallProfile

client = MemoryClient(home="~/.agent-memory")

# Write memories with ownership and visibility
client.add("User prefers dark mode.", owner="mizuki", type="preference",
           visibility=[])                      # private to owner
client.add("Deploy target is port 8000.", owner="neo", type="environment",
           visibility=["global"])              # visible to every agent

# Requester-aware search: each agent sees only what it may see
hits = client.search("deploy port", requester_agent_id="neo")

# Token-budgeted context pack for the prompt, with reinforcement loop closed
pack = client.context_pack("deploy port", requester_agent_id="neo",
                           max_tokens=1200, auto_reinforce=True)

# Associate memories; linked memories resonate into future recalls
a = client.add("Staging deploy failed with database lock.", visibility=["global"])
b = client.add("Always snapshot before schema changes.", visibility=["global"])
client.link(a.id, b.id, relation="caused_by", weight=0.8)

# Persist an agent persona: soft ranking bias per memory type
client.save_profile(RecallProfile(agent_id="neo",
                                  type_weights={"procedure": 1.5, "note": 0.7}))

# Periodic hygiene: merge duplicates, synthesize concept memories
client.consolidate()
```

## Architecture

```text
query
  -> candidate providers (FTS5 | vector sidecar | resonance graph | fallback)
  -> merge/dedupe by stable memory_id
  -> rejoin authoritative rows from SQLite
  -> ACL hard gate -> expires_at hard gate
  -> scoring (relevance x importance x confidence x freshness x reinforcement)
  -> per-agent profile re-weighting (soft)
  -> truth arbitration + context budget allocation
```

Design invariants:

- The SQLite `memories` table is the single source of truth; FTS/vector indexes are disposable and rebuildable (`rebuild_indexes()`).
- Candidate providers return IDs and scores only — content is always re-read through SQLite behind the ACL and expiry hard gates.
- Association edges (`memory_links`) are authoritative data, survive index rebuilds, decay when unused, and never let an invisible memory bridge two visible ones.

See [SPEC.md](SPEC.md) for the full contract.

## Storage engines: SQLite + turbovec

AgentMemoryOS uses **two storage layers with strictly different authority**:

- **SQLite** (always on) is the single source of truth: memories, links,
  profiles, and the FTS5 lexical index all live in one `memories.db` file.
- **turbovec** (installed with `[full]` / `[semantic]`) is the semantic vector
  engine: an in-memory quantized index that recalls memories by meaning rather
  than keywords. It is deliberately **disposable** — it returns candidate
  `memory_id`s and scores only; every candidate rejoins SQLite and passes the
  ACL/expiry hard gates before its content can be used, and the index can be
  dropped and rebuilt at any time without touching the truth store.

Semantic recall works out of the box:

```python
client = MemoryClient(home="~/.agent-memory", semantic="auto")
```

`semantic="auto"` wires in a self-syncing turbovec index over a built-in
deterministic hashing embedder (no model downloads; typo- and
morphology-tolerant lexical vectors). The index rebuilds itself whenever the
memories table changes and degrades silently to lexical + resonance recall
when the backend isn't installed. For deeper semantics, plug any embedding
model into `TurbovecSemanticCandidateProvider.from_vectors(...)` with your
own `embed_query`. `agent-memory doctor` confirms the backend is importable.

## Memory lifecycle & retention

```bash
agent-memory retention               # archive expired + memories idle 4+ half-lives
agent-memory retention --half-lives 0   # expired only
agent-memory check                   # SQLite + FTS + link-graph integrity
```

Archived memories leave recall entirely but stay restorable (Web UI → Tools →
Retention & archive, or `POST /api/archive/{id}/restore`). Pinned and
authority-track memories are never archived by decay. Databases self-migrate
through a versioned, forward-only migration table (`agent-memory check`
reports the schema version).

## Backup & restore

```bash
agent-memory backup ~/backups/memories-$(date +%F).db   # online, WAL-safe
agent-memory restore ~/backups/memories-2026-07-11.db --force
```

Backups use SQLite's online backup API, so they are consistent even while
agents are writing. Disposable indexes rebuild automatically after a restore.

## Multi-agent projects

One project can mix **Claude Code, Codex, OpenClaw, and multiple Hermes
profiles** against a single store. Register each agent with its teams —
in the console's **Agents** tab or via API — and team members automatically
see `team:<project>` memories with no extra wiring:

```bash
curl -X POST localhost:8000/api/agents -H 'content-type: application/json' \
  -d '{"id": "cc-main", "kind": "claude-code", "teams": ["apollo"]}'
```

Or declare the whole fleet as code — `<home>/agents.toml` is re-applied
every time the store opens (file-listed agents are file-authoritative;
manually registered agents are untouched):

```toml
[agents.cc-main]
kind = "claude-code"
teams = ["apollo", "shared-infra"]   # multiple teams = multiple projects

[agents.hermes-neo]
kind = "hermes"
teams = ["apollo", "ops"]
```

Each MCP server declares its identity with `AGENT_MEMORY_AGENT_ID`, so
memories default to that agent as owner and every recall carries its team
ACL. Ship one project's shared memory to another host with
`agent-memory sync export apollo.jsonl --team apollo`.

## Federation (multi-host sync)

```bash
# one-time, on each host
agent-memory peers add http://other-host:8000 --peer-token <their token>

# converge with every registered peer (pull + push, deterministic merges)
agent-memory sync auto
```

Peers are stored per-home; `sync auto` (or the console's "Sync mesh now")
converges bidirectionally with each peer — last-writer-wins on memories and
profiles, strongest-wins on links — and unreachable peers fail individually,
never fatally. File bundles (`sync export/import`) cover air-gapped moves.
Pair with `agent-memory service install` and a cron/timer entry for
continuous mesh sync.

## Agent integrations

Step-by-step guides for wiring AgentMemoryOS into common agents — click a tile:

<p>
  <a href="docs/integrations/claude-code.md"><img src="assets/integrations/claude-code.svg" alt="Claude Code integration guide" height="56"></a>
  <a href="docs/integrations/codex.md"><img src="assets/integrations/codex.svg" alt="Codex integration guide" height="56"></a>
  <br>
  <a href="docs/integrations/openclaw.md"><img src="assets/integrations/openclaw.svg" alt="OpenClaw integration guide" height="56"></a>
  <a href="docs/integrations/hermes-agent.md"><img src="assets/integrations/hermes-agent.svg" alt="Hermes Agent integration guide" height="56"></a>
</p>

Any MCP-capable agent can use the same pattern: run
`python -m agent_memory_os.mcp_server` as a stdio MCP server pointing at a
shared `AGENT_MEMORY_HOME`.

## MCP server

```bash
pip install 'agent-memory-os[mcp]'
python -m agent_memory_os.mcp_server
```

Tools (11): `memory_add`, `memory_search`, `memory_context_pack`, `memory_orchestrate_context`, `memory_link`, `memory_update`, `memory_recall_feedback`, `memory_consolidate`, `memory_offload_context`, `memory_reload_context`, `memory_snapshot_diff`. Set `AGENT_MEMORY_AGENT_ID` so each agent acts under its own identity.

## Web UI

```bash
pip install 'agent-memory-os[api]'
agent-memory-web --host 127.0.0.1 --port 8000 --home ~/.agent-memory-web
```

The console speaks **English, 繁體中文, 简体中文, 日本語, and 한국어** — auto-detected from the browser, switchable in the header. It ships with a stats dashboard (scope/type/relation breakdowns, 14-day activity, most-recalled memories), search and recency browsing (memory cards with in-place editing, feedback, links, and delete actions), an interactive association-graph view, a context-pack preview with per-memory decisions, and add/link/consolidate tools — all driven by a global "acting as" identity.

Endpoints: health/stats/dashboard/integrity · memories CRUD + browse · search / context-pack / orchestrate · links + graph · recall feedback · share / revoke / audit · consolidate / retention / archive+restore · agents registry · peers + mesh sync · bundle export/import · owner purge. Full table in the [User Guide](docs/USER_GUIDE.md).

Search, browse, graph, recall feedback, and context-pack accept `requester_agent_id` and enforce the same ACL hard gates as the SDK. Requests without a requester run in unrestricted admin view — bind to localhost only, or require a bearer token on every API route with `--token <secret>` (or `AGENT_MEMORY_WEB_TOKEN`).

Note: keep the `--home` database on a local disk. Network filesystems (NFS/SMB) can fail SQLite FTS5 schema creation with `database is locked`.

### Run as a login service (macOS / Linux / Windows)

```bash
agent-memory service install [--host 127.0.0.1] [--port 8000]
agent-memory service status | start | stop | uninstall
```

`install` registers the console with the native service manager so it starts
automatically at login and restarts on failure — launchd LaunchAgent on
macOS, a systemd user unit on Linux, a Task Scheduler logon task on Windows.
No admin rights required; the service runs the exact Python environment it
was installed from, and logs to `<home>/logs/web.log`. On Linux, run
`loginctl enable-linger $USER` if it must start at boot without a login.
Add `--dry-run` to preview the actions. CI runs the full test suite on
Ubuntu, macOS, and Windows across Python 3.11–3.13.

## Development

```bash
pip install -e '.[dev]'
pytest
```

## Status

Alpha (`0.2.x`). The core contracts above are implemented and covered by the test suite; interfaces may still change before `1.0`. See [PROJECT_STATUS.md](PROJECT_STATUS.md) and [PROGRESS.md](PROGRESS.md) for the evidence-backed state of each feature.

## Documentation

- **[User Guide](docs/USER_GUIDE.md)** — concepts, full CLI / HTTP API / MCP references, multi-agent and federation walkthroughs, ops checklist
- **[Docker guide](docs/DOCKER.md)** — `docker`/`docker compose` startup, config via env, two-node sync mesh
- [SPEC](SPEC.md) — contracts and invariants, by milestone
- **[Validation Plan](docs/VALIDATION_PLAN.md)** & **[latest validation report](docs/reports/20260711-v0.13.0-validation-report.md)** — gate matrix, reproducible harness (`scripts/validation_run.py`), measured results
- **[Security & code review (v0.10.0)](docs/reviews/20260711-v0.10.0-review.md)** — six-angle audit, fixes applied, and the federation-hardening follow-ups
- [CHANGELOG](CHANGELOG.md) · [Roadmap](docs/ROADMAP.md) · [Integration guides](docs/integrations/claude-code.md)

## License

[Apache License 2.0](LICENSE)
