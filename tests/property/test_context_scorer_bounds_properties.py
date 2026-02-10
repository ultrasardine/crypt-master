"""
Property-based tests for ContextScorer Composite Score Bounds.

Feature: market-intelligence-layer
Property 5: Composite scores are bounded

These tests use the hypothesis library to verify that ContextScorer.compute_scores()
always produces composite scores within the valid range [0.0, 1.0].

**Validates: Requirements 3.1, 3.2, 3.3**
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.core.models import MarketContextSnapshot
from lib.analysis.context import ContextScorer, ContextScorerConfig

# =============================================================================
# Custom Strategies for ContextScorer Testing
# =============================================================================


@st.composite
def market_context_snapshots(draw: st.DrawFn) -> MarketContextSnapshot:
    """
    Generate random MarketContextSnapshot instances for testing.

    Returns snapshots with all fields populated with valid random values,
    including None for optional fields.
    """
    snapshot = MarketContextSnapshot(
        symbol=draw(st.one_of(st.none(), st.text(min_size=1, max_size=20))),
        timestamp=timezone.now(),
        btc_dominance=draw(
            st.one_of(
                st.none(),
                st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
            )
        ),
        global_market_cap=draw(
            st.one_of(
                st.none(),
                st.decimals(
                    min_value=Decimal("0.0"),
                    max_value=Decimal("1e15"),
                    allow_nan=False,
                    allow_infinity=False,
                    places=2,
                ),
            )
        ),
        total_volume_24h=draw(
            st.one_of(
                st.none(),
                st.decimals(
                    min_value=Decimal("0.0"),
                    max_value=Decimal("1e15"),
                    allow_nan=False,
                    allow_infinity=False,
                    places=2,
                ),
            )
        ),
        active_addresses=draw(st.one_of(st.none(), st.integers(min_value=0, max_value=10_000_000))),
        net_exchange_flow=draw(
            st.one_of(
                st.none(),
                st.floats(min_value=-10000.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
            )
        ),
        whale_tx_count=draw(st.one_of(st.none(), st.integers(min_value=0, max_value=10000))),
        defi_tvl=draw(
            st.one_of(
                st.none(),
                st.decimals(
                    min_value=Decimal("0.0"),
                    max_value=Decimal("200e9"),
                    allow_nan=False,
                    allow_infinity=False,
                    places=2,
                ),
            )
        ),
        social_sentiment_score=draw(
            st.one_of(
                st.none(),
                st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            )
        ),
        social_mention_count=draw(st.one_of(st.none(), st.integers(min_value=0, max_value=1000000))),
        social_buzz_score=draw(
            st.one_of(
                st.none(),
                st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
            )
        ),
        fear_greed_index=draw(st.one_of(st.none(), st.integers(min_value=0, max_value=100))),
        is_stale=draw(st.booleans()),
        stale_fields=draw(st.lists(st.text(min_size=1, max_size=30), max_size=10)),
        is_degraded=draw(st.booleans()),
    )
    return snapshot


@st.composite
def technical_summaries(draw: st.DrawFn) -> dict[str, float]:
    """
    Generate random technical summary dictionaries for testing.

    Returns dicts with technical indicator values, including None for
    optional indicators.
    """
    summary = {}

    # ADX (0-100)
    if draw(st.booleans()):
        summary["adx"] = draw(
            st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
        )

    # Bollinger Band width (0-0.2)
    if draw(st.booleans()):
        summary["bb_width"] = draw(
            st.floats(min_value=0.0, max_value=0.2, allow_nan=False, allow_infinity=False)
        )

    # MACD histogram (-2.0 to 2.0)
    if draw(st.booleans()):
        summary["macd_histogram"] = draw(
            st.floats(min_value=-2.0, max_value=2.0, allow_nan=False, allow_infinity=False)
        )

    # Volume ratio (0-5.0)
    if draw(st.booleans()):
        summary["volume_ratio"] = draw(
            st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False)
        )

    # Volatility (0-0.2)
    if draw(st.booleans()):
        summary["volatility"] = draw(
            st.floats(min_value=0.0, max_value=0.2, allow_nan=False, allow_infinity=False)
        )

    # RSI (0-100)
    if draw(st.booleans()):
        summary["rsi"] = draw(
            st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
        )

    return summary


@st.composite
def context_scorer_configs(draw: st.DrawFn) -> ContextScorerConfig:
    """
    Generate random valid ContextScorerConfig instances for testing.

    Returns configs with all thresholds and weights in valid ranges.
    """
    return ContextScorerConfig(
        # Thresholds (0.0-1.0)
        risk_on_threshold=draw(st.floats(min_value=0.5, max_value=0.9, allow_nan=False)),
        risk_off_threshold=draw(st.floats(min_value=0.1, max_value=0.5, allow_nan=False)),
        trend_strong_threshold=draw(st.floats(min_value=0.5, max_value=0.9, allow_nan=False)),
        trend_weak_threshold=draw(st.floats(min_value=0.1, max_value=0.5, allow_nan=False)),
        sentiment_positive_threshold=draw(st.floats(min_value=0.5, max_value=0.9, allow_nan=False)),
        sentiment_negative_threshold=draw(st.floats(min_value=0.1, max_value=0.5, allow_nan=False)),
        # Weights (non-negative, will be normalized)
        ta_weight_trend=draw(st.floats(min_value=0.1, max_value=1.0, allow_nan=False)),
        onchain_weight_trend=draw(st.floats(min_value=0.1, max_value=1.0, allow_nan=False)),
        volume_weight_trend=draw(st.floats(min_value=0.1, max_value=1.0, allow_nan=False)),
        fgi_weight_risk=draw(st.floats(min_value=0.1, max_value=1.0, allow_nan=False)),
        exchange_flow_weight_risk=draw(st.floats(min_value=0.1, max_value=1.0, allow_nan=False)),
        tvl_weight_risk=draw(st.floats(min_value=0.1, max_value=1.0, allow_nan=False)),
        volatility_weight_risk=draw(st.floats(min_value=0.1, max_value=1.0, allow_nan=False)),
        social_weight_sentiment=draw(st.floats(min_value=0.1, max_value=1.0, allow_nan=False)),
        fgi_weight_sentiment=draw(st.floats(min_value=0.1, max_value=1.0, allow_nan=False)),
        news_weight_sentiment=draw(st.floats(min_value=0.1, max_value=1.0, allow_nan=False)),
    )


# =============================================================================
# Property 5: Composite scores are bounded
# =============================================================================


class TestContextScorerCompositeBounds:
    """
    Property 5: Composite scores are bounded

    *For any* valid `MarketContextSnapshot` and any valid technical summary dict,
    the `ContextScorer.compute_scores()` output SHALL have `trend_strength_score`,
    `risk_regime_score`, and `sentiment_regime_score` all within the range [0.0, 1.0].

    **Validates: Requirements 3.1, 3.2, 3.3**
    """

    @settings(max_examples=25)
    @given(
        snapshot=market_context_snapshots(),
        technical=technical_summaries(),
    )
    def test_composite_scores_are_bounded(
        self,
        snapshot: MarketContextSnapshot,
        technical: dict[str, float],
    ) -> None:
        """
        Property: For any valid inputs, ContextScorer SHALL produce scores
        within [0.0, 1.0].

        This is the core property that ensures all composite scores are
        properly bounded regardless of input values.

        **Validates: Requirements 3.1, 3.2, 3.3**
        """
        scorer = ContextScorer()
        result = scorer.compute_scores(snapshot, technical)

        # All three composite scores must be bounded
        assert 0.0 <= result.trend_strength_score <= 1.0, (
            f"trend_strength_score {result.trend_strength_score} out of bounds"
        )
        assert 0.0 <= result.risk_regime_score <= 1.0, (
            f"risk_regime_score {result.risk_regime_score} out of bounds"
        )
        assert 0.0 <= result.sentiment_regime_score <= 1.0, (
            f"sentiment_regime_score {result.sentiment_regime_score} out of bounds"
        )

    @settings(max_examples=25)
    @given(
        snapshot=market_context_snapshots(),
        technical=technical_summaries(),
        config=context_scorer_configs(),
    )
    def test_composite_scores_bounded_with_custom_config(
        self,
        snapshot: MarketContextSnapshot,
        technical: dict[str, float],
        config: ContextScorerConfig,
    ) -> None:
        """
        Property: For any valid inputs and any valid config, ContextScorer
        SHALL produce scores within [0.0, 1.0].

        This verifies that custom configurations don't break the bounds property.

        **Validates: Requirements 3.1, 3.2, 3.3**
        """
        scorer = ContextScorer(config=config)
        result = scorer.compute_scores(snapshot, technical)

        assert 0.0 <= result.trend_strength_score <= 1.0
        assert 0.0 <= result.risk_regime_score <= 1.0
        assert 0.0 <= result.sentiment_regime_score <= 1.0

    @settings(max_examples=20)
    @given(
        technical=technical_summaries(),
    )
    def test_composite_scores_bounded_with_empty_snapshot(
        self,
        technical: dict[str, float],
    ) -> None:
        """
        Property: For a snapshot with all None values, ContextScorer SHALL
        still produce bounded scores.

        This verifies graceful handling of missing data.

        **Validates: Requirements 3.1, 3.2, 3.3**
        """
        # Create snapshot with all optional fields as None
        snapshot = MarketContextSnapshot(
            timestamp=timezone.now(),
            symbol=None,
            btc_dominance=None,
            global_market_cap=None,
            total_volume_24h=None,
            active_addresses=None,
            net_exchange_flow=None,
            whale_tx_count=None,
            defi_tvl=None,
            social_sentiment_score=None,
            social_mention_count=None,
            social_buzz_score=None,
            fear_greed_index=None,
            is_stale=False,
            stale_fields=[],
            is_degraded=False,
        )

        scorer = ContextScorer()
        result = scorer.compute_scores(snapshot, technical)

        assert 0.0 <= result.trend_strength_score <= 1.0
        assert 0.0 <= result.risk_regime_score <= 1.0
        assert 0.0 <= result.sentiment_regime_score <= 1.0

    @settings(max_examples=20)
    @given(
        snapshot=market_context_snapshots(),
    )
    def test_composite_scores_bounded_with_empty_technical(
        self,
        snapshot: MarketContextSnapshot,
    ) -> None:
        """
        Property: For an empty technical summary, ContextScorer SHALL
        still produce bounded scores.

        This verifies graceful handling of missing technical data.

        **Validates: Requirements 3.1, 3.2, 3.3**
        """
        scorer = ContextScorer()
        result = scorer.compute_scores(snapshot, {})

        assert 0.0 <= result.trend_strength_score <= 1.0
        assert 0.0 <= result.risk_regime_score <= 1.0
        assert 0.0 <= result.sentiment_regime_score <= 1.0

    @settings(max_examples=20)
    @given(
        snapshot=market_context_snapshots(),
        technical=technical_summaries(),
    )
    def test_scores_are_valid_floats(
        self,
        snapshot: MarketContextSnapshot,
        technical: dict[str, float],
    ) -> None:
        """
        Property: All composite scores SHALL be valid floats (not NaN or infinity).

        This ensures scores are usable for further calculations.

        **Validates: Requirements 3.1, 3.2, 3.3**
        """
        import math

        scorer = ContextScorer()
        result = scorer.compute_scores(snapshot, technical)

        # Check all scores are valid floats
        assert isinstance(result.trend_strength_score, float)
        assert isinstance(result.risk_regime_score, float)
        assert isinstance(result.sentiment_regime_score, float)

        # Check not NaN or infinity
        assert not math.isnan(result.trend_strength_score)
        assert not math.isnan(result.risk_regime_score)
        assert not math.isnan(result.sentiment_regime_score)
        assert not math.isinf(result.trend_strength_score)
        assert not math.isinf(result.risk_regime_score)
        assert not math.isinf(result.sentiment_regime_score)

    @settings(max_examples=15)
    @given(
        snapshot=market_context_snapshots(),
        technical=technical_summaries(),
    )
    def test_regime_is_valid_enum(
        self,
        snapshot: MarketContextSnapshot,
        technical: dict[str, float],
    ) -> None:
        """
        Property: The regime field SHALL always be a valid Regime enum value.

        This ensures regime classification always produces a valid result.

        **Validates: Requirements 3.1, 3.2, 3.3**
        """
        from lib.analysis.context import Regime

        scorer = ContextScorer()
        result = scorer.compute_scores(snapshot, technical)

        # Regime must be a valid enum value
        assert isinstance(result.regime, Regime)
        assert result.regime in Regime

    @settings(max_examples=15)
    @given(
        snapshot=market_context_snapshots(),
        technical=technical_summaries(),
    )
    def test_is_degraded_matches_snapshot_staleness(
        self,
        snapshot: MarketContextSnapshot,
        technical: dict[str, float],
    ) -> None:
        """
        Property: The is_degraded field SHALL be True if snapshot is stale
        or has stale fields.

        This ensures degradation tracking is consistent.

        **Validates: Requirements 3.1, 3.2, 3.3**
        """
        scorer = ContextScorer()
        result = scorer.compute_scores(snapshot, technical)

        # If snapshot is stale or has stale fields, result should be degraded
        if snapshot.is_stale or snapshot.stale_fields:
            assert result.is_degraded is True

    @settings(max_examples=20)
    @given(
        technical=technical_summaries(),
    )
    def test_extreme_values_produce_bounded_scores(
        self,
        technical: dict[str, float],
    ) -> None:
        """
        Property: For extreme input values (at boundaries), ContextScorer
        SHALL still produce bounded scores.

        This tests edge cases with maximum/minimum values.

        **Validates: Requirements 3.1, 3.2, 3.3**
        """
        # Create snapshot with extreme values
        snapshot = MarketContextSnapshot(
            timestamp=timezone.now(),
            symbol="BTC_USDT",
            btc_dominance=100.0,  # Maximum
            global_market_cap=Decimal("1e15"),  # Very large
            total_volume_24h=Decimal("1e15"),  # Very large
            active_addresses=10_000_000,  # Maximum
            net_exchange_flow=10000.0,  # Maximum
            whale_tx_count=10000,  # Maximum
            defi_tvl=Decimal("200e9"),  # Maximum
            social_sentiment_score=1.0,  # Maximum
            social_mention_count=1000000,  # Maximum
            social_buzz_score=100.0,  # Maximum
            fear_greed_index=100,  # Maximum
            is_stale=False,
            stale_fields=[],
            is_degraded=False,
        )

        scorer = ContextScorer()
        result = scorer.compute_scores(snapshot, technical)

        assert 0.0 <= result.trend_strength_score <= 1.0
        assert 0.0 <= result.risk_regime_score <= 1.0
        assert 0.0 <= result.sentiment_regime_score <= 1.0

    @settings(max_examples=20)
    @given(
        technical=technical_summaries(),
    )
    def test_minimum_values_produce_bounded_scores(
        self,
        technical: dict[str, float],
    ) -> None:
        """
        Property: For minimum input values, ContextScorer SHALL still
        produce bounded scores.

        This tests edge cases with minimum values.

        **Validates: Requirements 3.1, 3.2, 3.3**
        """
        # Create snapshot with minimum values
        snapshot = MarketContextSnapshot(
            timestamp=timezone.now(),
            symbol="BTC_USDT",
            btc_dominance=0.0,  # Minimum
            global_market_cap=Decimal("0.0"),  # Minimum
            total_volume_24h=Decimal("0.0"),  # Minimum
            active_addresses=0,  # Minimum
            net_exchange_flow=-10000.0,  # Minimum
            whale_tx_count=0,  # Minimum
            defi_tvl=Decimal("0.0"),  # Minimum
            social_sentiment_score=-1.0,  # Minimum
            social_mention_count=0,  # Minimum
            social_buzz_score=0.0,  # Minimum
            fear_greed_index=0,  # Minimum
            is_stale=False,
            stale_fields=[],
            is_degraded=False,
        )

        scorer = ContextScorer()
        result = scorer.compute_scores(snapshot, technical)

        assert 0.0 <= result.trend_strength_score <= 1.0
        assert 0.0 <= result.risk_regime_score <= 1.0
        assert 0.0 <= result.sentiment_regime_score <= 1.0
