from agent_memory_os.context_pack import approx_tokens, build_context_pack
from agent_memory_os.schema import MemoryRecord, SearchResult


def test_approx_tokens_is_positive():
    """Lineage:
    main: introduced d02c22b5@pre-migration-registry.
    """
    assert approx_tokens("") == 1
    assert approx_tokens("abcd") == 1
    assert approx_tokens("abcde") == 2


def test_context_pack_respects_small_budget():
    """Lineage:
    main: introduced d02c22b5@pre-migration-registry.
    """
    results = [
        SearchResult(MemoryRecord(content="x" * 500, importance=0.9, confidence=0.9), score=1.0),
        SearchResult(MemoryRecord(content="y" * 500, importance=0.8, confidence=0.8), score=0.9),
    ]
    pack = build_context_pack(results, max_tokens=64)
    assert pack.startswith("MEMORY CONTEXT PACK")
    assert len(pack) < 320
