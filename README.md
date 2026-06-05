# AgentMemoryOS

Local-first memory runtime for AI agents.

AgentMemoryOS is an experimental open-source memory layer inspired by the practical needs of long-running multi-agent teams: durable local memory, fast RAM cache, hybrid retrieval, and context-budgeted recall so agents do not keep overfilling their prompt with stale facts.

## Goals

- **Local-first**: works offline with SQLite; no SaaS required.
- **Agent-neutral**: usable from Hermes, Claude Desktop, Codex-style agents, LangChain, AutoGen, CrewAI, and custom tools.
- **MCP-native**: expose memory tools through MCP so other agents can plug in.
- **Fast hot path**: RAM LRU cache for frequently recalled context packs and pinned facts.
- **Context-budget aware**: return a compact context pack instead of dumping every memory into the model context.
- **Truth-arbitrated**: protect authoritative core memories under noisy budget pressure, suppress duplicates, and mark contradictions.
- **Auditable**: every memory has scope, owner, type, timestamps, source, confidence, and importance.

## Current status

AgentMemoryOS is currently **Development / Validation only** for Hermes integration.

It is **not** approved as the default Hermes Agent memory backend. Use it in staging, shadow, or experimental mode until the production activation gates are complete.

Canonical activation gate document:

- [`docs/hermes-activation-gates.md`](docs/hermes-activation-gates.md)

## Current MVP

Implemented now:

- SQLite persistence.
- SQLite FTS5 keyword retrieval.
- Structured memory records.
- In-process LRU cache.
- Context pack builder with a hard token-ish budget, truth arbitration, selected/rejected decision metadata, duplicate suppression, and contradiction markers.
- Requester-aware ACL filtering for search and context packs.
- Expiration hard filter with recency/decay-aware effective scoring.
- v0.2.1 retrieval-safety contract: SQLite memories are the source of truth, while FTS5/future vector/fallback paths are disposable candidate providers merged by stable memory id.
- Python SDK.
- CLI commands: `add`, `search`, `pack`, `stats`.
- Optional MCP server scaffold.

Planned next:

- v0.2.1 refactor: candidate provider abstraction around the existing retrieval-safety baseline.
- v0.2.2 expansion: richer Truth Arbitration stress fixtures, reserved budget buckets, and stronger contradiction severity handling.
- Version-downgrade verification and migration/rollback proof before Hermes default-backend activation.
- Hermes provider integration in shadow mode first; production default activation requires the gates in `docs/hermes-activation-gates.md`.
- sqlite-vec / Qdrant hybrid vector search after the retrieval foundation is sealed.
- Deduplication and stale-memory consolidation.
- REST API.
- Import/export from Mem0.ai and Hermes `MEMORY.md` / `USER.md`.

## Quick start

```bash
PYTHONPATH=src python -m agent_memory_os.cli add "User prefers Traditional Chinese." --owner bastet-agent --scope user --type preference --tag language
PYTHONPATH=src python -m agent_memory_os.cli search "language preference" --owner bastet-agent
PYTHONPATH=src python -m agent_memory_os.cli pack "How should I answer this user?" --owner bastet-agent --max-tokens 500
PYTHONPATH=src python -m pytest -q
```

Default database path:

```text
~/.agent-memory/memories.db
```

Override with:

```bash
export AGENT_MEMORY_HOME=/path/to/memory-home
```

## Python SDK

```python
from agent_memory_os import MemoryClient

client = MemoryClient(home="/tmp/agent-memory")
client.add(
    content="User prefers timestamped filenames YYYYMMDD_HHMMSS.",
    owner="bastet-agent",
    scope="user",
    type="preference",
    tags=["filename", "preference"],
)

hits = client.search("filename convention", owner="bastet-agent", limit=5)
pack = client.context_pack("Create a report", owner="bastet-agent", max_tokens=300)
report = client.context_pack_report("Create a report", owner="bastet-agent", max_tokens=300)
for decision in report.decisions:
    print(decision.memory_id, decision.selected, decision.reason)
```

## Repository status

See:

- [`PROJECT_STATUS.md`](PROJECT_STATUS.md) for current implementation and verification status.
- [`SPEC.md`](SPEC.md) for the product/architecture specification.
- [`docs/HISTORY.md`](docs/HISTORY.md) for the full project journey, decisions, completed work, pending work, and code-level contracts.
- [`docs/hermes-activation-gates.md`](docs/hermes-activation-gates.md) for the Hermes non-default deployment decision, activation gates, shadow-mode rules, and evidence bundle requirements.
- [`docs/plans/20260605_114049-retrieval-foundation-v0.2.1.md`](docs/plans/20260605_114049-retrieval-foundation-v0.2.1.md) for the retrieval safety layer and no-data-loss contract.
- [`docs/plans/20260605_143442-version-downgrade-verification.md`](docs/plans/20260605_143442-version-downgrade-verification.md) for downgrade, migration, rollback, and compatibility verification planning.
- [`docs/stress-cases/case-01-noisy-truth.md`](docs/stress-cases/case-01-noisy-truth.md) for `[Mizuki/StressCase] Case 01: 喧囂中的真理`.

## AgentMemoryOS v0.3 Baseline

The public v0.3 baseline is documented by these canonical entry points:

- [AgentMemoryOS_README.md](docs/AgentMemoryOS_README.md) — public v0.3 overview and release baseline.
- [Shadow_Mode_Timeline.md](docs/Shadow_Mode_Timeline.md) — v0.3 → v0.4 shadow-mode validation timeline and go/no-go KPIs.
- [Memory_Resonance_Spec.md](docs/Memory_Resonance_Spec.md) — v0.4 ERA triplet / resonance index design.

Prototype implementation modules are available under `src/agent_memory_os/`:

- `memory_resonance.py` — embedded ERA triplet index and two-hop resonance expansion.
- `shadow_mode.py` — append-only legacy-vs-candidate recall comparison monitor.
