# AgentMemoryOS - Project History and Roadmap

Last updated: 2026-06-06 23:48:38 CST (+0800)

## Purpose

This document records the project journey, decisions, completed work, pending work, and code-level contracts inside the AgentMemoryOS repository itself.

AgentMemoryOS, also referred to in early discussions as Mnemosyne Local, is a local-first, MCP-native, RAM-cache-accelerated long-term memory engine for multi-agent systems.

Core engineering principle:

> Memory permission control is more important than recall volume.

The system must not blindly inject all memories into prompts. It must retrieve only authorized, relevant, high-quality memories and pack them under an explicit context budget.

## Canonical repository

- Working tree: `/mnt/nas/Hermes-Gitlab/agent-memory-os`
- GitLab remote: `git@gitlab.com:hermes-agent-bastet/agent-memory-os.git`
- Public URL: `https://gitlab.com/hermes-agent-bastet/agent-memory-os`
- Current branch at documentation time: `main`

## Collaborator / label conventions

- `[Neo/Engineering]`: implementation, architecture, tests, infra, CI/CD.
- `[Mizuki/Product]`: requirements, UX, persona stress cases, memory quality.
- Shared tags:
  - `[AgentMemoryOS/Spec]`
  - `[AgentMemoryOS/MVP]`
  - `[AgentMemoryOS/v0.2]`
  - `[MemoryPolicy]`
  - `[ContextBudget]`
  - `[RetrievalQuality]`
  - `[OpenSource]`

## Product direction

AgentMemoryOS is designed to address several long-running AI agent pain points:

1. Context windows are too small for durable memory.
2. Cloud memory platforms add privacy, latency, cost, and dependency risks.
3. Multi-persona and multi-agent memory sharing needs explicit access control.
4. Retrieval quality alone is not enough; unauthorized memories must never be considered.
5. Prompt context must be budgeted and explainable.

Target compatibility includes Hermes, Claude Code / Claude Desktop style agents, OpenAI Agents, LangChain, CrewAI, AutoGen, and custom MCP clients.

## Hermes activation status

AgentMemoryOS v0.3.1 is the current **Shadow Evidence & Migration Safety** engineering gate for Hermes integration.

It is not approved as the default Hermes Agent memory engine. Production activation is blocked until the following are verified with recorded evidence:

1. Shadow Evidence Pack.
2. Hermes `MEMORY.md` / `USER.md` importer safety and idempotency.
3. Version-downgrade compatibility.
4. Lossless migration.
5. Rollback safety.
6. Hermes shadow integration with `production_injection=false`.
7. Multi-profile ACL validation for the explicitly allowlisted `neo` and `mizuki` shadow coverage.
8. Golden Recall Query Set.
9. Mizuki/Product stress cases and final subjective acceptance.

Canonical roadmap document:

- `docs/ROADMAP.md`

Canonical gate document:

- `docs/hermes-activation-gates.md`

Downgrade verification plan:

- `docs/plans/20260605_143442-version-downgrade-verification.md`

Roadmap lock:

- v0.4 Memory Resonance is a future research milestone only.
- v0.4 must not be reported as complete, active canary, production-injected, all-profile activated, or default Hermes memory behavior until v0.3.1 gates pass and a separate documented decision opens the next phase.

## Architecture summary

Core retrieval pipeline:

```text
Raw Data
→ ACL Filter / Hard Cut
→ Budget Allocator / Priority-based
→ Context Pack
```

Expanded architecture:

```text
User / Agent query
  -> query planner
  -> scope + ACL filter
  -> hot cache lookup
  -> SQLite FTS5 retrieval
  -> optional vector retrieval
  -> rerank by relevance + importance + confidence + freshness
  -> context budget allocator
  -> prompt-ready context pack
```

## Project evolution

### Phase 0: Conception and infrastructure

- Defined the product as a local-first AI agent memory runtime.
- Established the NAS working tree at `/mnt/nas/Hermes-Gitlab/agent-memory-os`.
- Created and synchronized the GitLab repository.
- Established the tiered memory direction: hot cache, local structured/FTS storage, future vector/cold archive support.

### Phase 1: MVP - The Security Foundation

Focus: ACL and visibility enforcement.

Core principle:

> Memories without permission have no right to be ranked.

Completed baseline components:

- SQLite persistence.
- SQLite FTS5 keyword retrieval.
- Structured memory records.
- In-process LRU cache.
- Context pack builder with conservative token-ish budget.
- Python SDK.
- CLI commands: `add`, `search`, `pack`, `stats`.
- Optional MCP server scaffold.
- Unit tests.

### Phase 2: v0.2 - 喧囂中的真理

Focus: Context Budget and Truth Arbitration.

Goal: solve the memory pollution and resource-arbitration problem.

Key engineering challenges:

