"""
Unit tests for MarketAnalysisAgent.

Tests the market analysis agent service including signal generation,
Redis publishing, and PostgreSQL storage.

Requirements tested:
- 3.1-3.8: Technical analysis integration
- 4.1-4.5: Sentiment analysis integration
- 5.1-5.6: Signal generation with confidence scoring
"""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from lib.analysis.confidence import IndicatorScore
from lib.analysis.signal import Signal
from lib.analysis.technical import SignalDirection


# Mock Django before importing the agent
@pytest.fixture(autouse=True)
def mock_django_setup():
    """Mock Django setup for testing."""
    with patch("django.setup"):
        yield


@pytest.fixture
def mock_settings():
    """Mock Django settings."""
    settings = MagicMock()
    settings.PIONEX_API_KEY = "test_key"
    settings.PIONEX_API_SECRET = "test_secret"
    settings.REDIS_URL = "redis://localhost:6379/0"
    settings.RSI_PERIOD = 14
    settings.MACD_FAST = 12
    settings.MACD_SLOW = 26
    settings.MACD_SIGNAL = 9
    settings.BOLLINGER_PERIOD = 20
    settings.BOLLINGER_STD = 2.0
    settings.ANALYSIS_INTERVAL_SECONDS = 60
    settings.RISK_MIN_CONFIDENCE = 0.85
    return settings


class TestAgentConfig:
    """Tests for AgentConfig."""

    def test_default_values(self):
        """AgentConfig should have sensible defaults."""
        from agents.market_agent import AgentConfig

        config = AgentConfig()

        assert config.analysis_interval == 60
        assert config.candle_interval == "1H"
        assert config.min_confidence == 85.0
        assert config.technical_weight == 0.60
        assert config.sentiment_weight == 0.30
        assert config.news_weight == 0.10

    def test_custom_values(self):
        """AgentConfig should accept custom values."""
        from agents.market_agent import AgentConfig

        config = AgentConfig(
            analysis_interval=120,
            candle_interval="4H",
            min_confidence=90.0,
            active_symbols=["BTC_USDT", "ETH_USDT"],
        )

        assert config.analysis_interval == 120
        assert config.candle_interval == "4H"
        assert config.min_confidence == 90.0
        assert config.active_symbols == ["BTC_USDT", "ETH_USDT"]


class TestTechnicalScoreCalculation:
    """Tests for technical indicator score calculations."""

    @pytest.fixture
    def agent(self, mock_settings):
        """Create a MarketAnalysisAgent for testing."""
        from agents.market_agent import AgentConfig, MarketAnalysisAgent

        with patch("agents.market_agent.settings", mock_settings):
            config = AgentConfig()
            return MarketAnalysisAgent(config=config)

    def test_rsi_to_confidence_oversold(self, agent):
        """RSI below 30 should give high confidence."""
        confidence = agent._rsi_to_confidence(20.0)
        assert confidence >= 70.0

    def test_rsi_to_confidence_overbought(self, agent):
        """RSI above 70 should give high confidence."""
        confidence = agent._rsi_to_confidence(80.0)
        assert confidence >= 70.0

    def test_rsi_to_confidence_neutral(self, agent):
        """RSI in neutral zone should give moderate confidence."""
        confidence = agent._rsi_to_confidence(50.0)
        assert 50.0 <= confidence <= 70.0

    def test_rsi_to_confidence_none(self, agent):
        """None RSI should return 50% confidence."""
        confidence = agent._rsi_to_confidence(None)
        assert confidence == 50.0

    def test_stoch_to_confidence_oversold(self, agent):
        """Stochastic below 20 should give high confidence."""
        stoch_result = MagicMock()
        stoch_result.k = 10.0
        stoch_result.d = 12.0

        confidence = agent._stoch_to_confidence(stoch_result)
        assert confidence >= 70.0

    def test_stoch_to_confidence_overbought(self, agent):
        """Stochastic above 80 should give high confidence."""
        stoch_result = MagicMock()
        stoch_result.k = 90.0
        stoch_result.d = 88.0

        confidence = agent._stoch_to_confidence(stoch_result)
        assert confidence >= 70.0

    def test_volume_to_confidence_anomaly(self, agent):
        """Volume anomaly should give high confidence."""
        vol_result = MagicMock()
        vol_result.volume_ratio = 2.5
        vol_result.is_anomaly = True

        confidence = agent._volume_to_confidence(vol_result)
        assert confidence == 80.0

    def test_volume_to_confidence_normal(self, agent):
        """Normal volume should give moderate confidence."""
        vol_result = MagicMock()
        vol_result.volume_ratio = 1.0
        vol_result.is_anomaly = False

        confidence = agent._volume_to_confidence(vol_result)
        assert confidence == 60.0


