# AgentMemoryOS v0.2.1 Retrieval Foundation Plan

Timestamp: 2026-06-05 11:40:49 CST (+0800)

## Goal

Define a retrieval safety layer before introducing full semantic/vector search or heavier noisy-context arbitration.

The immediate objective is to make retrieval backends non-destructive and explainable:

```text
SQLite memories table = source of truth
FTS5 index            = disposable lexical candidate provider
Future vector index   = disposable semantic candidate provider
Fallback provider     = bounded safety-net candidate provider
Context pack          = downstream allocator, never storage
```

## Why this exists before Case 01

`[Mizuki/StressCase] Case 01: 喧囂中的真理` should test context-budget arbitration, not accidental candidate starvation.

If the authoritative memory never reaches the allocator because FTS5 has zero lexical overlap, the stress case fails for the wrong reason. v0.2.1 separates failure classes:

1. Candidate recall failure.
2. ACL / expiry leakage.
3. Scoring or reranking error.
4. Context-budget eviction error.

## Pipeline contract

```text
query
  -> candidate providers
       - FTS5CandidateProvider
       - future SemanticCandidateProvider
       - PinnedRecentFallbackProvider
  -> merge / dedupe by stable memory_id
  -> join authoritative records from SQLite memories table
  -> ACL hard gate
  -> expires_at hard gate
  -> metadata-aware scoring
  -> context budget allocation
  -> final ACL/expiry re-check before prompt insertion
```

Hard invariants:

- `memory_id` is the only durable join key.
- Backend-specific row ids, vector ids, chunk ids, or ranks must not replace memory identity.
- ACL is never a score multiplier. Unauthorized candidates are removed before ranking.
- `expires_at` is a hard exclusion, including pinned memories.
- A missing or failed index degrades recall quality only; it must not delete, mutate, or hide source records.

## Candidate providers

### `FTS5CandidateProvider`

Purpose: preserve the existing lexical baseline.

Expected behavior:

- Query SQLite FTS5 and return candidate ids with lexical scores.
- Return provider metadata such as `source="fts5"`, raw rank, and normalized score.
- Do not return full authoritative records as the long-term contract; callers should join records by `memory_id`.

### `PinnedRecentFallbackProvider`

Purpose: bounded safety net for zero-hit or low-hit lexical queries.

Allowed sources:

- Pinned, non-expired memories visible to the requester.
- Recent high-importance memories visible to the requester.
- Explicitly filtered same-owner/team memories when caller supplies type/tag filters.
- Authoritative/core records eligible for the requester.

Restrictions:

- Must still pass ACL hard gate and expiry hard gate.
- Must be small and explainable; default target should be single-digit candidates.
- Must not become a hidden replacement for semantic search.

### Future `SemanticCandidateProvider`

Purpose: add semantic recall without replacing existing lexical behavior.

Contract:

```text
hybrid_candidates = union(fts5_candidates, semantic_candidates, fallback_candidates)
```

Then dedupe by `memory_id`, join source records, reapply ACL/expiry, and score.

## Index rebuild / no-data-loss contract

A rebuild operation must satisfy:

- Dropping/rebuilding FTS5 or future vector indexes does not remove rows from `memories`.
- Rebuild preserves every memory id and metadata field:
  - `visibility`
  - `source`
  - `expires_at`
  - `decay_policy`
  - `decay_half_life_days`
  - `last_accessed_at`
  - `access_count`
  - `confidence`
  - `importance`
  - `pinned`
- Failed vector/semantic rebuild must not make the source database appear empty.
- CLI/API should expose an explicit index rebuild operation before relying on external index state.

## TDD acceptance matrix for v0.2.1

Add tests before changing production retrieval internals:

- `test_zero_fts_hits_can_fallback_to_allowed_recent_core_memory`
- `test_fallback_does_not_leak_private_memory`
- `test_fallback_excludes_expired_memories`
- `test_hybrid_retrieval_unions_fts_and_semantic_candidates`
- `test_semantic_candidates_still_pass_acl_gate`
- `test_semantic_candidates_still_exclude_expired_memories`
- `test_index_rebuild_preserves_memory_ids`
- `test_index_rebuild_does_not_modify_memory_records`
- `test_backend_failure_degrades_recall_without_deleting_records`

## Recommended implementation order

1. Introduce a candidate provider abstraction without changing external `MemoryClient.search()` behavior.
2. Wrap current FTS5 search as `FTS5CandidateProvider`.
3. Merge candidates by `memory_id` and rejoin authoritative rows from `memories`.
4. Reapply ACL and expiry gates after candidate merge.
5. Add bounded zero-hit fallback under ACL.
6. Add explicit index rebuild API/CLI and no-data-loss tests.
7. Only then proceed to noisy-truth budget arbitration and semantic/vector retrieval.

## Definition of done

v0.2.1 is done when:

- The existing baseline plus retrieval-foundation tests pass.
- Targeted retrieval-foundation tests pass.
- Zero-hit fallback returns only authorized, non-expired candidates.
- Rebuild/no-data-loss tests prove indexes are disposable artifacts.
- Documentation states that SQLite `memories` remains the authoritative source of truth.

## Implementation snapshot

Initial baseline completed at 2026-06-05 11:40 CST (+0800):

- `MemoryClient.rebuild_indexes()` exposes the rebuild API.
- `MemoryStore.rebuild_indexes()` drops/recreates FTS5 triggers/table and repopulates from `memories`.
- Zero-hit search fallback returns bounded pinned/recent authorized records.
- `tests/test_retrieval_foundation.py` covers zero-hit fallback, private non-leak, expired exclusion, and rebuild/no-loss behavior.
- Verification: `PYTHONPATH=src python3 -m pytest -q` -> `29 passed`.
