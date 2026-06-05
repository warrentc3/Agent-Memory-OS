from __future__ import annotations

from .schema import SearchResult


def approx_tokens(text: str) -> int:
    # Conservative, dependency-free approximation for MVP.
    return max(1, (len(text) + 3) // 4)


def build_context_pack(results: list[SearchResult], *, max_tokens: int = 1200) -> str:
    if max_tokens < 32:
        raise ValueError("max_tokens must be >= 32")
    header = "MEMORY CONTEXT PACK:\n"
    used = approx_tokens(header)
    lines: list[str] = [header.rstrip()]
    for idx, result in enumerate(results, start=1):
        r = result.record
        tags = ",".join(r.tags[:5])
        line = f"- [{idx}] ({r.scope}/{r.type}; importance={r.importance:.2f}; confidence={r.confidence:.2f}; tags={tags}) {r.content}"
        cost = approx_tokens(line) + 1
        if used + cost > max_tokens:
            remaining = max_tokens - used
            if remaining > 24:
                clipped_chars = max(32, remaining * 4 - 16)
                lines.append(line[:clipped_chars].rstrip() + "…")
            break
        lines.append(line)
        used += cost
    return "\n".join(lines) + "\n"
