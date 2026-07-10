from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import DefaultDict, Sequence
import hashlib
import json
import math
import re
import sqlite3

from .candidates import Candidate, CandidateProvider
from .schema import MemoryLink, MemoryRecord, RecallProfile, SearchResult, utc_now
from .scoring import effective_score, freshness_factor, reinforcement_factor


MAX_SEMANTIC_CANDIDATES = 500
MAX_RESONANCE_CANDIDATES = 200
RESONANCE_HOP_DECAY = 0.6
RESONANCE_MAX_EDGES_PER_NODE = 8
LINK_DECAY_HALF_LIFE_DAYS = 90.0
CO_RECALL_WEIGHT_STEP = 0.05
CO_RECALL_WEAKEN_STEP = 0.1
CO_RECALL_INITIAL_WEIGHT = 0.2
NEGATIVE_FEEDBACK_CONFIDENCE_STEP = 0.05
SUPERSEDED_SCORE_PENALTY = 0.4


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
  DELETE FROM memories_fts WHERE id = old.id;
END;
CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
  DELETE FROM memories_fts WHERE id = old.id;
  INSERT INTO memories_fts(id, owner, scope, type, content, summary, tags)
  VALUES (new.id, new.owner, new.scope, new.type, new.content, new.summary, new.tags);
