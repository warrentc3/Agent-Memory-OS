from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
from typing import Sequence
import json
import math
import sqlite3

from .candidates import Candidate, CandidateProvider
from .schema import MemoryRecord, SearchResult, utc_now
from .scoring import effective_score, freshness_factor, reinforcement_factor


MAX_SEMANTIC_CANDIDATES = 500


SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
  id TEXT PRIMARY KEY,
  owner TEXT NOT NULL,
  scope TEXT NOT NULL,
  type TEXT NOT NULL,
  content TEXT NOT NULL,
  summary TEXT NOT NULL,
  tags TEXT NOT NULL DEFAULT '[]',
  visibility TEXT NOT NULL DEFAULT '[]',
  source TEXT NOT NULL DEFAULT '{}',
  confidence REAL NOT NULL DEFAULT 0.8,
  importance REAL NOT NULL DEFAULT 0.5,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  expires_at TEXT,
  decay_policy TEXT NOT NULL DEFAULT 'exponential',
  decay_half_life_days REAL NOT NULL DEFAULT 30.0,
  last_accessed_at TEXT,
  access_count INTEGER NOT NULL DEFAULT 0,
  pinned INTEGER NOT NULL DEFAULT 0
);
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
  id UNINDEXED,
  owner UNINDEXED,
  scope,
  type,
  content,
  summary,
  tags,
  tokenize = 'unicode61'
);
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
  INSERT INTO memories_fts(id, owner, scope, type, content, summary, tags)
  VALUES (new.id, new.owner, new.scope, new.type, new.content, new.summary, new.tags);
END;
CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, id, owner, scope, type, content, summary, tags)
  VALUES('delete', old.id, old.owner, old.scope, old.type, old.content, old.summary, old.tags);
END;
CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, id, owner, scope, type, content, summary, tags)
  VALUES('delete', old.id, old.owner, old.scope, old.type, old.content, old.summary, old.tags);
  INSERT INTO memories_fts(id, owner, scope, type, content, summary, tags)
  VALUES (new.id, new.owner, new.scope, new.type, new.content, new.summary, new.tags);
