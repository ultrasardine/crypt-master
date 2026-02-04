"""
News Sentiment Analysis Library with Ollama LLM Integration.

This module provides news sentiment analysis by fetching crypto news from RSS feeds
and analyzing sentiment using a local Ollama LLM instance.

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

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

import httpx

from lib.analysis.technical import SignalDirection

if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


class NewsSentiment(Enum):
    """Sentiment classification for news articles."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class NewsArticle:
    """
    Represents a news article fetched from RSS feed.

    Attributes:
        title: Article title
        description: Article description/summary
        link: URL to the full article
        published: Publication timestamp
        source: RSS feed source name
    """

    title: str
    description: str
    link: str
    published: datetime | None
    source: str


@dataclass(frozen=True)
class ArticleSentiment:
    """
    Sentiment analysis result for a single article.

    Attributes:
        article: The analyzed article
        sentiment: Bullish/bearish/neutral classification
        confidence: Confidence score (0-100)
        mentioned_symbols: List of cryptocurrency symbols mentioned
        reasoning: LLM's reasoning for the sentiment
        cached: Whether this result was served from cache
        analysis_timestamp: When the analysis was performed
    """

    article: NewsArticle
    sentiment: NewsSentiment
    confidence: float
    mentioned_symbols: list[str]
    reasoning: str
    cached: bool = False
    analysis_timestamp: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


@dataclass(frozen=True)
class NewsAnalysisResult:
    """
    Aggregated news sentiment analysis result.

    Attributes:
        overall_sentiment: Aggregated sentiment across all articles
        overall_confidence: Aggregated confidence score (0-100)
        signal: Trading signal derived from news sentiment
        articles_analyzed: Number of articles analyzed
        bullish_count: Number of bullish articles
        bearish_count: Number of bearish articles
        neutral_count: Number of neutral articles
        article_sentiments: Individual article sentiment results
        symbol_sentiments: Sentiment breakdown by symbol
        data_unavailable: Whether news data was unavailable
        ollama_unavailable: Whether Ollama was unavailable
        error_message: Error message if analysis failed
        timestamp: When the analysis was performed
    """

    overall_sentiment: NewsSentiment
    overall_confidence: float
    signal: SignalDirection
    articles_analyzed: int
    bullish_count: int
    bearish_count: int
    neutral_count: int
    article_sentiments: tuple[ArticleSentiment, ...]
    symbol_sentiments: dict[str, NewsSentiment]
    data_unavailable: bool = False
    ollama_unavailable: bool = False
    error_message: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


@dataclass
class NewsAnalyzerConfig:
    """
    Configuration for NewsAnalyzer.

    Attributes:
        ollama_url: URL for the Ollama API (default: http://localhost:11434)
        model: LLM model to use (default: llama3.2)
        rss_feeds: List of RSS feed URLs to fetch news from
        cache_duration_seconds: How long to cache results (default 1800 = 30 min)
        http_timeout_seconds: HTTP request timeout (default 30 seconds)
        max_articles: Maximum articles to analyze per cycle (default 10)
        bullish_threshold: Confidence threshold for bullish signal (default 60)
        bearish_threshold: Confidence threshold for bearish signal (default 60)
    """

    ollama_url: str = "http://localhost:11434"
    model: str = "llama3.2"
    rss_feeds: list[str] = field(
        default_factory=lambda: [
            "https://cointelegraph.com/rss",
            "https://cryptonews.com/news/feed/",
        ]
    )
    cache_duration_seconds: int = 1800
    http_timeout_seconds: float = 30.0
    max_articles: int = 10
    bullish_threshold: float = 60.0
    bearish_threshold: float = 60.0


@dataclass
class _CacheEntry:
    """Internal cache entry for storing article analysis results."""

    result: ArticleSentiment
    expires_at: float  # Unix timestamp