END;
CREATE TABLE IF NOT EXISTS memory_links (
  src_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
  dst_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
  relation TEXT NOT NULL DEFAULT 'related_to',
  weight REAL NOT NULL DEFAULT 0.5,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_activated_at TEXT,
  activation_count INTEGER NOT NULL DEFAULT 0,
  source TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (src_id, dst_id, relation)
);
CREATE INDEX IF NOT EXISTS memory_links_src ON memory_links(src_id);
CREATE INDEX IF NOT EXISTS memory_links_dst ON memory_links(dst_id);
CREATE TABLE IF NOT EXISTS recall_profiles (
  agent_id TEXT PRIMARY KEY,
  type_weights TEXT NOT NULL DEFAULT '{}',
  scope_weights TEXT NOT NULL DEFAULT '{}',
  updated_at TEXT NOT NULL
);
"""

AUTO_LINK_WEIGHT = 0.3
AUTO_LINK_LIMIT = 5
CONSOLIDATION_MIN_CLUSTER_WEIGHT = 0.6
CONSOLIDATION_MIN_ACTIVATIONS = 3
CONSOLIDATION_MIN_CLUSTER_SIZE = 3


class MemoryStore:
    def __init__(
        self,
        path: str | Path,
        *,
        candidate_providers: Sequence[CandidateProvider] | None = None,
        resonance_hops: int = 1,
        check_same_thread: bool = True,
    ):
        if resonance_hops < 0:
            raise ValueError("resonance_hops must be >= 0")
        self.path = Path(path)
        self.candidate_providers = list(candidate_providers or [])
        self.resonance_hops = resonance_hops
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False lets a server share one connection across a
        # threadpool; callers doing so must serialize access themselves.
        self.conn = sqlite3.connect(self.path, check_same_thread=check_same_thread)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        # Multi-agent deployments share one database file; WAL lets concurrent
        # readers coexist with a writer and busy_timeout absorbs write races.
        # Both PRAGMAs degrade gracefully where unsupported (e.g. some network
        # filesystems keep journal_mode unchanged).
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self._ensure_decay_columns()
        self._ensure_valid_fts_triggers()
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

    def _ensure_valid_fts_triggers(self) -> None:
        """Replace legacy FTS triggers that used the FTS5 'delete' command.

        The 'delete' command is only valid for external-content/contentless
        FTS5 tables; on this regular FTS5 table it raises 'SQL logic error' on
        every UPDATE/DELETE. Databases created before the fix keep the broken
        triggers because SCHEMA uses CREATE TRIGGER IF NOT EXISTS.
        """
        rows = self.conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'trigger' AND name IN ('memories_ad', 'memories_au')"
        ).fetchall()
        broken = [row["name"] for row in rows if "'delete'" in (row["sql"] or "")]
        if not broken:
            return
        for name in broken:
            self.conn.execute(f"DROP TRIGGER IF EXISTS {name}")
        self.conn.executescript(SCHEMA)

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

    UPDATABLE_FIELDS = {
        "content", "summary", "tags", "visibility", "source", "confidence",
        "importance", "type", "scope", "pinned", "expires_at",
        "decay_policy", "decay_half_life_days",
    }

    def update_memory(self, memory_id: str, **fields) -> MemoryRecord:
        """Update selected fields of a memory; validation runs through MemoryRecord.

        The updated_at bump is intentional here (unlike recall feedback):
        editing content IS new information, so the freshness clock restarts.
        """
        unknown = set(fields) - self.UPDATABLE_FIELDS
        if unknown:
            raise ValueError(f"cannot update fields: {sorted(unknown)}")
        existing = self.get(memory_id)
        if existing is None:
            raise KeyError(memory_id)
        for name, value in fields.items():
            setattr(existing, name, value)
        if "content" in fields and "summary" not in fields:
            existing.summary = None
        existing.summary = existing.normalized_summary()
        existing.updated_at = utc_now()
        # Re-run dataclass validation on the mutated record
        MemoryRecord(**{
            "content": existing.content, "owner": existing.owner, "scope": existing.scope,
            "type": existing.type, "confidence": existing.confidence,
            "importance": existing.importance, "decay_policy": existing.decay_policy,
            "decay_half_life_days": existing.decay_half_life_days,
            "access_count": existing.access_count,
        })
        self.conn.execute(
            """
            UPDATE memories SET content=?, summary=?, tags=?, visibility=?, source=?,
                                confidence=?, importance=?, type=?, scope=?, pinned=?,
                                expires_at=?, decay_policy=?, decay_half_life_days=?, updated_at=?
            WHERE id=?
            """,
            (
                existing.content, existing.summary, existing.tags_json(),
                existing.visibility_json(), existing.source_json(),
                existing.confidence, existing.importance, existing.type, existing.scope,
                int(existing.pinned), existing.expires_at, existing.decay_policy,
                existing.decay_half_life_days, existing.updated_at, memory_id,
            ),
        )
        self.conn.commit()
        return existing

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
        self.conn.execute(
            "DELETE FROM memory_links WHERE src_id = ? OR dst_id = ?", (memory_id, memory_id)
        )
        cur = self.conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def add_link(self, link: MemoryLink) -> MemoryLink:
        """Upsert an authoritative association edge between two existing memories."""
        for endpoint in (link.src_id, link.dst_id):
            if self.get(endpoint) is None:
                raise KeyError(endpoint)
        self.conn.execute(
            """
            INSERT INTO memory_links(src_id, dst_id, relation, weight, created_at, updated_at,
                                     last_activated_at, activation_count, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(src_id, dst_id, relation) DO UPDATE SET
              weight = excluded.weight,
              updated_at = excluded.updated_at,
              source = excluded.source
            """,
            (
                link.src_id, link.dst_id, link.relation, link.weight,
                link.created_at, link.updated_at, link.last_activated_at,
                link.activation_count, link.source_json(),
            ),
        )
        self.conn.commit()
        return link

    def remove_link(self, src_id: str, dst_id: str, relation: str | None = None) -> bool:
        where = "((src_id = ? AND dst_id = ?) OR (src_id = ? AND dst_id = ?))"
        params: list[object] = [src_id, dst_id, dst_id, src_id]
        if relation:
            where += " AND relation = ?"
            params.append(relation)
        cur = self.conn.execute(f"DELETE FROM memory_links WHERE {where}", params)
        self.conn.commit()
        return cur.rowcount > 0

    def auto_link_similar(
        self,
        record: MemoryRecord,
        *,
        limit: int = AUTO_LINK_LIMIT,
        weight: float = AUTO_LINK_WEIGHT,
    ) -> list[MemoryLink]:
        """Create weak `related_to` edges from a new memory to its FTS neighbors.

        This is the write-time association pass: a new memory immediately joins
        the graph near lexically similar memories. Edges are weak and derived —
        co-recall reinforcement decides which of them mature. Reading through
        these edges is still ACL/expiry hard-gated, so linking across owners or
        visibility levels leaks nothing.
        """
        query = " ".join(record.content.split()[:16])
        if not query.strip():
            return []
        rows = self._fts_rows(
            query,
            owner=None,
            scope=None,
            requester_agent_id=None,
            requester_team_id=None,
            limit=limit + 1,
            now=utc_now(),
        )
        created: list[MemoryLink] = []
        for row in rows:
            if row["id"] == record.id or len(created) >= limit:
                continue
            existing = self.conn.execute(
                "SELECT 1 FROM memory_links WHERE (src_id = ? AND dst_id = ?) OR (src_id = ? AND dst_id = ?)",
                (record.id, row["id"], row["id"], record.id),
            ).fetchone()
            if existing:
                continue
            created.append(
                self.add_link(
                    MemoryLink(
                        src_id=record.id,
                        dst_id=row["id"],
                        relation="related_to",
                        weight=weight,
                        source={"auto": "fts_similarity"},
                    )
                )
            )
        return created

    def save_profile(self, profile: RecallProfile) -> RecallProfile:
        if not profile.agent_id:
            raise ValueError("profile.agent_id must be non-empty to persist")
        self.conn.execute(
            """
            INSERT INTO recall_profiles(agent_id, type_weights, scope_weights, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(agent_id) DO UPDATE SET
              type_weights = excluded.type_weights,
              scope_weights = excluded.scope_weights,
              updated_at = excluded.updated_at
            """,
            (
                profile.agent_id,
                json.dumps(profile.type_weights, ensure_ascii=False, sort_keys=True),
                json.dumps(profile.scope_weights, ensure_ascii=False, sort_keys=True),
                utc_now(),
            ),
        )
        self.conn.commit()
        return profile

    def load_profile(self, agent_id: str) -> RecallProfile | None:
        row = self.conn.execute(
            "SELECT * FROM recall_profiles WHERE agent_id = ?", (agent_id,)
        ).fetchone()
        if row is None:
            return None
        return RecallProfile(
            agent_id=row["agent_id"],
            type_weights=json.loads(row["type_weights"] or "{}"),
            scope_weights=json.loads(row["scope_weights"] or "{}"),
        )

    def list_recent(
        self,
        *,
        owner: str | None = None,
        scope: str | None = None,
        memory_type: str | None = None,
        requester_agent_id: str | None = None,
        requester_team_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[MemoryRecord]:
        """List memories by recency for browsing (inventory view, no scoring)."""
        where = ["1=1"]
        params: list[object] = []
        if owner:
            where.append("owner = ?")
            params.append(owner)
        if scope:
            where.append("scope = ?")
            params.append(scope)
        if memory_type:
            where.append("type = ?")
            params.append(memory_type)
        self._append_acl_filter(
            where,
            params,
            requester_agent_id=requester_agent_id,
            requester_team_id=requester_team_id,
            alias="",
        )
        params.extend([max(1, limit), max(0, offset)])
        rows = self.conn.execute(
            f"""
            SELECT * FROM memories WHERE {' AND '.join(where)}
            ORDER BY updated_at DESC, rowid DESC
            LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def graph_snapshot(
        self,
        *,
        requester_agent_id: str | None = None,
        requester_team_id: str | None = None,
        limit: int = 300,
    ) -> dict[str, list[dict]]:
        """Return the association graph for visualization, ACL-gated.

        Only nodes visible to the requester are returned, and an edge survives
        only when BOTH endpoints are visible — the same invariant as resonance
        traversal, so the picture never leaks a private neighbor.
        """
        edges = self.conn.execute(
            "SELECT src_id, dst_id, relation, weight FROM memory_links ORDER BY weight DESC LIMIT ?",
            (max(1, limit),),
        ).fetchall()
        ids = list({edge["src_id"] for edge in edges} | {edge["dst_id"] for edge in edges})
        rows = self._visible_rows_for_ids(
            ids,
            owner=None,
            scope=None,
            requester_agent_id=requester_agent_id,
            requester_team_id=requester_team_id,
            now=utc_now(),
        )
        visible = {row["id"]: row for row in rows}
        kept_edges = [
            edge for edge in edges
            if edge["src_id"] in visible and edge["dst_id"] in visible
        ]
        degree: DefaultDict[str, int] = defaultdict(int)
        for edge in kept_edges:
            degree[edge["src_id"]] += 1
            degree[edge["dst_id"]] += 1
        return {
            "nodes": [
                {
                    "id": row["id"],
                    "label": row["summary"],
                    "scope": row["scope"],
                    "type": row["type"],
                    "pinned": bool(row["pinned"]),
                    "degree": degree[row["id"]],
                }
                for row in visible.values()
            ],
            "edges": [
                {
                    "src": edge["src_id"],
                    "dst": edge["dst_id"],
                    "relation": edge["relation"],
                    "weight": float(edge["weight"]),
                }
                for edge in kept_edges
            ],
        }

    def latest_snapshot_record(self, session_id: str) -> MemoryRecord | None:
        """Return the most recent context snapshot for a session.

        Recency is determined by snapshot metadata and insertion order, never
        by FTS relevance — same-second snapshots must still resolve to the
        latest one deterministically.
        """
        row = self.conn.execute(
            """
            SELECT * FROM memories
            WHERE type = 'snapshot' AND json_extract(source, '$.session_id') = ?
            ORDER BY json_extract(source, '$.snapshot_index') DESC, created_at DESC, rowid DESC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        return self._row_to_record(row) if row else None

    def link_exists(self, memory_id: str, other_id: str) -> bool:
        """Return whether any edge connects the two memories in either direction."""
        row = self.conn.execute(
            "SELECT 1 FROM memory_links WHERE (src_id = ? AND dst_id = ?) OR (src_id = ? AND dst_id = ?) LIMIT 1",
            (memory_id, other_id, other_id, memory_id),
        ).fetchone()
        return row is not None

    def links_for(self, memory_id: str) -> list[MemoryLink]:
        rows = self.conn.execute(
            "SELECT * FROM memory_links WHERE src_id = ? OR dst_id = ? ORDER BY weight DESC, src_id, dst_id",
            (memory_id, memory_id),
        ).fetchall()
        return [self._row_to_link(row) for row in rows]

    def record_recall(
        self,
        memory_ids: Sequence[str],
        *,
        create_colinks: bool = False,
        helpful: bool = True,
        requester_agent_id: str | None = None,
        requester_team_id: str | None = None,
    ) -> dict[str, int]:
        """Reinforce or weaken memories recalled together.

        Co-recall is the Hebbian signal of associative memory: memories that are
        useful together should surface together next time. With `helpful=True`
        each call bumps per-memory reinforcement metadata and strengthens
        existing links between every co-recalled pair; `create_colinks=True`
        additionally creates weak `co_recalled` edges for pairs with no existing
        link. With `helpful=False` the recall misled the agent: link weights are
        reduced and memory confidence drops slightly — the self-correction path.
        Negative feedback deliberately leaves `updated_at` alone: touching it
        would reset the freshness-decay clock and boost the memory instead.

        `supersedes` edges carry truth-arbitration direction, not association
        strength, so recall feedback never adjusts them.

        When a requester is given, only memories that requester can see are
        affected — feedback from untrusted surfaces (HTTP/MCP) cannot touch
        another agent's private memories.
        """
        ids = self._recall_eligible_ids(
            memory_ids,
            requester_agent_id=requester_agent_id,
            requester_team_id=requester_team_id,
        )
        now = utc_now()
        reinforced_links = 0
        created_links = 0
        weakened_links = 0
        for memory_id in ids:
            if helpful:
                self.conn.execute(
                    "UPDATE memories SET access_count = access_count + 1, last_accessed_at = ? WHERE id = ?",
                    (now, memory_id),
                )
            else:
                self.conn.execute(
                    "UPDATE memories SET confidence = max(0.0, confidence - ?) WHERE id = ?",
                    (NEGATIVE_FEEDBACK_CONFIDENCE_STEP, memory_id),
                )
        pair_clause = (
            "((src_id = ? AND dst_id = ?) OR (src_id = ? AND dst_id = ?)) AND relation != 'supersedes'"
        )
        for i, src_id in enumerate(ids):
            for dst_id in ids[i + 1:]:
                pair_params = (src_id, dst_id, dst_id, src_id)
                if helpful:
                    cur = self.conn.execute(
                        f"""
                        UPDATE memory_links
                        SET weight = min(1.0, weight + ?),
                            activation_count = activation_count + 1,
                            last_activated_at = ?,
                            updated_at = ?
                        WHERE {pair_clause}
                        """,
                        (CO_RECALL_WEIGHT_STEP, now, now, *pair_params),
                    )
                    if cur.rowcount > 0:
                        reinforced_links += cur.rowcount
                    elif create_colinks:
                        self.add_link(
                            MemoryLink(
                                src_id=src_id,
                                dst_id=dst_id,
                                relation="co_recalled",
                                weight=CO_RECALL_INITIAL_WEIGHT,
                                last_activated_at=now,
                                activation_count=1,
                            )
                        )
                        created_links += 1
                else:
                    cur = self.conn.execute(
                        f"""
                        UPDATE memory_links
                        SET weight = max(0.0, weight - ?), updated_at = ?
                        WHERE {pair_clause}
                        """,
                        (CO_RECALL_WEAKEN_STEP, now, *pair_params),
                    )
                    weakened_links += cur.rowcount
        self.conn.commit()
        return {
            "reinforced_memories": len(ids) if helpful else 0,
            "weakened_memories": 0 if helpful else len(ids),
            "reinforced_links": reinforced_links,
            "created_links": created_links,
            "weakened_links": weakened_links,
        }

    def _recall_eligible_ids(
        self,
        memory_ids: Sequence[str],
        *,
        requester_agent_id: str | None,
        requester_team_id: str | None,
    ) -> list[str]:
        ordered = [memory_id for memory_id in dict.fromkeys(memory_ids) if memory_id]
        if not ordered:
            return []
        placeholders = ",".join("?" for _ in ordered)
        where = [f"id IN ({placeholders})"]
        params: list[object] = [*ordered]
        self._append_acl_filter(
            where,
            params,
            requester_agent_id=requester_agent_id,
            requester_team_id=requester_team_id,
            alias="",
        )
        visible = {
            row["id"]
            for row in self.conn.execute(
                f"SELECT id FROM memories WHERE {' AND '.join(where)}", params
            ).fetchall()
        }
        return [memory_id for memory_id in ordered if memory_id in visible]

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
        profile: RecallProfile | None = None,
    ) -> list[SearchResult]:
        """Search memories via dual-track retrieval plus resonance expansion.

        Track A is query-bound FTS5 relevance. Track B is query-independent
        authority recall for bedrock memories. Track C expands direct hits
        through authoritative `memory_links` edges (associative recall). All
        tracks pass the same expiry and requester ACL hard gates before
        scoring/fusion; an optional RecallProfile then applies per-agent soft
        re-weighting to ranking only.
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
            # bm25() returns more-negative values for stronger matches; map to
            # (0.5, 1.0) so relevance rises with match strength instead of
            # inverting it.
            rank = min(float(row["rank"]), 0.0)
            text_score = (1.0 - rank) / (2.0 - rank)
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

        if self.resonance_hops > 0 and results:
            resonance_results = self._resonance_results(
                seed_scores={memory_id: result.score for memory_id, result in results.items()},
                owner=owner,
                scope=scope,
                requester_agent_id=requester_agent_id,
                requester_team_id=requester_team_id,
                now=now,
                now_dt=now_dt,
            )
            for result in resonance_results:
                previous = results.get(result.record.id)
                if previous is None or result.score > previous.score:
                    results[result.record.id] = result

        self._apply_supersedes_demotion(results)

        final_results = sorted(results.values(), key=lambda result: result.score, reverse=True)
        if not final_results:
            final_results = self._fallback_candidates(
                owner=owner,
                scope=scope,
                requester_agent_id=requester_agent_id,
                requester_team_id=requester_team_id,
                limit=limit,
            )
        if profile is not None:
            for result in final_results:
                weight = profile.weight_for(result.record)
                result.score *= weight
                result.reason = f"{result.reason}+profile:{weight:.2f}"
            final_results.sort(key=lambda result: result.score, reverse=True)
        return final_results[:limit]

    def consolidate(self, *, owner: str | None = None, scope: str | None = None) -> dict[str, int]:
        """Write-side hygiene pass: merge exact duplicates, synthesize concepts.

        Both steps only operate within groups sharing identical owner, scope,
        and visibility, so consolidation can never move content across ACL
        boundaries or blend private and public memories into one record.
        """
        duplicates_merged = self._merge_exact_duplicates(owner=owner, scope=scope)
        concepts_created = self._synthesize_corecall_clusters(owner=owner, scope=scope)
        return {"duplicates_merged": duplicates_merged, "concepts_created": concepts_created}

    def _merge_exact_duplicates(self, *, owner: str | None, scope: str | None) -> int:
        where = ["1=1"]
        params: list[object] = []
        if owner:
            where.append("owner = ?")
            params.append(owner)
        if scope:
            where.append("scope = ?")
            params.append(scope)
        rows = self.conn.execute(
            f"SELECT * FROM memories WHERE {' AND '.join(where)}", params
        ).fetchall()
        groups: DefaultDict[tuple, list[sqlite3.Row]] = defaultdict(list)
        for row in rows:
            key = (row["owner"], row["scope"], row["visibility"], _content_fingerprint(row["content"]))
            groups[key].append(row)

        merged = 0
        for group in groups.values():
            if len(group) < 2:
                continue
            # Pinned and authority-track records must never lose to a casual
            # duplicate, regardless of confidence.
            group.sort(key=_merge_priority, reverse=True)
            canonical = group[0]
            for duplicate in group[1:]:
                for link in self.links_for(duplicate["id"]):
                    other_end = link.dst_id if link.src_id == duplicate["id"] else link.src_id
                    if other_end == canonical["id"]:
                        continue
                    if self.link_exists(canonical["id"], other_end):
                        continue
                    src, dst = (
                        (canonical["id"], other_end)
                        if link.src_id == duplicate["id"]
                        else (other_end, canonical["id"])
                    )
                    self.add_link(
                        MemoryLink(
                            src_id=src, dst_id=dst, relation=link.relation,
                            weight=link.weight, last_activated_at=link.last_activated_at,
                            activation_count=link.activation_count, source=link.source,
                        )
                    )
                self.conn.execute(
                    "UPDATE memories SET access_count = access_count + ? WHERE id = ?",
                    (int(duplicate["access_count"] or 0), canonical["id"]),
                )
                self.delete(duplicate["id"])
                merged += 1
        self.conn.commit()
        return merged

    def _synthesize_corecall_clusters(self, *, owner: str | None, scope: str | None) -> int:
        """Turn strongly co-recalled clusters into concept nodes.

        Concept nodes are the cheap recall handle: everyday retrieval hits the
        synthesized summary, and `derived_from` edges lead back to the original
        episodes when detail is needed.
        """
        edges = self.conn.execute(
            """
            SELECT l.src_id, l.dst_id FROM memory_links l
            JOIN memories s ON s.id = l.src_id
            JOIN memories d ON d.id = l.dst_id
            WHERE l.relation = 'co_recalled' AND l.weight >= ? AND l.activation_count >= ?
              AND s.owner = d.owner AND s.scope = d.scope AND s.visibility = d.visibility
            """,
            (CONSOLIDATION_MIN_CLUSTER_WEIGHT, CONSOLIDATION_MIN_ACTIVATIONS),
        ).fetchall()

        parent: dict[str, str] = {}

        def find(node: str) -> str:
            parent.setdefault(node, node)
            while parent[node] != node:
                parent[node] = parent[parent[node]]
                node = parent[node]
            return node

        for edge in edges:
            root_a, root_b = find(edge["src_id"]), find(edge["dst_id"])
            if root_a != root_b:
                parent[root_b] = root_a

        clusters: DefaultDict[str, list[str]] = defaultdict(list)
        for node in parent:
            clusters[find(node)].append(node)

        created = 0
        for members in clusters.values():
            if len(members) < CONSOLIDATION_MIN_CLUSTER_SIZE:
                continue
            placeholders = ",".join("?" for _ in members)
            rows = self.conn.execute(
                f"SELECT * FROM memories WHERE id IN ({placeholders}) ORDER BY updated_at",
                members,
            ).fetchall()
            if len(rows) < CONSOLIDATION_MIN_CLUSTER_SIZE:
                continue
            first = rows[0]
            if owner and first["owner"] != owner:
                continue
            if scope and first["scope"] != scope:
                continue
            already = self.conn.execute(
                f"SELECT 1 FROM memory_links WHERE relation = 'derived_from' AND dst_id IN ({placeholders}) LIMIT 1",
                members,
            ).fetchone()
            if already:
                continue
            summaries = "; ".join(row["summary"] for row in rows)
            concept = MemoryRecord(
                content=f"Consolidated insight from {len(rows)} related memories: {summaries}",
                owner=first["owner"],
                scope=first["scope"],
                type="note",
                visibility=json.loads(first["visibility"] or "[]"),
                importance=max(float(row["importance"]) for row in rows),
                confidence=sum(float(row["confidence"]) for row in rows) / len(rows),
                source={"auto": "consolidation", "consolidated_from": [row["id"] for row in rows]},
            )
            self.add(concept)
            for row in rows:
                self.add_link(
                    MemoryLink(
                        src_id=concept.id, dst_id=row["id"], relation="derived_from",
                        weight=0.9, source={"auto": "consolidation"},
                    )
                )
            created += 1
        self.conn.commit()
        return created

    def _apply_supersedes_demotion(self, results: dict[str, SearchResult]) -> None:
        """Demote memories whose superseding record is also in the result set.

        `supersedes` is the one directional relation: when both ends survive the
        hard gates, the superseded end is stale by definition and must not
        outrank its replacement. Demotion only fires when the requester can see
        the superseding memory, so edge direction never leaks hidden records.
        """
        if len(results) < 2:
            return
        ids = list(results)
        placeholders = ",".join("?" for _ in ids)
        edges = self.conn.execute(
            f"""
            SELECT src_id, dst_id FROM memory_links
            WHERE relation = 'supersedes'
              AND src_id IN ({placeholders}) AND dst_id IN ({placeholders})
            """,
            [*ids, *ids],
        ).fetchall()
        for edge in edges:
            superseded = results.get(edge["dst_id"])
            if superseded is None or edge["src_id"] not in results:
                continue
            superseded.score *= SUPERSEDED_SCORE_PENALTY
            superseded.reason = f"{superseded.reason}+superseded_by:{edge['src_id']}"

    def _resonance_results(
        self,
        *,
        seed_scores: dict[str, float],
        owner: str | None,
        scope: str | None,
        requester_agent_id: str | None,
        requester_team_id: str | None,
        now: str,
        now_dt: datetime,
    ) -> list[SearchResult]:
        """Expand seed hits through memory_links with ACL-safe traversal.

        Requester-invisible or expired nodes are dropped before they enter the
        frontier, so they are both unreturnable and untraversable: a private
        memory can never bridge two public memories for an unauthorized
        requester, and edge existence never leaks through scores.

        Edges themselves decay: an association that has not been co-activated
        recently contributes less activation than a well-worn one, and each
        frontier node only expands its strongest RESONANCE_MAX_EDGES_PER_NODE
        edges so hub memories cannot flood the cluster.
        """
        visited: set[str] = set(seed_scores)
        frontier: dict[str, float] = dict(seed_scores)
        collected: list[tuple[sqlite3.Row, float, int, str]] = []

        for hop in range(1, self.resonance_hops + 1):
            if not frontier or len(collected) >= MAX_RESONANCE_CANDIDATES:
                break
            frontier_ids = list(frontier)
            placeholders = ",".join("?" for _ in frontier_ids)
            edges = self.conn.execute(
                f"""
                SELECT src_id AS from_id, dst_id AS neighbor_id, weight, relation,
                       last_activated_at, updated_at
                FROM memory_links WHERE src_id IN ({placeholders})
                UNION ALL
                SELECT dst_id AS from_id, src_id AS neighbor_id, weight, relation,
                       last_activated_at, updated_at
                FROM memory_links WHERE dst_id IN ({placeholders})
                """,
                [*frontier_ids, *frontier_ids],
            ).fetchall()

            edges_by_node: DefaultDict[str, list[tuple[float, sqlite3.Row]]] = defaultdict(list)
            for edge in edges:
                if edge["neighbor_id"] in visited:
                    continue
                edge_weight = min(max(float(edge["weight"]), 0.0), 1.0)
                link_age_days = self._age_days(
                    edge["last_activated_at"] or edge["updated_at"], now_dt
                )
                link_freshness = 0.5 ** (link_age_days / LINK_DECAY_HALF_LIFE_DAYS)
                edges_by_node[edge["from_id"]].append((edge_weight * link_freshness, edge))

            activations: dict[str, tuple[float, str, str]] = {}
            for from_id, node_edges in edges_by_node.items():
                node_edges.sort(key=lambda item: item[0], reverse=True)
                for effective_weight, edge in node_edges[:RESONANCE_MAX_EDGES_PER_NODE]:
                    neighbor_id = edge["neighbor_id"]
                    activation = frontier[from_id] * effective_weight * RESONANCE_HOP_DECAY
                    if activation > activations.get(neighbor_id, (0.0, "", ""))[0]:
                        activations[neighbor_id] = (activation, from_id, edge["relation"])
            if not activations:
                break

            ids = list(activations)
            rows = self._visible_rows_for_ids(
                ids,
                owner=owner,
                scope=scope,
                requester_agent_id=requester_agent_id,
                requester_team_id=requester_team_id,
                now=now,
            )

            visited.update(ids)
            frontier = {}
            for row in rows:
                activation, from_id, relation = activations[row["id"]]
                frontier[row["id"]] = activation
                collected.append((row, activation, hop, f"via:{from_id}:{relation}"))
                if len(collected) >= MAX_RESONANCE_CANDIDATES:
                    break

        return [
            self._score_row(
                row,
                text_score=activation,
                now_dt=now_dt,
                reason_prefix=f"resonance:hop{hop}:{path}",
            )
            for row, activation, hop, path in collected
        ]

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
        # Over-fetch from providers: the ACL/expiry hard gates run AFTER the
        # provider returns, so asking for exactly `limit` can leave the whole
        # semantic track empty for requesters who can't see the global top hits.
        provider_fetch_limit = max(limit, min(candidate_cap, limit * 5))
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
                    limit=provider_fetch_limit,
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

        rows = self._visible_rows_for_ids(
            list(candidates_by_id),
            owner=owner,
            scope=scope,
            requester_agent_id=requester_agent_id,
            requester_team_id=requester_team_id,
            now=now,
        )
        return [(row, candidates_by_id[row["id"]]) for row in rows]

    def _visible_rows_for_ids(
        self,
        ids: list[str],
        *,
        owner: str | None,
        scope: str | None,
        requester_agent_id: str | None,
        requester_team_id: str | None,
        now: str,
    ) -> list[sqlite3.Row]:
        """Rejoin untrusted candidate ids through the ACL/expiry hard gates.

        This is the single security gate for every id-producing retrieval
        track (semantic sidecars, resonance expansion): keep it in one place so
        a future ACL change cannot diverge between tracks.
        """
        if not ids:
            return []
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
        return self.conn.execute(
            f"SELECT * FROM memories WHERE {' AND '.join(where)}",
            params,
        ).fetchall()

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
        links = self.conn.execute("SELECT COUNT(*) FROM memory_links").fetchone()[0]
        return {"total": total, "by_scope": by_scope, "by_type": by_type, "links": links}

    def dashboard_stats(self, *, activity_days: int = 14) -> dict[str, object]:
        """Aggregate figures for the console dashboard."""
        now = utc_now()
        base = self.stats()
        pinned = self.conn.execute("SELECT COUNT(*) FROM memories WHERE pinned = 1").fetchone()[0]
        expired = self.conn.execute(
            "SELECT COUNT(*) FROM memories WHERE expires_at IS NOT NULL AND expires_at <= ?", (now,)
        ).fetchone()[0]
        by_owner = dict(
            self.conn.execute(
                "SELECT owner, COUNT(*) FROM memories GROUP BY owner ORDER BY COUNT(*) DESC LIMIT 6"
            ).fetchall()
        )
        by_relation = dict(
            self.conn.execute("SELECT relation, COUNT(*) FROM memory_links GROUP BY relation").fetchall()
        )
        top_recalled = [
            {"id": row["id"], "summary": row["summary"], "access_count": int(row["access_count"])}
            for row in self.conn.execute(
                "SELECT id, summary, access_count FROM memories WHERE access_count > 0 "
                "ORDER BY access_count DESC, updated_at DESC LIMIT 5"
            ).fetchall()
        ]
        today = datetime.now(timezone.utc).date()
        days = [(today - timedelta(days=offset)).isoformat() for offset in range(activity_days - 1, -1, -1)]
        counted = dict(
            self.conn.execute(
                "SELECT substr(created_at, 1, 10) AS day, COUNT(*) FROM memories "
                "WHERE substr(created_at, 1, 10) >= ? GROUP BY day",
                (days[0],),
            ).fetchall()
        )
        return base | {
            "pinned": int(pinned),
            "expired": int(expired),
            "by_owner": by_owner,
            "by_relation": by_relation,
            "top_recalled": top_recalled,
            "activity": [{"day": day, "count": int(counted.get(day, 0))} for day in days],
        }

    def _row_to_link(self, row: sqlite3.Row) -> MemoryLink:
        return MemoryLink(
            src_id=row["src_id"], dst_id=row["dst_id"], relation=row["relation"],
            weight=float(row["weight"]), created_at=row["created_at"], updated_at=row["updated_at"],
            last_activated_at=row["last_activated_at"],
            activation_count=int(row["activation_count"] or 0),
            source=json.loads(row["source"] or "{}"),
        )

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


def _content_fingerprint(text: str) -> str:
    """Hash the FULL normalized content for exact-duplicate detection.

    Unlike context_pack's claim fingerprint (which truncates for cheap
    comparison), consolidation deletes records, so two memories that share a
    long prefix but diverge later must never collide.
    """
    normalized = re.sub(r"\W+", " ", text.casefold()).strip()
    normalized = " ".join(normalized.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _merge_priority(row: sqlite3.Row) -> tuple:
    source = json.loads(row["source"] or "{}")
    try:
        weight = float(source.get("weight", 0) or 0)
    except (TypeError, ValueError):
        weight = 0.0
    authority = 1 if (source.get("permanence") in (True, 1) and weight >= 10) else 0
    return (int(row["pinned"] or 0), authority, float(row["confidence"]), row["updated_at"], row["id"])
