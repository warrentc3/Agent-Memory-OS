from __future__ import annotations

from dataclasses import dataclass, field
import re

from .schema import SearchResult


@dataclass(slots=True)
class ContextDecision:
    memory_id: str
    selected: bool
    effective_score: float
    token_count: int
    reason: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ContextPackReport:
    text: str
    decisions: list[ContextDecision]
    used_tokens: int
    max_tokens: int


def approx_tokens(text: str) -> int:
    # Conservative, dependency-free approximation for MVP.
    return max(1, (len(text) + 3) // 4)


def build_context_pack(results: list[SearchResult], *, max_tokens: int = 1200) -> str:
    return build_context_pack_report(results, max_tokens=max_tokens).text


def build_context_pack_report(results: list[SearchResult], *, max_tokens: int = 1200) -> ContextPackReport:
    if max_tokens < 32:
        raise ValueError("max_tokens must be >= 32")

    ranked = sorted(results, key=_arbitration_score, reverse=True)
    conflict_keys = _conflict_keys(results)

    header = "MEMORY CONTEXT PACK:"
    used = approx_tokens(header + "\n")
    lines: list[str] = [header]
    decisions: list[ContextDecision] = []
    seen_claims: set[tuple[str, str]] = set()
    selected_count = 0

    for result in ranked:
        record = result.record
        score = _arbitration_score(result)
        reason = _base_reasons(result, conflict_keys)
        claim_key = _claim_key(result)
        claim_value = _claim_value(result)
        duplicate_key = (claim_key, claim_value)

        if duplicate_key in seen_claims:
            reason.append("duplicate_cluster_suppressed")
            decisions.append(
                ContextDecision(
                    memory_id=record.id,
                    selected=False,
                    effective_score=score,
                    token_count=_line_tokens(result, selected_count + 1, conflict_keys),
                    reason=reason,
                )
            )
            continue

        line = _format_line(result, selected_count + 1, conflict_keys)
        cost = approx_tokens(line) + 1
        if used + cost > max_tokens:
            reason.append("budget_exceeded")
            decisions.append(
                ContextDecision(
                    memory_id=record.id,
                    selected=False,
                    effective_score=score,
                    token_count=cost,
                    reason=reason,
                )
            )
            continue

        reason.append("fits_budget")
        selected_count += 1
        lines.append(line)
        used += cost
        seen_claims.add(duplicate_key)
        decisions.append(
            ContextDecision(
                memory_id=record.id,
                selected=True,
                effective_score=score,
                token_count=cost,
                reason=reason,
            )
        )

    return ContextPackReport(
        text="\n".join(lines) + "\n",
        decisions=decisions,
        used_tokens=used,
        max_tokens=max_tokens,
    )


def _format_line(result: SearchResult, idx: int, conflict_keys: set[str]) -> str:
    r = result.record
    tags = ",".join(r.tags[:5])
    conflict = " [CONFLICT]" if _claim_key(result) in conflict_keys else ""
    return (
        f"- [{idx}]{conflict} ({r.scope}/{r.type}; importance={r.importance:.2f}; "
        f"confidence={r.confidence:.2f}; score={_arbitration_score(result):.3f}; tags={tags}) {r.content}"
    )


def _line_tokens(result: SearchResult, idx: int, conflict_keys: set[str]) -> int:
    return approx_tokens(_format_line(result, idx, conflict_keys)) + 1


def _base_reasons(result: SearchResult, conflict_keys: set[str]) -> list[str]:
    r = result.record
    reasons = ["acl_allowed", "not_expired"]
    source = r.source or {}
    tags = set(r.tags)
    if r.confidence >= 0.8:
        reasons.append("high_confidence")
    elif r.confidence < 0.5:
        reasons.append("low_confidence")
    if r.importance >= 0.8:
        reasons.append("high_importance")
    if source.get("authoritative") is True or "authoritative" in tags or "core" in tags:
        reasons.append("authoritative")
    if source.get("permanence") is True or r.pinned:
        reasons.append("permanent")
    if _weight(source) > 8:
        reasons.append("weight_gt_8")
    if {"authoritative", "permanent", "weight_gt_8"}.intersection(reasons):
        reasons.append("core_reserved_budget")
    if _claim_key(result) in conflict_keys:
        reasons.append("conflict_detected")
    if result.reason:
        reasons.append(f"provider:{result.reason}")
    return reasons


def _arbitration_score(result: SearchResult) -> float:
    r = result.record
    source = r.source or {}
    tags = set(r.tags)
    score = float(result.score)
    score += r.confidence * 1.2
    score += r.importance * 1.2
    if source.get("authoritative") is True or "authoritative" in tags or "core" in tags:
        score += 1.0
    if source.get("permanence") is True or r.pinned:
        score += 0.8
    if _weight(source) > 8:
        score += 0.8
    if r.confidence < 0.5:
        score -= 1.0
    return score


def _conflict_keys(results: list[SearchResult]) -> set[str]:
    claims_by_key: dict[str, set[str]] = {}
    for result in results:
        source = result.record.source or {}
        if "claim" not in source:
            continue
        claims_by_key.setdefault(_claim_key(result), set()).add(str(source["claim"]))
    return {key for key, claims in claims_by_key.items() if len(claims) > 1}


def _claim_key(result: SearchResult) -> str:
    source = result.record.source or {}
    key = source.get("claim_key")
    if key:
        return str(key)
    return _fingerprint(result.record.content)


def _claim_value(result: SearchResult) -> str:
    source = result.record.source or {}
    if "claim" in source:
        return str(source["claim"])
    return _fingerprint(result.record.content)


def _fingerprint(text: str) -> str:
    normalized = re.sub(r"\W+", " ", text.casefold()).strip()
    return " ".join(normalized.split())[:160]


def _weight(source: dict) -> float:
    try:
        return float(source.get("weight", 0))
    except (TypeError, ValueError):
        return 0.0
