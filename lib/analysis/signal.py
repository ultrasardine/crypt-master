"""
Signal Generation Library.

This module provides the SignalGenerator class that combines technical analysis,
sentiment analysis, and confidence scoring to generate trading signals.

Requirements:
- 5.5: Only execute trades when confidence_score meets or exceeds the minimum threshold (default 85%)
- 5.1: Generate Signal containing direction (BUY/SELL/HOLD), confidence_score, and supporting_factors
- 5.6: Include all indicator values and their individual contributions to the confidence_score
- 3.1.1: SignalGenerator accepts optional ContextScores parameter
- 3.1.2: Context scores incorporated into confidence calculation with configurable weight
- 3.1.4: Strategy recommendations based on regime
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
    from lib.analysis.context import ContextScores, Regime


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
        regime: Market regime at time of signal (optional)
        context_scores: Dict of composite context scores (optional)
        recommended_bot_type: Context-recommended bot type (optional)

    Requirements:
    - 3.1.3: Signal dataclass extended with regime and context_scores fields
    - 3.1.5: Signal includes recommended_bot_type field
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
    regime: str | None = None
    context_scores: dict[str, float] | None = None
    recommended_bot_type: str | None = None


@dataclass
class SignalGeneratorConfig:
    """
    Configuration for SignalGenerator.

    Attributes:
        min_confidence_threshold: Minimum confidence to generate BUY/SELL signal (default 85%)
        confidence_config: Configuration for the underlying ConfidenceScorer
        context_weight: Weight for context scores in confidence calculation (default 15%)
        risk_off_threshold_offset: Additional threshold increase in RISK_OFF regime (default 10%)

    Requirements:
    - 3.1.2: Context scores weight configurable (default 15%)
    - 3.1.4: Risk-off threshold offset configurable (default 10%)
    """

    min_confidence_threshold: float = 85.0
    confidence_config: ConfidenceConfig | None = None
    context_weight: float = 15.0  # Percentage weight for context scores
    risk_off_threshold_offset: float = 10.0  # Additional threshold in RISK_OFF regime

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if not 0 <= self.min_confidence_threshold <= 100:
            raise ValueError(
                f"min_confidence_threshold must be between 0 and 100, "
                f"got {self.min_confidence_threshold}"
            )
        if not 0 <= self.context_weight <= 100:
            raise ValueError(
                f"context_weight must be between 0 and 100, "
                f"got {self.context_weight}"
            )
        if not 0 <= self.risk_off_threshold_offset <= 50:
            raise ValueError(
                f"risk_off_threshold_offset must be between 0 and 50, "
                f"got {self.risk_off_threshold_offset}"
            )


class SignalGenerator:
    """
    Signal generator that combines analysis sources into trading signals.

    Uses ConfidenceScorer to calculate confidence from technical indicators,
    sentiment analysis, and news sentiment. Enforces minimum confidence
    threshold (default 85%) - signals below threshold are converted to HOLD.

    When context is provided, the generator:
    - Incorporates context scores into confidence calculation (15% weight)
    - Recommends bot types based on regime (GRID for RANGE_BOUND, DCA for TRENDING_UP)
    - Increases confidence threshold in RISK_OFF regime (+10%)

    Requirements:
        - 5.5: Only execute trades when confidence_score meets or exceeds minimum threshold (default 85%)
        - 5.1: Generate Signal containing direction, confidence_score, and supporting_factors
        - 5.6: Include all indicator values and their individual contributions
        - 3.1.1: Accept optional ContextScores parameter
        - 3.1.2: Incorporate context scores with configurable weight (default 15%)
        - 3.1.4: Strategy recommendations based on regime

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
        context: "ContextScores | None" = None,
    ) -> Signal:
        """
        Generate a trading signal from analysis inputs.

        Combines technical indicators, sentiment, and news into a confidence
        score. If confidence is below the minimum threshold (default 85%),
        the signal direction is overridden to HOLD.

        When context is provided:
        - Context scores are incorporated into confidence with 15% weight
        - Bot type recommendations are made based on regime
        - RISK_OFF regime increases the confidence threshold by 10%

        Args:
            symbol: Trading pair symbol (e.g., "BTC_USDT")
            technical_scores: List of technical indicator scores
            sentiment_score: Optional sentiment analysis score
            news_score: Optional news sentiment score
            context: Optional context scores with regime information

        Returns:
            Signal with direction, confidence, and all metadata

        Requirements:
            - 5.5: Only execute trades when confidence >= threshold (default 85%)
            - 5.1: Generate Signal with direction, confidence, supporting_factors
            - 5.6: Include all indicator values and contributions
            - 3.1.1: Accept optional ContextScores parameter
            - 3.1.2: Incorporate context scores with 15% weight
            - 3.1.4: Strategy recommendations based on regime
        """
        # Calculate confidence using the scorer
        confidence_result = self._scorer.calculate_confidence(
            technical_scores=technical_scores,
            sentiment_score=sentiment_score,
            news_score=news_score,
        )

        # Determine effective threshold and adjust confidence based on context
        effective_threshold = self._get_effective_threshold(context)
        adjusted_confidence = self._adjust_confidence_with_context(
            confidence_result.confidence, context
        )

        # Check if confidence meets threshold
        meets_threshold = adjusted_confidence >= effective_threshold

        # Determine final signal direction
        # Requirement 5.5: Only execute trades when confidence meets threshold
        if meets_threshold:
            final_direction = confidence_result.signal
        else:
            final_direction = SignalDirection.HOLD

        # Determine recommended bot type based on context
        recommended_bot_type = self._get_recommended_bot_type(context)

        # Extract context metadata for signal
        regime_str: str | None = None
        context_scores_dict: dict[str, float] | None = None
        if context is not None:
            regime_str = context.regime.value
            context_scores_dict = {
                "trend_strength_score": context.trend_strength_score,
                "risk_regime_score": context.risk_regime_score,
                "sentiment_regime_score": context.sentiment_regime_score,
            }

        # Generate reasoning
        reasoning = self._generate_reasoning(
            confidence_result=confidence_result,
            meets_threshold=meets_threshold,
            threshold=effective_threshold,
            context=context,
            adjusted_confidence=adjusted_confidence,
        )

        return Signal(
            symbol=symbol,
            direction=final_direction,
            confidence=adjusted_confidence,
            timestamp=confidence_result.timestamp,
            indicators=confidence_result.breakdown.indicators,
            breakdown=confidence_result.breakdown,
            reasoning=reasoning,
            meets_threshold=meets_threshold,
            threshold_used=effective_threshold,
            regime=regime_str,
            context_scores=context_scores_dict,
            recommended_bot_type=recommended_bot_type,
        )

    def _get_effective_threshold(self, context: "ContextScores | None") -> float:
        """
        Get the effective confidence threshold based on context.

        In RISK_OFF regime, the threshold is increased by the configured offset.

        Args:
            context: Optional context scores with regime information

        Returns:
            Effective minimum confidence threshold

        Requirements:
        - 3.1.4: Increase min_confidence_threshold by 10% in RISK_OFF
        """
        base_threshold = self.config.min_confidence_threshold

        if context is None:
            return base_threshold

        # Import here to avoid circular imports
        from lib.analysis.context import Regime

        if context.regime == Regime.RISK_OFF:
            # Increase threshold in RISK_OFF regime, capped at 100
            return min(base_threshold + self.config.risk_off_threshold_offset, 100.0)

        return base_threshold

    def _adjust_confidence_with_context(
        self,
        base_confidence: float,
        context: "ContextScores | None",
    ) -> float:
        """
        Adjust confidence score by incorporating context scores.

        When context is available, context scores contribute 15% to the final
        confidence, reducing the base confidence contribution to 85%.

        Args:
            base_confidence: Original confidence from technical/sentiment analysis
            context: Optional context scores

        Returns:
            Adjusted confidence score (0-100)

        Requirements:
        - 3.1.2: Incorporate context scores with 15% weight
        """
        if context is None:
            return base_confidence

        # Import here to avoid circular imports
        from lib.analysis.context import Regime

        # If regime is UNKNOWN, fall back to base confidence
        if context.regime == Regime.UNKNOWN:
            return base_confidence

        # Calculate context contribution (average of three scores, scaled to 0-100)
        context_score = (
            (context.trend_strength_score + context.risk_regime_score +
             context.sentiment_regime_score) / 3.0
        ) * 100.0

        # Apply weights: base confidence gets (100 - context_weight)%, context gets context_weight%
        context_weight = self.config.context_weight / 100.0
        base_weight = 1.0 - context_weight

        adjusted = (base_confidence * base_weight) + (context_score * context_weight)

        # Ensure result is bounded
        return max(0.0, min(100.0, adjusted))

    def _get_recommended_bot_type(self, context: "ContextScores | None") -> str | None:
        """
        Determine recommended bot type based on market regime.

        Strategy recommendations:
        - RANGE_BOUND with neutral sentiment: GRID bots preferred
        - TRENDING_UP with RISK_ON indicators: DCA bots preferred
        - RISK_OFF: No new bots recommended (NONE)
        - Other regimes or no context: None (no recommendation)

        Args:
            context: Optional context scores with regime information

        Returns:
            Recommended bot type ("GRID", "DCA", "NONE") or None

        Requirements:
        - 3.1.4: GRID preferred in RANGE_BOUND regime
        - 3.1.4: DCA preferred in TRENDING_UP + RISK_ON
        - 3.1.4: No new bots in RISK_OFF
        """
        if context is None:
            return None

        # Import here to avoid circular imports
        from lib.analysis.context import Regime

        if context.regime == Regime.UNKNOWN:
            return None

        # RANGE_BOUND with neutral sentiment -> GRID
        if context.regime == Regime.RANGE_BOUND:
            # Check if sentiment is in neutral zone (between 0.4 and 0.6)
            if 0.4 <= context.sentiment_regime_score <= 0.6:
                return "GRID"
            # Even without neutral sentiment, GRID is still preferred in range-bound
            return "GRID"

        # TRENDING_UP -> DCA (especially with RISK_ON indicators)
        if context.regime == Regime.TRENDING_UP:
            # DCA is preferred in trending up markets
            return "DCA"

        # RISK_ON -> DCA (bullish conditions)
        if context.regime == Regime.RISK_ON:
            return "DCA"

        # RISK_OFF -> No new bots
        if context.regime == Regime.RISK_OFF:
            return "NONE"

        # TRENDING_DOWN -> No recommendation (cautious)
        if context.regime == Regime.TRENDING_DOWN:
            return "NONE"

        return None

    def _generate_reasoning(
        self,
        confidence_result: ConfidenceResult,
        meets_threshold: bool,
        threshold: float,
        context: "ContextScores | None" = None,
        adjusted_confidence: float | None = None,
    ) -> str:
        """
        Generate human-readable reasoning for the signal.

        Args:
            confidence_result: Result from confidence scorer
            meets_threshold: Whether confidence meets minimum threshold
            threshold: The minimum confidence threshold
            context: Optional context scores with regime information
            adjusted_confidence: Confidence after context adjustment

        Returns:
            Human-readable explanation string
        """
        base_reasoning = confidence_result.reasoning
        display_confidence = adjusted_confidence or confidence_result.confidence

        # Add context information if available
        context_info = ""
        if context is not None:
            context_info = (
                f" Market regime: {context.regime.value}. "
                f"Trend strength: {context.trend_strength_score:.2f}, "
                f"Risk: {context.risk_regime_score:.2f}, "
                f"Sentiment: {context.sentiment_regime_score:.2f}."
            )
            if context.is_degraded:
                context_info += " (Context data degraded)"

        if not meets_threshold:
            return (
                f"HOLD signal - confidence {display_confidence:.1f}% "
                f"below minimum threshold {threshold:.1f}%. "
                f"Original signal was {confidence_result.signal.value}. "
                f"{base_reasoning}{context_info}"
            )

        if confidence_result.conflict_detected:
            return (
                f"HOLD signal due to conflicting indicators. "
                f"Confidence: {display_confidence:.1f}%. "
                f"{base_reasoning}{context_info}"
            )

        return (
            f"{confidence_result.signal.value} signal with "
            f"{display_confidence:.1f}% confidence "
            f"(threshold: {threshold:.1f}%). "
            f"{base_reasoning}{context_info}"
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
        metadata = {
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

        # Add context-aware fields if present
        if signal.regime is not None:
            metadata["regime"] = signal.regime
        if signal.context_scores is not None:
            metadata["context_scores"] = signal.context_scores
        if signal.recommended_bot_type is not None:
            metadata["recommended_bot_type"] = signal.recommended_bot_type

        return metadata
