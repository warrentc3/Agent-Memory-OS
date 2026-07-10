# AgentMemoryOS Roadmap

Last updated: 2026-07-11

Governance rules:

1. A milestone is "done" only when its features are merged, tested, and
   evidenced in this repository. Production claims (canary percentages,
   default-backend status, traffic switches) belong in `PROJECT_STATUS.md`
   with evidence, never here.
2. **Web console parity is part of Done**: every engine feature that changes
   what users can inspect or control (new memory fields, new operations, new
   retrieval behavior) ships with matching Web UI support in the same
   milestone — the console must never lag the engine.

## Shipped — v0.2.3 (current release)

- SQLite + FTS5 source of truth; requester-aware ACL and expiry hard gates
- Truth arbitration, context budget packs with auditable decisions
- Memory association layer: authoritative `memory_links`, resonance recall
  (ACL-safe traversal), link decay, hub damping, supersedes demotion
- Recall loop: Hebbian reinforcement, negative feedback, auto-reinforce packs
- Per-agent `RecallProfile` personas (persisted, auto-applied)
- Write-side consolidation (duplicate merge + concept synthesis)
- turbovec semantic candidate sidecar (validation-gated, disposable)
- Web console: dashboard, search/browse/edit, association graph, tools,
  bearer-token auth; MCP server (9 tools); token/doctor/backup CLI
- CI (3 Python versions) and Trusted-Publishing release workflow

## v0.3 — Robust persistent memory (in progress)

Goal: a memory you can trust with years of an agent's life.

1. **Durability operations** — `agent-memory backup/restore` (shipped),
   scheduled snapshot rotation, integrity check command
   (`PRAGMA integrity_check` + row-count/id invariants).
2. **Schema migrations** — versioned migration table and forward-only
   migration runner, replacing ad-hoc `ALTER TABLE` checks; downgrade
   verification stays a release gate.
3. **Embedding pipeline** — optional background indexer that keeps a turbovec
   index in sync with the memories table (pluggable embedder), so semantic
   recall works out of the box instead of requiring hand-wired vectors.
4. **Retention policies** — per-scope/type archival rules: expired and
   decayed-out memories move to a cold archive table (excluded from recall,
   restorable) instead of deletion-only lifecycle.
5. **Hermes activation evidence** — shadow comparison logs, golden recall at
   target, importer idempotency; gates in `PROJECT_STATUS.md`.

## v0.4 — Dynamic context orchestration (in progress)

Goal: the memory system decides *what enters the context window, when* —
not just what exists.

1. **Session working memory** — SHIPPED: `ContextSnapshot` offload/reload
   with MCP tools, snapshot rotation in retention (keep newest 5 per
   session), and `snapshot_diff()` / `memory_snapshot_diff` reporting what
   changed between the two most recent snapshots.
2. **Budget-aware orchestration** — SHIPPED: `orchestrate_context()` splits
   the token budget across session / bedrock / warnings / procedures / task
   buckets with surplus flowing to task recall; exposed via SDK, MCP
   (`memory_orchestrate_context`), `GET /api/orchestrate`, and the console.
3. **Proactive recall** — SHIPPED: warnings and procedures surface via
   dedicated buckets with importance-ranked top-up even when the task
   wording never matches them; task-type detection (risk / how-to terms)
   shifts bucket budgets and is reported as `emphasis`.
4. **Mid-task recall loop** — SHIPPED (first form): with a `session_id`,
   repeated orchestrate calls exclude memories already delivered this
   session (bedrock constants exempt), logged in `session_recall_log`.
5. **Resonance maturation** — LLM-assisted triplet extraction at
   consolidation time replacing regex ERA; graph-quality metrics
   (hub distribution, orphan rate) on the dashboard.

## v0.5 — Memory federation & adaptive forgetting (in progress)

1. **Cross-agent memory negotiation** — SHIPPED (first form): owner-only
   `share_memory` / `revoke_share` grants (agent or team), de-identified
   copies with the owner's name scrubbed, and a per-memory audit trail
   (`memory_audit`, migration 5). Console cards gain a Share action.
2. **Federated sync** — SHIPPED (first form): `agent-memory sync export /
   import` moves portable JSONL bundles between hosts with deterministic
   merge rules — last-writer-wins on memories/profiles, strongest-wins on
   links. Remaining: online peer-to-peer transport over the same rules.
3. **Telemetry-tuned forgetting** — SHIPPED (first form): helpful/unhelpful
   recall feedback is counted per memory (migration 6) and retention
   recomputes decay half-lives idempotently — proven-helpful memories forget
   slower (up to 4x base), misleading ones faster (down to 0.5x).

## Later / research
