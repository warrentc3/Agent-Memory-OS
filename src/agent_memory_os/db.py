from __future__ import annotations

from pathlib import Path
import json
import sqlite3

from .schema import MemoryRecord, SearchResult, utc_now


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
  expires_at TEXT
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
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def add(self, record: MemoryRecord) -> MemoryRecord:
        record.summary = record.normalized_summary()
        self.conn.execute(
            """
            INSERT INTO memories(id, owner, scope, type, content, summary, tags, visibility, source,
                                 confidence, importance, created_at, updated_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id, record.owner, record.scope, record.type, record.content, record.summary,
                record.tags_json(), record.visibility_json(), record.source_json(),
                record.confidence, record.importance, record.created_at, record.updated_at, record.expires_at,
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
        query = self._fts_query(query)
        where = ["memories_fts MATCH ?", "(m.expires_at IS NULL OR m.expires_at > ?)"]
        params: list[object] = [query, utc_now()]
        if owner:
            where.append("m.owner = ?")
            params.append(owner)
        if scope:
            where.append("m.scope = ?")
            params.append(scope)
        if requester_agent_id:
            acl_clauses = [
                "m.owner = ?",
                "EXISTS (SELECT 1 FROM json_each(m.visibility) WHERE value = 'global')",
                "EXISTS (SELECT 1 FROM json_each(m.visibility) WHERE value = ?)",
            ]
            params.extend([requester_agent_id, f"agent:{requester_agent_id}"])
            if requester_team_id:
                acl_clauses.extend(
                    [
                        "EXISTS (SELECT 1 FROM json_each(m.visibility) WHERE value = 'team' AND json_extract(m.source, '$.team_id') = ?)",
                        "EXISTS (SELECT 1 FROM json_each(m.visibility) WHERE value = ?)",
                    ]
                )
                params.extend([requester_team_id, f"team:{requester_team_id}"])
            where.append("(" + " OR ".join(acl_clauses) + ")")
        params.append(limit)
        sql = f"""
          SELECT m.*, bm25(memories_fts) AS rank
          FROM memories_fts
          JOIN memories m ON m.id = memories_fts.id
          WHERE {' AND '.join(where)}
          ORDER BY rank, m.importance DESC, m.confidence DESC, m.updated_at DESC
          LIMIT ?
        """
        rows = self.conn.execute(sql, params).fetchall()
        results = []
        for row in rows:
            # bm25 lower is better; convert to positive-ish score with metadata boost.
            rank = float(row["rank"])
            score = (1.0 / (1.0 + abs(rank))) + float(row["importance"]) * 0.2 + float(row["confidence"]) * 0.1
            results.append(SearchResult(record=self._row_to_record(row), score=score))
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
        )

    @staticmethod
    def _fts_query(query: str) -> str:
        terms = [t.replace('"', ' ').strip() for t in query.split() if t.strip()]
        return " OR ".join(f'"{t}"' for t in terms) if terms else '""'
