# Importing from other memory systems

Bring existing memories into AgentMemoryOS from Mem0, Zep/Graphiti, or a ChatGPT
export:

```bash
agent-memory import --from mem0    mem0-export.json     --owner alice
agent-memory import --from zep     zep-export.json      --owner alice --visibility global
agent-memory import --from chatgpt conversations.json   --owner me
```

Or from the SDK:

```python
from agent_memory_os import MemoryClient
from agent_memory_os.importers import import_export

client = MemoryClient(home="~/.agent-memory")
report = import_export(client, "mem0", "mem0-export.json", owner="alice")
print(report.as_dict())   # {source, scanned, inserted, updated, skipped, warnings}
```

## How it behaves

- **Idempotent.** Each record gets a deterministic id (`<source>_<hash>`). Re-running
  an import skips unchanged records and refreshes changed ones — never duplicates.
- **Private by default.** Imported memories have `visibility=[]` (owner-only) unless
  you pass `--visibility` (comma-separated grants, e.g. `global` or `team:apollo`).
- **Provenance kept.** Each memory's `source` records the origin system, the source
  key, and a content hash.
- **Forgiving.** Unknown/extra fields are ignored; empty records are skipped. A file
  that isn't valid JSON errors clearly.

## Expected export shapes

Export formats drift between tool versions, so the importers accept the common
documented shapes and degrade gracefully.

### Mem0 (`--from mem0`)
A JSON list of memory objects, or `{"results": [...]}` / `{"memories": [...]}`.
Each object: a text field (`memory` / `text` / `content`) plus optional `id`,
`user_id`, `metadata`, and timestamp provenance. Timestamp fields are checked in
`created_at`, `createdAt`, `timestamp` order. Their values are classified by shape;
timezone-explicit ISO timestamps (`Z` or an explicit offset, with or without
fractional seconds) and Unix epoch seconds are converted to AgentMemoryOS's
canonical UTC stamp. Unsupported or invalid values produce a warning and the next
timestamp field is tried.

Current Python OSS `Memory.get_all(...)` and hosted Get Memories responses use a
`{"results": [...]}` envelope. TypeScript OSS uses the same envelope with camel-case
`createdAt`. Mem0's platform Memory Export feature produces a caller-defined schema,
so its output is importable only when that schema produces compatible records.

### Zep / Graphiti (`--from zep`)
A JSON object with `facts` (edges carrying a `fact`/`name`/`summary` string)
and/or `messages` (with `content` and `role`), or a bare list of facts. Each
fact/message becomes one memory.

### ChatGPT (`--from chatgpt`)
Two shapes are accepted:
- **Account memory** — `{"memories": [...]}` (strings or `{content}` objects).
- **`conversations.json`** from a data export — the importer extracts your
  **user turns** (the durable signal) from each conversation's message mapping.

## After importing

Imported content flows through the normal pipeline — search, context packs,
resonance, retention. If you use a real embedding model, rebuild the semantic
index after a large import (see [EMBEDDINGS.md](EMBEDDINGS.md)). Review what
landed in the Web console's **Browse** tab, and widen visibility later with
share/revoke if you imported private and want to share to a team.
