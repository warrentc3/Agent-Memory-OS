from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol


@dataclass(slots=True)
class Candidate:
    """Untrusted retrieval candidate produced by a disposable index/provider.

    Candidate providers may suggest stable MemoryRecord IDs and scoring metadata.
    They must not be treated as authoritative content sources; callers must rejoin
    every candidate through SQLite and apply ACL/expiry hard gates before use.
    """

    memory_id: str
    provider: str
    score: float
    rank: int | None = None
    reason: str = ""


class CandidateProvider(Protocol):
    """Protocol for untrusted retrieval candidate sidecars."""

    name: str

    def candidates(
        self,
        query: str,
        *,
        owner: str | None = None,
        scope: str | None = None,
        requester_agent_id: str | None = None,
        requester_team_id: str | None = None,
        limit: int = 10,
    ) -> Iterable[Candidate]:
        """Return untrusted candidate IDs and scores for later SQLite rejoin."""
        ...
