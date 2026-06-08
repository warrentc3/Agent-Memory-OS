# Turbovec Semantic Provider Validation Plan

> **For Hermes:** Use `subagent-driven-development` when implementing this plan task-by-task. This document consolidates the Neo engineering audit and Mizuki/product-safety review into one project validation scheme.
>
> **Formal positioning ADR:** `docs/adr/ADR-0001-turbovec-semantic-sidecar-positioning.md` is the canonical decision record for `turbovec` as a disposable `SemanticCandidateProvider` / vector sidecar. The ADR accepts sidecar positioning only; it does not authorize production prompt influence.

**Goal:** Validate and integrate `turbovec` into AgentMemoryOS as an optional, disposable semantic candidate provider without weakening SQLite source-of-truth, ACL, expiry, rollback, or context-budget guarantees.

**Architecture:** `turbovec` is a compressed vector candidate sidecar. It may return candidate `memory_id`s, but final records must always be rejoined from SQLite `memories` and pass requester-aware ACL and expiry gates before scoring, context packing, logging, or prompt injection. The integration starts shadow-only and graduates through golden recall, latency, no-data-loss, and rollback gates.

**Tech Stack:** Python 3.11, SQLite/FTS5, optional `turbovec==0.7.0`, optional `numpy`, AgentMemoryOS `MemoryClient` / `MemoryStore`, existing `ShadowRecallMonitor`, pytest.

---

## 1. Synchronized research summary

### 1.1 Neo engineering findings

- Current implementation is centered in `src/agent_memory_os/db.py`.
- `MemoryStore.search()` currently performs FTS5, authority-track, scoring, fallback, ACL, and expiry handling inside one monolithic flow.
- `MemoryClient` in `src/agent_memory_os/client.py` does not yet accept candidate providers or semantic backends.
- `pyproject.toml` has no runtime dependencies and no semantic optional extra.
- Existing tests are green with the current implementation.
- The correct first engineering step is a provider abstraction refactor, not direct turbovec insertion.

### 1.2 Mizuki/product-safety findings

- SQLite `memories` must remain the only durable source of truth.
- `turbovec` must not be an ACL authority, memory store, memory ID generator, or prompt-injection authority.
- Any vector candidate must be treated as untrusted until it is rejoined to SQLite and passes hard ACL/expiry gates.
- Shadow-mode output must not affect production answers until gates pass.
- Private/expired memory appearing in search, context pack, candidate dump, shadow log, or debug trace is a blocker.

### 1.3 Operational findings

- `turbovec` is promising for compressed long-term semantic recall, especially where FTS5 has low lexical overlap.
- Vector index files should be local-runtime sidecars, not NAS live runtime artifacts.
- Rebuild must be blue/green or atomic-swap style: build into a new path, verify, then switch.
- Vector index failure must degrade to FTS5 + authority track + fallback.
- Known API pitfall: `IdMapIndex` allowlist must be C-contiguous `np.uint64`:

```python
allowed = np.ascontiguousarray(allowed_ids, dtype=np.uint64)
```

---

## 2. Non-negotiable invariants

1. `memories.id` / `memory_id` is the durable join key.
2. SQLite `memories` is the only durable source of truth.
3. FTS5, turbovec, embedding caches, vector mappings, and context caches are disposable indexes/caches.
4. `turbovec` may return only candidate identity and score metadata, never authoritative prompt-ready memory content.
5. All candidate results must pass:

```text
candidate IDs
  -> SQLite authoritative rejoin
  -> requester-aware ACL hard gate
  -> expires_at hard gate
  -> metadata/freshness/reinforcement scoring
  -> context budget allocation
  -> final ACL/expiry check before prompt insertion
```

6. `turbovec` allowlist is an optimization only, not a security boundary.
7. Shadow/canary logs must not leak unauthorized content or private candidate IDs.
8. Any ACL leakage is immediate NO-GO and rollback to FTS-only/fallback path.

---

## 3. Target retrieval pipeline

```text
query
  -> FTS5CandidateProvider
  -> TurbovecSemanticCandidateProvider
  -> PinnedRecentFallbackProvider when normal candidates are empty or degraded
  -> merge/dedupe by memory_id
  -> authoritative SQLite rejoin
  -> ACL hard gate
  -> expiry hard gate
  -> effective_score(metadata, freshness, reinforcement, provider score)
  -> context pack arbitration
  -> final gate before prompt insertion
```

