# WebUI Port Correction — 2026-06-17 22:57 CST (+0800)

## Correction

The intended AgentMemoryOS WebUI port for this task is `8000`, not `8765`.

The previous triage followed stale/incomplete repo-local documentation that mentioned `8765`; that was insufficient because live service expectations were not verified against the actual requested runtime port before taking action.

## Corrective actions taken

1. Stopped the incorrectly started temporary `8765` process:
   - Hermes session: `proc_763e8d9f7459`
   - Result: killed
2. Verified both relevant ports:
   - Before restart, neither `8000` nor `8765` had a listener.
   - `http://127.0.0.1:8000/`, `/health`, `/api/stats` returned connection refused before startup.
3. Started WebUI on the correct port `8000`:

```bash
cd /mnt/nas/Hermes-Gitlab/agent-memory-os
PYTHONPATH=/mnt/nas/Hermes-Gitlab/agent-memory-os/src PYTHONUNBUFFERED=1 \
  python3 -m agent_memory_os.web_app --host 127.0.0.1 --port 8000 --home /home/hermes/.agent-memory-os-web
```

Runtime process:

- Hermes session: `proc_b629303937b0`
- PID: `2369731`
- Bind: `127.0.0.1:8000`

## Verification evidence

Timestamp: `2026-06-17 22:57:24 CST (+0800)`

Listener:

```text
LISTEN 0 2048 127.0.0.1:8000 users:(("python3",pid=2369731,fd=14))
```

HTTP smoke on `8000`:

```text
/ status=200 content_type=text/html; charset=utf-8
/health status=200 content_type=application/json body='{"status":"ok"}'
/api/stats status=200 content_type=application/json body='{"total":1,"by_scope":{"user":1},"by_type":{"note":1},"cache_items":0}'
```

## Correct diagnosis

The immediate WebUI unavailability on the expected endpoint was: no listener on `127.0.0.1:8000` before the corrective startup.

The earlier `8765` recovery was incorrect for the requested operational endpoint and is superseded by this evidence file.

## Remaining durability caveat

This is still a temporary tracked Hermes background process, not a durable supervisor/systemd deployment. If the process exits or the host/session restarts, port `8000` will become unavailable again unless a persistent service is configured.