- Context Budget Allocator: manage limited prompt space under noise saturation.
- Core Memory Protection: keep `permanence=true` / high-weight memories alive under pressure.
- Temporal Decay and Recency: reduce stale-but-similar memory influence.
- Truth Arbitration: handle contradictory memories with conflict metadata.
- Explainability: emit selected/rejected decision reasons.

### Phase 2.1: v0.2.1 - Retrieval Foundation

Focus: prevent candidate recall gaps and future index migrations from causing memory loss or false stress-case failures.

Core source-of-truth contract:

```text
SQLite memories table = durable source of truth
FTS5 index            = disposable lexical candidate provider
Future vector index   = disposable semantic candidate provider
Fallback provider     = bounded safety net, never storage
Context pack          = downstream allocator, never storage
```

v0.2.1 must land before full vector retrieval and before heavier noisy-context arbitration. The purpose is to prove that all retrieval sources only produce candidate `memory_id`s, then the system rejoins the authoritative SQLite records and reapplies ACL/expiry hard gates.

Planned providers:

- `FTS5CandidateProvider`: wraps current lexical retrieval behavior.
- `PinnedRecentFallbackProvider`: bounded zero-hit fallback for authorized, non-expired pinned/recent/core memories.
- Future `SemanticCandidateProvider`: semantic recall source unioned with lexical and fallback candidates, never a replacement.

Implementation plan:

- `docs/plans/20260605_114049-retrieval-foundation-v0.2.1.md`

## Data model definition

The memory record model includes:

- `id`
- `owner`
- `scope`
- `type`
- `content`
- `summary`
- `tags`
- `visibility`
- `source`
- `confidence`
- `importance`
- `created_at`
- `updated_at`
- `expires_at`
- `decay_policy`
- `decay_half_life_days`
- `last_accessed_at`
- `access_count`
- `pinned`

## Completed implementation history

### v0.3.1 Shadow Evidence & Migration Safety

Recorded the roadmap lock for the next Hermes integration gate.

Authoritative stance:

- v0.3.1 is the active engineering gate.
- `production_injection=false`.
- Shadow profile coverage is explicitly allowlisted to `neo` and `mizuki`.
- Shadow evidence, importer idempotency, migration/rollback safety, ACL zero-leakage, golden recall, and Mizuki/Product stress cases must pass before any production switch.
- v0.4 Memory Resonance remains a future research milestone only until the v0.3.1 gates pass and a separate documented decision opens that phase.

### MVP implementation

Implemented baseline components listed above and added test coverage for core behavior.

### GitLab bootstrap

Initialized and pushed the repository to:

```text
git@gitlab.com:hermes-agent-bastet/agent-memory-os.git
```

### v0.2 ACL baseline

Implemented requester-aware ACL filtering in search and context-pack paths.

Key code areas:

- `src/agent_memory_os/client.py`
- `src/agent_memory_os/db.py`
- `tests/test_acl_visibility.py`
- `scripts/verify_acl_identities.py`
- `tests/test_verification_script.py`

Current supported visibility behavior:

- `visibility=["agent"]`: owner/requester isolation.
- `visibility=["global"]`: visible to any requester.
- `visibility=["agent:<id>"]`: explicit agent allowlist.
- `visibility=["team"]` or `visibility=["team:<id>"]`: team-aware access via requester team id.
- Expired memories are excluded from search results and therefore cannot enter context packs.

### ACL subjective QA

Created `scripts/verify_acl_identities.py` to seed a temporary ACL fixture and switch requester identities across Mizuki, Neo, and Guest.

Acceptance result:

- Mizuki sees: `private_emotional_preference`, `team_memory`, `global_memory`.
- Neo sees: `team_memory`, `global_memory`.
- Guest sees: `global_memory`.
- Leak check: `leak_check.passed=true`.

This confirmed both raw search and context-pack filtering.

### Memory Decay & Recency planning

Created a detailed v0.2 implementation plan:

- `docs/plans/20260605_100751-memory-decay-recency-v0.2.md`

The planned scoring shape is:

```text
effective_score = text_score
                * importance_weight
                * confidence_weight
                * freshness_weight
                * reinforcement_weight
                * dedupe_penalty
                * contradiction_penalty
```

ACL and expiry are hard filters, not soft multipliers.

### Memory Decay & Recency baseline

Implemented the first v0.2 scoring baseline.

Key code areas:

- `src/agent_memory_os/scoring.py`
- `src/agent_memory_os/schema.py`
- `src/agent_memory_os/db.py`
- `tests/test_decay_scoring.py`
- `tests/test_memory_decay_recency.py`
- `tests/test_acl_visibility.py`

Implemented behavior:

