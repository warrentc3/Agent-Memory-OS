# Compatibility & versioning policy

AgentMemoryOS follows [Semantic Versioning](https://semver.org/) from `1.0.0`.
`MAJOR.MINOR.PATCH`:

- **PATCH** (`1.0.x`) — bug fixes, docs, internal changes. No behavior change to
  the surfaces below.
- **MINOR** (`1.x.0`) — new, backward-compatible features. Existing code, data,
  and bundles keep working.
- **MAJOR** (`2.0.0`) — a breaking change to one of the surfaces below, called
  out in the CHANGELOG with a migration note.

## What "public" means (covered by semver)

1. **SDK API** — the names exported from `agent_memory_os.__init__` (`MemoryClient`
   and its documented methods, `MemoryRecord`, `MemoryLink`, `RecallProfile`,
   `SearchResult`). Method signatures grow only additively within a MAJOR; a
   removal or a breaking signature change bumps MAJOR.
2. **CLI** — documented `agent-memory` subcommands and their flags. New commands
   and new optional flags are MINOR; removing/renaming a command or flag is MAJOR.
3. **HTTP API** — documented `/api/*` routes and their response shapes (see the
   User Guide). Additive fields are MINOR.
4. **On-disk schema** — the SQLite database **migrates forward automatically** and
   this is a permanent guarantee: a database written by any `1.x` opens and
   upgrades under any newer `1.y`. Migrations are forward-only; we do not promise
   *down*-grades (keep a backup before a MAJOR upgrade — `backup --keep`).
5. **Sync bundle format** — the current bundle is **version 3**. Import accepts
   bundle versions `1`, `2`, and `3`, so a newer node can always read an older
   node's bundle. A new bundle version is introduced only when needed and old
   versions stay readable across the current MAJOR.

## Not covered (may change in any release)

- Anything prefixed with `_`, and modules not re-exported from the package root
  (e.g. `db.py` internals, `candidates.py`, provider internals).
- The disposable index layout (FTS/turbovec/resonance) — indexes are rebuildable
  from SQLite by definition (`rebuild_indexes()`), so their internal shape is not
  a compatibility surface.
- The hashing embedder's exact vectors (semantic recall is a soft ranking signal;
  bring your own embedding model for stability — see `docs/EMBEDDINGS.md`).
- Web console HTML/CSS/JS structure and internal endpoints not in the API table.

## Deprecation

When a public surface must change within `1.x`, the old form keeps working for at
least one MINOR release, emits a `DeprecationWarning` (SDK) or a stderr notice
(CLI), and is documented in the CHANGELOG before removal in the next MAJOR.

## Checking your version

`agent-memory check` prints the package and on-disk schema versions; the Web
console shows the running version in the bottom-right badge and at `GET /api/node`.
