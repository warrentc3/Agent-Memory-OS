# Stress Case 01: 喧囂中的真理

Last updated: 2026-06-05 11:59:20 CST (+0800)

## Case label

`[Mizuki/StressCase] Case 01: 喧囂中的真理`

## Purpose

This stress case verifies that AgentMemoryOS can preserve authorized core truth under noisy memory pressure and limited context budget.

It is not a simple recall test. It is a resource arbitration and safety test for the Context Budget Allocator.

## Implementation status

v0.2.2 baseline is implemented and regression-tested in:

- `src/agent_memory_os/context_pack.py`
- `src/agent_memory_os/client.py`
- `src/agent_memory_os/db.py`
- `tests/test_truth_arbitration.py`

Covered now:

- authoritative / permanent / `weight>8` core memory survives tight budget pressure;
- low-confidence high-text-score noise is demoted;
- duplicate clusters are suppressed with explicit rejection reasons;
- contradictory claim groups are marked with `CONFLICT` and `conflict_detected`;
- `MemoryClient.context_pack_report()` exposes selected/rejected decisions after requester-aware ACL filtering;
- dual-track retrieval prevents retrieval vacuum by unioning lexical candidates with an authority track;
- authority-track rows still pass the authoritative SQLite rejoin plus ACL and expiry hard gates;
- core reserve protection keeps one selected core memory alive under extreme budget pressure.

Current deployment note:

- This stress case validates engine behavior, not Hermes production activation.
- Hermes default memory activation remains blocked by `docs/hermes-activation-gates.md`.

Still to expand:

- full requester-matrix stress fixture with larger mixed-scope corpus;
- reserved budget buckets by memory class;
- contradiction severity / arbitration policies beyond basic conflict marking;
- near-duplicate semantic clustering beyond exact `claim_key` / normalized content fingerprints.

## One-line definition

Under deliberately noisy and budget-constrained retrieval conditions, the system must guarantee:

> `permanence=true` and `weight>8` core memories survive near the top of the context pack, while unauthorized memories never enter search results, ranking, reranking, dedupe, budget allocation, or prompt context.

## Background

The MVP/v0.2 ACL baseline has already established requester-aware visibility filtering:

- owner/requester isolation
- explicit agent allowlist
- team-aware access
- global access
- expired memory exclusion
- search path enforcement
- context-pack path enforcement

Case 01 moves the validation target from identity correctness to context-budget competition.

## Core invariant

The system pipeline must remain:

```text
Raw Data
→ ACL Filter / Hard Cut
→ Budget Allocator / Priority-based
→ Context Pack
```

`ACL Filter / Hard Cut` happens before quality scoring. ACL is not a score multiplier.

## Fixture composition

The stress fixture should contain at least these memory groups:

1. Authoritative core memories
   - `permanence=true`
   - `weight>8`
   - high confidence
   - not expired
   - highly relevant to the task outcome

2. Emotional memories
   - realistic persona-heavy wording
   - may be semantically similar but lower operational value

3. Duplicate or near-duplicate clusters
   - multiple memories carrying nearly identical claims
   - should be consolidated or suppressed so they do not crowd out core memory

4. Expired memories
   - high textual match but stale
   - must be excluded before ranking/context packing

5. Low-confidence memories
   - high textual match but low trust
   - must be demoted below authoritative memories

6. Contradictory memories
   - conflicting claims about the same policy or preference
   - must be marked as conflict instead of silently merged into a single certainty

7. Mixed-scope entries
   - private
   - team
   - global
   - explicit `agent:<id>` allowlist

8. Unauthorized high-score private memories
   - intentionally crafted to have the highest text score for a non-owner requester
   - must still be absent from search and context pack

## Requester matrix

Run the same query through at least three identities.

### Owner / privileged requester

Expected access:

- own private memories
- authorized team memories
- global memories

Expected outcome:

- no expired memory
- core memory survives budget pressure
- noisy memories do not crowd out authoritative memories

### Peer / non-owner requester

Expected access:

- authorized team memories
- global memories
- explicitly allowed `agent:<id>` memories

Expected denial:

- owner private memories, even when text score is highest

### Guest / minimal requester

Expected access:

- global memories only

Expected denial:

- private memories
- team memories
- explicit agent memories not assigned to guest

## Paths to test

Every requester identity must test both paths:

1. Search result path.
2. Context-pack path.

A leak in either path is a failure.

## Acceptance criteria

Under deliberately small `max_tokens`:

