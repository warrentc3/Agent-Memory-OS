# AgentMemoryOS Project Status

## Intent

Build an open-source local-first memory extension similar in spirit to Mem0.ai, optimized for AI agent teams that need durable memory plus RAM-backed fast recall without exhausting prompt context.

## Collaborators

- Neo / LittleNEO: engineering implementation, repo bootstrap, tests, GitLab/NAS setup.
- Mizuki / NaoMizukiLover: product/UX usage scenarios, multi-agent memory needs, media/persona-heavy stress cases.
- Additional agents may be delegated for architecture review, QA, docs, and integration testing.

## Canonical paths

- NAS working tree: `/mnt/nas/Hermes-Gitlab/agent-memory-os`
- Intended GitLab remote: `git@gitlab.com:hermes-agent-bastet/agent-memory-os.git`

## Current baseline

- Python package skeleton created.
- SQLite + FTS5 memory store implemented.
- In-memory LRU cache implemented.
- Context-pack budget logic implemented.
- CLI implemented.
- Optional MCP server scaffold added.
- Unit tests added.

## Next engineering decisions

1. Choose vector backend for v0.2: `sqlite-vec`, `fastembed`, or Qdrant.
2. Define exact Hermes provider/MCP integration point.
3. Add memory dedupe/consolidation flow.
4. Add importers for Hermes `MEMORY.md` / `USER.md` and Mem0 export/API.
5. Decide whether the default deployment mode is embedded library, local daemon, or both.

## Verification commands

```bash
cd /mnt/nas/Hermes-Gitlab/agent-memory-os
PYTHONPATH=src python3 -m pytest -q
git status --short --branch
```
