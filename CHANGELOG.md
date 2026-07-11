# Changelog — Agent Memory OS

All notable changes, newest first. Releases are published to
[PyPI](https://pypi.org/project/agent-memory-os/) via Trusted Publishing and
tagged on GitHub/GitLab.

## [1.0.3] — 2026-07-12

Docker packaging release — the published image is now the complete AgentMemoryOS.
No engine/SDK changes from 1.0.2.

- **Docker image is now complete and multi-mode.** The image installs the `full`
  extra (Web console + MCP server + turbovec + CLI), and the entrypoint dispatches
  on the first argument: `web` (default), `mcp` (the stdio MCP server), or any
  other args run the `agent-memory` CLI. One image, every surface. Verified end
  to end, including a real MCP introspection handshake against
  `docker run -i … mcp`. (`--build-arg EXTRAS=api` still gives a lean web-only build.)
- **docker-compose** (single + mesh) build the complete image too — dropped the
  `EXTRAS=api` override that was forcing web-only containers.

## [1.0.2] — 2026-07-12

Maturity pass for the 1.x line — docs, one opt-in feature, guards, and one fix.
Also the first release listed on the MCP Registry (the PyPI description now
carries the ownership marker, so the registry workflow can publish).

- **Fix (revocation staleness)**: the client's per-query recall cache was not
  invalidated by team/project membership changes, so a removed member could keep
  seeing a revoked team/project memory for a previously-run query until the cache
  evicted it. `add/remove_team_member`, `add/remove_project_member`, and
  `delete_team/delete_project` now clear the cache immediately (like
  `register_agent` already did). Found while writing the runnable example; covered
  by `tests/test_revocation_cache.py`.
- **`examples/`**: a runnable `team_memory.py` — three agents share one store under
  a hard ACL (private/team/project/global), a budgeted context pack, and instant
  re-scoping on member removal. Self-asserting, so it doubles as a smoke test.
- **MCP Registry manifest verified**: `server.json` is validated against the live
  registry schema and a real stdio MCP handshake confirms
  `python -m agent_memory_os.mcp_server` starts and lists the tools
  (`tests/test_server_json_and_mcp.py`). Fixed an over-length `description` that
  would have failed the registry publish.
- **`CONTRIBUTING.md`** + issue/PR templates (security routed to private reporting).

- **Importers** (`agent-memory import --from mem0|zep|chatgpt <export.json>`, and
  `agent_memory_os.importers.import_export`): best-effort migration from other
  memory systems. Deterministic ids (idempotent, no duplicates), private by
  default (`--visibility` to widen), source provenance. See `docs/IMPORTERS.md`.
- **Unencrypted-peer guard**: `add_peer` now warns when a peer URL is plain HTTP
  over the network (token + content would cross the wire in the clear); use
  https:// (TLS proxy/tunnel) for any non-localhost peer.
- **Security & governance docs**: `SECURITY.md` (private disclosure policy +
  honest known limitations) and `docs/THREAT_MODEL.md` (trust boundaries, the
  precise eventual/cooperative revocation guarantee, hardening checklist).
- **`COMPATIBILITY.md`**: the 1.x semver promise across the SDK API, CLI, HTTP
  API, forward-only schema migration, and the sync bundle format (v3, reads 1–3).
- **`docs/EMBEDDINGS.md`**: plug in fastembed/sentence-transformers via
  `TurbovecSemanticCandidateProvider.from_vectors()`, plus 10k→1M scale guidance.
- **README**: a one-line `claude mcp add` snippet and an animated console demo
  GIF; `docs/PROMOTION.md` holds ready-to-submit listing copy for MCP directories.

## [1.0.1] — 2026-07-12

Docs-only release to refresh the PyPI project page (the description is frozen
per version). No code changes.

- README: status badges (PyPI / Python / CI / Docker pulls / License), a top
  navigation bar, and a fact-based "How it compares" positioning table vs Mem0
  and Zep/Graphiti (architecture, not a benchmark).
- New 繁體中文 README (`README.zh-Hant.md`) with an English⇄中文 language switch.
- Web console dashboard screenshot in the README and the Docker Hub overview.

## [1.0.0] — 2026-07-12

First stable release. Everything below lands on top of v0.14.0's federated org
structure, and closes the trust-model, observability, and operability gaps that
a "memory system for AI-agent teams" needs to be run in production.

### Trust model — revocation & escalation (migration 15)
- **Revocation now propagates.** An independent ACL clock (`acl_updated_at`)
  carries share/revoke changes over sync WITHOUT restarting the decay/freshness
  clock. A post-hoc revoke retracts already-synced access on peers; a re-share
  converges back; an older incoming ACL never clobbers a newer local one.
- **Untrusted peers cannot escalate visibility.** Org-structure and ACL merges
  are authorized against the pushing peer's policy scope: a peer may only assert
  team/project membership within its own scope, may only *shrink* a memory's
  visibility (a revoke), never widen it, and cannot delete org structure it
  doesn't own. Anonymous HTTP pushes get no org mutations at all. Future-dated
  org/ACL timestamps are rejected so a forged clock can't pin state.
- Deterministic tie-break on equal-timestamp membership so nodes converge;
  member-removal cascades correctly to projects; deleting a team strips both
  team-grant schemes so a reused id can't resurrect access.
- `suggested_peer_policy(agent)` derives the tightest policy from local
  membership (advisory; the manual policy stays the enforced upper bound).

### Observability
- `GET /healthz` — integrity-aware readiness (200 ok / 503 degraded); the Docker
  HEALTHCHECK uses it.
- `GET /metrics` — Prometheus text format (aggregate counts only: memories,
  orphans, index drift, teams, projects, peers, peer errors, integrity).
- `agent-memory doctor` reports processes that predate the installed version.

### Updating & operations
- **`agent-memory update`** finishes the job: after a pip upgrade it restarts the
  running web console it owns via a self-written pidfile (never a `ps`-derived
  command — closes a local code-exec vector), reports MCP servers to restart in
  their host app, and (`update --check`) flags stale "disk-new/memory-old"
  processes. Docker deployments get image-pull guidance instead.
- `agent-memory service restart`; `agent-memory backup --keep N` (safe rotation
  that can never delete the live database); `agent-memory token create --readonly`
  (a GET-only web token tier).
- Ops/maintenance: orphan detection (owner- and existence-aware, so cleanup never
  deletes recoverable data), one-click orphan cleanup, manual reindex, vacuum.

### Web console
- Version badge (bottom-right), token-usage dashboard cards (total / top agent /
  team / project), a self-update button with version check, a membership-audit
  viewer, a graph scope filter, and a read-only-mode banner — all across 5 locales.

### Hardening & resilience
- Bundle import is fuzz-hardened (malformed lines roll back atomically; garbage
  fields are coerced, not executed). A CI `upgrade-path` job proves a DB written
  by the last published release migrates forward with data + integrity intact.
- Full code + security review (fan-out, two rounds) with reports under
  `docs/reviews/`; performance verified at 10k memories (add 0.17 ms, search
  <1 ms, context-pack 7.8 ms).

## [0.14.0] — 2026-07-11

**Federated org structure** (migration 14). Teams, projects, and their
membership now converge across nodes, so cross-node team/project ACL is
consistent — the missing piece that makes "team operation" correct in a mesh.

- **Convergent org sync**: bundles (v3) carry each team/project with an
  `updated_at` and its full member set. Import applies last-writer-wins on
  `updated_at` and REPLACES the member set, so additions AND removals converge.
  Deletions propagate via `org_tombstones` (a reused id can't resurrect a
  deleted team/project). Org export is scoped like memory (`full`/`shared` →
  all; `team:<id>` → that team + its projects; `project:<id>` → that project +
  its team). The subset invariant is preserved on import.
- **Membership audit** (`org_audit`): create/delete team & project and every
  member add/remove is recorded with actor + timestamp; readable via
  `client.org_audit_log()` and `GET /api/org/audit`. API member routes accept
  an `actor`.

**Ops & maintenance tooling.**

- **Orphan memories**: a memory scoped to a team/project with no members is
  visible to no one. `find_orphan_memories()` / `delete_orphan_memories()`,
  the `agent-memory maintenance orphans [--delete]` command, and a console
  **Maintenance** panel surface and clean them. Removing a team/project member
  warns (CLI + console) when it just orphaned memory.
- **`agent-memory maintenance`**: `scan` (health), `orphans`, `reindex`
  (rebuild FTS/semantic from the truth store), `vacuum` (reclaim disk +
  refresh planner stats) — plus `/api/maintenance/*` and console buttons.
- **`agent-memory update`**: detects the deployment (host `pip` vs Docker
  container) and OS, checks PyPI for a newer version, and either upgrades via
  pip or prints the `docker pull`/recreate steps. `--check` reports only.

**Docs.** README repositioned around **AI-agent team operation** (shared team &
project memory, federation) rather than single-agent recall.
- Review fixes from `docs/reviews/20260711-v0.13.0-review.md` (shipped in this
  release): `create_project` can't re-point a project to a different team;
  `register_agent(teams=None)` leaves membership untouched (metadata edits no
  longer wipe it); `to_project` reachable in the share API; the CLI reports
  domain errors cleanly; deleting a team/project revokes its orphaned
  visibility grant (no id-reuse resurrection).

## [0.13.0] — 2026-07-11

**First-class Teams & Projects** (migration 13). Teams and projects are now
real, manageable entities with explicit membership, so team-shared vs
project-shared memory is scoped and synced correctly.

- **Membership model**: `teams`, `team_members`, `projects` (belongs to a team),
  `project_members` — the join tables are authoritative for ACL. A project's
  members must be a subset of its team's; leaving a team cascades out of its
  projects; deleting a team removes its projects; removing an agent clears all
  its memberships. Existing flat `agent.teams` are backfilled into `team_members`.
- **`project:<id>` ACL**: `visibility: ["team:apollo"]` reaches every team
  member; `visibility: ["project:apollo-web"]` reaches only that project's
  members. Resolved through membership, cached with the same 30s TTL as teams.
- **Scoped sync**: `export_bundle(project=…)` and a `project:<id>` peer policy
  bundle only a project's shared memory (to project members' nodes), so project
  memory never reaches non-members. `share_memory`/`revoke_share` gain `to_project`.
