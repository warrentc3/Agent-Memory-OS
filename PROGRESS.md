# AgentMemoryOS Progress

Last updated: 2026-06-09 12:08:37 CST (+0800)

## Current project status

- Status: running
- Project root: `/mnt/nas/Hermes-Gitlab/agent-memory-os`
- GitLab remote: `git@gitlab.com:hermes-agent-bastet/agent-memory-os.git`
- Stable branch: `main`
- Active worktree branch: `feat/pr3-turbovec-provider`
- Current HEAD observed during audit: `d75ae93`
- `main` / `origin/main` observed during audit: `4c2eb2b`
- Observed release tags: `v0.1.0-stable`
- Package metadata version: `0.1.0`

## Completed evidence-backed milestones

- completed — MVP / local-first memory baseline exists with SQLite + FTS5 source-of-truth files under `src/agent_memory_os/`.
  - Evidence: tracked files include `src/agent_memory_os/client.py`, `db.py`, `schema.py`, `context_pack.py`, and related tests.
- completed — Requester-aware ACL and visibility behavior has documented verification evidence.
  - Evidence: `PROJECT_STATUS.md` verification snapshot and `scripts/verify_acl_identities.py`.
- completed — Retrieval foundation, truth arbitration, memory decay/recency, and shadow-mode test modules exist.
  - Evidence: tracked tests under `tests/test_retrieval_foundation.py`, `tests/test_truth_arbitration.py`, `tests/test_decay_scoring.py`, `tests/test_memory_decay_recency.py`, and `tests/test_shadow_mode.py`.
- completed — PR3 turbovec provider branch exists as an optional semantic candidate sidecar.
  - Evidence: active branch `feat/pr3-turbovec-provider`, `src/agent_memory_os/providers/turbovec.py`, `tests/test_turbovec_provider.py`, `docs/adr/ADR-0001-turbovec-semantic-sidecar-positioning.md`.
- completed — Multi-project governance documentation scaffold has been added.
  - Evidence: `PROGRESS.md`, `docs/portfolio-status.md`, `docs/project-status/current.md`, `docs/evidence/`, `docs/blockers/`, `docs/handoffs/`, `docs/reviews/`.

## Current non-production constraints

- blocked — Hermes default memory backend activation.
  - Blocker: activation gates in `docs/hermes-activation-gates.md` are not complete.
  - Required input/evidence: downgrade verification, migration/rollback evidence, shadow integration comparison, multi-profile ACL validation, and Mizuki/Product final acceptance.
- blocked — Production prompt influence from turbovec semantic candidates.
  - Blocker: ADR hold decision keeps PR3 optional-off / shadow-evidence-only.
  - Required input/evidence: golden recall, ACL/expiry, rollback, latency, consistency, killswitch, and product acceptance gates.
- blocked — Claiming `v0.3-awakened` as an actual release tag.
  - Blocker: `git tag --list` currently shows only `v0.1.0-stable`.
  - Required input/evidence: create/push a matching release tag through normal review/release process, or keep v0.3 language as roadmap/validation.

## Next milestones

1. Complete PR3 review for `feat/pr3-turbovec-provider` with tests and docs evidence.
2. Run full test suite on the active branch after current documentation changes.
3. Produce activation-gate evidence bundle before any Hermes production/default backend discussion.
4. Keep `PROJECT_STATUS.md` and this `PROGRESS.md` updated at each handoff, blocker, review, and release decision.
