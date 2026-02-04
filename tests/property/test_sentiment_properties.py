"""
Property-based tests for Sentiment Analysis Module.

Feature: pionex-trading-bot
Property 6: Fear & Greed Signal Mapping

These tests use the hypothesis library to verify that the sentiment analyzer
signal mapping behaves correctly across all valid FGI values.

**Validates: Requirements 4.2, 4.3**
"""

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from lib.analysis.sentiment import (
    SentimentAnalyzer,
    SentimentConfig,
    FearGreedClassification,
)
from lib.analysis.technical import SignalDirection


# =============================================================================
# Custom Strategies for FGI Values
# =============================================================================

# Strategy for valid FGI values (0-100)
fgi_value_strategy = st.integers(min_value=0, max_value=100)

# Strategy for extreme fear zone (0-25)
extreme_fear_strategy = st.integers(min_value=0, max_value=25)

# Strategy for extreme greed zone (75-100)
extreme_greed_strategy = st.integers(min_value=75, max_value=100)

# Strategy for neutral/hold zone (26-74)
neutral_zone_strategy = st.integers(min_value=26, max_value=74)

# Strategy for custom thresholds (ensuring valid ranges)
@st.composite
def custom_thresholds_strategy(draw: st.DrawFn) -> tuple[int, int]:
    """
    Generate valid custom threshold pairs.
    
    extreme_fear_threshold must be < extreme_greed_threshold
    Both must be within valid FGI range (0-100).
    """
    extreme_fear = draw(st.integers(min_value=0, max_value=49))
    extreme_greed = draw(st.integers(min_value=extreme_fear + 1, max_value=100))
    return extreme_fear, extreme_greed


# =============================================================================
# Property 6: Fear & Greed Signal Mapping
# =============================================================================