- **Management everywhere**: WebUI **Teams** tab (create a team and pick node
  members; create projects under it and pick members from the team), CLI
  `agent-memory team|project …`, and `/api/teams`, `/api/projects` (+members).

## [0.12.1] — 2026-07-11

- **Web console login fix**: the console now shows a proper in-page token
  login form instead of relying on a `prompt()` dialog (which browsers could
  suppress and which stacked up under the page's parallel API calls, leaving
  users unable to log in). A 401 clears the stored token and reveals the login
  form; entering the token stores it and reloads.

## [0.12.0] — 2026-07-11

**Multiple instances on one machine.** Run several Agent Memory OS instances
side by side (each with its own `--home`) without port clashes, and identify
each other by name during sync.

- **Instance settings** `<home>/instance.toml` (`[instance]` → `node_name`,
  `host`, `port`) — all optional, sensible defaults; `node_name` defaults to a
  host+home label so co-located instances don't collide.
- **Auto port selection**: `agent-memory-web` resolves the port as CLI `--port`
  > `instance.toml` > 8000, and if it's taken, advances to the next free port
  (`--strict-port` to fail instead). It prints the bound URL and node name.
- **Node identity for sync (migration 12)**: `GET /api/node` advertises this
  instance's `node_name`; a registered peer stores a friendly `name` (auto-
  fetched from the peer on add, or `peers add --name` / the console field), so
  the peer list and sync results show names instead of bare URLs. Bundles carry
  the origin `node_name` in their header.