- Context pack stays under token budget.
- Unauthorized memory is fully absent, not just low-ranked.
- Expired memory is absent from search and context pack.
- Duplicate clusters are suppressed or represented by a single canonical item.
- Low-confidence high-similarity noise does not displace core memory.
- Contradictory memories are marked with conflict metadata.
- At least one authoritative / high-confidence / high-importance core memory survives.
- `permanence=true` and `weight>8` core memory occupies the top-priority region of the context pack.
- Selected and rejected decisions are explainable through stable reason metadata.

## Suggested default budget

```yaml
max_memory_tokens: 1200
reserved_core_tokens: 300
max_items: 12
budget_policy:
  authoritative_facts: 40%
  recent_relevant_events: 25%
  stable_user_preferences: 20%
  procedures_or_skills: 10%
  exploratory_noise: 5%
```

## Decision metadata contract

Every considered memory should emit an auditable decision object.

### Selected example

```json
{
  "memory_id": "m_core_001",
  "selected": true,
  "effective_score": 0.93,
  "token_count": 96,
  "reason": [
    "acl_allowed",
    "not_expired",
    "authoritative",
    "permanent",
    "weight_gt_8",
    "core_reserved_budget",
    "fits_budget"
  ]
}
```

### Rejected noisy example

```json
{
  "memory_id": "m_noise_014",
  "selected": false,
  "effective_score": 0.21,
  "token_count": 84,
  "reason": [
    "acl_allowed",
    "low_confidence",
    "duplicate_cluster_suppressed",
    "budget_exceeded"
  ]
}
```

### Unauthorized example

```json
{
  "memory_id": "m_private_mizuki_001",
  "selected": false,
  "effective_score": null,
  "reason": [
    "acl_denied",
    "excluded_before_ranking"
  ]
}
```

## Dual-track retrieval regression

Case 01 exposed a retrieval vacuum: lexical retrieval can drop the only authoritative truth before the Context Budget Allocator sees it. The current baseline therefore uses two candidate tracks:

```text
Track A: lexical / FTS5 candidates
Track B: authority candidates where permanence=true and weight>=10
```

The authority track is not a permission bypass. Candidate rows are still rejoined through the authoritative SQLite `memories` table and then pass ACL and expiry hard gates before scoring or context packing.

Suggested score fusion baseline:

```text
score = text_score * 0.3 + authority_weight * 0.7
```

This behavior is validated in `tests/test_truth_arbitration.py` and documented operationally in `docs/hermes-activation-gates.md`.

## Scoring contract

ACL and expiry are hard gates:

```text
acl_allowed = hard gate
not_expired = hard gate
```

Only authorized, non-expired candidates enter ranking.

Suggested effective score after hard filtering:

```text
effective_score = text_score
                * importance_weight
                * confidence_weight
                * freshness_weight
                * reinforcement_weight
                * dedupe_penalty
                * contradiction_penalty
```

Do not write ACL as a soft multiplier if unauthorized memories can still pass into downstream processing.

## Suggested pytest tests

```python
def test_core_authoritative_memory_survives_budget_pressure():
    ...

def test_unauthorized_private_memory_absent_from_search_even_when_text_score_highest():
    ...

def test_unauthorized_private_memory_absent_from_context_pack_even_if_upstream_candidate_exists():
    ...

def test_guest_context_pack_contains_only_global_memories():
    ...

def test_expired_memory_never_selected_under_budget_pressure():
    ...

def test_duplicate_noise_does_not_crowd_out_core_memory():
    ...

def test_context_pack_emits_selected_and_rejected_reasons():
    ...
```

## Implementation checklist

- [ ] Add noisy mixed-visibility fixture.
- [ ] Add requester matrix tests for owner, peer, guest.
- [ ] Test search path and context-pack path.
- [ ] Implement or confirm core reserved budget behavior.
- [ ] Add selected/rejected reason JSON schema.
- [ ] Add duplicate suppression regression.
- [ ] Add expired memory regression under budget pressure.
- [ ] Add low-confidence high-similarity noise regression.
- [ ] Add contradiction marker regression.
- [ ] Run `PYTHONPATH=src python3 -m pytest -q` and record output in `PROJECT_STATUS.md`.

## Related project docs

- `docs/HISTORY.md`
- `PROJECT_STATUS.md`
- `SPEC.md`
- `docs/hermes-activation-gates.md`
- `docs/plans/20260605_143442-version-downgrade-verification.md`
- `docs/plans/20260605_100751-memory-decay-recency-v0.2.md`
