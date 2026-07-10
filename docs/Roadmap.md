# AgentMemoryOS Roadmap

Last updated: 2026-07-11

Governance rule: a milestone is "done" only when its features are merged,
tested, and evidenced in this repository. Production claims (canary
percentages, default-backend status, traffic switches) belong in
`PROJECT_STATUS.md` with evidence, never here.

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

## v0.4 — Dynamic context orchestration (design + prototypes)

Goal: the memory system decides *what enters the context window, when* —
not just what exists.

1. **Session working memory** — `ContextSnapshot` offload/reload (prototype
   shipped, exposed via MCP): agents park working state mid-session and
   resume across context-window resets; add snapshot retention and diffing.
2. **Budget-aware orchestration** — one call that splits a token budget
   across bedrock memories, task-relevant recall, resonance neighbors, and
   session snapshots, with per-bucket reserves (extends the v0.2.2
   arbitration allocator).
3. **Proactive recall** — type-aware triggers: procedures surface when a task
   type is detected, warnings surface before matching risky actions, not
   only on lexical/semantic query match.
4. **Mid-task recall loop** — MCP affordances for iterative deepening
   (initial pack → follow-up queries with dedup against what the agent
   already saw this session).
5. **Resonance maturation** — LLM-assisted triplet extraction at
   consolidation time replacing regex ERA; graph-quality metrics
   (hub distribution, orphan rate) on the dashboard.

## Later / research

- Cross-agent memory negotiation: explicit share/de-identify flows with audit
  trail (private → team without copy-paste)
- Federated multi-host sync with conflict resolution
- Forgetting curves tuned from recall-feedback telemetry
