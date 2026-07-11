# Agent Memory OS SPEC

Current through v0.9.x. Sections are additive by milestone.

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

## v0.2.3 Memory association and repeated recall

Associative recall lets memories that share no query terms with the request
still surface because they are linked to direct hits — the difference between
"search" and "remembering".

### Authoritative links

- `memory_links` is an authoritative SQLite table next to `memories`; links
  survive disposable index rebuilds.
- Relations: `related_to`, `supersedes`, `caused_by`, `derived_from`,
  `co_recalled`. Weight is clamped to `[0.0, 1.0]`.
- Traversal is undirected for resonance recall.

### Resonance retrieval track

Search fuses three tracks: FTS5 relevance, authority recall, and resonance
expansion. Resonance takes the direct hits as seeds and walks `memory_links`
up to `resonance_hops` (default 1):

```text
activation = seed_score * edge_weight * 0.6 ** hop
```

Safety invariants:

- Every traversed node passes the same ACL and `expires_at` hard gates as
  direct hits before scoring.
- Requester-invisible or expired nodes are dropped before entering the
  frontier: they are both unreturnable and untraversable. A private memory can
  never bridge two public memories for an unauthorized requester, and edge
  existence never leaks through scores.
- Resonance candidates are capped (`MAX_RESONANCE_CANDIDATES = 200`) and can
  be disabled with `resonance_hops = 0`.

### Repeated recall reinforcement and self-correction

`client.record_recall(memory_ids, create_colinks=False, helpful=True)` is the
Hebbian feedback loop: memories recalled (and useful) together get their
`access_count` bumped and every existing link between co-recalled pairs gains
`+0.05` weight (capped at 1.0). With `create_colinks=True`, unlinked pairs get
a weak `co_recalled` edge (`0.2`). Well-worn recall paths therefore resonate
more strongly over time.

`helpful=False` is the self-correction path: the recall misled the agent, so
link weights drop by `0.1`, memory `confidence` drops by `0.05`, and no
reinforcement is recorded.

`context_pack(..., auto_reinforce=True)` / `context_pack_report(...,
auto_reinforce=True)` close the loop automatically: every memory the
arbitration layer selects into the pack is treated as a recall event and
reinforced, so MCP callers do not need to remember to report back.

### Link decay, hub damping, and audit paths

- Edges decay like memories: resonance multiplies edge weight by
  `0.5 ** (days_since_last_activation / 90)`, so associations that stop being
  co-activated fade instead of persisting forever.
- Each frontier node expands only its strongest `8` edges
  (`RESONANCE_MAX_EDGES_PER_NODE`), so hub memories cannot flood the cluster.
- Resonance results carry an auditable path in `reason`:
  `resonance:hop1:via:<seed_id>:<relation>`.
- `supersedes` is directional: when both ends of a `supersedes` edge survive
  the hard gates, the superseded memory's score is multiplied by `0.4` and its
  reason gains `superseded_by:<id>`. Demotion only fires when the requester
  can see the superseding memory.

### Write-time association and the ERA bridge

- `client.add(content, auto_link=True)` creates weak `related_to` edges
  (`0.3`, `source.auto = "fts_similarity"`) from a new memory to its top FTS
  neighbors, so new memories join the graph immediately; co-recall
  reinforcement decides which edges mature.
- `ERATripletIndex.derive_links(min_shared_terms=2, max_term_degree=20)`
  derives `(src_id, dst_id, weight)` pairs from shared ERA terms (hub terms
  skipped), and `client.import_links(pairs)` upserts them as authoritative
  edges — the bridge from the disposable v0.4 prototype into `memory_links`.

### Persisted recall profiles

`recall_profiles` is an authoritative table (`agent_id`, `type_weights`,
`scope_weights`). `client.save_profile(profile)` persists an agent's soul
attributes; `search`/`context_pack` auto-load the stored profile for
`requester_agent_id` when no explicit profile is passed. Profiles remain soft
ranking multipliers only.

### Write-side consolidation

`client.consolidate(owner=None, scope=None)` is the hygiene pass:

1. **Duplicate merge**: memories with identical owner, scope, visibility, and
   normalized content fingerprint collapse into the highest-confidence copy;
   links re-point to the survivor and `access_count` accumulates.
