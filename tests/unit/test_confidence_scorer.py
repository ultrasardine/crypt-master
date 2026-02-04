"""
Unit tests for ConfidenceScorer.

Tests the confidence scoring system including weighted calculations,
alignment bonuses, conflict handling, and signal generation.

Requirements tested:
- 5.1: Generate trading signals combining technical and sentiment analysis
- 5.2: Calculate confidence score using weighted combination (technical 60%, sentiment 30%, news 10%)
- 5.3: Apply alignment bonus when multiple indicators agree (up to +10%)
- 5.4: Handle conflicting signals by defaulting to HOLD
- 5.6: Include all contributing factors in signal metadata
"""

import pytest
from datetime import datetime, timezone

from lib.analysis import (
    ConfidenceBreakdown,
    ConfidenceConfig,
    ConfidenceResult,
    ConfidenceScorer,
    IndicatorScore,
    SignalDirection,
)


@pytest.fixture
def config() -> ConfidenceConfig:
    """Create a ConfidenceConfig with default values."""
    return ConfidenceConfig()


@pytest.fixture
def scorer(config: ConfidenceConfig) -> ConfidenceScorer:
    """Create a ConfidenceScorer with default config."""
    return ConfidenceScorer(config=config)


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


class TestWeightedCalculation:
    """Tests for weighted confidence calculation - Requirement 5.2."""
    
    def test_default_weights_sum_to_one(self) -> None:
        """Default weights should sum to 1.0."""
        config = ConfidenceConfig()
        total = config.technical_weight + config.sentiment_weight + config.news_weight
        assert abs(total - 1.0) < 0.001
    
    def test_default_weights_are_correct(self) -> None:
        """Default weights should be 60% technical, 30% sentiment, 10% news."""
        config = ConfidenceConfig()
        assert config.technical_weight == 0.60
        assert config.sentiment_weight == 0.30
        assert config.news_weight == 0.10
    
    def test_technical_only_calculation(self, scorer: ConfidenceScorer) -> None:
        """With only technical indicators, score should be weighted correctly."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 100.0, weight=1.0),
        ]
        
        result = scorer.calculate_confidence(technical)
        
        # 100% confidence * 60% weight = 60% base score
        assert result.breakdown.technical_score == pytest.approx(60.0, rel=0.01)
        assert result.breakdown.sentiment_score == 0.0
        assert result.breakdown.news_score == 0.0
    
    def test_all_sources_calculation(self, scorer: ConfidenceScorer) -> None:
        """With all sources at 100%, base score should be 100%."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 100.0, weight=1.0),
        ]
        sentiment = create_indicator("FGI", SignalDirection.BUY, 100.0, weight=1.0)
        news = create_indicator("News", SignalDirection.BUY, 100.0, weight=1.0)
        
        result = scorer.calculate_confidence(technical, sentiment, news)
        
        # All at 100%: 60% + 30% + 10% = 100%
        assert result.breakdown.base_score == pytest.approx(100.0, rel=0.01)
    
    def test_partial_confidence_calculation(self, scorer: ConfidenceScorer) -> None:
        """Partial confidence values should be weighted correctly."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 80.0, weight=1.0),
        ]
        sentiment = create_indicator("FGI", SignalDirection.BUY, 60.0, weight=1.0)
        news = create_indicator("News", SignalDirection.BUY, 40.0, weight=1.0)
        
        result = scorer.calculate_confidence(technical, sentiment, news)
        
        # 80% * 60% + 60% * 30% + 40% * 10% = 48% + 18% + 4% = 70%
        expected_base = 80 * 0.60 + 60 * 0.30 + 40 * 0.10
        assert result.breakdown.base_score == pytest.approx(expected_base, rel=0.01)
    
    def test_multiple_technical_indicators_averaged(
        self, scorer: ConfidenceScorer
    ) -> None:
        """Multiple technical indicators should be weight-averaged."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 100.0, weight=0.5),
            create_indicator("MACD", SignalDirection.BUY, 50.0, weight=0.5),
        ]
        
        result = scorer.calculate_confidence(technical)
        
        # Average: (100 * 0.5 + 50 * 0.5) / 1.0 = 75%
        # Technical contribution: 75% * 60% = 45%
        assert result.breakdown.technical_score == pytest.approx(45.0, rel=0.01)


