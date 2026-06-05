# AgentMemoryOS - Project History and Roadmap

Last updated: 2026-06-05 11:04:59 CST (+0800)

## Purpose

This document records the project journey, decisions, completed work, pending work, and code-level contracts inside the AgentMemoryOS repository itself.

AgentMemoryOS, also referred to in early discussions as Mnemosyne Local, is a local-first, MCP-native, RAM-cache-accelerated long-term memory engine for multi-agent systems.

Core engineering principle:

> Memory permission control is more important than recall volume.

The system must not blindly inject all memories into prompts. It must retrieve only authorized, relevant, high-quality memories and pack them under an explicit context budget.

## Canonical repository

- Working tree: `/mnt/nas/Hermes-Gitlab/agent-memory-os`
- GitLab remote: `git@gitlab.com:hermes-agent-bastet/agent-memory-os.git`
- Public URL: `https://gitlab.com/hermes-agent-bastet/agent-memory-os`
- Current branch at documentation time: `main`

## Collaborator / label conventions

- `[Neo/Engineering]`: implementation, architecture, tests, infra, CI/CD.
- `[Mizuki/Product]`: requirements, UX, persona stress cases, memory quality.
- Shared tags:
  - `[AgentMemoryOS/Spec]`
  - `[AgentMemoryOS/MVP]`
  - `[AgentMemoryOS/v0.2]`
  - `[MemoryPolicy]`
  - `[ContextBudget]`
  - `[RetrievalQuality]`
  - `[OpenSource]`

## Product direction

AgentMemoryOS is designed to address several long-running AI agent pain points:

1. Context windows are too small for durable memory.
2. Cloud memory platforms add privacy, latency, cost, and dependency risks.
3. Multi-persona and multi-agent memory sharing needs explicit access control.
4. Retrieval quality alone is not enough; unauthorized memories must never be considered.
5. Prompt context must be budgeted and explainable.

Target compatibility includes Hermes, Claude Code / Claude Desktop style agents, OpenAI Agents, LangChain, CrewAI, AutoGen, and custom MCP clients.

## Architecture summary

Core retrieval pipeline:

```text
Raw Data
→ ACL Filter / Hard Cut
→ Budget Allocator / Priority-based
→ Context Pack
```

Expanded architecture:

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

## Project evolution

### Phase 0: Conception and infrastructure

- Defined the product as a local-first AI agent memory runtime.
- Established the NAS working tree at `/mnt/nas/Hermes-Gitlab/agent-memory-os`.
- Created and synchronized the GitLab repository.
- Established the tiered memory direction: hot cache, local structured/FTS storage, future vector/cold archive support.

### Phase 1: MVP - The Security Foundation

Focus: ACL and visibility enforcement.

Core principle:

> Memories without permission have no right to be ranked.

Completed baseline components:

- SQLite persistence.
- SQLite FTS5 keyword retrieval.
- Structured memory records.
- In-process LRU cache.
- Context pack builder with conservative token-ish budget.
- Python SDK.
- CLI commands: `add`, `search`, `pack`, `stats`.
- Optional MCP server scaffold.
- Unit tests.

### Phase 2: v0.2 - 喧囂中的真理

Focus: Context Budget and Truth Arbitration.

Goal: solve the memory pollution and resource-arbitration problem.

Key engineering challenges:

- Context Budget Allocator: manage limited prompt space under noise saturation.
- Core Memory Protection: keep `permanence=true` / high-weight memories alive under pressure.
- Temporal Decay and Recency: reduce stale-but-similar memory influence.
- Truth Arbitration: handle contradictory memories with conflict metadata.
- Explainability: emit selected/rejected decision reasons.

## Data model definition

The memory record model includes:

- `id`
- `owner`
- `scope`
- `type`
- `content`
- `summary`
- `tags`
- `visibility`
- `source`
- `confidence`
- `importance`
- `created_at`
- `updated_at`
- `expires_at`

## Completed implementation history

### MVP implementation

Implemented baseline components listed above and added test coverage for core behavior.

### GitLab bootstrap

Initialized and pushed the repository to:

```text
git@gitlab.com:hermes-agent-bastet/agent-memory-os.git
```

### v0.2 ACL baseline

Implemented requester-aware ACL filtering in search and context-pack paths.

Key code areas:

- `src/agent_memory_os/client.py`
- `src/agent_memory_os/db.py`
- `tests/test_acl_visibility.py`
- `scripts/verify_acl_identities.py`
- `tests/test_verification_script.py`

Current supported visibility behavior:

- `visibility=["agent"]`: owner/requester isolation.
- `visibility=["global"]`: visible to any requester.
- `visibility=["agent:<id>"]`: explicit agent allowlist.
- `visibility=["team"]` or `visibility=["team:<id>"]`: team-aware access via requester team id.
- Expired memories are excluded from search results and therefore cannot enter context packs.

### ACL subjective QA

Created `scripts/verify_acl_identities.py` to seed a temporary ACL fixture and switch requester identities across Mizuki, Neo, and Guest.

Acceptance result:

- Mizuki sees: `private_emotional_preference`, `team_memory`, `global_memory`.
- Neo sees: `team_memory`, `global_memory`.
- Guest sees: `global_memory`.
- Leak check: `leak_check.passed=true`.

This confirmed both raw search and context-pack filtering.

### Memory Decay & Recency planning

Created a detailed v0.2 implementation plan:

- `docs/plans/20260605_100751-memory-decay-recency-v0.2.md`

The planned scoring shape is:

```text
effective_score = text_score
                * importance_weight
                * confidence_weight
                * freshness_weight
                * reinforcement_weight
                * dedupe_penalty
                * contradiction_penalty
```