- **`agent-memory node`** shows/sets `node_name`/`host`/`port`; `service install`
  and the console honour the configured port; the console header shows this
  instance's node name.
- **Fix**: port availability is probed by connection, not bind — a restarted
  server re-binds its usual port instead of drifting (TIME_WAIT on POSIX,
  SO_REUSEADDR on Windows), which had surfaced as "failed to fetch" in the
  console. The graph view also degrades gracefully on unexpected data.

**Docker.** `Dockerfile` + `docker-compose.yml` run the Web console with memories
persisted in a `/data` volume; a two-node `docker-compose.mesh.yml` shows
instances syncing by name. The image binds `0.0.0.0` with `--strict-port`,
auto-generates a token on first run (secure by default), and configures entirely
through env (`AGENT_MEMORY_WEB_TOKEN`, `AGENT_MEMORY_NODE_NAME`,
`AGENT_MEMORY_WEB_HOST/PORT`) — env now overrides `instance.toml`. Semantic +
MCP are opt-in via `--build-arg EXTRAS=full`. See `docs/DOCKER.md`.

## [0.11.1] — 2026-07-11

Correctness, ranking, and privacy fixes — review batches 2 and 3, closing every
remaining finding (D5–D15) of `docs/reviews/20260711-v0.10.0-review.md`.

- **Ranking (D5)**: the authority (bedrock) track no longer double-applies
  importance/confidence/freshness — it fuses raw lexical relevance, so a
  matching authority memory is scored once.