class TestAlignmentBonus:
    """Tests for alignment bonus - Requirement 5.3."""
    
    def test_full_alignment_bonus(self, scorer: ConfidenceScorer) -> None:
        """All indicators agreeing should give full alignment bonus."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 80.0, weight=0.5),
            create_indicator("MACD", SignalDirection.BUY, 80.0, weight=0.5),
        ]
        sentiment = create_indicator("FGI", SignalDirection.BUY, 80.0, weight=1.0)
        news = create_indicator("News", SignalDirection.BUY, 80.0, weight=1.0)
        
        result = scorer.calculate_confidence(technical, sentiment, news)
        
        # All 4 indicators agree, so full 10% bonus
        assert result.breakdown.alignment_bonus == pytest.approx(10.0, rel=0.01)
        assert result.breakdown.agreeing_indicators == 4
        assert result.breakdown.total_indicators == 4
    
    def test_partial_alignment_bonus(self, scorer: ConfidenceScorer) -> None:
        """Partial agreement should give proportional bonus."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 80.0, weight=0.5),
            create_indicator("MACD", SignalDirection.HOLD, 50.0, weight=0.5),
        ]
        sentiment = create_indicator("FGI", SignalDirection.BUY, 80.0, weight=1.0)
        
        result = scorer.calculate_confidence(technical, sentiment)
        
        # 2 out of 3 agree with BUY, so 2/3 * 10% = 6.67% bonus
        expected_bonus = (2 / 3) * 10.0
        assert result.breakdown.alignment_bonus == pytest.approx(expected_bonus, rel=0.01)
        assert result.breakdown.agreeing_indicators == 2
    
    def test_no_alignment_bonus_with_conflict(self, scorer: ConfidenceScorer) -> None:
        """Conflicting signals should not receive alignment bonus."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 80.0, weight=1.0),
        ]
        sentiment = create_indicator("FGI", SignalDirection.SELL, 80.0, weight=1.0)
        
        result = scorer.calculate_confidence(technical, sentiment)
        
        # Conflict detected, no alignment bonus
        assert result.breakdown.alignment_bonus == 0.0
        assert result.conflict_detected is True
    
    def test_alignment_bonus_capped_at_max(self) -> None:
        """Alignment bonus should not exceed max_alignment_bonus."""
        config = ConfidenceConfig(max_alignment_bonus=5.0)
        scorer = ConfidenceScorer(config=config)
        
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 80.0, weight=1.0),
        ]
        sentiment = create_indicator("FGI", SignalDirection.BUY, 80.0, weight=1.0)
        
        result = scorer.calculate_confidence(technical, sentiment)
        
        # Max bonus is 5%, all agree so full bonus
        assert result.breakdown.alignment_bonus == pytest.approx(5.0, rel=0.01)
    
    def test_final_score_capped_at_100(self, scorer: ConfidenceScorer) -> None:
        """Final score should not exceed 100%."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 100.0, weight=1.0),
        ]
        sentiment = create_indicator("FGI", SignalDirection.BUY, 100.0, weight=1.0)
        news = create_indicator("News", SignalDirection.BUY, 100.0, weight=1.0)
        
        result = scorer.calculate_confidence(technical, sentiment, news)
        
        # Base score 100% + 10% bonus should cap at 100%
        assert result.confidence <= 100.0
        assert result.breakdown.final_score <= 100.0


