from __future__ import annotations

from pathlib import Path
import os

from .cache import LRUCache
from .context_pack import build_context_pack
from .db import MemoryStore
from .schema import MemoryRecord, SearchResult


class MemoryClient:
    def __init__(self, home: str | Path | None = None, *, cache_items: int = 512):
        home_path = Path(home or os.getenv("AGENT_MEMORY_HOME", "~/.agent-memory")).expanduser()
        self.home = home_path
        self.store = MemoryStore(home_path / "memories.db")
        self.cache: LRUCache[tuple, object] = LRUCache(max_items=cache_items)

    def add(self, content: str, **kwargs) -> MemoryRecord:
        record = MemoryRecord(content=content, **kwargs)
        saved = self.store.add(record)
        self.cache.clear()
        return saved

    def get(self, memory_id: str) -> MemoryRecord | None:
        return self.store.get(memory_id)

    def search(self, query: str, *, owner: str | None = None, scope: str | None = None, limit: int = 10) -> list[SearchResult]:
        key = ("search", query, owner, scope, limit)
        cached = self.cache.get(key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        results = self.store.search(query, owner=owner, scope=scope, limit=limit)
        self.cache.set(key, results)
        return results

    def context_pack(self, query: str, *, owner: str | None = None, scope: str | None = None, limit: int = 12, max_tokens: int = 1200) -> str:
        key = ("pack", query, owner, scope, limit, max_tokens)
        cached = self.cache.get(key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        results = self.search(query, owner=owner, scope=scope, limit=limit)
        pack = build_context_pack(results, max_tokens=max_tokens)
        self.cache.set(key, pack)
        return pack

    def stats(self) -> dict[str, object]:
        return self.store.stats() | {"cache_items": len(self.cache)}

    def close(self) -> None:
        self.store.close()
