from __future__ import annotations

import numpy as np
import pytest

from agent_memory_os.providers.turbovec import TurbovecSemanticCandidateProvider, semantic_backend_available
from agent_memory_os.providers.turbovec import UINT64_MAX


class CapturingIndex:
    def __init__(self, scores=None, ids=None):
        self.queries = None
        self.k = None
        self.allowlist = None
        self.scores = scores if scores is not None else np.array([[0.91, 0.42]], dtype=np.float32)
        self.ids = ids if ids is not None else np.array([[42, 7]], dtype=np.uint64)

    def search(self, queries, k, *, allowlist=None):
        self.queries = queries
        self.k = k
        self.allowlist = allowlist
        return self.scores, self.ids


def test_turbovec_provider_returns_memory_id_candidates_not_content():
    index = CapturingIndex()
    provider = TurbovecSemanticCandidateProvider(
        index=index,
        external_id_to_memory_id={42: "mem-alpha", 7: "mem-beta"},
        embed_query=lambda query: np.ones(8, dtype=np.float32),
    )

    candidates = list(provider.candidates("semantic query", limit=2))

    assert [(candidate.memory_id, candidate.provider, candidate.rank) for candidate in candidates] == [
        ("mem-alpha", "turbovec", 1),
        ("mem-beta", "turbovec", 2),
    ]
    assert candidates[0].score == pytest.approx(0.91)
    assert candidates[1].score == pytest.approx(0.42)
    assert all(not hasattr(candidate, "content") for candidate in candidates)
    assert index.k == 2


def test_turbovec_provider_uses_c_contiguous_uint64_allowlist():
    index = CapturingIndex()
    provider = TurbovecSemanticCandidateProvider(
        index=index,
        external_id_to_memory_id={42: "mem-alpha", 7: "mem-beta"},
        embed_query=lambda query: np.ones(8, dtype=np.float32),
    )
    non_contiguous_allowlist = np.array([999, 42, 888, 7], dtype=np.int64)[1::2]
    assert not non_contiguous_allowlist.flags.c_contiguous

    list(provider.candidates("semantic query", limit=2, allowed_external_ids=non_contiguous_allowlist))

    assert index.allowlist is not None
    assert index.allowlist.dtype == np.uint64
    assert index.allowlist.flags.c_contiguous
    assert index.allowlist.tolist() == [42, 7]


def test_turbovec_provider_skips_unmapped_external_ids():
    index = CapturingIndex(
        scores=np.array([[0.8, 0.7]], dtype=np.float32),
        ids=np.array([[123, 42]], dtype=np.uint64),
    )
    provider = TurbovecSemanticCandidateProvider(
        index=index,
        external_id_to_memory_id={42: "mem-alpha"},
        embed_query=lambda query: np.ones(8, dtype=np.float32),
    )

    candidates = list(provider.candidates("semantic query", limit=2))

    assert [candidate.memory_id for candidate in candidates] == ["mem-alpha"]
    assert candidates[0].rank == 2


def test_turbovec_provider_detects_external_id_mapping_collisions():
    with pytest.raises(ValueError, match="external id collision"):
        TurbovecSemanticCandidateProvider.external_id_to_memory_id_map(
            {"mem-alpha": 77, "mem-beta": 77}
        )


@pytest.mark.parametrize("bad_external_id", [True, -1, UINT64_MAX + 1, 1.5, "1"])
def test_turbovec_provider_rejects_non_uint64_mapping_ids(bad_external_id):
    with pytest.raises(ValueError, match="uint64 integers"):
        TurbovecSemanticCandidateProvider.external_id_to_memory_id_map({"mem-alpha": bad_external_id})


@pytest.mark.parametrize("bad_allowlist_id", [True, -1, UINT64_MAX + 1, 1.5, "1"])
def test_turbovec_provider_rejects_non_uint64_allowlist_ids(bad_allowlist_id):
    index = CapturingIndex()
    provider = TurbovecSemanticCandidateProvider(
        index=index,
        external_id_to_memory_id={42: "mem-alpha"},
        embed_query=lambda query: np.ones(8, dtype=np.float32),
    )

    with pytest.raises(ValueError, match="uint64 integers"):
        list(provider.candidates("semantic query", allowed_external_ids=[bad_allowlist_id]))


def test_turbovec_provider_skips_malformed_backend_external_ids_without_wrapping():
    index = CapturingIndex(
        scores=np.array([[0.99, 0.7]], dtype=np.float32),
        ids=np.array([[-1, 42]], dtype=object),
    )
    provider = TurbovecSemanticCandidateProvider(
        index=index,
        external_id_to_memory_id={UINT64_MAX: "wrapped-sentinel-must-not-match", 42: "mem-alpha"},
        embed_query=lambda query: np.ones(8, dtype=np.float32),
    )

    candidates = list(provider.candidates("semantic query", limit=2))

    assert [candidate.memory_id for candidate in candidates] == ["mem-alpha"]


def test_turbovec_provider_handles_missing_optional_backend(monkeypatch):
    from agent_memory_os.providers import turbovec as provider_module

    def missing_backend():
        raise ImportError("turbovec missing")

    monkeypatch.setattr(provider_module, "_load_optional_dependencies", missing_backend)

    assert semantic_backend_available() is False
    with pytest.raises(RuntimeError, match="semantic optional dependencies are unavailable"):
        TurbovecSemanticCandidateProvider.from_vectors(
            vectors=np.ones((1, 8), dtype=np.float32),
            external_id_by_memory_id={"mem-alpha": 1},
            embed_query=lambda query: np.ones(8, dtype=np.float32),
        )


def test_turbovec_provider_from_vectors_smoke_when_dependency_is_available():
    pytest.importorskip("turbovec")
    provider = TurbovecSemanticCandidateProvider.from_vectors(
        vectors=np.eye(8, dtype=np.float32)[:2],
        external_id_by_memory_id={"mem-alpha": 101, "mem-beta": 202},
        embed_query=lambda query: np.eye(8, dtype=np.float32)[0],
        bit_width=4,
    )

    candidates = list(provider.candidates("semantic query", limit=1))

    assert len(candidates) == 1
    assert candidates[0].memory_id in {"mem-alpha", "mem-beta"}
    assert candidates[0].provider == "turbovec"
