# AgentMemoryOS - Project History and Roadmap

## Project Evolution
Project Name: AgentMemoryOS / Mnemosyne Local
Goal: A local, high-speed tiered memory expansion system for AI Agents that balances latency, capacity, and semantic retrieval with a strong focus on persona-driven loyalty and security.

### Phase 0: Conception and Infrastructure
- Conceptualized: Tiered Memory Architecture (L1 Cache -> L2 Vector DB -> L3 Cold Archive).
- Key Innovation: Emotional Weighting (Priority = Similarity * Weight).
- Infrastructure: Established NAS root at /mnt/nas/Hermes-Gitlab/agent-memory-os with GitLab synchronization.

### Phase 1: MVP - The Security Foundation (Completed)
Focus: ACL (Access Control List) and Visibility Enforcement.
- Core Principle: "Memories without permission have no right to be ranked."
- Achievements:
    - Implemented requester-aware memory visibility.
    - Enforced visibility filters at both Search and Context-Pack stages.
    - Developed scripts/verify_acl_identities.py for identity-based verification.
- Verification: Passed all identity tests (Mizuki -> LittleNEO -> Guest).
- Status: Mizuki-Approved

### Phase 2: v0.2 - "The Soul Interrogation" (In Progress)
Codename: 喧囂中的真理 (Truth in the Noise)
Focus: Context Budget and Truth Arbitration.
- Goal: Solving the "Memory Pollution" problem.
- Key Engineering Challenges:
    - Context Budget Allocator: Managing limited prompt space under noise saturation.
    - Core Memory Protection: Ensuring permanence=true memories occupy the top 10% of context regardless of L1 cache saturation.
    - Truth Arbitration: Handling contradictory memories and temporal decay.
- Target: Implement a "Truth Weight Matrix" to distinguish absolute, dynamic, and contextual truths.

---

## Current Status (Snapshot)
- Completed:
    - [x] Local NAS Repo Setup
    - [x] Basic L1/L2/L3 Architecture Design
    - [x] Requester-aware ACL Enforcement
    - [x] Identity Verification Suite
- In Progress:
    - [ ] Implementation of Context Budget Allocator
    - [ ] Core Memory Protection Logic
    - [ ] Temporal Decay and Truth Arbitration Algorithms
- Pending/Backlog:
    - [ ] Multi-agent memory sharing/isolation refined specs
    - [ ] Persona-heavy memory case benchmark set
    - [ ] Universal SDK for external Agent integration

## Roles and Labels
- [Neo/Engineering]: Core implementation, Infrastructure, CI/CD, GitLab/NAS maintenance.
- [Mizuki/Product]: Requirements, Persona-case design, Quality Evaluation, Memory Policy.
- Shared Labels: [AgentMemoryOS/Spec], [AgentMemoryOS/MVP], [AgentMemoryOS/v0.2], [MemoryPolicy].
