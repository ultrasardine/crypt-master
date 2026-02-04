"""
Unit tests for News Analyzer Module.

Tests the NewsAnalyzer class for fetching and analyzing crypto news
using Ollama LLM integration.

Requirements:
- 11.1: Connect to local Ollama instance for LLM inference
- 11.2: Fetch recent crypto news from configurable RSS feeds
- 11.3: Extract sentiment (bullish/bearish/neutral) and confidence per article
- 11.4: Identify mentioned cryptocurrencies and associate sentiment with trading pairs
- 11.5: Incorporate news sentiment as weighted factor in confidence scoring
- 11.6: Graceful degradation when Ollama is unavailable
- 11.7: Cache results to avoid redundant LLM calls
- 11.8: Support configurable LLM model selection
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from lib.analysis.news import (
    NewsAnalyzer,
    NewsAnalyzerConfig,
    NewsArticle,
    ArticleSentiment,
    NewsAnalysisResult,
    NewsSentiment,
)
from lib.analysis.technical import SignalDirection


# Sample RSS feed XML for testing
SAMPLE_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Crypto News</title>
    <item>
      <title>Bitcoin Surges Past $100K as Institutional Adoption Grows</title>
      <description>Major financial institutions are increasing their Bitcoin holdings, driving prices to new highs.</description>
      <link>https://example.com/btc-surge</link>
      <pubDate>Wed, 04 Feb 2026 10:00:00 +0000</pubDate>
    </item>
    <item>
      <title>Ethereum Network Upgrade Improves Scalability</title>
      <description>The latest Ethereum upgrade has significantly improved transaction throughput.</description>
      <link>https://example.com/eth-upgrade</link>
      <pubDate>Wed, 04 Feb 2026 09:00:00 +0000</pubDate>
    </item>
    <item>
      <title>Regulatory Concerns Mount for Crypto Exchanges</title>
      <description>New regulations may impact cryptocurrency trading platforms worldwide.</description>
      <link>https://example.com/regulation</link>
      <pubDate>Wed, 04 Feb 2026 08:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>"""


# Sample Ollama response for testing
SAMPLE_OLLAMA_RESPONSE = {
    "response": """SENTIMENT: bullish
CONFIDENCE: 85
REASONING: Strong institutional adoption signals positive market sentiment."""
}


class TestNewsAnalyzerConfig:
    """Tests for NewsAnalyzerConfig."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = NewsAnalyzerConfig()
        
        assert config.ollama_url == "http://localhost:11434"
        assert config.model == "llama3.2"
        assert len(config.rss_feeds) > 0
        assert config.cache_duration_seconds == 1800
        assert config.max_articles == 10

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = NewsAnalyzerConfig(
            ollama_url="http://custom:11434",
            model="mistral",
            rss_feeds=["https://custom.feed/rss"],
            cache_duration_seconds=3600,
            max_articles=5,
        )
        
        assert config.ollama_url == "http://custom:11434"
        assert config.model == "mistral"
        assert config.rss_feeds == ["https://custom.feed/rss"]
        assert config.cache_duration_seconds == 3600
        assert config.max_articles == 5


class TestNewsArticle:
    """Tests for NewsArticle dataclass."""

    def test_article_creation(self) -> None:
        """Test creating a NewsArticle."""
        article = NewsArticle(
            title="Test Article",
            description="Test description",
            link="https://example.com/article",
            published=datetime.now(tz=timezone.utc),
            source="example.com",
        )
        
        assert article.title == "Test Article"
        assert article.description == "Test description"
        assert article.link == "https://example.com/article"
        assert article.source == "example.com"


class TestSymbolDetection:
    """Tests for cryptocurrency symbol detection."""

    def test_detect_bitcoin(self) -> None:
        """Test detecting Bitcoin mentions."""
        analyzer = NewsAnalyzer()
        
        symbols = analyzer._detect_symbols("Bitcoin price surges to new highs")
        assert "BTC" in symbols
        
        symbols = analyzer._detect_symbols("BTC reaches $100K")
        assert "BTC" in symbols

    def test_detect_ethereum(self) -> None:
        """Test detecting Ethereum mentions."""
        analyzer = NewsAnalyzer()
        
        symbols = analyzer._detect_symbols("Ethereum network upgrade")
        assert "ETH" in symbols
        
        symbols = analyzer._detect_symbols("ETH gas fees drop")
        assert "ETH" in symbols

    def test_detect_multiple_symbols(self) -> None:
        """Test detecting multiple cryptocurrency mentions."""
        analyzer = NewsAnalyzer()
        
        text = "Bitcoin and Ethereum lead the market while Solana gains momentum"
        symbols = analyzer._detect_symbols(text)
        
        assert "BTC" in symbols
        assert "ETH" in symbols
        assert "SOL" in symbols

    def test_no_symbols_detected(self) -> None:
        """Test when no cryptocurrency symbols are mentioned."""
        analyzer = NewsAnalyzer()
        
        symbols = analyzer._detect_symbols("Stock market news today")
        assert len(symbols) == 0


class TestRSSParsing:
    """Tests for RSS feed parsing."""

    def test_parse_rss_feed(self) -> None:
        """Test parsing RSS feed XML."""
        analyzer = NewsAnalyzer()
        
        articles = analyzer._parse_rss_feed(SAMPLE_RSS_XML, "https://example.com/rss")
        
        assert len(articles) == 3
        assert articles[0].title == "Bitcoin Surges Past $100K as Institutional Adoption Grows"
        assert "BTC" in analyzer._detect_symbols(articles[0].title)

    def test_parse_invalid_xml(self) -> None:
        """Test handling invalid XML gracefully."""
        analyzer = NewsAnalyzer()
        
        articles = analyzer._parse_rss_feed("not valid xml", "https://example.com/rss")
        assert len(articles) == 0

    def test_parse_empty_feed(self) -> None:
        """Test handling empty RSS feed."""
        analyzer = NewsAnalyzer()
        
        empty_xml = """<?xml version="1.0"?><rss><channel></channel></rss>"""
        articles = analyzer._parse_rss_feed(empty_xml, "https://example.com/rss")
        assert len(articles) == 0


class TestOllamaResponseParsing:
    """Tests for Ollama response parsing."""

    def test_parse_bullish_response(self) -> None:
        """Test parsing bullish sentiment response."""
        analyzer = NewsAnalyzer()
        
        response = """SENTIMENT: bullish