END;
"""


class MemoryStore:
    def __init__(self, path: str | Path, *, candidate_providers: Sequence[CandidateProvider] | None = None):
        self.path = Path(path)
        self.candidate_providers = list(candidate_providers or [])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._ensure_decay_columns()
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def _ensure_decay_columns(self) -> None:
        existing = {row["name"] for row in self.conn.execute("PRAGMA table_info(memories)")}
        columns = {
            "decay_policy": "TEXT NOT NULL DEFAULT 'exponential'",
            "decay_half_life_days": "REAL NOT NULL DEFAULT 30.0",
            "last_accessed_at": "TEXT",
            "access_count": "INTEGER NOT NULL DEFAULT 0",
            "pinned": "INTEGER NOT NULL DEFAULT 0",
        }
        for name, definition in columns.items():
            if name not in existing:
                self.conn.execute(f"ALTER TABLE memories ADD COLUMN {name} {definition}")

    def add(self, record: MemoryRecord) -> MemoryRecord:
        record.summary = record.normalized_summary()
        self.conn.execute(
            """
            INSERT INTO memories(id, owner, scope, type, content, summary, tags, visibility, source,
                                 confidence, importance, created_at, updated_at, expires_at,
                                 decay_policy, decay_half_life_days, last_accessed_at, access_count, pinned)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id, record.owner, record.scope, record.type, record.content, record.summary,
                record.tags_json(), record.visibility_json(), record.source_json(),
                record.confidence, record.importance, record.created_at, record.updated_at, record.expires_at,
                record.decay_policy, record.decay_half_life_days, record.last_accessed_at,
                record.access_count, int(record.pinned),
            ),
        )
        self.conn.commit()
        return record

    def get(self, memory_id: str) -> MemoryRecord | None:
        row = self.conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        return self._row_to_record(row) if row else None

    def update_content(self, memory_id: str, content: str, *, summary: str | None = None) -> MemoryRecord:
        now = utc_now()
        existing = self.get(memory_id)
        if not existing:
            raise KeyError(memory_id)
        existing.content = content
        existing.summary = summary or MemoryRecord(content=content).normalized_summary()
        existing.updated_at = now
        self.conn.execute(
            "UPDATE memories SET content=?, summary=?, updated_at=? WHERE id=?",
            (existing.content, existing.summary, existing.updated_at, memory_id),
        )
        self.conn.commit()
        return existing

    def delete(self, memory_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def rebuild_indexes(self) -> dict[str, int]:
        """Rebuild disposable retrieval indexes from authoritative memories."""
        self.conn.executescript(
            """
            DROP TRIGGER IF EXISTS memories_ai;
            DROP TRIGGER IF EXISTS memories_ad;
            DROP TRIGGER IF EXISTS memories_au;
            DROP TABLE IF EXISTS memories_fts;
            """
        )
        self.conn.executescript(SCHEMA)
        self.conn.execute(
            """
            INSERT INTO memories_fts(id, owner, scope, type, content, summary, tags)
            SELECT id, owner, scope, type, content, summary, tags FROM memories
            """
        )
        self.conn.commit()
        indexed = self.conn.execute("SELECT COUNT(*) FROM memories_fts").fetchone()[0]
        total = self.conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        return {"memories_indexed": int(indexed), "memories_total": int(total)}

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
        """Search memories via dual-track retrieval.

        Track A is query-bound FTS5 relevance. Track B is query-independent
        authority recall for bedrock memories. Both tracks still pass the same
        expiry and requester ACL hard gates before scoring/fusion.
        """
        now = utc_now()
        now_dt = datetime.now(timezone.utc)
        rows = self._fts_rows(
            query,
            owner=owner,
            scope=scope,
            requester_agent_id=requester_agent_id,
            requester_team_id=requester_team_id,
            limit=limit,
            now=now,
        )
        results: dict[str, SearchResult] = {}
        for row in rows:
            rank = float(row["rank"])
            text_score = 1.0 / (1.0 + abs(rank))
            result = self._score_row(row, text_score=text_score, now_dt=now_dt, reason_prefix="fts")
            results[result.record.id] = result

        authority_rows = self._authority_rows(
            owner=owner,
            scope=scope,
            requester_agent_id=requester_agent_id,
            requester_team_id=requester_team_id,
            limit=limit,
            now=now,
        )
        for row in authority_rows:
            source = json.loads(row["source"] or "{}")
            authority_weight = min(max(float(source.get("weight", 10.0)), 0.0), 10.0) / 10.0
            text_component = results.get(row["id"]).score if row["id"] in results else 0.0
            fused_score = (text_component * 0.3) + (authority_weight * 0.7)
            result = self._score_row(
                row,
                text_score=fused_score,
                now_dt=now_dt,
                reason_prefix="authority_track",
            )
            previous = results.get(result.record.id)
            if previous is None or result.score > previous.score:
                results[result.record.id] = result

        semantic_rows = self._semantic_candidate_rows(
            query,
            owner=owner,
            scope=scope,
            requester_agent_id=requester_agent_id,
            requester_team_id=requester_team_id,
            limit=limit,
            now=now,
        )
        for row, candidate in semantic_rows:
            result = self._score_row(
                row,
                text_score=max(0.0, float(candidate.score)),
                now_dt=now_dt,
                reason_prefix=self._semantic_reason_prefix(candidate),
            )
            previous = results.get(result.record.id)
            if previous is None or result.score > previous.score:
                results[result.record.id] = result

        final_results = sorted(results.values(), key=lambda result: result.score, reverse=True)
        if not final_results:
            final_results = self._fallback_candidates(
                owner=owner,
                scope=scope,
                requester_agent_id=requester_agent_id,
                requester_team_id=requester_team_id,
                limit=limit,
            )
        return final_results[:limit]

    def _fts_rows(
        self,
        query: str,
        *,
        owner: str | None,
        scope: str | None,
        requester_agent_id: str | None,
        requester_team_id: str | None,
        limit: int,
        now: str,
    ) -> list[sqlite3.Row]:
        fts_query = self._fts_query(query)
        where = ["memories_fts MATCH ?", "(m.expires_at IS NULL OR m.expires_at > ?)"]
        params: list[object] = [fts_query, now]
        if owner:
            where.append("m.owner = ?")
            params.append(owner)
        if scope:
            where.append("m.scope = ?")
            params.append(scope)
        self._append_acl_filter(
            where,
            params,
            requester_agent_id=requester_agent_id,
            requester_team_id=requester_team_id,
            alias="m.",
        )
        params.append(max(limit * 5, limit))
        return self.conn.execute(
            f"""
            SELECT m.*, bm25(memories_fts) AS rank
            FROM memories_fts
            JOIN memories m ON m.id = memories_fts.id
            WHERE {' AND '.join(where)}
            ORDER BY rank, m.importance DESC, m.confidence DESC, m.updated_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    def _authority_rows(
        self,
        *,
        owner: str | None,
        scope: str | None,
        requester_agent_id: str | None,
        requester_team_id: str | None,
        limit: int,
        now: str,
    ) -> list[sqlite3.Row]:
        where = [
            "(expires_at IS NULL OR expires_at > ?)",
            "(json_extract(source, '$.permanence') = 1 AND json_extract(source, '$.weight') >= 10)",
        ]
        params: list[object] = [now]
        if owner:
            where.append("owner = ?")
            params.append(owner)
        if scope:
            where.append("scope = ?")
            params.append(scope)
        self._append_acl_filter(
            where,
            params,
            requester_agent_id=requester_agent_id,
            requester_team_id=requester_team_id,
            alias="",
        )
        params.append(max(limit, 1))
        return self.conn.execute(
            f"""
            SELECT * FROM memories
            WHERE {' AND '.join(where)}
            ORDER BY pinned DESC, json_extract(source, '$.weight') DESC,
                     importance DESC, confidence DESC, updated_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    def _semantic_candidate_rows(
        self,
        query: str,
        *,
        owner: str | None,
        scope: str | None,
        requester_agent_id: str | None,
        requester_team_id: str | None,
        limit: int,
        now: str,
    ) -> list[tuple[sqlite3.Row, Candidate]]:
        """Rejoin untrusted semantic candidates through SQLite and hard gates."""
        if not self.candidate_providers:
            return []

        candidates_by_id: dict[str, Candidate] = {}
        candidate_cap = max(1, min(MAX_SEMANTIC_CANDIDATES, max(limit * 10, limit)))
        for provider in self.candidate_providers:
            provider_name = self._safe_provider_name(provider)
            provider_candidates: dict[str, Candidate] = {}
            raw_seen = 0
            try:
                candidates = provider.candidates(
                    query,
                    owner=owner,
                    scope=scope,
                    requester_agent_id=requester_agent_id,
                    requester_team_id=requester_team_id,
                    limit=limit,
                )
                for raw_candidate in candidates:
                    raw_seen += 1
                    if raw_seen > candidate_cap:
                        break
                    candidate = self._coerce_semantic_candidate(raw_candidate, provider_name=provider_name)
                    if candidate is None:
                        continue
                    previous = provider_candidates.get(candidate.memory_id)
                    if previous is None or candidate.score > previous.score:
                        provider_candidates[candidate.memory_id] = candidate
                    if len(provider_candidates) >= candidate_cap:
                        break
            except Exception:
                # Candidate providers are optional sidecars. Backend failure must
                # discard provider-local partial output and degrade to
                # authoritative SQLite/FTS/fallback retrieval.
                continue
            for memory_id, candidate in provider_candidates.items():
                previous = candidates_by_id.get(memory_id)
                if previous is None or candidate.score > previous.score:
                    candidates_by_id[memory_id] = candidate
                if len(candidates_by_id) >= candidate_cap:
                    break
            if len(candidates_by_id) >= candidate_cap:
                break

        if not candidates_by_id:
            return []

        ids = list(candidates_by_id)
        placeholders = ",".join("?" for _ in ids)
        where = [f"id IN ({placeholders})", "(expires_at IS NULL OR expires_at > ?)"]
        params: list[object] = [*ids, now]
        if owner:
            where.append("owner = ?")
            params.append(owner)
        if scope:
            where.append("scope = ?")
            params.append(scope)
        self._append_acl_filter(
            where,
            params,
            requester_agent_id=requester_agent_id,
            requester_team_id=requester_team_id,
            alias="",
        )
        rows = self.conn.execute(
            f"""
            SELECT * FROM memories
            WHERE {' AND '.join(where)}
            """,
            params,
        ).fetchall()
        return [(row, candidates_by_id[row["id"]]) for row in rows]

    @classmethod
    def _coerce_semantic_candidate(cls, raw_candidate: object, *, provider_name: str) -> Candidate | None:
        memory_id = getattr(raw_candidate, "memory_id", None)
        if not isinstance(memory_id, str):
            return None
        memory_id = memory_id.strip()
        if not memory_id:
            return None

        raw_score = getattr(raw_candidate, "score", None)
        if raw_score is None:
            return None
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(score):
            return None
        score = min(max(score, 0.0), 1.0)

        raw_rank = getattr(raw_candidate, "rank", None)
        rank = raw_rank if isinstance(raw_rank, int) else None
        reason = cls._safe_semantic_label(getattr(raw_candidate, "reason", ""))
        return Candidate(
            memory_id=memory_id,
            provider=provider_name,
            score=score,
            rank=rank,
            reason=reason,
        )

    @staticmethod
    def _safe_provider_name(provider: CandidateProvider) -> str:
        try:
            raw_name = getattr(provider, "name")
        except Exception:
            raw_name = provider.__class__.__name__
        return MemoryStore._safe_semantic_label(raw_name)

    @staticmethod
    def _safe_semantic_label(value: object, *, max_length: int = 80) -> str:
        try:
            text = "" if value is None else str(value)
        except Exception:
            text = "unknown"
        cleaned = "".join(char if char.isalnum() or char in {"_", "-", ":", "."} else "_" for char in text)
        return cleaned[:max_length] or "unknown"

    @staticmethod
    def _semantic_reason_prefix(candidate: Candidate) -> str:
        reason = f"semantic:{candidate.provider}"
        if candidate.reason:
            reason = f"{reason}:{candidate.reason}"
        return reason

    def _append_acl_filter(
        self,
        where: list[str],
        params: list[object],
        *,
        requester_agent_id: str | None,
        requester_team_id: str | None,
        alias: str,
    ) -> None:
        if not requester_agent_id:
            return
        acl_clauses = [
            f"{alias}owner = ?",
            f"EXISTS (SELECT 1 FROM json_each({alias}visibility) WHERE value = 'global')",
            f"EXISTS (SELECT 1 FROM json_each({alias}visibility) WHERE value = ?)",
        ]
        params.extend([requester_agent_id, f"agent:{requester_agent_id}"])
        if requester_team_id:
            acl_clauses.extend(
                [
                    f"EXISTS (SELECT 1 FROM json_each({alias}visibility) WHERE value = 'team' AND json_extract({alias}source, '$.team_id') = ?)",
                    f"EXISTS (SELECT 1 FROM json_each({alias}visibility) WHERE value = ?)",
                ]
            )
            params.extend([requester_team_id, f"team:{requester_team_id}"])
        where.append("(" + " OR ".join(acl_clauses) + ")")

    def _score_row(
        self,
        row: sqlite3.Row,
        *,
        text_score: float,
        now_dt: datetime,
        reason_prefix: str,
    ) -> SearchResult:
        age_days = self._age_days(row["updated_at"], now_dt)
        freshness = freshness_factor(
            row["decay_policy"],
            age_days=age_days,
            half_life_days=float(row["decay_half_life_days"]),
            pinned=bool(row["pinned"]),
        )
        reinforcement = reinforcement_factor(int(row["access_count"] or 0))
        score = effective_score(
            text_score=text_score,
            importance=float(row["importance"]),
            confidence=float(row["confidence"]),
            freshness=freshness,
            reinforcement=reinforcement,
        )
        reason = f"{reason_prefix}+metadata+freshness:{freshness:.3f}+reinforcement:{reinforcement:.3f}"
        return SearchResult(record=self._row_to_record(row), score=score, reason=reason)

    def _fallback_candidates(
        self,
        *,
        owner: str | None,
        scope: str | None,
        requester_agent_id: str | None,
        requester_team_id: str | None,
        limit: int,
    ) -> list[SearchResult]:
        where = ["(expires_at IS NULL OR expires_at > ?)"]
        params: list[object] = [utc_now()]
        if owner:
            where.append("owner = ?")
            params.append(owner)
        if scope:
            where.append("scope = ?")
            params.append(scope)
        if requester_agent_id:
            acl_clauses = [
                "owner = ?",
                "EXISTS (SELECT 1 FROM json_each(visibility) WHERE value = 'global')",
                "EXISTS (SELECT 1 FROM json_each(visibility) WHERE value = ?)",
            ]
            params.extend([requester_agent_id, f"agent:{requester_agent_id}"])
            if requester_team_id:
                acl_clauses.extend(
                    [
                        "EXISTS (SELECT 1 FROM json_each(visibility) WHERE value = 'team' AND json_extract(source, '$.team_id') = ?)",
                        "EXISTS (SELECT 1 FROM json_each(visibility) WHERE value = ?)",
                    ]
                )
                params.extend([requester_team_id, f"team:{requester_team_id}"])
            where.append("(" + " OR ".join(acl_clauses) + ")")
        params.append(max(limit, 1))
        rows = self.conn.execute(
            f"""
            SELECT * FROM memories
            WHERE {' AND '.join(where)}
            ORDER BY pinned DESC, importance DESC, confidence DESC, updated_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        results: list[SearchResult] = []
        now_dt = datetime.now(timezone.utc)
        for row in rows:
            age_days = self._age_days(row["updated_at"], now_dt)
            freshness = freshness_factor(
                row["decay_policy"],
                age_days=age_days,
                half_life_days=float(row["decay_half_life_days"]),
                pinned=bool(row["pinned"]),
            )
            reinforcement = reinforcement_factor(int(row["access_count"] or 0))
            score = effective_score(
                text_score=0.05,
                importance=float(row["importance"]),
                confidence=float(row["confidence"]),
                freshness=freshness,
                reinforcement=reinforcement,
            )
            reason = f"fallback:pinned_recent+freshness:{freshness:.3f}+reinforcement:{reinforcement:.3f}"
            results.append(SearchResult(record=self._row_to_record(row), score=score, reason=reason))
        results.sort(key=lambda result: result.score, reverse=True)
        return results

    def stats(self) -> dict[str, int]:
        total = self.conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        by_scope = dict(self.conn.execute("SELECT scope, COUNT(*) FROM memories GROUP BY scope").fetchall())
        by_type = dict(self.conn.execute("SELECT type, COUNT(*) FROM memories GROUP BY type").fetchall())
        return {"total": total, "by_scope": by_scope, "by_type": by_type}

    def _row_to_record(self, row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            id=row["id"], owner=row["owner"], scope=row["scope"], type=row["type"],
            content=row["content"], summary=row["summary"], tags=json.loads(row["tags"] or "[]"),
            visibility=json.loads(row["visibility"] or "[]"), source=json.loads(row["source"] or "{}"),
            confidence=float(row["confidence"]), importance=float(row["importance"]),
            created_at=row["created_at"], updated_at=row["updated_at"], expires_at=row["expires_at"],
            decay_policy=row["decay_policy"], decay_half_life_days=float(row["decay_half_life_days"]),
            last_accessed_at=row["last_accessed_at"], access_count=int(row["access_count"] or 0),
            pinned=bool(row["pinned"]),
        )

    @staticmethod
    def _age_days(value: str, now_dt: datetime) -> float:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return 0.0
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0.0, (now_dt - parsed).total_seconds() / 86_400)

    @staticmethod
    def _fts_query(query: str) -> str:
        terms = [t.replace('"', ' ').strip() for t in query.split() if t.strip()]
        return " OR ".join(f'"{t}"' for t in terms) if terms else '""'
