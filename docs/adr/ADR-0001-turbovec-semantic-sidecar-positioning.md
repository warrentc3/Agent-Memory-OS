# ADR-0001: turbovec as Disposable SemanticCandidateProvider Sidecar

**Status:** Accepted for positioning; **not** accepted for production prompt influence
**Date:** 2026-06-08
**Scope:** AgentMemoryOS v0.3.1 Shadow Evidence & Migration Safety
**Runtime stance:** `production_injection=false`
**Shadow profile scope:** explicitly limited to `neo` and `mizuki` unless a later gate changes the allowlist

---

## 1. Decision

`turbovec` may be evaluated and implemented only as a **disposable `SemanticCandidateProvider` / vector sidecar**.

It is allowed to provide semantic candidate identity and score metadata. It is not allowed to become the source of truth, ACL authority, memory ID authority, prompt-injection authority, or replacement for SQLite/FTS5.

Decision summary:

- **GO:** provider-abstraction refactor.
- **GO:** fake semantic-provider safety tests before real vector integration.
- **GO:** optional `turbovec` backend, disabled by default, for local spike / benchmark / shadow evidence.
- **NO-GO:** direct production prompt injection before shadow evidence, golden recall, ACL, expiry, rollback, and product/safety gates pass.
- **NO-GO:** claiming v0.4 Memory Resonance, active canary, production injection, or all-profile activation from this work.

This ADR formalizes the Neo engineering view and Mizuki product/safety/audit sign-off for the sidecar positioning only. It does not authorize production activation.

---

## 2. Non-negotiable safety boundary

`turbovec` may return only candidate IDs and semantic score metadata.

It must never return prompt-ready memory content.

Required pipeline:

```text
query
  -> FTS5CandidateProvider
  -> TurbovecSemanticCandidateProvider
  -> PinnedRecentFallbackProvider
  -> merge/dedupe by stable memory_id
  -> authoritative SQLite rejoin
  -> requester-aware ACL hard gate
  -> expires_at hard gate
  -> metadata/freshness/reinforcement scoring
  -> context budget allocator
  -> final ACL/expiry re-check before prompt insertion
```

Hard invariants:

1. SQLite `memories` remains the only durable source of truth.
2. Stable SQLite `memory_id` remains the durable join key.
3. `turbovec` vector IDs are backend-local and disposable.
4. `turbovec` allowlists are performance hints only, not security controls.
5. Every vector candidate must rejoin through SQLite before content can be used.
6. ACL and expiry are hard gates, not score modifiers.
7. Semantic score may influence relevance after hard gates, but can never decide who is allowed to see a memory.
8. Explicit recall / pinned authoritative memory / ACL hard gate outrank semantic similarity.

Activation clause:

```text
Semantic Provider = index suggestion only.
It decides what may be relevant.
It never decides who may see it.
```

---

## 3. Shadow logging and audit constraints

Shadow and debug output must avoid private content leakage.

Allowed shadow log fields:

- `request_hash`
- `provider`
- `candidate_ids`
- `sqlite_filter_result`
- `acl_result_counts`
- `expiry_result_counts`
- `latency_ms`
- `semantic_score`
- `source_reference` or equivalent non-content provenance pointer
- `go_no_go`

Disallowed shadow/debug log content:

- raw private memory content
- unauthorized memory content
- expired memory content
- prompt-ready content from vector sidecar
- any log shape that links unauthorized private content to a requester-visible trace

If an unauthorized candidate is produced by `turbovec`, it may be counted as filtered/rejected evidence, but its content must not be logged or exposed.

Debug explainability requirement:

- When semantic recall contributes to a selected candidate, debug mode must be able to report the semantic provider, semantic score, selected `memory_id`, and source reference after SQLite rejoin and ACL/expiry gates.
- If a user or auditor questions why a memory was recalled, the system must support traceability from final selected memory back to provider contribution without exposing unauthorized content.

---

## 4. Neo engineering view

Scope:

- Build a provider abstraction before adding `turbovec`.
- Preserve existing FTS5 / authority / fallback behavior during the refactor.
- Add fake semantic-provider tests before integrating the real backend.
- Keep `turbovec` as an optional extra, disabled by default.
- Make provider failure degrade safely to FTS5 + authority/fallback.

Evidence sources:

- Current project validation plan: `docs/plans/20260608_174539-turbovec-semantic-provider-validation.md`
- Existing AgentMemoryOS activation-gate stance: `docs/hermes-activation-gates.md`
- Required baseline commands:

```bash
PYTHONPATH=src python3 -m pytest -q
PYTHONPATH=src python3 scripts/verify_acl_identities.py --home /tmp/agent-memory-os-semantic-acl --identity all
```

Engineering gates:

- Full tests pass before and after provider abstraction.
- Fake semantic provider proves private, expired, duplicate, noisy, and orphan candidates cannot bypass SQLite rejoin.
- `turbovec` import failure disables semantic retrieval gracefully.
- `IdMapIndex` external IDs map back to stable `memory_id`s with collision detection.
- Python allowlists use C-contiguous uint64 arrays:

```python
allowed = np.ascontiguousarray(allowed_ids, dtype=np.uint64)
```

Target metrics before any production-influence discussion:

- factual/golden recall target: `recall@K >= 0.95`
- p99 candidate latency target: `<= 200ms`
- p99 candidate latency pause threshold: `> 500ms`
- ACL leakage count: `0`
- expired hit count: `0`
- forbidden substring hit count: `0`

