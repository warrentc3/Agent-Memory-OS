"""Local-first Web UI and HTTP API for AgentMemoryOS.

This is an inspection and smoke-test console for a locally running memory
store. It exposes the same requester-aware retrieval the SDK offers: searches
without a `requester_agent_id` run in unrestricted owner/admin view, so bind
the server to localhost only unless you front it with real authentication.
"""

from __future__ import annotations

import argparse
import html
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator

from .client import MemoryClient
from .schema import MemoryRecord, SearchResult, VALID_LINK_RELATIONS

VALID_SCOPES = {"user", "agent", "project", "team", "global"}
VALID_TYPES = {"preference", "fact", "procedure", "environment", "decision", "warning", "note"}


class AddMemoryRequest(BaseModel):
    content: str = Field(min_length=1)
    owner: str = "default"
    scope: str = "user"
    type: str = "note"
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    visibility: list[str] = Field(default_factory=list)
    source: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    expires_at: str | None = None
    decay_policy: str = "exponential"
    pinned: bool = False
    auto_link: bool = False

    @field_validator("scope")
    @classmethod
    def _valid_scope(cls, value: str) -> str:
        if value not in VALID_SCOPES:
            raise ValueError(f"scope must be one of {sorted(VALID_SCOPES)}")
        return value

    @field_validator("type")
    @classmethod
    def _valid_type(cls, value: str) -> str:
        if value not in VALID_TYPES:
            raise ValueError(f"type must be one of {sorted(VALID_TYPES)}")
        return value

    @field_validator("expires_at")
    @classmethod
    def _valid_expires_at(cls, value: str | None) -> str | None:
        # Expiry gates compare this lexicographically against ISO-8601 UTC
        # "now"; a non-ISO value would silently make the memory permanently
        # expired (or never-expiring) with no error anywhere.
        if value is None:
            return value
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("expires_at must be an ISO-8601 timestamp") from exc
        return value


class LinkRequest(BaseModel):
    src_id: str = Field(min_length=1)
    dst_id: str = Field(min_length=1)
    relation: str = "related_to"
    weight: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("relation")
    @classmethod
    def _valid_relation(cls, value: str) -> str:
        if value not in VALID_LINK_RELATIONS:
            raise ValueError(f"relation must be one of {sorted(VALID_LINK_RELATIONS)}")
        return value


class RecallFeedbackRequest(BaseModel):
    memory_ids: list[str] = Field(min_length=1)
    helpful: bool = True
    create_colinks: bool = False
    requester_agent_id: str | None = None
    requester_team_id: str | None = None


def _record_payload(record: MemoryRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "content": record.content,
        "owner": record.owner,
        "scope": record.scope,
        "type": record.type,
        "summary": record.summary,
        "tags": record.tags,
        "visibility": record.visibility,
        "source": record.source,
        "confidence": record.confidence,
        "importance": record.importance,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "expires_at": record.expires_at,
        "decay_policy": record.decay_policy,
        "pinned": record.pinned,
        "access_count": record.access_count,
    }


def _search_result_payload(result: SearchResult) -> dict[str, Any]:
    return _record_payload(result.record) | {
        "score": result.score,
        "reason": result.reason,
    }