Provider output shape should remain minimal:

```python
@dataclass(slots=True)
class Candidate:
    memory_id: str
    provider: str
    score: float
    rank: int | None = None
    reason: str = ""
```

---

## 4. Validation gates

### Gate 0: Baseline preservation

**Purpose:** Prove that the current project remains green before semantic integration.

Commands:

```bash
PYTHONPATH=src python3 -m pytest -q
PYTHONPATH=src python3 scripts/verify_acl_identities.py --home /tmp/agent-memory-os-acl-baseline --identity all
```

Pass criteria:

- pytest passes.
- ACL verifier passes for Mizuki / Neo / Guest.
- No private leakage.

### Gate 1: Provider abstraction without behavior change

**Purpose:** Refactor retrieval into candidate providers while preserving current behavior.

Pass criteria:

- Existing test suite stays green.
- Search result ordering and `reason` provenance remain compatible or explicitly updated in tests.
- FTS5, authority track, and fallback all still pass ACL/expiry.
- `MemoryClient.search()` public API remains backward-compatible.

### Gate 2: Fake semantic provider safety contract

**Purpose:** Prove semantic candidates cannot bypass security before adding turbovec.

Required tests:

- `test_semantic_candidate_is_rejoined_from_sqlite`
- `test_semantic_candidate_private_memory_does_not_leak_to_other_agent`
- `test_semantic_candidate_expired_memory_is_excluded`
- `test_semantic_candidate_duplicate_is_deduped_by_memory_id`
- `test_semantic_provider_failure_degrades_to_fts_and_fallback`
- `test_context_pack_report_does_not_include_unauthorized_semantic_candidates`

Pass criteria:

- Unauthorized semantic candidates do not appear in search results.
- Unauthorized semantic candidates do not appear in context pack text.
- Unauthorized semantic candidates do not appear in selected/rejected decision content.
- Expired semantic candidates are excluded.
- Provider errors do not fail the whole retrieval path.

### Gate 3: Optional turbovec backend

**Purpose:** Add real `turbovec` as disabled-by-default optional backend.

Pass criteria:

- Base install works without `turbovec` installed.
- Semantic extra can install `turbovec==0.7.0` and `numpy`.
- Provider import failure gracefully disables semantic backend.
- `allowlist` uses `np.ascontiguousarray(..., dtype=np.uint64)`.
- uint64 external IDs map back to stable `memory_id`s.
- Mapping collision is detected and handled safely.

### Gate 4: Golden recall and red-team corpus

**Purpose:** Quantify whether semantic recall helps without unsafe recall.

Golden corpus must include:

- exact lexical queries
- semantic paraphrases
- Chinese query to English memory
- English query to Chinese memory
- no lexical overlap queries
- ambiguous user-preference queries
- procedure/runbook queries
- ACL red-team queries
- expired-memory red-team queries
- duplicate/noisy-memory pressure queries

Metrics:

- recall@3 / recall@5 / recall@10 / recall@20
- precision@k
- MRR or nDCG@k
- vector-only correct hits
- false positives
- duplicate suppression correctness
- ACL leakage count
- expired hit count

Pass criteria:

- factual/golden recall >= 0.95 before canary.
- no precision regression large enough to pollute context budget.
- ACL leakage count = 0.
- expired hit count = 0.
- duplicate context injection count = 0.

### Gate 5: Shadow mode evidence

**Purpose:** Run turbovec side-by-side with legacy path without affecting live answers.

Use existing `ShadowRecallMonitor` style records:

```json
{
  "query": "...",
  "legacy_ids": ["..."],
  "candidate_ids": ["..."],
  "top_k_hit_rate": 1.0,
  "legacy_latency_ms": 12.3,
  "candidate_latency_ms": 18.4,
  "latency_delta_ms": 6.1,
  "acl_zero_leakage": true,
  "go_no_go": "go"
}
```

Pass criteria:

- Production injection remains false.
- Candidate path is log-only during Phase 1.
- p99 candidate latency target <= 200ms.
- p99 > 500ms pauses rollout.
- Any ACL leakage returns to Phase 1 and disables semantic provider.

### Gate 6: No-data-loss rebuild

**Purpose:** Prove vector index lifecycle cannot damage memory records.

Required checks:

- Pre/post SQLite row count equality.
- Pre/post `memory_id` equality.
- Pre/post core fields unchanged.
- Drop vector index and verify FTS/fallback still works.
- Rebuild vector index and verify indexed count parity.
- Corrupt vector index and verify safe fallback.

Pass criteria:

- No SQLite row mutation caused by vector rebuild.
- No `memory_id` mutation.
- Rebuild failure never makes the memory database appear empty.
- Orphan vector IDs never reach prompt context because SQLite rejoin fails.

### Gate 7: Rollback and downgrade

**Purpose:** Prove production can disable or remove turbovec safely.

Rollback levels:

1. Feature flag rollback: disable semantic provider, keep FTS/fallback.
2. Index rollback: switch back to previous vector sidecar or remove vector sidecar.
3. DB rollback: restore SQLite backup, rebuild disposable indexes, restart shadow only.

Pass criteria:

- `AGENT_MEMORY_SEMANTIC_PROVIDER=off` or equivalent returns to FTS/fallback.
- Old index can be restored or ignored.
- SQLite backup restore succeeds.
- `MemoryClient.rebuild_indexes()` succeeds after rollback.
- ACL verifier still passes.

---

## 5. Implementation task plan

### Task 1: Add provider contract skeleton

**Objective:** Introduce candidate provider types without changing behavior.

**Files:**

- Create: `src/agent_memory_os/candidates.py`
- Modify: `src/agent_memory_os/db.py`
- Test: existing tests only for this task

**Steps:**

1. Create `Candidate` dataclass and `CandidateProvider` protocol.
2. Keep all existing `MemoryStore.search()` behavior intact.
3. Add no runtime dependency.
4. Run:

```bash
PYTHONPATH=src python3 -m pytest -q
```

Expected: all tests pass.

### Task 2: Refactor FTS candidates behind internal provider helper

**Objective:** Separate candidate generation from SQLite authoritative row materialization.

**Files:**

- Modify: `src/agent_memory_os/db.py`
- Test: `tests/test_retrieval_foundation.py`, `tests/test_acl_visibility.py`

**Steps:**

1. Convert FTS rows into `Candidate` entries with `provider="fts"`.
2. Add helper to rejoin candidate IDs to SQLite rows.
3. Apply ACL/expiry after rejoin.
4. Preserve scoring semantics.
5. Run:

```bash
PYTHONPATH=src python3 -m pytest tests/test_retrieval_foundation.py tests/test_acl_visibility.py -q
PYTHONPATH=src python3 -m pytest -q
```

Expected: all tests pass.

### Task 3: Add fake semantic provider tests

**Objective:** Lock security behavior before using turbovec.

**Files:**

- Create: `tests/test_semantic_candidates.py`
- Modify: `src/agent_memory_os/client.py`
- Modify: `src/agent_memory_os/db.py`

**Steps:**

1. Add a fake semantic provider returning controlled `memory_id`s.
2. Test unauthorized private candidate is removed.
3. Test expired candidate is removed.
4. Test duplicate candidate dedupes by `memory_id`.
5. Test provider exception degrades safely.
6. Run:

```bash
PYTHONPATH=src python3 -m pytest tests/test_semantic_candidates.py -q
PYTHONPATH=src python3 scripts/verify_acl_identities.py --home /tmp/agent-memory-os-semantic-acl --identity all
```

Expected: all tests pass, no leakage.

### Task 4: Add optional turbovec dependency extra

**Objective:** Make turbovec installable without affecting base package.

**Files:**

- Modify: `pyproject.toml`

**Steps:**

1. Add optional semantic extra:

```toml
semantic = ["numpy>=1.26", "turbovec==0.7.0"]
```

2. Verify base tests without semantic extra.
3. Verify semantic environment import smoke separately.

Commands:

```bash
PYTHONPATH=src python3 -m pytest -q
python3 - <<'PY'
try:
    import turbovec
    import numpy as np
    print("semantic imports ok")
except Exception as exc:
    print(f"semantic imports unavailable: {exc}")
PY
```

Expected: base tests pass even if semantic imports are unavailable.

### Task 5: Implement `TurbovecSemanticCandidateProvider`

**Objective:** Add real compressed semantic provider, disabled by default.

**Files:**

- Create: `src/agent_memory_os/providers/__init__.py`
- Create: `src/agent_memory_os/providers/turbovec.py`
- Test: `tests/test_turbovec_provider.py`