- `decay_policy`: `none`, `linear`, or `exponential`.
- `decay_half_life_days`: defaulted by memory type, positive for decaying policies.
- `pinned`: disables freshness decay while preserving ACL and expiration hard gates.
- `access_count`: contributes a capped reinforcement factor.
- Search now fetches extra FTS candidates, computes effective score, sorts by metadata-aware score, then trims to requested limit.

Implemented scoring shape:

```text
effective_score = text_score
                * (0.45 + 0.35 * importance + 0.20 * confidence)
                * freshness_factor
                * reinforcement_factor
```

Verification coverage:

- Exponential half-life behavior.
- Linear decay floor.
- Pinned/no-decay handling.
- Reinforcement cap.
- Schema defaults and validation.
- Recent memory outranking stale equivalent memory.
- Important authoritative older memory outranking recent low-confidence trivia.
- Expired memory exclusion even when important or pinned.
- Regression that pinned/fresh private memory remains hidden from unauthorized agents.

### v0.2.1 Retrieval Foundation baseline

Defined the retrieval safety contract and implemented the first regression-tested fallback/rebuild baseline.

Key documented contracts:

- SQLite `memories` table remains the only durable source of truth.
- FTS5, future vector indexes, and fallback sources are candidate providers only.
- Candidate providers merge/dedupe by stable `memory_id` before authoritative SQLite rejoin.
- ACL and `expires_at` hard gates run after candidate merge and before context insertion.
- Zero-hit fallback is small, explainable, ACL-preserving, and non-expired.
- `MemoryClient.rebuild_indexes()` rebuilds disposable FTS5 state from authoritative `memories` rows.
- Index rebuild does not delete, mutate, or regenerate memory rows.

Implemented TDD acceptance tests:

- `test_zero_fts_hits_can_fallback_to_allowed_recent_core_memory`
- `test_fallback_does_not_leak_private_memory`
- `test_fallback_excludes_expired_memories`
- `test_index_rebuild_preserves_memory_ids_and_records`

Still planned for the explicit provider-class refactor and semantic backend stage:

- `test_hybrid_retrieval_unions_fts_and_semantic_candidates`
- `test_semantic_candidates_still_pass_acl_gate`
- `test_semantic_candidates_still_exclude_expired_memories`
- `test_backend_failure_degrades_recall_without_deleting_records`

### v0.2.2 Truth Arbitration baseline

Implemented the first Context Budget Allocator / Truth Arbitration baseline for `[Mizuki/StressCase] Case 01: 喧囂中的真理`.

Key code areas:

- `src/agent_memory_os/context_pack.py`
- `src/agent_memory_os/client.py`
- `tests/test_truth_arbitration.py`

Implemented behavior:

- `build_context_pack_report()` returns both prompt text and auditable selected/rejected `ContextDecision` metadata.
- `MemoryClient.context_pack_report()` exposes the audited path using the same requester-aware search/ACL filtering as `context_pack()`.
- Authoritative, permanent, and `source.weight > 8` core memories receive priority under budget pressure.
- Low-confidence noisy memories are demoted even when lexical score is high.
- Duplicate clusters are suppressed using `source.claim_key` or a normalized content fingerprint and receive `duplicate_cluster_suppressed` rejection reasons.
- Contradictory records sharing `source.claim_key` but carrying different `source.claim` values receive `conflict_detected`; selected context lines are marked `CONFLICT`.

Implemented TDD acceptance tests:

- `test_truth_arbitration_keeps_authoritative_core_under_budget_pressure`
- `test_truth_arbitration_suppresses_duplicate_clusters_with_rejection_reasons`
- `test_truth_arbitration_marks_contradictions_instead_of_silently_blending`
- `test_context_pack_report_keeps_private_memory_absent_for_peer_requester`

## Authoritative engineering decisions

### ACL is a hard gate

Unauthorized memory must be eliminated before ranking, reranking, dedupe, budget allocation, or prompt assembly.

Correct semantic flow:

```python
allowed_candidates = [m for m in raw_candidates if can_read(m, requester)]
ranked = sorted(allowed_candidates, key=effective_score, reverse=True)
```

Incorrect semantic flow:

```python
# Wrong: unauthorized memories still flow downstream.
effective_score = text_score * acl_allowed
```

### Search and Context Pack must both enforce ACL

It is insufficient to enforce ACL only at storage metadata or search result level. Context-pack construction must also be requester-aware and must not bypass the same authorization rules.

### Core truth must survive budget pressure

The next major engineering stress case requires the context budget allocator to preserve high-authority memories even when noisy memories are more textually similar.

### Zero Trust multi-agent memory

No agent receives implicit read-all access. Even a core/engineering agent does not automatically read another persona's private memory unless explicitly authorized.

### Retrieval indexes are disposable artifacts

Retrieval backends may improve candidate recall but must never become the authoritative memory store.

Required flow:

