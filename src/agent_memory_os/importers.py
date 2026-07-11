"""Best-effort importers from other memory systems into AgentMemoryOS.

Each importer maps a source export (a JSON file) onto durable memories with:
- a DETERMINISTIC id derived from source + a stable per-record key, so re-running
  an import skips unchanged records and refreshes changed ones (never duplicates);
- `source` metadata recording exactly where the memory came from;
- an owner you choose (default the source name), and private-by-default visibility
  unless you pass `--visibility`.

Export schemas across tools drift, so these accept the *documented common shapes*
and degrade gracefully on unknown fields rather than crashing. See
`docs/IMPORTERS.md` for the exact shapes and how to produce each export.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .client import MemoryClient

SUPPORTED = ("mem0", "zep", "chatgpt")


@dataclass(slots=True)
class ImportReport:
    source: str
    scanned: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "source": self.source, "scanned": self.scanned, "inserted": self.inserted,
            "updated": self.updated, "skipped": self.skipped, "warnings": self.warnings,
        }


@dataclass(slots=True)
class _Item:
    key: str          # stable per-record identity within the source
    content: str
    meta: dict[str, Any]


def _det_id(source: str, key: str) -> str:
    return f"{source}_" + hashlib.sha256(f"{source}:{key}".encode("utf-8")).hexdigest()[:32]


def _first(d: dict, *names: str) -> Any:
    for n in names:
        v = d.get(n)
        if v not in (None, ""):
            return v
    return None


def _mem0_items(data: Any) -> Iterable[_Item]:
    """Mem0 export: a list of memory objects, or {"results":[...]} / {"memories":[...]}.
    Each object typically has `memory`/`text`/`content` plus `id`, `user_id`,
    `metadata`, `created_at`."""
    rows = data
    if isinstance(data, dict):
        rows = _first(data, "results", "memories", "data") or []
    for i, row in enumerate(rows or []):
        if not isinstance(row, dict):
            continue
        content = _first(row, "memory", "text", "content")
        if not content:
            continue
        key = str(_first(row, "id", "hash") or f"idx{i:06d}")
        yield _Item(key=key, content=str(content), meta={
            "user_id": _first(row, "user_id", "agent_id"),
            "created_at": _first(row, "created_at", "timestamp"),
            "metadata": row.get("metadata"),
        })


def _zep_items(data: Any) -> Iterable[_Item]:
    """Zep/Graphiti export: `facts` (edges with a `fact` string) and/or `messages`
    (with `content`/`role`). Accept a list or an object holding either."""
    facts = messages = None
    if isinstance(data, dict):
        facts = _first(data, "facts", "edges")
        messages = _first(data, "messages", "episodes")
    elif isinstance(data, list):
        facts = data
    for i, row in enumerate(facts or []):
        if isinstance(row, dict):
            content = _first(row, "fact", "name", "summary", "content")
        else:
            content = row
        if not content:
            continue
        key = str((isinstance(row, dict) and _first(row, "uuid", "id")) or f"fact{i:06d}")
        yield _Item(key=key, content=str(content), meta={"kind": "fact"})
    for i, row in enumerate(messages or []):
        if not isinstance(row, dict):
            continue
        content = _first(row, "content", "message")
        if not content:
            continue
        key = str(_first(row, "uuid", "id") or f"msg{i:06d}")
        yield _Item(key=key, content=str(content),
                    meta={"kind": "message", "role": row.get("role")})


def _chatgpt_items(data: Any) -> Iterable[_Item]:
    """ChatGPT export. Two shapes: the account `memory`/`user_memories` list, OR
    `conversations.json` (list of conversations with a `mapping` of message nodes).
    For conversations we import only messages tagged as user memory is unavailable,
    so we import `system`/`assistant` 'memory'-like notes conservatively: by default
    only explicit memory entries, and (opt-in) conversation messages."""
    # Shape A: explicit memory entries.
    entries = None
    if isinstance(data, dict):
        entries = _first(data, "memories", "user_memories", "memory")
    if isinstance(entries, list):
        for i, row in enumerate(entries):
            content = row if isinstance(row, str) else (isinstance(row, dict) and _first(row, "content", "text", "memory"))
            if not content:
                continue
            key = str((isinstance(row, dict) and _first(row, "id")) or f"mem{i:06d}")
            yield _Item(key=key, content=str(content), meta={"kind": "chatgpt-memory"})
        return
    # Shape B: conversations.json — extract user turns (the durable signal).
    convs = data if isinstance(data, list) else _first(data, "conversations") or []
    for c, conv in enumerate(convs or []):
        if not isinstance(conv, dict):
            continue
        title = conv.get("title") or ""
        mapping = conv.get("mapping") or {}
        for node_id, node in mapping.items():
            msg = (node or {}).get("message") if isinstance(node, dict) else None
            if not isinstance(msg, dict):
                continue
            role = (msg.get("author") or {}).get("role")
            if role != "user":
                continue
            parts = ((msg.get("content") or {}).get("parts")) or []
            text = " ".join(p for p in parts if isinstance(p, str)).strip()
            if not text:
                continue
            yield _Item(key=str(msg.get("id") or f"{c}:{node_id}"), content=text,
                        meta={"kind": "chatgpt-conversation", "title": title, "role": role})


_PARSERS = {"mem0": _mem0_items, "zep": _zep_items, "chatgpt": _chatgpt_items}


def import_export(
    client: MemoryClient,
    source: str,
    path: str | Path,
    *,
    owner: str | None = None,
    visibility: list[str] | None = None,
    memory_type: str = "note",
) -> ImportReport:
    """Import a `source` export file into the store (idempotent by deterministic id)."""
    source = source.lower().strip()
    if source not in _PARSERS:
        raise ValueError(f"unknown source {source!r}; supported: {', '.join(SUPPORTED)}")
    owner = owner or source
    visibility = visibility if visibility is not None else []  # private by default
    report = ImportReport(source=source)
    text = Path(path).expanduser().read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc

    for item in _PARSERS[source](data):
        content = item.content.strip()
        if not content:
            continue
        report.scanned += 1
        mem_id = _det_id(source, item.key)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        existing = client.get(mem_id)
        if existing and existing.content == content:
            report.skipped += 1
            continue
        src_meta = {"system": f"{source}-import", "source_key": item.key,
                    "content_sha256": digest, **{k: v for k, v in item.meta.items() if v is not None}}
        if existing:
            client.store.update_content(mem_id, content)
            report.updated += 1
            continue
        client.add(content, id=mem_id, owner=owner, type=memory_type,
                   tags=[f"{source}-import"], visibility=list(visibility), source=src_meta)
        report.inserted += 1
    return report