- **Lossless archive/restore (D7, migration 10)**: archived memories keep their
  association edges in a link archive; `restore_archived` re-attaches every edge
  whose other endpoint is live again (was: restored at degree 0).
- **De-identified share privacy (D10)**: the recipient-visible copy no longer
  carries the owner's id in its audit row, and owner-identifying tags are dropped.
- **CJK token estimate (D12)**: `approx_tokens` counts CJK codepoints at ~1
  token each, so an orchestrated pack of Japanese/Chinese text no longer blows
  the caller's real token budget 4–6×.
- **Token file (D13)**: written 0600 atomically (no world-readable window, safe
  concurrent rotate).
- **Contradiction guard (D14)**: `record_recall(create_colinks=True)` never lays
  a `co_recalled` edge over a pair joined only by `supersedes`.
- **Team-ACL cache TTL (D8)**: cross-process membership changes are picked up
  within 30s instead of persisting until restart.
- **Configured decay base (D6, migration 11)**: feedback tuning scales the
  memory's configured half-life (default-for-type, or a value you set), so an
  explicit `decay_half_life_days` is no longer clobbered on every retention pass.
- **Sync no longer freezes the server (D9)**: `/api/sync/run` passes the shared
  lock instead of holding it — DB access stays serialized, but a slow/unreachable
  peer's HTTP round-trip never blocks other requests.
- **Orchestrator fallthrough (D11)**: a top hit claimed by the warnings/procedures
  section but dropped by that section's token cap now falls through to the task
  section instead of vanishing from the pack.
- **agents.toml partial entries (D15)**: re-applying a `[agents.<id>]` table that
  sets only some fields keeps the console-set values for the rest, instead of
  resetting them to defaults on every open.

## [0.11.0] — 2026-07-11

**Federation trust model** (migration 9) — resolves review findings D1–D4.

- **Per-peer sync policy**: each peer declares what leaves for it — `shared`
  (default: everything except private `visibility=[]` memories), `full` (whole
  store, own trusted replica nodes only), or `team:<id>` (one project). Private
  memories never leave the machine under `shared`/`team`. Existing peers migrate
  to `full` (no behaviour change); new peers default to `shared`.
- **HTTP export is always `shared`-scoped**: `GET /api/sync/export` never serves
  private memories (it cannot authenticate the puller); full private replication
  flows only over the authenticated push leg between own nodes.
- **Tombstones**: deletions and owner purges record a tombstone that propagates
  over sync, so a deleted memory no longer resurrects from a peer that still
  holds it.
- **Provenance + anti-impersonation**: imports from a semi-trusted peer record
  `source.synced_from` and may not create a memory authored by one of your local
  registered agents.
- **Convergent LWW**: conflict timestamps are normalized (`Z` vs `+00:00`) and a
  same-second edit is resolved by a deterministic content tie-break, so two
  nodes converge instead of diverging silently.
- CLI `peers add --policy`, `PeerRequest.policy`, and a console policy selector
  (with a warning that `full` shares private memory) keep parity across surfaces.

## [0.10.1] — 2026-07-11

Security & correctness fixes from the full v0.10.0 review
(`docs/reviews/20260711-v0.10.0-review.md`).

- **MCP identity escape (security)**: `memory_orchestrate_context` and
  `memory_recall_feedback` no longer accept a caller-supplied
  `requester_agent_id` that overrode the env-pinned agent identity.
- **Web ACL gate**: `GET /api/memories/{id}` and `/links` now enforce the
  same visibility gate as `/api/search` (new `get_visible()`).
- **Right-to-forget**: `purge_owner` now also destroys cold-archive rows and
  the recall/audit logs, so purged content is not restorable.
- `resonance_search` no longer raises on a found seed; LLM link extractor
  survives a non-string reply; `agents.toml` rejects a string `teams` and
  validates the whole file before applying (no half-registered fleet).
- share/revoke no longer reset the freshness/decay clock; the auto semantic
  index rebuilds after an in-place same-second edit; `rotate_snapshots` never
  archives pinned snapshots; `import_bundle` rolls back on a corrupt line;
  bundle temp files are written UTF-8 (Windows non-ASCII).

## [0.10.0] — 2026-07-11

- **Validation milestone**: `docs/VALIDATION_PLAN.md` (G1 security / G2
  functional / G3 performance / G4 deployment gate matrix) supersedes the
  v0.2.x-era Hermes shadow gates; reproducible harness
  `scripts/validation_run.py` generates professional reports into
  `docs/reports/` and runs in CI (`--quick`).
