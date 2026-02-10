"""
Property-based tests for Regime Classification Determinism.

Feature: market-intelligence-layer
Property 6: Regime classification is deterministic and consistent with thresholds

These tests use the hypothesis library to verify that regime classification
is deterministic (same inputs always produce same output) and consistent
with the documented threshold rules.

**Validates: Requirements 3.4**
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.core.models import MarketContextSnapshot
from lib.analysis.context import ContextScorer, Regime

# =============================================================================
# Custom Strategies for Regime Classification Testing
# =============================================================================


@st.composite
def market_context_snapshots_for_regime(draw: st.DrawFn) -> MarketContextSnapshot:
    """
    Generate MarketContextSnapshot instances with controlled values
    for regime classification testing.
    """
    snapshot = MarketContextSnapshot(
        symbol=draw(st.one_of(st.none(), st.just("BTC_USDT"))),
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
def technical_summaries_for_regime(draw: st.DrawFn) -> dict[str, float]:
    """
    Generate technical summary dictionaries with controlled values
    for regime classification testing.
    """
    summary = {}

    # ADX (0-100) - critical for regime classification
    if draw(st.booleans()):
        summary["adx"] = draw(
            st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
        )

    # MACD histogram (-2.0 to 2.0) - critical for regime classification
    if draw(st.booleans()):
        summary["macd_histogram"] = draw(
            st.floats(min_value=-2.0, max_value=2.0, allow_nan=False, allow_infinity=False)
        )

    # Other indicators
    if draw(st.booleans()):
        summary["bb_width"] = draw(
            st.floats(min_value=0.0, max_value=0.2, allow_nan=False, allow_infinity=False)
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
# Property 6: Regime classification is deterministic and consistent
# =============================================================================


class TestRegimeClassificationDeterminism:
    """
    Property 6: Regime classification is deterministic and consistent with thresholds

    *For any* inputs, calling _classify_regime twice with the same inputs SHALL
    return the same Regime value, and the returned regime SHALL be consistent
    with the documented threshold rules.

    **Validates: Requirements 3.4**
    """

    @settings(max_examples=25)
    @given(
        snapshot=market_context_snapshots_for_regime(),
        technical=technical_summaries_for_regime(),
    )
    def test_regime_classification_is_deterministic(
        self,
        snapshot: MarketContextSnapshot,
        technical: dict[str, float],
    ) -> None:
        """
        Property: For any inputs, calling compute_scores twice SHALL produce
        the same regime classification.

        This verifies that regime classification is deterministic.

        **Validates: Requirements 3.4**
        """
        scorer = ContextScorer()

        # Call compute_scores twice with identical inputs
        result1 = scorer.compute_scores(snapshot, technical)
        result2 = scorer.compute_scores(snapshot, technical)

        # Regime must be identical
        assert result1.regime == result2.regime, (
            f"Regime classification is not deterministic: "
            f"first call returned {result1.regime}, second call returned {result2.regime}"
        )

    @settings(max_examples=20)
    @given(
        snapshot=market_context_snapshots_for_regime(),
        technical=technical_summaries_for_regime(),
    )
    def test_regime_classification_is_consistent_with_rules(
        self,
        snapshot: MarketContextSnapshot,
        technical: dict[str, float],
    ) -> None:
        """
        Property: For any inputs, the returned regime SHALL be consistent
        with the documented threshold rules.

        This verifies that regime classification follows the specification.

        **Validates: Requirements 3.4**
        """
        scorer = ContextScorer()
        result = scorer.compute_scores(snapshot, technical)

        # Extract values for rule checking
        fgi = snapshot.fear_greed_index
        social_sentiment = snapshot.social_sentiment_score
        btc_dominance = snapshot.btc_dominance
        net_exchange_flow = snapshot.net_exchange_flow
        adx = technical.get("adx")
        macd_histogram = technical.get("macd_histogram")
        trend_strength_100 = result.trend_strength_score * 100.0

        # Verify regime is consistent with rules
        if result.regime == Regime.RISK_ON:
            # RISK_ON: FGI > 60 AND social sentiment > 0.3 AND BTC dominance < 50
            assert fgi is not None and fgi > 60, "RISK_ON requires FGI > 60"
            assert social_sentiment is not None and social_sentiment > 0.3, (
                "RISK_ON requires social sentiment > 0.3"
            )
            assert btc_dominance is not None and btc_dominance < 50.0, (
                "RISK_ON requires BTC dominance < 50"
            )

        elif result.regime == Regime.RISK_OFF:
            # RISK_OFF: FGI < 30 AND net exchange flow positive
            assert fgi is not None and fgi < 30, "RISK_OFF requires FGI < 30"
            assert net_exchange_flow is not None and net_exchange_flow > 0, (
                "RISK_OFF requires positive net exchange flow"
            )

        elif result.regime == Regime.RANGE_BOUND:
            # RANGE_BOUND: ADX < 20 AND trend_strength < 30
            assert adx is not None and adx < 20, "RANGE_BOUND requires ADX < 20"
            assert trend_strength_100 < 30, "RANGE_BOUND requires trend_strength < 30"

        elif result.regime == Regime.TRENDING_UP:
            # TRENDING_UP: ADX > 25 AND MACD histogram positive AND trend_strength > 60
            assert adx is not None and adx > 25, "TRENDING_UP requires ADX > 25"
            assert macd_histogram is not None and macd_histogram > 0, (
                "TRENDING_UP requires positive MACD histogram"
            )
            assert trend_strength_100 > 60, "TRENDING_UP requires trend_strength > 60"

        elif result.regime == Regime.TRENDING_DOWN:
            # TRENDING_DOWN: ADX > 25 AND MACD histogram negative AND trend_strength > 60
            assert adx is not None and adx > 25, "TRENDING_DOWN requires ADX > 25"
            assert macd_histogram is not None and macd_histogram < 0, (
                "TRENDING_DOWN requires negative MACD histogram"
            )
            assert trend_strength_100 > 60, "TRENDING_DOWN requires trend_strength > 60"

        elif result.regime == Regime.UNKNOWN:
            # UNKNOWN is the fallback when no other conditions match
            # No specific assertions needed
            pass

    def test_risk_on_regime_conditions(self) -> None:
        """
        Property: When RISK_ON conditions are met, regime SHALL be RISK_ON.

        This tests the specific RISK_ON rule.

        **Validates: Requirements 3.4**
        """
        # Create snapshot with RISK_ON conditions
        snapshot = MarketContextSnapshot(
            timestamp=timezone.now(),
            symbol="BTC_USDT",
            fear_greed_index=70,  # > 60
            social_sentiment_score=0.5,  # > 0.3
            btc_dominance=40.0,  # < 50
            net_exchange_flow=None,
            defi_tvl=None,
            is_stale=False,
            stale_fields=[],
            is_degraded=False,
        )

        technical = {
            "adx": 15.0,
            "macd_histogram": 0.1,
        }

        scorer = ContextScorer()
        result = scorer.compute_scores(snapshot, technical)

        assert result.regime == Regime.RISK_ON

    def test_risk_off_regime_conditions(self) -> None:
        """
        Property: When RISK_OFF conditions are met, regime SHALL be RISK_OFF.

        This tests the specific RISK_OFF rule.

        **Validates: Requirements 3.4**
        """
        # Create snapshot with RISK_OFF conditions
        snapshot = MarketContextSnapshot(
            timestamp=timezone.now(),
            symbol="BTC_USDT",
            fear_greed_index=20,  # < 30
            social_sentiment_score=-0.5,
            btc_dominance=60.0,
            net_exchange_flow=100.0,  # > 0 (positive)
            defi_tvl=Decimal("50e9"),
            is_stale=False,
            stale_fields=[],
            is_degraded=False,
        )

        technical = {
            "adx": 15.0,
            "macd_histogram": -0.1,
        }

        scorer = ContextScorer()
        result = scorer.compute_scores(snapshot, technical)

        assert result.regime == Regime.RISK_OFF

    def test_range_bound_regime_conditions(self) -> None:
        """
        Property: When RANGE_BOUND conditions are met, regime SHALL be RANGE_BOUND.

        This tests the specific RANGE_BOUND rule.

        **Validates: Requirements 3.4**
        """
        # Create snapshot with RANGE_BOUND conditions
        snapshot = MarketContextSnapshot(
            timestamp=timezone.now(),
            symbol="BTC_USDT",
            fear_greed_index=50,
            social_sentiment_score=0.0,
            btc_dominance=50.0,
            net_exchange_flow=-50.0,
            defi_tvl=Decimal("80e9"),
            is_stale=False,
            stale_fields=[],
            is_degraded=False,
        )

        # Low ADX and low trend strength
        technical = {
            "adx": 15.0,  # < 20
            "macd_histogram": 0.0,
            "bb_width": 0.01,  # Low volatility
        }

        scorer = ContextScorer()
        result = scorer.compute_scores(snapshot, technical)

        assert result.regime == Regime.RANGE_BOUND

    def test_trending_up_regime_conditions(self) -> None:
        """
        Property: When TRENDING_UP conditions are met, regime SHALL be TRENDING_UP.

        This tests the specific TRENDING_UP rule.

        **Validates: Requirements 3.4**
        """
        # Create snapshot with TRENDING_UP conditions
        snapshot = MarketContextSnapshot(
            timestamp=timezone.now(),
            symbol="BTC_USDT",
            fear_greed_index=50,
            social_sentiment_score=0.2,
            btc_dominance=45.0,
            net_exchange_flow=-100.0,
            defi_tvl=Decimal("100e9"),
            active_addresses=800_000,  # High activity
            is_stale=False,
            stale_fields=[],
            is_degraded=False,
        )

        # Strong trend indicators
        technical = {
            "adx": 35.0,  # > 25
            "macd_histogram": 0.5,  # > 0 (positive)
            "bb_width": 0.08,  # Wide bands
            "volume_ratio": 1.5,
        }

        scorer = ContextScorer()
        result = scorer.compute_scores(snapshot, technical)

        assert result.regime == Regime.TRENDING_UP

    def test_trending_down_regime_conditions(self) -> None:
        """
        Property: When TRENDING_DOWN conditions are met, regime SHALL be TRENDING_DOWN.

        This tests the specific TRENDING_DOWN rule.

        **Validates: Requirements 3.4**
        """
        # Create snapshot with TRENDING_DOWN conditions
        snapshot = MarketContextSnapshot(
            timestamp=timezone.now(),
            symbol="BTC_USDT",
            fear_greed_index=50,
            social_sentiment_score=-0.2,
            btc_dominance=55.0,
            net_exchange_flow=50.0,
            defi_tvl=Decimal("70e9"),
            active_addresses=600_000,
            is_stale=False,
            stale_fields=[],
            is_degraded=False,
        )

        # Strong downtrend indicators
        technical = {
            "adx": 40.0,  # > 25
            "macd_histogram": -0.5,  # < 0 (negative)
            "bb_width": 0.09,  # Wide bands
            "volume_ratio": 1.8,
        }

        scorer = ContextScorer()
        result = scorer.compute_scores(snapshot, technical)

        assert result.regime == Regime.TRENDING_DOWN

    def test_unknown_regime_when_insufficient_data(self) -> None:
        """
        Property: When insufficient data is available, regime SHALL be UNKNOWN.

        This tests the fallback to UNKNOWN.

        **Validates: Requirements 3.4**
        """
        # Create snapshot with minimal data
        snapshot = MarketContextSnapshot(
            timestamp=timezone.now(),
            symbol="BTC_USDT",
            fear_greed_index=None,
            social_sentiment_score=None,
            btc_dominance=None,
            net_exchange_flow=None,
            defi_tvl=None,
            is_stale=False,
            stale_fields=[],
            is_degraded=False,
        )

        technical = {}  # No technical data

        scorer = ContextScorer()
        result = scorer.compute_scores(snapshot, technical)

        assert result.regime == Regime.UNKNOWN

    @settings(max_examples=20)
    @given(
        snapshot=market_context_snapshots_for_regime(),
        technical=technical_summaries_for_regime(),
    )
    def test_regime_is_always_valid_enum(
        self,
        snapshot: MarketContextSnapshot,
        technical: dict[str, float],
    ) -> None:
        """
        Property: For any inputs, regime SHALL always be a valid Regime enum value.

        This ensures no invalid regime values are produced.

        **Validates: Requirements 3.4**
        """
        scorer = ContextScorer()
        result = scorer.compute_scores(snapshot, technical)

        # Regime must be a valid enum value
        assert isinstance(result.regime, Regime)
        assert result.regime in [
            Regime.RISK_ON,
            Regime.RISK_OFF,
            Regime.RANGE_BOUND,
            Regime.TRENDING_UP,
            Regime.TRENDING_DOWN,
            Regime.UNKNOWN,
        ]
