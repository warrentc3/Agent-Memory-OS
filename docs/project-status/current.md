# Current Project Status — AgentMemoryOS

Last updated: 2026-06-09 12:20:32 CST (+0800)

## Repository facts

- Project root: `/mnt/nas/Hermes-Gitlab/agent-memory-os`
- GitLab remote: `git@gitlab.com:hermes-agent-bastet/agent-memory-os.git`
- Active branch: `feat/pr3-turbovec-provider`
- Upstream: `origin/feat/pr3-turbovec-provider`
- Current HEAD: `b9c26be`
- `main` / `origin/main`: `4c2eb2b`
- Observed Git tags: `v0.1.0-stable`
- Python package version: `0.1.0` in `pyproject.toml`

## Operational status

- Status: running
- Runtime posture: development / validation only
- Hermes production/default backend: blocked; not approved
- Turbovec semantic sidecar: optional, disabled by default, shadow/benchmark evidence only
- Source of truth: SQLite / durable records remain authoritative; semantic/vector IDs are candidate IDs only and must rejoin through SQLite with ACL and expiry checks

## Documentation entry points

Read these before any task:

1. `PROJECT_STATUS.md`
2. `PROGRESS.md`
3. `README.md`
4. `SPEC.md`
5. `docs/HISTORY.md`
6. `docs/hermes-activation-gates.md`
7. `docs/adr/ADR-0001-turbovec-semantic-sidecar-positioning.md`
8. Relevant plan/review/evidence file under `docs/`

## Current known drift corrected by this governance pass

- README previously described `v0.3-awakened` as a release tag; current git evidence only shows `v0.1.0-stable`.
- `PROJECT_STATUS.md` previously described v0.3 as physically deployed on `main`; the status now distinguishes actual package/tag/branch evidence from validation/roadmap language.

## Acceptance boundary for future completion claims

A future task may be marked `completed` only when it includes at least one concrete evidence item:

- Git diff / commit / tag / branch evidence
- Test command and result
- Artifact path
- Review note under `docs/reviews/`
- Updated source-of-truth doc with matching timestamp

A task must be marked `blocked` when it depends on missing credentials, missing release decision, missing human approval, incomplete activation evidence, or production-scope authorization.
