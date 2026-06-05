# Technical Specification: Memory Resonance (v0.4)

## 1. Conceptual Architecture
**Memory Resonance** moves beyond linear vector-space retrieval (k-NN) and adopts a **Graph-Neural Hybrid** approach. Instead of just finding "similar" chunks, the system identifies "resonant" clusters of memories that are logically, temporally, or emotionally linked.

### Linear Retrieval vs. Resonance
- **Linear (v0.3):** Query $\to$ Vector Search $\to$ Top-K nearest neighbors.
- **Resonance (v0.4):** Query $\to$ Initial Seed $\to$ **Associative Expansion** (Walking the Graph) $\to$ Resonance Cluster $\to$ Synthesis.

## 2. Technical Stack
The Resonance layer will be implemented as a graph index bridging the existing vector stores.

- **Graph Engine:** `Neo4j` (Enterprise) or `NetworkX` (Lightweight/Embedded) for relationship mapping.
- **Indexing:** Custom graph indices for "Entity-Relation-Attribute" (ERA) triplets.
- **Integration:** Wrapper around existing `AgentMemoryOS` plugins to map vector IDs to graph nodes.

## 3. Implementation Plan

### Phase 1: Graph Schema Definition
- Define nodes: `MemoryChunk`, `Entity`, `Concept`, `Timestamp`.
- Define edges: `RELATED_TO`, `CONTRASTS_WITH`, `EVOLVED_FROM`, `MENTIONS`.

### Phase 2: Associative Retrieval Algorithm
1. **Seed Capture:** Perform a standard vector search to find the top 3 most relevant chunks.
2. **Graph Walk:** Traverse 2-hop neighbors of the seeds to gather contextually relevant but non-similar memories.
3. **Weighting:** Apply a "Resonance Weight" based on edge strength and temporal decay.
4. **Re-ranking:** Use a cross-encoder to finalize the context window.

### Phase 3: Dynamic Pruning
- Implement "Memory Decay" where unused edges are weakened over time, simulating biological forgetting and focusing the "Resonance" on high-utility paths.

## 4. Expected Outcomes
- **Complex Recall:** Ability to retrieve a sequence of events that are not semantically similar but logically linked.
- **Synthesis:** Better generation of "insights" by connecting distant but related memory nodes.
- **Efficiency:** Reduced context window noise by filtering out non-resonant vectors.