**Required implementation details:**

- Use `IdMapIndex` external IDs as uint64 only.
- Convert uint64 IDs back to `memory_id` before returning candidates.
- Never return authoritative content from vector sidecar.
- Use `np.ascontiguousarray(allowed_ids, dtype=np.uint64)` for allowlists.
- Detect mapping collisions.
- Provide graceful disabled state if dependency import fails.

**Verification:**

```bash
PYTHONPATH=src python3 -m pytest tests/test_turbovec_provider.py -q
PYTHONPATH=src python3 -m pytest -q
```

Expected: tests pass or turbovec tests skip cleanly if optional dependency is absent.

### Task 6: Add vector rebuild lifecycle

**Objective:** Rebuild disposable turbovec index from SQLite without mutating memories.

**Files:**

- Modify: `src/agent_memory_os/client.py`
- Modify: `src/agent_memory_os/db.py`
- Modify/Create: `src/agent_memory_os/providers/turbovec.py`
- Test: `tests/test_vector_rebuild.py`

**Steps:**

1. Extend `MemoryClient.rebuild_indexes()` to call optional provider rebuild.
2. Build vector index into `vector/build-<timestamp>/`.
3. Verify count parity.
4. Atomic swap to `vector/current` only after validation.
5. Keep previous index for rollback.
6. Run no-data-loss test.

Expected: dropping/rebuilding vector index changes no rows in `memories`.

### Task 7: Add shadow benchmark command/report

**Objective:** Produce evidence before any production use.

**Files:**

- Modify/Create: `src/agent_memory_os/shadow_mode.py`
- Create: `scripts/run_turbovec_shadow_benchmark.py`
- Create: `docs/golden-recall/README.md`

**Steps:**

1. Define golden query fixture format.
2. Run legacy retrieval and candidate retrieval.
3. Log JSONL comparison records.
4. Summarize recall, precision, latency, leakage, no-go counts.
5. Ensure no unauthorized content is written into logs.

Expected output summary keys:

```json
{
  "queries": 500,
  "recall_at_10": 0.96,
  "precision_at_10": 0.91,
  "p99_candidate_latency_ms": 180,
  "acl_leakage_count": 0,
  "expired_hit_count": 0,
  "go_no_go": "go"
}
```

### Task 8: Document production activation decision

**Objective:** Seal the decision only after evidence exists.

**Files:**

- Update: `docs/hermes-activation-gates.md`
- Update: `PROJECT_STATUS.md`
- Optional Create: `docs/adr/ADR-XXXX-turbovec-semantic-provider.md`

**Steps:**

1. Add turbovec as candidate/shadow-only until gates pass.
2. Link benchmark artifacts.
3. Record rollback command.
4. Mark status as `Candidate`, not `SEALED`, until tests + shadow evidence exist.

---

## 6. NO-GO conditions

Any one of these blocks production/default use:

1. ACL leakage > 0.
2. Expired memory appears in search, context pack, report, or shadow logs.
3. Vector sidecar content bypasses SQLite authoritative rejoin.
4. Vector ID or chunk ID replaces durable `memory_id`.
5. Index rebuild mutates or deletes rows in `memories`.
6. Rebuild failure makes the memory database appear empty.
7. Production prompt injection occurs before shadow validation.
8. Golden recall < 0.95 for factual/golden queries.
9. p99 candidate latency > 500ms.
10. Semantic noise evicts authoritative/core memory under context budget stress.
11. Rollback cannot restore FTS/fallback-only operation.
12. Shadow/debug/candidate logs expose unauthorized private content.

---

## 7. Project adoption recommendation

Adopt `turbovec` in three phases:

### Phase A: Research-to-project landing

- Add this plan to `docs/plans/`.
- Keep production behavior unchanged.
- Open implementation work from Task 1 only.

### Phase B: Shadow candidate

- Implement provider abstraction.
- Add fake semantic security tests.
- Add optional turbovec backend.
- Run golden recall and ACL red-team fixtures.

### Phase C: Operational candidate

- Add vector rebuild lifecycle.
- Add shadow benchmark summaries.
- Validate rollback.
- Only then propose canary/default activation.

Final recommendation:

```text
turbovec is suitable for AgentMemoryOS as a compressed semantic candidate sidecar.
It is not suitable as a database, ACL authority, or production prompt source until all gates pass.
```
