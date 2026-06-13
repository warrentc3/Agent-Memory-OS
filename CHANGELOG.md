# Changelog - Agent Memory OS

## [2026-06-13] Feature: Dynamic Context Orchestration (DCO) & Fixes
- **Feature**: Implemented Dynamic Context Orchestration (DCO) for active/dormant memory management.
- **Testing**: Completed precision test suite in `tests/test_context_orchestration.py`, establishing the performance baseline.
- **Fix**: Resolved `asdict` serialization issue in `client.py`.
- **Fix**: Corrected `session_id` indexing and prefixing in the memory client to ensure consistent snapshot retrieval.
- **Fix**: Fixed `SearchResult` schema inconsistency and `AttributeError` in `resonance_search`.
- **Fix**: Added ISO-to-Unix timestamp conversion for resonance weight calculations.

## [2026-06-12] Initial DCO Scaffolding
- Defined `ContextSnapshot` schema and basic API signatures.