class TestFearGreedSignalMapping:
    """
    Property 6: Fear & Greed Signal Mapping
    
    *For any* FGI value:
    - 0-25 → BUY signal (Extreme Fear)
    - 75-100 → SELL signal (Extreme Greed)
    - 26-74 → HOLD signal (Neutral zone)
    - When API is unavailable → HOLD signal
    
    **Validates: Requirements 4.2, 4.3**
    """

    @settings(max_examples=100)
    @given(value=extreme_fear_strategy)
    def test_extreme_fear_always_generates_buy_signal(
        self,
        value: int,
    ) -> None:
        """
        Property: For any FGI value in [0, 25], signal SHALL be BUY.
        
        This validates the contrarian trading strategy where extreme fear
        indicates a buying opportunity.
        
        **Validates: Requirements 4.2**
        """
        analyzer = SentimentAnalyzer()
        signal = analyzer.value_to_signal(value)
        
        assert signal == SignalDirection.BUY, (
            f"FGI value {value} (extreme fear zone [0, 25]) "
            f"should generate BUY signal, got {signal}"
        )

    @settings(max_examples=100)
    @given(value=extreme_greed_strategy)
    def test_extreme_greed_always_generates_sell_signal(
        self,
        value: int,
    ) -> None:
        """
        Property: For any FGI value in [75, 100], signal SHALL be SELL.
        
        This validates the contrarian trading strategy where extreme greed
        indicates a selling opportunity.
        
        **Validates: Requirements 4.2**
        """
        analyzer = SentimentAnalyzer()
        signal = analyzer.value_to_signal(value)
        
        assert signal == SignalDirection.SELL, (
            f"FGI value {value} (extreme greed zone [75, 100]) "
            f"should generate SELL signal, got {signal}"
        )

    @settings(max_examples=100)
    @given(value=neutral_zone_strategy)
    def test_neutral_zone_always_generates_hold_signal(
        self,
        value: int,
    ) -> None:
        """
        Property: For any FGI value in [26, 74], signal SHALL be HOLD.
        
        Values in the neutral zone do not indicate strong sentiment,
        so no trading action is recommended.
        
        **Validates: Requirements 4.2**
        """
        analyzer = SentimentAnalyzer()
        signal = analyzer.value_to_signal(value)
        
        assert signal == SignalDirection.HOLD, (
            f"FGI value {value} (neutral zone [26, 74]) "
            f"should generate HOLD signal, got {signal}"
        )

    @settings(max_examples=100)
    @given(value=fgi_value_strategy)
    def test_signal_is_always_valid_direction(
        self,
        value: int,
    ) -> None:
        """
        Property: For any valid FGI value, signal SHALL be one of BUY, SELL, or HOLD.
        
        This ensures the signal mapping is complete and covers all valid inputs.
        
        **Validates: Requirements 4.2**
        """
        analyzer = SentimentAnalyzer()
        signal = analyzer.value_to_signal(value)
        
        valid_signals = {SignalDirection.BUY, SignalDirection.SELL, SignalDirection.HOLD}
        assert signal in valid_signals, (
            f"FGI value {value} generated invalid signal {signal}, "
            f"expected one of {valid_signals}"
        )

    @settings(max_examples=100)
    @given(value=fgi_value_strategy)
    def test_signal_mapping_is_deterministic(
        self,
        value: int,
    ) -> None:
        """
        Property: For any FGI value, calling value_to_signal twice SHALL produce
        identical results.
        
        Signal mapping must be deterministic for consistent trading behavior.
        
        **Validates: Requirements 4.2**
        """
        analyzer = SentimentAnalyzer()
        
        signal1 = analyzer.value_to_signal(value)
        signal2 = analyzer.value_to_signal(value)
        
        assert signal1 == signal2, (
            f"Signal mapping not deterministic for FGI value {value}: "
            f"got {signal1} and {signal2}"
        )

    @settings(max_examples=100)
    @given(
        value=fgi_value_strategy,
        thresholds=custom_thresholds_strategy(),
    )
    def test_signal_respects_custom_thresholds(
        self,
        value: int,
        thresholds: tuple[int, int],
    ) -> None:
        """
        Property: Signal mapping SHALL respect custom threshold configuration.
        
        When custom thresholds are provided, the signal zones should adjust
        accordingly.
        
        **Validates: Requirements 4.2**
        """
        extreme_fear_threshold, extreme_greed_threshold = thresholds
        
        config = SentimentConfig(
            extreme_fear_threshold=extreme_fear_threshold,
            extreme_greed_threshold=extreme_greed_threshold,
        )
        analyzer = SentimentAnalyzer(config=config)
        
        signal = analyzer.value_to_signal(value)
        
        # Verify signal matches expected zone based on custom thresholds
        if value <= extreme_fear_threshold:
            assert signal == SignalDirection.BUY, (
                f"FGI value {value} <= extreme_fear_threshold {extreme_fear_threshold} "
                f"should generate BUY signal, got {signal}"
            )
        elif value >= extreme_greed_threshold:
            assert signal == SignalDirection.SELL, (
                f"FGI value {value} >= extreme_greed_threshold {extreme_greed_threshold} "
                f"should generate SELL signal, got {signal}"
            )
        else:
            assert signal == SignalDirection.HOLD, (
                f"FGI value {value} in neutral zone "
                f"({extreme_fear_threshold}, {extreme_greed_threshold}) "
                f"should generate HOLD signal, got {signal}"
            )


