"""
Property-based tests for News Caching Module.

Feature: pionex-trading-bot
Property 18: News Cache Hit

These tests use the hypothesis library to verify that the news analyzer
caching behaves correctly - cached results are returned without LLM calls.

**Validates: Requirements 11.7**
"""

from datetime import UTC, datetime

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from lib.analysis.news import (
    ArticleSentiment,
    NewsAnalyzer,
    NewsAnalyzerConfig,
    NewsArticle,
    NewsSentiment,
)

# =============================================================================
# Custom Strategies for News Articles
# =============================================================================

# Strategy for article titles
title_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=5,
    max_size=100,
).filter(lambda x: x.strip())

# Strategy for article descriptions
description_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=10,
    max_size=300,
).filter(lambda x: x.strip())

# Strategy for URLs
url_strategy = st.from_regex(
    r"https://[a-z]{3,10}\.[a-z]{2,5}/[a-z0-9\-]{5,20}",
    fullmatch=True,
)

# Strategy for source names
source_strategy = st.from_regex(r"[a-z]{3,15}\.[a-z]{2,5}", fullmatch=True)


@st.composite
def news_article_strategy(draw: st.DrawFn) -> NewsArticle:
    """
    Generate valid NewsArticle objects.
    """
    title = draw(title_strategy)
    description = draw(description_strategy)
    link = draw(url_strategy)
    source = draw(source_strategy)

    return NewsArticle(
        title=title,
        description=description,
        link=link,
        published=datetime.now(tz=UTC),
        source=source,
    )


# Strategy for sentiment values
sentiment_strategy = st.sampled_from(
    [
        NewsSentiment.BULLISH,
        NewsSentiment.BEARISH,
        NewsSentiment.NEUTRAL,
    ]
)

# Strategy for confidence values
confidence_strategy = st.floats(min_value=0.0, max_value=100.0, allow_nan=False)

# Strategy for cryptocurrency symbols
symbol_strategy = st.sampled_from(["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE"])

# Strategy for symbol lists
symbol_list_strategy = st.lists(symbol_strategy, min_size=0, max_size=3, unique=True)

# Strategy for reasoning text
reasoning_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=5,
    max_size=100,
).filter(lambda x: x.strip())


@st.composite
def article_sentiment_strategy(draw: st.DrawFn) -> tuple[NewsArticle, ArticleSentiment]:
    """
    Generate a NewsArticle and its corresponding ArticleSentiment.
    """
    article = draw(news_article_strategy())
    sentiment = draw(sentiment_strategy)
    confidence = draw(confidence_strategy)
    symbols = draw(symbol_list_strategy)
    reasoning = draw(reasoning_strategy)

    article_sentiment = ArticleSentiment(
        article=article,
        sentiment=sentiment,
        confidence=confidence,
        mentioned_symbols=symbols,
        reasoning=reasoning,
        cached=False,
        analysis_timestamp=datetime.now(tz=UTC),
    )

    return article, article_sentiment


# =============================================================================
# Property 18: News Cache Hit
# =============================================================================


