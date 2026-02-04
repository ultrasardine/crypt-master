"""
Confidence Scoring Library for Signal Generation.

This module provides confidence scoring by combining technical indicators,
sentiment analysis, and news sentiment into a weighted confidence score.

Requirements:
- 5.1: Generate trading signals combining technical and sentiment analysis
- 5.2: Calculate confidence score using weighted combination (technical 60%, sentiment 30%, news 10%)
- 5.3: Apply alignment bonus when multiple indicators agree (up to +10%)
- 5.4: Handle conflicting signals by defaulting to HOLD
- 5.6: Include all contributing factors in signal metadata
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from lib.analysis.technical import SignalDirection

if TYPE_CHECKING:
    pass


@dataclass(frozen=True)
class IndicatorScore:
    """
    Score from an individual indicator.

    Attributes:
        name: Name of the indicator (e.g., "RSI", "MACD", "FGI")
        signal: The signal direction from this indicator
        confidence: Confidence level for this indicator (0-100)
        weight: Weight assigned to this indicator in the overall calculation
        value: Optional raw value from the indicator
        data_insufficient: Whether the indicator had insufficient data
    """

    name: str
    signal: SignalDirection
    confidence: float
    weight: float
    value: float | None = None
    data_insufficient: bool = False


@dataclass(frozen=True)
class ConfidenceBreakdown:
    """
    Detailed breakdown of confidence score calculation.

    Attributes:
        technical_score: Weighted technical analysis score (0-100)
        sentiment_score: Weighted sentiment analysis score (0-100)
        news_score: Weighted news sentiment score (0-100)
        alignment_bonus: Bonus for indicator agreement (0-10)
        base_score: Score before alignment bonus
        final_score: Final confidence score after all adjustments
        indicators: List of all indicator scores used
        agreeing_indicators: Count of indicators agreeing with final signal
        total_indicators: Total number of indicators considered
    """

    technical_score: float
    sentiment_score: float
    news_score: float
    alignment_bonus: float
    base_score: float
    final_score: float
    indicators: tuple[IndicatorScore, ...]
    agreeing_indicators: int
    total_indicators: int


@dataclass(frozen=True)
class ConfidenceResult:
    """
    Result of confidence scoring.

    Attributes:
        signal: Final trading signal direction
        confidence: Final confidence score (0-100)
        breakdown: Detailed breakdown of the calculation
        timestamp: When the score was calculated
        conflict_detected: Whether conflicting signals were detected
        reasoning: Human-readable explanation of the result
    """

    signal: SignalDirection
    confidence: float
    breakdown: ConfidenceBreakdown
    timestamp: datetime
    conflict_detected: bool = False
    reasoning: str = ""


@dataclass
class ConfidenceConfig:
    """
    Configuration for ConfidenceScorer.

    Attributes:
        technical_weight: Weight for technical analysis (default 0.60 = 60%)
        sentiment_weight: Weight for sentiment analysis (default 0.30 = 30%)
        news_weight: Weight for news sentiment (default 0.10 = 10%)
        max_alignment_bonus: Maximum bonus for indicator alignment (default 10%)
        conflict_threshold: Minimum agreement ratio to avoid HOLD (default 0.5)
        min_confidence_for_signal: Minimum confidence to generate BUY/SELL (default 0)
    """

    technical_weight: float = 0.60
    sentiment_weight: float = 0.30
    news_weight: float = 0.10
    max_alignment_bonus: float = 10.0
    conflict_threshold: float = 0.5
    min_confidence_for_signal: float = 0.0

    def __post_init__(self) -> None:
        """Validate configuration values."""
        total_weight = self.technical_weight + self.sentiment_weight + self.news_weight
        if abs(total_weight - 1.0) > 0.001:
            raise ValueError(
                f"Weights must sum to 1.0, got {total_weight:.3f} "
                f"(technical={self.technical_weight}, sentiment={self.sentiment_weight}, "
                f"news={self.news_weight})"
            )

        if not 0 <= self.max_alignment_bonus <= 100:
            raise ValueError(
                f"max_alignment_bonus must be between 0 and 100, got {self.max_alignment_bonus}"
            )

        if not 0 <= self.conflict_threshold <= 1:
            raise ValueError(
                f"conflict_threshold must be between 0 and 1, got {self.conflict_threshold}"
            )


class ConfidenceScorer:
    """
    Confidence scorer that combines multiple analysis sources.

    Combines technical indicators, sentiment analysis, and news sentiment
    into a weighted confidence score. Applies alignment bonuses when
    indicators agree and handles conflicts by defaulting to HOLD.

    Requirements:
        - 5.1: Generate trading signals combining technical and sentiment analysis
        - 5.2: Calculate confidence score using weighted combination
        - 5.3: Apply alignment bonus when multiple indicators agree (up to +10%)
        - 5.4: Handle conflicting signals by defaulting to HOLD
        - 5.6: Include all contributing factors in signal metadata

    Example:
        >>> scorer = ConfidenceScorer()
        >>> technical_scores = [
        ...     IndicatorScore("RSI", SignalDirection.BUY, 80.0, 0.3),
        ...     IndicatorScore("MACD", SignalDirection.BUY, 75.0, 0.3),
        ... ]
        >>> sentiment = IndicatorScore("FGI", SignalDirection.BUY, 70.0, 1.0)
        >>> result = scorer.calculate_confidence(technical_scores, sentiment)
        >>> print(f"Signal: {result.signal}, Confidence: {result.confidence:.1f}%")
    """

    def __init__(self, config: ConfidenceConfig | None = None) -> None:
        """
        Initialize the ConfidenceScorer.

        Args:
            config: Optional configuration for scoring parameters.
                    Uses defaults if not provided.
        """
        self.config = config or ConfidenceConfig()

    def calculate_confidence(
        self,
        technical_scores: list[IndicatorScore],
        sentiment_score: IndicatorScore | None = None,
        news_score: IndicatorScore | None = None,
    ) -> ConfidenceResult:
        """
        Calculate overall confidence score from multiple indicators.

        Combines technical indicators, sentiment, and news into a weighted
        confidence score. Applies alignment bonus when indicators agree
        and defaults to HOLD when significant conflicts are detected.

        Args:
            technical_scores: List of technical indicator scores
            sentiment_score: Optional sentiment analysis score
            news_score: Optional news sentiment score

        Returns:
            ConfidenceResult with signal, confidence, and detailed breakdown

        Requirements:
            - 5.1: Generate trading signals combining technical and sentiment
            - 5.2: Calculate weighted confidence score
            - 5.3: Apply alignment bonus for agreeing indicators
            - 5.4: Handle conflicts with HOLD signal
            - 5.6: Include all contributing factors
        """
        # Collect all indicators
        all_indicators: list[IndicatorScore] = []
        all_indicators.extend(technical_scores)
        if sentiment_score is not None:
            all_indicators.append(sentiment_score)
        if news_score is not None:
            all_indicators.append(news_score)

        # Filter out indicators with insufficient data
        valid_indicators = [ind for ind in all_indicators if not ind.data_insufficient]

        # If no valid indicators, return HOLD with zero confidence
        if not valid_indicators:
            return self._create_no_data_result(all_indicators)

        # Calculate weighted scores for each category
        technical_weighted = self._calculate_category_score(
            [ind for ind in technical_scores if not ind.data_insufficient]
        )
        sentiment_weighted = self._calculate_single_score(sentiment_score)
        news_weighted = self._calculate_single_score(news_score)

        # Determine the dominant signal direction
        signal_counts = self._count_signals(valid_indicators)
        dominant_signal, conflict_detected = self._determine_signal(signal_counts, valid_indicators)

        # Calculate base confidence score
        base_score = self._calculate_base_score(
            technical_weighted,
            sentiment_weighted,
            news_weighted,
        )

        # Calculate alignment bonus
        agreeing_count = self._count_agreeing_indicators(valid_indicators, dominant_signal)
        alignment_bonus = self._calculate_alignment_bonus(agreeing_count, len(valid_indicators))

        # Apply conflict penalty - if conflict detected, no alignment bonus
        if conflict_detected:
            alignment_bonus = 0.0

        # Calculate final score (capped at 100)
        final_score = min(100.0, base_score + alignment_bonus)

        # If conflict detected, override signal to HOLD
        final_signal = SignalDirection.HOLD if conflict_detected else dominant_signal

        # Build breakdown
        breakdown = ConfidenceBreakdown(
            technical_score=technical_weighted * self.config.technical_weight * 100,
            sentiment_score=sentiment_weighted * self.config.sentiment_weight * 100,
            news_score=news_weighted * self.config.news_weight * 100,
            alignment_bonus=alignment_bonus,
            base_score=base_score,
            final_score=final_score,
            indicators=tuple(all_indicators),
            agreeing_indicators=agreeing_count,
            total_indicators=len(valid_indicators),
        )

        # Generate reasoning
        reasoning = self._generate_reasoning(final_signal, conflict_detected, breakdown)

        return ConfidenceResult(
            signal=final_signal,
            confidence=final_score,
            breakdown=breakdown,
            timestamp=datetime.now(tz=UTC),
            conflict_detected=conflict_detected,
            reasoning=reasoning,
        )

    def _calculate_category_score(self, indicators: list[IndicatorScore]) -> float:
        """
        Calculate weighted average score for a category of indicators.

        Args:
            indicators: List of indicator scores in the category

        Returns:
            Weighted average confidence (0-1 scale)
        """
        if not indicators:
            return 0.0

        total_weight = sum(ind.weight for ind in indicators)
        if total_weight == 0:
            return 0.0

        weighted_sum = sum(ind.confidence * ind.weight for ind in indicators)

        # Normalize to 0-1 scale
        return (weighted_sum / total_weight) / 100.0

    def _calculate_single_score(self, indicator: IndicatorScore | None) -> float:
        """
        Calculate score for a single indicator.

        Args:
            indicator: Single indicator score or None

        Returns:
            Confidence on 0-1 scale, or 0 if None/insufficient
        """
        if indicator is None or indicator.data_insufficient:
            return 0.0

        return indicator.confidence / 100.0

    def _count_signals(self, indicators: list[IndicatorScore]) -> dict[SignalDirection, int]:
        """
        Count occurrences of each signal direction.

        Args:
            indicators: List of indicator scores

        Returns:
            Dictionary mapping signal direction to count
        """
        counts: dict[SignalDirection, int] = {
            SignalDirection.BUY: 0,
            SignalDirection.SELL: 0,
            SignalDirection.HOLD: 0,
        }

        for ind in indicators:
            counts[ind.signal] += 1

        return counts

    def _determine_signal(
        self,
        signal_counts: dict[SignalDirection, int],
        indicators: list[IndicatorScore],
    ) -> tuple[SignalDirection, bool]:
        """
        Determine the dominant signal and detect conflicts.

        A conflict is detected when BUY and SELL signals both have
        significant representation (above conflict_threshold).

        Args:
            signal_counts: Count of each signal direction
            indicators: List of all indicators

        Returns:
            Tuple of (dominant_signal, conflict_detected)

        Requirements:
            - 5.4: Handle conflicting signals by defaulting to HOLD
        """
        total = len(indicators)
        if total == 0:
            return SignalDirection.HOLD, False

        buy_ratio = signal_counts[SignalDirection.BUY] / total
        sell_ratio = signal_counts[SignalDirection.SELL] / total

        # Detect conflict: both BUY and SELL have significant presence
        conflict_detected = (
            buy_ratio >= self.config.conflict_threshold
            and sell_ratio >= self.config.conflict_threshold
        )

        if conflict_detected:
            return SignalDirection.HOLD, True

        # Determine dominant signal (excluding HOLD from dominance)
        if signal_counts[SignalDirection.BUY] > signal_counts[SignalDirection.SELL]:
            return SignalDirection.BUY, False
        elif signal_counts[SignalDirection.SELL] > signal_counts[SignalDirection.BUY]:
            return SignalDirection.SELL, False
        else:
            # Equal BUY and SELL, or all HOLD
            return SignalDirection.HOLD, False

    def _calculate_base_score(
        self,
        technical: float,
        sentiment: float,
        news: float,
    ) -> float:
        """
        Calculate base confidence score from weighted components.

        Args:
            technical: Technical score (0-1)
            sentiment: Sentiment score (0-1)
            news: News score (0-1)

        Returns:
            Base confidence score (0-100)

        Requirements:
            - 5.2: Calculate confidence using weighted combination
        """
        weighted_score = (
            technical * self.config.technical_weight
            + sentiment * self.config.sentiment_weight
            + news * self.config.news_weight
        )

        return weighted_score * 100.0

    def _count_agreeing_indicators(
        self,
        indicators: list[IndicatorScore],
        signal: SignalDirection,
    ) -> int:
        """
        Count indicators that agree with the given signal.

        Args:
            indicators: List of indicator scores
            signal: Signal direction to check agreement with

        Returns:
            Number of agreeing indicators
        """
        return sum(1 for ind in indicators if ind.signal == signal)

    def _calculate_alignment_bonus(
        self,
        agreeing_count: int,
        total_count: int,
    ) -> float:
        """
        Calculate alignment bonus based on indicator agreement.

        The bonus scales linearly from 0 to max_alignment_bonus based on
        the proportion of agreeing indicators.

        Args:
            agreeing_count: Number of indicators agreeing with signal
            total_count: Total number of indicators

        Returns:
            Alignment bonus (0 to max_alignment_bonus)

        Requirements:
            - 5.3: Apply alignment bonus when multiple indicators agree (up to +10%)
        """
        if total_count == 0:
            return 0.0

        agreement_ratio = agreeing_count / total_count

        # Scale bonus based on agreement ratio
        # Full bonus only when all indicators agree
        return agreement_ratio * self.config.max_alignment_bonus

    def _generate_reasoning(
        self,
        signal: SignalDirection,
        conflict_detected: bool,
        breakdown: ConfidenceBreakdown,
    ) -> str:
        """
        Generate human-readable reasoning for the result.

        Args:
            signal: Final signal direction
            conflict_detected: Whether conflicts were detected
            breakdown: Detailed score breakdown

        Returns:
            Human-readable explanation string
        """
        if conflict_detected:
            return (
                f"HOLD signal due to conflicting indicators. "
                f"{breakdown.agreeing_indicators}/{breakdown.total_indicators} "
                f"indicators agree. Base score: {breakdown.base_score:.1f}%"
            )

        if signal == SignalDirection.HOLD:
            return (
                f"HOLD signal - no clear directional consensus. "
                f"Base score: {breakdown.base_score:.1f}%"
            )

        return (
            f"{signal.value} signal with {breakdown.final_score:.1f}% confidence. "
            f"{breakdown.agreeing_indicators}/{breakdown.total_indicators} "
            f"indicators agree (+{breakdown.alignment_bonus:.1f}% bonus). "
            f"Technical: {breakdown.technical_score:.1f}%, "
            f"Sentiment: {breakdown.sentiment_score:.1f}%, "
            f"News: {breakdown.news_score:.1f}%"
        )

    def _create_no_data_result(self, indicators: list[IndicatorScore]) -> ConfidenceResult:
        """
        Create a result when no valid data is available.

        Args:
            indicators: List of all indicators (all with insufficient data)

        Returns:
            ConfidenceResult with HOLD signal and zero confidence
        """
        breakdown = ConfidenceBreakdown(
            technical_score=0.0,
            sentiment_score=0.0,
            news_score=0.0,
            alignment_bonus=0.0,
            base_score=0.0,
            final_score=0.0,
            indicators=tuple(indicators),
            agreeing_indicators=0,
            total_indicators=0,
        )

        return ConfidenceResult(
            signal=SignalDirection.HOLD,
            confidence=0.0,
            breakdown=breakdown,
            timestamp=datetime.now(tz=UTC),
            conflict_detected=False,
            reasoning="HOLD signal - insufficient data from all indicators",
        )
