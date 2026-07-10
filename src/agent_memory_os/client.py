from __future__ import annotations

from pathlib import Path
from typing import Sequence
import os
from datetime import datetime, timezone
import json

from .candidates import CandidateProvider
from .cache import LRUCache
from .context_pack import ContextPackReport, build_context_pack, build_context_pack_report
from .db import MemoryStore
from .schema import MemoryLink, MemoryRecord, RecallProfile, SearchResult

class MemoryClient:
    def __init__(
        self,
        home: str | Path | None = None,
        *,
        cache_items: int = 512,
        candidate_providers: Sequence[CandidateProvider] | None = None,
        resonance_hops: int = 1,
        profile: RecallProfile | None = None,
        check_same_thread: bool = True,
    ):
        home_path = Path(home or os.getenv("AGENT_MEMORY_HOME", "~/.agent-memory")).expanduser()
        self.home = home_path
        self.store = MemoryStore(
            home_path / "memories.db",
            candidate_providers=candidate_providers,
            resonance_hops=resonance_hops,
            check_same_thread=check_same_thread,
        )
        self.profile = profile
        self.cache: LRUCache[tuple, object] = LRUCache(max_items=cache_items)
        self._profile_cache: dict[str, RecallProfile | None] = {}

    def add(self, content: str, *, auto_link: bool = False, **kwargs) -> MemoryRecord:
        record = MemoryRecord(content=content, **kwargs)
        saved = self.store.add(record)
        if auto_link:
            self.store.auto_link_similar(saved)
        self.cache.clear()
        return saved

    def get(self, memory_id: str) -> MemoryRecord | None:
        return self.store.get(memory_id)

    def delete(self, memory_id: str) -> bool:
        removed = self.store.delete(memory_id)
        if removed:
            self.cache.clear()
        return removed

    def list_recent(
        self,
        *,
        owner: str | None = None,
        scope: str | None = None,
        requester_agent_id: str | None = None,
        requester_team_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[MemoryRecord]:
        return self.store.list_recent(
            owner=owner,
            scope=scope,
            requester_agent_id=requester_agent_id,
            requester_team_id=requester_team_id,
            limit=limit,
            offset=offset,
        )

    def link(
        self,
        src_id: str,
        dst_id: str,
        *,
        relation: str = "related_to",
        weight: float = 0.5,
        source: dict | None = None,
    ) -> MemoryLink:
        saved = self.store.add_link(
            MemoryLink(src_id=src_id, dst_id=dst_id, relation=relation, weight=weight, source=source or {})
        )
        self.cache.clear()
        return saved

    def unlink(self, src_id: str, dst_id: str, *, relation: str | None = None) -> bool:
        removed = self.store.remove_link(src_id, dst_id, relation=relation)
        if removed:
            self.cache.clear()
        return removed

    def links(self, memory_id: str) -> list[MemoryLink]:
        return self.store.links_for(memory_id)

    def record_recall(
        self,
        memory_ids: Sequence[str],
        *,
        create_colinks: bool = False,
        helpful: bool = True,
        requester_agent_id: str | None = None,
        requester_team_id: str | None = None,
    ) -> dict[str, int]:
        """Report that these memories were recalled together.

        This is the repeated-recall feedback loop: with `helpful=True` it
        reinforces each memory and strengthens the association edges between
        them so future queries resonate along well-worn paths; with
        `helpful=False` the recall misled the agent, so links weaken and
        confidence drops — the self-correction path. Pass the requester when
        the feedback comes from an untrusted surface: only memories visible to
        that requester are affected.
        """
        result = self.store.record_recall(
            memory_ids,
            create_colinks=create_colinks,
            helpful=helpful,
            requester_agent_id=requester_agent_id,
            requester_team_id=requester_team_id,
        )
        self.cache.clear()
        return result

    def import_links(
        self,
        pairs: Sequence[tuple[str, str, float]],
        *,
        relation: str = "related_to",
        source: dict | None = None,
    ) -> int:
        """Bulk-import derived association edges (e.g. from the ERA index).

        Pairs whose endpoints no longer exist are skipped. Pairs already
        connected (in either direction) are left untouched so a periodic sync
        can never clobber reinforcement-learned weights.
        """
        imported = 0
        for src_id, dst_id, weight in pairs:
            if self.store.link_exists(src_id, dst_id):
                continue
            try:
                self.store.add_link(
                    MemoryLink(
                        src_id=src_id, dst_id=dst_id, relation=relation,
                        weight=weight, source=source or {"auto": "derived"},
                    )
                )
                imported += 1
            except (KeyError, ValueError):
                continue
        if imported:
            self.cache.clear()
        return imported

    def save_profile(self, profile: RecallProfile) -> RecallProfile:
        """Persist a named agent recall profile in the memory database."""
        saved = self.store.save_profile(profile)
        self._profile_cache.pop(profile.agent_id, None)
        self.cache.clear()
        return saved

    def load_profile(self, agent_id: str) -> RecallProfile | None:
        # Only cache hits: caching a miss forever would blind a long-running
        # server to profiles saved later by another process.
        cached = self._profile_cache.get(agent_id)
        if cached is not None:
            return cached
        profile = self.store.load_profile(agent_id)
        if profile is not None:
            self._profile_cache[agent_id] = profile
        return profile

    def consolidate(self, *, owner: str | None = None, scope: str | None = None) -> dict[str, int]:
        """Run the write-side hygiene pass: merge duplicates, synthesize concepts."""
        result = self.store.consolidate(owner=owner, scope=scope)
        self.cache.clear()
        return result

    def _resolve_profile(
        self, profile: RecallProfile | None, requester_agent_id: str | None
    ) -> RecallProfile | None:
        if profile is not None:
            return profile
        if self.profile is not None:
            return self.profile
        if requester_agent_id:
            return self.load_profile(requester_agent_id)
        return None

    def search(
        self,
        query: str,
        *,
        owner: str | None = None,
        scope: str | None = None,
        requester_agent_id: str | None = None,
        requester_team_id: str | None = None,
        limit: int = 10,
        profile: RecallProfile | None = None,
    ) -> list[SearchResult]:
        active_profile = self._resolve_profile(profile, requester_agent_id)
        profile_key = active_profile.signature() if active_profile else None
        key = ("search", query, owner, scope, requester_agent_id, requester_team_id, limit, profile_key)
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
            profile=active_profile,
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
        profile: RecallProfile | None = None,
        auto_reinforce: bool = False,
    ) -> str:
        if auto_reinforce:
            return self.context_pack_report(
                query,
                owner=owner,
                scope=scope,
                requester_agent_id=requester_agent_id,
                requester_team_id=requester_team_id,
                limit=limit,
                max_tokens=max_tokens,
                profile=profile,
                auto_reinforce=True,
            ).text
        active_profile = self._resolve_profile(profile, requester_agent_id)
        profile_key = active_profile.signature() if active_profile else None
        key = ("pack", query, owner, scope, requester_agent_id, requester_team_id, limit, max_tokens, profile_key)
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
            profile=active_profile,
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
        profile: RecallProfile | None = None,
        auto_reinforce: bool = False,
    ) -> ContextPackReport:
        active_profile = self._resolve_profile(profile, requester_agent_id)
        profile_key = active_profile.signature() if active_profile else None
        key = (
            "pack_report", query, owner, scope, requester_agent_id, requester_team_id,
            limit, max_tokens, profile_key,
        )
        if not auto_reinforce:
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
            profile=active_profile,
        )
        report = build_context_pack_report(results, max_tokens=max_tokens)
        if auto_reinforce:
            # Selection is the recall event: close the reinforcement loop here
            # so callers (especially MCP clients) don't have to remember to.
            selected = [decision.memory_id for decision in report.decisions if decision.selected]
            if selected:
                self.store.record_recall(selected)
                self.cache.clear()
            return report
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
        # Ensure the session_id is in the content for FTS searchability
        # ContextSnapshot.to_record currently only puts session_id in source.
        # We add it to the content to ensure reload_context search works.
        record.content = f"session_id:{session_id}\n{record.content}"
        
        from dataclasses import asdict
        record_dict = asdict(record)
        content = record_dict.pop("content")
        saved = self.add(content, **record_dict)
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
            # Latest is a recency question, not a relevance question: FTS
            # ranking picks an arbitrary snapshot when timestamps tie.
            record = self.store.latest_snapshot_record(session_id)
            if not record:
                raise ValueError(f"No snapshots found for session {session_id}")

        # The content carries a session_id prefix for FTS searchability
        raw_content = record.content
        if raw_content.startswith(f"session_id:{session_id}\n"):
            raw_content = raw_content[len(f"session_id:{session_id}\n"):]

        return json.loads(raw_content)

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
