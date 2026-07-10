# WebUI Availability Triage — 2026-06-17 22:17 CST (+0800)

## Scope

- Project: AgentMemoryOS
- Repo: `/mnt/nas/Hermes-Gitlab/agent-memory-os`
- Allowed runtime home: `/home/hermes/.agent-memory-os-web`
- WebUI URL tested: `http://127.0.0.1:8765/`

## Team investigation summary

- Neo / engineering found the WebUI code path imports, starts, and passes `tests/test_web_app.py`; however WebUI files and script entrypoint are currently local working-tree changes/untracked, not committed into HEAD.
- Blue / ops found the live symptom is absence of a durable WebUI service/process. When no process is running, port `8765` is closed. The documented command starts successfully and returns HTTP 200 on smoke endpoints.
- Bunny / QA was blocked by tool safety while attempting duplicate curl/browser verification; no file changes.

## Current evidence

Command:

```bash
cd /mnt/nas/Hermes-Gitlab/agent-memory-os
PYTHONPATH=/mnt/nas/Hermes-Gitlab/agent-memory-os/src PYTHONUNBUFFERED=1 \
  python3 -m agent_memory_os.web_app --host 127.0.0.1 --port 8765 --home /home/hermes/.agent-memory-os-web
```

Tracked runtime process:

- Hermes process session: `proc_763e8d9f7459`
- PID: `2365087`
- Bind: `127.0.0.1:8765`

HTTP smoke result after restart:

```text
/ status=200 content_type=text/html; charset=utf-8
/health status=200 content_type=application/json body='{"status":"ok"}'
/api/stats status=200 content_type=application/json body='{"total":1,"by_scope":{"user":1},"by_type":{"note":1},"cache_items":0}'
```

Git state observed at 2026-06-17 22:17:42 CST:

```text
## feat/pr3-turbovec-provider...origin/feat/pr3-turbovec-provider
 M PROGRESS.md
 M PROJECT_STATUS.md
 M README.md
 M docs/project-status/current.md
 M pyproject.toml
?? src/agent_memory_os/web_app.py
?? tests/test_web_app.py
HEAD: 9f285be
```

## Diagnosis

Direct availability issue: WebUI was not backed by a persistent supervisor/service. If the ad-hoc Python process exits or is killed, `127.0.0.1:8765` becomes unavailable.

Version-control/deployment risk: `src/agent_memory_os/web_app.py`, `tests/test_web_app.py`, and the `agent-memory-web` script entrypoint appear to be uncommitted/untracked local work. A clean checkout or deployment from Git HEAD may not contain the WebUI implementation.

Network boundary: the documented command binds `127.0.0.1`; it is reachable only from the same host unless a reverse proxy/tunnel or `0.0.0.0` binding is intentionally configured.

## Current status

- Status: running
- WebUI is currently available locally at `http://127.0.0.1:8765/` via tracked process `proc_763e8d9f7459` / PID `2365087`.
- This is a temporary runtime recovery, not a durable service deployment.

## Recommended next actions

1. Review and commit the WebUI source, tests, entrypoint, and docs if accepted.
2. Add a durable supervisor unit/service or documented `hermes`/systemd startup path.
3. Decide intended access boundary: localhost-only, LAN, reverse proxy, or authenticated public route.
4. Re-run `PYTHONPATH=src python3 -m pytest tests/test_web_app.py -q` and HTTP smoke after the durable service path is added.
