# Using AgentMemoryOS with Hermes Agent

Hermes integration follows this repository's activation-gate governance:
**shadow first, production only after the gates pass**
(see `docs/hermes-activation-gates.md`).

## 1. Import existing Hermes memory

Bring each profile's `MEMORY.md` / `USER.md` into the store (idempotent —
safe to re-run):

```bash
agent-memory import-hermes \
  --profile mizuki \
  --profile-home /path/to/hermes/profiles/mizuki \
  --json
```

Repeat per profile. Each profile becomes an `owner`, so requester-aware ACL
maps directly onto Hermes profile boundaries.

## 2. Shadow mode

Run AgentMemoryOS **beside** the production Hermes memory path: for each
Hermes recall, also query AgentMemoryOS and log the comparison — production
prompts keep using the existing path.

```python
from agent_memory_os import MemoryClient
from agent_memory_os.shadow_mode import ShadowModeRunner  # comparison logger

client = MemoryClient(home="/var/hermes/.agent-memory")
# log candidates + latency + ACL checks per query; never inject into prompts
```

Summarize the evidence and check the activation gate:

```bash
agent-memory shadow-summary --log agent_memory_os_shadow.jsonl --json
agent-memory golden-recall --cases golden_queries.json --json
```

## 3. Activation gates

Before switching Hermes' default memory backend, the gate list in
`PROJECT_STATUS.md` must pass: zero ACL leakage in shadow evidence, importer
idempotency, downgrade/rollback verification, golden recall at target, and
product acceptance. Until then, keep `production_injection=false`.

## 4. Per-profile personas

Give each Hermes profile a recall profile so retrieval matches its role:

```python
from agent_memory_os import RecallProfile
client.save_profile(RecallProfile(agent_id="mizuki",
                                  type_weights={"preference": 1.4, "note": 1.1}))
client.save_profile(RecallProfile(agent_id="neo",
                                  type_weights={"procedure": 1.5, "decision": 1.3}))
```

Searches with `requester_agent_id=<profile>` auto-apply the stored profile.

## Agent identity (multi-agent projects)

Set `AGENT_MEMORY_AGENT_ID` in the MCP server env so this agent's reads and
writes carry its identity: memories default to it as owner, and searches
automatically include every team the agent belongs to (register agents and
teams in the Web console's **Agents** tab, or via `POST /api/agents`).
