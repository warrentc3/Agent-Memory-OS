# Memory Resonance Prototype: Graph Index Implementation
## Status: Initial Prototype (v0.4-alpha)

The initial implementation of the `ERATripletIndex` in `src/agent_memory_os/memory_resonance.py` provides:
1. **ERA Triplet Extraction**: Automatic detection of Subject-Relation-Object patterns.
2. **Two-Hop Resonance Expansion**: `resonance_cluster` method allows traversing shared entities to find logically linked memories.
3. **Deterministic Ranking**: Seeds first, then by graph distance and term overlap.

### Next Steps for Prototype:
- Integrate `ERATripletIndex` with the main `MemoryClient` as a secondary retrieval provider.
- Implement the `ResonanceWeight` logic (edge strength + temporal decay).
- Expand the regex patterns for more complex relation extraction.
- Compare resonance-retrieved clusters against standard k-NN results for a "Resonance Evidence Pack".