class TestConflictHandling:
    """Tests for conflict handling - Requirement 5.4."""
    
    def test_buy_sell_conflict_returns_hold(self, scorer: ConfidenceScorer) -> None:
        """Conflicting BUY and SELL signals should return HOLD."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 80.0, weight=1.0),
        ]
        sentiment = create_indicator("FGI", SignalDirection.SELL, 80.0, weight=1.0)
        
        result = scorer.calculate_confidence(technical, sentiment)
        
        assert result.signal == SignalDirection.HOLD
        assert result.conflict_detected is True
    
    def test_no_conflict_with_hold_indicators(
        self, scorer: ConfidenceScorer
    ) -> None:
        """HOLD indicators should not cause conflict detection."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 80.0, weight=1.0),
            create_indicator("MACD", SignalDirection.HOLD, 50.0, weight=1.0),
        ]
        sentiment = create_indicator("FGI", SignalDirection.BUY, 80.0, weight=1.0)
        
        result = scorer.calculate_confidence(technical, sentiment)
        
        assert result.signal == SignalDirection.BUY
        assert result.conflict_detected is False
    
    def test_majority_buy_wins(self, scorer: ConfidenceScorer) -> None:
        """When BUY signals outnumber SELL, BUY should win."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 80.0, weight=0.33),
            create_indicator("MACD", SignalDirection.BUY, 80.0, weight=0.33),
            create_indicator("BB", SignalDirection.SELL, 80.0, weight=0.34),
        ]
        
        result = scorer.calculate_confidence(technical)
        
        # 2 BUY vs 1 SELL, BUY wins (no conflict since SELL < 50%)
        assert result.signal == SignalDirection.BUY
        assert result.conflict_detected is False
    
    def test_majority_sell_wins(self, scorer: ConfidenceScorer) -> None:
        """When SELL signals outnumber BUY, SELL should win."""
        technical = [
            create_indicator("RSI", SignalDirection.SELL, 80.0, weight=0.33),
            create_indicator("MACD", SignalDirection.SELL, 80.0, weight=0.33),
            create_indicator("BB", SignalDirection.BUY, 80.0, weight=0.34),
        ]
        
        result = scorer.calculate_confidence(technical)
        
        # 2 SELL vs 1 BUY, SELL wins
        assert result.signal == SignalDirection.SELL
        assert result.conflict_detected is False
    
    def test_equal_buy_sell_returns_hold(self, scorer: ConfidenceScorer) -> None:
        """Equal BUY and SELL counts should return HOLD."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 80.0, weight=0.5),
            create_indicator("MACD", SignalDirection.SELL, 80.0, weight=0.5),
        ]
        
        result = scorer.calculate_confidence(technical)
        
        # 1 BUY vs 1 SELL = conflict
        assert result.signal == SignalDirection.HOLD
        assert result.conflict_detected is True
    
    def test_custom_conflict_threshold(self) -> None:
        """Custom conflict threshold should affect conflict detection."""
        # With threshold of 0.4, need 40% of each to conflict
        config = ConfidenceConfig(conflict_threshold=0.4)
        scorer = ConfidenceScorer(config=config)
        
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 80.0, weight=0.5),
            create_indicator("MACD", SignalDirection.SELL, 80.0, weight=0.5),
        ]
        
        result = scorer.calculate_confidence(technical)
        
        # 50% BUY, 50% SELL - both above 40% threshold = conflict
        assert result.conflict_detected is True
        assert result.signal == SignalDirection.HOLD


class TestSignalGeneration:
    """Tests for signal generation - Requirement 5.1."""
    
    def test_buy_signal_generation(self, scorer: ConfidenceScorer) -> None:
        """Should generate BUY signal when indicators agree on BUY."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 80.0, weight=1.0),
        ]
        sentiment = create_indicator("FGI", SignalDirection.BUY, 70.0, weight=1.0)
        
        result = scorer.calculate_confidence(technical, sentiment)
        
        assert result.signal == SignalDirection.BUY
    
    def test_sell_signal_generation(self, scorer: ConfidenceScorer) -> None:
        """Should generate SELL signal when indicators agree on SELL."""
        technical = [
            create_indicator("RSI", SignalDirection.SELL, 80.0, weight=1.0),
        ]
        sentiment = create_indicator("FGI", SignalDirection.SELL, 70.0, weight=1.0)
        
        result = scorer.calculate_confidence(technical, sentiment)
        
        assert result.signal == SignalDirection.SELL
    
    def test_hold_signal_with_all_hold_indicators(
        self, scorer: ConfidenceScorer
    ) -> None:
        """Should generate HOLD when all indicators are HOLD."""
        technical = [
            create_indicator("RSI", SignalDirection.HOLD, 50.0, weight=1.0),
        ]
        sentiment = create_indicator("FGI", SignalDirection.HOLD, 50.0, weight=1.0)
        
        result = scorer.calculate_confidence(technical, sentiment)
        
        assert result.signal == SignalDirection.HOLD
        assert result.conflict_detected is False


class TestInsufficientData:
    """Tests for handling insufficient data - Requirement 5.6."""
    
    def test_insufficient_data_excluded(self, scorer: ConfidenceScorer) -> None:
        """Indicators with insufficient data should be excluded."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 80.0, weight=0.5),
            create_indicator(
                "MACD", SignalDirection.SELL, 80.0, weight=0.5,
                data_insufficient=True
            ),
        ]
        
        result = scorer.calculate_confidence(technical)
        
        # Only RSI should be counted
        assert result.breakdown.total_indicators == 1
        assert result.signal == SignalDirection.BUY
    
    def test_all_insufficient_data_returns_hold(
        self, scorer: ConfidenceScorer
    ) -> None:
        """All indicators with insufficient data should return HOLD."""
        technical = [
            create_indicator(
                "RSI", SignalDirection.BUY, 80.0, weight=1.0,
                data_insufficient=True
            ),
        ]
        sentiment = create_indicator(
            "FGI", SignalDirection.BUY, 80.0, weight=1.0,
            data_insufficient=True
        )
        
        result = scorer.calculate_confidence(technical, sentiment)
        
        assert result.signal == SignalDirection.HOLD
        assert result.confidence == 0.0
        assert result.breakdown.total_indicators == 0
    
    def test_empty_indicators_returns_hold(self, scorer: ConfidenceScorer) -> None:
        """Empty indicator list should return HOLD."""
        result = scorer.calculate_confidence([])
        
        assert result.signal == SignalDirection.HOLD
        assert result.confidence == 0.0


