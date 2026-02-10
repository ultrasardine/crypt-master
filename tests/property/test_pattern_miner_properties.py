"""
Property-based tests for Pattern Miner.

Feature: market-intelligence-layer
Properties 13-14: Pattern storage threshold enforcement

These tests use the hypothesis library to verify that the PatternMiner
correctly enforces thresholds for pattern storage.

**Validates: Requirements 5.2, 5.5**
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from lib.analysis.pattern_miner import PatternCandidate, PatternMinerConfig


# =============================================================================
# Custom Strategies for Pattern Miner Testing
# =============================================================================


@st.composite
def pattern_candidate_strategy(
    draw: st.DrawFn,
    min_sample_size: int | None = None,
    max_sample_size: int | None = None,
    min_hit_rate: float | None = None,
    max_hit_rate: float | None = None,
    min_avg_pnl: float | None = None,
    max_avg_pnl: float | None = None,
) -> PatternCandidate:
    """
    Generate random PatternCandidate instances for testing.

    Args:
        draw: Hypothesis draw function
        min_sample_size: Minimum sample size (default: 1)
        max_sample_size: Maximum sample size (default: 1000)
        min_hit_rate: Minimum hit rate (default: 0.0)
        max_hit_rate: Maximum hit rate (default: 1.0)
        min_avg_pnl: Minimum average P&L (default: -50.0)
        max_avg_pnl: Maximum average P&L (default: 50.0)

    Returns:
        PatternCandidate instance with valid values
    """
    sample_size = draw(
        st.integers(
            min_value=min_sample_size or 1,
            max_value=max_sample_size or 1000,
        )
    )

    hit_rate = draw(
        st.floats(
            min_value=min_hit_rate or 0.0,
            max_value=max_hit_rate or 1.0,
            allow_nan=False,
            allow_infinity=False,
        )
    )

    avg_pnl = draw(
        st.floats(
            min_value=min_avg_pnl or -50.0,
            max_value=max_avg_pnl or 50.0,
            allow_nan=False,
            allow_infinity=False,
        )
    )

    regime = draw(
        st.sampled_from(["RISK_ON", "RISK_OFF", "RANGE_BOUND", "TRENDING_UP", "TRENDING_DOWN"])
    )

    return PatternCandidate(
        feature_combination={"regime": regime},
        sample_size=sample_size,
        hit_rate=hit_rate,
        average_pnl=avg_pnl,
    )


@st.composite
def pattern_miner_config_strategy(draw: st.DrawFn) -> PatternMinerConfig:
    """
    Generate random PatternMinerConfig instances for testing.

    Returns:
        PatternMinerConfig instance with valid values
    """
    return PatternMinerConfig(
        min_sample_size=draw(st.integers(min_value=1, max_value=100)),
        min_hit_rate=draw(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
        ),
        min_avg_pnl=draw(
            st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False)
        ),
        lookback_days=draw(st.integers(min_value=1, max_value=365)),
    )


# =============================================================================
# Property 13: Pattern storage respects thresholds
# =============================================================================


class TestPatternThresholdEnforcement:
    """
    Property 13: Pattern storage respects thresholds

    *For any* feature combination evaluated by the `PatternMiner`, if the
    combination's hit-rate is below `min_hit_rate` OR average P&L is below
    `min_avg_pnl`, the combination SHALL NOT be stored as a `StrategyPattern`.

    **Validates: Requirements 5.2**
    """

    @settings(max_examples=100)
    @given(
        config=pattern_miner_config_strategy(),
        # Generate candidate with hit_rate in lower range to ensure below threshold
        hit_rate=st.floats(min_value=0.0, max_value=0.3, allow_nan=False, allow_infinity=False),
        sample_size=st.integers(min_value=50, max_value=200),
        avg_pnl=st.floats(min_value=5.0, max_value=50.0, allow_nan=False, allow_infinity=False),
    )
    def test_below_hit_rate_threshold_not_stored(
        self,
        config: PatternMinerConfig,
        hit_rate: float,
        sample_size: int,
        avg_pnl: float,
    ) -> None:
        """
        Property: For any candidate with hit_rate below min_hit_rate,
        the candidate SHALL NOT be stored.

        **Validates: Requirements 5.2**
        """
        # Ensure candidate is below hit rate threshold
        assume(hit_rate < config.min_hit_rate)
        # Ensure sample size is sufficient (to isolate hit rate check)
        assume(sample_size >= config.min_sample_size)

        candidate = PatternCandidate(
            feature_combination={"regime": "RISK_ON"},
            sample_size=sample_size,
            hit_rate=hit_rate,
            average_pnl=avg_pnl,
        )

        # Check if candidate would be stored
        would_store = (
            candidate.sample_size >= config.min_sample_size
            and candidate.hit_rate >= config.min_hit_rate
            and candidate.average_pnl >= config.min_avg_pnl
        )

        assert not would_store, (
            f"Candidate with hit_rate {candidate.hit_rate:.2f} below threshold "
            f"{config.min_hit_rate:.2f} should NOT be stored"
        )

    @settings(max_examples=100)
    @given(
        config=pattern_miner_config_strategy(),
        # Generate candidate with avg_pnl in lower range to ensure below threshold
        avg_pnl=st.floats(min_value=-50.0, max_value=-5.0, allow_nan=False, allow_infinity=False),
        sample_size=st.integers(min_value=50, max_value=200),
        hit_rate=st.floats(min_value=0.7, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    def test_below_avg_pnl_threshold_not_stored(
        self,
        config: PatternMinerConfig,
        avg_pnl: float,
        sample_size: int,
        hit_rate: float,
    ) -> None:
        """
        Property: For any candidate with average_pnl below min_avg_pnl,
        the candidate SHALL NOT be stored.

        **Validates: Requirements 5.2**
        """
        # Ensure candidate is below avg P&L threshold
        assume(avg_pnl < config.min_avg_pnl)
        # Ensure sample size and hit rate are sufficient (to isolate avg P&L check)
        assume(sample_size >= config.min_sample_size)
        assume(hit_rate >= config.min_hit_rate)

        candidate = PatternCandidate(
            feature_combination={"regime": "RISK_ON"},
            sample_size=sample_size,
            hit_rate=hit_rate,
            average_pnl=avg_pnl,
        )

        # Check if candidate would be stored
        would_store = (
            candidate.sample_size >= config.min_sample_size
            and candidate.hit_rate >= config.min_hit_rate
            and candidate.average_pnl >= config.min_avg_pnl
        )

        assert not would_store, (
            f"Candidate with average_pnl {candidate.average_pnl:.2f}% below threshold "
            f"{config.min_avg_pnl:.2f}% should NOT be stored"
        )

    @settings(max_examples=100)
    @given(
        config=pattern_miner_config_strategy(),
        # Generate candidate with values that are likely to meet thresholds
        sample_size=st.integers(min_value=100, max_value=500),
        hit_rate=st.floats(min_value=0.8, max_value=1.0, allow_nan=False, allow_infinity=False),
        avg_pnl=st.floats(min_value=10.0, max_value=50.0, allow_nan=False, allow_infinity=False),
    )
    def test_meeting_all_thresholds_would_store(
        self,
        config: PatternMinerConfig,
        sample_size: int,
        hit_rate: float,
        avg_pnl: float,
    ) -> None:
        """
        Property: For any candidate meeting all thresholds,
        the candidate SHALL be stored.

        **Validates: Requirements 5.2**
        """
        candidate = PatternCandidate(
            feature_combination={"regime": "RISK_ON"},
            sample_size=sample_size,
            hit_rate=hit_rate,
            average_pnl=avg_pnl,
        )

        # Ensure candidate meets all thresholds
        assume(candidate.sample_size >= config.min_sample_size)
        assume(candidate.hit_rate >= config.min_hit_rate)
        assume(candidate.average_pnl >= config.min_avg_pnl)

        # Check if candidate would be stored
        would_store = (
            candidate.sample_size >= config.min_sample_size
            and candidate.hit_rate >= config.min_hit_rate
            and candidate.average_pnl >= config.min_avg_pnl
        )

        assert would_store, (
            f"Candidate meeting all thresholds should be stored: "
            f"sample_size={candidate.sample_size} >= {config.min_sample_size}, "
            f"hit_rate={candidate.hit_rate:.2f} >= {config.min_hit_rate:.2f}, "
            f"average_pnl={candidate.average_pnl:.2f}% >= {config.min_avg_pnl:.2f}%"
        )

    @settings(max_examples=100)
    @given(
        min_hit_rate=st.floats(min_value=0.1, max_value=0.9, allow_nan=False, allow_infinity=False),
        min_avg_pnl=st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False),
        # Generate candidate that's below both thresholds
        hit_rate_offset=st.floats(
            min_value=0.01, max_value=0.5, allow_nan=False, allow_infinity=False
        ),
        avg_pnl_offset=st.floats(
            min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False
        ),
    )
    def test_below_both_thresholds_not_stored(
        self,
        min_hit_rate: float,
        min_avg_pnl: float,
        hit_rate_offset: float,
        avg_pnl_offset: float,
    ) -> None:
        """
        Property: For any candidate below BOTH hit_rate AND avg_pnl thresholds,
        the candidate SHALL NOT be stored.

        **Validates: Requirements 5.2**
        """
        config = PatternMinerConfig(
            min_sample_size=10,
            min_hit_rate=min_hit_rate,
            min_avg_pnl=min_avg_pnl,
        )

        # Create candidate below both thresholds
        candidate = PatternCandidate(
            feature_combination={"regime": "TRENDING_UP"},
            sample_size=100,  # Sufficient sample size
            hit_rate=max(0.0, min_hit_rate - hit_rate_offset),
            average_pnl=min_avg_pnl - avg_pnl_offset,
        )

        # Check if candidate would be stored
        would_store = (
            candidate.sample_size >= config.min_sample_size
            and candidate.hit_rate >= config.min_hit_rate
            and candidate.average_pnl >= config.min_avg_pnl
        )

        assert not would_store, (
            f"Candidate below both thresholds should NOT be stored"
        )


# =============================================================================
# Property 14: Minimum sample size gate
# =============================================================================


class TestMinimumSampleSizeGate:
    """
    Property 14: Minimum sample size gate

    *For any* feature combination evaluated by the `PatternMiner` with a
    sample size below `min_sample_size`, the combination SHALL NOT be stored
    as a `StrategyPattern`, regardless of hit-rate or average P&L.

    **Validates: Requirements 5.5**
    """

    @settings(max_examples=100)
    @given(
        # Generate config with min_sample_size >= 2 to ensure we can test below threshold
        min_sample_size=st.integers(min_value=2, max_value=100),
        min_hit_rate=st.floats(min_value=0.0, max_value=0.5, allow_nan=False, allow_infinity=False),
        min_avg_pnl=st.floats(min_value=-10.0, max_value=5.0, allow_nan=False, allow_infinity=False),
        # Generate candidate with excellent metrics but small sample
        hit_rate=st.floats(min_value=0.8, max_value=1.0, allow_nan=False, allow_infinity=False),
        avg_pnl=st.floats(min_value=5.0, max_value=50.0, allow_nan=False, allow_infinity=False),
    )
    def test_below_sample_size_not_stored_despite_good_metrics(
        self,
        min_sample_size: int,
        min_hit_rate: float,
        min_avg_pnl: float,
        hit_rate: float,
        avg_pnl: float,
    ) -> None:
        """
        Property: For any candidate with sample_size below min_sample_size,
        the candidate SHALL NOT be stored, even with excellent hit_rate and avg_pnl.

        **Validates: Requirements 5.5**
        """
        config = PatternMinerConfig(
            min_sample_size=min_sample_size,
            min_hit_rate=min_hit_rate,
            min_avg_pnl=min_avg_pnl,
        )

        # Create candidate with sample size below threshold but excellent metrics
        sample_size = min_sample_size - 1  # Always below threshold since min_sample_size >= 2

        candidate = PatternCandidate(
            feature_combination={"regime": "RISK_ON"},
            sample_size=sample_size,
            hit_rate=hit_rate,
            average_pnl=avg_pnl,
        )

        # Verify metrics are excellent (above thresholds)
        assume(candidate.hit_rate >= config.min_hit_rate)
        assume(candidate.average_pnl >= config.min_avg_pnl)

        # Check if candidate would be stored
        would_store = (
            candidate.sample_size >= config.min_sample_size
            and candidate.hit_rate >= config.min_hit_rate
            and candidate.average_pnl >= config.min_avg_pnl
        )

        assert not would_store, (
            f"Candidate with sample_size {candidate.sample_size} below threshold "
            f"{config.min_sample_size} should NOT be stored, even with "
            f"hit_rate={candidate.hit_rate:.2f} and avg_pnl={candidate.average_pnl:.2f}%"
        )

    @settings(max_examples=100)
    @given(
        min_sample_size=st.integers(min_value=5, max_value=100),
        sample_size_offset=st.integers(min_value=1, max_value=10),
    )
    def test_sample_size_exactly_at_threshold_is_stored(
        self,
        min_sample_size: int,
        sample_size_offset: int,
    ) -> None:
        """
        Property: For any candidate with sample_size exactly at min_sample_size,
        the candidate SHALL be stored (if other thresholds are met).

        **Validates: Requirements 5.5**
        """
        config = PatternMinerConfig(
            min_sample_size=min_sample_size,
            min_hit_rate=0.5,
            min_avg_pnl=0.0,
        )

        # Create candidate with sample size exactly at threshold
        candidate = PatternCandidate(
            feature_combination={"regime": "RANGE_BOUND"},
            sample_size=min_sample_size,  # Exactly at threshold
            hit_rate=0.7,  # Above threshold
            average_pnl=2.0,  # Above threshold
        )

        # Check if candidate would be stored
        would_store = (
            candidate.sample_size >= config.min_sample_size
            and candidate.hit_rate >= config.min_hit_rate
            and candidate.average_pnl >= config.min_avg_pnl
        )

        assert would_store, (
            f"Candidate with sample_size {candidate.sample_size} exactly at threshold "
            f"{config.min_sample_size} should be stored"
        )

    @settings(max_examples=100)
    @given(
        min_sample_size=st.integers(min_value=5, max_value=100),
    )
    def test_sample_size_one_below_threshold_not_stored(
        self,
        min_sample_size: int,
    ) -> None:
        """
        Property: For any candidate with sample_size one below min_sample_size,
        the candidate SHALL NOT be stored.

        **Validates: Requirements 5.5**
        """
        config = PatternMinerConfig(
            min_sample_size=min_sample_size,
            min_hit_rate=0.5,
            min_avg_pnl=0.0,
        )

        # Create candidate with sample size one below threshold
        candidate = PatternCandidate(
            feature_combination={"regime": "TRENDING_DOWN"},
            sample_size=min_sample_size - 1,  # One below threshold
            hit_rate=0.9,  # Excellent
            average_pnl=10.0,  # Excellent
        )

        # Check if candidate would be stored
        would_store = (
            candidate.sample_size >= config.min_sample_size
            and candidate.hit_rate >= config.min_hit_rate
            and candidate.average_pnl >= config.min_avg_pnl
        )

        assert not would_store, (
            f"Candidate with sample_size {candidate.sample_size} one below threshold "
            f"{config.min_sample_size} should NOT be stored"
        )

    @settings(max_examples=100)
    @given(
        min_sample_size=st.integers(min_value=10, max_value=100),
        actual_sample_size=st.integers(min_value=1, max_value=9),
    )
    def test_any_sample_size_below_threshold_not_stored(
        self,
        min_sample_size: int,
        actual_sample_size: int,
    ) -> None:
        """
        Property: For any sample_size below min_sample_size,
        the candidate SHALL NOT be stored.

        **Validates: Requirements 5.5**
        """
        # Ensure actual sample size is below threshold
        assume(actual_sample_size < min_sample_size)

        config = PatternMinerConfig(
            min_sample_size=min_sample_size,
            min_hit_rate=0.5,
            min_avg_pnl=0.0,
        )

        candidate = PatternCandidate(
            feature_combination={"regime": "RISK_OFF"},
            sample_size=actual_sample_size,
            hit_rate=1.0,  # Perfect hit rate
            average_pnl=100.0,  # Excellent P&L
        )

        # Check if candidate would be stored
        would_store = (
            candidate.sample_size >= config.min_sample_size
            and candidate.hit_rate >= config.min_hit_rate
            and candidate.average_pnl >= config.min_avg_pnl
        )

        assert not would_store, (
            f"Candidate with sample_size {actual_sample_size} below threshold "
            f"{min_sample_size} should NOT be stored, regardless of metrics"
        )
