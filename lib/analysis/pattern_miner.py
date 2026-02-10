"""
Pattern Mining Library.

This module provides the PatternMiner class that analyzes historical signals
and their outcomes to discover winning strategy patterns.

Requirements:
- 3.3.2: Query historical Signal records with associated Trade outcomes
- 3.3.3: Group signals by regime and indicator ranges, calculate win rate and avg P&L
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING

from django.db.models import Avg, Count, Q
from django.utils import timezone

if TYPE_CHECKING:
    from apps.trading.models import StrategyPattern

logger = logging.getLogger(__name__)


@dataclass
class PatternMinerConfig:
    """
    Configuration for PatternMiner.

    Attributes:
        min_sample_size: Minimum number of signals required to form a pattern (default: 30)
        min_hit_rate: Minimum win rate to store a pattern (default: 0.55)
        min_avg_pnl: Minimum average P&L percentage to store a pattern (default: 0.5)
        lookback_days: Number of days to look back for historical data (default: 90)
        feature_keys: List of feature keys to analyze for pattern discovery

    Requirements:
    - 3.3.4: Configurable thresholds for pattern storage
    """

    min_sample_size: int = 30
    min_hit_rate: float = 0.55
    min_avg_pnl: float = 0.5  # percent
    lookback_days: int = 90
    feature_keys: list[str] = field(
        default_factory=lambda: [
            "regime",
            "trend_strength_score",
            "risk_regime_score",
            "sentiment_regime_score",
            "fear_greed_bucket",
        ]
    )

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.min_sample_size < 1:
            raise ValueError(f"min_sample_size must be >= 1, got {self.min_sample_size}")
        if not 0.0 <= self.min_hit_rate <= 1.0:
            raise ValueError(f"min_hit_rate must be between 0.0 and 1.0, got {self.min_hit_rate}")
        if self.lookback_days < 1:
            raise ValueError(f"lookback_days must be >= 1, got {self.lookback_days}")


@dataclass
class PatternCandidate:
    """
    A candidate pattern discovered during mining.

    Attributes:
        feature_combination: Dict of feature names to values/ranges
        sample_size: Number of signals matching this pattern
        hit_rate: Fraction of profitable signals
        average_pnl: Average P&L percentage
    """

    feature_combination: dict
    sample_size: int
    hit_rate: float
    average_pnl: float


class PatternMiner:
    """
    Pattern miner that analyzes historical signals and outcomes to discover
    winning strategy patterns.

    The miner:
    1. Queries historical Signal records with associated SignalOutcome data
    2. Groups signals by regime and indicator ranges
    3. Calculates win rate and average P&L for each group
    4. Stores groups meeting thresholds as StrategyPattern records

    Requirements:
    - 3.3.2: Query historical Signal records with associated Trade outcomes
    - 3.3.3: Group signals by regime and indicator ranges
    """

    def __init__(self, config: PatternMinerConfig | None = None) -> None:
        """
        Initialize the PatternMiner.

        Args:
            config: Optional configuration for pattern mining.
                    Uses defaults if not provided.
        """
        self.config = config or PatternMinerConfig()

    def discover_patterns(self, dry_run: bool = False) -> list["StrategyPattern"]:
        """
        Discover winning strategy patterns from historical data.

        Analyzes historical signals with outcomes, groups them by regime
        and indicator ranges, and stores patterns that meet the configured
        thresholds.

        Args:
            dry_run: If True, preview patterns without saving to database

        Returns:
            List of discovered StrategyPattern instances

        Requirements:
        - 3.3.2: Query historical Signal records with associated Trade outcomes
        - 3.3.3: Group signals by regime and indicator ranges
        - 3.3.4: Store groups meeting thresholds as StrategyPattern records
        """
        from apps.trading.models import Signal, SignalOutcome, StrategyPattern

        # Calculate lookback cutoff
        cutoff = timezone.now() - timedelta(days=self.config.lookback_days)

        # Query signals with outcomes
        signals_with_outcomes = Signal.objects.filter(
            created_at__gte=cutoff,
            outcome__isnull=False,
            regime__isnull=False,
        ).select_related("outcome")

        if not signals_with_outcomes.exists():
            logger.warning("No signals with outcomes found for pattern mining")
            return []

        # Group signals by regime and analyze
        candidates = self._analyze_by_regime(signals_with_outcomes)

        # Filter candidates by thresholds
        valid_candidates = [
            c
            for c in candidates
            if c.sample_size >= self.config.min_sample_size
            and c.hit_rate >= self.config.min_hit_rate
            and c.average_pnl >= self.config.min_avg_pnl
        ]

        logger.info(
            f"Pattern mining found {len(candidates)} candidates, "
            f"{len(valid_candidates)} meet thresholds"
        )

        if dry_run:
            # Return unsaved pattern instances for preview
            return [
                StrategyPattern(
                    feature_combination=c.feature_combination,
                    sample_size=c.sample_size,
                    hit_rate=c.hit_rate,
                    average_pnl=c.average_pnl,
                    is_active=True,
                )
                for c in valid_candidates
            ]

        # Create and save patterns
        patterns = []
        for candidate in valid_candidates:
            pattern = StrategyPattern.objects.create(
                feature_combination=candidate.feature_combination,
                sample_size=candidate.sample_size,
                hit_rate=candidate.hit_rate,
                average_pnl=candidate.average_pnl,
                is_active=True,
            )
            patterns.append(pattern)
            logger.info(f"Created pattern: {pattern}")

        return patterns

    def _analyze_by_regime(self, signals) -> list[PatternCandidate]:
        """
        Analyze signals grouped by regime.

        Args:
            signals: QuerySet of Signal objects with outcomes

        Returns:
            List of PatternCandidate instances
        """
        candidates = []

        # Get unique regimes
        regimes = signals.values_list("regime", flat=True).distinct()

        for regime in regimes:
            if not regime:
                continue

            regime_signals = signals.filter(regime=regime)
            candidate = self._analyze_signal_group(regime_signals, {"regime": regime})

            if candidate:
                candidates.append(candidate)

            # Further analyze by context score ranges within each regime
            candidates.extend(self._analyze_by_context_scores(regime_signals, regime))

        return candidates

    def _analyze_by_context_scores(self, signals, regime: str) -> list[PatternCandidate]:
        """
        Analyze signals by context score ranges within a regime.

        Args:
            signals: QuerySet of Signal objects for a specific regime
            regime: The regime being analyzed

        Returns:
            List of PatternCandidate instances
        """
        candidates = []

        # Define score buckets for analysis
        score_buckets = [
            ("low", 0.0, 0.33),
            ("medium", 0.33, 0.66),
            ("high", 0.66, 1.0),
        ]

        # Analyze by trend strength buckets
        for bucket_name, low, high in score_buckets:
            bucket_signals = signals.filter(
                context_scores__trend_strength_score__gte=low,
                context_scores__trend_strength_score__lt=high,
            )

            if bucket_signals.count() >= self.config.min_sample_size:
                candidate = self._analyze_signal_group(
                    bucket_signals,
                    {
                        "regime": regime,
                        "trend_strength_bucket": bucket_name,
                        "trend_strength_range": [low, high],
                    },
                )
                if candidate:
                    candidates.append(candidate)

        # Analyze by risk regime buckets
        for bucket_name, low, high in score_buckets:
            bucket_signals = signals.filter(
                context_scores__risk_regime_score__gte=low,
                context_scores__risk_regime_score__lt=high,
            )

            if bucket_signals.count() >= self.config.min_sample_size:
                candidate = self._analyze_signal_group(
                    bucket_signals,
                    {
                        "regime": regime,
                        "risk_regime_bucket": bucket_name,
                        "risk_regime_range": [low, high],
                    },
                )
                if candidate:
                    candidates.append(candidate)

        # Analyze by sentiment regime buckets
        for bucket_name, low, high in score_buckets:
            bucket_signals = signals.filter(
                context_scores__sentiment_regime_score__gte=low,
                context_scores__sentiment_regime_score__lt=high,
            )

            if bucket_signals.count() >= self.config.min_sample_size:
                candidate = self._analyze_signal_group(
                    bucket_signals,
                    {
                        "regime": regime,
                        "sentiment_regime_bucket": bucket_name,
                        "sentiment_regime_range": [low, high],
                    },
                )
                if candidate:
                    candidates.append(candidate)

        return candidates

    def _analyze_signal_group(
        self,
        signals,
        feature_combination: dict,
    ) -> PatternCandidate | None:
        """
        Analyze a group of signals and create a pattern candidate.

        Args:
            signals: QuerySet of Signal objects
            feature_combination: Dict describing the feature combination

        Returns:
            PatternCandidate if group has enough samples, None otherwise
        """
        count = signals.count()

        if count < self.config.min_sample_size:
            return None

        # Calculate metrics from outcomes
        profitable_count = signals.filter(outcome__is_profitable=True).count()
        hit_rate = profitable_count / count if count > 0 else 0.0

        # Calculate average P&L
        avg_pnl_result = signals.filter(
            outcome__final_pnl_percent__isnull=False
        ).aggregate(avg_pnl=Avg("outcome__final_pnl_percent"))

        average_pnl = avg_pnl_result["avg_pnl"] or 0.0

        return PatternCandidate(
            feature_combination=feature_combination,
            sample_size=count,
            hit_rate=hit_rate,
            average_pnl=average_pnl,
        )

    def get_matching_patterns(
        self,
        regime: str,
        context_scores: dict[str, float] | None = None,
    ) -> list["StrategyPattern"]:
        """
        Get active patterns that match the given regime and context scores.

        Args:
            regime: Current market regime
            context_scores: Optional dict of context scores

        Returns:
            List of matching StrategyPattern instances, ordered by hit_rate
        """
        from apps.trading.models import StrategyPattern

        # Start with active patterns for the regime
        patterns = StrategyPattern.objects.active().for_regime(regime)

        if not context_scores:
            return list(patterns)

        # Filter by context score ranges if available
        matching = []
        for pattern in patterns:
            if self._pattern_matches_context(pattern, context_scores):
                matching.append(pattern)

        return matching

    def _pattern_matches_context(
        self,
        pattern: "StrategyPattern",
        context_scores: dict[str, float],
    ) -> bool:
        """
        Check if a pattern matches the given context scores.

        Args:
            pattern: StrategyPattern to check
            context_scores: Dict of context scores

        Returns:
            True if pattern matches, False otherwise
        """
        fc = pattern.feature_combination

        # Check trend strength range
        if "trend_strength_range" in fc:
            low, high = fc["trend_strength_range"]
            score = context_scores.get("trend_strength_score", 0.5)
            if not (low <= score < high):
                return False

        # Check risk regime range
        if "risk_regime_range" in fc:
            low, high = fc["risk_regime_range"]
            score = context_scores.get("risk_regime_score", 0.5)
            if not (low <= score < high):
                return False

        # Check sentiment regime range
        if "sentiment_regime_range" in fc:
            low, high = fc["sentiment_regime_range"]
            score = context_scores.get("sentiment_regime_score", 0.5)
            if not (low <= score < high):
                return False

        return True