class TestBreakdownMetadata:
    """Tests for breakdown metadata - Requirement 5.6."""
    
    def test_breakdown_includes_all_indicators(
        self, scorer: ConfidenceScorer
    ) -> None:
        """Breakdown should include all indicators."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 80.0, weight=0.5),
            create_indicator("MACD", SignalDirection.BUY, 70.0, weight=0.5),
        ]
        sentiment = create_indicator("FGI", SignalDirection.BUY, 60.0, weight=1.0)
        news = create_indicator("News", SignalDirection.BUY, 50.0, weight=1.0)
        
        result = scorer.calculate_confidence(technical, sentiment, news)
        
        assert len(result.breakdown.indicators) == 4
        indicator_names = [ind.name for ind in result.breakdown.indicators]
        assert "RSI" in indicator_names
        assert "MACD" in indicator_names
        assert "FGI" in indicator_names
        assert "News" in indicator_names
    
    def test_breakdown_has_correct_scores(self, scorer: ConfidenceScorer) -> None:
        """Breakdown should have correct individual scores."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 80.0, weight=1.0),
        ]
        sentiment = create_indicator("FGI", SignalDirection.BUY, 60.0, weight=1.0)
        news = create_indicator("News", SignalDirection.BUY, 40.0, weight=1.0)
        
        result = scorer.calculate_confidence(technical, sentiment, news)
        
        # Technical: 80% * 60% = 48%
        assert result.breakdown.technical_score == pytest.approx(48.0, rel=0.01)
        # Sentiment: 60% * 30% = 18%
        assert result.breakdown.sentiment_score == pytest.approx(18.0, rel=0.01)
        # News: 40% * 10% = 4%
        assert result.breakdown.news_score == pytest.approx(4.0, rel=0.01)
    
    def test_result_has_timestamp(self, scorer: ConfidenceScorer) -> None:
        """Result should have a timestamp."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 80.0, weight=1.0),
        ]
        
        result = scorer.calculate_confidence(technical)
        
        assert result.timestamp is not None
        assert isinstance(result.timestamp, datetime)
    
    def test_result_has_reasoning(self, scorer: ConfidenceScorer) -> None:
        """Result should have human-readable reasoning."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 80.0, weight=1.0),
        ]
        
        result = scorer.calculate_confidence(technical)
        
        assert result.reasoning is not None
        assert len(result.reasoning) > 0
        assert "BUY" in result.reasoning


