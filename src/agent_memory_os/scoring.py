from __future__ import annotations

import math

VALID_DECAY_POLICIES = {"none", "linear", "exponential"}


def freshness_factor(
    policy: str | None,
    *,
    age_days: float,
    half_life_days: float | None,
    pinned: bool = False,
) -> float:
    """Return a bounded freshness multiplier for a memory record.

    Expiration and ACL are handled outside this soft scoring function.
    """
    normalized_policy = policy or "none"
    if normalized_policy not in VALID_DECAY_POLICIES:
        raise ValueError(f"invalid decay policy: {policy}")
    if pinned or normalized_policy == "none":
        return 1.0
    if half_life_days is None or half_life_days <= 0:
        raise ValueError("half_life_days must be positive when decay is enabled")
    bounded_age = max(0.0, float(age_days))
    if normalized_policy == "linear":
        return max(0.0, 1.0 - bounded_age / float(half_life_days))
    return 0.5 ** (bounded_age / float(half_life_days))


def reinforcement_factor(access_count: int | None) -> float:
    """Return the access-count reinforcement multiplier, capped to avoid lock-in."""
    count = max(0, int(access_count or 0))
    return min(1.25, 1.0 + math.log1p(count) * 0.03)


def effective_score(
    *,
    text_score: float,
    importance: float,
    confidence: float,
    freshness: float,
    reinforcement: float,
) -> float:
    """Combine textual match quality with metadata, freshness, and reinforcement."""
    metadata_weight = 0.45 + 0.35 * float(importance) + 0.20 * float(confidence)
    return float(text_score) * metadata_weight * float(freshness) * float(reinforcement)