class TestSignalSerialization:
    """Tests for signal JSON serialization."""

    @pytest.fixture
    def agent(self, mock_settings):
        """Create a MarketAnalysisAgent for testing."""
        from agents.market_agent import AgentConfig, MarketAnalysisAgent

        with patch("agents.market_agent.settings", mock_settings):
            config = AgentConfig()
            return MarketAnalysisAgent(config=config)

    @pytest.fixture
    def sample_signal(self):
        """Create a sample signal for testing."""
        from lib.analysis.confidence import ConfidenceBreakdown

        indicators = (
            IndicatorScore("RSI", SignalDirection.BUY, 80.0, 0.2, 35.0, False),
            IndicatorScore("MACD", SignalDirection.BUY, 75.0, 0.2, 0.5, False),
        )

        breakdown = ConfidenceBreakdown(
            technical_score=48.0,
            sentiment_score=24.0,
            news_score=8.0,
            alignment_bonus=5.0,
            base_score=80.0,
            final_score=85.0,
            indicators=indicators,
            agreeing_indicators=2,
            total_indicators=2,
        )

        return Signal(
            symbol="BTC_USDT",
            direction=SignalDirection.BUY,
            confidence=85.0,
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
            indicators=indicators,
            breakdown=breakdown,
            reasoning="BUY signal with 85.0% confidence",
            meets_threshold=True,
            threshold_used=85.0,
        )

    def test_signal_to_json_contains_required_fields(self, agent, sample_signal):
        """Signal JSON should contain all required fields."""
        json_data = agent._signal_to_json(sample_signal)

        assert "symbol" in json_data
        assert "direction" in json_data
        assert "confidence" in json_data
        assert "timestamp" in json_data
        assert "indicators" in json_data
        assert "breakdown" in json_data
        assert "reasoning" in json_data
        assert "meets_threshold" in json_data
        assert "threshold_used" in json_data

    def test_signal_to_json_values(self, agent, sample_signal):
        """Signal JSON should have correct values."""
        json_data = agent._signal_to_json(sample_signal)

        assert json_data["symbol"] == "BTC_USDT"
        assert json_data["direction"] == "BUY"
        assert json_data["confidence"] == 85.0
        assert json_data["meets_threshold"] is True
        assert json_data["threshold_used"] == 85.0

    def test_signal_to_json_indicators(self, agent, sample_signal):
        """Signal JSON should contain indicator details."""
        json_data = agent._signal_to_json(sample_signal)

        assert len(json_data["indicators"]) == 2

        rsi_ind = json_data["indicators"][0]
        assert rsi_ind["name"] == "RSI"
        assert rsi_ind["signal"] == "BUY"
        assert rsi_ind["confidence"] == 80.0
        assert rsi_ind["weight"] == 0.2
        assert rsi_ind["value"] == 35.0

    def test_signal_to_json_breakdown(self, agent, sample_signal):
        """Signal JSON should contain breakdown details."""
        json_data = agent._signal_to_json(sample_signal)

        breakdown = json_data["breakdown"]
        assert breakdown["technical_score"] == 48.0
        assert breakdown["sentiment_score"] == 24.0
        assert breakdown["news_score"] == 8.0
        assert breakdown["alignment_bonus"] == 5.0
        assert breakdown["final_score"] == 85.0

    def test_signal_to_json_is_serializable(self, agent, sample_signal):
        """Signal JSON should be JSON serializable."""
        json_data = agent._signal_to_json(sample_signal)

        # Should not raise
        serialized = json.dumps(json_data)
        assert isinstance(serialized, str)

        # Should be deserializable
        deserialized = json.loads(serialized)
        assert deserialized["symbol"] == "BTC_USDT"


