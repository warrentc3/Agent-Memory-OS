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
- First GitLab project created and pushed.
- v0.2 ACL baseline implemented for requester-aware search/context-pack filtering:
  - `visibility=["agent"]`: owner/requester isolation.
  - `visibility=["global"]`: visible to any requester.
  - `visibility=["agent:<id>"]`: explicit agent allowlist.
  - `visibility=["team"]` or `visibility=["team:<id>"]`: team-aware access via requester team id.
  - `expires_at` is excluded from search results when expired.
- Subjective QA verification script added:
  - `scripts/verify_acl_identities.py` seeds a temporary ACL fixture and switches identities across Mizuki, Neo, and Guest.
  - Verifies both raw search and context-pack filtering, with a leak check for `private_emotional_preference`.

## Verification snapshot

- Test command: `PYTHONPATH=src python3 -m pytest -q`
- Result: `12 passed` at `2026-06-05 10:19:41 CST`
- ACL targeted command: `PYTHONPATH=src python3 -m pytest tests/test_acl_visibility.py -q`
- ACL targeted result: `4 passed`
- Subjective QA command: `PYTHONPATH=src python3 scripts/verify_acl_identities.py --home /tmp/agent-memory-os-mizuki-qa --identity all`
- Subjective QA result: Mizuki sees `private_emotional_preference`, `team_memory`, `global_memory`; Neo sees `team_memory`, `global_memory`; Guest sees `global_memory`; `leak_check.passed=true`.
- Live QA re-run command: `PYTHONPATH=src python3 scripts/verify_acl_identities.py --home /tmp/agent-memory-os-mizuki-qa-live --identity all`
- Live QA re-run result: same visibility matrix passed; `leak_check.passed=true` at `2026-06-05 10:30:38 CST`.
- Product acceptance: `[AgentMemoryOS/MVP]` requester-aware ACL visibility is officially `Mizuki-Approved` for the `feat: enforce requester-aware memory visibility` baseline.
- First commit: `d02c22b feat: bootstrap AgentMemoryOS MVP`
- GitLab URL: `https://gitlab.com/hermes-agent-bastet/agent-memory-os`

## Team collaboration route repair snapshot

Recorded at `2026-06-05 11:04:59 CST (+0800)` as operational context for multi-agent AgentMemoryOS dogfooding.

- Incident: Telegram bot-to-bot collaboration routing intermittently rejected team agents with logs like `Unauthorized user: 8511600388 (小NEO) on telegram`.
- Root cause: Hermes Gateway had two state/authorization gaps:
  - `gateway/run.py` did not map `Platform.TELEGRAM` to `TELEGRAM_ALLOW_BOTS`, so Telegram bot identities could not bypass the human allowlist even when policy allowed bot mentions.
  - `gateway/session.py` did not serialize/deserialize `SessionSource.is_bot`, so bot identity could be lost across session state boundaries.
- Runtime policy: team profiles were normalized to `telegram.allow_bots: mentions` for Bastet, Blue, Bunny, Feifei, Mizuki, Yuyu, and Neo.
- Verification:
  - Hermes targeted tests: `python -m pytest tests/gateway/test_telegram_bot_auth_bypass.py tests/gateway/test_feishu_bot_auth_bypass.py -q` → `12 passed`.
  - Services restarted via systemd: `hermes-bastet.service`, `hermes-blue.service`, `hermes-bunny.service`, `hermes-feifei.service`, `hermes-mizuki.service`, `hermes-yuyu.service` → all `active`.
  - Post-start log scan after `2026-06-05 11:02:20` found no new `Unauthorized user` authorization failures.
- Related non-root-cause warning: one Telegram `Group migrated to supergroup` send error was observed and should be treated as a separate chat-id migration issue, not as the bot authorization root cause.

## Architecture review notes before v0.2

- Clarify which SPEC features are implemented versus planned, especially `visibility` ACL, `expires_at`, audit log, and MCP update/delete/consolidation tools.
- Add input validation for `scope`, `type`, `confidence`, and `importance`.
- Add tests for update/delete FTS triggers, expired memory handling, installation/entrypoint smoke test, and precision of multi-term search.
- Document SQLite FTS5 as a runtime prerequisite.

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

## Project-local documentation

The project history and stress-case definitions are now documented inside this repository, not only in the external wiki:

- `docs/HISTORY.md`: project journey, planning, completed work, pending work, decisions, code-level contracts, and recovery order.
- `docs/stress-cases/case-01-noisy-truth.md`: `[Mizuki/StressCase] Case 01: 喧囂中的真理`, fixture design, requester matrix, budget acceptance criteria, and suggested pytest tests.
