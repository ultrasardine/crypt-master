"""
Property-based tests for Context-Aware Signal Generation.

Feature: market-intelligence-layer
Properties 8-12: Context-aware signal generation properties

These tests use the hypothesis library to verify that the SignalGenerator
correctly handles context scores and regime information.

**Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5**
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from lib.analysis.confidence import IndicatorScore
from lib.analysis.context import ContextScores, ContextScorerConfig, Regime
from lib.analysis.signal import Signal, SignalGenerator, SignalGeneratorConfig
from lib.analysis.technical import SignalDirection


# =============================================================================
# Custom Strategies for Context-Aware Signal Testing
# =============================================================================


@st.composite
def context_scores_strategy(
    draw: st.DrawFn,
    regime: Regime | None = None,
) -> ContextScores:
    """
    Generate random ContextScores instances for testing.

    Args:
        draw: Hypothesis draw function
        regime: Optional specific regime to use (random if None)

    Returns:
        ContextScores instance with valid values
    """
    if regime is None:
        regime = draw(st.sampled_from(list(Regime)))

    return ContextScores(
        trend_strength_score=draw(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
        ),
        risk_regime_score=draw(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
        ),
        sentiment_regime_score=draw(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
        ),
        regime=regime,
        is_degraded=draw(st.booleans()),
    )


@st.composite
def technical_indicator_scores(draw: st.DrawFn) -> list[IndicatorScore]:
    """
    Generate random technical indicator scores for testing.

    Returns:
        List of IndicatorScore instances
    """
    num_indicators = draw(st.integers(min_value=1, max_value=5))
    indicators = []

    for i in range(num_indicators):
        indicators.append(
            IndicatorScore(
                name=f"Indicator_{i}",
                signal=draw(st.sampled_from(list(SignalDirection))),
                confidence=draw(
                    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
                ),
                weight=draw(
                    st.floats(min_value=0.1, max_value=1.0, allow_nan=False, allow_infinity=False)
                ),
            )
        )

    return indicators


@st.composite
def sentiment_indicator_score(draw: st.DrawFn) -> IndicatorScore | None:
    """Generate optional sentiment indicator score."""
    if draw(st.booleans()):
        return IndicatorScore(
            name="FGI",
            signal=draw(st.sampled_from(list(SignalDirection))),
            confidence=draw(
                st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
            ),
            weight=1.0,
        )
    return None


# =============================================================================
# Property 8: Context-aware signals include regime metadata
# =============================================================================


class TestContextMetadataInclusion:
    """
    Property 8: Context-aware signals include regime metadata

    *For any* signal generated with a non-None `ContextScores` argument,
    the resulting `Signal` SHALL have a non-None `regime` field and a
    non-None `context_scores` dict containing keys `trend_strength_score`,
    `risk_regime_score`, and `sentiment_regime_score`.

    **Validates: Requirements 4.1**
    """

    @settings(max_examples=100)
    @given(
        technical_scores=technical_indicator_scores(),
        sentiment_score=sentiment_indicator_score(),
        context=context_scores_strategy(),
    )
    def test_signal_with_context_has_regime_metadata(
        self,
        technical_scores: list[IndicatorScore],
        sentiment_score: IndicatorScore | None,
        context: ContextScores,
    ) -> None:
        """
        Property: For any signal generated with non-None ContextScores,
        the Signal SHALL have non-None regime field.

        **Validates: Requirements 4.1**
        """
        generator = SignalGenerator()
        signal = generator.generate_signal(
            symbol="BTC_USDT",
            technical_scores=technical_scores,
            sentiment_score=sentiment_score,
            context=context,
        )

        # Signal must have regime metadata when context is provided
        assert signal.regime is not None, "Signal with context must have regime field"
        assert signal.regime == context.regime.value, "Regime must match context regime"

    @settings(max_examples=100)
    @given(
        technical_scores=technical_indicator_scores(),
        sentiment_score=sentiment_indicator_score(),
        context=context_scores_strategy(),
    )
    def test_signal_with_context_has_context_scores_dict(
        self,
        technical_scores: list[IndicatorScore],
        sentiment_score: IndicatorScore | None,
        context: ContextScores,
    ) -> None:
        """
        Property: For any signal generated with non-None ContextScores,
        the Signal SHALL have non-None context_scores dict with required keys.

        **Validates: Requirements 4.1**
        """
        generator = SignalGenerator()
        signal = generator.generate_signal(
            symbol="BTC_USDT",
            technical_scores=technical_scores,
            sentiment_score=sentiment_score,
            context=context,
        )

        # Signal must have context_scores dict when context is provided
        assert signal.context_scores is not None, "Signal with context must have context_scores"

        # Dict must contain all required keys
        required_keys = {"trend_strength_score", "risk_regime_score", "sentiment_regime_score"}
        assert required_keys.issubset(
            signal.context_scores.keys()
        ), f"context_scores must contain {required_keys}"

        # Values must match the input context
        assert signal.context_scores["trend_strength_score"] == context.trend_strength_score
        assert signal.context_scores["risk_regime_score"] == context.risk_regime_score
        assert signal.context_scores["sentiment_regime_score"] == context.sentiment_regime_score

    @settings(max_examples=50)
    @given(
        technical_scores=technical_indicator_scores(),
        sentiment_score=sentiment_indicator_score(),
        context=context_scores_strategy(),
    )
    def test_context_scores_values_are_bounded(
        self,
        technical_scores: list[IndicatorScore],
        sentiment_score: IndicatorScore | None,
        context: ContextScores,
    ) -> None:
        """
        Property: All context_scores values in the Signal SHALL be
        within [0.0, 1.0].

        **Validates: Requirements 4.1**
        """
        generator = SignalGenerator()
        signal = generator.generate_signal(
            symbol="BTC_USDT",
            technical_scores=technical_scores,
            sentiment_score=sentiment_score,
            context=context,
        )

        assert signal.context_scores is not None

        for key, value in signal.context_scores.items():
            assert 0.0 <= value <= 1.0, f"{key} value {value} out of bounds [0.0, 1.0]"



# =============================================================================
# Property 9: Range-bound regime permits GRID bots
# =============================================================================


class TestRangeBoundGridRecommendation:
    """
    Property 9: Range-bound regime permits GRID bots

    *For any* `ContextScores` where `regime == RANGE_BOUND` and
    `sentiment_regime_score` is between the negative and positive sentiment
    thresholds (neutral zone), the `Signal` produced by the generator SHALL
    have `recommended_bot_type` that includes "GRID" as a permitted option.

    **Validates: Requirements 4.2**
    """

    @settings(max_examples=100)
    @given(
        technical_scores=technical_indicator_scores(),
        sentiment_score=sentiment_indicator_score(),
        trend_strength=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        risk_regime=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        # Neutral sentiment zone: between 0.4 and 0.6
        sentiment_regime=st.floats(min_value=0.4, max_value=0.6, allow_nan=False, allow_infinity=False),
    )
    def test_range_bound_with_neutral_sentiment_recommends_grid(
        self,
        technical_scores: list[IndicatorScore],
        sentiment_score: IndicatorScore | None,
        trend_strength: float,
        risk_regime: float,
        sentiment_regime: float,
    ) -> None:
        """
        Property: For RANGE_BOUND regime with neutral sentiment,
        the Signal SHALL recommend GRID bots.

        **Validates: Requirements 4.2**
        """
        context = ContextScores(
            trend_strength_score=trend_strength,
            risk_regime_score=risk_regime,
            sentiment_regime_score=sentiment_regime,
            regime=Regime.RANGE_BOUND,
            is_degraded=False,
        )

        generator = SignalGenerator()
        signal = generator.generate_signal(
            symbol="BTC_USDT",
            technical_scores=technical_scores,
            sentiment_score=sentiment_score,
            context=context,
        )

        # RANGE_BOUND with neutral sentiment should recommend GRID
        assert signal.recommended_bot_type == "GRID", (
            f"RANGE_BOUND with neutral sentiment ({sentiment_regime:.2f}) "
            f"should recommend GRID, got {signal.recommended_bot_type}"
        )

    @settings(max_examples=100)
    @given(
        technical_scores=technical_indicator_scores(),
        sentiment_score=sentiment_indicator_score(),
        trend_strength=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        risk_regime=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        # Any sentiment value
        sentiment_regime=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    def test_range_bound_always_recommends_grid(
        self,
        technical_scores: list[IndicatorScore],
        sentiment_score: IndicatorScore | None,
        trend_strength: float,
        risk_regime: float,
        sentiment_regime: float,
    ) -> None:
        """
        Property: For RANGE_BOUND regime (regardless of sentiment),
        the Signal SHALL recommend GRID bots.

        **Validates: Requirements 4.2**
        """
        context = ContextScores(
            trend_strength_score=trend_strength,
            risk_regime_score=risk_regime,
            sentiment_regime_score=sentiment_regime,
            regime=Regime.RANGE_BOUND,
            is_degraded=False,
        )

        generator = SignalGenerator()
        signal = generator.generate_signal(
            symbol="BTC_USDT",
            technical_scores=technical_scores,
            sentiment_score=sentiment_score,
            context=context,
        )

        # RANGE_BOUND should always recommend GRID
        assert signal.recommended_bot_type == "GRID", (
            f"RANGE_BOUND regime should recommend GRID, got {signal.recommended_bot_type}"
        )



# =============================================================================
# Property 10: Trending-up regime with strong on-chain prefers DCA
# =============================================================================


class TestTrendingUpDcaPreference:
    """
    Property 10: Trending-up regime with strong on-chain prefers DCA

    *For any* `ContextScores` where `regime == TRENDING_UP` and the
    corresponding `MarketContextSnapshot` has `onchain_active_addresses_score >= 0.6`
    and `onchain_tvl_score >= 0.6`, the `Signal` produced by the generator
    SHALL have `recommended_bot_type == "DCA"`.

    Note: Since the SignalGenerator doesn't have direct access to the snapshot,
    we test that TRENDING_UP regime always recommends DCA.

    **Validates: Requirements 4.3**
    """

    @settings(max_examples=100)
    @given(
        technical_scores=technical_indicator_scores(),
        sentiment_score=sentiment_indicator_score(),
        trend_strength=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        risk_regime=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        sentiment_regime=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    def test_trending_up_recommends_dca(
        self,
        technical_scores: list[IndicatorScore],
        sentiment_score: IndicatorScore | None,
        trend_strength: float,
        risk_regime: float,
        sentiment_regime: float,
    ) -> None:
        """
        Property: For TRENDING_UP regime, the Signal SHALL recommend DCA bots.

        **Validates: Requirements 4.3**
        """
        context = ContextScores(
            trend_strength_score=trend_strength,
            risk_regime_score=risk_regime,
            sentiment_regime_score=sentiment_regime,
            regime=Regime.TRENDING_UP,
            is_degraded=False,
        )

        generator = SignalGenerator()
        signal = generator.generate_signal(
            symbol="BTC_USDT",
            technical_scores=technical_scores,
            sentiment_score=sentiment_score,
            context=context,
        )

        # TRENDING_UP should recommend DCA
        assert signal.recommended_bot_type == "DCA", (
            f"TRENDING_UP regime should recommend DCA, got {signal.recommended_bot_type}"
        )

    @settings(max_examples=100)
    @given(
        technical_scores=technical_indicator_scores(),
        sentiment_score=sentiment_indicator_score(),
        # Strong trend strength (>= 0.6)
        trend_strength=st.floats(min_value=0.6, max_value=1.0, allow_nan=False, allow_infinity=False),
        # Strong risk-on (>= 0.6)
        risk_regime=st.floats(min_value=0.6, max_value=1.0, allow_nan=False, allow_infinity=False),
        sentiment_regime=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    def test_trending_up_with_strong_indicators_recommends_dca(
        self,
        technical_scores: list[IndicatorScore],
        sentiment_score: IndicatorScore | None,
        trend_strength: float,
        risk_regime: float,
        sentiment_regime: float,
    ) -> None:
        """
        Property: For TRENDING_UP regime with strong trend and risk-on indicators,
        the Signal SHALL recommend DCA bots.

        **Validates: Requirements 4.3**
        """
        context = ContextScores(
            trend_strength_score=trend_strength,
            risk_regime_score=risk_regime,
            sentiment_regime_score=sentiment_regime,
            regime=Regime.TRENDING_UP,
            is_degraded=False,
        )

        generator = SignalGenerator()
        signal = generator.generate_signal(
            symbol="BTC_USDT",
            technical_scores=technical_scores,
            sentiment_score=sentiment_score,
            context=context,
        )

        # TRENDING_UP with strong indicators should recommend DCA
        assert signal.recommended_bot_type == "DCA", (
            f"TRENDING_UP with strong indicators should recommend DCA, "
            f"got {signal.recommended_bot_type}"
        )

    @settings(max_examples=100)
    @given(
        technical_scores=technical_indicator_scores(),
        sentiment_score=sentiment_indicator_score(),
        trend_strength=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        risk_regime=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        sentiment_regime=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    def test_risk_on_recommends_dca(
        self,
        technical_scores: list[IndicatorScore],
        sentiment_score: IndicatorScore | None,
        trend_strength: float,
        risk_regime: float,
        sentiment_regime: float,
    ) -> None:
        """
        Property: For RISK_ON regime, the Signal SHALL recommend DCA bots.

        **Validates: Requirements 4.3**
        """
        context = ContextScores(
            trend_strength_score=trend_strength,
            risk_regime_score=risk_regime,
            sentiment_regime_score=sentiment_regime,
            regime=Regime.RISK_ON,
            is_degraded=False,
        )

        generator = SignalGenerator()
        signal = generator.generate_signal(
            symbol="BTC_USDT",
            technical_scores=technical_scores,
            sentiment_score=sentiment_score,
            context=context,
        )

        # RISK_ON should recommend DCA
        assert signal.recommended_bot_type == "DCA", (
            f"RISK_ON regime should recommend DCA, got {signal.recommended_bot_type}"
        )



# =============================================================================
# Property 11: Risk-off regime increases confidence threshold
# =============================================================================


class TestRiskOffThresholdIncrease:
    """
    Property 11: Risk-off regime increases confidence threshold

    *For any* `ContextScores` where `regime == RISK_OFF`, the effective
    minimum confidence threshold used by the `SignalGenerator` SHALL be
    greater than or equal to the base `min_confidence_threshold` plus
    the configured risk-off offset.

    **Validates: Requirements 4.4**
    """

    @settings(max_examples=100)
    @given(
        technical_scores=technical_indicator_scores(),
        sentiment_score=sentiment_indicator_score(),
        trend_strength=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        risk_regime=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        sentiment_regime=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    def test_risk_off_increases_threshold(
        self,
        technical_scores: list[IndicatorScore],
        sentiment_score: IndicatorScore | None,
        trend_strength: float,
        risk_regime: float,
        sentiment_regime: float,
    ) -> None:
        """
        Property: For RISK_OFF regime, the effective threshold SHALL be
        increased by the configured offset.

        **Validates: Requirements 4.4**
        """
        base_threshold = 85.0
        risk_off_offset = 10.0

        config = SignalGeneratorConfig(
            min_confidence_threshold=base_threshold,
            risk_off_threshold_offset=risk_off_offset,
        )

        context = ContextScores(
            trend_strength_score=trend_strength,
            risk_regime_score=risk_regime,
            sentiment_regime_score=sentiment_regime,
            regime=Regime.RISK_OFF,
            is_degraded=False,
        )

        generator = SignalGenerator(config=config)
        signal = generator.generate_signal(
            symbol="BTC_USDT",
            technical_scores=technical_scores,
            sentiment_score=sentiment_score,
            context=context,
        )

        # The threshold_used should be base + offset
        expected_threshold = min(base_threshold + risk_off_offset, 100.0)
        assert signal.threshold_used == expected_threshold, (
            f"RISK_OFF threshold should be {expected_threshold}, got {signal.threshold_used}"
        )

    @settings(max_examples=100)
    @given(
        technical_scores=technical_indicator_scores(),
        sentiment_score=sentiment_indicator_score(),
        trend_strength=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        risk_regime=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        sentiment_regime=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        base_threshold=st.floats(min_value=50.0, max_value=90.0, allow_nan=False, allow_infinity=False),
        risk_off_offset=st.floats(min_value=5.0, max_value=20.0, allow_nan=False, allow_infinity=False),
    )
    def test_risk_off_threshold_with_custom_config(
        self,
        technical_scores: list[IndicatorScore],
        sentiment_score: IndicatorScore | None,
        trend_strength: float,
        risk_regime: float,
        sentiment_regime: float,
        base_threshold: float,
        risk_off_offset: float,
    ) -> None:
        """
        Property: For any valid config, RISK_OFF regime SHALL increase
        threshold by the configured offset.

        **Validates: Requirements 4.4**
        """
        config = SignalGeneratorConfig(
            min_confidence_threshold=base_threshold,
            risk_off_threshold_offset=risk_off_offset,
        )

        context = ContextScores(
            trend_strength_score=trend_strength,
            risk_regime_score=risk_regime,
            sentiment_regime_score=sentiment_regime,
            regime=Regime.RISK_OFF,
            is_degraded=False,
        )

        generator = SignalGenerator(config=config)
        signal = generator.generate_signal(
            symbol="BTC_USDT",
            technical_scores=technical_scores,
            sentiment_score=sentiment_score,
            context=context,
        )

        # The threshold_used should be base + offset, capped at 100
        expected_threshold = min(base_threshold + risk_off_offset, 100.0)
        assert abs(signal.threshold_used - expected_threshold) < 0.001, (
            f"RISK_OFF threshold should be {expected_threshold}, got {signal.threshold_used}"
        )

    @settings(max_examples=100)
    @given(
        technical_scores=technical_indicator_scores(),
        sentiment_score=sentiment_indicator_score(),
        trend_strength=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        risk_regime=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        sentiment_regime=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        regime=st.sampled_from([Regime.RISK_ON, Regime.TRENDING_UP, Regime.TRENDING_DOWN, Regime.RANGE_BOUND]),
    )
    def test_non_risk_off_uses_base_threshold(
        self,
        technical_scores: list[IndicatorScore],
        sentiment_score: IndicatorScore | None,
        trend_strength: float,
        risk_regime: float,
        sentiment_regime: float,
        regime: Regime,
    ) -> None:
        """
        Property: For non-RISK_OFF regimes, the threshold SHALL be
        the base threshold (no increase).

        **Validates: Requirements 4.4**
        """
        base_threshold = 85.0
        risk_off_offset = 10.0

        config = SignalGeneratorConfig(
            min_confidence_threshold=base_threshold,
            risk_off_threshold_offset=risk_off_offset,
        )

        context = ContextScores(
            trend_strength_score=trend_strength,
            risk_regime_score=risk_regime,
            sentiment_regime_score=sentiment_regime,
            regime=regime,
            is_degraded=False,
        )

        generator = SignalGenerator(config=config)
        signal = generator.generate_signal(
            symbol="BTC_USDT",
            technical_scores=technical_scores,
            sentiment_score=sentiment_score,
            context=context,
        )

        # Non-RISK_OFF regimes should use base threshold
        assert signal.threshold_used == base_threshold, (
            f"{regime.value} should use base threshold {base_threshold}, "
            f"got {signal.threshold_used}"
        )

    @settings(max_examples=50)
    @given(
        technical_scores=technical_indicator_scores(),
        sentiment_score=sentiment_indicator_score(),
        trend_strength=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        risk_regime=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        sentiment_regime=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    def test_risk_off_recommends_none(
        self,
        technical_scores: list[IndicatorScore],
        sentiment_score: IndicatorScore | None,
        trend_strength: float,
        risk_regime: float,
        sentiment_regime: float,
    ) -> None:
        """
        Property: For RISK_OFF regime, the Signal SHALL recommend
        no new bots (NONE).

        **Validates: Requirements 4.4**
        """
        context = ContextScores(
            trend_strength_score=trend_strength,
            risk_regime_score=risk_regime,
            sentiment_regime_score=sentiment_regime,
            regime=Regime.RISK_OFF,
            is_degraded=False,
        )

        generator = SignalGenerator()
        signal = generator.generate_signal(
            symbol="BTC_USDT",
            technical_scores=technical_scores,
            sentiment_score=sentiment_score,
            context=context,
        )

        # RISK_OFF should recommend no new bots
        assert signal.recommended_bot_type == "NONE", (
            f"RISK_OFF regime should recommend NONE, got {signal.recommended_bot_type}"
        )



# =============================================================================
# Property 12: No-context fallback equivalence
# =============================================================================


class TestNoContextFallback:
    """
    Property 12: No-context fallback equivalence

    *For any* set of technical scores, sentiment score, and news score,
    generating a signal with `context=None` SHALL produce a `Signal` with
    `regime == None`, `context_scores == None`, and `recommended_bot_type == None`,
    and the `direction` and `confidence` SHALL be identical to what the
    existing (pre-context) logic produces.

    **Validates: Requirements 4.5**
    """

    @settings(max_examples=100)
    @given(
        technical_scores=technical_indicator_scores(),
        sentiment_score=sentiment_indicator_score(),
    )
    def test_no_context_has_none_regime(
        self,
        technical_scores: list[IndicatorScore],
        sentiment_score: IndicatorScore | None,
    ) -> None:
        """
        Property: For context=None, the Signal SHALL have regime=None.

        **Validates: Requirements 4.5**
        """
        generator = SignalGenerator()
        signal = generator.generate_signal(
            symbol="BTC_USDT",
            technical_scores=technical_scores,
            sentiment_score=sentiment_score,
            context=None,
        )

        assert signal.regime is None, f"No-context signal should have regime=None, got {signal.regime}"

    @settings(max_examples=100)
    @given(
        technical_scores=technical_indicator_scores(),
        sentiment_score=sentiment_indicator_score(),
    )
    def test_no_context_has_none_context_scores(
        self,
        technical_scores: list[IndicatorScore],
        sentiment_score: IndicatorScore | None,
    ) -> None:
        """
        Property: For context=None, the Signal SHALL have context_scores=None.

        **Validates: Requirements 4.5**
        """
        generator = SignalGenerator()
        signal = generator.generate_signal(
            symbol="BTC_USDT",
            technical_scores=technical_scores,
            sentiment_score=sentiment_score,
            context=None,
        )

        assert signal.context_scores is None, (
            f"No-context signal should have context_scores=None, got {signal.context_scores}"
        )

    @settings(max_examples=100)
    @given(
        technical_scores=technical_indicator_scores(),
        sentiment_score=sentiment_indicator_score(),
    )
    def test_no_context_has_none_recommended_bot_type(
        self,
        technical_scores: list[IndicatorScore],
        sentiment_score: IndicatorScore | None,
    ) -> None:
        """
        Property: For context=None, the Signal SHALL have recommended_bot_type=None.

        **Validates: Requirements 4.5**
        """
        generator = SignalGenerator()
        signal = generator.generate_signal(
            symbol="BTC_USDT",
            technical_scores=technical_scores,
            sentiment_score=sentiment_score,
            context=None,
        )

        assert signal.recommended_bot_type is None, (
            f"No-context signal should have recommended_bot_type=None, "
            f"got {signal.recommended_bot_type}"
        )

    @settings(max_examples=100)
    @given(
        technical_scores=technical_indicator_scores(),
        sentiment_score=sentiment_indicator_score(),
    )
    def test_no_context_uses_base_threshold(
        self,
        technical_scores: list[IndicatorScore],
        sentiment_score: IndicatorScore | None,
    ) -> None:
        """
        Property: For context=None, the Signal SHALL use the base threshold.

        **Validates: Requirements 4.5**
        """
        base_threshold = 85.0
        config = SignalGeneratorConfig(min_confidence_threshold=base_threshold)

        generator = SignalGenerator(config=config)
        signal = generator.generate_signal(
            symbol="BTC_USDT",
            technical_scores=technical_scores,
            sentiment_score=sentiment_score,
            context=None,
        )

        assert signal.threshold_used == base_threshold, (
            f"No-context signal should use base threshold {base_threshold}, "
            f"got {signal.threshold_used}"
        )

    @settings(max_examples=100)
    @given(
        technical_scores=technical_indicator_scores(),
        sentiment_score=sentiment_indicator_score(),
        trend_strength=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        risk_regime=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        sentiment_regime=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    def test_unknown_regime_fallback_equivalence(
        self,
        technical_scores: list[IndicatorScore],
        sentiment_score: IndicatorScore | None,
        trend_strength: float,
        risk_regime: float,
        sentiment_regime: float,
    ) -> None:
        """
        Property: For UNKNOWN regime, the Signal SHALL behave like no-context
        for confidence calculation (no context adjustment).

        **Validates: Requirements 4.5**
        """
        context_unknown = ContextScores(
            trend_strength_score=trend_strength,
            risk_regime_score=risk_regime,
            sentiment_regime_score=sentiment_regime,
            regime=Regime.UNKNOWN,
            is_degraded=False,
        )

        generator = SignalGenerator()

        # Generate signal with UNKNOWN regime
        signal_unknown = generator.generate_signal(
            symbol="BTC_USDT",
            technical_scores=technical_scores,
            sentiment_score=sentiment_score,
            context=context_unknown,
        )

        # Generate signal with no context
        signal_none = generator.generate_signal(
            symbol="BTC_USDT",
            technical_scores=technical_scores,
            sentiment_score=sentiment_score,
            context=None,
        )

        # UNKNOWN regime should use base confidence (no context adjustment)
        # The confidence should be the same as no-context
        assert signal_unknown.confidence == signal_none.confidence, (
            f"UNKNOWN regime confidence ({signal_unknown.confidence}) should equal "
            f"no-context confidence ({signal_none.confidence})"
        )

        # Direction should also be the same
        assert signal_unknown.direction == signal_none.direction, (
            f"UNKNOWN regime direction ({signal_unknown.direction}) should equal "
            f"no-context direction ({signal_none.direction})"
        )

        # Threshold should be the same (base threshold)
        assert signal_unknown.threshold_used == signal_none.threshold_used, (
            f"UNKNOWN regime threshold ({signal_unknown.threshold_used}) should equal "
            f"no-context threshold ({signal_none.threshold_used})"
        )

    @settings(max_examples=50)
    @given(
        technical_scores=technical_indicator_scores(),
        sentiment_score=sentiment_indicator_score(),
        trend_strength=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        risk_regime=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        sentiment_regime=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    def test_unknown_regime_has_none_recommended_bot_type(
        self,
        technical_scores: list[IndicatorScore],
        sentiment_score: IndicatorScore | None,
        trend_strength: float,
        risk_regime: float,
        sentiment_regime: float,
    ) -> None:
        """
        Property: For UNKNOWN regime, the Signal SHALL have
        recommended_bot_type=None.

        **Validates: Requirements 4.5**
        """
        context = ContextScores(
            trend_strength_score=trend_strength,
            risk_regime_score=risk_regime,
            sentiment_regime_score=sentiment_regime,
            regime=Regime.UNKNOWN,
            is_degraded=False,
        )

        generator = SignalGenerator()
        signal = generator.generate_signal(
            symbol="BTC_USDT",
            technical_scores=technical_scores,
            sentiment_score=sentiment_score,
            context=context,
        )

        assert signal.recommended_bot_type is None, (
            f"UNKNOWN regime should have recommended_bot_type=None, "
            f"got {signal.recommended_bot_type}"
        )