class TestNewsCacheHit:
    """
    Property 18: News Cache Hit

    *For any* article analyzed twice, second call SHALL return cached result
    without LLM call.

    **Validates: Requirements 11.7**
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(data=article_sentiment_strategy())
    def test_cache_key_determinism(
        self,
        data: tuple[NewsArticle, ArticleSentiment],
    ) -> None:
        """
        Property: For any article, generating cache key twice SHALL produce
        identical results.

        Cache key generation must be deterministic for consistent caching.

        **Validates: Requirements 11.7**
        """
        article, _ = data
        analyzer = NewsAnalyzer()

        key1 = analyzer._generate_cache_key(article)
        key2 = analyzer._generate_cache_key(article)

        assert key1 == key2, (
            f"Cache key not deterministic for article '{article.title[:30]}...': "
            f"got {key1} and {key2}"
        )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        data1=article_sentiment_strategy(),
        data2=article_sentiment_strategy(),
    )
    def test_different_articles_different_keys(
        self,
        data1: tuple[NewsArticle, ArticleSentiment],
        data2: tuple[NewsArticle, ArticleSentiment],
    ) -> None:
        """
        Property: For any two different articles, cache keys SHALL be different.

        This ensures cache collisions don't occur between different articles.

        **Validates: Requirements 11.7**
        """
        article1, _ = data1
        article2, _ = data2

        # Skip if articles have same link (would be same article)
        assume(article1.link != article2.link)

        analyzer = NewsAnalyzer()

        key1 = analyzer._generate_cache_key(article1)
        key2 = analyzer._generate_cache_key(article2)

        assert key1 != key2, (
            f"Different articles produced same cache key: "
            f"'{article1.title[:20]}...' and '{article2.title[:20]}...' "
            f"both got key {key1}"
        )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(data=article_sentiment_strategy())
    def test_cached_result_marked_as_cached(
        self,
        data: tuple[NewsArticle, ArticleSentiment],
    ) -> None:
        """
        Property: For any cached result, the cached flag SHALL be True.

        This ensures cached results are properly identified.

        **Validates: Requirements 11.7**
        """
        article, sentiment = data
        analyzer = NewsAnalyzer()

        # Cache the result
        analyzer._cache_result(article, sentiment)

        # Retrieve from cache
        cached = analyzer._get_cached_result(article)

        assert cached is not None, "Cached result should be retrievable"
        assert cached.cached is True, f"Cached result should have cached=True, got {cached.cached}"

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(data=article_sentiment_strategy())
    def test_cached_result_preserves_sentiment(
        self,
        data: tuple[NewsArticle, ArticleSentiment],
    ) -> None:
        """
        Property: For any cached result, sentiment SHALL be preserved.

        Caching must not alter the sentiment analysis result.

        **Validates: Requirements 11.7**
        """
        article, sentiment = data
        analyzer = NewsAnalyzer()

        # Cache the result
        analyzer._cache_result(article, sentiment)

        # Retrieve from cache
        cached = analyzer._get_cached_result(article)

        assert cached is not None, "Cached result should be retrievable"
        assert cached.sentiment == sentiment.sentiment, (
            f"Cached sentiment {cached.sentiment} != original {sentiment.sentiment}"
        )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(data=article_sentiment_strategy())
    def test_cached_result_preserves_confidence(
        self,
        data: tuple[NewsArticle, ArticleSentiment],
    ) -> None:
        """
        Property: For any cached result, confidence SHALL be preserved.

        Caching must not alter the confidence score.

        **Validates: Requirements 11.7**
        """
        article, sentiment = data
        analyzer = NewsAnalyzer()

        # Cache the result
        analyzer._cache_result(article, sentiment)

        # Retrieve from cache
        cached = analyzer._get_cached_result(article)

        assert cached is not None, "Cached result should be retrievable"
        assert cached.confidence == sentiment.confidence, (
            f"Cached confidence {cached.confidence} != original {sentiment.confidence}"
        )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(data=article_sentiment_strategy())
    def test_cached_result_preserves_symbols(
        self,
        data: tuple[NewsArticle, ArticleSentiment],
    ) -> None:
        """
        Property: For any cached result, mentioned symbols SHALL be preserved.

        Caching must not alter the detected cryptocurrency symbols.

        **Validates: Requirements 11.7**
        """
        article, sentiment = data
        analyzer = NewsAnalyzer()

        # Cache the result
        analyzer._cache_result(article, sentiment)

        # Retrieve from cache
        cached = analyzer._get_cached_result(article)

        assert cached is not None, "Cached result should be retrievable"
        assert cached.mentioned_symbols == sentiment.mentioned_symbols, (
            f"Cached symbols {cached.mentioned_symbols} != original {sentiment.mentioned_symbols}"
        )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(data=article_sentiment_strategy())
    def test_cached_result_preserves_reasoning(
        self,
        data: tuple[NewsArticle, ArticleSentiment],
    ) -> None:
        """
        Property: For any cached result, reasoning SHALL be preserved.

        Caching must not alter the LLM's reasoning.

        **Validates: Requirements 11.7**
        """
        article, sentiment = data
        analyzer = NewsAnalyzer()

        # Cache the result
        analyzer._cache_result(article, sentiment)

        # Retrieve from cache
        cached = analyzer._get_cached_result(article)

        assert cached is not None, "Cached result should be retrievable"
        assert cached.reasoning == sentiment.reasoning, (
            f"Cached reasoning '{cached.reasoning[:30]}...' != "
            f"original '{sentiment.reasoning[:30]}...'"
        )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(data=article_sentiment_strategy())
    def test_uncached_article_returns_none(
        self,
        data: tuple[NewsArticle, ArticleSentiment],
    ) -> None:
        """
        Property: For any article not in cache, _get_cached_result SHALL return None.

        This ensures cache misses are properly handled.

        **Validates: Requirements 11.7**
        """
        article, _ = data
        analyzer = NewsAnalyzer()

        # Don't cache anything - should return None
        cached = analyzer._get_cached_result(article)

        assert cached is None, f"Uncached article should return None, got {cached}"

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(data=article_sentiment_strategy())
    def test_clear_cache_removes_all_entries(
        self,
        data: tuple[NewsArticle, ArticleSentiment],
    ) -> None:
        """
        Property: After clear_cache(), all cached results SHALL be removed.

        **Validates: Requirements 11.7**
        """
        article, sentiment = data
        analyzer = NewsAnalyzer()

        # Cache the result
        analyzer._cache_result(article, sentiment)

        # Verify it's cached
        assert analyzer._get_cached_result(article) is not None

        # Clear cache
        analyzer.clear_cache()

        # Verify it's gone
        cached = analyzer._get_cached_result(article)
        assert cached is None, f"Cache should be empty after clear_cache(), but found {cached}"


class TestCacheKeyProperties:
    """
    Tests for cache key generation properties.

    **Validates: Requirements 11.7**
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(article=news_article_strategy())
    def test_cache_key_is_string(
        self,
        article: NewsArticle,
    ) -> None:
        """
        Property: For any article, cache key SHALL be a string.

        **Validates: Requirements 11.7**
        """
        analyzer = NewsAnalyzer()
        key = analyzer._generate_cache_key(article)

        assert isinstance(key, str), f"Cache key should be string, got {type(key)}"

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(article=news_article_strategy())
    def test_cache_key_has_fixed_length(
        self,
        article: NewsArticle,
    ) -> None:
        """
        Property: For any article, cache key SHALL have fixed length (16 chars).

        This ensures consistent key format for storage.

        **Validates: Requirements 11.7**
        """
        analyzer = NewsAnalyzer()
        key = analyzer._generate_cache_key(article)

        assert len(key) == 16, f"Cache key should be 16 chars, got {len(key)}: {key}"

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(article=news_article_strategy())
    def test_cache_key_is_hexadecimal(
        self,
        article: NewsArticle,
    ) -> None:
        """
        Property: For any article, cache key SHALL be valid hexadecimal.

        **Validates: Requirements 11.7**
        """
        analyzer = NewsAnalyzer()
        key = analyzer._generate_cache_key(article)

        # Try to parse as hex - should not raise
        try:
            int(key, 16)
        except ValueError:
            pytest.fail(f"Cache key '{key}' is not valid hexadecimal")


