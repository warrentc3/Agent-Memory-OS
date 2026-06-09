# Current Blockers — AgentMemoryOS

Last updated: 2026-06-09 12:17:49 CST (+0800)

## Completed in local validation: downgrade / migration / rollback / ACL fixture gates

- Status: completed
- Evidence: `docs/evidence/20260609_121749-activation-gate-verification.md`
- Command evidence:
  - `PYTHONPATH=src python3 scripts/verify_downgrade_compatibility.py --home /tmp/agent-memory-os-downgrade-qa --matrix all` -> `status: PASS`
  - `PYTHONPATH=src python3 scripts/verify_acl_identities.py --home /tmp/agent-memory-os-acl-verification --identity all` -> `leak_check.passed: true`
  - `PYTHONPATH=src python3 -m pytest -q` -> `100%`
- Cleared local fixture evidence:
  - Version-downgrade verification
  - Lossless migration row/ID preservation for old-schema/current-runtime and stable-field export fixtures
  - Rollback safety after simulated migration failure and backup restore
  - Disposable index rebuild safety
  - Multi-profile ACL fixture matrix for Mizuki / Neo / Guest across search and context-pack paths

## Blocked: Hermes production/default backend activation

- Status: blocked
- Remaining blocker: production activation still lacks Hermes shadow integration comparison and final Product acceptance.
- Completed prerequisite evidence:
  - Version-downgrade verification: `docs/evidence/20260609_121749-activation-gate-verification.md`
  - Lossless migration fixture evidence: `docs/evidence/20260609_121749-activation-gate-verification.md`
  - Rollback safety fixture evidence: `docs/evidence/20260609_121749-activation-gate-verification.md`
  - Multi-profile ACL fixture validation: `docs/evidence/20260609_121749-activation-gate-verification.md`
- Remaining required evidence/input:
  - Hermes shadow integration comparison against the current Hermes memory behavior
  - Exact adapter/config diff used for shadow mode
  - Mizuki/Product final subjective acceptance
- Source: `docs/hermes-activation-gates.md`, `PROJECT_STATUS.md`

## Blocked: turbovec production prompt influence

- Status: blocked
- Blocker: PR3 ADR keeps turbovec optional-off / shadow-evidence-only.
- Required evidence/input:
  - Golden recall evidence
  - ACL/expiry rejoin verification with the actual semantic sidecar path
  - Rollback and consistency evidence for any semantic sidecar artifacts
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