def _render_index(stats: dict[str, Any]) -> str:
    total = html.escape(str(stats.get("total", 0)))
    links = html.escape(str(stats.get("links", 0)))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentMemoryOS Web UI</title>
  <style>
    :root {{ color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }}
    body {{ margin: 0; background: #0b1020; color: #eef2ff; }}
    main {{ max-width: 920px; margin: 0 auto; padding: 40px 20px; }}
    section {{ background: #121a33; border: 1px solid #25304f; border-radius: 18px; padding: 20px; margin: 18px 0; }}
    input, textarea, button {{ width: 100%; box-sizing: border-box; border-radius: 10px; border: 1px solid #334166; padding: 10px; margin: 8px 0; }}
    input, textarea {{ background: #0b1020; color: #eef2ff; }}
    button {{ background: #7c3aed; color: white; font-weight: 700; cursor: pointer; }}
    pre {{ white-space: pre-wrap; background: #070b16; padding: 14px; border-radius: 12px; overflow: auto; }}
    .stats {{ display: flex; gap: 14px; flex-wrap: wrap; }}
    .pill {{ background: #1d2848; border-radius: 999px; padding: 8px 12px; }}
    label {{ font-size: 0.85em; color: #93a4d0; }}
  </style>
</head>
<body>
  <main>
    <h1>AgentMemoryOS Web UI</h1>
    <p>Local-first memory inspection console. Searches without a requester run in unrestricted admin view.</p>
    <section class="stats">
      <div class="pill">Total memories: <strong>{total}</strong></div>
      <div class="pill">Links: <strong>{links}</strong></div>
      <div class="pill"><a href="/api/stats">/api/stats</a></div>
      <div class="pill"><a href="/health">/health</a></div>
    </section>
    <section>
      <h2>Add memory</h2>
      <textarea id="content" rows="4" placeholder="Memory content"></textarea>
      <label>owner</label><input id="owner" value="default">
      <label>scope (user/agent/project/team/global)</label><input id="scope" value="user">
      <label>type (preference/fact/procedure/environment/decision/warning/note)</label><input id="type" value="note">
      <label>visibility (comma separated, e.g. global or agent:neo; empty = owner-only)</label><input id="visibility" value="">
      <button onclick="addMemory()">Add</button>
    </section>
    <section>
      <h2>Search &amp; context pack</h2>
      <input id="query" placeholder="Search query">
      <label>requester agent id (empty = unrestricted admin view)</label><input id="requester" value="">
      <button onclick="searchMemory()">Search</button>
      <button onclick="contextPack()">Context pack</button>
      <pre id="output">Ready.</pre>
    </section>
  </main>
  <script>
    async function show(promise) {{
      const output = document.getElementById('output');
      try {{
        const response = await promise;
        const body = await response.json();
        output.textContent = (response.ok ? '' : 'HTTP ' + response.status + '\\n')
          + JSON.stringify(body, null, 2);
      }} catch (error) {{
        output.textContent = 'Request failed: ' + error;
      }}
    }}
    function visibilityList() {{
      return document.getElementById('visibility').value
        .split(',').map(v => v.trim()).filter(Boolean);
    }}
    function addMemory() {{
      show(fetch('/api/memories', {{
        method: 'POST',
        headers: {{'content-type': 'application/json'}},
        body: JSON.stringify({{
          content: document.getElementById('content').value,
          owner: document.getElementById('owner').value,
          scope: document.getElementById('scope').value,
          type: document.getElementById('type').value,
          visibility: visibilityList()
        }})
      }}));
    }}
    function searchMemory() {{
      const params = new URLSearchParams({{ q: document.getElementById('query').value }});
      const requester = document.getElementById('requester').value.trim();
      if (requester) params.set('requester_agent_id', requester);
      show(fetch('/api/search?' + params));
    }}
    function contextPack() {{
      const params = new URLSearchParams({{ q: document.getElementById('query').value }});
      const requester = document.getElementById('requester').value.trim();
      if (requester) params.set('requester_agent_id', requester);
      show(fetch('/api/context-pack?' + params));
    }}
  </script>
</body>
</html>"""


def create_app(home: str | Path | None = None) -> FastAPI:
    # One shared client per app: the schema/migration cost is paid once and
    # the LRU cache actually works. SQLite access is serialized by `lock`
    # because sync endpoints run in a threadpool.
    client = MemoryClient(home=home, check_same_thread=False)
    lock = threading.Lock()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        client.close()

    app = FastAPI(title="AgentMemoryOS Web UI", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/stats")
    def stats() -> dict[str, Any]:
        with lock:
            return client.stats()

    @app.post("/api/memories")
    def add_memory(request: AddMemoryRequest) -> dict[str, Any]:
        payload = request.model_dump()
        auto_link = payload.pop("auto_link")
        content = payload.pop("content")
        with lock:
            try:
                record = client.add(content, auto_link=auto_link, **payload)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _record_payload(record)

    @app.get("/api/memories/{memory_id}")
    def get_memory(memory_id: str) -> dict[str, Any]:
        with lock:
            record = client.get(memory_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"memory not found: {memory_id}")
        return _record_payload(record)

    @app.get("/api/memories/{memory_id}/links")
    def memory_links(memory_id: str) -> dict[str, Any]:
        with lock:
            if client.get(memory_id) is None:
                raise HTTPException(status_code=404, detail=f"memory not found: {memory_id}")
            links = client.links(memory_id)
        return {
            "memory_id": memory_id,
            "links": [
                {
                    "src_id": link.src_id,
                    "dst_id": link.dst_id,
                    "relation": link.relation,
                    "weight": link.weight,
                    "activation_count": link.activation_count,
                    "last_activated_at": link.last_activated_at,
                }
                for link in links
            ],
        }

    @app.post("/api/links")
    def add_link(request: LinkRequest) -> dict[str, Any]:
        with lock:
            try:
                link = client.link(
                    request.src_id, request.dst_id,
                    relation=request.relation, weight=request.weight,
                )
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=f"memory not found: {exc.args[0]}") from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "src_id": link.src_id,
            "dst_id": link.dst_id,
            "relation": link.relation,
            "weight": link.weight,
        }

    @app.post("/api/recall")
    def recall_feedback(request: RecallFeedbackRequest) -> dict[str, int]:
        with lock:
            return client.record_recall(
                request.memory_ids,
                helpful=request.helpful,
                create_colinks=request.create_colinks,
                requester_agent_id=request.requester_agent_id or None,
                requester_team_id=request.requester_team_id or None,
            )

    @app.post("/api/consolidate")
    def consolidate(owner: str | None = None, scope: str | None = None) -> dict[str, int]:
        with lock:
            return client.consolidate(owner=owner or None, scope=scope or None)

    @app.get("/api/search")
    def search(
        q: str = Query(min_length=1),
        owner: str | None = None,
        scope: str | None = None,
        requester_agent_id: str | None = None,
        requester_team_id: str | None = None,
        limit: int = Query(default=10, ge=1, le=100),
    ) -> dict[str, Any]:
        with lock:
            results = client.search(
                q,
                owner=owner or None,
                scope=scope or None,
                requester_agent_id=requester_agent_id or None,
                requester_team_id=requester_team_id or None,
                limit=limit,
            )
        return {"query": q, "results": [_search_result_payload(result) for result in results]}

    @app.get("/api/context-pack")
    def context_pack(
        q: str = Query(min_length=1),
        owner: str | None = None,
        scope: str | None = None,
        requester_agent_id: str | None = None,
        requester_team_id: str | None = None,
        max_tokens: int = Query(default=1200, ge=32, le=32000),
        auto_reinforce: bool = False,
    ) -> dict[str, Any]:
        with lock:
            report = client.context_pack_report(
                q,
                owner=owner or None,
                scope=scope or None,
                requester_agent_id=requester_agent_id or None,
                requester_team_id=requester_team_id or None,
                max_tokens=max_tokens,
                auto_reinforce=auto_reinforce,
            )
        return {
            "query": q,
            "text": report.text,
            "used_tokens": report.used_tokens,
            "max_tokens": report.max_tokens,
            "decisions": [
                {
                    "memory_id": decision.memory_id,
                    "selected": decision.selected,
                    "effective_score": decision.effective_score,
                    "reason": decision.reason,
                }
                for decision in report.decisions
            ],
        }

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        with lock:
            page = _render_index(client.stats())
        return HTMLResponse(page)

    return app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="agent-memory-web", description="Run the AgentMemoryOS Web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--home", default=None, help="Memory home directory; defaults to AGENT_MEMORY_HOME or ~/.agent-memory")
    args = parser.parse_args(argv)

    import uvicorn

    uvicorn.run(create_app(home=args.home), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
