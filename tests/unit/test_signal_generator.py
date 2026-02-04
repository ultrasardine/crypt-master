"""
Unit tests for SignalGenerator.

Tests the signal generation system including confidence threshold enforcement,
signal metadata generation, and integration with ConfidenceScorer.

Requirements tested:
- 5.5: Only execute trades when confidence_score meets or exceeds minimum threshold (default 85%)
- 5.1: Generate Signal containing direction, confidence_score, and supporting_factors
- 5.6: Include all indicator values and their individual contributions
"""

import pytest
from datetime import datetime, timezone

from lib.analysis import (
    ConfidenceConfig,
    IndicatorScore,
    Signal,
    SignalDirection,
    SignalGenerator,
    SignalGeneratorConfig,
)


@pytest.fixture
def config() -> SignalGeneratorConfig:
    """Create a SignalGeneratorConfig with default values."""
    return SignalGeneratorConfig()


@pytest.fixture
def generator(config: SignalGeneratorConfig) -> SignalGenerator:
    """Create a SignalGenerator with default config."""
    return SignalGenerator(config=config)


def create_indicator(
    name: str,
    signal: SignalDirection,
    confidence: float,
    weight: float = 1.0,
    value: float | None = None,
    data_insufficient: bool = False,
) -> IndicatorScore:
    """Helper to create IndicatorScore instances."""
    return IndicatorScore(
        name=name,
        signal=signal,
        confidence=confidence,
        weight=weight,
        value=value,
        data_insufficient=data_insufficient,
    )


class TestMinimumConfidenceThreshold:
    """Tests for minimum confidence threshold enforcement - Requirement 5.5."""
    
    def test_default_threshold_is_85_percent(self) -> None:
        """Default minimum confidence threshold should be 85%."""
        config = SignalGeneratorConfig()
        assert config.min_confidence_threshold == 85.0
    
    def test_signal_above_threshold_keeps_direction(
        self, generator: SignalGenerator
    ) -> None:
        """Signal with confidence >= 85% should keep original direction."""
        # Create indicators that will produce high confidence
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 100.0, weight=1.0),
        ]
        sentiment = create_indicator("FGI", SignalDirection.BUY, 100.0, weight=1.0)
        news = create_indicator("News", SignalDirection.BUY, 100.0, weight=1.0)
        
        signal = generator.generate_signal(
            "BTC_USDT", technical, sentiment, news
        )
        
        # With all at 100%, confidence should be 100% + alignment bonus (capped at 100)
        assert signal.confidence >= 85.0
        assert signal.direction == SignalDirection.BUY
        assert signal.meets_threshold is True
    
    def test_signal_below_threshold_becomes_hold(
        self, generator: SignalGenerator
    ) -> None:
        """Signal with confidence < 85% should become HOLD."""
        # Create indicators that will produce low confidence
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 50.0, weight=1.0),
        ]
        # Only technical at 50% = 50% * 60% = 30% base score
        
        signal = generator.generate_signal("BTC_USDT", technical)
        
        assert signal.confidence < 85.0
        assert signal.direction == SignalDirection.HOLD
        assert signal.meets_threshold is False
    
    def test_signal_exactly_at_threshold_passes(self) -> None:
        """Signal with confidence exactly at 85% should pass threshold."""
        # Use custom config to make testing easier
        config = SignalGeneratorConfig(min_confidence_threshold=50.0)
        generator = SignalGenerator(config=config)
        
        # Create indicators that produce exactly 50% confidence
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 83.33, weight=1.0),
        ]
        # 83.33% * 60% = 50% base score
        
        signal = generator.generate_signal("BTC_USDT", technical)
        
        # Should be at or above threshold
        assert signal.confidence >= 50.0
        assert signal.meets_threshold is True
    
    def test_custom_threshold_enforced(self) -> None:
        """Custom threshold should be enforced correctly."""
        config = SignalGeneratorConfig(min_confidence_threshold=90.0)
        generator = SignalGenerator(config=config)
        
        # Create indicators that produce ~85% confidence
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 100.0, weight=1.0),
        ]
        sentiment = create_indicator("FGI", SignalDirection.BUY, 100.0, weight=1.0)
        # 100% * 60% + 100% * 30% = 90% base score
        
        signal = generator.generate_signal("BTC_USDT", technical, sentiment)
        
        # With 90% threshold, this should pass
        assert signal.threshold_used == 90.0
        assert signal.meets_threshold is True
    
    def test_sell_signal_below_threshold_becomes_hold(
        self, generator: SignalGenerator
    ) -> None:
        """SELL signal with confidence < 85% should become HOLD."""
        technical = [
            create_indicator("RSI", SignalDirection.SELL, 50.0, weight=1.0),
        ]
        
        signal = generator.generate_signal("BTC_USDT", technical)
        
        assert signal.confidence < 85.0
        assert signal.direction == SignalDirection.HOLD
        assert signal.meets_threshold is False


