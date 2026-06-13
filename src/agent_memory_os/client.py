from __future__ import annotations

from pathlib import Path
import os
from datetime import datetime, timezone
import json

from .cache import LRUCache
from .context_pack import ContextPackReport, build_context_pack, build_context_pack_report
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

    def search(
        self,
        query: str,
        *,
        owner: str | None = None,
        scope: str | None = None,
        requester_agent_id: str | None = None,
        requester_team_id: str | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        key = ("search", query, owner, scope, requester_agent_id, requester_team_id, limit)
        cached = self.cache.get(key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        results = self.store.search(
            query,
            owner=owner,
            scope=scope,
            requester_agent_id=requester_agent_id,
            requester_team_id=requester_team_id,
            limit=limit,
        )
        self.cache.set(key, results)
        return results

    def context_pack(
        self,
        query: str,
        *,
        owner: str | None = None,
        scope: str | None = None,
        requester_agent_id: str | None = None,
        requester_team_id: str | None = None,
        limit: int = 12,
        max_tokens: int = 1200,
    ) -> str:
        key = ("pack", query, owner, scope, requester_agent_id, requester_team_id, limit, max_tokens)
        cached = self.cache.get(key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        results = self.search(
            query,
            owner=owner,
            scope=scope,
            requester_agent_id=requester_agent_id,
            requester_team_id=requester_team_id,
            limit=limit,
        )
        pack = build_context_pack(results, max_tokens=max_tokens)
        self.cache.set(key, pack)
        return pack

    def context_pack_report(
        self,
        query: str,
        *,
        owner: str | None = None,
        scope: str | None = None,
        requester_agent_id: str | None = None,
        requester_team_id: str | None = None,
        limit: int = 12,
        max_tokens: int = 1200,
    ) -> ContextPackReport:
        key = ("pack_report", query, owner, scope, requester_agent_id, requester_team_id, limit, max_tokens)
        cached = self.cache.get(key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        results = self.search(
            query,
            owner=owner,
            scope=scope,
            requester_agent_id=requester_agent_id,
            requester_team_id=requester_team_id,
            limit=limit,
        )
        report = build_context_pack_report(results, max_tokens=max_tokens)
        self.cache.set(key, report)
        return report

    def stats(self) -> dict[str, object]:
        return self.store.stats() | {"cache_items": len(self.cache)}

    def rebuild_indexes(self) -> dict[str, int]:
        result = self.store.rebuild_indexes()
        self.cache.clear()
        return result

    def close(self) -> None:
        self.store.close()

    def offload_context(
        self,
        snapshot_data: dict[str, Any],
        session_id: str,
        trigger: str = "manual",
    ) -> str:
        """
        Saves the current agent state as a ContextSnapshot memory record.
        """
        from .schema import ContextSnapshot
        snapshot = ContextSnapshot(
            session_id=session_id,
            snapshot_data=snapshot_data,
            trigger=trigger,
        )
        record = snapshot.to_record()
        saved = self.add(record.content, **{k: v for k, v in record.__dict__.items() if k != "content"})
        return saved.id

    def reload_context(
        self,
        session_id: str,
        snapshot_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Retrieves the specified or most recent snapshot for the given session.
        """
        if snapshot_id:
            record = self.get(snapshot_id)
            if not record: 
                raise ValueError(f"Snapshot {snapshot_id} not found")
        else:
            # Search for the latest snapshot for this session
            results = self.search(
                query=f"session_id:{session_id}", 
                limit=1
            )
            if not results:
                raise ValueError(f"No snapshots found for session {session_id}")
            record = results[0].record

        return json.loads(record.content)

    def resonance_search(
        self,
        query: str,
        *,
        limit: int = 5,
        resonance_hops: int = 2,
    ) -> list[SearchResult]:
        """
        Enhanced retrieval using Memory Resonance logic.
        1. Perform standard semantic search to find seed chunks.
        2. Expand cluster using resonance weights.
        3. Merge and rank results based on final resonance scores.
        """
        # 1. Get seed chunks via semantic search
        seeds = self.search(query, limit=limit * 2)
        if not seeds:
            return []
        
        seed_ids = [res.record.id for res in seeds]
        
        # 2. Use ResonanceIndex to expand
        from .memory_resonance import ERATripletIndex, MemoryChunk
        idx = ERATripletIndex() 
        
        for res in seeds:
            ts = datetime.fromisoformat(res.record.updated_at.replace('Z', '+00:00')).timestamp()
            idx.add_chunk(MemoryChunk(id=res.record.id, text=res.record.content, timestamp=ts))
            
        resonant_ids = idx.resonance_cluster(seed_ids, hops=resonance_hops)
        
        final_results = []
        id_map = {res.id: res for res in seeds}
        for rid in resonant_ids:
            if rid in id_map:
                final_results.append(id_map[rid])
            if len(final_results) >= limit:
                break
        return final_results