---

## 5. Mizuki product / safety / audit view

Scope:

- Confirm the semantic sidecar safety boundary.
- Require auditability without private-content logging.
- Add product-facing NO-GO gates beyond raw engineering metrics.

Safety requirements:

- `turbovec` provides candidate IDs only.
- All IDs must rejoin SQLite and pass ACL/expiry hard gates.
- Private content must not appear in shadow logs.
- Unauthorized candidate content must not be linked to requester-visible logs.
- Semantic provider weight must not override explicit recall or ACL hard gates.

Product/audit requirements:

- Debug mode must expose semantic score and source reference for authorized selected memories.
- The user/auditor must be able to trace why semantic recall contributed to a memory selection.
- Documentation must clearly say the provider is an index suggestion, not memory authority.

Additional Mizuki NO-GO gates:

1. **Zero Leakage:** in 1000 randomized permission-combination tests, no unauthorized content may enter context after SQLite filtering. Required result: `leak_count = 0`.
2. **Consistency Check:** the same query across controlled time windows must keep candidate-set drift within an accepted threshold so semantic recall does not create unstable agent identity. The exact drift threshold must be specified in the benchmark fixture before production influence.
3. **One-click Killswitch:** `AGENT_MEMORY_SEMANTIC_PROVIDER=off` or equivalent must fully return to SQL/FTS/fallback mode within 1 second and must not affect existing memory reads/writes.

---

## 6. Cross-review resolution

### Neo review of Mizuki constraints

Accepted.

The product/safety requirements are compatible with the provider-sidecar architecture if the implementation enforces:

- candidate IDs only from `turbovec`
- mandatory SQLite rejoin
- ACL/expiry hard gates after rejoin
- final ACL/expiry re-check before prompt insertion
- no private content in shadow/debug logs
- killswitch fallback to FTS5 + authority/fallback

### Mizuki review of Neo implementation path

Accepted with gates.

The engineering path is acceptable only if tests prove semantic candidates cannot bypass:

- SQLite source-of-truth rejoin
- requester-aware ACL
- expiry filtering
- duplicate suppression
- context-budget arbitration
- shadow-log privacy constraints

Benchmark success alone is not sufficient for production activation. The sidecar must pass safety/audit gates and remain under `production_injection=false` until explicit cutover approval.

---

## 7. Implementation sequence

1. **Provider foundation**
   - Add `Candidate` and `CandidateProvider` abstractions.
   - Keep existing behavior unchanged.
   - Run full tests and ACL verifier.

2. **Fake semantic safety tests**
   - Inject allowed, unauthorized private, expired, duplicate, noisy, and orphan candidates.
   - Prove no semantic candidate can bypass SQLite / ACL / expiry / context budget.

3. **Optional turbovec backend**
   - Add optional dependency extra only.
   - Keep backend disabled by default.
   - Return candidate IDs and scores only.
   - Detect ID-mapping collisions.

4. **Index lifecycle**
   - Build vector index from SQLite only.
   - Use local runtime sidecar storage.
   - Prefer blue/green index directories and atomic swap.
   - Preserve previous index for rollback.
   - Never mutate `memories` during vector rebuild.

5. **Shadow benchmark / evidence pack**
   - Compare FTS5 only, turbovec only for measurement, FTS5+turbovec union, and full retrieval+budget path.
   - Emit persisted evidence only; do not rerun retrieval inside read-only evidence packs.
   - Confirm `production_injection=false`.

6. **Activation decision**
   - Update `docs/hermes-activation-gates.md` and `PROJECT_STATUS.md` only after evidence exists.
   - Keep status as candidate/shadow-only until all gates pass.

---

## 8. NO-GO conditions

Any one condition blocks production/default use or prompt influence:

1. ACL leakage count > 0.
2. Expired memory appears in search, context pack, report, shadow log, or debug trace.
3. Vector sidecar returns prompt-ready content.
4. Vector candidate bypasses SQLite authoritative rejoin.
5. Vector ID or chunk ID replaces durable `memory_id`.
6. Vector index rebuild mutates, deletes, or hides SQLite `memories` rows.
7. Rebuild failure makes the memory database appear empty.
8. Production prompt injection occurs before shadow validation.
9. Golden/factual recall is below target.
10. p99 candidate latency exceeds pause threshold.
11. Semantic noise evicts authoritative/core memory under context-budget stress.
12. Rollback cannot restore FTS/fallback-only operation.
13. Shadow/debug/candidate logs expose unauthorized private content.
14. Killswitch cannot disable semantic provider within the accepted operational window.
15. Candidate-set drift exceeds the accepted consistency threshold once defined.

---

## 9. Active Sync sign-off

- **Neo engineering view:** implementation path OK for provider abstraction, fake safety tests, optional disabled-by-default sidecar, and shadow-only benchmark.
- **Mizuki product/safety view:** safety gates OK for sidecar positioning, with zero-leakage, no-private-content logging, explainability, consistency, and killswitch requirements.
- **Unresolved positioning questions:** none.
- **Implementation thresholds still to define before production influence:** candidate-set drift threshold and final benchmark fixture parameters.
- **Final decision:** `turbovec` positioning is accepted as a disposable semantic candidate sidecar only. Production prompt influence remains NO-GO until v0.3.1 shadow evidence and activation gates pass.

---

## 10. References

- `docs/plans/20260608_174539-turbovec-semantic-provider-validation.md`
- `docs/hermes-activation-gates.md`
- `docs/HISTORY.md`
