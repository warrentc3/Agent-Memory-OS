# AgentMemoryOS Project Status

## Intent

Build an open-source local-first memory extension similar in spirit to Mem0.ai, optimized for AI agent teams that need durable memory plus RAM-backed fast recall without exhausting prompt context.

## Collaborators

- Neo / LittleNEO: engineering implementation, repo bootstrap, tests, GitLab/NAS setup.
- Mizuki / NaoMizukiLover: product/UX usage scenarios, multi-agent memory needs, media/persona-heavy stress cases.
- Additional agents may be delegated for architecture review, QA, docs, and integration testing.

## Canonical paths

- NAS working tree: `/mnt/nas/Hermes-Gitlab/agent-memory-os`
- Intended GitLab remote: `git@gitlab.com:hermes-agent-bastet/agent-memory-os.git`

## Current baseline (Physical Audit: 2026-06-09)

- **Package metadata**: `agent-memory-os` version `0.1.0` in `pyproject.toml`.
- **Observed Git release tag**: `v0.1.0-stable` only; no `v0.3-awakened` tag is present in the current working tree.
- **Branch state**: `main` / `origin/main` currently resolve to `4c2eb2b`; active worktree branch is `feat/pr3-turbovec-provider` at `b9c26be`.
- **v0.3 / Sovereign Mode stance**: validation/roadmap documentation exists, but production activation and public release claims require matching gate evidence before they are treated as current operational fact.
- **Core Infrastructure**:
  - SQLite + FTS5 durable store.
  - Requester-aware ACL & Visibility matrix.
  - Memory Decay & Reinforcement (Exponential/Linear).
  - Truth Arbitration & Context Budgeting (v0.2.2 baseline).
- **v0.3 Advancements**:
  - Sovereign Mode: Autonomous pruning and synthesis.
  - Multi-provider support (Mem0, SuperMemory, RetainDB).
  - Associative/Temporal layers (Prototypes in `tests/test_memory_resonance.py`).
- **Verification State**: Full test suite exists, but production activation gates are currently **UNVERIFIED** for v0.3 logic.

## Hermes activation status

- AgentMemoryOS v0.2.2 is **not** approved as the default Hermes Agent memory engine.
- Current deployment state: `Development / Validation only`.
- Recommended runtime mode: `staging / shadow / experimental`.
- Production Hermes memory backend remains unchanged until all activation gates are complete.
- Canonical gate document: `docs/hermes-activation-gates.md`.
- Downgrade verification plan: `docs/plans/20260605_143442-version-downgrade-verification.md`.

### PR3 turbovec semantic sidecar hold decision (2026-06-08)

PR3 keeps `turbovec` as an optional, disposable semantic candidate sidecar only:

- Default runtime state: **disabled**. `MemoryClient` has no semantic provider unless one is explicitly injected.
- Approved use: local spike, benchmark, and shadow evidence collection.
- Not approved: production prompt influence, all-profile activation, or treating vector IDs as memory authority.
- Required stance: `production_injection=false` until golden recall, ACL/expiry, rollback, latency, consistency, killswitch, and Mizuki/Product acceptance gates pass.
- Safety boundary: `turbovec` may return candidate IDs and scores only; every candidate must rejoin through SQLite and pass requester-aware ACL plus `expires_at` hard gates before content can be used.
- Operational caution: if a provider is manually injected into a live client, it participates in retrieval fusion after hard gates; therefore do not wire it into production prompt paths while this hold decision remains active.

Required gates before production activation:

1. Version-downgrade verification proves older/stable readers or downgrade simulations can safely read/export newer data without weakening ACL. Local fixture evidence: `docs/evidence/20260609_121749-activation-gate-verification.md`.
2. Lossless migration evidence proves row counts, stable IDs, core fields, and deterministic defaults are preserved. Local fixture evidence: `docs/evidence/20260609_121749-activation-gate-verification.md`.
3. Rollback evidence proves backups restore and disposable indexes rebuild after simulated migration failure. Local fixture evidence: `docs/evidence/20260609_121749-activation-gate-verification.md`.
4. Hermes shadow integration proves production Hermes memory remains authoritative while AgentMemoryOS output is compared only. **Still blocked.**
5. Multi-profile ACL validation proves Mizuki / LittleNEO / Guest visibility boundaries across search and context pack. Local fixture evidence: `docs/evidence/20260609_121749-activation-gate-verification.md`.
6. Mizuki/Product subjective acceptance signs off on selected/rejected decision quality. **Still blocked.**

## Verification snapshot