class TestTechnicalScoreCalculationIntegration:
    """Integration tests for technical score calculation."""

    @pytest.fixture
    def agent(self, mock_settings):
        """Create a MarketAnalysisAgent for testing."""
        from agents.market_agent import AgentConfig, MarketAnalysisAgent

        with patch("agents.market_agent.settings", mock_settings):
            config = AgentConfig()
            return MarketAnalysisAgent(config=config)

    def test_calculate_technical_scores_returns_list(self, agent):
        """_calculate_technical_scores should return a list of IndicatorScores."""
        # Generate sample price data
        np.random.seed(42)
        closes = np.cumsum(np.random.randn(100)) + 100
        highs = closes + np.abs(np.random.randn(100))
        lows = closes - np.abs(np.random.randn(100))
        volumes = np.abs(np.random.randn(100)) * 1000 + 1000

        scores = agent._calculate_technical_scores(closes, highs, lows, volumes)

        assert isinstance(scores, list)
        assert len(scores) == 6  # RSI, MACD, BB, ADX, STOCH, VOL

    def test_calculate_technical_scores_indicator_names(self, agent):
        """_calculate_technical_scores should include all expected indicators."""
        np.random.seed(42)
        closes = np.cumsum(np.random.randn(100)) + 100
        highs = closes + np.abs(np.random.randn(100))
        lows = closes - np.abs(np.random.randn(100))
        volumes = np.abs(np.random.randn(100)) * 1000 + 1000

        scores = agent._calculate_technical_scores(closes, highs, lows, volumes)

        names = [s.name for s in scores]
        assert "RSI" in names
        assert "MACD" in names
        assert "BB" in names
        assert "ADX" in names
        assert "STOCH" in names
        assert "VOL" in names

    def test_calculate_technical_scores_weights_sum_to_one(self, agent):
        """Technical indicator weights should sum to 1.0."""
        np.random.seed(42)
        closes = np.cumsum(np.random.randn(100)) + 100
        highs = closes + np.abs(np.random.randn(100))
        lows = closes - np.abs(np.random.randn(100))
        volumes = np.abs(np.random.randn(100)) * 1000 + 1000

        scores = agent._calculate_technical_scores(closes, highs, lows, volumes)

        total_weight = sum(s.weight for s in scores)
        assert abs(total_weight - 1.0) < 0.01  # Allow small floating point error

    def test_calculate_technical_scores_confidence_in_range(self, agent):
        """All confidence scores should be in [0, 100] range."""
        np.random.seed(42)
        closes = np.cumsum(np.random.randn(100)) + 100
        highs = closes + np.abs(np.random.randn(100))
        lows = closes - np.abs(np.random.randn(100))
        volumes = np.abs(np.random.randn(100)) * 1000 + 1000

        scores = agent._calculate_technical_scores(closes, highs, lows, volumes)

        for score in scores:
            assert 0 <= score.confidence <= 100, f"{score.name} confidence out of range"


