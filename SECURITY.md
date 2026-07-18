# Security Policy

AgentMemoryOS stores and shares memories under an access-control model, so we
take security reports seriously.

## Reporting a vulnerability

**Please do not open a public issue for a security vulnerability.**

Report privately via GitHub's **[Report a vulnerability](https://github.com/yamantaka520/Agent-Memory-OS/security/advisories/new)**
(Security → Advisories), or email the maintainer listed on the GitHub profile.
Include: affected version (`agent-memory check` shows the schema version), a
description, and a minimal reproduction if possible.

We aim to acknowledge within a few days, agree on a fix and disclosure timeline,
and credit you in the release notes unless you prefer to remain anonymous.

## Supported versions

Fixes land on the latest `1.x` release. Because the database self-migrates
forward, upgrading to the newest version is the supported remediation path.

## Threat model & known limitations

AgentMemoryOS is **local-first**: the primary deployment is a personal or team
machine, and the strongest boundary is the OS user account that owns the
`~/.agent-memory` directory. Read [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md)
for the full model. The load-bearing points:

- **The ACL is enforced for honest callers, in-process.** `visibility`
  (private / agent / team / project / global) is a hard gate applied before
  ranking on every read path. It protects agents *cooperating through the same
  store*; it is **not** a sandbox against a local user who can read the SQLite
  file directly. Protect the file with OS permissions; use full-disk or
  filesystem encryption (or SQLCipher) if the host is untrusted.

- **The Web API is one shared bearer token (coarse trust).** Any full-token
  holder is effectively admin. Two narrower tiers exist: a **read-only** token
  (GET-only, but still sees all readable content) and a **sync** token
  (`agent-memory token create --sync`) that authorizes *only* the federation
  routes (`/api/node`, `/api/sync/*`) — hand that to a peer instead of the admin
  token. There is still no per-user authentication. Bind to `127.0.0.1`
  (default) or front it with a reverse proxy that adds real auth before exposing
  it.

- **Federation trusts peers up to their declared policy — and no further.** A
  peer can only assert org membership within its own `team:`/`project:` scope,
  can only *shrink* a memory's visibility (never escalate it), and anonymous
  HTTP pushes cannot mutate org structure at all. But peers are still
  semi-trusted collaborators, not adversaries: a malicious *full*-policy peer,
  or one you explicitly scoped to a team, can do damage within that scope. Only
  grant `full` to nodes you own.

- **Pairing codes are bearer credentials for one join.** `team invite` codes
  are single-use with a short TTL, stored hash-only, and grant nothing without
  a valid code. Anyone holding an unexpired code can join that one team and
  receive a sync token and the mesh key, so share codes over a channel you
  trust and mint them just-in-time. The redeem endpoint
  (`POST /api/pairing/redeem`) is the only API route exempt from bearer auth.
  The redeem bodies are Fernet-encrypted under the code, which keeps the
  tokens/mesh key out of URL/header access logs — but the code rides in the
  same POST body (the server needs it to decrypt), so this is **not**
  confidentiality against a full-body network observer. For a join beyond
  loopback use TLS: `agent-memory join` refuses a non-local `http://` target
  unless you pass `--insecure`. (A future asymmetric handshake would remove
  the need to transmit the code at all.)

- **Peer transport: content encryption is available; protect the token with
  TLS.** Set a shared mesh key (`agent-memory sync genkey`, distributed as
  `AGENT_MEMORY_SYNC_KEY` on every node) and sync bundles are encrypted
  app-layer (Fernet / AES-128-CBC+HMAC) — the memory content stays confidential
  even over plain HTTP or through a TLS-terminating proxy, because the key is a
  separate secret that never crosses the wire. HTTPS peer URLs are certificate-
  verified. The **bearer token itself still travels in the `Authorization`
  header**, so for a non-localhost peer also run it over TLS (reverse proxy or
  tunnel) and use a sync-scoped token so a captured token grants only sync
  access, not admin. Encryption is opportunistic: it engages only when a mesh
  key is configured, so set the key on *all* nodes for confidentiality.

- **Revocation reaches honest nodes that keep syncing.** Revoking access
  propagates and retracts already-synced memory on peers that sync again. It
  cannot reach a node that has left the mesh (or an operator who copied the DB):
  once bytes have left your machine, treat them as disclosed. See the threat
  model for the precise guarantee.

None of these are defects — they are the boundaries of a local-first design.
They are documented so you can deploy within them.
