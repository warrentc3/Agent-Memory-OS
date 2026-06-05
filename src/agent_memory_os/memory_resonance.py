"""Prototype graph-neural memory resonance primitives.

This module implements a lightweight embedded ERA (Entity-Relation-Attribute)
triplet index for AgentMemoryOS v0.4 experiments.  It intentionally avoids
external graph dependencies so shadow-mode probes can run in constrained test
and gateway environments.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import re
from typing import DefaultDict, Iterable


_TOKEN_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9_.-]*\b")
_VERSION_RE = re.compile(r"\bv\d+(?:\.\d+)+\b", re.IGNORECASE)
_USES_RE = re.compile(
    r"\b(?P<subject>[A-Z][A-Za-z0-9_.-]*)\s+uses\s+"
    r"(?P<object>[A-Z][A-Za-z0-9_.-]*)\b",
    re.IGNORECASE,
)
_EVOLVES_RE = re.compile(
    r"\b(?P<subject>[A-Z][A-Za-z0-9_.-]*)\s+evolves\s+from\s+"
    r"(?P<source>v\d+(?:\.\d+)+)\s+to\s+(?P<target>v\d+(?:\.\d+)+)\b",
    re.IGNORECASE,
)
_STOPWORDS = {
    "and",
    "for",
    "from",
    "mode",
    "the",
    "to",
    "topic",
    "uses",
    "with",
}


@dataclass(frozen=True)
class MemoryChunk:
    """A memory unit that can be projected into the resonance graph."""

    id: str
    text: str
    timestamp: str = ""


class ERATripletIndex:
    """Embedded ERA triplet index with two-hop resonance expansion.

    The prototype stores memory chunks, extracts simple ERA triplets, and links
    chunks through shared entities/concepts.  It is designed as the v0.4
    bootstrap before a production graph backend such as Neo4j is introduced.
    """

    def __init__(self) -> None:
        self._chunks: dict[str, MemoryChunk] = {}
        self._triplets_by_chunk: DefaultDict[str, set[tuple[str, str, str]]] = defaultdict(set)
        self._terms_by_chunk: DefaultDict[str, set[str]] = defaultdict(set)
        self._chunks_by_term: DefaultDict[str, set[str]] = defaultdict(set)

    def add_chunk(self, chunk: MemoryChunk) -> None:
        """Add or replace a chunk and index its ERA terms."""

        if not chunk.id:
            raise ValueError("MemoryChunk.id must be non-empty")

        self._remove_chunk_terms(chunk.id)
        self._chunks[chunk.id] = chunk

        triplets = self._extract_triplets(chunk)
        terms = self._extract_terms(chunk.text)
        terms.update(_normalize(value) for triplet in triplets for value in triplet)
        terms.discard("")

        self._triplets_by_chunk[chunk.id] = triplets
        self._terms_by_chunk[chunk.id] = terms
        for term in terms:
            self._chunks_by_term[term].add(chunk.id)

    def triplets_for_chunk(self, chunk_id: str) -> set[tuple[str, str, str]]:
        """Return extracted ERA triplets for a chunk."""

        return set(self._triplets_by_chunk.get(chunk_id, set()))

    def resonance_cluster(self, seed_chunk_ids: Iterable[str], *, hops: int = 2) -> list[str]:
        """Expand seed chunks through shared ERA terms and rank the cluster.

        Ranking is deterministic: seeds first, then closer graph distance, then
        stronger term overlap with the seed set, then chunk id.
        """

        seeds = [chunk_id for chunk_id in seed_chunk_ids if chunk_id in self._chunks]
        if hops < 0:
            raise ValueError("hops must be >= 0")
        if not seeds:
            return []

        seed_terms = set().union(*(self._terms_by_chunk[seed] for seed in seeds))
        distances: dict[str, int] = {seed: 0 for seed in seeds}
        queue: deque[tuple[str, int]] = deque((seed, 0) for seed in seeds)

        while queue:
            chunk_id, distance = queue.popleft()
            if distance >= hops:
                continue
            for neighbor in self._neighbors(chunk_id):
                if neighbor in distances:
                    continue
                distances[neighbor] = distance + 1
                queue.append((neighbor, distance + 1))

        return sorted(
            distances,
            key=lambda chunk_id: (
                distances[chunk_id],
                -len(self._terms_by_chunk[chunk_id] & seed_terms),
                chunk_id,
            ),
        )

    def _neighbors(self, chunk_id: str) -> set[str]:
        neighbors: set[str] = set()
        for term in self._terms_by_chunk.get(chunk_id, set()):
            neighbors.update(self._chunks_by_term.get(term, set()))
        neighbors.discard(chunk_id)
        return neighbors

    def _remove_chunk_terms(self, chunk_id: str) -> None:
        for term in self._terms_by_chunk.get(chunk_id, set()):
            chunk_ids = self._chunks_by_term.get(term)
            if not chunk_ids:
                continue
            chunk_ids.discard(chunk_id)
            if not chunk_ids:
                self._chunks_by_term.pop(term, None)
        self._terms_by_chunk.pop(chunk_id, None)
        self._triplets_by_chunk.pop(chunk_id, None)

    def _extract_triplets(self, chunk: MemoryChunk) -> set[tuple[str, str, str]]:
        triplets: set[tuple[str, str, str]] = set()

        for match in _USES_RE.finditer(chunk.text):
            triplets.add((match.group("subject"), "uses", match.group("object")))

        primary_entity = self._primary_entity(chunk.text)
        for match in _EVOLVES_RE.finditer(chunk.text):
            subject = match.group("subject")
            if _normalize(subject) in _STOPWORDS and primary_entity:
                subject = primary_entity
            triplets.add((subject, "evolves_from", match.group("source")))
            triplets.add((subject, "evolves_to", match.group("target")))

        if chunk.timestamp:
            subject = self._primary_entity(chunk.text)
            if subject:
                triplets.add((subject, "timestamp", chunk.timestamp))

        return triplets

    def _primary_entity(self, text: str) -> str:
        for token in _TOKEN_RE.findall(text):
            if token[:1].isupper() and _normalize(token) not in _STOPWORDS:
                return token
        return ""

    def _extract_terms(self, text: str) -> set[str]:
        terms = {_normalize(token) for token in _TOKEN_RE.findall(text)}
        terms.update(_normalize(version) for version in _VERSION_RE.findall(text))
        return {term for term in terms if term and term not in _STOPWORDS}


def _normalize(value: str) -> str:
    return value.strip().lower()
