"""
Sentiment Analysis Library for Fear & Greed Index.

This module provides sentiment analysis by fetching and interpreting the
Fear & Greed Index from the Alternative.me API.

Requirements:
- 4.1: Fetch Fear & Greed Index from Alternative.me API
- 4.2: Interpret FGI values: 0-25 = Extreme Fear (BUY), 75-100 = Extreme Greed (SELL)
- 4.3: Handle API unavailability gracefully (return neutral/HOLD signal)
- 4.4: Cache FGI values to avoid excessive API calls (configurable duration)
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

import httpx

from lib.analysis.technical import SignalDirection

if TYPE_CHECKING:
    pass


class FearGreedClassification(Enum):
    """Classification of Fear & Greed Index values."""

    EXTREME_FEAR = "Extreme Fear"
    FEAR = "Fear"
    NEUTRAL = "Neutral"
    GREED = "Greed"
    EXTREME_GREED = "Extreme Greed"


@dataclass(frozen=True)
class SentimentResult:
    """
    Result of sentiment analysis.

    Attributes:
        value: Fear & Greed Index value (0-100), None if unavailable
        classification: Human-readable classification of the value
        signal: Trading signal derived from the value
        timestamp: When the data was fetched/cached
        data_unavailable: Whether the API was unavailable
        cached: Whether this result was served from cache
        error_message: Error message if API call failed
    """

    value: int | None
    classification: FearGreedClassification
    signal: SignalDirection
    timestamp: datetime
    data_unavailable: bool = False
    cached: bool = False
    error_message: str | None = None


@dataclass
class SentimentConfig:
    """
    Configuration for SentimentAnalyzer.

    Attributes:
        api_url: URL for the Fear & Greed Index API
        cache_duration_seconds: How long to cache results (default 3600 = 1 hour)
        timeout_seconds: HTTP request timeout (default 10 seconds)
        extreme_fear_threshold: Upper bound for extreme fear (default 25)
        fear_threshold: Upper bound for fear (default 45)
        greed_threshold: Lower bound for greed (default 55)
        extreme_greed_threshold: Lower bound for extreme greed (default 75)
    """

    api_url: str = "https://api.alternative.me/fng/"
    cache_duration_seconds: int = 3600
    timeout_seconds: float = 10.0
    extreme_fear_threshold: int = 25
    fear_threshold: int = 45
    greed_threshold: int = 55
    extreme_greed_threshold: int = 75


@dataclass
class _CacheEntry:
    """Internal cache entry for storing FGI results."""

    result: SentimentResult
    expires_at: float  # Unix timestamp


class SentimentAnalyzer:
    """
    Sentiment analyzer using Fear & Greed Index.

    Fetches the Fear & Greed Index from Alternative.me API and interprets
    the values to generate trading signals. Includes caching to avoid
    excessive API calls.

    Requirements:
        - 4.1: Fetch Fear & Greed Index from Alternative.me API
        - 4.2: Interpret FGI values: 0-25 = Extreme Fear (BUY), 75-100 = Extreme Greed (SELL)
        - 4.3: Handle API unavailability gracefully (return neutral/HOLD signal)
        - 4.4: Cache FGI values to avoid excessive API calls (configurable duration)

    Example:
        >>> analyzer = SentimentAnalyzer()
        >>> result = await analyzer.get_fear_greed_index()
        >>> print(f"FGI: {result.value}, Signal: {result.signal}")
    """

    def __init__(
        self,
        config: SentimentConfig | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """
        Initialize the SentimentAnalyzer.

        Args:
            config: Optional configuration for the analyzer.
                    Uses defaults if not provided.
            http_client: Optional httpx AsyncClient for dependency injection.
                        Creates a new client if not provided.
        """
        self.config = config or SentimentConfig()
        self._http_client = http_client
        self._owns_client = http_client is None
        self._cache: _CacheEntry | None = None
        self._cache_lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.timeout_seconds)
            )
        return self._http_client

    async def close(self) -> None:
        """Close the HTTP client if we own it."""
        if self._owns_client and self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def __aenter__(self) -> SentimentAnalyzer:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()

    def classify_value(self, value: int) -> FearGreedClassification:
        """
        Classify a Fear & Greed Index value.

        Args:
            value: FGI value (0-100)

        Returns:
            Classification enum value
        """
        if value <= self.config.extreme_fear_threshold:
            return FearGreedClassification.EXTREME_FEAR
        elif value <= self.config.fear_threshold:
            return FearGreedClassification.FEAR
        elif value < self.config.greed_threshold:
            return FearGreedClassification.NEUTRAL
        elif value < self.config.extreme_greed_threshold:
            return FearGreedClassification.GREED
        else:
            return FearGreedClassification.EXTREME_GREED

    def value_to_signal(self, value: int) -> SignalDirection:
        """
        Convert a Fear & Greed Index value to a trading signal.

        Requirement 4.2:
        - 0-25 (Extreme Fear) = BUY signal (contrarian: buy when others are fearful)
        - 75-100 (Extreme Greed) = SELL signal (contrarian: sell when others are greedy)
        - 26-74 = HOLD signal (neutral zone)

        Args:
            value: FGI value (0-100)

        Returns:
            Trading signal direction
        """
        if value <= self.config.extreme_fear_threshold:
            return SignalDirection.BUY
        elif value >= self.config.extreme_greed_threshold:
            return SignalDirection.SELL
        else:
            return SignalDirection.HOLD

    def _is_cache_valid(self) -> bool:
        """Check if the cache is still valid."""
        if self._cache is None:
            return False
        return time.time() < self._cache.expires_at

    def _get_cached_result(self) -> SentimentResult | None:
        """Get cached result if valid, marking it as cached."""
        if not self._is_cache_valid():
            return None

        cached = self._cache
        if cached is None:
            return None

        # Return a copy with cached=True
        return SentimentResult(
            value=cached.result.value,
            classification=cached.result.classification,
            signal=cached.result.signal,
            timestamp=cached.result.timestamp,
            data_unavailable=cached.result.data_unavailable,
            cached=True,
            error_message=cached.result.error_message,
        )

    def _cache_result(self, result: SentimentResult) -> None:
        """Cache a result with expiration."""
        self._cache = _CacheEntry(
            result=result,
            expires_at=time.time() + self.config.cache_duration_seconds,
        )

    def clear_cache(self) -> None:
        """Clear the cached result."""
        self._cache = None

    async def get_fear_greed_index(self, force_refresh: bool = False) -> SentimentResult:
        """
        Get the current Fear & Greed Index.

        Fetches the FGI from Alternative.me API, with caching to avoid
        excessive API calls. Handles API unavailability gracefully by
        returning a neutral HOLD signal.

        Args:
            force_refresh: If True, bypass cache and fetch fresh data

        Returns:
            SentimentResult with value, classification, signal, and metadata

        Requirements:
            - 4.1: Fetch Fear & Greed Index from Alternative.me API
            - 4.2: Interpret FGI values to signals
            - 4.3: Handle API unavailability gracefully
            - 4.4: Cache FGI values to avoid excessive API calls
        """
        async with self._cache_lock:
            # Check cache first (unless force refresh)
            if not force_refresh:
                cached = self._get_cached_result()
                if cached is not None:
                    return cached

            # Fetch from API
            try:
                result = await self._fetch_from_api()
                self._cache_result(result)
                return result
            except Exception as e:
                # Requirement 4.3: Handle API unavailability gracefully
                return self._create_unavailable_result(str(e))

    async def _fetch_from_api(self) -> SentimentResult:
        """
        Fetch Fear & Greed Index from the API.

        Returns:
            SentimentResult with fetched data

        Raises:
            Exception: If API call fails
        """
        client = await self._get_client()

        response = await client.get(self.config.api_url)
        response.raise_for_status()

        data = response.json()

        # Parse the API response
        # Alternative.me API returns: {"name": "Fear and Greed Index", "data": [{"value": "23", ...}]}
        if "data" not in data or not data["data"]:
            raise ValueError("Invalid API response: missing 'data' field")

        fgi_data = data["data"][0]
        value_str = fgi_data.get("value")

        if value_str is None:
            raise ValueError("Invalid API response: missing 'value' field")

        value = int(value_str)

        # Validate value is in expected range
        if not 0 <= value <= 100:
            raise ValueError(f"Invalid FGI value: {value} (expected 0-100)")

        # Get timestamp from API or use current time
        timestamp_str = fgi_data.get("timestamp")
        if timestamp_str:
            timestamp = datetime.fromtimestamp(int(timestamp_str), tz=UTC)
        else:
            timestamp = datetime.now(tz=UTC)

        classification = self.classify_value(value)
        signal = self.value_to_signal(value)

        return SentimentResult(
            value=value,
            classification=classification,
            signal=signal,
            timestamp=timestamp,
            data_unavailable=False,
            cached=False,
            error_message=None,
        )

    def _create_unavailable_result(self, error_message: str) -> SentimentResult:
        """
        Create a result for when the API is unavailable.

        Requirement 4.3: Handle API unavailability gracefully by returning
        a neutral HOLD signal.

        Args:
            error_message: Description of the error

        Returns:
            SentimentResult with data_unavailable=True and HOLD signal
        """
        return SentimentResult(
            value=None,
            classification=FearGreedClassification.NEUTRAL,
            signal=SignalDirection.HOLD,
            timestamp=datetime.now(tz=UTC),
            data_unavailable=True,
            cached=False,
            error_message=error_message,
        )
