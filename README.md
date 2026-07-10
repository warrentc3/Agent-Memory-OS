# AgentMemoryOS

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
pip install agent-memory-os            # core (no dependencies)
pip install 'agent-memory-os[mcp]'     # + MCP server
pip install 'agent-memory-os[api]'     # + Web UI
pip install 'agent-memory-os[semantic]' # + vector candidate sidecar
```

Requires Python 3.11+ with SQLite FTS5 (included in standard CPython builds).

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

## MCP server

```bash
pip install 'agent-memory-os[mcp]'
python -m agent_memory_os.mcp_server
```

Tools: `memory_add`, `memory_search`, `memory_context_pack`, `memory_link`, `memory_recall_feedback`, `memory_consolidate`.

## Web UI

```bash
pip install 'agent-memory-os[api]'
agent-memory-web --host 127.0.0.1 --port 8000 --home ~/.agent-memory-web
```

The console ships with search and recency browsing (memory cards with feedback, links, and delete actions), an interactive association-graph view, a context-pack preview with per-memory decisions, and add/link/consolidate tools — all driven by a global "acting as" identity.

Endpoints: `GET /health`, `GET /api/stats`, `GET|POST /api/memories`, `GET|DELETE /api/memories/{id}`, `GET /api/memories/{id}/links`, `GET /api/graph`, `POST /api/links`, `POST /api/recall`, `POST /api/consolidate`, `GET /api/search`, `GET /api/context-pack`.

Search, browse, graph, recall feedback, and context-pack accept `requester_agent_id` and enforce the same ACL hard gates as the SDK. Requests without a requester run in unrestricted admin view — bind to localhost only, or require a bearer token on every API route with `--token <secret>` (or `AGENT_MEMORY_WEB_TOKEN`).

Note: keep the `--home` database on a local disk. Network filesystems (NFS/SMB) can fail SQLite FTS5 schema creation with `database is locked`.

## Development

```bash
pip install -e '.[dev]'
pytest
```

## Status

Pre-alpha (`0.1.x`). The core contracts above are implemented and covered by the test suite; interfaces may still change before `1.0`. See [PROJECT_STATUS.md](PROJECT_STATUS.md) and [PROGRESS.md](PROGRESS.md) for the evidence-backed state of each feature.

## License

[Apache License 2.0](LICENSE)
