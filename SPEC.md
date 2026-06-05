# AgentMemoryOS SPEC v0.2.1

## Product thesis

AgentMemoryOS is a local-first, open memory runtime for AI agents. It separates long-term memory from the LLM context window and retrieves only relevant, budgeted memory snippets per task.

## Problem

Agents need durable facts, preferences, project conventions, and operational lessons. Current prompt-injected memory blocks are small and frequently overflow. Cloud memory platforms are useful but introduce latency, cost, dependency, and privacy tradeoffs.

## Architecture

```text
User / Agent query
  -> query planner
  -> scope + ACL filter
  -> hot cache lookup
  -> SQLite FTS5 retrieval
  -> optional vector retrieval
  -> rerank by relevance + importance + confidence + freshness
  -> context budget allocator
  -> prompt-ready context pack
```

## Memory schema

Required fields:

- `id`: stable memory ID.
- `owner`: canonical user/profile/team owner, e.g. `bastet-agent`.
- `scope`: `user`, `agent`, `project`, `team`, or `global`.
- `type`: `preference`, `fact`, `procedure`, `environment`, `decision`, `warning`, or `note`.
- `content`: canonical memory text.
- `summary`: short recall label.
- `tags`: list of topic labels.
- `visibility`: allowed agents/profiles; empty means owner-only/global rules.
- `source`: JSON source metadata.
- `confidence`: 0.0 to 1.0.
- `importance`: 0.0 to 1.0.
- `created_at`, `updated_at`, `expires_at`.
- `decay_policy`: `none`, `linear`, or `exponential`; soft scoring only.
- `decay_half_life_days`: positive float used by linear/exponential decay.
- `last_accessed_at`, `access_count`: reinforcement metadata; explicit update flow is planned.
- `pinned`: disables decay but does not bypass ACL or expiration.

## Expiration, decay, and ranking

AgentMemoryOS keeps hard safety filters separate from soft retrieval ranking:

1. **ACL / visibility hard gate**: unauthorized memories are excluded before ranking.
2. **Expiration hard gate**: `expires_at <= now` is excluded from search and context packs.
3. **Decay soft score**: stale but still-valid memories receive a freshness multiplier.
4. **Pinned safety**: pinned memories keep `freshness_factor = 1.0`, but still obey ACL and `expires_at`.

Initial v0.2 formula:

```text
effective_score = text_score
                * (0.45 + 0.35 * importance + 0.20 * confidence)
                * freshness_factor
                * reinforcement_factor
```

Freshness:

```text
none or pinned: 1.0
linear:         max(0.0, 1 - age_days / half_life_days)
exponential:    0.5 ** (age_days / half_life_days)
```

Reinforcement:

```text
min(1.25, 1.0 + log1p(access_count) * 0.03)
```

## MVP storage

- `memories` table for structured data.
- `memories_fts` FTS5 virtual table for keyword retrieval.
- In-process LRU cache for search/context packs.

## v0.2.1 Retrieval Foundation contract

AgentMemoryOS treats raw memories and retrieval indexes as separate layers:

```text
SQLite memories table = durable source of truth
FTS5 index            = disposable lexical candidate provider
Future vector index   = disposable semantic candidate provider
Fallback provider     = bounded safety net, never storage
Context pack          = downstream allocator, never storage
```

Safe retrieval pipeline:

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

Retrieval safety invariants:

- `memory_id` is the durable join key across all providers.
- Backend-specific ids, vector row ids, chunk ids, and raw ranks must not replace memory identity.
- Semantic retrieval must union with lexical/fallback candidates rather than replace them.
- Zero-hit fallback may surface pinned/recent/core candidates, but only after ACL and `expires_at` hard gates.
- Dropping or rebuilding FTS/vector indexes must not delete or mutate rows in `memories`.
- Index rebuild must preserve memory ids and metadata, including `visibility`, `source`, `expires_at`, `decay_policy`, `confidence`, `importance`, and `pinned`.

## Context budget policy

The context pack builder uses an approximate token count of `ceil(chars / 4)` and stops before `max_tokens`. This is deliberately conservative and dependency-free for MVP. Future versions can use tokenizer-specific counters.

## MCP tools planned

- `memory_add`
- `memory_search`
- `memory_get`
- `memory_update`
- `memory_forget`
- `memory_consolidate`
- `memory_context_pack`

## Safety rules

- Do not store raw secrets by default.
- Prefer source-linked, high-confidence facts over inferred facts.
- Use expiration/stale markers for volatile project state.
- Keep audit metadata for memory changes.