class TestAPIUnavailabilitySignalMapping:
    """
    Tests for API unavailability handling.
    
    When the Fear & Greed Index API is unavailable, the system SHALL
    return a HOLD signal to avoid making trading decisions without
    sentiment data.
    
    **Validates: Requirements 4.3**
    """

    @settings(max_examples=100)
    @given(error_message=st.text(min_size=1, max_size=200))
    def test_unavailable_result_always_returns_hold_signal(
        self,
        error_message: str,
    ) -> None:
        """
        Property: When API is unavailable, signal SHALL be HOLD.
        
        This ensures graceful degradation when sentiment data cannot be fetched.
        
        **Validates: Requirements 4.3**
        """
        analyzer = SentimentAnalyzer()
        
        # Simulate API unavailability by calling the internal method
        result = analyzer._create_unavailable_result(error_message)
        
        assert result.signal == SignalDirection.HOLD, (
            f"API unavailable result should have HOLD signal, got {result.signal}"
        )
        assert result.data_unavailable is True, (
            "API unavailable result should have data_unavailable=True"
        )
        assert result.value is None, (
            f"API unavailable result should have value=None, got {result.value}"
        )

    @settings(max_examples=100)
    @given(error_message=st.text(min_size=1, max_size=200))
    def test_unavailable_result_has_neutral_classification(
        self,
        error_message: str,
    ) -> None:
        """
        Property: When API is unavailable, classification SHALL be NEUTRAL.
        
        **Validates: Requirements 4.3**
        """
        analyzer = SentimentAnalyzer()
        result = analyzer._create_unavailable_result(error_message)
        
        assert result.classification == FearGreedClassification.NEUTRAL, (
            f"API unavailable result should have NEUTRAL classification, "
            f"got {result.classification}"
        )

    @settings(max_examples=100)
    @given(error_message=st.text(min_size=1, max_size=200))
    def test_unavailable_result_preserves_error_message(
        self,
        error_message: str,
    ) -> None:
        """
        Property: When API is unavailable, error message SHALL be preserved.
        
        This ensures error context is available for debugging and logging.
        
        **Validates: Requirements 4.3**
        """
        analyzer = SentimentAnalyzer()
        result = analyzer._create_unavailable_result(error_message)
        
        assert result.error_message == error_message, (
            f"Error message not preserved: expected {error_message!r}, "
            f"got {result.error_message!r}"
        )


class TestSignalMappingBoundaryConditions:
    """
    Tests for boundary conditions in signal mapping.
    
    These tests verify that the exact boundary values (25, 26, 74, 75)
    are handled correctly according to the specification.
    
    **Validates: Requirements 4.2**
    """

    @settings(max_examples=100)
    @given(
        extreme_fear_threshold=st.integers(min_value=1, max_value=49),
    )
    def test_boundary_at_extreme_fear_threshold(
        self,
        extreme_fear_threshold: int,
    ) -> None:
        """
        Property: Value exactly at extreme_fear_threshold SHALL be BUY.
        Value at extreme_fear_threshold + 1 SHALL be HOLD.
        
        **Validates: Requirements 4.2**
        """
        config = SentimentConfig(
            extreme_fear_threshold=extreme_fear_threshold,
            extreme_greed_threshold=extreme_fear_threshold + 50,  # Ensure valid range
        )
        analyzer = SentimentAnalyzer(config=config)
        
        # At threshold should be BUY
        signal_at = analyzer.value_to_signal(extreme_fear_threshold)
        assert signal_at == SignalDirection.BUY, (
            f"Value at extreme_fear_threshold ({extreme_fear_threshold}) "
            f"should be BUY, got {signal_at}"
        )
        
        # Above threshold should be HOLD
        signal_above = analyzer.value_to_signal(extreme_fear_threshold + 1)
        assert signal_above == SignalDirection.HOLD, (
            f"Value above extreme_fear_threshold ({extreme_fear_threshold + 1}) "
            f"should be HOLD, got {signal_above}"
        )

    @settings(max_examples=100)
    @given(
        extreme_greed_threshold=st.integers(min_value=51, max_value=100),
    )
    def test_boundary_at_extreme_greed_threshold(
        self,
        extreme_greed_threshold: int,
    ) -> None:
        """
        Property: Value exactly at extreme_greed_threshold SHALL be SELL.
        Value at extreme_greed_threshold - 1 SHALL be HOLD.
        
        **Validates: Requirements 4.2**
        """
        config = SentimentConfig(
            extreme_fear_threshold=extreme_greed_threshold - 50,  # Ensure valid range
            extreme_greed_threshold=extreme_greed_threshold,
        )
        analyzer = SentimentAnalyzer(config=config)
        
        # At threshold should be SELL
        signal_at = analyzer.value_to_signal(extreme_greed_threshold)
        assert signal_at == SignalDirection.SELL, (
            f"Value at extreme_greed_threshold ({extreme_greed_threshold}) "
            f"should be SELL, got {signal_at}"
        )
        
        # Below threshold should be HOLD
        signal_below = analyzer.value_to_signal(extreme_greed_threshold - 1)
        assert signal_below == SignalDirection.HOLD, (
            f"Value below extreme_greed_threshold ({extreme_greed_threshold - 1}) "
            f"should be HOLD, got {signal_below}"
        )

    def test_default_boundary_values(self) -> None:
        """
        Property: Default thresholds (25, 75) SHALL produce correct signals
        at exact boundary values.
        
        **Validates: Requirements 4.2**
        """
        analyzer = SentimentAnalyzer()
        
        # Test default extreme fear boundary (25)
        assert analyzer.value_to_signal(25) == SignalDirection.BUY, (
            "Value 25 should be BUY with default thresholds"
        )
        assert analyzer.value_to_signal(26) == SignalDirection.HOLD, (
            "Value 26 should be HOLD with default thresholds"
        )
        
        # Test default extreme greed boundary (75)
        assert analyzer.value_to_signal(74) == SignalDirection.HOLD, (
            "Value 74 should be HOLD with default thresholds"
        )
        assert analyzer.value_to_signal(75) == SignalDirection.SELL, (
            "Value 75 should be SELL with default thresholds"
        )