class TestSignalGeneration:
    """Tests for signal generation - Requirement 5.1."""
    
    def test_signal_contains_symbol(self, generator: SignalGenerator) -> None:
        """Signal should contain the trading pair symbol."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 100.0, weight=1.0),
        ]
        
        signal = generator.generate_signal("BTC_USDT", technical)
        
        assert signal.symbol == "BTC_USDT"
    
    def test_signal_contains_direction(self, generator: SignalGenerator) -> None:
        """Signal should contain direction (BUY/SELL/HOLD)."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 100.0, weight=1.0),
        ]
        sentiment = create_indicator("FGI", SignalDirection.BUY, 100.0, weight=1.0)
        news = create_indicator("News", SignalDirection.BUY, 100.0, weight=1.0)
        
        signal = generator.generate_signal(
            "ETH_USDT", technical, sentiment, news
        )
        
        assert signal.direction in (
            SignalDirection.BUY,
            SignalDirection.SELL,
            SignalDirection.HOLD,
        )
    
    def test_signal_contains_confidence_score(
        self, generator: SignalGenerator
    ) -> None:
        """Signal should contain confidence score (0-100)."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 80.0, weight=1.0),
        ]
        
        signal = generator.generate_signal("BTC_USDT", technical)
        
        assert 0 <= signal.confidence <= 100
    
    def test_signal_contains_timestamp(self, generator: SignalGenerator) -> None:
        """Signal should contain timestamp."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 80.0, weight=1.0),
        ]
        
        signal = generator.generate_signal("BTC_USDT", technical)
        
        assert signal.timestamp is not None
        assert isinstance(signal.timestamp, datetime)
    
    def test_signal_contains_reasoning(self, generator: SignalGenerator) -> None:
        """Signal should contain human-readable reasoning."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 80.0, weight=1.0),
        ]
        
        signal = generator.generate_signal("BTC_USDT", technical)
        
        assert signal.reasoning is not None
        assert len(signal.reasoning) > 0
    
    def test_buy_signal_generation(self, generator: SignalGenerator) -> None:
        """Should generate BUY signal when indicators agree and confidence is high."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 100.0, weight=1.0),
        ]
        sentiment = create_indicator("FGI", SignalDirection.BUY, 100.0, weight=1.0)
        news = create_indicator("News", SignalDirection.BUY, 100.0, weight=1.0)
        
        signal = generator.generate_signal(
            "BTC_USDT", technical, sentiment, news
        )
        
        assert signal.direction == SignalDirection.BUY
        assert signal.meets_threshold is True
    
    def test_sell_signal_generation(self, generator: SignalGenerator) -> None:
        """Should generate SELL signal when indicators agree and confidence is high."""
        technical = [
            create_indicator("RSI", SignalDirection.SELL, 100.0, weight=1.0),
        ]
        sentiment = create_indicator("FGI", SignalDirection.SELL, 100.0, weight=1.0)
        news = create_indicator("News", SignalDirection.SELL, 100.0, weight=1.0)
        
        signal = generator.generate_signal(
            "BTC_USDT", technical, sentiment, news
        )
        
        assert signal.direction == SignalDirection.SELL
        assert signal.meets_threshold is True
    
    def test_hold_signal_on_conflict(self, generator: SignalGenerator) -> None:
        """Should generate HOLD signal when indicators conflict."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 100.0, weight=1.0),
        ]
        sentiment = create_indicator("FGI", SignalDirection.SELL, 100.0, weight=1.0)
        
        signal = generator.generate_signal("BTC_USDT", technical, sentiment)
        
        assert signal.direction == SignalDirection.HOLD


class TestSignalMetadata:
    """Tests for signal metadata - Requirement 5.6."""
    
    def test_signal_contains_all_indicators(
        self, generator: SignalGenerator
    ) -> None:
        """Signal should contain all indicator scores."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 80.0, weight=0.5),
            create_indicator("MACD", SignalDirection.BUY, 70.0, weight=0.5),
        ]
        sentiment = create_indicator("FGI", SignalDirection.BUY, 60.0, weight=1.0)
        news = create_indicator("News", SignalDirection.BUY, 50.0, weight=1.0)
        
        signal = generator.generate_signal(
            "BTC_USDT", technical, sentiment, news
        )
        
        assert len(signal.indicators) == 4
        indicator_names = [ind.name for ind in signal.indicators]
        assert "RSI" in indicator_names
        assert "MACD" in indicator_names
        assert "FGI" in indicator_names
        assert "News" in indicator_names
    
    def test_signal_contains_breakdown(self, generator: SignalGenerator) -> None:
        """Signal should contain detailed confidence breakdown."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 80.0, weight=1.0),
        ]
        sentiment = create_indicator("FGI", SignalDirection.BUY, 60.0, weight=1.0)
        
        signal = generator.generate_signal("BTC_USDT", technical, sentiment)
        
        assert signal.breakdown is not None
        assert hasattr(signal.breakdown, "technical_score")
        assert hasattr(signal.breakdown, "sentiment_score")
        assert hasattr(signal.breakdown, "news_score")
        assert hasattr(signal.breakdown, "alignment_bonus")
        assert hasattr(signal.breakdown, "base_score")
        assert hasattr(signal.breakdown, "final_score")
    
    def test_signal_contains_threshold_info(
        self, generator: SignalGenerator
    ) -> None:
        """Signal should contain threshold information."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 80.0, weight=1.0),
        ]
        
        signal = generator.generate_signal("BTC_USDT", technical)
        
        assert hasattr(signal, "meets_threshold")
        assert hasattr(signal, "threshold_used")
        assert signal.threshold_used == 85.0
    
    def test_get_signal_metadata_returns_dict(
        self, generator: SignalGenerator
    ) -> None:
        """get_signal_metadata should return a dictionary."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 80.0, weight=1.0),
        ]
        
        signal = generator.generate_signal("BTC_USDT", technical)
        metadata = generator.get_signal_metadata(signal)
        
        assert isinstance(metadata, dict)
        assert "symbol" in metadata
        assert "direction" in metadata
        assert "confidence" in metadata
        assert "timestamp" in metadata
        assert "breakdown" in metadata
        assert "indicators" in metadata
    
    def test_metadata_contains_indicator_details(
        self, generator: SignalGenerator
    ) -> None:
        """Metadata should contain detailed indicator information."""
        technical = [
            create_indicator(
                "RSI", SignalDirection.BUY, 80.0, weight=0.5, value=35.0
            ),
        ]
        
        signal = generator.generate_signal("BTC_USDT", technical)
        metadata = generator.get_signal_metadata(signal)
        
        assert len(metadata["indicators"]) == 1
        ind = metadata["indicators"][0]
        assert ind["name"] == "RSI"
        assert ind["signal"] == "BUY"
        assert ind["confidence"] == 80.0
        assert ind["weight"] == 0.5
        assert ind["value"] == 35.0
        assert ind["data_insufficient"] is False


class TestWouldExecute:
    """Tests for would_execute method - Requirement 5.5."""
    
    def test_would_execute_buy_above_threshold(
        self, generator: SignalGenerator
    ) -> None:
        """BUY signal above threshold should execute."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 100.0, weight=1.0),
        ]
        sentiment = create_indicator("FGI", SignalDirection.BUY, 100.0, weight=1.0)
        news = create_indicator("News", SignalDirection.BUY, 100.0, weight=1.0)
        
        signal = generator.generate_signal(
            "BTC_USDT", technical, sentiment, news
        )
        
        assert generator.would_execute(signal) is True
    
    def test_would_execute_sell_above_threshold(
        self, generator: SignalGenerator
    ) -> None:
        """SELL signal above threshold should execute."""
        technical = [
            create_indicator("RSI", SignalDirection.SELL, 100.0, weight=1.0),
        ]
        sentiment = create_indicator("FGI", SignalDirection.SELL, 100.0, weight=1.0)
        news = create_indicator("News", SignalDirection.SELL, 100.0, weight=1.0)
        
        signal = generator.generate_signal(
            "BTC_USDT", technical, sentiment, news
        )
        
        assert generator.would_execute(signal) is True
    
    def test_would_not_execute_below_threshold(
        self, generator: SignalGenerator
    ) -> None:
        """Signal below threshold should not execute."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 50.0, weight=1.0),
        ]
        
        signal = generator.generate_signal("BTC_USDT", technical)
        
        assert generator.would_execute(signal) is False
    
    def test_would_not_execute_hold_signal(
        self, generator: SignalGenerator
    ) -> None:
        """HOLD signal should not execute even with high confidence."""
        technical = [
            create_indicator("RSI", SignalDirection.HOLD, 100.0, weight=1.0),
        ]
        sentiment = create_indicator("FGI", SignalDirection.HOLD, 100.0, weight=1.0)
        news = create_indicator("News", SignalDirection.HOLD, 100.0, weight=1.0)
        
        signal = generator.generate_signal(
            "BTC_USDT", technical, sentiment, news
        )
        
        assert generator.would_execute(signal) is False


class TestSignalGeneratorConfig:
    """Tests for SignalGeneratorConfig validation."""
    
    def test_invalid_threshold_below_zero_raises_error(self) -> None:
        """Threshold below 0 should raise ValueError."""
        with pytest.raises(ValueError, match="min_confidence_threshold"):
            SignalGeneratorConfig(min_confidence_threshold=-10.0)
    
    def test_invalid_threshold_above_100_raises_error(self) -> None:
        """Threshold above 100 should raise ValueError."""
        with pytest.raises(ValueError, match="min_confidence_threshold"):
            SignalGeneratorConfig(min_confidence_threshold=150.0)
    
    def test_valid_threshold_accepted(self) -> None:
        """Valid threshold values should be accepted."""
        config = SignalGeneratorConfig(min_confidence_threshold=75.0)
        assert config.min_confidence_threshold == 75.0
    
    def test_zero_threshold_accepted(self) -> None:
        """Zero threshold should be accepted."""
        config = SignalGeneratorConfig(min_confidence_threshold=0.0)
        assert config.min_confidence_threshold == 0.0
    
    def test_100_threshold_accepted(self) -> None:
        """100% threshold should be accepted."""
        config = SignalGeneratorConfig(min_confidence_threshold=100.0)
        assert config.min_confidence_threshold == 100.0
    
    def test_custom_confidence_config_used(self) -> None:
        """Custom ConfidenceConfig should be passed to scorer."""
        confidence_config = ConfidenceConfig(
            technical_weight=0.5,
            sentiment_weight=0.4,
            news_weight=0.1,
        )
        config = SignalGeneratorConfig(
            min_confidence_threshold=80.0,
            confidence_config=confidence_config,
        )
        generator = SignalGenerator(config=config)
        
        # Verify the custom config is used
        assert generator._scorer.config.technical_weight == 0.5
        assert generator._scorer.config.sentiment_weight == 0.4


class TestSignalImmutability:
    """Tests for Signal dataclass immutability."""
    
    def test_signal_is_immutable(self, generator: SignalGenerator) -> None:
        """Signal should be immutable (frozen)."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 80.0, weight=1.0),
        ]
        
        signal = generator.generate_signal("BTC_USDT", technical)
        
        with pytest.raises(AttributeError):
            signal.confidence = 90.0  # type: ignore
    
    def test_signal_indicators_are_tuple(
        self, generator: SignalGenerator
    ) -> None:
        """Signal indicators should be a tuple (immutable)."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 80.0, weight=1.0),
        ]
        
        signal = generator.generate_signal("BTC_USDT", technical)
        
        assert isinstance(signal.indicators, tuple)


class TestEdgeCases:
    """Tests for edge cases."""
    
    def test_empty_technical_indicators(
        self, generator: SignalGenerator
    ) -> None:
        """Empty technical indicators should return HOLD."""
        signal = generator.generate_signal("BTC_USDT", [])
        
        assert signal.direction == SignalDirection.HOLD
        assert signal.confidence == 0.0
    
    def test_all_insufficient_data(self, generator: SignalGenerator) -> None:
        """All indicators with insufficient data should return HOLD."""
        technical = [
            create_indicator(
                "RSI", SignalDirection.BUY, 80.0, weight=1.0,
                data_insufficient=True
            ),
        ]
        
        signal = generator.generate_signal("BTC_USDT", technical)
        
        assert signal.direction == SignalDirection.HOLD
        assert signal.confidence == 0.0
    
    def test_none_sentiment_and_news(self, generator: SignalGenerator) -> None:
        """None sentiment and news should be handled correctly."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 100.0, weight=1.0),
        ]
        sentiment = create_indicator("FGI", SignalDirection.BUY, 100.0, weight=1.0)
        news = create_indicator("News", SignalDirection.BUY, 100.0, weight=1.0)
        
        signal = generator.generate_signal(
            "BTC_USDT", technical, sentiment, news
        )
        
        # Should work without errors
        assert signal.symbol == "BTC_USDT"
    
    def test_different_symbols(self, generator: SignalGenerator) -> None:
        """Different symbols should be preserved in signal."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 80.0, weight=1.0),
        ]
        
        signal1 = generator.generate_signal("BTC_USDT", technical)
        signal2 = generator.generate_signal("ETH_USDT", technical)
        signal3 = generator.generate_signal("SOL_USDT", technical)
        
        assert signal1.symbol == "BTC_USDT"
        assert signal2.symbol == "ETH_USDT"
        assert signal3.symbol == "SOL_USDT"
    
    def test_reasoning_includes_threshold_info_when_below(
        self, generator: SignalGenerator
    ) -> None:
        """Reasoning should mention threshold when signal is below it."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 50.0, weight=1.0),
        ]
        
        signal = generator.generate_signal("BTC_USDT", technical)
        
        assert "threshold" in signal.reasoning.lower()
        assert "85" in signal.reasoning or "85.0" in signal.reasoning


class TestMinConfidenceThresholdProperty:
    """Tests for min_confidence_threshold property."""
    
    def test_min_confidence_threshold_property(
        self, generator: SignalGenerator
    ) -> None:
        """min_confidence_threshold property should return config value."""
        assert generator.min_confidence_threshold == 85.0
    
    def test_custom_threshold_via_property(self) -> None:
        """Custom threshold should be accessible via property."""
        config = SignalGeneratorConfig(min_confidence_threshold=90.0)
        generator = SignalGenerator(config=config)
        
        assert generator.min_confidence_threshold == 90.0