class TestCacheStatsProperties:
    """
    Tests for cache statistics properties.

    **Validates: Requirements 11.7**
    """

    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        articles=st.lists(
            news_article_strategy(), min_size=1, max_size=10, unique_by=lambda a: a.link
        )
    )
    def test_cache_stats_count_matches_entries(
        self,
        articles: list[NewsArticle],
    ) -> None:
        """
        Property: Cache stats total_entries SHALL match number of cached items.

        **Validates: Requirements 11.7**
        """
        analyzer = NewsAnalyzer()

        # Cache multiple articles
        for article in articles:
            sentiment = ArticleSentiment(
                article=article,
                sentiment=NewsSentiment.NEUTRAL,
                confidence=50.0,
                mentioned_symbols=[],
                reasoning="Test",
            )
            analyzer._cache_result(article, sentiment)

        stats = analyzer.get_cache_stats()

        assert stats["total_entries"] == len(articles), (
            f"Cache stats show {stats['total_entries']} entries, "
            f"but cached {len(articles)} articles"
        )

    def test_empty_cache_stats(self) -> None:
        """
        Property: Empty cache SHALL have zero entries in stats.

        **Validates: Requirements 11.7**
        """
        analyzer = NewsAnalyzer()
        stats = analyzer.get_cache_stats()

        assert stats["total_entries"] == 0
        assert stats["valid_entries"] == 0
        assert stats["expired_entries"] == 0


class TestCacheConsistency:
    """
    Tests for cache consistency across multiple analyzers.

    **Validates: Requirements 11.7**
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(article=news_article_strategy())
    def test_same_article_same_key_different_analyzers(
        self,
        article: NewsArticle,
    ) -> None:
        """
        Property: Same article SHALL produce same cache key across different
        analyzer instances.

        This ensures cache keys are consistent and could be shared.

        **Validates: Requirements 11.7**
        """
        analyzer1 = NewsAnalyzer()
        analyzer2 = NewsAnalyzer()

        key1 = analyzer1._generate_cache_key(article)
        key2 = analyzer2._generate_cache_key(article)

        assert key1 == key2, f"Same article produced different keys: {key1} vs {key2}"

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        article=news_article_strategy(),
        config1=st.builds(
            NewsAnalyzerConfig,
            cache_duration_seconds=st.integers(min_value=60, max_value=7200),
        ),
        config2=st.builds(
            NewsAnalyzerConfig,
            cache_duration_seconds=st.integers(min_value=60, max_value=7200),
        ),
    )
    def test_cache_key_independent_of_config(
        self,
        article: NewsArticle,
        config1: NewsAnalyzerConfig,
        config2: NewsAnalyzerConfig,
    ) -> None:
        """
        Property: Cache key SHALL be independent of analyzer configuration.

        Different cache durations or other config should not affect key generation.

        **Validates: Requirements 11.7**
        """
        analyzer1 = NewsAnalyzer(config=config1)
        analyzer2 = NewsAnalyzer(config=config2)

        key1 = analyzer1._generate_cache_key(article)
        key2 = analyzer2._generate_cache_key(article)

        assert key1 == key2, f"Cache key should be config-independent: {key1} vs {key2}"