class TestAsyncMethods:
    """Tests for async methods using mocks."""

    @pytest.fixture
    def agent(self, mock_settings):
        """Create a MarketAnalysisAgent for testing."""
        from agents.market_agent import AgentConfig, MarketAnalysisAgent

        with patch("agents.market_agent.settings", mock_settings):
            config = AgentConfig()
            return MarketAnalysisAgent(config=config)

    @pytest.mark.asyncio
    async def test_publish_signal_calls_redis(self, agent, mock_settings):
        """publish_signal should publish to Redis channel."""
        from lib.analysis.confidence import ConfidenceBreakdown

        # Create mock Redis client
        mock_redis = AsyncMock()
        agent._redis_client = mock_redis
        agent._owns_redis = False

        # Create sample signal
        indicators = (IndicatorScore("RSI", SignalDirection.BUY, 80.0, 0.2, 35.0, False),)
        breakdown = ConfidenceBreakdown(
            technical_score=48.0,
            sentiment_score=24.0,
            news_score=8.0,
            alignment_bonus=5.0,
            base_score=80.0,
            final_score=85.0,
            indicators=indicators,
            agreeing_indicators=1,
            total_indicators=1,
        )
        signal = Signal(
            symbol="BTC_USDT",
            direction=SignalDirection.BUY,
            confidence=85.0,
            timestamp=datetime.now(tz=UTC),
            indicators=indicators,
            breakdown=breakdown,
            reasoning="Test signal",
            meets_threshold=True,
            threshold_used=85.0,
        )

        await agent.publish_signal(signal)

        # Verify Redis publish was called
        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        assert call_args[0][0] == "signals"  # Channel name

        # Verify JSON payload
        payload = json.loads(call_args[0][1])
        assert payload["symbol"] == "BTC_USDT"
        assert payload["direction"] == "BUY"

    @pytest.mark.asyncio
    async def test_get_sentiment_score_returns_indicator_score(self, agent, mock_settings):
        """_get_sentiment_score should return IndicatorScore."""
        from lib.analysis.sentiment import FearGreedClassification, SentimentResult

        # Mock sentiment analyzer
        mock_result = SentimentResult(
            value=25,
            classification=FearGreedClassification.EXTREME_FEAR,
            signal=SignalDirection.BUY,
            timestamp=datetime.now(tz=UTC),
            data_unavailable=False,
            cached=False,
            error_message=None,
        )
        agent._sentiment_analyzer.get_fear_greed_index = AsyncMock(return_value=mock_result)

        score = await agent._get_sentiment_score()

        assert score is not None
        assert score.name == "FGI"
        assert score.signal == SignalDirection.BUY
        assert score.confidence == 25.0
        assert score.weight == 1.0

    @pytest.mark.asyncio
    async def test_get_sentiment_score_handles_unavailable(self, agent, mock_settings):
        """_get_sentiment_score should return None when data unavailable."""
        from lib.analysis.sentiment import FearGreedClassification, SentimentResult

        # Mock sentiment analyzer with unavailable data
        mock_result = SentimentResult(
            value=None,
            classification=FearGreedClassification.NEUTRAL,
            signal=SignalDirection.HOLD,
            timestamp=datetime.now(tz=UTC),
            data_unavailable=True,
            cached=False,
            error_message="API unavailable",
        )
        agent._sentiment_analyzer.get_fear_greed_index = AsyncMock(return_value=mock_result)

        score = await agent._get_sentiment_score()

        assert score is None


