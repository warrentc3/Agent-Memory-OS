<p align="center">
  <img src="https://raw.githubusercontent.com/yamantaka520/Agent-Memory-OS/main/assets/agent-memory-os-logo-integrated-v2.png" alt="Agent Memory OS" width="560">
</p>

<p align="center">A local-first, open-source memory engine for AI-agent <b>teams</b>.</p>

---

One SQLite file is the whole brain: durable memories with a hard **requester-aware
ACL**, an associative **resonance** recall graph, budgeted **context packs**, and
**federated sync** across nodes with a real trust model. Ships an **MCP server**
(so Claude Code / Codex / any MCP client can remember across sessions) and a
**FastAPI web console** — all behind one bearer token.

## Quick start

```bash
docker run -d --name agent-memory \
  -p 8000:8000 \
  -v agent-memory-data:/data \
  yamantaka520/agent-memory-os:latest
```

The container generates a Web API token on first boot — read it from the logs:

```bash
docker logs agent-memory | grep -i token
```

Then open **http://localhost:8000** and paste the token. The MCP server runs the
same image; the database lives in the `/data` volume and self-migrates forward on
every upgrade.

### docker compose

```yaml
services:
  agent-memory:
    image: yamantaka520/agent-memory-os:latest
    ports: ["8000:8000"]
    volumes: ["agent-memory-data:/data"]
    restart: unless-stopped
volumes:
  agent-memory-data:
```

## What's inside

- **Requester-aware ACL** — private / agent / team / project / global visibility, a
  hard gate enforced before ranking, never a soft score.
- **Teams & projects, federated** — membership converges across nodes; per-peer
  policy (`shared` / `full` / `team:` / `project:`) is an enforced authorization
  scope. Revocation propagates — revoking access retracts already-synced memory.
- **Resonance recall** — an authoritative link graph surfaces related memories
  even without shared query terms; traversal is ACL-safe.
- **Context packs** — token-budgeted, auditable memory selection per prompt.
- **Ops built in** — `/healthz` (readiness) and `/metrics` (Prometheus), one-click
  maintenance, backup rotation, a read-only token tier, and a self-updater.

## Tags

- `latest` — the newest stable release
- `1.0.0`, `0.14.0`, … — pinned versions (use a pin in production)

Multi-arch: `linux/amd64` and `linux/arm64`.

## Configuration (env)

| Variable | Purpose |
|---|---|
| `AGENT_MEMORY_WEB_TOKEN` | Set a fixed Web API token instead of the generated one. |
| `AGENT_MEMORY_WEB_READONLY_TOKEN` | A second, GET-only token for dashboards/auditors. |
| `AGENT_MEMORY_NODE_NAME` | This node's name in sync/federation. |

The image's `HEALTHCHECK` probes `/healthz`. A two-node sync mesh and full env
reference are in the [Docker guide](https://github.com/yamantaka520/Agent-Memory-OS/blob/main/docs/DOCKER.md).

## Links

- **Source & docs:** https://github.com/yamantaka520/Agent-Memory-OS
- **PyPI:** https://pypi.org/project/agent-memory-os/ (`pip install 'agent-memory-os[full]'`)
- **User guide:** https://github.com/yamantaka520/Agent-Memory-OS/blob/main/docs/USER_GUIDE.md
- **License:** Apache-2.0
