"""Embedding pipeline: semantic recall that works out of the box.

`HashingEmbedder` is the dependency-free default — deterministic feature
hashing over words and character trigrams. It captures lexical similarity in
vector space (typo- and morphology-tolerant), not deep semantics; swap in any
real embedding model by passing a `str -> sequence[float]` callable.

`AutoSemanticIndex` keeps a turbovec index in sync with the memories table by
watching a cheap change signature and rebuilding lazily — the disposable-index
philosophy: the vector index is never authoritative and can always be rebuilt
from SQLite.
"""

from __future__ import annotations

import math
import re
import zlib
from collections.abc import Iterable, Sequence

from .candidates import Candidate

_WORD_RE = re.compile(r"\w+", re.UNICODE)


class HashingEmbedder:
    """Deterministic feature-hashing embedder (no model, no downloads)."""

    def __init__(self, dim: int = 256):
        if dim < 16:
            raise ValueError("dim must be >= 16")
        self.dim = dim

    def __call__(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for feature in self._features(text):
            digest = zlib.crc32(feature.encode("utf-8"))
            index = digest % self.dim
            sign = 1.0 if (digest >> 16) & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]

    @staticmethod
    def _features(text: str) -> Iterable[str]:
        words = _WORD_RE.findall(text.lower())
        for word in words:
            yield "w:" + word
            padded = f"^{word}$"
            for i in range(len(padded) - 2):
                yield "t:" + padded[i : i + 3]


class AutoSemanticIndex:
    """CandidateProvider that self-maintains a turbovec index over the store.

    Rebuilds whenever the memories table changes (count / max rowid / max
    updated_at signature), so no write-path coupling is needed and multiple
    processes sharing the database each converge on their own fresh index.
    Returns candidate ids only; the store's ACL/expiry hard gates still apply.
    """

    name = "turbovec-auto"

    def __init__(self, store, embedder=None, *, dim: int = 256):
        self._store = store
        self._embedder = embedder or HashingEmbedder(dim)
        self._provider = None
        self._signature: tuple | None = None

    def candidates(
        self,
        query: str,
        *,
        owner: str | None = None,
        scope: str | None = None,
        requester_agent_id: str | None = None,
        requester_team_id: str | None = None,
        limit: int = 10,
    ) -> Sequence[Candidate]:
        signature = self._store.semantic_signature()
        if signature != self._signature:
            self._rebuild(signature)
        if self._provider is None:
            return []
        return list(
            self._provider.candidates(
                query,
                owner=owner,
                scope=scope,
                requester_agent_id=requester_agent_id,
                requester_team_id=requester_team_id,
                limit=limit,
            )
        )

    def _rebuild(self, signature: tuple) -> None:
        from .providers.turbovec import TurbovecSemanticCandidateProvider

        corpus = self._store.semantic_corpus()
        if not corpus:
            self._provider = None
            self._signature = signature
            return
        vectors = [self._embedder(text) for _, _, text in corpus]
        mapping = {memory_id: rowid for rowid, memory_id, _ in corpus}
        self._provider = TurbovecSemanticCandidateProvider.from_vectors(
            vectors=vectors,
            external_id_by_memory_id=mapping,
            embed_query=self._embedder,
        )
        self._signature = signature