CONFIDENCE: 85
REASONING: Strong positive indicators."""
        
        sentiment, confidence, reasoning = analyzer._parse_ollama_response(response)
        
        assert sentiment == NewsSentiment.BULLISH
        assert confidence == 85.0
        assert "positive" in reasoning.lower()

    def test_parse_bearish_response(self) -> None:
        """Test parsing bearish sentiment response."""
        analyzer = NewsAnalyzer()
        
        response = """SENTIMENT: bearish
CONFIDENCE: 70
REASONING: Regulatory concerns are negative."""
        
        sentiment, confidence, reasoning = analyzer._parse_ollama_response(response)
        
        assert sentiment == NewsSentiment.BEARISH
        assert confidence == 70.0

    def test_parse_neutral_response(self) -> None:
        """Test parsing neutral sentiment response."""
        analyzer = NewsAnalyzer()
        
        response = """SENTIMENT: neutral
CONFIDENCE: 50
REASONING: Mixed signals in the market."""
        
        sentiment, confidence, reasoning = analyzer._parse_ollama_response(response)
        
        assert sentiment == NewsSentiment.NEUTRAL
        assert confidence == 50.0

    def test_parse_malformed_response(self) -> None:
        """Test handling malformed Ollama response."""
        analyzer = NewsAnalyzer()
        
        response = "This is not a properly formatted response"
        
        sentiment, confidence, reasoning = analyzer._parse_ollama_response(response)
        
        # Should default to neutral with 50% confidence
        assert sentiment == NewsSentiment.NEUTRAL
        assert confidence == 50.0

    def test_parse_confidence_with_percent(self) -> None:
        """Test parsing confidence with percent sign."""
        analyzer = NewsAnalyzer()
        
        response = """SENTIMENT: bullish
