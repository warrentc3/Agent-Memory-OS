"""LLM-assisted link extraction for `consolidate(link_extractor=...)`.

The package never talks to an LLM itself — `make_llm_link_extractor` wraps
ANY completion function (`str -> str`) into a link extractor: it batches
memory summaries into a prompt, asks for association pairs as JSON, and
parses the reply defensively (bad output degrades to zero links, never an
exception mid-consolidation).

Example with any client:

    def complete(prompt: str) -> str:
        return llm.generate(prompt)          # your model, your keys

    client.consolidate(link_extractor=make_llm_link_extractor(complete))
"""

from __future__ import annotations

import json
import re
from typing import Callable, Iterable

from .schema import MemoryRecord

PROMPT_TEMPLATE = """You map associations between an AI agent's memories.

Below are memories, one per line, as: <id> :: <summary>

{catalog}

Return ONLY a JSON array of association pairs between DIFFERENT memories that
are meaningfully related (shared topic, cause/effect, same procedure or
entity). Each element: {{"src": "<id>", "dst": "<id>", "weight": 0.0-1.0}}.
Return [] if nothing is related. No prose, no markdown fences.
"""

MAX_MEMORIES_PER_PROMPT = 60


def make_llm_link_extractor(
    complete: Callable[[str], str],
    *,
    max_memories: int = MAX_MEMORIES_PER_PROMPT,
) -> Callable[[list[MemoryRecord]], list[tuple[str, str, float]]]:
    def extract(records: list[MemoryRecord]) -> list[tuple[str, str, float]]:
        known_ids = {record.id for record in records}
        pairs: list[tuple[str, str, float]] = []
        for start in range(0, len(records), max_memories):
            batch = records[start : start + max_memories]
            catalog = "\n".join(
                f"{record.id} :: {record.summary or record.content[:96]}" for record in batch
            )
            try:
                reply = complete(PROMPT_TEMPLATE.format(catalog=catalog))
            except Exception:  # noqa: BLE001 - extractor must never break consolidation
                continue
            pairs.extend(_parse_pairs(reply, known_ids))
        return pairs

    return extract


def _parse_pairs(reply: str, known_ids: set[str]) -> list[tuple[str, str, float]]:
    match = re.search(r"\[.*\]", reply, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    pairs: list[tuple[str, str, float]] = []
    seen: set[frozenset] = set()
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        src, dst = item.get("src"), item.get("dst")
        if src not in known_ids or dst not in known_ids or src == dst:
            continue
        key = frozenset((src, dst))
        if key in seen:
            continue
        seen.add(key)
        try:
            weight = min(1.0, max(0.0, float(item.get("weight", 0.5))))
        except (TypeError, ValueError):
            weight = 0.5
        pairs.append((src, dst, weight))
    return pairs
