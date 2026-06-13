
## [2026-06-13] Fix: SearchResult Schema Inconsistency
- Fixed AttributeError in `MemoryClient.resonance_search` where `SearchResult` was accessed as `MemoryRecord`.
- Added ISO-to-Unix timestamp conversion for resonance weight calculations.
- Verified property alignment between `schema.py` and `client.py`.
