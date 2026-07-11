# Examples

Runnable, self-contained scripts (each uses a throwaway SQLite home — no setup,
no server, no LLM). Run from the repo root:

```bash
pip install agent-memory-os
python examples/team_memory.py
```

| Example | Shows |
|---|---|
| [`team_memory.py`](team_memory.py) | Three agents share one store under a hard ACL — private / team / project / global visibility, requester-gated recall, a budgeted context pack, and instant re-scoping when a member is removed. |

Each script also asserts its expected output, so it doubles as a smoke test.
