# Changelog — Agent Memory OS

All notable changes, newest first. Releases are published to
[PyPI](https://pypi.org/project/agent-memory-os/) via Trusted Publishing and
tagged on GitHub/GitLab.

## [0.10.1] — 2026-07-11

Security & correctness fixes from the full v0.10.0 review
(`docs/reviews/20260711-v0.10.0-review.md`).

- **MCP identity escape (security)**: `memory_orchestrate_context` and
  `memory_recall_feedback` no longer accept a caller-supplied
  `requester_agent_id` that overrode the env-pinned agent identity.
- **Web ACL gate**: `GET /api/memories/{id}` and `/links` now enforce the
  same visibility gate as `/api/search` (new `get_visible()`).
- **Right-to-forget**: `purge_owner` now also destroys cold-archive rows and
  the recall/audit logs, so purged content is not restorable.
- `resonance_search` no longer raises on a found seed; LLM link extractor
  survives a non-string reply; `agents.toml` rejects a string `teams` and
  validates the whole file before applying (no half-registered fleet).
- share/revoke no longer reset the freshness/decay clock; the auto semantic
  index rebuilds after an in-place same-second edit; `rotate_snapshots` never
  archives pinned snapshots; `import_bundle` rolls back on a corrupt line;
  bundle temp files are written UTF-8 (Windows non-ASCII).

## [0.10.0] — 2026-07-11

- **Validation milestone**: `docs/VALIDATION_PLAN.md` (G1 security / G2
  functional / G3 performance / G4 deployment gate matrix) supersedes the
  v0.2.x-era Hermes shadow gates; reproducible harness
  `scripts/validation_run.py` generates professional reports into
  `docs/reports/` and runs in CI (`--quick`).
- First full run: **PASS** — 12/12 security, 10/10 functional, 13/13
  performance on a 5k-memory fleet corpus (search p95 11.9 ms,
  orchestrate p95 20.4 ms, writes 8.3k/s).
- **Ranking fix found by validation**: the query-independent authority
  (bedrock) track could crowd resonance results out of the result window
  at scale; its share is now capped at limit/4.
- Documentation sweep: new `docs/USER_GUIDE.md` (full CLI/API/MCP
  reference), CHANGELOG as release history, SPEC current through v0.9,
  INSTALLATION rewritten, status docs refreshed.

## [0.9.0] — 2026-07-11

- **Fleet as code**: `<home>/agents.toml` declares the whole multi-agent,
  multi-project fleet; re-applied on every store open (file-authoritative
  for listed agents, manual registrations untouched).
- **Console i18n**: English, 繁體中文, 简体中文, 日本語, 한국어 — auto-detected,
  live-switchable, persisted.

## [0.8.0] — 2026-07-11

- **Agent registry** (migration 8): agents are first-class entities (id,
  kind, teams, last-seen) with a console Agents tab and `/api/agents`.
- **Team auto-resolution ACL**: registered team memberships resolve inside
  the ACL hard gate — `team:<project>` memory visible to every member with
  zero per-call wiring.
- **Per-agent MCP identity**: `AGENT_MEMORY_AGENT_ID` gives each connected
  agent its own owner/requester identity.
- **Project-scoped sync**: `sync export --team <project>`.

## [0.7.0] — 2026-07-10

- **Mesh federation** (migration 7): peer registry, `agent-memory peers`,
  `sync auto` bidirectional convergence with per-peer failure isolation,
  console peer management.
- **LLM extraction plumbing**: `make_llm_link_extractor(fn)` wraps any
  completion callable into a consolidation link extractor with defensive
  parsing.

## [0.6.0] — 2026-07-10

- **Memory negotiation** (migration 5): owner-only `share_memory` /
  `revoke_share`, de-identified copies, per-memory audit trail.
- **Federated sync**: portable JSONL bundles + peer HTTP transport
  (`/api/sync/export|import`, `sync pull/push`) with deterministic merges.
- **Adaptive forgetting** (migration 6): helpful/unhelpful feedback tunes
  decay half-lives (`base × clamp(√((1+h)/(1+u)), 0.5, 4)`).

## [0.5.0] — 2026-07-10

- **Cross-OS login service**: `agent-memory service install` — launchd /
  systemd user unit / Task Scheduler; per-user, auto-restart, `--dry-run`.
- **Three-OS CI**: Ubuntu, macOS, Windows × Python 3.11–3.13.

## [0.4.0] — 2026-07-10

- **Dynamic context orchestration**: `orchestrate_context()` splits the
  token budget across session / bedrock / warnings / procedures / task
  buckets; proactive recall; task-type emphasis; session iterative
  deepening (migration 4); snapshot rotation and `snapshot_diff()`.

## [0.3.0] — 2026-07-10

- **Schema migrations** (versioned, forward-only) and
  `agent-memory check` integrity verification.
- **Cold-archive retention** (migration 3): expired/decayed memories become
  restorable archives; pinned/authority never archived by decay.
- **Auto semantic recall**: `MemoryClient(semantic="auto")` — self-syncing
  turbovec index over a dependency-free hashing embedder.
- `agent-memory backup/restore` (WAL-safe online backups).

## [0.2.4] — 2026-07-10

- Console dashboard, in-place memory editing (`PATCH`), agent purge danger
  zone, converging-evidence resonance, token/doctor CLI, official logo.

## [0.2.3] — 2026-07-10

- First public release: memory association layer (`memory_links`,
  ACL-safe resonance recall, link decay, hub damping, supersedes),
  Hebbian reinforcement loop with negative feedback, persisted recall
  profiles, write-side consolidation, requester-aware Web console,
  MCP server, Apache-2.0.

## Pre-release lineage

- **2026-06-12 → 06-13** — Dynamic Context Orchestration prototypes
  (`ContextSnapshot` schema, offload/reload, precision test suite) on the
  Hermes workstream, later merged and hardened in 0.4.0.
- **2026-06-05 → 06-09** — v0.2.x internal baselines: SQLite+FTS5 source of
  truth, requester-aware ACL, truth arbitration, retrieval foundation,
  turbovec sidecar validation (`v0.1.0-stable` tag).