2. **Concept synthesis**: clusters of >= 3 memories connected by strong
   co-recall edges (`weight >= 0.6`, `activation_count >= 3`) with identical
   owner/scope/visibility are synthesized into a concept memory
   (`source.auto = "consolidation"`) with `derived_from` edges back to each
   episode. Everyday retrieval hits the concept; details stay reachable
   through the graph. The pass is idempotent, and clusters spanning different
   visibility are never blended (ACL-safe by construction).

### Multi-agent deployment

The store enables SQLite WAL journal mode and a 5s busy timeout so multiple
agent processes can share one database file; both PRAGMAs degrade gracefully
on filesystems that do not support them.

### Per-agent recall profiles

Different agents have different personas, so they need different memory.
`RecallProfile(agent_id, type_weights, scope_weights)` applies a soft
multiplier (clamped to `[0.25, 2.0]`) to ranking by memory `type`/`scope` —
an engineering agent can lean on `procedure`/`decision` while a companion
agent leans on `preference`/`note`. Profiles re-weight ranking only; they
never bypass ACL or expiry hard gates and never grant visibility.

```python
profile = RecallProfile(agent_id="neo", type_weights={"procedure": 1.5})
client.search(query, requester_agent_id="neo", profile=profile)
client.link(src_id, dst_id, relation="caused_by", weight=0.8)
client.record_recall([mem_a.id, mem_b.id], create_colinks=True)
```

## Context budget policy

The context pack builder uses an approximate token count of `ceil(chars / 4)` and stops before `max_tokens`. This is deliberately conservative and dependency-free for MVP. Future versions can use tokenizer-specific counters.

v0.2.2 adds an auditable Truth Arbitration layer for context packing:

- `build_context_pack_report()` returns both prompt text and `ContextDecision` entries.
- Authoritative / permanent / `source.weight > 8` core memories receive priority under budget pressure.
- Low-confidence noisy memories are demoted even when lexical score is high.
- Duplicate clusters are suppressed using `source.claim_key` when available, otherwise a normalized content fingerprint.
- Contradictory claim groups are detected when records share `source.claim_key` but carry different `source.claim` values; selected pack lines include `CONFLICT`, and decisions include `conflict_detected`.
- Decision reasons are stable strings such as `acl_allowed`, `not_expired`, `authoritative`, `permanent`, `weight_gt_8`, `core_reserved_budget`, `fits_budget`, `budget_exceeded`, and `duplicate_cluster_suppressed`.

Public SDK entry points:

```python
pack = client.context_pack(query, requester_agent_id="neo", max_tokens=1200)
report = client.context_pack_report(query, requester_agent_id="neo", max_tokens=1200)
```

## MCP tools planned

- `memory_add`
- `memory_search`
- `memory_get`
- `memory_update`
- `memory_forget`
- `memory_consolidate`
- `memory_context_pack`
- `memory_link` (implemented in scaffold)
- `memory_recall_feedback` (implemented in scaffold)

## Safety rules

- Do not store raw secrets by default.
- Prefer source-linked, high-confidence facts over inferred facts.
- Use expiration/stale markers for volatile project state.
- Keep audit metadata for memory changes.

## v0.4 Dynamic context orchestration (first slice)

`client.orchestrate_context(task, session_id=None, max_tokens=2000, ...)`
returns a prompt-ready block split across budgeted buckets, in order:

```text
SESSION    8%  pointer to the latest ContextSnapshot for the session
BEDROCK   20%  authority-track constants; repeat every call, dedup-exempt
WARNINGS  14%  proactive: warning memories, importance-ranked top-up
PROCEDURES 12% proactive: procedure memories, importance-ranked top-up
TASK      46%  relevance recall (full retrieval stack), receives all surplus
```

Rules: every bucket passes the same ACL/expiry hard gates; unused budget
flows to the task bucket; with a `session_id`, delivered memory ids are
recorded in `session_recall_log` and excluded from later calls (iterative
deepening) — bedrock and session pointers always repeat. Snapshot rotation in
`run_retention()` archives all but the newest 5 snapshots per session.


## v0.5 Federation & adaptive forgetting (first slice)

- **Negotiated sharing**: `share_memory(memory_id, actor, to_agent|to_team,
  deidentify=False)` — only the owner may grant or revoke; a de-identified
  share creates a scrubbed copy whose provenance exists only in the
  `memory_audit` trail. Sharing never mutates ACL semantics: grants are
  ordinary visibility entries and pass through the same hard gates.
