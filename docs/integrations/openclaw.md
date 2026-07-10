# Using AgentMemoryOS with OpenClaw

OpenClaw agents can attach AgentMemoryOS two ways: as an MCP stdio server
(preferred when your OpenClaw build has MCP support) or through the HTTP API.

## 1. Install

```bash
pip install 'agent-memory-os[full]'
agent-memory doctor
agent-memory token create        # you'll need this for the HTTP route
```

## Option A — MCP server

Register a stdio MCP server in your OpenClaw configuration (see OpenClaw's
docs for the exact config location; the server definition is standard MCP):

- **command**: `python`
- **args**: `["-m", "agent_memory_os.mcp_server"]`
- **env**: `AGENT_MEMORY_HOME=/path/to/.agent-memory`

The agent then gets `memory_add`, `memory_search`, `memory_context_pack`,
`memory_link`, `memory_update`, `memory_recall_feedback`,
`memory_consolidate`, and the DCO tools `memory_offload_context` /
`memory_reload_context`.

## Option B — HTTP API

Run the server:

```bash
agent-memory-web --host 127.0.0.1 --port 8000
```

Then call it from your OpenClaw skill/plugin with the bearer token:

```python
import requests

BASE = "http://127.0.0.1:8000"
HEADERS = {"Authorization": "Bearer <token from `agent-memory token show`>"}
AGENT_ID = "openclaw-main"

def recall(task_summary: str) -> str:
    response = requests.get(f"{BASE}/api/context-pack", headers=HEADERS, params={
        "q": task_summary, "requester_agent_id": AGENT_ID, "auto_reinforce": "true",
    })
    return response.json()["text"]

def remember(content: str, private: bool = False) -> str:
    response = requests.post(f"{BASE}/api/memories", headers=HEADERS, json={
        "content": content, "owner": AGENT_ID,
        "visibility": [] if private else ["global"],
        "auto_link": True,
    })
    return response.json()["id"]
```

Inject `recall(...)` output at the top of the prompt each turn; call
`remember(...)` when the agent learns something durable.

## Multi-agent OpenClaw fleets

Point every agent at the same `AGENT_MEMORY_HOME` (or the same HTTP server)
and give each a distinct `owner` / `requester_agent_id`. Private memories
stay private; `visibility: ["global"]` shares knowledge fleet-wide.

## Agent identity (multi-agent projects)

Set `AGENT_MEMORY_AGENT_ID` in the MCP server env so this agent's reads and
writes carry its identity: memories default to it as owner, and searches
automatically include every team the agent belongs to (register agents and
teams in the Web console's **Agents** tab, or via `POST /api/agents`).
