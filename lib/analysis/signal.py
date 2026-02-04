"""
Signal Generation Library.

This module provides the SignalGenerator class that combines technical analysis,
sentiment analysis, and confidence scoring to generate trading signals.

Requirements:
- 5.5: Only execute trades when confidence_score meets or exceeds the minimum threshold (default 85%)
- 5.1: Generate Signal containing direction (BUY/SELL/HOLD), confidence_score, and supporting_factors
- 5.6: Include all indicator values and their individual contributions to the confidence_score
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from lib.analysis.confidence import (
    ConfidenceBreakdown,
    ConfidenceConfig,
    ConfidenceResult,
    ConfidenceScorer,
    IndicatorScore,
)
from lib.analysis.technical import SignalDirection

if TYPE_CHECKING:
    pass


@dataclass(frozen=True)
class Signal:
    """
    Trading signal with all metadata.
    
    Attributes:
        symbol: Trading pair symbol (e.g., "BTC_USDT")
        direction: Signal direction (BUY/SELL/HOLD)
        confidence: Confidence score (0-100)
        timestamp: When the signal was generated
        indicators: List of all indicator scores used
        breakdown: Detailed confidence breakdown
        reasoning: Human-readable explanation
        meets_threshold: Whether confidence meets minimum threshold
        threshold_used: The minimum confidence threshold that was applied
    """
    symbol: str
    direction: SignalDirection
    confidence: float
    timestamp: datetime
    indicators: tuple[IndicatorScore, ...]
    breakdown: ConfidenceBreakdown
    reasoning: str
    meets_threshold: bool
    threshold_used: float


@dataclass
class SignalGeneratorConfig:
    """
    Configuration for SignalGenerator.
    
    Attributes:
        min_confidence_threshold: Minimum confidence to generate BUY/SELL signal (default 85%)
        confidence_config: Configuration for the underlying ConfidenceScorer
    """
    min_confidence_threshold: float = 85.0
    confidence_config: ConfidenceConfig | None = None
    
    def __post_init__(self) -> None:
        """Validate configuration values."""
        if not 0 <= self.min_confidence_threshold <= 100:
            raise ValueError(
                f"min_confidence_threshold must be between 0 and 100, "
                f"got {self.min_confidence_threshold}"
            )


class SignalGenerator:
    """
    Signal generator that combines analysis sources into trading signals.
    
    Uses ConfidenceScorer to calculate confidence from technical indicators,
    sentiment analysis, and news sentiment. Enforces minimum confidence
    threshold (default 85%) - signals below threshold are converted to HOLD.
    
    Requirements:
        - 5.5: Only execute trades when confidence_score meets or exceeds minimum threshold (default 85%)
        - 5.1: Generate Signal containing direction, confidence_score, and supporting_factors
        - 5.6: Include all indicator values and their individual contributions
    
    Example:
        >>> generator = SignalGenerator()
        >>> technical_scores = [
        ...     IndicatorScore("RSI", SignalDirection.BUY, 90.0, 0.3),
        ...     IndicatorScore("MACD", SignalDirection.BUY, 85.0, 0.3),
        ... ]
        >>> sentiment = IndicatorScore("FGI", SignalDirection.BUY, 80.0, 1.0)
        >>> signal = generator.generate_signal("BTC_USDT", technical_scores, sentiment)
        >>> print(f"Signal: {signal.direction}, Confidence: {signal.confidence:.1f}%")
    """
    
    def __init__(self, config: SignalGeneratorConfig | None = None) -> None:
        """
        Initialize the SignalGenerator.
        
        Args:
            config: Optional configuration for signal generation.
                    Uses defaults if not provided.
        """
        self.config = config or SignalGeneratorConfig()
        self._scorer = ConfidenceScorer(config=self.config.confidence_config)
    
    @property
    def min_confidence_threshold(self) -> float:
        """Get the minimum confidence threshold."""
        return self.config.min_confidence_threshold
    
    def generate_signal(
        self,
        symbol: str,
        technical_scores: list[IndicatorScore],
        sentiment_score: IndicatorScore | None = None,
        news_score: IndicatorScore | None = None,
    ) -> Signal:
        """
        Generate a trading signal from analysis inputs.
        
        Combines technical indicators, sentiment, and news into a confidence
        score. If confidence is below the minimum threshold (default 85%),
        the signal direction is overridden to HOLD.
        
        Args:
            symbol: Trading pair symbol (e.g., "BTC_USDT")
            technical_scores: List of technical indicator scores
            sentiment_score: Optional sentiment analysis score
            news_score: Optional news sentiment score
            
        Returns:
            Signal with direction, confidence, and all metadata
            
        Requirements:
            - 5.5: Only execute trades when confidence >= threshold (default 85%)
            - 5.1: Generate Signal with direction, confidence, supporting_factors
            - 5.6: Include all indicator values and contributions
        """
        # Calculate confidence using the scorer
        confidence_result = self._scorer.calculate_confidence(
            technical_scores=technical_scores,
            sentiment_score=sentiment_score,
            news_score=news_score,
        )
        
        # Check if confidence meets threshold
        meets_threshold = confidence_result.confidence >= self.config.min_confidence_threshold
        
        # Determine final signal direction
        # Requirement 5.5: Only execute trades when confidence meets threshold
        if meets_threshold:
            final_direction = confidence_result.signal
        else:
            final_direction = SignalDirection.HOLD
        
        # Generate reasoning
        reasoning = self._generate_reasoning(
            confidence_result=confidence_result,
            meets_threshold=meets_threshold,
            threshold=self.config.min_confidence_threshold,
        )
        
        return Signal(
            symbol=symbol,
            direction=final_direction,
            confidence=confidence_result.confidence,
            timestamp=confidence_result.timestamp,
            indicators=confidence_result.breakdown.indicators,
            breakdown=confidence_result.breakdown,
            reasoning=reasoning,
            meets_threshold=meets_threshold,
            threshold_used=self.config.min_confidence_threshold,
        )
    
    def _generate_reasoning(
        self,
        confidence_result: ConfidenceResult,
        meets_threshold: bool,
        threshold: float,
    ) -> str:
        """
        Generate human-readable reasoning for the signal.
        
        Args:
            confidence_result: Result from confidence scorer
            meets_threshold: Whether confidence meets minimum threshold
            threshold: The minimum confidence threshold
            
        Returns:
            Human-readable explanation string
        """
        base_reasoning = confidence_result.reasoning
        
        if not meets_threshold:
            return (
                f"HOLD signal - confidence {confidence_result.confidence:.1f}% "
                f"below minimum threshold {threshold:.1f}%. "
                f"Original signal was {confidence_result.signal.value}. "
                f"{base_reasoning}"
            )
        
        if confidence_result.conflict_detected:
            return (
                f"HOLD signal due to conflicting indicators. "
                f"Confidence: {confidence_result.confidence:.1f}%. "
                f"{base_reasoning}"
            )
        
        return (
            f"{confidence_result.signal.value} signal with "
            f"{confidence_result.confidence:.1f}% confidence "
            f"(threshold: {threshold:.1f}%). "
            f"{base_reasoning}"
        )
    
    def would_execute(self, signal: Signal) -> bool:
        """
        Check if a signal would result in trade execution.
        
        A signal results in execution only if:
        1. Direction is BUY or SELL (not HOLD)
        2. Confidence meets or exceeds the minimum threshold
        
        Args:
            signal: The signal to check
            
        Returns:
            True if the signal would trigger a trade execution
            
        Requirements:
            - 5.5: Only execute trades when confidence >= threshold
        """
        return (
            signal.direction in (SignalDirection.BUY, SignalDirection.SELL)
            and signal.meets_threshold
        )
    
    def get_signal_metadata(self, signal: Signal) -> dict:
        """
        Get signal metadata as a dictionary for logging/storage.
        
        Args:
            signal: The signal to extract metadata from
            
        Returns:
            Dictionary with all signal metadata
            
        Requirements:
            - 5.6: Include all indicator values and contributions
        """
        return {
            "symbol": signal.symbol,
            "direction": signal.direction.value,
            "confidence": signal.confidence,
            "timestamp": signal.timestamp.isoformat(),
            "meets_threshold": signal.meets_threshold,
            "threshold_used": signal.threshold_used,
            "reasoning": signal.reasoning,
            "breakdown": {
                "technical_score": signal.breakdown.technical_score,
                "sentiment_score": signal.breakdown.sentiment_score,
                "news_score": signal.breakdown.news_score,
                "alignment_bonus": signal.breakdown.alignment_bonus,
                "base_score": signal.breakdown.base_score,
                "final_score": signal.breakdown.final_score,
                "agreeing_indicators": signal.breakdown.agreeing_indicators,
                "total_indicators": signal.breakdown.total_indicators,
            },
            "indicators": [
                {
                    "name": ind.name,
                    "signal": ind.signal.value,
                    "confidence": ind.confidence,
                    "weight": ind.weight,
                    "value": ind.value,
                    "data_insufficient": ind.data_insufficient,
                }
                for ind in signal.indicators
            ],
        }