```text
candidate ids -> merge by memory_id -> authoritative SQLite rejoin -> ACL/expiry hard gates -> score -> pack
```

Forbidden designs:

- migrating raw memory text into a vector DB without retaining SQLite records;
- regenerating memory ids during embedding/index rebuild;
- storing ACL/expiry only in vector metadata and skipping the authoritative re-check;
- treating missing vector/FTS index rows as proof that a memory does not exist.

## Verification snapshot

Last known verification from `PROJECT_STATUS.md`:

```bash
cd /mnt/nas/Hermes-Gitlab/agent-memory-os
PYTHONPATH=src python3 -m pytest -q
# 33 passed at 2026-06-05 11:59 CST (+0800)
```

Truth Arbitration targeted verification:

```bash
PYTHONPATH=src python3 -m pytest tests/test_truth_arbitration.py -q
# 4 passed
```

ACL targeted verification:

```bash
PYTHONPATH=src python3 -m pytest tests/test_acl_visibility.py -q
# 6 passed
```

Decay targeted verification:

```bash
PYTHONPATH=src python3 -m pytest tests/test_decay_scoring.py tests/test_memory_decay_recency.py -q
# 11 passed
```

Subjective ACL QA:

```bash
PYTHONPATH=src python3 scripts/verify_acl_identities.py --home /tmp/agent-memory-os-mizuki-qa --identity all
# leak_check.passed=true
```

## Current status snapshot

Completed:

- [x] Local NAS repo setup.
- [x] Basic tiered memory architecture design.
- [x] SQLite + FTS5 MVP.
- [x] LRU cache.
- [x] Context pack hard budget baseline.
- [x] Requester-aware ACL enforcement.
- [x] Identity verification suite.
- [x] Memory Decay & Recency implementation plan.
- [x] Memory Decay & Recency scoring baseline.
- [x] v0.2.1 Retrieval Foundation contract/specification.
- [x] v0.2.1 zero-hit fallback under ACL.
- [x] v0.2.1 index rebuild/no-data-loss regression tests.
- [x] v0.2.2 Context Budget Allocator / Truth Arbitration baseline.
- [x] v0.2.2 selected/rejected decision reason metadata.
- [x] v0.2.2 duplicate suppression and contradiction markers.
- [x] Project-local history and stress-case documentation.
- [x] Hermes activation gate documentation.
- [x] Version-downgrade verification planning document.

In progress / next:

- [ ] Version-downgrade verification implementation and evidence capture.
- [ ] Migration/rollback verification implementation and evidence capture.
- [ ] Hermes shadow integration design and comparison harness.
- [ ] v0.2.1 candidate-provider abstraction.
- [ ] v0.2.2 richer requester-matrix noisy fixture.
- [ ] v0.2.2 reserved budget buckets and contradiction severity.

Pending / backlog:

- [ ] Multi-agent memory sharing/isolation refined specs.
- [ ] Persona-heavy memory benchmark set.
- [ ] Universal SDK / integration path for external agents.
- [ ] Vector backend selection and implementation.
- [ ] Memory dedupe/consolidation flow.
- [ ] Audit log.
- [ ] MCP `update`, `delete`, and `consolidate` tools.
- [ ] Import/export from Hermes `MEMORY.md` / `USER.md` and Mem0.

## Project-local recovery order

When resuming this project from a new session:

1. Read `README.md`.
2. Read `PROJECT_STATUS.md`.
3. Read `docs/ROADMAP.md` for the current v0.3.1 runtime stance, v0.4 lock, and forbidden overclaim list.
4. Read this file: `docs/HISTORY.md`.
5. Read `docs/hermes-activation-gates.md` before any Hermes runtime integration or activation work.
6. Read `docs/stress-cases/case-01-noisy-truth.md`.
7. Read `docs/plans/20260605_143442-version-downgrade-verification.md` before migration/downgrade work.
8. Read `docs/plans/20260605_114049-retrieval-foundation-v0.2.1.md`.
9. Run:

```bash
cd /mnt/nas/Hermes-Gitlab/agent-memory-os
PYTHONPATH=src python3 -m pytest -q
PYTHONPATH=src python3 scripts/verify_acl_identities.py --home /tmp/agent-memory-os-qa --identity all
```

7. Only claim a visibility, retrieval, or budget behavior is complete after test output confirms it.

## Related project docs

- `README.md`
- `SPEC.md`
- `PROJECT_STATUS.md`
- `docs/ROADMAP.md`
- `docs/hermes-activation-gates.md`
- `docs/plans/20260605_143442-version-downgrade-verification.md`
- `docs/plans/20260605_114049-retrieval-foundation-v0.2.1.md`
- `docs/stress-cases/case-01-noisy-truth.md`
- `docs/plans/20260605_100751-memory-decay-recency-v0.2.md`
