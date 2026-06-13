"""Prototype graph-neural memory resonance primitives.

This module implements an embedded ERA (Entity-Relation-Attribute)
triplet index for AgentMemoryOS v0.4 experiments.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import re
import time
from typing import DefaultDict, Iterable

_TOKEN_RE = re.compile(r"\\b[A-Za-z][A-Za-z0-9_.-]*\\b")
_VERSION_RE = re.compile(r"\\bv\\d+(?:\\.\\d+)+\\b", re.IGNORECASE)
_USES_RE = re.compile(
    r"\\b(?P<subject>[A-Z][A-Za-z0-9_.-]*)\\s+uses\\s+"
    r"(?P<object>[A-Z][A-Za-z0-9_.-]*)\\b",
    re.IGNORECASE,
)
_EVOLVES_RE = re.compile(
    r"\\b(?P<subject>[A-Z][A-Za-z0-9_.-]*)\\s+evolves\\s+from\\s+"
    r"(?P<source>v\\d+(?:\\.\\d+)+)\\s+to\\s+(?P<target>v\\d+(?:\\.\\d+)+)\\b",
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
    timestamp: float = 0.0  # Unix timestamp for decay logic

class ResonanceWeight:
    """Logic for calculating memory resonance strength."""
    
    @staticmethod
    def calculate(base_strength: float, timestamp: float, current_time: float = None) -> float:
        """
        Compute weighted strength based on temporal decay and edge strength.
        Formula: Strength = max(min_weight, Base * exp(-lambda * delta_t))
        """
        if current_time is None:
            current_time = time.time()
            
        delta_t = max(0, current_time - timestamp)
        # Decay constant: reduced from 0.00000133 to 0.0000008 to mitigate recall drop
        decay_lambda = 0.0000008 
        decay_factor = 2.71828 ** (-decay_lambda * delta_t)
        
        # Introduce weight floor to prevent total resonance collapse
        min_weight = 0.01
        return max(min_weight, base_strength * decay_factor)

class ERATripletIndex:
    """Embedded ERA triplet index with ResonanceWeighting.
    
    Transitioned from basic distance ranking to weight-based resonance.
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
        """
        Expand seed chunks using ResonanceWeight.
        Ranked by calculated resonance strength instead of simple distance.
        """
        seeds = [chunk_id for chunk_id in seed_chunk_ids if chunk_id in self._chunks]
        if hops < 0:
            raise ValueError("hops must be >= 0")
        if not seeds:
            return []

        seed_terms = set().union(*(self._terms_by_chunk[seed] for seed in seeds))
        resonance_scores: dict[str, float] = {}
        
        # Initialize seeds with high base resonance
        current_time = time.time()
        for seed in seeds:
            chunk = self._chunks[seed]
            resonance_scores[seed] = ResonanceWeight.calculate(1.0, chunk.timestamp, current_time)

        # Expansion
        visited = set(seeds)
        queue = deque([(seed, 0, 1.0) for seed in seeds]) # (id, dist, strength)

        while queue:
            curr_id, dist, strength = queue.popleft()
            if dist >= hops:
                continue
            
            for neighbor in self._neighbors(curr_id):
                if neighbor in visited:
                    continue
                
                # Edge strength based on term overlap
                overlap = len(self._terms_by_chunk[neighbor] & self._terms_by_chunk[curr_id])
                edge_strength = overlap / max(1, len(self._terms_by_chunk[neighbor]))
                
                # Calculate resonance for neighbor
                chunk = self._chunks[neighbor]
                decayed_strength = ResonanceWeight.calculate(edge_strength * strength, chunk.timestamp, current_time)
                
                resonance_scores[neighbor] = decayed_strength
                visited.add(neighbor)
                queue.append((neighbor, dist + 1, decayed_strength))

        # Sort by resonance score descending
        return sorted(resonance_scores.keys(), key=lambda cid: resonance_scores[cid], reverse=True)

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
                triplets.add((subject, "timestamp", str(chunk.timestamp)))
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
