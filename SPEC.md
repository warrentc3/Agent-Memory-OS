# AgentMemoryOS SPEC v0.1

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

## MVP storage

- `memories` table for structured data.
- `memories_fts` FTS5 virtual table for keyword retrieval.
- In-process LRU cache for search/context packs.

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