class TestNewsAnalysisIntegration:
    """Tests for news analysis integration in MarketAnalysisAgent."""

    @pytest.fixture
    def agent_with_news(self, mock_settings):
        """Create a MarketAnalysisAgent with news analysis enabled."""
        from agents.market_agent import AgentConfig, MarketAnalysisAgent

        mock_settings.LLM_ANALYSIS_ENABLED = True
        mock_settings.OLLAMA_URL = "http://localhost:11434"
        mock_settings.OLLAMA_MODEL = "llama3.2"
        mock_settings.NEWS_RSS_FEEDS = None

        with patch("agents.market_agent.settings", mock_settings):
            config = AgentConfig(
                llm_analysis_enabled=True,
                ollama_url="http://localhost:11434",
                ollama_model="llama3.2",
            )
            return MarketAnalysisAgent(config=config)

    @pytest.fixture
    def agent_without_news(self, mock_settings):
        """Create a MarketAnalysisAgent without news analysis."""
        from agents.market_agent import AgentConfig, MarketAnalysisAgent

        mock_settings.LLM_ANALYSIS_ENABLED = False

        with patch("agents.market_agent.settings", mock_settings):
            config = AgentConfig(llm_analysis_enabled=False)
            return MarketAnalysisAgent(config=config)

    def test_news_analyzer_initialized_when_enabled(self, agent_with_news):
        """News analyzer should be initialized when LLM analysis is enabled."""
        assert agent_with_news._news_analyzer is not None

    def test_news_analyzer_not_initialized_when_disabled(self, agent_without_news):
        """News analyzer should be None when LLM analysis is disabled."""
        assert agent_without_news._news_analyzer is None

    @pytest.mark.asyncio
    async def test_get_news_score_returns_none_when_disabled(self, agent_without_news):
        """_get_news_score should return None when news analysis is disabled."""
        score = await agent_without_news._get_news_score()
        assert score is None

    @pytest.mark.asyncio
    async def test_get_news_score_returns_indicator_score(self, agent_with_news):
        """_get_news_score should return IndicatorScore when available."""
        from lib.analysis.news import NewsAnalysisResult, NewsSentiment

        # Mock news analyzer
        mock_result = NewsAnalysisResult(
            overall_sentiment=NewsSentiment.BULLISH,
            overall_confidence=75.0,
            signal=SignalDirection.BUY,
            articles_analyzed=5,
            bullish_count=3,
            bearish_count=1,
            neutral_count=1,
            article_sentiments=(),
            symbol_sentiments={},
            data_unavailable=False,
            ollama_unavailable=False,
            error_message=None,
        )
        agent_with_news._news_analyzer.analyze_news = AsyncMock(return_value=mock_result)

        score = await agent_with_news._get_news_score()

        assert score is not None
        assert score.name == "NEWS"
        assert score.signal == SignalDirection.BUY
        assert score.confidence == 75.0
        assert score.weight == 1.0

    @pytest.mark.asyncio
    async def test_get_news_score_handles_ollama_unavailable(self, agent_with_news):
        """_get_news_score should return None when Ollama is unavailable."""
        from lib.analysis.news import NewsAnalysisResult, NewsSentiment

        # Mock news analyzer with Ollama unavailable
        mock_result = NewsAnalysisResult(
            overall_sentiment=NewsSentiment.NEUTRAL,
            overall_confidence=0.0,
            signal=SignalDirection.HOLD,
            articles_analyzed=0,
            bullish_count=0,
            bearish_count=0,
            neutral_count=0,
            article_sentiments=(),
            symbol_sentiments={},
            data_unavailable=False,
            ollama_unavailable=True,
            error_message="Ollama not responding",
        )
        agent_with_news._news_analyzer.analyze_news = AsyncMock(return_value=mock_result)

        score = await agent_with_news._get_news_score()

        assert score is None

    @pytest.mark.asyncio
    async def test_get_news_score_handles_data_unavailable(self, agent_with_news):
        """_get_news_score should return None when news data is unavailable."""
        from lib.analysis.news import NewsAnalysisResult, NewsSentiment

        # Mock news analyzer with data unavailable
        mock_result = NewsAnalysisResult(
            overall_sentiment=NewsSentiment.NEUTRAL,
            overall_confidence=0.0,
            signal=SignalDirection.HOLD,
            articles_analyzed=0,
            bullish_count=0,
            bearish_count=0,
            neutral_count=0,
            article_sentiments=(),
            symbol_sentiments={},
            data_unavailable=True,
            ollama_unavailable=False,
            error_message="No RSS feeds available",
        )
        agent_with_news._news_analyzer.analyze_news = AsyncMock(return_value=mock_result)

        score = await agent_with_news._get_news_score()

        assert score is None


