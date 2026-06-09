# Current Blockers — AgentMemoryOS

Last updated: 2026-06-09 12:08:37 CST (+0800)

## Blocked: Hermes production/default backend activation

- Status: blocked
- Blocker: activation gates are incomplete.
- Required evidence/input:
  - Version-downgrade verification
  - Lossless migration evidence
  - Rollback safety evidence
  - Hermes shadow integration comparison
  - Multi-profile ACL validation
  - Mizuki/Product final subjective acceptance
- Source: `docs/hermes-activation-gates.md`, `PROJECT_STATUS.md`

## Blocked: turbovec production prompt influence

- Status: blocked
- Blocker: PR3 ADR keeps turbovec optional-off / shadow-evidence-only.
- Required evidence/input:
  - Golden recall evidence
  - ACL/expiry rejoin verification
  - Rollback and consistency evidence
  - Latency benchmark
  - Kill switch plan
  - Product acceptance
- Source: `docs/adr/ADR-0001-turbovec-semantic-sidecar-positioning.md`

## Blocked: treating v0.3-awakened as observed release tag

- Status: blocked
- Blocker: `git tag --list` currently shows only `v0.1.0-stable`.
- Required evidence/input:
  - Create and push a reviewed release tag, or keep v0.3 language as validation/roadmap.

## Not blocked: documentation governance scaffold

- Status: completed
- Evidence: `PROGRESS.md`, `docs/portfolio-status.md`, `docs/project-status/current.md`, `docs/evidence/`, `docs/reviews/`, `docs/blockers/`, `docs/handoffs/`.
