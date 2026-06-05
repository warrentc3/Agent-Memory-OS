# Hermes Activation Gates

Last updated: 2026-06-05 14:34:42 CST (+0800)

## Status

AgentMemoryOS v0.2.2 is **not** approved as the default Hermes Agent memory engine.

Current deployment state:

```text
Development / Validation only
Recommended runtime mode: staging / shadow / experimental
Production Hermes default memory backend: disabled / not switched
```

The current engine is valuable as a verified research-grade memory core. It has passed the requester-aware ACL baseline and the first noisy-truth retrieval stress case, but production activation requires additional downgrade, migration, adapter, rollback, and multi-profile verification.

## Activation consensus

The activation decision is gated by this consensus:

> AgentMemoryOS may become the Hermes Agent default memory engine only after LittleNEO confirms lossless data migration, zero-conflict interface integration, rollback safety, and Mizuki completes final subjective product acceptance.

This document is the canonical repository-local record of that deployment gate.

## What is already validated

Validated at the current baseline:

- Requester-aware ACL visibility across search and context-pack paths.
- Private / team / global identity matrix using `scripts/verify_acl_identities.py`.
- Expired memories excluded before ranking and context packing.
- Memory decay and recency scoring baseline.
- Pinned memories bypass freshness decay but do not bypass ACL or expiry hard gates.
- v0.2.1 retrieval foundation:
  - SQLite `memories` table is the durable source of truth.
  - FTS5 and future vector indexes are disposable candidate providers.
  - Zero-hit fallback is bounded and ACL-preserving.
  - `MemoryClient.rebuild_indexes()` preserves stable memory rows and IDs.
- v0.2.2 Truth Arbitration baseline:
  - selected/rejected `ContextDecision` metadata;
  - duplicate suppression;
  - conflict marking;
  - authority/core reserve behavior under budget pressure.
- Case 01 noisy-truth regression baseline:
  - one authoritative core truth survives many low-confidence noisy entries under tight budget;
  - unauthorized private memory remains absent from both search and context-pack decisions.

## Not yet production-approved

The following are not complete enough for production default activation:

- Hermes memory provider adapter or plugin integration.
- MCP server contract hardening for production memory operations.
- Shadow-mode comparison against Hermes' current memory behavior.
- Version-downgrade verification against older schema/client expectations.
- End-to-end migration and rollback procedure.
- Multi-profile Hermes gateway validation across real profiles.
- Larger noisy-context parameterized stress fixtures such as `noise_count = [50, 100, 500]`.
- Bucket-based Context Budget Allocator policy for production memory classes.
- Operational observability for selected/rejected reasons in live runtime logs or debugging output.

## Production activation checklist

AgentMemoryOS must remain non-default until every item below has evidence attached.

### 1. Version-downgrade verification

Required evidence:

- Older clients or downgrade simulations can safely read a database that contains newer optional columns.
- Missing new columns are added by migration without corrupting old data.
- Unknown metadata keys in `source` do not break search, pack, or export paths.
- If exact downgrade execution is impossible, the system must provide a documented forward-only migration plus safe read/export fallback.

Reference plan:

- `docs/plans/20260605_143442-version-downgrade-verification.md`

### 2. Lossless migration

Required evidence:

- Pre/post migration memory row count matches.
- Stable `memory_id` values remain unchanged.
- Core fields remain byte-equivalent where no migration transform is expected.
- Optional new columns receive deterministic defaults.
- FTS5 and future vector indexes can be rebuilt without deleting or mutating durable memory rows.

### 3. Rollback safety

Required evidence:

- Backup location and restore commands are documented.
- Rollback preserves the original SQLite database file or produces a compatible export.
- Failure during migration leaves the pre-migration backup usable.
- Rebuilding disposable indexes after rollback succeeds.

### 4. Hermes shadow integration

Required evidence:

- Hermes existing memory backend remains the production answer path.
- AgentMemoryOS receives mirrored writes or replicated fixtures only.
- Shadow search/pack outputs are logged for comparison but not injected into production prompts.
- Interface conflicts are recorded and resolved before any default switch.

### 5. Multi-profile ACL validation

Required evidence:

- Mizuki / Core identity can read authorized private, team, and global records.
- LittleNEO / Team identity can read authorized team and global records, but never Mizuki private records.
- Guest / external identity can read global records only.
- The same matrix is verified across search results and context-pack decisions.

### 6. Mizuki subjective acceptance

Required evidence:

- Product-facing report contains the relevant context pack text.
- Selected and rejected decisions include stable reason metadata.
- Unauthorized, expired, duplicate, low-confidence, and conflicting memories are visibly handled.
- Mizuki explicitly accepts the behavior after reviewing the evidence.

## Non-goals before activation

Do not block the staging/shadow phase on these future enhancements:

- Full semantic vector retrieval.
- Perfect near-duplicate semantic clustering.
- Advanced contradiction resolution beyond explicit conflict marking.
- UI polish for memory inspection.

These can improve the system later, but they are not substitutes for migration, rollback, ACL, and interface safety.

## Safe deployment modes

### Development mode

Use for local tests and feature work.

```text
Hermes production memory: unchanged
AgentMemoryOS: local test database
Risk: isolated to test home path
```

### Shadow mode

Use for integration validation.

```text
Hermes production memory: authoritative runtime path
AgentMemoryOS: mirrored or fixture-based comparison path
Prompt injection: disabled unless explicitly requested for a test
Risk: low, because AgentMemoryOS does not decide production answers
```

### Default backend mode

Do not use until this document's production activation checklist is complete.

```text
Hermes production memory: AgentMemoryOS
Prompt injection: enabled through audited context-pack path
Risk: high unless all gates are passed
```

## Stop conditions

Immediately stop activation work and remain in shadow/development mode if any of these occur:

- Any private memory appears for a non-authorized requester.
- Expired memory appears in search or context pack.
- Migration changes or regenerates `memory_id` values.
- Rollback cannot restore the pre-migration database.
- Hermes adapter requires changing production gateway routing before shadow validation is complete.
- Mizuki rejects the subjective memory quality or visibility behavior.

## Minimum evidence bundle before final review

Before requesting final product acceptance, produce a single evidence bundle containing:

1. Git commit hash and branch.
2. Full pytest output.
3. ACL identity verification output.
4. Case 01 noisy-truth stress output.
5. Downgrade verification output.
6. Migration/rollback verification output.
7. Hermes shadow integration comparison output.
8. Diff or link to the exact adapter/config used.
9. Known limitations and unresolved risks.

## Related documents

- `PROJECT_STATUS.md`
- `docs/HISTORY.md`
- `docs/stress-cases/case-01-noisy-truth.md`
- `docs/plans/20260605_143442-version-downgrade-verification.md`
- `docs/plans/20260605_114049-retrieval-foundation-v0.2.1.md`