class TestNewsTechnicalConflictDetection:
    """Tests for news/technical signal conflict detection."""

    @pytest.fixture
    def agent(self, mock_settings):
        """Create a MarketAnalysisAgent for testing."""
        from agents.market_agent import AgentConfig, MarketAnalysisAgent

        with patch("agents.market_agent.settings", mock_settings):
            config = AgentConfig()
            return MarketAnalysisAgent(config=config)

    def test_no_conflict_when_news_is_hold(self, agent):
        """No conflict should be detected when news signal is HOLD."""
        technical_scores = [
            IndicatorScore("RSI", SignalDirection.BUY, 80.0, 0.2),
            IndicatorScore("MACD", SignalDirection.BUY, 75.0, 0.2),
            IndicatorScore("BB", SignalDirection.BUY, 70.0, 0.2),
        ]
        news_score = IndicatorScore("NEWS", SignalDirection.HOLD, 50.0, 1.0)

        conflict = agent._detect_news_technical_conflict(technical_scores, news_score)

        assert conflict is False

    def test_no_conflict_when_signals_agree(self, agent):
        """No conflict should be detected when news and technical agree."""
        technical_scores = [
            IndicatorScore("RSI", SignalDirection.BUY, 80.0, 0.2),
            IndicatorScore("MACD", SignalDirection.BUY, 75.0, 0.2),
            IndicatorScore("BB", SignalDirection.BUY, 70.0, 0.2),
        ]
        news_score = IndicatorScore("NEWS", SignalDirection.BUY, 75.0, 1.0)

        conflict = agent._detect_news_technical_conflict(technical_scores, news_score)

        assert conflict is False

    def test_conflict_when_news_bullish_technical_bearish(self, agent):
        """Conflict should be detected when news is bullish but technical is bearish."""
        technical_scores = [
            IndicatorScore("RSI", SignalDirection.SELL, 80.0, 0.2),
            IndicatorScore("MACD", SignalDirection.SELL, 75.0, 0.2),
            IndicatorScore("BB", SignalDirection.SELL, 70.0, 0.2),
            IndicatorScore("ADX", SignalDirection.SELL, 65.0, 0.2),
        ]
        news_score = IndicatorScore("NEWS", SignalDirection.BUY, 75.0, 1.0)

        conflict = agent._detect_news_technical_conflict(technical_scores, news_score)

        assert conflict is True

    def test_conflict_when_news_bearish_technical_bullish(self, agent):
        """Conflict should be detected when news is bearish but technical is bullish."""
        technical_scores = [
            IndicatorScore("RSI", SignalDirection.BUY, 80.0, 0.2),
            IndicatorScore("MACD", SignalDirection.BUY, 75.0, 0.2),
            IndicatorScore("BB", SignalDirection.BUY, 70.0, 0.2),
            IndicatorScore("ADX", SignalDirection.BUY, 65.0, 0.2),
        ]
        news_score = IndicatorScore("NEWS", SignalDirection.SELL, 75.0, 1.0)

        conflict = agent._detect_news_technical_conflict(technical_scores, news_score)

        assert conflict is True

    def test_no_conflict_when_technical_mixed(self, agent):
        """No conflict when technical signals are mixed (no clear consensus)."""
        technical_scores = [
            IndicatorScore("RSI", SignalDirection.BUY, 80.0, 0.2),
            IndicatorScore("MACD", SignalDirection.SELL, 75.0, 0.2),
            IndicatorScore("BB", SignalDirection.HOLD, 70.0, 0.2),
        ]
        news_score = IndicatorScore("NEWS", SignalDirection.BUY, 75.0, 1.0)

        conflict = agent._detect_news_technical_conflict(technical_scores, news_score)

        assert conflict is False

    def test_no_conflict_with_empty_technical_scores(self, agent):
        """No conflict should be detected with empty technical scores."""
        technical_scores = []
        news_score = IndicatorScore("NEWS", SignalDirection.BUY, 75.0, 1.0)

        conflict = agent._detect_news_technical_conflict(technical_scores, news_score)

        assert conflict is False
