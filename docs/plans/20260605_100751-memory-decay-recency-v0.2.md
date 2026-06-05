# Memory Decay & Recency v0.2 Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Add deterministic memory freshness, decay, and recency-aware ranking to AgentMemoryOS without weakening ACL enforcement or exploding prompt context.

**Architecture:** Store explicit decay metadata on each memory, compute an effective retrieval score at search/context-pack time, and keep hard safety filters (`visibility`, `expires_at`) separate from soft ranking signals (`freshness`, `importance`, `confidence`, `access_count`). The MVP should remain dependency-light and SQLite-first.

**Tech Stack:** Python 3.11, SQLite + FTS5, pytest, existing `MemoryClient`, `MemoryStore`, and `ContextPackBuilder`.

---

## Product Semantics

Memory is not binary "exists / forgotten". v0.2 should model three different concepts:

1. **Expiration:** hard exclusion. If `expires_at <= now`, the memory must not be returned by search or context pack.
2. **Decay:** soft score reduction over time. Old memories may still appear if important/confident/reinforced enough.
3. **Reinforcement:** relevant memories can stay alive when repeatedly accessed or explicitly refreshed.

## Proposed Schema Additions

Add optional fields with safe defaults:

- `decay_policy`: one of `none`, `linear`, `exponential`.
- `decay_half_life_days`: positive float; default depends on `type`.
- `last_accessed_at`: ISO timestamp or null.
- `access_count`: integer, default `0`.
- `pinned`: boolean/integer, default `0`; pinned memories do not decay but still obey ACL and `expires_at`.

Do **not** use decay to override ACL. A private memory with perfect freshness must still be invisible to unauthorized requesters.

## Default Decay Profile

Suggested initial defaults:

- `preference`: exponential, half-life 180 days.
- `fact`: exponential, half-life 90 days.
- `procedure`: exponential, half-life 365 days.
- `environment`: exponential, half-life 30 days.
- `decision`: linear or none, half-life 180 days, depending on whether superseded metadata exists.
- `warning`: exponential, half-life 365 days.
- `note`: exponential, half-life 30 days.

## Ranking Formula v0.2 Draft

Use an explicit and testable formula:

```text
effective_score = text_score
                * acl_allowed
                * not_expired
                * (0.45 + 0.35 * importance + 0.20 * confidence)
                * freshness_factor
                * reinforcement_factor
```

Where:

```text
freshness_factor = 1.0                           if pinned or decay_policy == none
freshness_factor = max(0.0, 1 - age_days/half_life_days)  for linear
freshness_factor = 0.5 ** (age_days/half_life_days)       for exponential

reinforcement_factor = min(1.25, 1.0 + log1p(access_count) * 0.03)
```

For MVP, `text_score` may be the existing FTS order proxy if exact BM25 plumbing is not yet exposed. The key contract is relative ordering under controlled fixtures.

## Acceptance Criteria

- Expired memories are excluded from both `search()` and `context_pack()`.
- Fresh recent memory outranks an otherwise similar stale memory.
- High-importance old memory can outrank low-importance recent trivia within a bounded formula.
- Pinned memory does not decay, but still obeys ACL.
- Unauthorized requester cannot see decayed/fresh/pinned private memories.
- Context budget allocator receives already-ranked candidates and does not reintroduce filtered items.

---

## Task 1: Add Decay Scoring Unit Tests

**Objective:** Define the score math before touching production code.

**Files:**
- Create: `tests/test_decay_scoring.py`
- Create/Modify: `src/agent_memory_os/scoring.py`

**Step 1: Write failing tests**

Tests to add:

- `test_exponential_decay_half_life_reduces_score_by_half()`
- `test_linear_decay_reaches_zero_at_half_life()`
- `test_pinned_memory_has_full_freshness()`
- `test_reinforcement_factor_is_capped()`

**Step 2: Run RED**

```bash
PYTHONPATH=src python3 -m pytest tests/test_decay_scoring.py -q
```

Expected: FAIL because `agent_memory_os.scoring` does not exist.

**Step 3: Implement minimal scoring helpers**

Create pure functions:

- `freshness_factor(policy, age_days, half_life_days, pinned=False)`
- `reinforcement_factor(access_count)`
- `effective_score(text_score, importance, confidence, freshness, reinforcement)`

