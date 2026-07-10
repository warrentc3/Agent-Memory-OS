# AgentMemoryOS Roadmap Alignment

Last updated: 2026-06-06 23:48:38 CST (+0800)

## Authoritative runtime stance

AgentMemoryOS is now in **v0.4: Memory Resonance (PROTOTYPING)**.

### Current State: Early Canary Rollout
- **Status**: Phase 2 / Early Canary
- **Traffic Switch**: 20% production traffic routed to AgentMemoryOS
- **Mode**: Active Production Injection (Canary)
- **Production Injection**: `true` (Canary group)
- **Active Profiles**: `canary_group` (Expanded from neo/mizuki)

---

## Milestone Definitions

### v0.3.1: Shadow Evidence & Migration Safety (ACTIVE)
The primary goal is to provide an empirical aevidence-based guarantee that the new memory system is safe and precise before any production cutover.

**Required Evidence Gates:**
1. **Shadow Evidence Pack**: Empirical proof of acceptable latency and recall rates.
2. **Importer Safety**: Idempotent parsing of `MEMORY.md`/`USER.md` with zero duplicate growth.
3. **Migration/Rollback Safety**: Verified lossless data movement and instant recovery capability.
4. **ACL Zero-Leakage**: Verified absolute isolation between profiles in all retrieval paths.
5. **Golden Recall**: 100% hit rate on deterministic representative query sets.
6. **Mizuki Stress Cases**: Successful handling of persona-specific, contradictory, and high-volume memory scenarios.

### v0.4: Memory Resonance (LOCKED)
**Status: Future Research Milestone.**

v0.4 introduces the transition from linear vector search to a Graph-Neural Hybrid approach, enabling associative "resonance" across memory entities.

**Activation Condition:**
v0.4 development and reporting MUST NOT start until all v0.3.1 gates are marked `PASS` in a formal Evidence Bundle.

---

## Forbidden Claims (The "Hard Gates")

Until v0.3.1 is formally closed and a documented decision opens the next phase, the following claims are strictly prohibited:
- ❌ "v0.4 is complete" or "v0.4 is in active canary".
- ❌ "Production injection is enabled" (`production_injection=true`).
- ❌ "All profiles have been activated".
- ❌ "AgentMemoryOS is now the default Hermes memory backend".
