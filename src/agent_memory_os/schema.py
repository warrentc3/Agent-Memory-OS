from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import json
import uuid

from .scoring import VALID_DECAY_POLICIES


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_memory_id() -> str:
    return "mem_" + uuid.uuid4().hex


DEFAULT_DECAY_HALF_LIFE_DAYS = {
    "preference": 180.0,
    "fact": 90.0,
    "procedure": 365.0,
    "environment": 30.0,
    "decision": 180.0,
    "warning": 365.0,
    "note": 30.0,
}


@dataclass(slots=True)
class MemoryRecord:
    content: str
    owner: str = "default"
    scope: str = "user"
    type: str = "note"
    summary: str | None = None
    tags: list[str] = field(default_factory=list)
    visibility: list[str] = field(default_factory=list)
    source: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.8
    importance: float = 0.5
    id: str = field(default_factory=new_memory_id)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    expires_at: str | None = None
    decay_policy: str = "exponential"
    decay_half_life_days: float | None = None
    last_accessed_at: str | None = None
    access_count: int = 0
    pinned: bool = False

    def __post_init__(self) -> None:
        if self.decay_policy not in VALID_DECAY_POLICIES:
            raise ValueError(f"decay_policy must be one of {sorted(VALID_DECAY_POLICIES)}")
        if self.decay_half_life_days is None:
            self.decay_half_life_days = DEFAULT_DECAY_HALF_LIFE_DAYS.get(self.type, 30.0)
        if self.decay_policy != "none" and self.decay_half_life_days <= 0:
            raise ValueError("decay_half_life_days must be positive")
        if self.access_count < 0:
            raise ValueError("access_count must be non-negative")

    def normalized_summary(self) -> str:
        if self.summary:
            return self.summary
        text = " ".join(self.content.split())
        return text[:96] + ("…" if len(text) > 96 else "")

    def tags_json(self) -> str:
        return json.dumps(self.tags, ensure_ascii=False)

    def visibility_json(self) -> str:
        return json.dumps(self.visibility, ensure_ascii=False)

    def source_json(self) -> str:
        return json.dumps(self.source, ensure_ascii=False, sort_keys=True)


@dataclass(slots=True)
class SearchResult:
    record: MemoryRecord
    score: float
    reason: str = "fts"
