# Validation Plan — v0.9.x Milestone Gates

Status: **ACTIVE** (supersedes `hermes-activation-gates.md`, which was
designed against the v0.2.x feature surface and no longer covers the
system: orchestration, retention, federation mesh, agent registry/team
ACL, adaptive forgetting, and the auto semantic index all post-date it).

Purpose: define what "validated" means for a v0.9.x deployment, and provide
a **reproducible simulation harness** (`scripts/validation_run.py`) that
exercises the gates and emits a professional report into `docs/reports/`.

## How to run

```bash
PYTHONPATH=src python scripts/validation_run.py            # full (~5k corpus)
PYTHONPATH=src python scripts/validation_run.py --quick    # CI-sized smoke
```

The harness builds a deterministic synthetic corpus (seeded), runs every
gate, and writes `docs/reports/<date>-v<version>-validation-report.md`
plus raw JSON under `docs/reports/data/`.

## Gate matrix

### G1 — Security & ACL (hard gates; any failure = overall FAIL)

| Check | Criterion |
|---|---|
| Private memory isolation | Non-owners never see `visibility: []` memories via search, pack, orchestrate, graph, or browse |
| Team boundary | `team:<id>` memories visible to every registered member, invisible to non-members; membership edits apply immediately |
| Resonance non-traversal | A private memory never bridges two public ones for an unauthorized requester |
| Share/revoke | Only owners can grant/revoke; revocation is immediate; de-identified copies contain no owner references |
| Recall-feedback gate | A requester cannot weaken memories it cannot see |
| Team-scoped export | Bundles never carry out-of-team memories or boundary-crossing links |

### G2 — Functional correctness

| Check | Criterion |
|---|---|
| Full test suite | 100% pass on the host running validation |
| Recall quality | Seeded needle queries: top-3 hit rate ≥ 95% (lexical), linked-neighbor surfacing works on ≥ 90% of probes |
| Orchestrator | All five buckets budget-respecting; proactive warnings/procedures present; session dedup verified |
| Lifecycle | Retention archives exactly the expired/idle set; restore revives; pinned/authority never decay-archived; feedback tunes half-lives as specified |
| Durability | backup → restore roundtrip byte-equivalent counts; integrity_check ok; legacy DB self-migrates to current schema version |
| Federation | Two-host bundle + HTTP convergence: both stores reach identical memory/link counts and contents |

### G3 — Performance (measured at ~5,000 memories / ~2,000 links, local disk)

| Metric | Target |
|---|---|
| Write throughput (add) | ≥ 200 memories/s |
| Search latency (requester + teams + resonance) | p50 ≤ 25 ms, p95 ≤ 80 ms |
| Context pack | p95 ≤ 100 ms |
| Orchestrate (5 buckets + session dedup) | p95 ≤ 150 ms |
| Graph snapshot (300 edges) | ≤ 250 ms |
| Dashboard stats | ≤ 250 ms |
| Retention full pass | ≤ 5 s |
| Consolidation (dedup + synthesis) | ≤ 10 s |
| Bundle export + import (full corpus) | ≤ 10 s each |
| Auto semantic index build (if turbovec present) | ≤ 30 s; query p95 ≤ 50 ms |

Targets are for a developer-class machine; the report records the actual
environment. A target miss is a WARN (investigate), not an automatic FAIL,
unless it exceeds 3× target.

### G4 — Deployment reality (verified per release, evidence in PROGRESS)

- Three-OS CI green (Ubuntu/macOS/Windows × Python 3.11–3.13)
- PyPI install + import + roundtrip on a clean environment
- Service install/uninstall roundtrip on at least one OS

## Verdict rules

- **PASS**: all G1 + G2 pass; G3 within targets (or WARNs justified).
- **CONDITIONAL**: G1/G2 pass, G3 has un-justified WARNs.
- **FAIL**: any G1 failure, any G2 failure, or a G3 result over 3× target.

Production adoption decisions (e.g., a Hermes default-backend switch)
require a PASS report generated on hardware representative of production,
plus product acceptance — the governance intent of the original gates,
carried forward.
