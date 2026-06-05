"""Shadow-mode recall comparison utilities for AgentMemoryOS.

The monitor records legacy-vs-candidate recall comparisons as JSONL so the
v0.3 -> v0.4 migration can collect KPI evidence while legacy memory remains the
primary response source.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean
from typing import Iterable, Any


@dataclass(frozen=True)
class ShadowModePolicy:
    """Acceptance thresholds from ``Shadow_Mode_Timeline.md``."""

    phase: str = "Phase 1: Silent Mirroring"
    recall_target: float = 0.95
    p99_latency_target_ms: float = 200.0
    p99_latency_pause_ms: float = 500.0


class ShadowRecallMonitor:
    """Append-only recorder for legacy/candidate recall comparisons."""

    def __init__(self, *, log_path: str | Path, policy: ShadowModePolicy | None = None) -> None:
        self.log_path = Path(log_path)
        self.policy = policy or ShadowModePolicy()

    def compare_recall(
        self,
        *,
        query: str,
        legacy_results: Iterable[str],
        candidate_results: Iterable[str],
        legacy_latency_ms: float,
        candidate_latency_ms: float,
        acl_leakage: bool = False,
    ) -> dict[str, Any]:
        """Compare top-k result overlap and persist one shadow-mode record."""

        legacy = list(legacy_results)
        candidate = list(candidate_results)
        top_k_hit_rate = _top_k_hit_rate(legacy, candidate)
        latency_delta_ms = round(float(candidate_latency_ms) - float(legacy_latency_ms), 3)
        go_no_go = self._go_no_go(top_k_hit_rate, float(candidate_latency_ms), acl_leakage)

        record: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": self.policy.phase,
            "query": query,
            "legacy_count": len(legacy),
            "candidate_count": len(candidate),
            "top_k_hit_rate": top_k_hit_rate,
            "legacy_latency_ms": float(legacy_latency_ms),
            "candidate_latency_ms": float(candidate_latency_ms),
            "latency_delta_ms": latency_delta_ms,
            "acl_zero_leakage": not acl_leakage,
            "go_no_go": go_no_go,
        }
        self._append(record)
        return record

    def summarize(self) -> dict[str, Any]:
        """Summarize KPI status from the JSONL log."""

        records = list(self._read_records())
        if not records:
            return {
                "records": 0,
                "mean_top_k_hit_rate": 0.0,
                "p99_candidate_latency_ms": 0.0,
                "no_go_count": 0,
            }

        latencies = sorted(float(record["candidate_latency_ms"]) for record in records)
        no_go_count = sum(1 for record in records if str(record.get("go_no_go", "")).startswith("NO_GO"))
        return {
            "records": len(records),
            "mean_top_k_hit_rate": round(mean(float(record["top_k_hit_rate"]) for record in records), 3),
            "p99_candidate_latency_ms": _nearest_rank_p99(latencies),
            "no_go_count": no_go_count,
        }

    def _go_no_go(self, hit_rate: float, candidate_latency_ms: float, acl_leakage: bool) -> str:
        if acl_leakage:
            return "NO_GO_ACL_LEAKAGE"
        if candidate_latency_ms > self.policy.p99_latency_pause_ms:
            return "NO_GO_LATENCY_PAUSE"
        if hit_rate < self.policy.recall_target:
            return "WATCH_RECALL_BELOW_TARGET"
        return "GO"

    def _append(self, record: dict[str, Any]) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    def _read_records(self) -> Iterable[dict[str, Any]]:
        if not self.log_path.exists():
            return []
        records = []
        with self.log_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records


def _top_k_hit_rate(legacy_results: list[str], candidate_results: list[str]) -> float:
    if not legacy_results:
        return 1.0 if not candidate_results else 0.0
    legacy_norm = {_normalize_result(result) for result in legacy_results}
    candidate_norm = {_normalize_result(result) for result in candidate_results}
    return round(len(legacy_norm & candidate_norm) / len(legacy_norm), 3)


def _normalize_result(result: str) -> str:
    return " ".join(result.casefold().split())


def _nearest_rank_p99(sorted_values: list[float]) -> float:
    if not sorted_values:
        return 0.0
    # Nearest-rank p99; for tiny shadow logs this intentionally resolves to max.
    index = max(0, min(len(sorted_values) - 1, int(0.99 * len(sorted_values) + 0.999999) - 1))
    value = sorted_values[index]
    return int(value) if value.is_integer() else value