CONFIDENCE: 90%
REASONING: Very positive."""
        
        sentiment, confidence, reasoning = analyzer._parse_ollama_response(response)
        
        assert confidence == 90.0


class TestSentimentToSignal:
    """Tests for sentiment to signal conversion."""

    def test_bullish_to_buy(self) -> None:
        """Test bullish sentiment converts to BUY signal."""
        analyzer = NewsAnalyzer()
        
        signal = analyzer._sentiment_to_signal(NewsSentiment.BULLISH)
        assert signal == SignalDirection.BUY

    def test_bearish_to_sell(self) -> None:
        """Test bearish sentiment converts to SELL signal."""
        analyzer = NewsAnalyzer()
        
        signal = analyzer._sentiment_to_signal(NewsSentiment.BEARISH)
        assert signal == SignalDirection.SELL

    def test_neutral_to_hold(self) -> None:
        """Test neutral sentiment converts to HOLD signal."""
        analyzer = NewsAnalyzer()
        
        signal = analyzer._sentiment_to_signal(NewsSentiment.NEUTRAL)
        assert signal == SignalDirection.HOLD


class TestCaching:
    """Tests for article analysis caching."""

    def test_cache_key_generation(self) -> None:
        """Test cache key generation is deterministic."""
        analyzer = NewsAnalyzer()
        
        article = NewsArticle(
            title="Test Article",
            description="Description",
            link="https://example.com/test",
            published=datetime.now(tz=timezone.utc),
            source="example.com",
        )
        
        key1 = analyzer._generate_cache_key(article)
        key2 = analyzer._generate_cache_key(article)
        
        assert key1 == key2
        assert len(key1) == 16  # SHA256 truncated to 16 chars

    def test_different_articles_different_keys(self) -> None:
        """Test different articles get different cache keys."""
        analyzer = NewsAnalyzer()
        
        article1 = NewsArticle(
            title="Article 1",
            description="Description",
            link="https://example.com/1",
            published=datetime.now(tz=timezone.utc),
            source="example.com",
        )
        
        article2 = NewsArticle(
            title="Article 2",
            description="Description",
            link="https://example.com/2",
            published=datetime.now(tz=timezone.utc),
            source="example.com",
        )
        
        key1 = analyzer._generate_cache_key(article1)
        key2 = analyzer._generate_cache_key(article2)
        
        assert key1 != key2

    def test_cache_stats(self) -> None:
        """Test cache statistics."""
        analyzer = NewsAnalyzer()
        
        stats = analyzer.get_cache_stats()
        
        assert "total_entries" in stats
        assert "valid_entries" in stats
        assert "expired_entries" in stats
        assert stats["total_entries"] == 0

    def test_clear_cache(self) -> None:
        """Test clearing cache."""
        analyzer = NewsAnalyzer()
        
        # Add something to cache manually
        analyzer._cache["test_key"] = MagicMock()
        assert len(analyzer._cache) == 1
        
        analyzer.clear_cache()
        assert len(analyzer._cache) == 0


class TestUnavailableResult:
    """Tests for unavailable result creation."""

    def test_ollama_unavailable_result(self) -> None:
        """Test creating result when Ollama is unavailable."""
        analyzer = NewsAnalyzer()
        
        result = analyzer._create_unavailable_result(
            ollama_unavailable=True,
            error_message="Ollama not responding",
        )
        
        assert result.ollama_unavailable is True
        assert result.overall_sentiment == NewsSentiment.NEUTRAL
        assert result.signal == SignalDirection.HOLD
        assert result.overall_confidence == 0.0
        assert result.articles_analyzed == 0

    def test_data_unavailable_result(self) -> None:
        """Test creating result when news data is unavailable."""
        analyzer = NewsAnalyzer()
        
        result = analyzer._create_unavailable_result(
            data_unavailable=True,
            error_message="No RSS feeds available",
        )
        
        assert result.data_unavailable is True
        assert result.overall_sentiment == NewsSentiment.NEUTRAL
        assert result.signal == SignalDirection.HOLD


class TestSentimentAggregation:
    """Tests for sentiment aggregation."""

    def test_aggregate_bullish_majority(self) -> None:
        """Test aggregation with bullish majority."""
        analyzer = NewsAnalyzer()
        
        article = NewsArticle(
            title="Test",
            description="Test",
            link="https://example.com",
            published=datetime.now(tz=timezone.utc),
            source="example.com",
        )
        
        sentiments = [
            ArticleSentiment(
                article=article,
                sentiment=NewsSentiment.BULLISH,
                confidence=80.0,
                mentioned_symbols=["BTC"],
                reasoning="Positive",
            ),
            ArticleSentiment(
                article=article,
                sentiment=NewsSentiment.BULLISH,
                confidence=75.0,
                mentioned_symbols=["ETH"],
                reasoning="Positive",
            ),
            ArticleSentiment(
                article=article,
                sentiment=NewsSentiment.NEUTRAL,
                confidence=50.0,
                mentioned_symbols=[],
                reasoning="Neutral",
            ),
        ]
        
        result = analyzer._aggregate_sentiments(sentiments)
        
        assert result.overall_sentiment == NewsSentiment.BULLISH
        assert result.signal == SignalDirection.BUY
        assert result.bullish_count == 2
        assert result.neutral_count == 1
        assert result.bearish_count == 0

    def test_aggregate_bearish_majority(self) -> None:
        """Test aggregation with bearish majority."""
        analyzer = NewsAnalyzer()
        
        article = NewsArticle(
            title="Test",
            description="Test",
            link="https://example.com",
            published=datetime.now(tz=timezone.utc),
            source="example.com",
        )
        
        sentiments = [
            ArticleSentiment(
                article=article,
                sentiment=NewsSentiment.BEARISH,
                confidence=70.0,
                mentioned_symbols=["BTC"],
                reasoning="Negative",
            ),
            ArticleSentiment(
                article=article,
                sentiment=NewsSentiment.BEARISH,
                confidence=65.0,
                mentioned_symbols=["ETH"],
                reasoning="Negative",
            ),
        ]
        
        result = analyzer._aggregate_sentiments(sentiments)
        
        assert result.overall_sentiment == NewsSentiment.BEARISH
        assert result.signal == SignalDirection.SELL
        assert result.bearish_count == 2

    def test_aggregate_symbol_sentiments(self) -> None:
        """Test symbol sentiment mapping in aggregation."""
        analyzer = NewsAnalyzer()
        
        article = NewsArticle(
            title="Test",
            description="Test",
            link="https://example.com",
            published=datetime.now(tz=timezone.utc),
            source="example.com",
        )
        
        sentiments = [
            ArticleSentiment(
                article=article,
                sentiment=NewsSentiment.BULLISH,
                confidence=80.0,
                mentioned_symbols=["BTC", "ETH"],
                reasoning="Positive",
            ),
        ]
        
        result = analyzer._aggregate_sentiments(sentiments)
        
        assert "BTC" in result.symbol_sentiments
        assert "ETH" in result.symbol_sentiments
        assert result.symbol_sentiments["BTC"] == NewsSentiment.BULLISH


@pytest.mark.asyncio
class TestAsyncOperations:
    """Tests for async operations with mocked HTTP client."""

    async def test_check_ollama_available_success(self) -> None:
        """Test Ollama availability check when available."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        
        analyzer = NewsAnalyzer(http_client=mock_client)
        
        result = await analyzer.check_ollama_available()
        assert result is True

    async def test_check_ollama_available_failure(self) -> None:
        """Test Ollama availability check when unavailable."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        
        analyzer = NewsAnalyzer(http_client=mock_client)
        
        result = await analyzer.check_ollama_available()
        assert result is False

    async def test_fetch_news_success(self) -> None:
        """Test fetching news from RSS feeds."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = SAMPLE_RSS_XML
        mock_response.raise_for_status = MagicMock()
        
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        
        config = NewsAnalyzerConfig(
            rss_feeds=["https://example.com/rss"],
            max_articles=10,
        )
        analyzer = NewsAnalyzer(config=config, http_client=mock_client)
        
        articles = await analyzer.fetch_news()
        
        assert len(articles) == 3
        assert articles[0].title == "Bitcoin Surges Past $100K as Institutional Adoption Grows"

    async def test_fetch_news_failure(self) -> None:
        """Test handling RSS fetch failure."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("Network error"))
        
        config = NewsAnalyzerConfig(rss_feeds=["https://example.com/rss"])
        analyzer = NewsAnalyzer(config=config, http_client=mock_client)
        
        articles = await analyzer.fetch_news()
        assert len(articles) == 0

    async def test_analyze_news_ollama_unavailable(self) -> None:
        """Test analyze_news when Ollama is unavailable."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        
        analyzer = NewsAnalyzer(http_client=mock_client)
        
        result = await analyzer.analyze_news()
        
        assert result.ollama_unavailable is True
        assert result.signal == SignalDirection.HOLD
        assert result.overall_confidence == 0.0

    async def test_context_manager(self) -> None:
        """Test async context manager."""
        mock_client = AsyncMock()
        mock_client.aclose = AsyncMock()
        
        async with NewsAnalyzer(http_client=mock_client) as analyzer:
            assert analyzer is not None
        
        # Client should not be closed since we provided it
        mock_client.aclose.assert_not_called()
