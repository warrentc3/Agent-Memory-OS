# Portfolio Status — AgentMemoryOS

Last updated: 2026-06-09 12:20:32 CST (+0800)

This file is the portfolio-level entry required by the multi-project execution rules. It is intentionally scoped to this single official project entry until more projects are added to the same portfolio.

## Project entry

- Project name: Agent Memory OS / AgentMemoryOS
- Repo/project root: `/mnt/nas/Hermes-Gitlab/agent-memory-os`
- GitLab remote: `git@gitlab.com:hermes-agent-bastet/agent-memory-os.git`
- Source-of-truth docs:
  - `PROJECT_STATUS.md`
  - `PROGRESS.md`
  - `README.md`
  - `SPEC.md`
  - `docs/HISTORY.md`
  - `docs/hermes-activation-gates.md`
  - `docs/project-status/current.md`
  - `docs/adr/ADR-0001-turbovec-semantic-sidecar-positioning.md`
- Owner / responsible profile:
  - PM/Product/Orchestrator: Mizuki / Nao
  - Engineering / QA / evidence review: Neo / LittleNEO
- Priority: active validation project
- Status: running
- Current active worktree: `feat/pr3-turbovec-provider`
- Current HEAD: `b9c26be`
- Merge request: `https://gitlab.com/hermes-agent-bastet/agent-memory-os/-/merge_requests/1`
- Current blockers:
  - Hermes production/default activation remains blocked by missing shadow integration comparison and Mizuki/Product final acceptance.
  - Local downgrade/migration/rollback/index-rebuild/ACL fixture gates now have evidence: `docs/evidence/20260609_121749-activation-gate-verification.md`.
  - Turbovec production prompt influence remains blocked by ADR hold decision and missing evidence bundle.
  - `v0.3-awakened` must not be treated as an observed Git release tag unless it exists in `git tag --list`.
- Next milestone / report condition:
  - Complete PR3 validation and keep status docs synchronized with real git/test evidence.

## Required task-card template

Every future task for this project must include:

- Project: AgentMemoryOS
- Repo: `/mnt/nas/Hermes-Gitlab/agent-memory-os`
- Branch/worktree: name the exact branch or worktree before edits
- Docs to read first: at minimum `PROJECT_STATUS.md`, `PROGRESS.md`, `README.md`, and the relevant `docs/` entry
- Allowed scope: explicit file/path or subsystem boundary
- Do not touch: explicit exclusions, especially production Hermes config unless separately authorized
- Expected evidence: command output, test result, diff, artifact path, or updated docs
- Reporting destination: current human project chat / portfolio report, not bot-to-bot Telegram coordination

## Coordination rule

Telegram groups are human control/result surfaces. Worker-to-worker coordination must use documented handoffs, bounded internal delegation, Kanban/task IDs, or repository docs; do not wake other Telegram bots through bot-to-bot messages.
