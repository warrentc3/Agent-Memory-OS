# Evidence — Activation Gate Verification 2026-06-09 12:17:49 CST

## Scope

This evidence file records the safe, local-only activation-gate work completed after the governance commit on branch `feat/pr3-turbovec-provider`.

The verification used temporary fixture directories under `/tmp`; it did **not** read, write, migrate, or activate any production Hermes memory store.

## Commands executed

```bash
PYTHONPATH=src python3 scripts/verify_downgrade_compatibility.py \
  --home /tmp/agent-memory-os-downgrade-qa \
  --matrix all

PYTHONPATH=src python3 scripts/verify_acl_identities.py \
  --home /tmp/agent-memory-os-acl-verification \
  --identity all

PYTHONPATH=src python3 -m pytest -q
```

## Downgrade / migration / rollback verification result

The new script `scripts/verify_downgrade_compatibility.py` produced:

```json
{
  "status": "PASS",
  "summary": {
    "acl_matrix_passed": true,
    "index_rebuild_passed": true,
    "memory_ids_preserved": true,
    "rollback_restore_passed": true,
    "unknown_metadata_safe": true
  }
}
```

Verified matrix:

- Old minimal schema database opened by current runtime.
  - Row count preserved: `4 -> 4`.
  - Existing `memory_id` values preserved.
  - New decay columns were added with deterministic defaults.
  - ACL matrix remained correct for Mizuki, Neo, and Guest identities.
- Current database read by stable-field downgrade exporter.
  - Stable fields remained readable.
  - Unknown `source` metadata did not grant visibility.
  - Private fixture did not leak to Neo or Guest.
- Simulated migration failure after backup creation.
  - Backup restored successfully.
  - Row count and `memory_id` set were preserved.
  - `rebuild_indexes()` succeeded after restore.
  - Private fixture remained hidden from unauthorized requesters.
- Disposable FTS index rebuild.
  - Dropped FTS/index structures were rebuilt from durable `memories` rows.
  - Durable rows and IDs were preserved.
  - ACL behavior remained correct after rebuild.

## Multi-profile ACL verification result

Existing ACL verification script produced:

```text
leak_check: passed=true, private_leaked_to=[]
mizuki: search/context = private_emotional_preference, team_memory, global_memory
neo:    search/context = team_memory, global_memory
guest:  search/context = global_memory
```

## Pytest result

```text
......................................................................   [100%]
```

Exit code: `0`.

## Gate impact

Cleared by this evidence:

- Version-downgrade verification: completed for local fixture simulation.
- Lossless migration evidence: completed for old-schema/current-runtime and stable-field export fixtures.
- Rollback safety evidence: completed for simulated failure after backup creation.
- Multi-profile ACL validation: completed for Mizuki / Neo / Guest fixture identities across search and context-pack paths.

Still blocked:

- Hermes shadow integration comparison against the live Hermes memory backend.
- Production adapter/config diff for Hermes default backend mode.
- Mizuki/Product final subjective acceptance.
- Any production/default activation decision.

## Conclusion

AgentMemoryOS remains **development / validation only**. The safe local verification gates above have evidence, but production Hermes activation remains blocked until shadow integration and Product acceptance are completed and reviewed.
