from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import json
import uuid


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_memory_id() -> str:
    return "mem_" + uuid.uuid4().hex


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