class TestSignalMappingConsistency:
    """
    Tests for consistency properties of signal mapping.
    
    These tests verify that the signal mapping behaves consistently
    across different analyzer instances and configurations.
    
    **Validates: Requirements 4.2**
    """

    @settings(max_examples=100)
    @given(value=fgi_value_strategy)
    def test_multiple_analyzers_produce_same_signal(
        self,
        value: int,
    ) -> None:
        """
        Property: Multiple SentimentAnalyzer instances with same config
        SHALL produce identical signals for the same FGI value.
        
        **Validates: Requirements 4.2**
        """
        analyzer1 = SentimentAnalyzer()
        analyzer2 = SentimentAnalyzer()
        
        signal1 = analyzer1.value_to_signal(value)
        signal2 = analyzer2.value_to_signal(value)
        
        assert signal1 == signal2, (
            f"Different analyzer instances produced different signals "
            f"for FGI value {value}: {signal1} vs {signal2}"
        )

    @settings(max_examples=100)
    @given(
        value=fgi_value_strategy,
        thresholds=custom_thresholds_strategy(),
    )
    def test_same_config_produces_same_signal(
        self,
        value: int,
        thresholds: tuple[int, int],
    ) -> None:
        """
        Property: Analyzers with identical configuration SHALL produce
        identical signals for the same FGI value.
        
        **Validates: Requirements 4.2**
        """
        extreme_fear, extreme_greed = thresholds
        
        config1 = SentimentConfig(
            extreme_fear_threshold=extreme_fear,
            extreme_greed_threshold=extreme_greed,
        )
        config2 = SentimentConfig(
            extreme_fear_threshold=extreme_fear,
            extreme_greed_threshold=extreme_greed,
        )
        
        analyzer1 = SentimentAnalyzer(config=config1)
        analyzer2 = SentimentAnalyzer(config=config2)
        
        signal1 = analyzer1.value_to_signal(value)
        signal2 = analyzer2.value_to_signal(value)
        
        assert signal1 == signal2, (
            f"Analyzers with same config produced different signals "
            f"for FGI value {value}: {signal1} vs {signal2}"
        )