- **Bundle sync**: JSONL bundles carry memories, links, and profiles between
  hosts. Merge rules are deterministic and order-free: memories and profiles
  resolve by `updated_at` (last writer wins on stable ids); links keep the
  strongest weight / highest activation count / latest activation.
- **Adaptive forgetting**: `helpful_count` / `unhelpful_count` accumulate from
  recall feedback; retention recomputes
  `half_life = type_base * clamp(sqrt((1+h)/(1+u)), 0.5, 4)` (bounded to
  7–730 days), so utility telemetry — not just time — shapes the forgetting
  curve. The formula is a pure function of the counters, hence idempotent.


## v0.6–v0.9 Federation mesh, fleet identity, and console

### Mesh federation (v0.7)
- `sync_peers` registry (URL + bearer token) per home; `sync auto` converges
  bidirectionally with every peer using the v0.5 merge rules. Per-peer
  failure isolation; last outcome recorded per peer.
- Peer HTTP transport: `GET /api/sync/export`, `POST /api/sync/import`,
  behind the console token gate. Peer URLs are operator-configured only.

### Link-extraction plumbing (v0.7)
- `consolidate(derive_links=True)` runs the ERA heuristic over all memories;
  `consolidate(link_extractor=fn)` accepts any callable over MemoryRecords
  returning `(src_id, dst_id, weight)`. `make_llm_link_extractor(complete)`
  adapts any LLM completion function with defensive JSON parsing — invalid
  output degrades to zero links, never an exception.

### Agent registry & team ACL (v0.8)
- `agents` table: id, display_name, kind (claude-code|codex|openclaw|hermes|
  custom), teams, notes, last_seen_at. Console Agents tab + `/api/agents`.
- **Team auto-resolution**: the ACL hard gate unions the requester's
  registered teams with any explicit `requester_team_id`. `team:<id>`
  grants therefore reach every member with no per-call wiring; membership
  edits invalidate the per-store team cache immediately.
- Per-agent MCP identity: `AGENT_MEMORY_AGENT_ID` supplies default owner
  and requester identity for all MCP tools and stamps last-seen.
- Team-scoped bundles: `export_bundle(team=…)` carries only that team's
  memories, links with both endpoints inside, and member profiles.

### Fleet configuration & console i18n (v0.9)
- `<home>/agents.toml` declares agents (`[agents.<id>]` with kind/teams);
  applied on every store open. The file is authoritative for listed agents;
  agents it does not list are never touched. Errors fail fast with context.
- The console ships five locales (en, zh-TW, zh-CN, ja, ko): an
  English-keyed dictionary layer over unchanged markup, browser-detected,
  live-switchable, persisted per user.

## v0.11 Federation trust model

Peer sync is no longer all-or-nothing. Each registered peer carries a
**policy** that governs what leaves the machine for it:

- `shared` (default for new peers) — every visibility EXCEPT private
  (`visibility=[]`). Private memories never leave.
- `full` — the entire store, including private memories. For your own trusted
  replica nodes only. Existing peers migrate to `full` so no deployment changes
  behaviour silently.
- `team:<id>` — only that one team/project's shared memory.

Enforcement and invariants:

- The HTTP `GET /api/sync/export` endpoint is **always `shared`-scoped**: it
  cannot authenticate which peer is pulling, so it never serves private
  memories. Full private replication happens only over the authenticated push
  leg (`POST /api/sync/import`) between own `full`-policy nodes.
- **Tombstones** (migration 9): `delete()` and `purge_owner()` record a
  tombstone `(id, deleted_at)` that travels in the bundle. On import a tombstone
  deletes a local row no newer than `deleted_at` and is retained so the deletion
  re-propagates and blocks resurrection.
- **Provenance & anti-impersonation**: an import from a semi-trusted peer
  (`trusted=False`, i.e. any non-`full` policy) records `source.synced_from` on
  each row and may NOT create a new memory whose `owner` is one of the importing
  host's locally-registered agents.
- **Convergent last-writer-wins**: `updated_at` is normalized before comparison
  (`Z` and `+00:00` resolve to the same instant); a same-instant conflict is
  broken deterministically by content, so two nodes converge on the same winner
  instead of diverging.

## v0.11.1 Review hardening (batches 2–3)

Closes findings D5–D15 of the v0.10.0 review. Two schema additions:

