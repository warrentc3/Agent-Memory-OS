import math

from agent_memory_os.scoring import (
    effective_score,
    freshness_factor,
    reinforcement_factor,
)


def test_exponential_decay_half_life_reduces_score_by_half():
    """Lineage:
    main: introduced 7231a70d@pre-migration-registry.
    """
    assert freshness_factor("exponential", age_days=30, half_life_days=30) == 0.5


def test_linear_decay_reaches_zero_at_half_life():
    """Lineage:
    main: introduced 7231a70d@pre-migration-registry.
    """
    assert freshness_factor("linear", age_days=30, half_life_days=30) == 0.0


def test_pinned_memory_has_full_freshness():
    """Lineage:
    main: introduced 7231a70d@pre-migration-registry.
    """
    assert freshness_factor("exponential", age_days=3650, half_life_days=1, pinned=True) == 1.0


def test_reinforcement_factor_is_capped():
    """Lineage:
    main: introduced 7231a70d@pre-migration-registry.
    """
    assert reinforcement_factor(0) == 1.0
    assert reinforcement_factor(10_000) == 1.25


def test_effective_score_combines_metadata_freshness_and_reinforcement():
    """Lineage:
    main: introduced 7231a70d@pre-migration-registry.
    """
    score = effective_score(
        text_score=1.0,
        importance=1.0,
        confidence=1.0,
        freshness=0.5,
        reinforcement=1.2,
    )
    assert math.isclose(score, 0.6)
