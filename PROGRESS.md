# AgentMemoryOS Progress

Last updated: 2026-06-17 22:17:42 CST (+0800)

## Current project status

- Status: running
- Project root: `/mnt/nas/Hermes-Gitlab/agent-memory-os`
- GitLab remote: `git@gitlab.com:hermes-agent-bastet/agent-memory-os.git`
- Stable branch: `main`
- Active worktree branch: `feat/pr3-turbovec-provider`
- Current HEAD: `b9c26be`
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

- completed — Web UI openability regression fixed and covered by FastAPI smoke tests.
  - Evidence: `src/agent_memory_os/web_app.py`, `tests/test_web_app.py`, `agent-memory-web` script entrypoint in `pyproject.toml`; `PYTHONPATH=src python3 -m pytest -q` passed 73 tests; manual HTTP smoke returned 200 for `/`, `/health`, `/api/stats`, `POST /api/memories`, and `/api/search`.
  - Runtime note: live Web UI should use a local-disk SQLite home such as `/home/hermes/.agent-memory-os-web`; NAS-backed `/mnt/nas/.../data` reproduced `sqlite3.OperationalError: database is locked` during FTS5 schema creation.
- completed — Memory association layer (v0.2.3): authoritative `memory_links` table, resonance retrieval track, co-recall reinforcement (`record_recall`), and per-agent `RecallProfile` soft re-weighting.
  - Evidence: `src/agent_memory_os/db.py`, `src/agent_memory_os/schema.py`, `src/agent_memory_os/client.py`, `tests/test_memory_links.py` (7 tests including resonance ACL leak-check: invisible nodes are untraversable).
- completed — FTS trigger latent bug fixed: legacy AFTER UPDATE/DELETE triggers used the FTS5 `'delete'` command (invalid for regular FTS5 tables), so every `update_content()`/`delete()` raised `SQL logic error`. Triggers now use plain `DELETE`, with startup migration for existing databases.
  - Evidence: `src/agent_memory_os/db.py` (`_ensure_valid_fts_triggers`), `tests/test_fts_triggers.py` (3 regression tests, closing the long-standing "tests for update/delete FTS triggers" gap in `PROJECT_STATUS.md`).
  - Verification: `PYTHONPATH=src python3 -m pytest` → `83 passed` at `2026-07-08`.
- completed — Association layer v2 enhancements (2026-07-10): link decay (90-day half-life on edge activation), hub-node damping (top-8 edges per node), resonance audit paths (`via:<seed>:<relation>`), directional `supersedes` demotion, negative feedback (`record_recall(helpful=False)`), context-pack `auto_reinforce` loop closure, write-time `auto_link`, ERA `derive_links` → `import_links` bridge, persisted `recall_profiles` table with auto-apply per requester, write-side `consolidate()` (duplicate merge + co-recall concept synthesis, visibility-safe), and WAL + busy_timeout for multi-agent deployments.
  - Evidence: `src/agent_memory_os/db.py`, `client.py`, `schema.py`, `memory_resonance.py`, `mcp_server.py`, `tests/test_memory_enhancements.py` (13 tests incl. consolidation visibility leak-check).
  - Verification: `PYTHONPATH=src python3 -m pytest` → `96 passed` at `2026-07-10`.
- completed — WebUI rework (2026-07-10): requester-aware ACL enforced on `/api/search` and new `/api/context-pack` (previously the API bypassed ACL entirely and leaked private memories); input validation for scope/type/confidence/importance/decay_policy; `visibility`/`expires_at`/`pinned`/`auto_link` accepted on create; association endpoints (`/api/links`, `/api/memories/{id}/links`, `/api/recall`, `/api/consolidate`, `/api/memories/{id}`); shared client with lock instead of per-request client; default port aligned to `8000`.
  - Evidence: `src/agent_memory_os/web_app.py`, `tests/test_web_app.py` (7 tests incl. search/context-pack ACL leak regressions); live uvicorn smoke on `127.0.0.1:8123` verified health/add/search/pack/stats/root and clean shutdown.
  - Verification: `PYTHONPATH=src python3 -m pytest` → `101 passed` at `2026-07-10`.
- running — WebUI availability triage / temporary runtime recovery corrected at `2026-06-17 22:57:24 CST`.
  - Evidence: `docs/evidence/20260617_225724-webui-port-8000-correction.md`; previous `docs/evidence/20260617_221742-webui-availability-triage.md` is superseded for runtime port selection because it used stale `8765` documentation instead of the expected `8000` endpoint.
  - Current local process: Hermes background session `proc_b629303937b0`, PID `2369731`, binding `127.0.0.1:8000`; `/`, `/health`, and `/api/stats` returned HTTP 200 after restart.
  - Durability caveat: this is an ad-hoc tracked process, not a supervisor/systemd service. WebUI will become unavailable again if this process exits or the host/session is restarted.
  - Deployment caveat: WebUI implementation/test files and script entrypoint are still local working-tree changes/untracked and require review/commit before clean checkout or deployment can rely on them.

## Current non-production constraints

- blocked — Hermes default memory backend activation.
  - Completed local prerequisite evidence: downgrade/migration/rollback/index-rebuild/ACL fixture matrix in `docs/evidence/20260609_121749-activation-gate-verification.md`.
  - Remaining blocker: Hermes shadow integration comparison and Mizuki/Product final acceptance are not complete.
  - Required input/evidence: shadow adapter/config diff, comparison logs against current Hermes memory behavior, and Product acceptance.
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
