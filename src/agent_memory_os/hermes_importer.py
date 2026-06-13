from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import hashlib
import json
import re
from typing import Iterable

from .client import MemoryClient

SEPARATOR = "§"
IMPORT_SYSTEM = "hermes-memory-md-import"


@dataclass(slots=True)
class HermesImportItem:
    profile: str
    file_kind: str
    source_path: Path
    section_index: int
    content: str
    owner: str
    scope: str
    type: str
    tags: list[str]
    visibility: list[str]
    memory_id: str
    source_key: str
    content_sha256: str


@dataclass(slots=True)
class HermesImportReport:
    profile: str
    imported_files: list[str] = field(default_factory=list)
    scanned: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    missing_files: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile,
            "imported_files": self.imported_files,
            "scanned": self.scanned,
            "inserted": self.inserted,
            "updated": self.updated,
            "skipped": self.skipped,
            "missing_files": self.missing_files,
        }


def split_memory_sections(text: str) -> list[str]:
    """Split Hermes MEMORY.md/USER.md content into durable memory blocks."""
    sections = []
    for raw in re.split(r"^§\s*$", text, flags=re.MULTILINE):
        section = raw.strip()
        if section:
            sections.append(section)
    return sections


def profile_memory_paths(profile_home: str | Path) -> dict[str, Path]:
    base = Path(profile_home).expanduser() / "memories"
    return {"memory": base / "MEMORY.md", "user": base / "USER.md"}


def iter_hermes_memory_items(profile: str, profile_home: str | Path) -> Iterable[HermesImportItem]:
    for file_kind, path in profile_memory_paths(profile_home).items():
        if not path.exists():
            continue
        sections = split_memory_sections(path.read_text(encoding="utf-8"))
        for index, content in enumerate(sections, start=1):
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            source_key = f"{profile}:{file_kind}:{index:04d}"
            memory_id = "hermes_" + hashlib.sha256(source_key.encode("utf-8")).hexdigest()[:32]
            yield HermesImportItem(
                profile=profile,
                file_kind=file_kind,
                source_path=path,
                section_index=index,
                content=content,
                owner=profile,
                scope="user" if file_kind == "user" else "profile",
                type=_infer_memory_type(content, file_kind),
                tags=["hermes-import", file_kind, profile],
                visibility=[f"agent:{profile}"],
                memory_id=memory_id,
                source_key=source_key,
                content_sha256=digest,
            )


def import_hermes_memory_files(
    client: MemoryClient,
    *,
    profile: str,
    profile_home: str | Path,
) -> HermesImportReport:
    """Import Hermes MEMORY.md and USER.md into AgentMemoryOS without duplicates.

    The import is profile-scoped and shadow-safe:
    - owner is the Hermes profile name;
    - visibility is restricted to that profile agent;
    - IDs are deterministic by profile/file/section slot, so reruns skip unchanged
      records and update changed slots instead of creating duplicates.
    """
    report = HermesImportReport(profile=profile)
    paths = profile_memory_paths(profile_home)
    for path in paths.values():
        if path.exists():
            report.imported_files.append(str(path))
        else:
            report.missing_files.append(str(path))

    for item in iter_hermes_memory_items(profile, profile_home):
        report.scanned += 1
        existing = client.get(item.memory_id)
        if existing and existing.content == item.content:
            report.skipped += 1
            continue
        source = {
            "system": IMPORT_SYSTEM,
            "profile": profile,
            "file_kind": item.file_kind,
            "path": str(item.source_path),
            "section_index": item.section_index,
            "source_key": item.source_key,
            "content_sha256": item.content_sha256,
            "permanence": True,
            "weight": 10,
        }
        if existing:
            # Content changed in the same source slot. Preserve the stable ID and
            # refresh metadata/source hash so later audits can trace the exact
            # imported section that produced the current record.
            client.store.update_content(item.memory_id, item.content)
            client.store.conn.execute(
                """
                UPDATE memories
                SET owner=?, scope=?, type=?, tags=?, visibility=?, source=?,
                    confidence=?, importance=?, decay_policy=?, pinned=?
                WHERE id=?
                """,
                (
                    item.owner,
                    item.scope,
                    item.type,
                    json.dumps(item.tags, ensure_ascii=False),
                    json.dumps(item.visibility, ensure_ascii=False),
                    json.dumps(source, ensure_ascii=False, sort_keys=True),
                    0.98,
                    0.9,
                    "none",
                    1,
                    item.memory_id,
                ),
            )
            client.store.conn.commit()
            report.updated += 1
            client.cache.clear()
            continue
        client.add(
            item.content,
            id=item.memory_id,
            owner=item.owner,
            scope=item.scope,
            type=item.type,
            tags=item.tags,
            visibility=item.visibility,
            source=source,
            confidence=0.98,
            importance=0.9,
            decay_policy="none",
            pinned=True,
        )
        report.inserted += 1
    return report


def _infer_memory_type(content: str, file_kind: str) -> str:
    lowered = content.lower()
    if file_kind == "user" and any(token in lowered for token in ("prefers", "wants", "likes", "user prefers", "使用者偏好")):
        return "preference"
    if any(token in lowered for token in ("workflow", "procedure", "run ", "執行", "流程", "步驟")):
        return "procedure"
    if any(token in lowered for token in ("service", "path", "directory", "cache", "ip ", "svc", "repo", "branch")):
        return "environment"
    if any(token in lowered for token in ("warning", "blocked", "forbidden", "zero-leakage", "暫停")):
        return "warning"
    return "fact"