class TestConfidenceConfig:
    """Tests for ConfidenceConfig validation."""
    
    def test_invalid_weights_raises_error(self) -> None:
        """Weights not summing to 1.0 should raise ValueError."""
        with pytest.raises(ValueError, match="Weights must sum to 1.0"):
            ConfidenceConfig(
                technical_weight=0.5,
                sentiment_weight=0.3,
                news_weight=0.1,  # Sum = 0.9
            )
    
    def test_invalid_alignment_bonus_raises_error(self) -> None:
        """Invalid alignment bonus should raise ValueError."""
        with pytest.raises(ValueError, match="max_alignment_bonus"):
            ConfidenceConfig(max_alignment_bonus=150.0)
    
    def test_invalid_conflict_threshold_raises_error(self) -> None:
        """Invalid conflict threshold should raise ValueError."""
        with pytest.raises(ValueError, match="conflict_threshold"):
            ConfidenceConfig(conflict_threshold=1.5)
    
    def test_custom_weights_accepted(self) -> None:
        """Custom weights summing to 1.0 should be accepted."""
        config = ConfidenceConfig(
            technical_weight=0.5,
            sentiment_weight=0.4,
            news_weight=0.1,
        )
        
        assert config.technical_weight == 0.5
        assert config.sentiment_weight == 0.4
        assert config.news_weight == 0.1


class TestIndicatorScore:
    """Tests for IndicatorScore dataclass."""
    
    def test_indicator_score_is_immutable(self) -> None:
        """IndicatorScore should be immutable (frozen)."""
        score = create_indicator("RSI", SignalDirection.BUY, 80.0, weight=1.0)
        
        with pytest.raises(AttributeError):
            score.confidence = 90.0  # type: ignore
    
    def test_indicator_score_default_values(self) -> None:
        """IndicatorScore should have correct default values."""
        score = IndicatorScore(
            name="RSI",
            signal=SignalDirection.BUY,
            confidence=80.0,
            weight=1.0,
        )
        
        assert score.value is None
        assert score.data_insufficient is False


class TestConfidenceResult:
    """Tests for ConfidenceResult dataclass."""
    
    def test_confidence_result_is_immutable(
        self, scorer: ConfidenceScorer
    ) -> None:
        """ConfidenceResult should be immutable (frozen)."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 80.0, weight=1.0),
        ]
        result = scorer.calculate_confidence(technical)
        
        with pytest.raises(AttributeError):
            result.confidence = 90.0  # type: ignore
    
    def test_confidence_result_default_values(
        self, scorer: ConfidenceScorer
    ) -> None:
        """ConfidenceResult should have correct default values."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 80.0, weight=1.0),
        ]
        result = scorer.calculate_confidence(technical)
        
        # conflict_detected defaults to False when no conflict
        assert result.conflict_detected is False


class TestEdgeCases:
    """Tests for edge cases."""
    
    def test_zero_confidence_indicators(self, scorer: ConfidenceScorer) -> None:
        """Zero confidence indicators should be handled correctly."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 0.0, weight=1.0),
        ]
        
        result = scorer.calculate_confidence(technical)
        
        assert result.breakdown.base_score == 0.0
        assert result.signal == SignalDirection.BUY  # Signal still determined
    
    def test_zero_weight_indicators(self, scorer: ConfidenceScorer) -> None:
        """Zero weight indicators should not affect score."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 100.0, weight=0.0),
            create_indicator("MACD", SignalDirection.BUY, 50.0, weight=1.0),
        ]
        
        result = scorer.calculate_confidence(technical)
        
        # Only MACD should contribute: 50% * 60% = 30%
        assert result.breakdown.technical_score == pytest.approx(30.0, rel=0.01)
    
    def test_single_indicator(self, scorer: ConfidenceScorer) -> None:
        """Single indicator should work correctly."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 80.0, weight=1.0),
        ]
        
        result = scorer.calculate_confidence(technical)
        
        assert result.signal == SignalDirection.BUY
        assert result.breakdown.agreeing_indicators == 1
        assert result.breakdown.total_indicators == 1
        # Full alignment bonus for single agreeing indicator
        assert result.breakdown.alignment_bonus == pytest.approx(10.0, rel=0.01)
    
    def test_none_sentiment_and_news(self, scorer: ConfidenceScorer) -> None:
        """None sentiment and news should be handled correctly."""
        technical = [
            create_indicator("RSI", SignalDirection.BUY, 80.0, weight=1.0),
        ]
        
        result = scorer.calculate_confidence(technical, None, None)
        
        assert result.breakdown.sentiment_score == 0.0
        assert result.breakdown.news_score == 0.0
