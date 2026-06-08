from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from numbers import Integral
from typing import Any
import math

from agent_memory_os.candidates import Candidate

UINT64_MAX = (1 << 64) - 1


def _load_optional_dependencies() -> tuple[Any, type]:
    """Load optional semantic dependencies lazily.

    The base package must remain importable without numpy/turbovec. Only users
    who explicitly construct/build the provider need the optional extra.
    """
    import numpy as np  # type: ignore[import-not-found]
    from turbovec import IdMapIndex  # type: ignore[import-not-found]

    return np, IdMapIndex


def semantic_backend_available() -> bool:
    """Return whether optional turbovec semantic dependencies are importable."""
    try:
        _load_optional_dependencies()
    except Exception:
        return False
    return True


@dataclass(slots=True)
class TurbovecSemanticCandidateProvider:
    """Disposable turbovec-backed semantic candidate sidecar.

    This provider returns stable SQLite ``memory_id`` candidates only. It never
    returns memory content and must always be followed by authoritative SQLite
    rejoin plus ACL/expiry hard gates by the caller.
    """

    index: Any
    external_id_to_memory_id: Mapping[int, str]
    embed_query: Callable[[str], Any]
    name: str = "turbovec"
    _np: Any | None = None

    def __post_init__(self) -> None:
        if self._np is None:
            self._np = _load_optional_dependencies()[0]
        self.external_id_to_memory_id = self._validate_external_to_memory_map(self.external_id_to_memory_id)

    @classmethod
    def from_vectors(
        cls,
        *,
        vectors: Any,
        external_id_by_memory_id: Mapping[str, int],
        embed_query: Callable[[str], Any],
        bit_width: int = 4,
    ) -> "TurbovecSemanticCandidateProvider":
        """Build an in-memory IdMapIndex from vectors and stable ID mapping."""
        try:
            np, id_map_index = _load_optional_dependencies()
        except Exception as exc:  # pragma: no cover - exact dependency differs by env
            raise RuntimeError("semantic optional dependencies are unavailable") from exc

        external_to_memory = cls.external_id_to_memory_id_map(external_id_by_memory_id)
        vector_array = np.ascontiguousarray(vectors, dtype=np.float32)
        if vector_array.ndim != 2 or vector_array.shape[0] != len(external_id_by_memory_id):
            raise ValueError("vectors must be a 2D array with one row per memory id")
        if vector_array.shape[1] <= 0:
            raise ValueError("vectors must have a positive dimension")

        external_ids = [external_id_by_memory_id[memory_id] for memory_id in external_id_by_memory_id]
        id_array = np.ascontiguousarray(external_ids, dtype=np.uint64)
        index = id_map_index(dim=int(vector_array.shape[1]), bit_width=bit_width)
        index.add_with_ids(vector_array, id_array)
        index.prepare()
        return cls(index=index, external_id_to_memory_id=external_to_memory, embed_query=embed_query, _np=np)

    @classmethod
    def external_id_to_memory_id_map(cls, external_id_by_memory_id: Mapping[str, int]) -> dict[int, str]:
        """Invert a memory_id -> uint64 map, rejecting unsafe collisions."""
        external_to_memory: dict[int, str] = {}
        for memory_id, external_id in external_id_by_memory_id.items():
            clean_memory_id = cls._validate_memory_id(memory_id)
            clean_external_id = cls._validate_external_id(external_id)
            previous = external_to_memory.get(clean_external_id)
            if previous is not None and previous != clean_memory_id:
                raise ValueError(
                    f"external id collision for {clean_external_id}: {previous!r} and {clean_memory_id!r}"
                )
            external_to_memory[clean_external_id] = clean_memory_id
        return external_to_memory

    def candidates(
        self,
        query: str,
        *,
        owner: str | None = None,
        scope: str | None = None,
        requester_agent_id: str | None = None,
        requester_team_id: str | None = None,
        limit: int = 10,
        allowed_external_ids: Iterable[int] | None = None,
    ) -> Iterable[Candidate]:
        del owner, scope, requester_agent_id, requester_team_id
        if limit <= 0:
            return []

        np = self._np if self._np is not None else _load_optional_dependencies()[0]
        query_vector = np.ascontiguousarray([self.embed_query(query)], dtype=np.float32)
        allowlist = None
        if allowed_external_ids is not None:
            validated_ids = [self._validate_external_id(external_id) for external_id in allowed_external_ids]
            allowlist = np.ascontiguousarray(validated_ids, dtype=np.uint64)
            if allowlist.size == 0:
                return []

        scores, external_ids = self.index.search(query_vector, int(limit), allowlist=allowlist)
        flat_scores = np.asarray(scores).reshape(-1)
        flat_ids = np.asarray(external_ids).reshape(-1)

        candidates: list[Candidate] = []
        for rank, (score, external_id) in enumerate(zip(flat_scores, flat_ids), start=1):
            try:
                clean_external_id = self._validate_external_id(external_id)
            except ValueError:
                continue
            memory_id = self.external_id_to_memory_id.get(clean_external_id)
            if memory_id is None:
                continue
            clean_score = self._clamp_score(score)
            candidates.append(
                Candidate(
                    memory_id=memory_id,
                    provider=self.name,
                    score=clean_score,
                    rank=rank,
                )
            )
        return candidates

    @classmethod
    def _validate_external_to_memory_map(cls, mapping: Mapping[int, str]) -> dict[int, str]:
        validated: dict[int, str] = {}
        for external_id, memory_id in mapping.items():
            clean_external_id = cls._validate_external_id(external_id)
            clean_memory_id = cls._validate_memory_id(memory_id)
            previous = validated.get(clean_external_id)
            if previous is not None and previous != clean_memory_id:
                raise ValueError(
                    f"external id collision for {clean_external_id}: {previous!r} and {clean_memory_id!r}"
                )
            validated[clean_external_id] = clean_memory_id
        return validated

    @staticmethod
    def _validate_external_id(external_id: int) -> int:
        if isinstance(external_id, bool) or not isinstance(external_id, Integral):
            raise ValueError("external ids must be uint64 integers")
        value = int(external_id)
        if value < 0 or value > UINT64_MAX:
            raise ValueError("external ids must be uint64 integers")
        return value

    @staticmethod
    def _validate_memory_id(memory_id: str) -> str:
        if not isinstance(memory_id, str):
            raise ValueError("memory ids must be non-empty strings")
        clean = memory_id.strip()
        if not clean:
            raise ValueError("memory ids must be non-empty strings")
        return clean

    @staticmethod
    def _clamp_score(score: Any) -> float:
        try:
            value = float(score)
        except (TypeError, ValueError):
            return 0.0
        if not math.isfinite(value):
            return 0.0
        return min(max(value, 0.0), 1.0)


__all__ = ["TurbovecSemanticCandidateProvider", "semantic_backend_available"]
