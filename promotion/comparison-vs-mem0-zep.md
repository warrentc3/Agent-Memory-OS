# Comparison / positioning article draft
# vs mem0 & zep — reusable as a dev.to / Hashnode / 掘金 post

> Two versions below: a short positioning table (drop into README or a tweet
> thread) and a longer blog post. Keep it honest — name the tradeoffs, don't
> trash the alternatives. HN and r/LocalLLaMA punish hype.

## Positioning table

| | Agent Memory OS | mem0 | Zep |
|---|---|---|---|
| Where data lives | **Your machine** (one SQLite file) | Cloud (or self-host + vector DB) | Cloud (or self-host service) |
| Needs an LLM / embeddings to work | **No** (optional add-on) | Typically yes | Yes |
| External services | **None** | Vector DB / API | Service + store |
| Install | `pip install "agent-memory-os[mcp]"` | SDK + keys/host | SDK + service |
| Multi-agent access control | **Per-memory ACL** (private/team/project/agent/global) | Per-user scoping | Per-user/session |
| Cross-machine sharing | **Federated sync, no central server** | Central cloud | Central service |
| Interfaces | MCP + Web UI + CLI | SDK / API | SDK / API |
| License | Apache-2.0 | mixed | mixed |

**One-liner:** mem0 and Zep are excellent cloud-first memory layers. Agent
Memory OS is the local-first answer: your data stays in one file on your box, it
works with no model, and it's built for a *team of agents* sharing memory under
an access-control model rather than a single assistant.

## Blog post draft

### Title options
- Local-first memory for AI agents: why one SQLite file beats a vector database
- I didn't want a cloud account to give my coding agent a memory

### Body

Every agent framework eventually hits the same wall: the agent forgets. The
common fix is a "memory layer" — and almost all of them assume a cloud account,
an embeddings model, and a vector database. That's a lot of moving parts (and a
lot of your data leaving your machine) just to remember "the user prefers pnpm."

I wanted something that:

1. **Runs locally, offline.** No account, no keys, no network. The entire store
   is a single SQLite file you can back up, diff, or delete.
2. **Works without a model.** Recall shouldn't require an LLM call. The default
   path is FTS5 keyword search plus an associative graph — memories link to the
   ones recalled alongside them, links decay over time, and feedback reinforces
   or weakens them. Embeddings are available as an optional sidecar, not a
   requirement.
3. **Assumes more than one agent.** Real setups have several agents (and
   teammates) that should share *some* memory and keep the rest private. So
   every memory carries a visibility ACL — private / team / project / agent /
   global — enforced as a hard gate on every read, not a filter layered on top.
   Separate machines can share memory through federated sync (bundle
   export/import + a peer mesh) with no central server.

**The honest tradeoffs:** it's SQLite, so it's built for a team's working memory,
not a billion-row warehouse. Default recall is keyword + co-recall, not semantic
search — turn on the embedding sidecar if you need vectors. And local-first means
*you* run it; there's no managed cloud to page someone at 3am.

It's MCP-native (12 tools), with a Web UI and CLI over the same store. I run it
wired into Claude Code and Codex against one shared home so both agents build on
the same project memory.

Apache-2.0, pure Python. Repo: https://github.com/yamantaka520/Agent-Memory-OS

If you've fought with agent memory, I'd love to hear what made you trust (or
distrust) it.