- First full run: **PASS** — 12/12 security, 10/10 functional, 13/13
  performance on a 5k-memory fleet corpus (search p95 11.9 ms,
  orchestrate p95 20.4 ms, writes 8.3k/s).
- **Ranking fix found by validation**: the query-independent authority
  (bedrock) track could crowd resonance results out of the result window
  at scale; its share is now capped at limit/4.
- Documentation sweep: new `docs/USER_GUIDE.md` (full CLI/API/MCP
  reference), CHANGELOG as release history, SPEC current through v0.9,
  INSTALLATION rewritten, status docs refreshed.

## [0.9.0] — 2026-07-11

- **Fleet as code**: `<home>/agents.toml` declares the whole multi-agent,
  multi-project fleet; re-applied on every store open (file-authoritative
  for listed agents, manual registrations untouched).
- **Console i18n**: English, 繁體中文, 简体中文, 日本語, 한국어 — auto-detected,
  live-switchable, persisted.

## [0.8.0] — 2026-07-11

- **Agent registry** (migration 8): agents are first-class entities (id,
  kind, teams, last-seen) with a console Agents tab and `/api/agents`.
- **Team auto-resolution ACL**: registered team memberships resolve inside
  the ACL hard gate — `team:<project>` memory visible to every member with
  zero per-call wiring.
- **Per-agent MCP identity**: `AGENT_MEMORY_AGENT_ID` gives each connected
  agent its own owner/requester identity.
- **Project-scoped sync**: `sync export --team <project>`.

## [0.7.0] — 2026-07-10

- **Mesh federation** (migration 7): peer registry, `agent-memory peers`,
  `sync auto` bidirectional convergence with per-peer failure isolation,
  console peer management.
- **LLM extraction plumbing**: `make_llm_link_extractor(fn)` wraps any
  completion callable into a consolidation link extractor with defensive
  parsing.

## [0.6.0] — 2026-07-10

- **Memory negotiation** (migration 5): owner-only `share_memory` /
  `revoke_share`, de-identified copies, per-memory audit trail.
- **Federated sync**: portable JSONL bundles + peer HTTP transport
  (`/api/sync/export|import`, `sync pull/push`) with deterministic merges.
- **Adaptive forgetting** (migration 6): helpful/unhelpful feedback tunes
  decay half-lives (`base × clamp(√((1+h)/(1+u)), 0.5, 4)`).

## [0.5.0] — 2026-07-10

- **Cross-OS login service**: `agent-memory service install` — launchd /
  systemd user unit / Task Scheduler; per-user, auto-restart, `--dry-run`.
- **Three-OS CI**: Ubuntu, macOS, Windows × Python 3.11–3.13.

## [0.4.0] — 2026-07-10

- **Dynamic context orchestration**: `orchestrate_context()` splits the
  token budget across session / bedrock / warnings / procedures / task
  buckets; proactive recall; task-type emphasis; session iterative
  deepening (migration 4); snapshot rotation and `snapshot_diff()`.

## [0.3.0] — 2026-07-10

- **Schema migrations** (versioned, forward-only) and
  `agent-memory check` integrity verification.
- **Cold-archive retention** (migration 3): expired/decayed memories become
  restorable archives; pinned/authority never archived by decay.
- **Auto semantic recall**: `MemoryClient(semantic="auto")` — self-syncing
  turbovec index over a dependency-free hashing embedder.
- `agent-memory backup/restore` (WAL-safe online backups).

## [0.2.4] — 2026-07-10

- Console dashboard, in-place memory editing (`PATCH`), agent purge danger
  zone, converging-evidence resonance, token/doctor CLI, official logo.

## [0.2.3] — 2026-07-10

- First public release: memory association layer (`memory_links`,
  ACL-safe resonance recall, link decay, hub damping, supersedes),
  Hebbian reinforcement loop with negative feedback, persisted recall
  profiles, write-side consolidation, requester-aware Web console,
  MCP server, Apache-2.0.

## Pre-release lineage

- **2026-06-12 → 06-13** — Dynamic Context Orchestration prototypes
  (`ContextSnapshot` schema, offload/reload, precision test suite) on the
  Hermes workstream, later merged and hardened in 0.4.0.
- **2026-06-05 → 06-09** — v0.2.x internal baselines: SQLite+FTS5 source of
  truth, requester-aware ACL, truth arbitration, retrieval foundation,
  turbovec sidecar validation (`v0.1.0-stable` tag).
