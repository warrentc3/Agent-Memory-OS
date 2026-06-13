"""Golden-query recall evaluation for AgentMemoryOS shadow cutover gates.

Golden queries are deterministic reviewer-owned cases used to prove that the
candidate memory backend can retrieve critical profile facts before production
injection is allowed.  The evaluator is intentionally local and lexical so the
Evidence Pack can be reproduced without LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json

from .client import MemoryClient


@dataclass(slots=True)
class GoldenQueryCase:
    id: str
    query: str
    expected: list[str]
    owner: str | None = None
    scope: str | None = None
    forbidden: list[str] = field(default_factory=list)
    limit: int = 10
    min_results: int = 1


@dataclass(slots=True)
class GoldenCaseResult:
    id: str
    query: str
    owner: str | None
    scope: str | None
    passed: bool
    expected_hit_rate: float
    expected_hits: list[str]
    expected_misses: list[str]
    forbidden_hits: list[str]
    retrieved_count: int
    result_ids: list[str]
    top_results: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "query": self.query,
            "owner": self.owner,
            "scope": self.scope,
            "passed": self.passed,
            "expected_hit_rate": self.expected_hit_rate,
            "expected_hits": self.expected_hits,
            "expected_misses": self.expected_misses,
            "forbidden_hits": self.forbidden_hits,
            "retrieved_count": self.retrieved_count,
            "result_ids": self.result_ids,
            "top_results": self.top_results,
        }


def load_golden_query_cases(path: str | Path) -> list[GoldenQueryCase]:
    """Load golden-query cases from JSON or JSONL.

    JSON may be either a list of case objects or ``{"cases": [...]}``. JSONL
    accepts one case object per non-empty line. The intentionally small schema
    avoids adding a YAML dependency to the local-first baseline.
    """

    p = Path(path)
    text = p.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if p.suffix.lower() == ".jsonl":
        raw_cases = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        payload = json.loads(text)
        raw_cases = payload.get("cases", payload) if isinstance(payload, dict) else payload
    if not isinstance(raw_cases, list):
        raise ValueError("golden query file must contain a list of cases or {'cases': [...]} object")
    return [_parse_case(raw, index=index) for index, raw in enumerate(raw_cases, start=1)]


def evaluate_golden_queries(
    client: MemoryClient,
    cases: list[GoldenQueryCase],
    *,
    default_limit: int = 10,
    recall_target: float = 0.95,
) -> dict[str, Any]:
    """Run golden queries against a MemoryClient and return an evidence report."""

    results = [_evaluate_case(client, case, default_limit=default_limit) for case in cases]
    total = len(results)
    passed = sum(1 for result in results if result.passed)
    forbidden_hit_count = sum(len(result.forbidden_hits) for result in results)
    golden_recall_rate = round(passed / total, 3) if total else 0.0
    mean_expected_hit_rate = (
        round(sum(result.expected_hit_rate for result in results) / total, 3) if total else 0.0
    )
    activation_gate = _activation_gate(
        total=total,
        golden_recall_rate=golden_recall_rate,
        forbidden_hit_count=forbidden_hit_count,
        recall_target=recall_target,
    )
    return {
        "activation_gate": activation_gate,
        "cases": total,
        "passed": passed,
        "failed": total - passed,
        "golden_recall_rate": golden_recall_rate,
        "mean_expected_hit_rate": mean_expected_hit_rate,
        "forbidden_hit_count": forbidden_hit_count,
        "recall_target": recall_target,
        "results": [result.as_dict() for result in results],
    }


def _evaluate_case(client: MemoryClient, case: GoldenQueryCase, *, default_limit: int) -> GoldenCaseResult:
    limit = case.limit or default_limit
    search_results = client.search(case.query, owner=case.owner, scope=case.scope, limit=limit)
    normalized_contents = [_normalize(result.record.content) for result in search_results]

    expected_hits = [term for term in case.expected if _contains_any(normalized_contents, term)]
    expected_misses = [term for term in case.expected if term not in expected_hits]
    forbidden_hits = [term for term in case.forbidden if _contains_any(normalized_contents, term)]
    expected_hit_rate = round(len(expected_hits) / len(case.expected), 3) if case.expected else 1.0
    passed = (
        not expected_misses
        and not forbidden_hits
        and len(search_results) >= case.min_results
    )
    return GoldenCaseResult(
        id=case.id,
        query=case.query,
        owner=case.owner,
        scope=case.scope,
        passed=passed,
        expected_hit_rate=expected_hit_rate,
        expected_hits=expected_hits,
        expected_misses=expected_misses,
        forbidden_hits=forbidden_hits,
        retrieved_count=len(search_results),
        result_ids=[result.record.id for result in search_results],
        top_results=[
            {
                "id": result.record.id,
                "score": result.score,
                "owner": result.record.owner,
                "scope": result.record.scope,
                "type": result.record.type,
                "summary": result.record.normalized_summary(),
            }
            for result in search_results[:5]
        ],
    )


def _parse_case(raw: object, *, index: int) -> GoldenQueryCase:
    if not isinstance(raw, dict):
        raise ValueError(f"golden query case #{index} must be an object")
    query = str(raw.get("query", "")).strip()
    if not query:
        raise ValueError(f"golden query case #{index} is missing query")
    expected = _string_list(raw.get("expected", raw.get("expected_contains", [])))
    forbidden = _string_list(raw.get("forbidden", raw.get("forbidden_contains", [])))
    return GoldenQueryCase(
        id=str(raw.get("id") or f"case-{index:03d}"),
        query=query,
        expected=expected,
        owner=_optional_string(raw.get("owner")),
        scope=_optional_string(raw.get("scope")),
        forbidden=forbidden,
        limit=int(raw.get("limit", 10) or 10),
        min_results=int(raw.get("min_results", 1) or 0),
    )


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        raise ValueError("expected/forbidden fields must be strings or lists of strings")
    return [str(item) for item in value]


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _contains_any(normalized_contents: list[str], term: str) -> bool:
    needle = _normalize(term)
    return any(needle in content for content in normalized_contents)


def _normalize(text: str) -> str:
    return " ".join(str(text).casefold().split())


def _activation_gate(
    *,
    total: int,
    golden_recall_rate: float,
    forbidden_hit_count: int,
    recall_target: float,
) -> str:
    if total == 0:
        return "NO_GO_NO_GOLDEN_CASES"
    if forbidden_hit_count:
        return "NO_GO_GOLDEN_FORBIDDEN_MATCH"
    if golden_recall_rate < recall_target:
        return "WATCH_GOLDEN_RECALL_BELOW_TARGET"
    return "GO"