ACL and expiry are hard filters, not soft multipliers.

### Team collaboration route repair

During AgentMemoryOS multi-agent dogfooding, Telegram collaboration routing exposed a Hermes Gateway authorization/session-state issue: team agents could mention each other, but bot-originated messages could still be rejected as unauthorized humans.

Evidence:

```text
WARNING gateway.run: Unauthorized user: 8511600388 (小NEO) on telegram
```

Root cause:

1. `gateway/run.py` had bot allowlist mappings for Discord and Feishu, but not Telegram. As a result, `TELEGRAM_ALLOW_BOTS` was not consulted in the runner-level authorization path.
2. `gateway/session.py` did not preserve `SessionSource.is_bot` through `to_dict()` / `from_dict()`, so bot identity could be lost when session state was serialized and reconstructed.

Fix contract:

- Add `Platform.TELEGRAM: "TELEGRAM_ALLOW_BOTS"` to the gateway runner bot-allowance map.
- Persist `SessionSource.is_bot` in session serialization.
- Normalize team profiles to `telegram.allow_bots: mentions`, preserving mention-gated collaboration without enabling unrestricted bot echo loops.

Verification snapshot:

```bash
cd /home/hermes/.hermes/hermes-agent
python -m pytest tests/gateway/test_telegram_bot_auth_bypass.py tests/gateway/test_feishu_bot_auth_bypass.py -q
# 12 passed
```

Runtime verification:

- Restarted: `hermes-bastet.service`, `hermes-blue.service`, `hermes-bunny.service`, `hermes-feifei.service`, `hermes-mizuki.service`, `hermes-yuyu.service`.
- Result: all restarted services reported `active`.
- Post-start log scan after `2026-06-05 11:02:20` found no new `Unauthorized user` failures.

Separate warning observed:

- Telegram reported `Group migrated to supergroup. New chat id: -1003586375148` for one send attempt. This is a chat-id migration issue and not part of the bot authorization root cause.

## Authoritative engineering decisions

### ACL is a hard gate

Unauthorized memory must be eliminated before ranking, reranking, dedupe, budget allocation, or prompt assembly.

Correct semantic flow:

```python
allowed_candidates = [m for m in raw_candidates if can_read(m, requester)]
ranked = sorted(allowed_candidates, key=effective_score, reverse=True)
```

Incorrect semantic flow:

```python
# Wrong: unauthorized memories still flow downstream.
effective_score = text_score * acl_allowed
```

### Search and Context Pack must both enforce ACL

It is insufficient to enforce ACL only at storage metadata or search result level. Context-pack construction must also be requester-aware and must not bypass the same authorization rules.

### Core truth must survive budget pressure

The next major engineering stress case requires the context budget allocator to preserve high-authority memories even when noisy memories are more textually similar.

### Zero Trust multi-agent memory

No agent receives implicit read-all access. Even a core/engineering agent does not automatically read another persona's private memory unless explicitly authorized.

## Verification snapshot

Last known verification from `PROJECT_STATUS.md`:

```bash
cd /mnt/nas/Hermes-Gitlab/agent-memory-os
PYTHONPATH=src python3 -m pytest -q
# 12 passed at 2026-06-05 10:19:41 CST
```

ACL targeted verification:

```bash
PYTHONPATH=src python3 -m pytest tests/test_acl_visibility.py -q
# 4 passed
```

Subjective ACL QA:

```bash
PYTHONPATH=src python3 scripts/verify_acl_identities.py --home /tmp/agent-memory-os-mizuki-qa --identity all
# leak_check.passed=true
```

## Current status snapshot

Completed:

- [x] Local NAS repo setup.
- [x] Basic tiered memory architecture design.
- [x] SQLite + FTS5 MVP.
- [x] LRU cache.
- [x] Context pack hard budget baseline.
- [x] Requester-aware ACL enforcement.
- [x] Identity verification suite.
- [x] Memory Decay & Recency implementation plan.
- [x] Project-local history and stress-case documentation.

In progress / next:

- [ ] Memory Decay & Recency implementation.
- [ ] Context Budget Allocator strengthening.
- [ ] Core Memory Protection logic.
- [ ] Temporal decay and truth arbitration algorithms.
- [ ] Selection/rejection reason metadata.

Pending / backlog:

- [ ] Multi-agent memory sharing/isolation refined specs.
- [ ] Persona-heavy memory benchmark set.
- [ ] Universal SDK / integration path for external agents.
- [ ] Vector backend selection and implementation.
- [ ] Memory dedupe/consolidation flow.
- [ ] Audit log.
- [ ] MCP `update`, `delete`, and `consolidate` tools.
- [ ] Import/export from Hermes `MEMORY.md` / `USER.md` and Mem0.

## Project-local recovery order

When resuming this project from a new session:

1. Read `README.md`.
2. Read `PROJECT_STATUS.md`.
3. Read this file: `docs/HISTORY.md`.
4. Read `docs/stress-cases/case-01-noisy-truth.md`.
5. Run:

```bash
cd /mnt/nas/Hermes-Gitlab/agent-memory-os
PYTHONPATH=src python3 -m pytest -q
PYTHONPATH=src python3 scripts/verify_acl_identities.py --home /tmp/agent-memory-os-qa --identity all
```

6. Only claim a visibility or budget behavior is complete after test output confirms it.

## Related project docs

- `README.md`
- `SPEC.md`
- `PROJECT_STATUS.md`
- `docs/stress-cases/case-01-noisy-truth.md`
- `docs/plans/20260605_100751-memory-decay-recency-v0.2.md`
