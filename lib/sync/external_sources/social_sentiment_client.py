"""
Social Sentiment Client.

This module provides an async client for fetching aggregated social sentiment
scores from third-party APIs such as LunarCrush or Santiment. The client fetches
per-symbol sentiment polarity, mention counts, and buzz scores.

Requirements:
- 1.3.1: Async client class for social sentiment
- 1.3.2: Fetch per-symbol sentiment polarity (-1.0 to 1.0), mention count, buzz score
- 1.3.3: Return typed dataclass per symbol
- 1.3.4: Return None on API failure with error logging
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from lib.sync.external_sources import ExternalMetrics

logger = logging.getLogger(__name__)


# Default API endpoints
LUNARCRUSH_BASE_URL = "https://api.lunarcrush.com/v2"
SANTIMENT_BASE_URL = "https://api.santiment.net/graphql"


@dataclass(frozen=True)
class SocialSentimentClientConfig:
    """
    Configuration for the social sentiment client.

    Attributes:
        api_provider: Which API to use ("lunarcrush" or "santiment")
        api_key: API key for authenticated endpoints
        base_url: Base URL for the API (defaults to provider's public endpoint)
        timeout_seconds: Request timeout in seconds
        max_retries: Maximum number of retry attempts on failure

    Requirements:
        - 1.3.1: Configurable timeout and retries
        - 1.3.4: Environment variable configuration
    """

    api_provider: str = "lunarcrush"  # "lunarcrush" or "santiment"
    api_key: str | None = None
    base_url: str | None = None
    timeout_seconds: float = 30.0
    max_retries: int = 3

    @classmethod
    def from_env(cls) -> SocialSentimentClientConfig:
        """
        Create configuration from environment variables.

        Environment variables:
            SOCIAL_SENTIMENT_PROVIDER: API provider ("lunarcrush" or "santiment")
            SOCIAL_SENTIMENT_API_KEY: API key for authenticated endpoints
            SOCIAL_SENTIMENT_BASE_URL: Custom base URL (optional)
            SOCIAL_SENTIMENT_TIMEOUT: Request timeout in seconds
            SOCIAL_SENTIMENT_MAX_RETRIES: Maximum retry attempts

        Returns:
            SocialSentimentClientConfig instance

        Requirements:
            - 1.3.4: Support environment variable configuration
        """
        provider = os.getenv("SOCIAL_SENTIMENT_PROVIDER", "lunarcrush").lower()
        api_key = os.getenv("SOCIAL_SENTIMENT_API_KEY")
        base_url = os.getenv("SOCIAL_SENTIMENT_BASE_URL")
        timeout = float(os.getenv("SOCIAL_SENTIMENT_TIMEOUT", "30.0"))
        max_retries = int(os.getenv("SOCIAL_SENTIMENT_MAX_RETRIES", "3"))

        # Set default base URL based on provider if not specified
        if base_url is None:
            base_url = (
                LUNARCRUSH_BASE_URL if provider == "lunarcrush" else SANTIMENT_BASE_URL
            )

        return cls(
            api_provider=provider,
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout,
            max_retries=max_retries,
        )


class SocialSentimentClient:
    """
    Async client for fetching social sentiment from LunarCrush or Santiment.

    This client provides methods to fetch per-symbol:
    - Sentiment polarity (-1.0 to 1.0, where -1 is very negative, 1 is very positive)
    - Mention count (number of social media mentions)
    - Buzz score (normalized engagement/activity score)

    The client uses httpx.AsyncClient with configurable timeout and retries,
    and handles API failures gracefully by returning None and logging errors.

    Requirements:
        - 1.3.1: Async client class for social sentiment
        - 1.3.2: Fetch sentiment polarity, mention count, buzz score per symbol
        - 1.3.3: Return typed dataclass per symbol
        - 1.3.4: Return None on API failure with error logging

    Example:
        >>> config = SocialSentimentClientConfig.from_env()
        >>> client = SocialSentimentClient(config)
        >>> metrics = await client.fetch(["BTC", "ETH"])
        >>> await client.close()
    """

    def __init__(
        self,
        config: SocialSentimentClientConfig | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """
        Initialize the social sentiment client.

        Args:
            config: Client configuration (defaults to environment-based config)
            http_client: Optional httpx AsyncClient for making HTTP requests
                        (useful for testing with mocked client)

        Requirements:
            - 1.3.1: Use httpx.AsyncClient with configurable timeout
            - 1.3.4: Support environment variable configuration
        """
        self.config = config or SocialSentimentClientConfig.from_env()
        self._http_client = http_client
        self._owned_client = http_client is None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """
        Get or create HTTP client with retry configuration.

        Returns:
            Configured httpx.AsyncClient instance

        Requirements:
            - 1.3.1: Use httpx.AsyncClient with configurable timeout and retries
        """
        if self._http_client is None:
            # Create client with timeout and retry configuration
            transport = httpx.AsyncHTTPTransport(retries=self.config.max_retries)
            self._http_client = httpx.AsyncClient(
                timeout=self.config.timeout_seconds,
                transport=transport,
            )
        return self._http_client

    async def fetch(self, symbols: list[str]) -> list[ExternalMetrics]:
        """
        Fetch social sentiment metrics from the configured API provider.

        This method fetches social sentiment metrics for the specified symbols.

        Args:
            symbols: List of trading pair symbols (e.g., ["BTC", "ETH"])

        Returns:
            List of ExternalMetrics, one per symbol with social sentiment data,
            or empty list if fetch fails

        Requirements:
            - 1.3.2: Fetch sentiment polarity, mention count, buzz score per symbol
            - 1.3.3: Return typed dataclass per symbol
            - 1.3.4: Return None on API failure with error logging
        """
        try:
            if self.config.api_provider == "lunarcrush":
                return await self._fetch_lunarcrush(symbols)
            elif self.config.api_provider == "santiment":
                return await self._fetch_santiment(symbols)
            else:
                logger.error(f"Unknown social sentiment API provider: {self.config.api_provider}")
                return []

        except Exception as e:
            logger.exception(f"Unexpected error fetching social sentiment data: {e}")
            return [
                ExternalMetrics(
                    source_name=self.config.api_provider,
                    symbol=symbol,
                    metrics={},
                    is_stale=True,
                    error_message=str(e),
                )
                for symbol in symbols
            ]

    async def _fetch_lunarcrush(self, symbols: list[str]) -> list[ExternalMetrics]:
        """
        Fetch social sentiment from LunarCrush API.

        LunarCrush requires an API key for all endpoints.

        Args:
            symbols: List of symbols to fetch data for

        Returns:
            List of ExternalMetrics with LunarCrush data

        Requirements:
            - 1.3.2: Fetch sentiment polarity, mention count, buzz score per symbol
            - 1.3.3: Return typed dataclass per symbol
            - 1.3.4: Return None on API failure with error logging
        """
        if not self.config.api_key:
            error_msg = "LunarCrush API key not configured"
            logger.error(error_msg)
            return [
                ExternalMetrics(
                    source_name="lunarcrush",
                    symbol=symbol,
                    metrics={},
                    is_stale=True,
                    error_message=error_msg,
                )
                for symbol in symbols
            ]

        results = []
        client = await self._get_http_client()

        for symbol in symbols:
            metrics: dict[str, float | int | None] = {}
            error_message: str | None = None
            is_stale = False
            fetched_at = datetime.now(timezone.utc)

            try:
                # Normalize symbol for LunarCrush (e.g., "BTC_USDT" -> "BTC")
                asset = symbol.split("_")[0] if "_" in symbol else symbol

                # Fetch asset details from LunarCrush
                url = f"{self.config.base_url}/assets"
                params: dict[str, Any] = {
                    "key": self.config.api_key,
                    "symbol": asset.upper(),
                }

                response = await client.get(url, params=params)
                response.raise_for_status()

                data = response.json()
                if not data or "data" not in data or not data["data"]:
                    logger.warning(f"LunarCrush returned empty data for {symbol}")
                    is_stale = True
                    error_message = f"No data available for {symbol}"
                else:
                    # Extract the first asset (should be the only one)
                    asset_data = data["data"][0] if isinstance(data["data"], list) else data["data"]

                    # Extract sentiment polarity (normalize from 0-5 scale to -1 to 1)
                    # LunarCrush uses sentiment score 0-5, where 3 is neutral
                    sentiment_raw = asset_data.get("sentiment")
                    if sentiment_raw is not None:
                        # Convert 0-5 scale to -1 to 1 scale (3 = 0, 0 = -1, 5 = 1)
                        sentiment_polarity = (float(sentiment_raw) - 3.0) / 2.0
                        # Clamp to [-1, 1] range
                        sentiment_polarity = max(-1.0, min(1.0, sentiment_polarity))
                        metrics["sentiment_polarity"] = sentiment_polarity
                    else:
                        metrics["sentiment_polarity"] = None
                        is_stale = True

                    # Extract mention count (social volume)
                    social_volume = asset_data.get("social_volume")
                    if social_volume is not None:
                        metrics["mention_count"] = int(social_volume)
                    else:
                        metrics["mention_count"] = None
                        is_stale = True

                    # Extract buzz score (galaxy score normalized to 0-1)
                    # LunarCrush galaxy score is 0-100
                    galaxy_score = asset_data.get("galaxy_score")
                    if galaxy_score is not None:
                        buzz_score = float(galaxy_score) / 100.0
                        metrics["buzz_score"] = buzz_score
                    else:
                        metrics["buzz_score"] = None
                        is_stale = True

                # Add timestamp
                metrics["fetched_at"] = fetched_at.timestamp()

                # Set error message if we failed to fetch meaningful data
                if is_stale and len([k for k, v in metrics.items() if k != "fetched_at" and v is not None]) == 0:
                    if not error_message:
                        error_message = f"Failed to fetch any social sentiment data for {symbol}"
                    logger.error(error_message)

                logger.info(
                    f"Fetched LunarCrush data for {symbol}: "
                    f"{len([k for k, v in metrics.items() if v is not None])} metrics"
                )

            except httpx.HTTPStatusError as e:
                error_message = f"HTTP error fetching LunarCrush data for {symbol}: {e.response.status_code}"
                logger.error(error_message)
                is_stale = True
            except httpx.RequestError as e:
                error_message = f"Request error fetching LunarCrush data for {symbol}: {e}"
                logger.error(error_message)
                is_stale = True
            except (KeyError, ValueError, TypeError, IndexError) as e:
                error_message = f"Error parsing LunarCrush data for {symbol}: {e}"
                logger.exception(error_message)
                is_stale = True

            results.append(
                ExternalMetrics(
                    source_name="lunarcrush",
                    symbol=symbol,
                    metrics=metrics,
                    is_stale=is_stale,
                    error_message=error_message,
                )
            )

        return results

    async def _fetch_santiment(self, symbols: list[str]) -> list[ExternalMetrics]:
        """
        Fetch social sentiment from Santiment API.

        Santiment uses GraphQL and requires an API key for all endpoints.

        Args:
            symbols: List of symbols to fetch data for

        Returns:
            List of ExternalMetrics with Santiment data

        Requirements:
            - 1.3.2: Fetch sentiment polarity, mention count, buzz score per symbol
            - 1.3.3: Return typed dataclass per symbol
            - 1.3.4: Return None on API failure with error logging
        """
        if not self.config.api_key:
            error_msg = "Santiment API key not configured"
            logger.error(error_msg)
            return [
                ExternalMetrics(
                    source_name="santiment",
                    symbol=symbol,
                    metrics={},
                    is_stale=True,
                    error_message=error_msg,
                )
                for symbol in symbols
            ]

        results = []
        client = await self._get_http_client()

        for symbol in symbols:
            metrics: dict[str, float | int | None] = {}
            error_message: str | None = None
            is_stale = False
            fetched_at = datetime.now(timezone.utc)

            try:
                # Normalize symbol for Santiment (e.g., "BTC_USDT" -> "bitcoin")
                # Santiment uses slugs like "bitcoin", "ethereum"
                asset_slug = self._symbol_to_santiment_slug(symbol)

                # Build GraphQL query for sentiment metrics
                query = """
                query($slug: String!, $from: DateTime!, $to: DateTime!) {
                  getMetric(metric: "sentiment_balance_total") {
                    timeseriesData(
                      slug: $slug
                      from: $from
                      to: $to
                      interval: "1d"
                    ) {
                      datetime
                      value
                    }
                  }
                  socialVolume: getMetric(metric: "social_volume_total") {
                    timeseriesData(
                      slug: $slug
                      from: $from
                      to: $to
                      interval: "1d"
                    ) {
                      datetime
                      value
                    }
                  }
                  socialDominance: getMetric(metric: "social_dominance_total") {
                    timeseriesData(
                      slug: $slug
                      from: $from
                      to: $to
                      interval: "1d"
                    ) {
                      datetime
                      value
                    }
                  }
                }
                """

                # Get data for the last 24 hours
                to_time = datetime.now(timezone.utc).isoformat()
                from_time = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

                variables = {
                    "slug": asset_slug,
                    "from": from_time,
                    "to": to_time,
                }

                headers = {
                    "Authorization": f"Apikey {self.config.api_key}",
                    "Content-Type": "application/json",
                }

                response = await client.post(
                    self.config.base_url,
                    json={"query": query, "variables": variables},
                    headers=headers,
                )
                response.raise_for_status()

                data = response.json()
                if not data or "data" not in data:
                    logger.warning(f"Santiment returned empty data for {symbol}")
                    is_stale = True
                    error_message = f"No data available for {symbol}"
                else:
                    # Extract sentiment balance (normalized to -1 to 1)
                    sentiment_data = data["data"].get("getMetric", {}).get("timeseriesData", [])
                    if sentiment_data:
                        latest_sentiment = sentiment_data[-1].get("value")
                        if latest_sentiment is not None:
                            # Santiment sentiment_balance is already in a reasonable range
                            # Normalize to -1 to 1 (assuming typical range is -10 to 10)
                            sentiment_polarity = max(-1.0, min(1.0, float(latest_sentiment) / 10.0))
                            metrics["sentiment_polarity"] = sentiment_polarity
                        else:
                            metrics["sentiment_polarity"] = None
                            is_stale = True
                    else:
                        metrics["sentiment_polarity"] = None
                        is_stale = True

                    # Extract social volume (mention count)
                    volume_data = data["data"].get("socialVolume", {}).get("timeseriesData", [])
                    if volume_data:
                        latest_volume = volume_data[-1].get("value")
                        if latest_volume is not None:
                            metrics["mention_count"] = int(latest_volume)
                        else:
                            metrics["mention_count"] = None
                            is_stale = True
                    else:
                        metrics["mention_count"] = None
                        is_stale = True

                    # Extract social dominance as buzz score (0-1 scale)
                    dominance_data = data["data"].get("socialDominance", {}).get("timeseriesData", [])
                    if dominance_data:
                        latest_dominance = dominance_data[-1].get("value")
                        if latest_dominance is not None:
                            # Social dominance is typically 0-100
                            buzz_score = float(latest_dominance) / 100.0
                            metrics["buzz_score"] = buzz_score
                        else:
                            metrics["buzz_score"] = None
                            is_stale = True
                    else:
                        metrics["buzz_score"] = None
                        is_stale = True

                # Add timestamp
                metrics["fetched_at"] = fetched_at.timestamp()

                # Set error message if we failed to fetch meaningful data
                if is_stale and len([k for k, v in metrics.items() if k != "fetched_at" and v is not None]) == 0:
                    if not error_message:
                        error_message = f"Failed to fetch any social sentiment data for {symbol}"
                    logger.error(error_message)

                logger.info(
                    f"Fetched Santiment data for {symbol}: "
                    f"{len([k for k, v in metrics.items() if v is not None])} metrics"
                )

            except httpx.HTTPStatusError as e:
                error_message = f"HTTP error fetching Santiment data for {symbol}: {e.response.status_code}"
                logger.error(error_message)
                is_stale = True
            except httpx.RequestError as e:
                error_message = f"Request error fetching Santiment data for {symbol}: {e}"
                logger.error(error_message)
                is_stale = True
            except (KeyError, ValueError, TypeError, IndexError) as e:
                error_message = f"Error parsing Santiment data for {symbol}: {e}"
                logger.exception(error_message)
                is_stale = True

            results.append(
                ExternalMetrics(
                    source_name="santiment",
                    symbol=symbol,
                    metrics=metrics,
                    is_stale=is_stale,
                    error_message=error_message,
                )
            )

        return results

    def _symbol_to_santiment_slug(self, symbol: str) -> str:
        """
        Convert a trading symbol to Santiment slug format.

        Args:
            symbol: Trading pair symbol (e.g., "BTC_USDT", "ETH")

        Returns:
            Santiment slug (e.g., "bitcoin", "ethereum")
        """
        # Extract base asset
        asset = symbol.split("_")[0] if "_" in symbol else symbol
        asset = asset.upper()

        # Map common symbols to Santiment slugs
        slug_map = {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "USDT": "tether",
            "BNB": "binance-coin",
            "XRP": "ripple",
            "ADA": "cardano",
            "SOL": "solana",
            "DOGE": "dogecoin",
            "DOT": "polkadot",
            "MATIC": "polygon",
            "AVAX": "avalanche",
            "LINK": "chainlink",
            "UNI": "uniswap",
            "ATOM": "cosmos",
            "LTC": "litecoin",
        }

        return slug_map.get(asset, asset.lower())

    async def close(self) -> None:
        """
        Close the HTTP client and release resources.

        Only closes the client if it was created by this instance
        (not provided externally).

        Requirements:
            - 1.3.1: Proper resource management with httpx.AsyncClient
        """
        if self._http_client is not None and self._owned_client:
            await self._http_client.aclose()
            self._http_client = None
