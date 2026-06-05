# Version-Downgrade Verification Plan

Last updated: 2026-06-05 14:34:42 CST (+0800)

## Purpose

This plan defines the downgrade and compatibility verification required before AgentMemoryOS can be considered for Hermes Agent default memory activation.

The goal is not to promise that every older binary can fully understand every newer feature. The goal is to prove that a version boundary cannot silently corrupt durable memory, leak unauthorized records, or make rollback impossible.

## Scope

This plan covers:

- SQLite schema compatibility.
- Optional-column migration behavior.
- Unknown metadata handling.
- Stable `memory_id` preservation.
- Disposable index rebuild after version changes.
- Read/export fallback when exact downgrade execution is not supported.

This plan does not cover:

- Vector backend selection.
- Production Hermes gateway routing.
- UI-level memory inspection.
- Cloud/SaaS memory synchronization.

## Compatibility principle

AgentMemoryOS follows a source-of-truth model:

```text
SQLite memories table = durable source of truth
FTS5 / vector indexes = disposable candidate providers
Context pack reports  = derived runtime artifacts
```

Therefore, downgrade verification must protect the SQLite memory rows first. Indexes may be dropped and rebuilt. Context packs may be regenerated. `memory_id` values and durable memory content must not be regenerated accidentally.

## Version boundary under test

Current baseline:

```text
v0.2.2 Truth Arbitration / Dual-Track Retrieval baseline
```

Important newer fields and behaviors include:

- `decay_policy`
- `decay_half_life_days`
- `last_accessed_at`
- `access_count`
- `pinned`
- source metadata such as `permanence`, `weight`, `claim_key`, and `claim`
- selected/rejected `ContextDecision` report metadata
- authority-track score fusion derived from durable records

Older baselines may not know these fields. The downgrade simulation must ensure unknown columns or source keys do not make data unreadable or unsafe.

## Required test matrix

### A. Old database to new runtime

Purpose: prove upgrade remains safe.

Steps:

1. Create a fixture database using the old minimal schema or a synthetic equivalent missing the newer optional columns.
2. Insert representative memories:
   - private memory;
   - team memory;
   - global memory;
   - expired memory;
   - high-importance memory.
3. Open the database with the current runtime.
4. Run search and context-pack queries for Mizuki, Neo, and Guest identities.
5. Verify migrations add missing columns with deterministic defaults.

Pass criteria:

- Existing memory rows remain present.
- Existing `memory_id` values remain unchanged.
- ACL behavior remains correct.
- Expired memories remain excluded.
- New optional columns have expected defaults.

### B. New database to old-runtime simulation

Purpose: prove newer data can be safely read or exported across a downgrade boundary.

Steps:

1. Create a database with the current runtime.
2. Insert records using newer metadata:
   - pinned memory;
   - decay-enabled memory;
   - permanent high-weight authority memory;
   - duplicate claim group;
   - conflict claim group.
3. Simulate an older reader that reads only stable baseline fields:
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
4. Verify the older reader ignores unknown columns and unknown `source` keys.

Pass criteria:

- Durable records can still be read or exported.
- Unknown metadata is ignored, not treated as permission grants.
- ACL does not become more permissive under downgraded interpretation.
- Missing advanced scoring features degrade recall quality only, not safety.

### C. Migration failure rollback

Purpose: prove a failed migration does not destroy the pre-migration database.

Steps:

1. Copy the database to a timestamped backup before migration.
2. Run a migration inside a controlled temporary directory.
3. Inject or simulate a failure after backup creation but before successful completion.
4. Restore the backup.
5. Run `rebuild_indexes()`.
6. Re-run ACL and context-pack smoke tests.

Pass criteria:

- Backup is restorable.
- Row count matches the pre-migration count.
- `memory_id` values match the pre-migration set.
- Search and context pack work after index rebuild.
- Private records remain hidden from unauthorized requesters.

### D. Disposable index rebuild

Purpose: prove indexes are not durable memory.

Steps:

1. Create a current-runtime database with mixed records.
2. Drop or corrupt FTS5 index rows in a test copy.
3. Run `MemoryClient.rebuild_indexes()`.
4. Re-run search and context-pack checks.

Pass criteria:

- Rebuild does not delete or mutate durable `memories` rows.
- `memory_id` values remain unchanged.
- Authorized records become searchable again.
- Unauthorized and expired records remain excluded.

## Suggested pytest test names

```python
def test_old_schema_database_upgrades_without_memory_id_changes():
    ...


def test_current_database_can_be_read_by_stable_field_exporter():
    ...


def test_unknown_source_metadata_does_not_grant_visibility():
    ...


def test_failed_migration_can_restore_backup_and_rebuild_indexes():
    ...


def test_downgrade_simulation_degrades_quality_not_safety():
    ...
```

## Required CLI/script evidence

A future verification script should produce a compact JSON report similar to:

```json
{
  "status": "PASS",
  "row_count_before": 12,
  "row_count_after": 12,
  "memory_ids_preserved": true,
  "acl_matrix_passed": true,
  "expired_exclusion_passed": true,
  "unknown_metadata_safe": true,
  "rollback_restore_passed": true,
  "index_rebuild_passed": true
}
```

Suggested command shape:

```bash
PYTHONPATH=src python3 scripts/verify_downgrade_compatibility.py \
  --home /tmp/agent-memory-os-downgrade-qa \
  --matrix all
```

## Acceptance criteria

Downgrade verification is accepted only when:

- Tests or scripts run against a temporary database, not a production Hermes memory store.
- The output includes row counts and `memory_id` preservation checks.
- ACL is tested after every upgrade, downgrade simulation, rollback, and rebuild step.
- Failures stop the activation path instead of being documented as minor warnings.
- The result is recorded in `PROJECT_STATUS.md` and referenced from `docs/hermes-activation-gates.md`.

## Relationship to Hermes activation

Passing this plan does not automatically enable AgentMemoryOS as Hermes default memory.

It only clears one gate in the larger activation checklist:

```text
Downgrade verification
+ lossless migration
+ rollback safety
+ Hermes shadow integration
+ multi-profile ACL validation
+ Mizuki subjective acceptance
= eligible for production activation discussion
```

## Related documents

- `docs/hermes-activation-gates.md`
- `docs/stress-cases/case-01-noisy-truth.md`
- `docs/plans/20260605_114049-retrieval-foundation-v0.2.1.md`
- `PROJECT_STATUS.md`
