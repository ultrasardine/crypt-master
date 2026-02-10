"""
Property-based tests for Stale Input Handling.

Feature: market-intelligence-layer
Property 7: Stale inputs produce degraded output

These tests use the hypothesis library to verify that ContextScorer
gracefully handles stale inputs and marks output as degraded.

**Validates: Requirements 3.5**
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.core.models import MarketContextSnapshot
from lib.analysis.context import ContextScorer

# =============================================================================
# Custom Strategies for Stale Input Testing
# =============================================================================


@st.composite
def stale_market_context_snapshots(draw: st.DrawFn) -> MarketContextSnapshot:
    """
    Generate MarketContextSnapshot instances with stale data.

    Returns snapshots where either is_stale=True or stale_fields is non-empty.
    """
    # Decide whether to use is_stale or stale_fields or both
    use_is_stale = draw(st.booleans())
    use_stale_fields = draw(st.booleans())

    # Ensure at least one is True
    if not use_is_stale and not use_stale_fields:
        use_is_stale = True

    stale_fields = []
    if use_stale_fields:
        # Generate non-empty list of stale field names
        stale_fields = draw(
            st.lists(
                st.sampled_from([
                    "btc_dominance",
                    "global_market_cap",
                    "total_volume_24h",
                    "active_addresses",
                    "net_exchange_flow",
                    "whale_tx_count",
                    "defi_tvl",
                    "social_sentiment_score",
                    "social_mention_count",
                    "social_buzz_score",
                    "fear_greed_index",
                ]),
                min_size=1,
                max_size=5,
                unique=True,
            )
        )

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
        is_stale=use_is_stale,
        stale_fields=stale_fields,
        is_degraded=draw(st.booleans()),
    )
    return snapshot


@st.composite
def technical_summaries(draw: st.DrawFn) -> dict[str, float]:
    """
    Generate random technical summary dictionaries for testing.
    """
    summary = {}

    if draw(st.booleans()):
        summary["adx"] = draw(
            st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
        )

    if draw(st.booleans()):
        summary["bb_width"] = draw(
            st.floats(min_value=0.0, max_value=0.2, allow_nan=False, allow_infinity=False)
        )

    if draw(st.booleans()):
        summary["macd_histogram"] = draw(
            st.floats(min_value=-2.0, max_value=2.0, allow_nan=False, allow_infinity=False)
        )

    if draw(st.booleans()):
        summary["volume_ratio"] = draw(
            st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False)
        )

    if draw(st.booleans()):
        summary["volatility"] = draw(
            st.floats(min_value=0.0, max_value=0.2, allow_nan=False, allow_infinity=False)
        )

    return summary


# =============================================================================
# Property 7: Stale inputs produce degraded output
# =============================================================================


class TestStaleInputHandling:
    """
    Property 7: Stale inputs produce degraded output

    *For any* `MarketContextSnapshot` where `stale_fields` is non-empty,
    the `ContextScorer.compute_scores()` output SHALL have `is_degraded == True`
    and all three composite scores SHALL still be valid floats in [0.0, 1.0].

    **Validates: Requirements 3.5**
    """

    @settings(max_examples=25)
    @given(
        snapshot=stale_market_context_snapshots(),
        technical=technical_summaries(),
    )
    def test_stale_inputs_produce_degraded_output(
        self,
        snapshot: MarketContextSnapshot,
        technical: dict[str, float],
    ) -> None:
        """
        Property: For any snapshot with stale data, ContextScorer SHALL
        mark output as degraded.

        This is the core property that ensures stale data is properly tracked.

        **Validates: Requirements 3.5**
        """
        scorer = ContextScorer()
        result = scorer.compute_scores(snapshot, technical)

        # If snapshot is stale or has stale fields, result must be degraded
        if snapshot.is_stale or snapshot.stale_fields:
            assert result.is_degraded is True, (
                f"Expected is_degraded=True for stale snapshot "
                f"(is_stale={snapshot.is_stale}, stale_fields={snapshot.stale_fields})"
            )

    @settings(max_examples=25)
    @given(
        snapshot=stale_market_context_snapshots(),
        technical=technical_summaries(),
    )
    def test_stale_inputs_still_produce_valid_scores(
        self,
        snapshot: MarketContextSnapshot,
        technical: dict[str, float],
    ) -> None:
        """
        Property: For any snapshot with stale data, ContextScorer SHALL
        still produce valid bounded scores.

        This ensures graceful degradation - stale data doesn't break scoring.

        **Validates: Requirements 3.5**
        """
        scorer = ContextScorer()
        result = scorer.compute_scores(snapshot, technical)

        # All scores must still be valid and bounded
        assert 0.0 <= result.trend_strength_score <= 1.0
        assert 0.0 <= result.risk_regime_score <= 1.0
        assert 0.0 <= result.sentiment_regime_score <= 1.0

        # Scores must be valid floats (not NaN or infinity)
        import math
        assert not math.isnan(result.trend_strength_score)
        assert not math.isnan(result.risk_regime_score)
        assert not math.isnan(result.sentiment_regime_score)
        assert not math.isinf(result.trend_strength_score)
        assert not math.isinf(result.risk_regime_score)
        assert not math.isinf(result.sentiment_regime_score)

    @settings(max_examples=20)
    @given(
        technical=technical_summaries(),
    )
    def test_is_stale_true_produces_degraded_output(
        self,
        technical: dict[str, float],
    ) -> None:
        """
        Property: For any snapshot with is_stale=True, output SHALL be degraded.

        This tests the is_stale flag specifically.

        **Validates: Requirements 3.5**
        """
        # Create snapshot with is_stale=True
        snapshot = MarketContextSnapshot(
            timestamp=timezone.now(),
            symbol="BTC_USDT",
            fear_greed_index=50,
            social_sentiment_score=0.0,
            btc_dominance=50.0,
            net_exchange_flow=0.0,
            defi_tvl=Decimal("80e9"),
            is_stale=True,  # Explicitly stale
            stale_fields=[],
            is_degraded=False,
        )

        scorer = ContextScorer()
        result = scorer.compute_scores(snapshot, technical)

        assert result.is_degraded is True

    @settings(max_examples=20)
    @given(
        technical=technical_summaries(),
    )
    def test_stale_fields_produces_degraded_output(
        self,
        technical: dict[str, float],
    ) -> None:
        """
        Property: For any snapshot with non-empty stale_fields, output SHALL be degraded.

        This tests the stale_fields list specifically.

        **Validates: Requirements 3.5**
        """
        # Create snapshot with stale_fields
        snapshot = MarketContextSnapshot(
            timestamp=timezone.now(),
            symbol="BTC_USDT",
            fear_greed_index=50,
            social_sentiment_score=0.0,
            btc_dominance=50.0,
            net_exchange_flow=0.0,
            defi_tvl=Decimal("80e9"),
            is_stale=False,
            stale_fields=["fear_greed_index", "social_sentiment_score"],  # Non-empty
            is_degraded=False,
        )

        scorer = ContextScorer()
        result = scorer.compute_scores(snapshot, technical)

        assert result.is_degraded is True

    @settings(max_examples=20)
    @given(
        technical=technical_summaries(),
    )
    def test_non_stale_inputs_produce_non_degraded_output(
        self,
        technical: dict[str, float],
    ) -> None:
        """
        Property: For any snapshot with is_stale=False and empty stale_fields,
        output SHALL NOT be degraded.

        This tests the negative case - fresh data should not be marked degraded.

        **Validates: Requirements 3.5**
        """
        # Create snapshot with no staleness
        snapshot = MarketContextSnapshot(
            timestamp=timezone.now(),
            symbol="BTC_USDT",
            fear_greed_index=50,
            social_sentiment_score=0.0,
            btc_dominance=50.0,
            net_exchange_flow=0.0,
            defi_tvl=Decimal("80e9"),
            is_stale=False,  # Not stale
            stale_fields=[],  # Empty
            is_degraded=False,
        )

        scorer = ContextScorer()
        result = scorer.compute_scores(snapshot, technical)

        assert result.is_degraded is False

    @settings(max_examples=20)
    @given(
        snapshot=stale_market_context_snapshots(),
        technical=technical_summaries(),
    )
    def test_stale_inputs_produce_valid_regime(
        self,
        snapshot: MarketContextSnapshot,
        technical: dict[str, float],
    ) -> None:
        """
        Property: For any snapshot with stale data, ContextScorer SHALL
        still produce a valid regime classification.

        This ensures regime classification works even with stale data.

        **Validates: Requirements 3.5**
        """
        from lib.analysis.context import Regime

        scorer = ContextScorer()
        result = scorer.compute_scores(snapshot, technical)

        # Regime must be a valid enum value
        assert isinstance(result.regime, Regime)
        assert result.regime in Regime

    @settings(max_examples=15)
    @given(
        snapshot=stale_market_context_snapshots(),
    )
    def test_stale_inputs_with_empty_technical_still_work(
        self,
        snapshot: MarketContextSnapshot,
    ) -> None:
        """
        Property: For any stale snapshot with empty technical data,
        ContextScorer SHALL still produce valid output.

        This tests the worst case - stale snapshot AND no technical data.

        **Validates: Requirements 3.5**
        """
        scorer = ContextScorer()
        result = scorer.compute_scores(snapshot, {})

        # Must be degraded
        assert result.is_degraded is True

        # Scores must still be valid
        assert 0.0 <= result.trend_strength_score <= 1.0
        assert 0.0 <= result.risk_regime_score <= 1.0
        assert 0.0 <= result.sentiment_regime_score <= 1.0

    @settings(max_examples=15)
    @given(
        technical=technical_summaries(),
    )
    def test_all_fields_stale_still_produces_valid_output(
        self,
        technical: dict[str, float],
    ) -> None:
        """
        Property: For a snapshot where all fields are marked stale,
        ContextScorer SHALL still produce valid output.

        This tests the extreme case of complete staleness.

        **Validates: Requirements 3.5**
        """
        # Create snapshot with all fields marked stale
        snapshot = MarketContextSnapshot(
            timestamp=timezone.now(),
            symbol="BTC_USDT",
            fear_greed_index=None,
            social_sentiment_score=None,
            btc_dominance=None,
            net_exchange_flow=None,
            defi_tvl=None,
            active_addresses=None,
            whale_tx_count=None,
            social_mention_count=None,
            social_buzz_score=None,
            global_market_cap=None,
            total_volume_24h=None,
            is_stale=True,
            stale_fields=[
                "btc_dominance",
                "global_market_cap",
                "total_volume_24h",
                "active_addresses",
                "net_exchange_flow",
                "whale_tx_count",
                "defi_tvl",
                "social_sentiment_score",
                "social_mention_count",
                "social_buzz_score",
                "fear_greed_index",
            ],
            is_degraded=False,
        )

        scorer = ContextScorer()
        result = scorer.compute_scores(snapshot, technical)

        # Must be degraded
        assert result.is_degraded is True

        # Scores must still be valid (likely neutral values)
        assert 0.0 <= result.trend_strength_score <= 1.0
        assert 0.0 <= result.risk_regime_score <= 1.0
        assert 0.0 <= result.sentiment_regime_score <= 1.0

    @settings(max_examples=20)
    @given(
        snapshot=stale_market_context_snapshots(),
        technical=technical_summaries(),
    )
    def test_degraded_output_is_deterministic(
        self,
        snapshot: MarketContextSnapshot,
        technical: dict[str, float],
    ) -> None:
        """
        Property: For any stale snapshot, calling compute_scores twice
        SHALL produce the same is_degraded value.

        This ensures degradation tracking is deterministic.

        **Validates: Requirements 3.5**
        """
        scorer = ContextScorer()

        result1 = scorer.compute_scores(snapshot, technical)
        result2 = scorer.compute_scores(snapshot, technical)

        assert result1.is_degraded == result2.is_degraded
