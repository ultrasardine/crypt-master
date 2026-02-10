"""
Context Scoring and Regime Detection Library.

This module provides the ContextScorer class that combines technical indicators,
external market metrics, and sentiment data to produce composite context scores
and classify market regimes.

Requirements:
- 2.1.1: ContextScorer class in lib/analysis/context.py
- 2.1.7: All weights and thresholds configurable via ContextScorerConfig
- 2.2.1: MarketRegime enum with regime values
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Regime(Enum):
    """
    Market regime classification.

    Requirements:
    - 2.2.1: MarketRegime enum with values for different market conditions
    """

    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    RANGE_BOUND = "RANGE_BOUND"
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ContextScores:
    """
    Composite context scores and regime classification.

    All scores are normalized to 0.0-1.0 range.

    Attributes:
        trend_strength_score: Composite trend strength (0.0-1.0)
        risk_regime_score: Composite risk regime (0.0-1.0)
        sentiment_regime_score: Composite sentiment regime (0.0-1.0)
        regime: Classified market regime
        is_degraded: True if any input was stale

    Requirements:
    - 2.1.2: ContextScores dataclass with trend, risk, sentiment scores and regime
    """

    trend_strength_score: float
    risk_regime_score: float
    sentiment_regime_score: float
    regime: Regime
    is_degraded: bool


@dataclass
class ContextScorerConfig:
    """
    Configuration for ContextScorer with all thresholds and weights.

    Requirements:
    - 2.1.7: All weights and thresholds configurable via dataclass
    """

    # Regime classification thresholds
    risk_on_threshold: float = 0.65
    risk_off_threshold: float = 0.35
    trend_strong_threshold: float = 0.6
    trend_weak_threshold: float = 0.4
    sentiment_positive_threshold: float = 0.6
    sentiment_negative_threshold: float = 0.4

    # Trend strength weights (must sum to 1.0)
    ta_weight_trend: float = 0.5
    onchain_weight_trend: float = 0.3
    volume_weight_trend: float = 0.2

    # Risk regime weights (must sum to 1.0)
    fgi_weight_risk: float = 0.3
    exchange_flow_weight_risk: float = 0.3
    tvl_weight_risk: float = 0.2
    volatility_weight_risk: float = 0.2

    # Sentiment regime weights (must sum to 1.0)
    social_weight_sentiment: float = 0.5
    fgi_weight_sentiment: float = 0.3
    news_weight_sentiment: float = 0.2

    def __post_init__(self) -> None:
        """Validate configuration values."""
        # Validate thresholds are in valid range
        thresholds = [
            ("risk_on_threshold", self.risk_on_threshold),
            ("risk_off_threshold", self.risk_off_threshold),
            ("trend_strong_threshold", self.trend_strong_threshold),
            ("trend_weak_threshold", self.trend_weak_threshold),
            ("sentiment_positive_threshold", self.sentiment_positive_threshold),
            ("sentiment_negative_threshold", self.sentiment_negative_threshold),
        ]

        for name, value in thresholds:
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0.0 and 1.0, got {value}")

        # Validate weights are non-negative
        weights = [
            ("ta_weight_trend", self.ta_weight_trend),
            ("onchain_weight_trend", self.onchain_weight_trend),
            ("volume_weight_trend", self.volume_weight_trend),
            ("fgi_weight_risk", self.fgi_weight_risk),
            ("exchange_flow_weight_risk", self.exchange_flow_weight_risk),
            ("tvl_weight_risk", self.tvl_weight_risk),
            ("volatility_weight_risk", self.volatility_weight_risk),
            ("social_weight_sentiment", self.social_weight_sentiment),
            ("fgi_weight_sentiment", self.fgi_weight_sentiment),
            ("news_weight_sentiment", self.news_weight_sentiment),
        ]

        for name, value in weights:
            if value < 0.0:
                raise ValueError(f"{name} must be non-negative, got {value}")


class ContextScorer:
    """
    Context scorer that combines technical indicators, external metrics,
    and sentiment data to produce composite scores and regime classification.

    Requirements:
    - 2.1.2: Accepts MarketContextSnapshot and TA indicators, outputs ContextScores
    - 2.1.3: trend_strength_score from ADX, Bollinger Bands, MACD histogram
    - 2.1.4: risk_regime_score from Fear & Greed Index, exchange flow, BTC dominance
    - 2.1.5: sentiment_regime_score from social sentiment, buzz, news
    - 2.1.8: Gracefully handles missing data by adjusting weights
    """

    def __init__(self, config: ContextScorerConfig | None = None) -> None:
        """
        Initialize the ContextScorer.

        Args:
            config: Optional configuration for scoring. Uses defaults if not provided.
        """
        self.config = config or ContextScorerConfig()

    def compute_scores(
        self,
        snapshot: "MarketContextSnapshot",  # type: ignore
        technical_summary: dict[str, float],
    ) -> ContextScores:
        """
        Compute composite scores and classify regime.

        Args:
            snapshot: Latest MarketContextSnapshot with external metrics
            technical_summary: Dict with keys like 'adx', 'rsi', 'bb_width',
                             'macd_histogram', 'volume_ratio' from technical analyzer

        Returns:
            ContextScores with trend, risk, sentiment scores and regime label

        Requirements:
        - 2.1.2: Compute composite scores from snapshot and technical data
        - 2.1.8: Handle missing data gracefully
        """
        # Compute individual composite scores
        trend_strength = self._compute_trend_strength(snapshot, technical_summary)
        risk_regime = self._compute_risk_regime(snapshot, technical_summary)
        sentiment_regime = self._compute_sentiment_regime(snapshot)

        # Classify regime based on raw values (not normalized scores)
        regime = self._classify_regime(
            snapshot=snapshot,
            technical_summary=technical_summary,
            trend_strength_score=trend_strength,
        )

        # Check if any input was stale
        is_degraded = snapshot.is_stale or bool(snapshot.stale_fields)

        return ContextScores(
            trend_strength_score=trend_strength,
            risk_regime_score=risk_regime,
            sentiment_regime_score=sentiment_regime,
            regime=regime,
            is_degraded=is_degraded,
        )

    def _compute_trend_strength(
        self,
        snapshot: "MarketContextSnapshot",  # type: ignore
        technical_summary: dict[str, float],
    ) -> float:
        """
        Compute trend strength score from ADX, Bollinger Bands, and MACD.

        Requirements:
        - 2.1.3: Derive from ADX, price vs Bollinger Bands, MACD histogram
        - 2.1.8: Adjust weights proportionally when data is missing

        Args:
            snapshot: Market context snapshot
            technical_summary: Technical indicator values

        Returns:
            Trend strength score (0.0-1.0)
        """
        components = []
        weights = []

        # Technical analysis component (ADX, BB, MACD)
        adx = technical_summary.get("adx")
        bb_width = technical_summary.get("bb_width")
        macd_histogram = technical_summary.get("macd_histogram")

        if adx is not None or bb_width is not None or macd_histogram is not None:
            ta_score = 0.0
            ta_count = 0

            # ADX: normalize to 0-1 (ADX ranges 0-100, strong trend > 25)
            if adx is not None:
                ta_score += min(adx / 50.0, 1.0)  # Cap at 1.0
                ta_count += 1

            # Bollinger Band width: wider bands = stronger trend
            if bb_width is not None:
                # Normalize BB width (typical range 0-0.1, strong > 0.05)
                ta_score += min(bb_width / 0.1, 1.0)
                ta_count += 1

            # MACD histogram: absolute value indicates trend strength
            if macd_histogram is not None:
                # Normalize MACD histogram (typical range -1 to 1)
                ta_score += min(abs(macd_histogram) / 1.0, 1.0)
                ta_count += 1

            if ta_count > 0:
                components.append(ta_score / ta_count)
                weights.append(self.config.ta_weight_trend)

        # On-chain component (active addresses as proxy for adoption/trend)
        if snapshot.active_addresses is not None:
            # Normalize active addresses (higher = stronger trend)
            # Assume typical range 0-1M addresses, strong > 500k
            onchain_score = min(snapshot.active_addresses / 1_000_000, 1.0)
            components.append(onchain_score)
            weights.append(self.config.onchain_weight_trend)

        # Volume component
        volume_ratio = technical_summary.get("volume_ratio")
        if volume_ratio is not None:
            # Volume ratio > 1.0 indicates above-average volume (stronger trend)
            volume_score = min(volume_ratio / 2.0, 1.0)  # Cap at 1.0
            components.append(volume_score)
            weights.append(self.config.volume_weight_trend)

        # Compute weighted average, adjusting weights proportionally
        if not components:
            return 0.5  # Neutral score when no data available

        total_weight = sum(weights)
        if total_weight == 0:
            return 0.5

        normalized_weights = [w / total_weight for w in weights]
        return sum(c * w for c, w in zip(components, normalized_weights))

    def _compute_risk_regime(
        self,
        snapshot: "MarketContextSnapshot",  # type: ignore
        technical_summary: dict[str, float],
    ) -> float:
        """
        Compute risk regime score from Fear & Greed Index, exchange flow,
        BTC dominance, and TVL.

        Requirements:
        - 2.1.4: Derive from FGI, net exchange flow, BTC dominance change
        - 2.1.8: Adjust weights proportionally when data is missing

        Args:
            snapshot: Market context snapshot
            technical_summary: Technical indicator values

        Returns:
            Risk regime score (0.0-1.0, higher = more risk-on)
        """
        components = []
        weights = []

        # Fear & Greed Index (0-100, higher = more greedy/risk-on)
        if snapshot.fear_greed_index is not None:
            fgi_score = snapshot.fear_greed_index / 100.0
            components.append(fgi_score)
            weights.append(self.config.fgi_weight_risk)

        # Net exchange flow (negative = outflow = risk-on, positive = inflow = risk-off)
        if snapshot.net_exchange_flow is not None:
            # Normalize: negative flow (outflow) = higher score (risk-on)
            # Typical range: -1000 to +1000 BTC
            flow_score = max(0.0, min(1.0, 0.5 - (snapshot.net_exchange_flow / 2000.0)))
            components.append(flow_score)
            weights.append(self.config.exchange_flow_weight_risk)

        # DeFi TVL (higher TVL = more risk-on)
        if snapshot.defi_tvl is not None:
            # Normalize TVL (typical range 0-100B, strong > 50B)
            tvl_score = min(float(snapshot.defi_tvl) / 100_000_000_000, 1.0)
            components.append(tvl_score)
            weights.append(self.config.tvl_weight_risk)

        # Volatility from technical summary (lower volatility = more risk-on)
        volatility = technical_summary.get("volatility")
        if volatility is not None:
            # Normalize volatility (typical range 0-0.1, high > 0.05)
            # Invert: lower volatility = higher risk-on score
            volatility_score = max(0.0, 1.0 - min(volatility / 0.1, 1.0))
            components.append(volatility_score)
            weights.append(self.config.volatility_weight_risk)

        # Compute weighted average
        if not components:
            return 0.5  # Neutral score when no data available

        total_weight = sum(weights)
        if total_weight == 0:
            return 0.5

        normalized_weights = [w / total_weight for w in weights]
        return sum(c * w for c, w in zip(components, normalized_weights))

    def _compute_sentiment_regime(
        self,
        snapshot: "MarketContextSnapshot",  # type: ignore
    ) -> float:
        """
        Compute sentiment regime score from social sentiment, buzz, and news.

        Requirements:
        - 2.1.5: Derive from social sentiment polarity, buzz score, news sentiment
        - 2.1.8: Adjust weights proportionally when data is missing

        Args:
            snapshot: Market context snapshot

        Returns:
            Sentiment regime score (0.0-1.0, higher = more positive sentiment)
        """
        components = []
        weights = []

        # Social sentiment score (-1.0 to 1.0, normalize to 0.0-1.0)
        if snapshot.social_sentiment_score is not None:
            social_score = (snapshot.social_sentiment_score + 1.0) / 2.0
            components.append(social_score)
            weights.append(self.config.social_weight_sentiment)

        # Social buzz score (higher buzz = more attention, proxy for sentiment strength)
        if snapshot.social_buzz_score is not None:
            # Normalize buzz score (typical range 0-100)
            buzz_score = min(snapshot.social_buzz_score / 100.0, 1.0)
            # Weight buzz with sentiment direction if available
            if snapshot.social_sentiment_score is not None:
                # If sentiment is negative, high buzz is bad (invert)
                if snapshot.social_sentiment_score < 0:
                    buzz_score = 1.0 - buzz_score
            components.append(buzz_score)
            # Buzz contributes to social weight
            weights.append(self.config.social_weight_sentiment * 0.3)

        # Fear & Greed Index as sentiment proxy
        if snapshot.fear_greed_index is not None:
            fgi_sentiment_score = snapshot.fear_greed_index / 100.0
            components.append(fgi_sentiment_score)
            weights.append(self.config.fgi_weight_sentiment)

        # News sentiment (placeholder for future implementation)
        # When news sentiment is added to snapshot, include it here
        # For now, we adjust weights proportionally without it

        # Compute weighted average
        if not components:
            return 0.5  # Neutral score when no data available

        total_weight = sum(weights)
        if total_weight == 0:
            return 0.5

        normalized_weights = [w / total_weight for w in weights]
        return sum(c * w for c, w in zip(components, normalized_weights))

    def _classify_regime(
        self,
        snapshot: "MarketContextSnapshot",  # type: ignore
        technical_summary: dict[str, float],
        trend_strength_score: float,
    ) -> Regime:
        """
        Derive regime from raw values using threshold-based rules.

        Requirements:
        - 2.2.2: Regime classification based on raw values
        - 2.2.3: Specific rules for each regime type

        Rules (from requirements 2.2.3):
        - RISK_ON: FGI > 60 AND social sentiment > 0.3 AND BTC dominance falling
        - RISK_OFF: FGI < 30 AND net exchange flow positive AND TVL dropping
        - RANGE_BOUND: ADX < 20 AND trend_strength < 30
        - TRENDING_UP: ADX > 25 AND MACD histogram positive AND trend_strength > 60
        - TRENDING_DOWN: ADX > 25 AND MACD histogram negative AND trend_strength > 60
        - UNKNOWN: otherwise

        Args:
            snapshot: Market context snapshot with raw values
            technical_summary: Technical indicator values
            trend_strength_score: Computed trend strength (0.0-1.0, converted to 0-100)

        Returns:
            Classified market regime
        """
        # Convert normalized trend_strength_score (0.0-1.0) to 0-100 scale
        trend_strength_100 = trend_strength_score * 100.0

        # Extract raw values
        fgi = snapshot.fear_greed_index
        social_sentiment = snapshot.social_sentiment_score
        btc_dominance = snapshot.btc_dominance
        net_exchange_flow = snapshot.net_exchange_flow
        defi_tvl = snapshot.defi_tvl
        adx = technical_summary.get("adx")
        macd_histogram = technical_summary.get("macd_histogram")

        # RISK_ON: FGI > 60 AND social sentiment > 0.3 AND BTC dominance falling
        # Note: We can't detect "falling" without historical data, so we check if dominance is low
        if fgi is not None and social_sentiment is not None and btc_dominance is not None:
            if fgi > 60 and social_sentiment > 0.3 and btc_dominance < 50.0:
                return Regime.RISK_ON

        # RISK_OFF: FGI < 30 AND net exchange flow positive AND TVL dropping
        # Note: We can't detect "dropping" without historical data, so we check if TVL is low
        if fgi is not None and net_exchange_flow is not None:
            if fgi < 30 and net_exchange_flow > 0:
                return Regime.RISK_OFF

        # RANGE_BOUND: ADX < 20 AND trend_strength < 30
        if adx is not None:
            if adx < 20 and trend_strength_100 < 30:
                return Regime.RANGE_BOUND

        # TRENDING_UP: ADX > 25 AND MACD histogram positive AND trend_strength > 60
        if adx is not None and macd_histogram is not None:
            if adx > 25 and macd_histogram > 0 and trend_strength_100 > 60:
                return Regime.TRENDING_UP

        # TRENDING_DOWN: ADX > 25 AND MACD histogram negative AND trend_strength > 60
        if adx is not None and macd_histogram is not None:
            if adx > 25 and macd_histogram < 0 and trend_strength_100 > 60:
                return Regime.TRENDING_DOWN

        # Default to UNKNOWN when conditions don't match or data is insufficient
        return Regime.UNKNOWN