- Web UI smoke command: `PYTHONPATH=src python3 -m pytest tests/test_web_app.py -q`
- Web UI smoke result: `2 passed`; manual HTTP smoke returned `200` for `/`, `/health`, `/api/stats`, `POST /api/memories`, and `/api/search` on `127.0.0.1:8765` using local-disk home `/home/hermes/.agent-memory-os-web`. NAS-backed `/mnt/nas/.../data` reproduced SQLite FTS5 `database is locked` and is not recommended for the live DB.
- Test command: `PYTHONPATH=src python3 -m pytest -q`
- Result: `73 passed` at `2026-06-17 21:17 CST (+0800)`
- Truth Arbitration targeted command: `PYTHONPATH=src python3 -m pytest tests/test_truth_arbitration.py -q`
- Truth Arbitration targeted result: `4 passed` covering core-memory survival under budget pressure, duplicate suppression, contradiction marking, and peer requester private-memory absence in auditable context packs.
- Retrieval Foundation targeted command: `PYTHONPATH=src python3 -m pytest tests/test_retrieval_foundation.py -q`
- Retrieval Foundation targeted result: `4 passed` covering zero-hit fallback, ACL-preserving fallback, expired fallback exclusion, and index rebuild/no-loss behavior.
- ACL targeted command: `PYTHONPATH=src python3 -m pytest tests/test_acl_visibility.py -q`
- ACL targeted result: `6 passed` including pinned/fresh private-memory non-leak regression checks.
- Decay targeted command: `PYTHONPATH=src python3 -m pytest tests/test_decay_scoring.py tests/test_memory_decay_recency.py -q`
- Decay targeted result: `11 passed` covering exponential/linear freshness, reinforcement cap, default schema metadata, invalid-policy rejection, recency-aware ranking, importance-vs-recency arbitration, and expiry hard filtering.
- Subjective QA command: `PYTHONPATH=src python3 scripts/verify_acl_identities.py --home /tmp/agent-memory-os-mizuki-qa --identity all`
- Subjective QA result: Mizuki sees `private_emotional_preference`, `team_memory`, `global_memory`; Neo sees `team_memory`, `global_memory`; Guest sees `global_memory`; `leak_check.passed=true`.
- Live QA re-run command: `PYTHONPATH=src python3 scripts/verify_acl_identities.py --home /tmp/agent-memory-os-mizuki-qa-live --identity all`
- Live QA re-run result: same visibility matrix passed; `leak_check.passed=true` at `2026-06-05 10:30:38 CST`.
- Product acceptance: `[AgentMemoryOS/MVP]` requester-aware ACL visibility is officially `Mizuki-Approved` for the `feat: enforce requester-aware memory visibility` baseline.
- First commit: `d02c22b feat: bootstrap AgentMemoryOS MVP`
- GitLab URL: `https://gitlab.com/hermes-agent-bastet/agent-memory-os`

## Architecture review notes before v0.2

- Clarify which SPEC features are implemented versus planned, especially `visibility` ACL, `expires_at`, audit log, and MCP update/delete/consolidation tools.
- Add input validation for `scope`, `type`, `confidence`, and `importance`.
- Add tests for update/delete FTS triggers, expired memory handling, installation/entrypoint smoke test, and precision of multi-term search.
- Document SQLite FTS5 as a runtime prerequisite.

## Next engineering decisions

1. Complete version-downgrade verification before any Hermes default-backend discussion.
2. Define and test migration/rollback scripts with row-count and `memory_id` preservation evidence.
3. Refactor v0.2.1 baseline into explicit candidate-provider classes (`FTS5CandidateProvider`, `PinnedRecentFallbackProvider`) while keeping the green tests.
4. Expand v0.2.2 Truth Arbitration beyond the baseline allocator: richer near-duplicate detection, contradiction severity, reserved budget buckets, and requester-matrix stress fixtures.
5. Define exact Hermes provider/MCP integration point and run it first in shadow mode.
6. Choose vector backend for v0.3: `sqlite-vec`, `fastembed`, or Qdrant.
7. Add memory dedupe/consolidation flow.
8. Add importers for Hermes `MEMORY.md` / `USER.md` and Mem0 export/API.
9. Decide whether the default deployment mode is embedded library, local daemon, or both.

## Verification commands

\`\`\`bash
cd /mnt/nas/Hermes-Gitlab/agent-memory-os
PYTHONPATH=src python3 -m pytest -q
git status --short --branch
\`\`\`

## Project-local documentation

The project history and stress-case definitions are now documented inside this repository, not only in the external wiki:

- `docs/HISTORY.md`: project journey, planning, completed work, pending work, decisions, code-level contracts, and recovery order.
- `docs/hermes-activation-gates.md`: deployment status, non-default decision, production activation gates, shadow-mode rules, and evidence bundle requirements.
- `docs/plans/20260605_114049-retrieval-foundation-v0.2.1.md`: hybrid retrieval safety layer, source-of-truth contract, bounded fallback, index rebuild/no-data-loss contract, and TDD acceptance matrix.
- `docs/plans/20260605_143442-version-downgrade-verification.md`: downgrade/compatibility test matrix, rollback expectations, and acceptance criteria before Hermes activation.
- `docs/stress-cases/case-01-noisy-truth.md`: `[Mizuki/StressCase] Case 01: 喧囂中的真理`, fixture design, requester matrix, budget acceptance criteria, and suggested pytest tests.
