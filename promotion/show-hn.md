# Show HN draft

> Post from your own HN account. Best time: weekday ~08:00–10:00 US Eastern.
> Reply to early comments fast — engagement in the first hour drives ranking.

## Title (pick one — keep under 80 chars, no hype words)

- `Show HN: Agent Memory OS – local-first memory for AI agents, one SQLite file`
- `Show HN: Local-first memory engine for AI-agent teams (no LLM, one SQLite file)`

## URL

https://github.com/yamantaka520/Agent-Memory-OS

## Body (first comment — HN convention is to add context as a comment)

I built Agent Memory OS because every "agent memory" option I tried wanted a
cloud account, an embeddings/LLM key, and a vector database just to remember a
handful of facts across sessions. For a local coding agent that felt backwards.

It's a memory engine that runs entirely on your machine:

- **One SQLite file.** FTS5 for keyword search; no server, no vector DB, no
  network calls. `pip install "agent-memory-os[mcp]"` and it works offline.
- **No LLM required.** Recall is keyword + an associative "resonance" pass
  (memories link to co-recalled memories, links decay over time, feedback
  reinforces or weakens them). You can bolt on embeddings if you want, but the
  default path needs no model.
- **Made for teams of agents, not one chatbot.** Every memory has a visibility
  ACL — private / team / project / agent / global — enforced as a hard gate on
  read. Two agents can share a project's memory while keeping private scratch
  space. Federated sync (bundle export/import + a peer mesh) lets separate
  machines share memory without a central server.
- **MCP-native.** 12 MCP tools (add/search/recall/link/share/context-pack…),
  plus a Web UI and a CLI over the same store. I run it wired into Claude Code
  and Codex simultaneously against one shared home.

Stack: pure Python, stdlib SQLite, Apache-2.0. Optional extras for MCP / FastAPI
Web UI / embeddings.

Design notes if useful: recall is a two-track retrieve (direct FTS hits +
ACL-safe graph traversal through association edges), a Hebbian reinforcement
loop on co-recall, a tunable forgetting curve, and write-time consolidation that
merges duplicates. The ACL is the part I care most about getting right — it's a
gate on every read path, not a filter bolted on top.

Would love feedback on the memory model and the local-first vs cloud tradeoff.
What would you want before trusting an agent's long-term memory?

## Likely questions — have answers ready

- **vs mem0 / zep?** Those are cloud-first (or self-host with vector DB + model).
  This is local-first, single file, no model needed, with a multi-agent ACL.
- **How is recall good without embeddings?** FTS5 + association graph; embeddings
  are optional and pluggable. Honest about the tradeoff — it's recall-by-keyword
  + co-recall, not semantic search, unless you enable the embedding sidecar.
- **Scaling?** It's SQLite; great for a team's working memory, not a billion-row
  warehouse. Say so plainly.