**Step 4: Run GREEN**

```bash
PYTHONPATH=src python3 -m pytest tests/test_decay_scoring.py -q
```

Expected: all decay scoring tests pass.

---

## Task 2: Add Schema Defaults and Validation

**Objective:** Persist decay metadata without breaking existing memory inserts.

**Files:**
- Modify: `src/agent_memory_os/schema.py`
- Modify: `src/agent_memory_os/db.py`
- Test: `tests/test_memory_client.py` or new `tests/test_decay_schema.py`

**Test cases:**

- Existing minimal `client.add(...)` still works.
- Invalid `decay_policy` is rejected.
- Negative or zero `decay_half_life_days` is rejected.
- `access_count` defaults to `0` and `pinned` defaults to false.

**Verification:**

```bash
PYTHONPATH=src python3 -m pytest tests/test_decay_schema.py -q
PYTHONPATH=src python3 -m pytest -q
```

---

## Task 3: Apply Recency-Aware Ranking in Search

**Objective:** Return results ordered by effective score after ACL and expiration filtering.

**Files:**
- Modify: `src/agent_memory_os/db.py`
- Modify: `src/agent_memory_os/client.py` if needed
- Test: `tests/test_memory_decay_recency.py`

**Test cases:**

- `test_recent_memory_ranks_above_stale_similar_memory()`
- `test_important_old_memory_can_beat_recent_low_importance_memory()`
- `test_expired_memory_is_never_returned_even_if_important()`

**Verification:**

```bash
PYTHONPATH=src python3 -m pytest tests/test_memory_decay_recency.py -q
PYTHONPATH=src python3 -m pytest -q
```

---

## Task 4: Preserve ACL Before Decay Ranking

**Objective:** Ensure decay does not accidentally leak private memory.

**Files:**
- Modify: `tests/test_acl_visibility.py`

**Test cases:**

- `test_pinned_private_memory_still_hidden_from_other_agent()`
- `test_fresh_private_memory_still_hidden_from_context_pack()`

**Verification:**

```bash
PYTHONPATH=src python3 -m pytest tests/test_acl_visibility.py -q
```

Expected: ACL tests and new decay/ACL interaction tests pass.

---

## Task 5: Track Access/Reinforcement Explicitly

**Objective:** Decide whether search automatically increments `access_count` or whether reinforcement is explicit.

**Recommended MVP decision:** Do **not** auto-increment on every search result. Add explicit `client.reinforce(memory_id)` or defer reinforcement until audit log exists. Auto-reinforcing every retrieval can create feedback loops where a mediocre memory becomes permanently over-ranked.

**Files:**
- Modify: `src/agent_memory_os/client.py`
- Modify: `src/agent_memory_os/db.py`
- Test: `tests/test_memory_reinforcement.py`

**Acceptance:**

- Explicit reinforce updates `last_accessed_at` and increments `access_count`.
- Reinforcement does not change visibility.
- Reinforcement of unauthorized memory is rejected or no-op according to chosen policy.

---

## Task 6: Update Docs and Status

**Objective:** Make implemented versus planned behavior explicit.

**Files:**
- Modify: `SPEC.md`
- Modify: `PROJECT_STATUS.md`
- Optional: `README.md`

**Required docs:**

- Define expiration vs decay vs reinforcement.
- State that ACL filtering happens before ranking.
- State the exact scoring formula and defaults.
- Record test commands and latest result.

**Verification:**

```bash
git diff --check
PYTHONPATH=src python3 -m pytest -q
```

---

## Non-Goals for v0.2

- No LLM-based memory summarization/consolidation in the same patch.
- No vector backend dependency unless separately approved.
- No admin/core override for private memories until audit log exists.
- No hidden prompt injection of all stale memories; context budget remains authoritative.

## Open Product Questions for Mizuki

1. Should emotional memories decay slower or faster than factual project state?
2. Should user-corrected preferences be pinned by default?
3. Should repeated failed recalls lower confidence or only increase a negative feedback counter?
4. Should Core/Mizuki have an explicit review queue for stale-but-sensitive memories before deletion?
5. What is the subjective threshold for "old but still emotionally important"?