- **Migration 10 — `memory_links_archive`**: cold-archiving a memory now copies
  its association edges here (no FK — an endpoint may itself be archived);
  `restore_archived` re-attaches every edge whose other endpoint is live again,
  so restore is lossless instead of returning a degree-0 node.
- **Migration 11 — `memories.decay_base_half_life_days`**: the configured base a
  memory's half-life was created with (or last explicitly set to). Feedback
  tuning scales THIS, so an explicit `decay_half_life_days` is never clobbered
  back to the type default.

Behavioural fixes (no schema): authority-track scoring fuses raw lexical
relevance (no double-applied metadata); the de-identified-share copy never
carries the owner's id or tags; `approx_tokens` is CJK-aware; the web token is
written 0600 atomically; a `supersedes`-only pair is never given a `co_recalled`
edge; the team-ACL cache has a 30 s TTL; `/api/sync/run` never holds the app
lock across peer HTTP; the orchestrator lets a cap-dropped section hit fall
through to the task section; and a partial `agents.toml` entry preserves the
console-set fields it doesn't mention.

## v0.12 Multi-instance identity & ports

Several instances can share one machine, each with its own `--home`.

- **`<home>/instance.toml`** (all optional): `[instance]` with `node_name`
  (shown to peers during sync), `host`, and `port`. `node_name` defaults to a
  `hostname-<home>` label so co-located instances are distinct out of the box.
- **Web UI port resolution**: `--port` > `instance.toml` > 8000. A taken port
  auto-advances to the next free one unless `--strict-port` is given. The same
  configured port is used by `service install`.
- **Node identity (migration 12)**: `GET /api/node` returns `{node_name,
  version}`. The peer registry gains a `name` column, auto-filled from the
  peer's advertised `node_name` when a peer is added (overridable). Bundles
  carry the exporter's `node_name` in their header. Identity is display-only —
  ACL and merge rules are unchanged.

## v0.13 Teams & Projects

Teams and projects are first-class, with membership as the ACL authority.

- **Schema (migration 13)**: `teams(id, name)`, `team_members(team_id,
  agent_id)`, `projects(id, team_id, name)`, `project_members(project_id,
  agent_id)`. The join tables are authoritative; `agents.teams` is a
  denormalized convenience backfilled into `team_members` on upgrade.
- **Invariants**: a project belongs to exactly one team; a project member MUST
  be a member of that team (enforced on add). Leaving a team removes the agent
  from that team's projects; deleting a team deletes its projects and
  memberships; removing an agent clears all its memberships.
- **ACL**: `visibility: ["team:<id>"]` resolves to team members;
  `visibility: ["project:<id>"]` resolves to project members (a subset). Both
  are hard gates, resolved from membership and cached with a 30s TTL.
- **Scoped sync**: `export_bundle(team=…|project=…)` and peer policies
  `team:<id>` / `project:<id>` restrict a bundle to that scope's shared memory
  and that scope's members' recall profiles — so project memory only ever
  reaches project members' nodes.
- **Surfaces**: WebUI Teams tab, CLI `agent-memory team|project`, and the
  `/api/teams` + `/api/projects` endpoints (with member sub-resources).
  `register_agent(teams=…)` (and `agents.toml`) set an agent's team membership
  by reconciling `team_members` to the declared list; `register_agent(teams=None)`
  leaves membership untouched.

## v0.14 Federated org structure

The org structure federates so cross-node team/project ACL is consistent.

- **Versioning (migration 14)**: `teams.updated_at` / `projects.updated_at` bump
  on any membership change. An `org_audit` log records create/delete and member
  add/remove (actor + timestamp). `org_tombstones(kind, id, deleted_at)` records
  team/project deletions.
- **Bundle v3**: carries `team` / `project` records (id, name, `updated_at`,
  full member list) and `org_tombstone` records, scoped to match the memory
  scope of the bundle.
- **Import — convergent LWW**: a team/project is upserted and its member set
  REPLACED when the incoming `updated_at` wins, so additions and removals both
  converge; an `org_tombstone` at/after the local `updated_at` deletes the
  team/project (and cascades), and is retained so an older live record can't
  resurrect it. Imported project members are filtered to current team members
  (subset invariant preserved even under partial sync).
- **Known follow-ups**: revocation still doesn't retract already-synced
  *memory* from a node; per-peer policy isn't auto-derived from local
  membership.
