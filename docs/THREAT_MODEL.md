# Threat model

What AgentMemoryOS defends against, what it doesn't, and why. This is the
honest contract behind the ACL and federation features — read it before
deploying beyond a single trusted machine.

## Assets

1. **Memory content** — potentially sensitive facts, preferences, and context.
2. **The ACL graph** — who (agent/team/project) may read what.
3. **The Web API token(s)** — the credential to the console/API.

## Trust boundaries

```
OS user account (owns ~/.agent-memory)      <- the strong boundary
  └─ AgentMemoryOS process (SDK / MCP / Web)
       └─ in-process ACL hard gate           <- honest-caller boundary
            └─ agents (private/agent/team/project/global)
  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─
  network: Web API (bearer token) · peer sync (policy-scoped)
```

## What it defends against (in scope)

- **Cross-agent over-reading through the store.** An agent querying via the SDK,
  MCP, or Web API only receives memories its `requester_agent_id` may see. The
  gate runs before ranking; candidate indexes (FTS/vector/resonance) return ids
  only, and content is re-read from SQLite behind the gate. An invisible memory
  can't even bridge two visible ones in resonance traversal.
- **Accidental cross-scope leakage in federation.** A bundle from a peer is
  merged under the peer's declared policy scope. A `team:X` peer may only assert
  team X (+ its projects); it cannot inject membership into another team, cannot
  *widen* any memory's visibility (only shrink — i.e. propagate a revoke), and
  cannot delete org structure outside its scope. Future-dated timestamps are
  rejected so a forged clock can't pin state. Anonymous HTTP `POST /api/sync/import`
  runs untrusted with **no** org mutations.
- **Silent index tampering.** SQLite is the sole source of truth; disposable
  indexes are rebuildable and never authoritative. `agent-memory check` verifies
  integrity.
- **Unauthenticated API access.** When a token is configured, every `/api/`
  route requires it (`/healthz` and `/metrics` are intentionally open and expose
  only aggregate counts).

## What it does NOT defend against (out of scope)

- **A local user reading the SQLite file directly.** The ACL is an application
  gate, not encryption. Anyone who can `sqlite3 memories.db` sees everything.
  → Mitigate with OS file permissions and disk/SQLCipher encryption.
- **A malicious `full`-policy peer.** `full` means "my own trusted replica." Such
  a peer can push private/global memory. → Only grant `full` to machines you own.
- **A scoped peer abusing its own scope.** A `team:X` peer is trusted for team X.
  It can add/remove team-X members within that scope. → Scope peers minimally;
  federation is for collaborators, not adversaries.
- **Network eavesdropping.** Sync and the API speak plain HTTP. → Put anything
  beyond localhost behind TLS.
- **Token compromise.** One shared bearer token = admin. There is no per-user
  auth. → Keep the token secret; bind to localhost or add real auth at a proxy.
- **Retracting data from a departed node.** Revocation propagates to nodes that
  keep syncing; it cannot reach a node that left the mesh or a copied database.
  → Once memory has synced off your machine, treat it as disclosed.

## Revocation guarantee (precise)

When you revoke a share (or remove a member), the change rides the independent
ACL clock and, on the next sync, an honest peer **removes the grant** (or drops
the now-orphaned memory). This holds for peers that continue to sync with a node
carrying the revocation. It is **eventual** (converges on next contact) and
**cooperative** (assumes honest peer software). It is not a cryptographic
guarantee and does not reach offline/departed nodes.

## Hardening checklist

- [ ] `chmod 700 ~/.agent-memory`; keep it on a local disk you control.
- [ ] Configure a Web token (`agent-memory token create`); never expose the API
      tokenless on a shared network.
- [ ] Use the read-only token for dashboards/auditors.
- [ ] Terminate TLS in front of any non-localhost peer or console.
- [ ] Grant `full` peer policy only to nodes you own; scope everyone else to the
      narrowest `team:`/`project:`.
- [ ] Encrypt the disk (or use SQLCipher) if the host is shared or portable.