class NewsAnalyzer:
    """
    News sentiment analyzer using Ollama LLM.

    Fetches crypto news from RSS feeds and analyzes sentiment using a local
    Ollama instance. Includes caching to avoid redundant LLM calls.

    Requirements:
        - 11.1: Connect to local Ollama instance for LLM inference
        - 11.2: Fetch recent crypto news from configurable RSS feeds
        - 11.3: Extract sentiment (bullish/bearish/neutral) and confidence per article
        - 11.4: Identify mentioned cryptocurrencies and associate sentiment with trading pairs
        - 11.5: Incorporate news sentiment as weighted factor in confidence scoring
        - 11.6: Graceful degradation when Ollama is unavailable
        - 11.7: Cache results to avoid redundant LLM calls
        - 11.8: Support configurable LLM model selection

    Example:
        >>> analyzer = NewsAnalyzer()
        >>> result = await analyzer.analyze_news()
        >>> print(f"Sentiment: {result.overall_sentiment}, Signal: {result.signal}")
    """

    # Common cryptocurrency symbols to detect in articles
    CRYPTO_SYMBOLS = {
        "BTC": ["bitcoin", "btc"],
        "ETH": ["ethereum", "eth", "ether"],
        "SOL": ["solana", "sol"],
        "XRP": ["ripple", "xrp"],
        "ADA": ["cardano", "ada"],
        "DOGE": ["dogecoin", "doge"],
        "DOT": ["polkadot", "dot"],
        "AVAX": ["avalanche", "avax"],
        "LINK": ["chainlink", "link"],
        "MATIC": ["polygon", "matic"],
        "UNI": ["uniswap", "uni"],
        "ATOM": ["cosmos", "atom"],
        "LTC": ["litecoin", "ltc"],
        "BNB": ["binance", "bnb"],
    }

    def __init__(
        self,
        config: NewsAnalyzerConfig | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """
        Initialize the NewsAnalyzer.

        Args:
            config: Optional configuration for the analyzer.
                    Uses defaults if not provided.
            http_client: Optional httpx AsyncClient for dependency injection.
                        Creates a new client if not provided.
        """
        self.config = config or NewsAnalyzerConfig()
        self._http_client = http_client
        self._owns_client = http_client is None
        self._cache: dict[str, _CacheEntry] = {}
        self._cache_lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.http_timeout_seconds)
            )
        return self._http_client

    async def close(self) -> None:
        """Close the HTTP client if we own it."""
        if self._owns_client and self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def __aenter__(self) -> NewsAnalyzer:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()

    def _generate_cache_key(self, article: NewsArticle) -> str:
        """
        Generate a unique cache key for an article.

        Uses a hash of the article's link and title to create a unique identifier.

        Args:
            article: The article to generate a key for

        Returns:
            A unique cache key string
        """
        content = f"{article.link}:{article.title}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _is_cache_valid(self, key: str) -> bool:
        """Check if a cache entry is still valid."""
        if key not in self._cache:
            return False
        return time.time() < self._cache[key].expires_at

    def _get_cached_result(self, article: NewsArticle) -> ArticleSentiment | None:
        """
        Get cached result for an article if valid.

        Args:
            article: The article to look up

        Returns:
            Cached ArticleSentiment with cached=True, or None if not cached

        Requirements:
            - 11.7: Cache results to avoid redundant LLM calls
        """
        key = self._generate_cache_key(article)
        if not self._is_cache_valid(key):
            return None

        cached = self._cache[key]
        # Return a copy with cached=True
        return ArticleSentiment(
            article=cached.result.article,
            sentiment=cached.result.sentiment,
            confidence=cached.result.confidence,
            mentioned_symbols=cached.result.mentioned_symbols,
            reasoning=cached.result.reasoning,
            cached=True,
            analysis_timestamp=cached.result.analysis_timestamp,
        )

    def _cache_result(self, article: NewsArticle, result: ArticleSentiment) -> None:
        """
        Cache an analysis result.

        Args:
            article: The analyzed article
            result: The analysis result to cache

        Requirements:
            - 11.7: Cache results to avoid redundant LLM calls
        """
        key = self._generate_cache_key(article)
        self._cache[key] = _CacheEntry(
            result=result,
            expires_at=time.time() + self.config.cache_duration_seconds,
        )

    def clear_cache(self) -> None:
        """Clear all cached results."""
        self._cache.clear()

    def get_cache_stats(self) -> dict[str, int]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        now = time.time()
        valid_entries = sum(1 for entry in self._cache.values() if entry.expires_at > now)
        return {
            "total_entries": len(self._cache),
            "valid_entries": valid_entries,
            "expired_entries": len(self._cache) - valid_entries,
        }

    async def check_ollama_available(self) -> bool:
        """
        Check if Ollama is available and responding.

        Returns:
            True if Ollama is available, False otherwise

        Requirements:
            - 11.6: Graceful degradation when Ollama is unavailable
        """
        try:
            client = await self._get_client()
            response = await client.get(f"{self.config.ollama_url}/api/tags")
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama availability check failed: {e}")
            return False

    async def fetch_news(self) -> list[NewsArticle]:
        """
        Fetch news articles from configured RSS feeds.

        Returns:
            List of NewsArticle objects

        Requirements:
            - 11.2: Fetch recent crypto news from configurable RSS feeds
        """
        articles: list[NewsArticle] = []
        client = await self._get_client()

        for feed_url in self.config.rss_feeds:
            try:
                response = await client.get(feed_url)
                response.raise_for_status()

                feed_articles = self._parse_rss_feed(response.text, feed_url)
                articles.extend(feed_articles)

                logger.debug(f"Fetched {len(feed_articles)} articles from {feed_url}")
            except Exception as e:
                logger.warning(f"Failed to fetch RSS feed {feed_url}: {e}")
                continue

        # Sort by publication date (newest first) and limit
        articles.sort(
            key=lambda a: a.published or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )

        return articles[: self.config.max_articles]

    def _parse_rss_feed(self, xml_content: str, source_url: str) -> list[NewsArticle]:
        """
        Parse RSS feed XML content into NewsArticle objects.

        Args:
            xml_content: Raw XML content from RSS feed
            source_url: URL of the RSS feed (for source attribution)

        Returns:
            List of NewsArticle objects
        """
        articles: list[NewsArticle] = []

        try:
            root = ET.fromstring(xml_content)

            # Handle both RSS 2.0 and Atom feeds
            items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")

            for item in items:
                try:
                    # RSS 2.0 format
                    title = (
                        item.findtext("title")
                        or item.findtext("{http://www.w3.org/2005/Atom}title")
                        or ""
                    )
                    description = (
                        item.findtext("description")
                        or item.findtext("{http://www.w3.org/2005/Atom}summary")
                        or item.findtext("{http://www.w3.org/2005/Atom}content")
                        or ""
                    )
                    link = item.findtext("link") or ""
                    if not link:
                        link_elem = item.find("{http://www.w3.org/2005/Atom}link")
                        if link_elem is not None:
                            link = link_elem.get("href", "")

                    pub_date_str = (
                        item.findtext("pubDate")
                        or item.findtext("{http://www.w3.org/2005/Atom}published")
                        or item.findtext("{http://www.w3.org/2005/Atom}updated")
                    )

                    published = self._parse_date(pub_date_str) if pub_date_str else None

                    # Extract source name from URL
                    source = source_url.split("/")[2] if "/" in source_url else source_url

                    if title:  # Only add if we have a title
                        articles.append(
                            NewsArticle(
                                title=title.strip(),
                                description=description.strip()[:500],  # Limit description length
                                link=link.strip(),
                                published=published,
                                source=source,
                            )
                        )
                except Exception as e:
                    logger.debug(f"Failed to parse RSS item: {e}")
                    continue

        except ET.ParseError as e:
            logger.warning(f"Failed to parse RSS XML: {e}")

        return articles

    def _parse_date(self, date_str: str) -> datetime | None:
        """
        Parse various date formats from RSS feeds.

        Args:
            date_str: Date string from RSS feed

        Returns:
            Parsed datetime or None if parsing fails
        """
        formats = [
            "%a, %d %b %Y %H:%M:%S %z",  # RFC 822
            "%a, %d %b %Y %H:%M:%S %Z",  # RFC 822 with timezone name
            "%Y-%m-%dT%H:%M:%S%z",  # ISO 8601
            "%Y-%m-%dT%H:%M:%SZ",  # ISO 8601 UTC
            "%Y-%m-%d %H:%M:%S",  # Simple format
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                return dt
            except ValueError:
                continue

        return None

    def _detect_symbols(self, text: str) -> list[str]:
        """
        Detect cryptocurrency symbols mentioned in text.

        Args:
            text: Text to search for cryptocurrency mentions

        Returns:
            List of detected symbol strings (e.g., ["BTC", "ETH"])

        Requirements:
            - 11.4: Identify mentioned cryptocurrencies
        """
        text_lower = text.lower()
        detected: list[str] = []

        for symbol, keywords in self.CRYPTO_SYMBOLS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    if symbol not in detected:
                        detected.append(symbol)
                    break

        return detected

    async def analyze_article(self, article: NewsArticle) -> ArticleSentiment:
        """
        Analyze sentiment of a single article using Ollama LLM.

        Args:
            article: The article to analyze

        Returns:
            ArticleSentiment with sentiment, confidence, and metadata

        Requirements:
            - 11.1: Connect to local Ollama instance for LLM inference
            - 11.3: Extract sentiment (bullish/bearish/neutral) and confidence
            - 11.7: Cache results to avoid redundant LLM calls
        """
        # Check cache first
        async with self._cache_lock:
            cached = self._get_cached_result(article)
            if cached is not None:
                logger.debug(f"Cache hit for article: {article.title[:50]}...")
                return cached

        # Detect mentioned symbols
        combined_text = f"{article.title} {article.description}"
        mentioned_symbols = self._detect_symbols(combined_text)

        # Analyze with LLM
        try:
            sentiment, confidence, reasoning = await self._analyze_with_ollama(article)
        except Exception as e:
            logger.warning(f"Ollama analysis failed for article: {e}")
            # Return neutral sentiment on failure
            sentiment = NewsSentiment.NEUTRAL
            confidence = 50.0
            reasoning = f"Analysis failed: {e}"

        result = ArticleSentiment(
            article=article,
            sentiment=sentiment,
            confidence=confidence,
            mentioned_symbols=mentioned_symbols,
            reasoning=reasoning,
            cached=False,
            analysis_timestamp=datetime.now(tz=UTC),
        )

        # Cache the result
        async with self._cache_lock:
            self._cache_result(article, result)

        return result

    async def _analyze_with_ollama(self, article: NewsArticle) -> tuple[NewsSentiment, float, str]:
        """
        Send article to Ollama for sentiment analysis.

        Args:
            article: The article to analyze

        Returns:
            Tuple of (sentiment, confidence, reasoning)

        Requirements:
            - 11.1: Connect to local Ollama instance for LLM inference
            - 11.8: Support configurable LLM model selection
        """
        client = await self._get_client()

        prompt = f"""Analyze the sentiment of this cryptocurrency news article for trading purposes.

Title: {article.title}
Description: {article.description}

Respond with EXACTLY this format (no other text):
SENTIMENT: [bullish/bearish/neutral]
CONFIDENCE: [0-100]
REASONING: [one sentence explanation]

Rules:
- bullish = positive for crypto prices (good news, adoption, growth)
- bearish = negative for crypto prices (bad news, regulation, hacks)
- neutral = no clear impact on prices
- Confidence should reflect how strongly the article indicates the sentiment"""

        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,  # Low temperature for consistent analysis
                "num_predict": 150,  # Limit response length
            },
        }

        response = await client.post(
            f"{self.config.ollama_url}/api/generate",
            json=payload,
        )
        response.raise_for_status()

        result = response.json()
        response_text = result.get("response", "")

        return self._parse_ollama_response(response_text)

    def _parse_ollama_response(self, response_text: str) -> tuple[NewsSentiment, float, str]:
        """
        Parse Ollama's response into structured sentiment data.

        Args:
            response_text: Raw response from Ollama

        Returns:
            Tuple of (sentiment, confidence, reasoning)
        """
        lines = response_text.strip().split("\n")

        sentiment = NewsSentiment.NEUTRAL
        confidence = 50.0
        reasoning = "Unable to parse response"

        for line in lines:
            line = line.strip()
            if line.upper().startswith("SENTIMENT:"):
                sentiment_str = line.split(":", 1)[1].strip().lower()
                if "bullish" in sentiment_str:
                    sentiment = NewsSentiment.BULLISH
                elif "bearish" in sentiment_str:
                    sentiment = NewsSentiment.BEARISH
                else:
                    sentiment = NewsSentiment.NEUTRAL
            elif line.upper().startswith("CONFIDENCE:"):
                try:
                    conf_str = line.split(":", 1)[1].strip()
                    # Extract number from string (handle "85%" or "85" formats)
                    conf_num = "".join(c for c in conf_str if c.isdigit() or c == ".")
                    confidence = float(conf_num) if conf_num else 50.0
                    confidence = max(0.0, min(100.0, confidence))  # Clamp to [0, 100]
                except (ValueError, IndexError):
                    confidence = 50.0
            elif line.upper().startswith("REASONING:"):
                reasoning = line.split(":", 1)[1].strip() if ":" in line else line

        return sentiment, confidence, reasoning

    def _sentiment_to_signal(self, sentiment: NewsSentiment) -> SignalDirection:
        """
        Convert news sentiment to trading signal.

        Args:
            sentiment: The news sentiment

        Returns:
            Trading signal direction
        """
        if sentiment == NewsSentiment.BULLISH:
            return SignalDirection.BUY
        elif sentiment == NewsSentiment.BEARISH:
            return SignalDirection.SELL
        else:
            return SignalDirection.HOLD

    async def analyze_news(
        self,
        symbol: str | None = None,
        force_refresh: bool = False,
    ) -> NewsAnalysisResult:
        """
        Analyze news sentiment for trading decisions.

        Fetches news from RSS feeds, analyzes each article with Ollama,
        and aggregates the results into an overall sentiment.

        Args:
            symbol: Optional symbol to filter news for (e.g., "BTC")
            force_refresh: If True, bypass cache for all articles

        Returns:
            NewsAnalysisResult with aggregated sentiment and signal

        Requirements:
            - 11.1-11.8: Full news analysis pipeline
        """
        # Check Ollama availability first
        ollama_available = await self.check_ollama_available()
        if not ollama_available:
            logger.warning("Ollama is unavailable, proceeding without news analysis")
            return self._create_unavailable_result(
                ollama_unavailable=True,
                error_message="Ollama LLM is unavailable",
            )

        # Fetch news articles
        try:
            articles = await self.fetch_news()
        except Exception as e:
            logger.error(f"Failed to fetch news: {e}")
            return self._create_unavailable_result(
                data_unavailable=True,
                error_message=f"Failed to fetch news: {e}",
            )

        if not articles:
            logger.warning("No news articles found")
            return self._create_unavailable_result(
                data_unavailable=True,
                error_message="No news articles available",
            )

        # Clear cache if force refresh
        if force_refresh:
            self.clear_cache()

        # Analyze each article
        article_sentiments: list[ArticleSentiment] = []
        for article in articles:
            try:
                sentiment = await self.analyze_article(article)

                # Filter by symbol if specified
                if symbol is None or symbol in sentiment.mentioned_symbols:
                    article_sentiments.append(sentiment)
            except Exception as e:
                logger.warning(f"Failed to analyze article '{article.title[:50]}...': {e}")
                continue

        if not article_sentiments:
            return self._create_unavailable_result(
                data_unavailable=True,
                error_message="No articles could be analyzed",
            )

        # Aggregate results
        return self._aggregate_sentiments(article_sentiments)

    def _aggregate_sentiments(
        self, article_sentiments: list[ArticleSentiment]
    ) -> NewsAnalysisResult:
        """
        Aggregate individual article sentiments into overall result.

        Args:
            article_sentiments: List of individual article sentiments

        Returns:
            Aggregated NewsAnalysisResult
        """
        bullish_count = sum(1 for s in article_sentiments if s.sentiment == NewsSentiment.BULLISH)
        bearish_count = sum(1 for s in article_sentiments if s.sentiment == NewsSentiment.BEARISH)
        neutral_count = sum(1 for s in article_sentiments if s.sentiment == NewsSentiment.NEUTRAL)

        # Calculate weighted average confidence
        total_confidence = sum(s.confidence for s in article_sentiments)
        avg_confidence = total_confidence / len(article_sentiments) if article_sentiments else 50.0

        # Determine overall sentiment based on majority
        if bullish_count > bearish_count and bullish_count > neutral_count:
            overall_sentiment = NewsSentiment.BULLISH
            # Boost confidence if strong majority
            sentiment_ratio = bullish_count / len(article_sentiments)
            overall_confidence = avg_confidence * (0.5 + 0.5 * sentiment_ratio)
        elif bearish_count > bullish_count and bearish_count > neutral_count:
            overall_sentiment = NewsSentiment.BEARISH
            sentiment_ratio = bearish_count / len(article_sentiments)
            overall_confidence = avg_confidence * (0.5 + 0.5 * sentiment_ratio)
        else:
            overall_sentiment = NewsSentiment.NEUTRAL
            overall_confidence = avg_confidence * 0.5  # Reduce confidence for neutral

        # Clamp confidence to [0, 100]
        overall_confidence = max(0.0, min(100.0, overall_confidence))

        # Build symbol sentiment map
        symbol_sentiments: dict[str, NewsSentiment] = {}
        for sentiment in article_sentiments:
            for symbol in sentiment.mentioned_symbols:
                if symbol not in symbol_sentiments:
                    # Use first occurrence's sentiment
                    symbol_sentiments[symbol] = sentiment.sentiment

        return NewsAnalysisResult(
            overall_sentiment=overall_sentiment,
            overall_confidence=overall_confidence,
            signal=self._sentiment_to_signal(overall_sentiment),
            articles_analyzed=len(article_sentiments),
            bullish_count=bullish_count,
            bearish_count=bearish_count,
            neutral_count=neutral_count,
            article_sentiments=tuple(article_sentiments),
            symbol_sentiments=symbol_sentiments,
            data_unavailable=False,
            ollama_unavailable=False,
            error_message=None,
            timestamp=datetime.now(tz=UTC),
        )

    def _create_unavailable_result(
        self,
        data_unavailable: bool = False,
        ollama_unavailable: bool = False,
        error_message: str | None = None,
    ) -> NewsAnalysisResult:
        """
        Create a result for when analysis is unavailable.

        Args:
            data_unavailable: Whether news data was unavailable
            ollama_unavailable: Whether Ollama was unavailable
            error_message: Description of the error

        Returns:
            NewsAnalysisResult with neutral sentiment and HOLD signal

        Requirements:
            - 11.6: Graceful degradation when Ollama is unavailable
        """
        return NewsAnalysisResult(
            overall_sentiment=NewsSentiment.NEUTRAL,
            overall_confidence=0.0,
            signal=SignalDirection.HOLD,
            articles_analyzed=0,
            bullish_count=0,
            bearish_count=0,
            neutral_count=0,
            article_sentiments=(),
            symbol_sentiments={},
            data_unavailable=data_unavailable,
            ollama_unavailable=ollama_unavailable,
            error_message=error_message,
            timestamp=datetime.now(tz=UTC),
        )

    async def analyze_for_symbol(self, symbol: str) -> NewsAnalysisResult:
        """
        Analyze news sentiment for a specific trading symbol.

        Args:
            symbol: Trading symbol (e.g., "BTC", "ETH")

        Returns:
            NewsAnalysisResult filtered for the specified symbol

        Requirements:
            - 11.4: Associate sentiment with specific trading pairs
        """
        return await self.analyze_news(symbol=symbol)
