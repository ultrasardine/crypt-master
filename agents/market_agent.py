"""
Market Analysis Agent Service.

This module implements the MarketAnalysisAgent, a long-running service that:
1. Fetches market data from Pionex
2. Calculates technical indicators
3. Retrieves sentiment data (Fear & Greed Index)
4. Retrieves news sentiment (via Ollama LLM)
5. Generates signals with confidence scores
6. Publishes signals to Redis for bot-agent
7. Stores results in PostgreSQL

Requirements:
- 3.1-3.8: Technical analysis with RSI, MACD, Bollinger Bands, etc.
- 4.1-4.5: Sentiment analysis with Fear & Greed Index
- 5.1-5.6: Signal generation with confidence scoring
- 11.1-11.9: LLM-based news sentiment analysis (optional)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from dataclasses import dataclass
from typing import Any

import django
import numpy as np
import redis.asyncio as aioredis

# Setup Django before importing models
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings

from apps.core.models import TradingPair
from apps.trading.models import Signal as SignalModel
from apps.trading.models import SignalDirection as DBSignalDirection
from lib.analysis.confidence import ConfidenceConfig, IndicatorScore
from lib.analysis.news import NewsAnalyzer, NewsAnalyzerConfig, NewsSentiment
from lib.analysis.sentiment import SentimentAnalyzer, SentimentConfig
from lib.analysis.signal import Signal, SignalGenerator, SignalGeneratorConfig
from lib.analysis.technical import (
    IndicatorConfig,
    SignalDirection,
    TechnicalAnalyzer,
)
from lib.logging import (
    LoggingConfig,
    get_system_logger,
    get_trading_logger,
    setup_logging,
)
from lib.messaging.websocket import get_broadcaster
from lib.pionex.client import PionexClient

logger = logging.getLogger(__name__)
trading_logger = get_trading_logger()
system_logger = get_system_logger()


# Redis channel for publishing signals
SIGNALS_CHANNEL = "signals"

# Default candle interval for analysis
DEFAULT_CANDLE_INTERVAL = "1H"

# Minimum candles required for analysis
MIN_CANDLES_REQUIRED = 50


@dataclass
class AgentConfig:
    """
    Configuration for MarketAnalysisAgent.

    Attributes:
        analysis_interval: Seconds between analysis cycles
        candle_interval: Candle interval for technical analysis
        min_confidence: Minimum confidence threshold for signals
        active_symbols: List of symbols to analyze (empty = all active)
        technical_weight: Weight for technical analysis in confidence
        sentiment_weight: Weight for sentiment analysis in confidence
        news_weight: Weight for news analysis in confidence
        llm_analysis_enabled: Whether to enable LLM news analysis
        ollama_url: URL for Ollama API
        ollama_model: LLM model to use for news analysis
        news_rss_feeds: RSS feeds for news analysis
    """

    analysis_interval: int = 60
    candle_interval: str = "1H"
    min_confidence: float = 85.0
    active_symbols: list[str] | None = None
    technical_weight: float = 0.60
    sentiment_weight: float = 0.30
    news_weight: float = 0.10
    llm_analysis_enabled: bool = False
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    news_rss_feeds: list[str] | None = None

    @classmethod
    def from_settings(cls) -> AgentConfig:
        """Create config from Django settings."""
        return cls(
            analysis_interval=getattr(settings, "ANALYSIS_INTERVAL_SECONDS", 60),
            min_confidence=getattr(settings, "RISK_MIN_CONFIDENCE", 0.85) * 100,
            technical_weight=0.60,
            sentiment_weight=0.30,
            news_weight=0.10,
            llm_analysis_enabled=getattr(settings, "LLM_ANALYSIS_ENABLED", False),
            ollama_url=getattr(settings, "OLLAMA_URL", "http://localhost:11434"),
            ollama_model=getattr(settings, "OLLAMA_MODEL", "llama3.2"),
            news_rss_feeds=getattr(settings, "NEWS_RSS_FEEDS", None),
        )


class MarketAnalysisAgent:
    """
    Long-running service for market analysis and signal generation.

    This agent continuously:
    1. Fetches market data from Pionex for configured trading pairs
    2. Calculates technical indicators (RSI, MACD, Bollinger Bands, etc.)
    3. Retrieves sentiment data (Fear & Greed Index)
    4. Retrieves news sentiment (via Ollama LLM, if enabled)
    5. Generates trading signals with confidence scores
    6. Publishes signals to Redis for the bot management agent
    7. Stores signals in PostgreSQL for dashboard display

    Requirements:
        - 3.1-3.8: Technical analysis with all indicators
        - 4.1-4.5: Sentiment analysis with Fear & Greed Index
        - 5.1-5.6: Signal generation with confidence scoring
        - 11.1-11.9: LLM-based news sentiment analysis (optional)

    Example:
        >>> agent = MarketAnalysisAgent()
        >>> await agent.run()  # Runs until stopped
    """

    def __init__(
        self,
        config: AgentConfig | None = None,
        pionex_client: PionexClient | None = None,
        redis_client: aioredis.Redis | None = None,
    ) -> None:
        """
        Initialize the MarketAnalysisAgent.

        Args:
            config: Agent configuration (uses defaults from settings if None)
            pionex_client: Optional Pionex client for dependency injection
            redis_client: Optional Redis client for dependency injection
        """
        self.config = config or AgentConfig.from_settings()
        self._pionex_client = pionex_client
        self._redis_client = redis_client
        self._owns_pionex = pionex_client is None
        self._owns_redis = redis_client is None

        # Initialize analyzers
        self._technical_analyzer = TechnicalAnalyzer(
            config=IndicatorConfig(
                rsi_period=getattr(settings, "RSI_PERIOD", 14),
                macd_fast=getattr(settings, "MACD_FAST", 12),
                macd_slow=getattr(settings, "MACD_SLOW", 26),
                macd_signal=getattr(settings, "MACD_SIGNAL", 9),
                bb_period=getattr(settings, "BOLLINGER_PERIOD", 20),
                bb_std_dev=getattr(settings, "BOLLINGER_STD", 2.0),
            )
        )

        self._sentiment_analyzer = SentimentAnalyzer(
            config=SentimentConfig(
                cache_duration_seconds=3600,  # Cache FGI for 1 hour
            )
        )

        # Initialize news analyzer if LLM analysis is enabled
        self._news_analyzer: NewsAnalyzer | None = None
        if self.config.llm_analysis_enabled:
            news_config = NewsAnalyzerConfig(
                ollama_url=self.config.ollama_url,
                model=self.config.ollama_model,
                cache_duration_seconds=1800,  # Cache news for 30 minutes
            )
            if self.config.news_rss_feeds:
                news_config.rss_feeds = self.config.news_rss_feeds
            self._news_analyzer = NewsAnalyzer(config=news_config)

        self._signal_generator = SignalGenerator(
            config=SignalGeneratorConfig(
                min_confidence_threshold=self.config.min_confidence,
                confidence_config=ConfidenceConfig(
                    technical_weight=self.config.technical_weight,
                    sentiment_weight=self.config.sentiment_weight,
                    news_weight=self.config.news_weight,
                ),
            )
        )

        self._running = False
        self._shutdown_event = asyncio.Event()

    async def _get_pionex_client(self) -> PionexClient:
        """Get or create the Pionex client."""
        if self._pionex_client is None:
            api_key = getattr(settings, "PIONEX_API_KEY", "")
            api_secret = getattr(settings, "PIONEX_API_SECRET", "")

            if not api_key or not api_secret:
                raise ValueError("PIONEX_API_KEY and PIONEX_API_SECRET must be set in environment")

            self._pionex_client = PionexClient(
                api_key=api_key,
                api_secret=api_secret,
            )
            await self._pionex_client._ensure_client()

        return self._pionex_client

    async def _get_redis_client(self) -> aioredis.Redis:
        """Get or create the Redis client."""
        if self._redis_client is None:
            redis_url = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")
            self._redis_client = aioredis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis_client

    async def close(self) -> None:
        """Close all clients and resources."""
        if self._owns_pionex and self._pionex_client is not None:
            await self._pionex_client.close()
            self._pionex_client = None

        if self._owns_redis and self._redis_client is not None:
            await self._redis_client.close()
            self._redis_client = None

        await self._sentiment_analyzer.close()

        if self._news_analyzer is not None:
            await self._news_analyzer.close()

    async def __aenter__(self) -> MarketAnalysisAgent:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()

    async def _get_active_symbols(self) -> list[str]:
        """
        Get list of active trading pair symbols to analyze.

        Returns:
            List of symbol strings (e.g., ["BTC_USDT", "ETH_USDT"])
        """
        if self.config.active_symbols:
            return self.config.active_symbols

        # Get active pairs from database using sync_to_async
        from asgiref.sync import sync_to_async

        @sync_to_async
        def fetch_symbols() -> list[str]:
            pairs = TradingPair.objects.active()
            return [pair.symbol for pair in pairs]

        return await fetch_symbols()

    async def run(self) -> None:
        """
        Main event loop for the market analysis agent.

        Continuously fetches market data, generates signals, and publishes
        them until stopped via shutdown() or signal interrupt.
        """
        self._running = True
        logger.info("MarketAnalysisAgent starting...")

        try:
            while self._running and not self._shutdown_event.is_set():
                try:
                    await self._analysis_cycle()
                except Exception as e:
                    logger.error(f"Error in analysis cycle: {e}", exc_info=True)

                # Wait for next cycle or shutdown
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=self.config.analysis_interval,
                    )
                except TimeoutError:
                    # Normal timeout, continue to next cycle
                    pass
        finally:
            self._running = False
            logger.info("MarketAnalysisAgent stopped")

    async def shutdown(self) -> None:
        """Signal the agent to stop gracefully."""
        logger.info("Shutdown requested...")
        self._running = False
        self._shutdown_event.set()

    async def _analysis_cycle(self) -> None:
        """
        Perform one complete analysis cycle for all active symbols.
        """
        symbols = await self._get_active_symbols()

        if not symbols:
            logger.warning("No active symbols to analyze")
            return

        logger.info(f"Starting analysis cycle for {len(symbols)} symbols")

        # Get sentiment data once per cycle (shared across all symbols)
        sentiment_score = await self._get_sentiment_score()

        # Get news sentiment once per cycle (if enabled)
        news_score = await self._get_news_score()

        for symbol in symbols:
            try:
                signal = await self.analyze_symbol(symbol, sentiment_score, news_score)

                if signal is not None:
                    await self.publish_signal(signal)
                    await self.store_signal(signal)

                    logger.info(
                        f"Signal generated for {symbol}: {signal.direction.value} "
                        f"({signal.confidence:.1f}% confidence)"
                    )
            except Exception as e:
                logger.error(f"Error analyzing {symbol}: {e}", exc_info=True)

        logger.info("Analysis cycle complete")

    async def _get_sentiment_score(self) -> IndicatorScore | None:
        """
        Get sentiment score from Fear & Greed Index.

        Returns:
            IndicatorScore for sentiment, or None if unavailable
        """
        try:
            result = await self._sentiment_analyzer.get_fear_greed_index()

            if result.data_unavailable:
                logger.warning(f"Sentiment data unavailable: {result.error_message}")
                return None

            # Convert to IndicatorScore
            # FGI value 0-100 maps to confidence
            # Signal direction comes from the analyzer
            confidence = float(result.value) if result.value is not None else 50.0

            return IndicatorScore(
                name="FGI",
                signal=result.signal,
                confidence=confidence,
                weight=1.0,  # Full weight within sentiment category
                value=float(result.value) if result.value is not None else None,
                data_insufficient=result.data_unavailable,
            )
        except Exception as e:
            logger.error(f"Error fetching sentiment: {e}", exc_info=True)
            return None

    async def _get_news_score(self) -> IndicatorScore | None:
        """
        Get news sentiment score from LLM analysis.

        Returns:
            IndicatorScore for news sentiment, or None if unavailable/disabled

        Requirements:
            - 11.5: Incorporate news sentiment as weighted factor in confidence scoring
            - 11.6: Graceful degradation when Ollama is unavailable
        """
        if self._news_analyzer is None:
            # LLM analysis not enabled
            return None

        try:
            result = await self._news_analyzer.analyze_news()

            if result.ollama_unavailable:
                logger.warning(f"News analysis unavailable (Ollama down): {result.error_message}")
                return None

            if result.data_unavailable:
                logger.warning(f"News data unavailable: {result.error_message}")
                return None

            # Convert news sentiment to signal direction
            if result.overall_sentiment == NewsSentiment.BULLISH:
                signal = SignalDirection.BUY
            elif result.overall_sentiment == NewsSentiment.BEARISH:
                signal = SignalDirection.SELL
            else:
                signal = SignalDirection.HOLD

            return IndicatorScore(
                name="NEWS",
                signal=signal,
                confidence=result.overall_confidence,
                weight=1.0,  # Full weight within news category
                value=result.overall_confidence,
                data_insufficient=result.data_unavailable,
            )
        except Exception as e:
            logger.error(f"Error fetching news sentiment: {e}", exc_info=True)
            return None

    async def analyze_symbol(
        self,
        symbol: str,
        sentiment_score: IndicatorScore | None = None,
        news_score: IndicatorScore | None = None,
    ) -> Signal | None:
        """
        Analyze a single trading pair and generate a signal.

        Args:
            symbol: Trading pair symbol (e.g., "BTC_USDT")
            sentiment_score: Pre-fetched sentiment score (optional)
            news_score: Pre-fetched news sentiment score (optional)

        Returns:
            Signal with direction, confidence, and metadata, or None if analysis fails

        Requirements:
            - 11.5: Incorporate news sentiment as weighted factor
            - 11.9: Detect conflicts between news and technical signals
        """
        client = await self._get_pionex_client()

        # Fetch candle data
        try:
            candles = await client.get_candles(
                symbol=symbol,
                interval=self.config.candle_interval,
                limit=200,  # Get enough data for all indicators
            )
        except Exception as e:
            logger.error(f"Failed to fetch candles for {symbol}: {e}")
            return None

        if len(candles) < MIN_CANDLES_REQUIRED:
            logger.warning(
                f"Insufficient candle data for {symbol}: {len(candles)} < {MIN_CANDLES_REQUIRED}"
            )
            return None

        # Extract price arrays
        closes = np.array([c.close for c in candles])
        highs = np.array([c.high for c in candles])
        lows = np.array([c.low for c in candles])
        volumes = np.array([c.volume for c in candles])

        # Calculate technical indicators
        technical_scores = self._calculate_technical_scores(closes, highs, lows, volumes)

        # Check for news/technical conflict (Requirement 11.9)
        if news_score is not None:
            conflict = self._detect_news_technical_conflict(technical_scores, news_score)
            if conflict:
                logger.warning(f"News sentiment conflicts with technical signals for {symbol}")

        # Generate signal
        signal = self._signal_generator.generate_signal(
            symbol=symbol,
            technical_scores=technical_scores,
            sentiment_score=sentiment_score,
            news_score=news_score,
        )

        return signal

    def _detect_news_technical_conflict(
        self,
        technical_scores: list[IndicatorScore],
        news_score: IndicatorScore,
    ) -> bool:
        """
        Detect if news sentiment strongly contradicts technical signals.

        Args:
            technical_scores: List of technical indicator scores
            news_score: News sentiment score

        Returns:
            True if there's a strong conflict, False otherwise

        Requirements:
            - 11.9: Detect conflicts between news and technical signals
        """
        if news_score.signal == SignalDirection.HOLD:
            return False

        # Count technical signals
        buy_count = sum(1 for s in technical_scores if s.signal == SignalDirection.BUY)
        sell_count = sum(1 for s in technical_scores if s.signal == SignalDirection.SELL)

        total = len(technical_scores)
        if total == 0:
            return False

        # Determine dominant technical signal
        if buy_count > sell_count and buy_count >= total * 0.6:
            dominant_technical = SignalDirection.BUY
        elif sell_count > buy_count and sell_count >= total * 0.6:
            dominant_technical = SignalDirection.SELL
        else:
            return False  # No clear technical consensus

        # Check for conflict
        if news_score.signal == SignalDirection.BUY and dominant_technical == SignalDirection.SELL:
            return True
        if news_score.signal == SignalDirection.SELL and dominant_technical == SignalDirection.BUY:
            return True

        return False

    def _calculate_technical_scores(
        self,
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        volumes: np.ndarray,
    ) -> list[IndicatorScore]:
        """
        Calculate all technical indicator scores.

        Args:
            closes: Array of closing prices
            highs: Array of high prices
            lows: Array of low prices
            volumes: Array of volumes

        Returns:
            List of IndicatorScore objects for each indicator
        """
        scores: list[IndicatorScore] = []

        # RSI
        rsi_result = self._technical_analyzer.calculate_rsi(closes)
        scores.append(
            IndicatorScore(
                name="RSI",
                signal=rsi_result.signal,
                confidence=self._rsi_to_confidence(rsi_result.value),
                weight=0.20,  # 20% of technical weight
                value=rsi_result.value,
                data_insufficient=rsi_result.data_insufficient,
            )
        )

        # MACD
        macd_result = self._technical_analyzer.calculate_macd(closes)
        scores.append(
            IndicatorScore(
                name="MACD",
                signal=macd_result.signal,
                confidence=self._macd_to_confidence(macd_result),
                weight=0.20,  # 20% of technical weight
                value=macd_result.histogram,
                data_insufficient=macd_result.data_insufficient,
            )
        )

        # Bollinger Bands
        bb_result = self._technical_analyzer.calculate_bollinger_bands(closes)
        scores.append(
            IndicatorScore(
                name="BB",
                signal=bb_result.signal,
                confidence=self._bb_to_confidence(bb_result, closes[-1]),
                weight=0.15,  # 15% of technical weight
                value=bb_result.middle_band,
                data_insufficient=bb_result.data_insufficient,
            )
        )

        # ADX (trend strength)
        adx_result = self._technical_analyzer.calculate_adx(highs, lows, closes)
        scores.append(
            IndicatorScore(
                name="ADX",
                signal=adx_result.signal,
                confidence=self._adx_to_confidence(adx_result),
                weight=0.15,  # 15% of technical weight
                value=adx_result.adx,
                data_insufficient=adx_result.data_insufficient,
            )
        )

        # Stochastic
        stoch_result = self._technical_analyzer.calculate_stochastic(highs, lows, closes)
        scores.append(
            IndicatorScore(
                name="STOCH",
                signal=stoch_result.signal,
                confidence=self._stoch_to_confidence(stoch_result),
                weight=0.15,  # 15% of technical weight
                value=stoch_result.k,
                data_insufficient=stoch_result.data_insufficient,
            )
        )

        # Volume analysis
        vol_result = self._technical_analyzer.analyze_volume(volumes)
        scores.append(
            IndicatorScore(
                name="VOL",
                signal=vol_result.signal,
                confidence=self._volume_to_confidence(vol_result),
                weight=0.15,  # 15% of technical weight
                value=vol_result.volume_ratio,
                data_insufficient=vol_result.data_insufficient,
            )
        )

        return scores

    def _rsi_to_confidence(self, rsi_value: float | None) -> float:
        """Convert RSI value to confidence score."""
        if rsi_value is None:
            return 50.0

        # RSI extremes (< 30 or > 70) give higher confidence
        if rsi_value <= 30:
            # Oversold: confidence increases as RSI decreases
            return 70.0 + (30 - rsi_value)  # 70-100
        elif rsi_value >= 70:
            # Overbought: confidence increases as RSI increases
            return 70.0 + (rsi_value - 70)  # 70-100
        else:
            # Neutral zone: lower confidence
            return 50.0 + abs(50 - rsi_value) * 0.4  # 50-70

    def _macd_to_confidence(self, macd_result) -> float:
        """Convert MACD result to confidence score."""
        if macd_result.histogram is None:
            return 50.0

        # Larger histogram values indicate stronger signals
        hist_abs = abs(macd_result.histogram)

        # Normalize histogram to confidence (rough heuristic)
        # This should be calibrated based on typical histogram values
        confidence = min(90.0, 60.0 + hist_abs * 10)
        return confidence

    def _bb_to_confidence(self, bb_result, current_price: float) -> float:
        """Convert Bollinger Bands result to confidence score."""
        if bb_result.upper_band is None or bb_result.lower_band is None:
            return 50.0

        band_width = bb_result.upper_band - bb_result.lower_band
        if band_width <= 0:
            return 50.0

        # Calculate position within bands
        if current_price >= bb_result.upper_band:
            # Above upper band: strong sell signal
            return 80.0
        elif current_price <= bb_result.lower_band:
            # Below lower band: strong buy signal
            return 80.0
        else:
            # Within bands: confidence based on distance from middle
            distance_from_middle = abs(current_price - bb_result.middle_band)
            half_width = band_width / 2
            position_ratio = distance_from_middle / half_width
            return 50.0 + position_ratio * 30  # 50-80

    def _adx_to_confidence(self, adx_result) -> float:
        """Convert ADX result to confidence score."""
        if adx_result.adx is None:
            return 50.0

        # ADX > 25 indicates strong trend
        if adx_result.adx >= 25:
            # Strong trend: higher confidence
            return min(95.0, 70.0 + (adx_result.adx - 25))
        else:
            # Weak trend: lower confidence
            return 50.0 + adx_result.adx  # 50-75

    def _stoch_to_confidence(self, stoch_result) -> float:
        """Convert Stochastic result to confidence score."""
        if stoch_result.k is None:
            return 50.0

        # Stochastic extremes (< 20 or > 80) give higher confidence
        if stoch_result.k <= 20:
            return 70.0 + (20 - stoch_result.k)  # 70-90
        elif stoch_result.k >= 80:
            return 70.0 + (stoch_result.k - 80)  # 70-90
        else:
            return 50.0 + abs(50 - stoch_result.k) * 0.4  # 50-70

    def _volume_to_confidence(self, vol_result) -> float:
        """Convert volume analysis result to confidence score."""
        if vol_result.volume_ratio is None:
            return 50.0

        # High volume (anomaly) increases confidence in current trend
        if vol_result.is_anomaly:
            return 80.0
        elif vol_result.volume_ratio >= 1.5:
            return 70.0
        elif vol_result.volume_ratio >= 1.0:
            return 60.0
        else:
            # Low volume: lower confidence
            return 50.0

    async def publish_signal(self, signal: Signal) -> None:
        """
        Publish a signal to Redis for the bot management agent.

        Args:
            signal: The signal to publish

        Requirements:
            - 5.1: Generate Signal containing direction, confidence_score, supporting_factors
            - 8.1: Real-time dashboard updates via WebSocket
            - 8.1: Log all trading decisions with full context
        """
        redis = await self._get_redis_client()

        # Serialize signal to JSON
        signal_data = self._signal_to_json(signal)

        # Publish to signals channel
        await redis.publish(SIGNALS_CHANNEL, json.dumps(signal_data))

        # Log the signal using structured trading logger
        trading_logger.log_signal(
            symbol=signal.symbol,
            direction=signal.direction.value,
            confidence=signal.confidence,
            indicators=[
                {
                    "name": ind.name,
                    "signal": ind.signal.value,
                    "confidence": ind.confidence,
                    "value": ind.value,
                }
                for ind in signal.indicators
            ],
            reasoning=signal.reasoning,
            meets_threshold=signal.meets_threshold,
            threshold=signal.threshold_used,
        )

        # Broadcast to WebSocket for real-time dashboard updates
        try:
            broadcaster = get_broadcaster()
            await broadcaster.broadcast_signal_update(
                symbol=signal.symbol,
                direction=signal.direction.value,
                confidence=signal.confidence,
                meets_threshold=signal.meets_threshold,
                indicators=[
                    {
                        "name": ind.name,
                        "signal": ind.signal.value,
                        "confidence": ind.confidence,
                        "value": ind.value,
                    }
                    for ind in signal.indicators
                ],
                reasoning=signal.reasoning,
            )
        except Exception as e:
            # Don't fail signal publishing if WebSocket broadcast fails
            logger.warning(f"Failed to broadcast signal to WebSocket: {e}")

        logger.debug(f"Published signal to Redis: {signal.symbol} {signal.direction.value}")

    async def store_signal(self, signal: Signal) -> None:
        """
        Store a signal in PostgreSQL.

        Args:
            signal: The signal to store
        """
        from asgiref.sync import sync_to_async

        try:
            @sync_to_async
            def create_signal():
                # Get or create trading pair
                trading_pair, _ = TradingPair.objects.get_or_create(
                    symbol=signal.symbol,
                    defaults={
                        "base_currency": signal.symbol.split("_")[0]
                        if "_" in signal.symbol
                        else signal.symbol[:3],
                        "quote_currency": signal.symbol.split("_")[1]
                        if "_" in signal.symbol
                        else "USDT",
                        "is_active": True,
                    },
                )

                # Map signal direction to DB enum
                direction_map = {
                    SignalDirection.BUY: DBSignalDirection.BUY,
                    SignalDirection.SELL: DBSignalDirection.SELL,
                    SignalDirection.HOLD: DBSignalDirection.HOLD,
                }

                # Create signal record
                SignalModel.objects.create(
                    trading_pair=trading_pair,
                    direction=direction_map[signal.direction],
                    confidence=signal.confidence,
                    indicators=self._signal_to_json(signal)["indicators"],
                    reasoning=signal.reasoning,
                )

            await create_signal()

            logger.debug(f"Stored signal in database: {signal.symbol}")
        except Exception as e:
            logger.error(f"Failed to store signal: {e}", exc_info=True)

    def _signal_to_json(self, signal: Signal) -> dict[str, Any]:
        """
        Convert a Signal to a JSON-serializable dictionary.

        Args:
            signal: The signal to convert

        Returns:
            Dictionary representation of the signal
        """
        return {
            "symbol": signal.symbol,
            "direction": signal.direction.value,
            "confidence": signal.confidence,
            "timestamp": signal.timestamp.isoformat(),
            "meets_threshold": signal.meets_threshold,
            "threshold_used": signal.threshold_used,
            "reasoning": signal.reasoning,
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
        }


def setup_signal_handlers(agent: MarketAnalysisAgent) -> None:
    """Setup signal handlers for graceful shutdown."""
    loop = asyncio.get_event_loop()

    def handle_signal(sig):
        logger.info(f"Received signal {sig.name}, initiating shutdown...")
        asyncio.create_task(agent.shutdown())

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: handle_signal(s))


async def main() -> None:
    """Main entry point for the market analysis agent."""
    # Setup structured logging
    setup_logging(
        LoggingConfig(
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            json_format=True,
        )
    )

    logger.info("Starting Market Analysis Agent...")

    # Log startup with configuration
    system_logger.log_startup(
        service_name="MarketAnalysisAgent",
        mode="dry-run" if getattr(settings, "DRY_RUN", True) else "live",
        config={
            "analysis_interval": getattr(settings, "ANALYSIS_INTERVAL_SECONDS", 60),
            "min_confidence": getattr(settings, "RISK_MIN_CONFIDENCE", 0.85) * 100,
            "rsi_period": getattr(settings, "RSI_PERIOD", 14),
            "macd_fast": getattr(settings, "MACD_FAST", 12),
            "macd_slow": getattr(settings, "MACD_SLOW", 26),
            "macd_signal": getattr(settings, "MACD_SIGNAL", 9),
            "bollinger_period": getattr(settings, "BOLLINGER_PERIOD", 20),
            "bollinger_std": getattr(settings, "BOLLINGER_STD", 2.0),
            "llm_analysis_enabled": getattr(settings, "LLM_ANALYSIS_ENABLED", False),
            "ollama_url": getattr(settings, "OLLAMA_URL", "http://localhost:11434"),
            "ollama_model": getattr(settings, "OLLAMA_MODEL", "llama3.2"),
        },
    )

    async with MarketAnalysisAgent() as agent:
        setup_signal_handlers(agent)
        await agent.run()

    # Log shutdown
    system_logger.log_shutdown(
        service_name="MarketAnalysisAgent",
        reason="normal",
    )


if __name__ == "__main__":
    asyncio.run(main())
