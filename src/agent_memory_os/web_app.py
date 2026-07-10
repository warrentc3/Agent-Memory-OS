"""Local-first Web UI and HTTP API for AgentMemoryOS.

This is an inspection and smoke-test console for a locally running memory
store. It exposes the same requester-aware retrieval the SDK offers: searches
without a `requester_agent_id` run in unrestricted owner/admin view, so bind
the server to localhost only unless you front it with real authentication.
"""

from __future__ import annotations

import argparse
import hmac
import os
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator

from .client import MemoryClient
from .schema import MemoryRecord, SearchResult, VALID_LINK_RELATIONS
from .tokens import load_token
from .web_ui import PAGE

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


class UpdateMemoryRequest(BaseModel):
    content: str | None = Field(default=None, min_length=1)
    summary: str | None = None
    scope: str | None = None
    type: str | None = None
    tags: list[str] | None = None
    visibility: list[str] | None = None
    source: dict[str, Any] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    importance: float | None = Field(default=None, ge=0.0, le=1.0)
    expires_at: str | None = None
    pinned: bool | None = None
    decay_policy: str | None = None

    @field_validator("scope")
    @classmethod
    def _valid_scope(cls, value: str | None) -> str | None:
        if value is not None and value not in VALID_SCOPES:
            raise ValueError(f"scope must be one of {sorted(VALID_SCOPES)}")
        return value

    @field_validator("type")
    @classmethod
    def _valid_type(cls, value: str | None) -> str | None:
        if value is not None and value not in VALID_TYPES:
            raise ValueError(f"type must be one of {sorted(VALID_TYPES)}")
        return value

    @field_validator("expires_at")
    @classmethod
    def _valid_expires_at(cls, value: str | None) -> str | None:
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


def create_app(home: str | Path | None = None, *, token: str | None = None) -> FastAPI:
    # One shared client per app: the schema/migration cost is paid once and
    # the LRU cache actually works. SQLite access is serialized by `lock`
    # because sync endpoints run in a threadpool.
    client = MemoryClient(home=home, check_same_thread=False)
    lock = threading.Lock()
    # Resolution order: explicit --token > env > <home>/web_token created by
    # `agent-memory token create`.
    api_token = token or os.getenv("AGENT_MEMORY_WEB_TOKEN") or load_token(home)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        client.close()

    app = FastAPI(title="AgentMemoryOS Web UI", lifespan=lifespan)

    if api_token:
        # Opt-in bearer-token gate for every API route. The page shell and
        # /health stay open so the UI can load and ask for the token.
        @app.middleware("http")
        async def require_token(request, call_next):
            if request.url.path.startswith("/api/"):
                supplied = request.headers.get("authorization", "")
                expected = f"Bearer {api_token}"
                if not hmac.compare_digest(supplied.encode(), expected.encode()):
                    return JSONResponse({"detail": "unauthorized"}, status_code=401)
            return await call_next(request)

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

    @app.get("/api/memories")
    def list_memories(
        owner: str | None = None,
        scope: str | None = None,
        type: str | None = None,  # noqa: A002 - query param name mirrors the schema field
        requester_agent_id: str | None = None,
        requester_team_id: str | None = None,
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        with lock:
            records = client.list_recent(
                owner=owner or None,
                scope=scope or None,
                memory_type=type or None,
                requester_agent_id=requester_agent_id or None,
                requester_team_id=requester_team_id or None,
                limit=limit,
                offset=offset,
            )
        return {"memories": [_record_payload(record) for record in records]}

    @app.get("/api/graph")
    def graph(
        requester_agent_id: str | None = None,
        requester_team_id: str | None = None,
        limit: int = Query(default=300, ge=1, le=1000),
    ) -> dict[str, Any]:
        with lock:
            return client.graph_snapshot(
                requester_agent_id=requester_agent_id or None,
                requester_team_id=requester_team_id or None,
                limit=limit,
            )

    @app.get("/api/memories/{memory_id}")
    def get_memory(memory_id: str) -> dict[str, Any]:
        with lock:
            record = client.get(memory_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"memory not found: {memory_id}")
        return _record_payload(record)

    @app.patch("/api/memories/{memory_id}")
    def update_memory(memory_id: str, request: UpdateMemoryRequest) -> dict[str, Any]:
        fields = {name: value for name, value in request.model_dump().items() if value is not None}
        if not fields:
            raise HTTPException(status_code=400, detail="no fields to update")
        with lock:
            try:
                record = client.update(memory_id, **fields)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=f"memory not found: {exc.args[0]}") from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _record_payload(record)

    @app.get("/api/dashboard")
    def dashboard() -> dict[str, Any]:
        with lock:
            return client.dashboard_stats()

    @app.delete("/api/owners/{owner}/memories")
    def purge_owner(owner: str, confirm: str = Query(default="")) -> dict[str, Any]:
        # Destructive and unscoped by id: the caller must retype the exact
        # owner as confirmation so a stray click can never wipe an agent.
        if confirm != owner:
            raise HTTPException(
                status_code=400,
                detail="confirmation mismatch: pass ?confirm=<owner> with the exact owner id",
            )
        with lock:
            try:
                result = client.purge_owner(owner)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"owner": owner} | result

    @app.delete("/api/memories/{memory_id}")
    def delete_memory(memory_id: str) -> dict[str, Any]:
        with lock:
            removed = client.delete(memory_id)
        if not removed:
            raise HTTPException(status_code=404, detail=f"memory not found: {memory_id}")
        return {"deleted": memory_id}

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
        return HTMLResponse(PAGE)

    return app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="agent-memory-web", description="Run the AgentMemoryOS Web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--home", default=None, help="Memory home directory; defaults to AGENT_MEMORY_HOME or ~/.agent-memory")
    parser.add_argument(
        "--token",
        default=None,
        help="Require this bearer token on all /api/ routes (also via AGENT_MEMORY_WEB_TOKEN)",
    )
    args = parser.parse_args(argv)

    import uvicorn

    if not (args.token or os.getenv("AGENT_MEMORY_WEB_TOKEN") or load_token(args.home)):
        print("NOTE: no API token configured — the console runs in open admin mode.")
        print("      Protect it with:  agent-memory token create")

    uvicorn.run(create_app(home=args.home, token=args.token), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
