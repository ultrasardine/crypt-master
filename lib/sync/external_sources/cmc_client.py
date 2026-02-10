"""
CoinMarketCap/CoinGecko Market Data Client.

This module provides an async client for fetching global market data from
CoinGecko (free tier) or CoinMarketCap APIs. The client fetches BTC dominance,
global market cap, total 24h volume, and top gainers/losers.

Requirements:
- 1.1.1: Async client class that fetches BTC dominance, global market cap,
         total 24h volume, and top 10 gainers/losers
- 1.1.2: Use httpx.AsyncClient with configurable timeout and retries
- 1.1.3: Return None on API failure with error logging
- 1.1.4: Support environment variable configuration for API keys and base URLs
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

from lib.sync.external_sources import ExternalMetrics

logger = logging.getLogger(__name__)


# Default API endpoints
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
COINMARKETCAP_BASE_URL = "https://pro-api.coinmarketcap.com/v1"


@dataclass(frozen=True)
class MarketDataClientConfig:
    """
    Configuration for the market data client.

    Attributes:
        api_provider: Which API to use ("coingecko" or "coinmarketcap")
        api_key: API key for authenticated endpoints (optional for CoinGecko free tier)
        base_url: Base URL for the API (defaults to provider's public endpoint)
        timeout_seconds: Request timeout in seconds
        max_retries: Maximum number of retry attempts on failure
        top_movers_limit: Number of top gainers/losers to fetch

    Requirements:
        - 1.1.2: Configurable timeout and retries
        - 1.1.4: Environment variable configuration
    """

    api_provider: str = "coingecko"  # "coingecko" or "coinmarketcap"
    api_key: str | None = None
    base_url: str | None = None
    timeout_seconds: float = 30.0
    max_retries: int = 3
    top_movers_limit: int = 10

    @classmethod
    def from_env(cls) -> MarketDataClientConfig:
        """
        Create configuration from environment variables.

        Environment variables:
            MARKET_DATA_PROVIDER: API provider ("coingecko" or "coinmarketcap")
            MARKET_DATA_API_KEY: API key for authenticated endpoints
            MARKET_DATA_BASE_URL: Custom base URL (optional)
            MARKET_DATA_TIMEOUT: Request timeout in seconds
            MARKET_DATA_MAX_RETRIES: Maximum retry attempts

        Returns:
            MarketDataClientConfig instance

        Requirements:
            - 1.1.4: Support environment variable configuration
        """
        provider = os.getenv("MARKET_DATA_PROVIDER", "coingecko").lower()
        api_key = os.getenv("MARKET_DATA_API_KEY")
        base_url = os.getenv("MARKET_DATA_BASE_URL")
        timeout = float(os.getenv("MARKET_DATA_TIMEOUT", "30.0"))
        max_retries = int(os.getenv("MARKET_DATA_MAX_RETRIES", "3"))

        # Set default base URL based on provider if not specified
        if base_url is None:
            base_url = (
                COINGECKO_BASE_URL if provider == "coingecko" else COINMARKETCAP_BASE_URL
            )

        return cls(
            api_provider=provider,
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout,
            max_retries=max_retries,
        )


class MarketDataClient:
    """
    Async client for fetching global market data from CoinGecko or CoinMarketCap.

    This client provides methods to fetch:
    - BTC dominance percentage
    - Global cryptocurrency market cap
    - Total 24h trading volume
    - Top 10 gainers and losers

    The client uses httpx.AsyncClient with configurable timeout and retries,
    and handles API failures gracefully by returning None and logging errors.

    Requirements:
        - 1.1.1: Fetch BTC dominance, global market cap, total 24h volume,
                 top 10 gainers/losers
        - 1.1.2: Use httpx.AsyncClient with configurable timeout and retries
        - 1.1.3: Return None on API failure with error logging
        - 1.1.4: Support environment variable configuration

    Example:
        >>> config = MarketDataClientConfig.from_env()
        >>> client = MarketDataClient(config)
        >>> metrics = await client.fetch([])
        >>> await client.close()
    """

    def __init__(
        self,
        config: MarketDataClientConfig | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """
        Initialize the market data client.

        Args:
            config: Client configuration (defaults to environment-based config)
            http_client: Optional httpx AsyncClient for making HTTP requests
                        (useful for testing with mocked client)

        Requirements:
            - 1.1.2: Use httpx.AsyncClient with configurable timeout
            - 1.1.4: Support environment variable configuration
        """
        self.config = config or MarketDataClientConfig.from_env()
        self._http_client = http_client
        self._owned_client = http_client is None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """
        Get or create HTTP client with retry configuration.

        Returns:
            Configured httpx.AsyncClient instance

        Requirements:
            - 1.1.2: Use httpx.AsyncClient with configurable timeout and retries
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
        Fetch global market data from the configured API provider.

        This method fetches all available market data and returns it as a single
        ExternalMetrics object with symbol=None (indicating global metrics).

        Args:
            symbols: List of trading pair symbols (unused for global metrics,
                    included for protocol compatibility)

        Returns:
            List containing a single ExternalMetrics with global market data,
            or empty list if fetch fails

        Requirements:
            - 1.1.1: Fetch BTC dominance, global market cap, total 24h volume,
                     top 10 gainers/losers
            - 1.1.3: Return None on API failure with error logging
        """
        try:
            if self.config.api_provider == "coingecko":
                return await self._fetch_coingecko()
            elif self.config.api_provider == "coinmarketcap":
                return await self._fetch_coinmarketcap()
            else:
                logger.error(f"Unknown API provider: {self.config.api_provider}")
                return []

        except Exception as e:
            logger.exception(f"Unexpected error fetching market data: {e}")
            return [
                ExternalMetrics(
                    source_name=self.config.api_provider,
                    symbol=None,
                    metrics={},
                    is_stale=True,
                    error_message=str(e),
                )
            ]

    async def _fetch_coingecko(self) -> list[ExternalMetrics]:
        """
        Fetch market data from CoinGecko API.

        CoinGecko provides free tier access to global market data without API key.

        Returns:
            List containing ExternalMetrics with CoinGecko data

        Requirements:
            - 1.1.1: Fetch BTC dominance, global market cap, total 24h volume,
                     top 10 gainers/losers
            - 1.1.3: Return None on API failure with error logging
        """
        metrics: dict[str, float | int | None] = {}
        error_message: str | None = None
        is_stale = False

        try:
            client = await self._get_http_client()

            # Fetch global market data
            global_data = await self._fetch_coingecko_global(client)
            if global_data:
                metrics.update(global_data)
            else:
                is_stale = True

            # Fetch top gainers/losers
            movers_data = await self._fetch_coingecko_movers(client)
            if movers_data:
                metrics.update(movers_data)
            else:
                is_stale = True

            if is_stale and not metrics:
                error_message = "Failed to fetch any data from CoinGecko"
                logger.error(error_message)

        except Exception as e:
            error_message = f"Error fetching CoinGecko data: {e}"
            logger.exception(error_message)
            is_stale = True

        return [
            ExternalMetrics(
                source_name="coingecko",
                symbol=None,
                metrics=metrics,
                is_stale=is_stale,
                error_message=error_message,
            )
        ]

    async def _fetch_coingecko_global(
        self, client: httpx.AsyncClient
    ) -> dict[str, float | int | None]:
        """
        Fetch global market data from CoinGecko.

        Args:
            client: HTTP client to use for requests

        Returns:
            Dict with btc_dominance, global_market_cap, total_volume_24h

        Requirements:
            - 1.1.1: Fetch BTC dominance, global market cap, total 24h volume
        """
        try:
            url = f"{self.config.base_url}/global"
            response = await client.get(url)
            response.raise_for_status()

            data = response.json()
            if not data or "data" not in data:
                logger.warning("CoinGecko global API returned empty data")
                return {}

            global_data = data["data"]

            # Extract metrics
            btc_dominance = global_data.get("market_cap_percentage", {}).get("btc")
            global_market_cap = global_data.get("total_market_cap", {}).get("usd")
            total_volume_24h = global_data.get("total_volume", {}).get("usd")

            logger.info(
                f"Fetched CoinGecko global data: BTC dominance={btc_dominance}%, "
                f"market cap=${global_market_cap}, volume=${total_volume_24h}"
            )

            return {
                "btc_dominance": float(btc_dominance) if btc_dominance is not None else None,
                "global_market_cap": (
                    float(global_market_cap) if global_market_cap is not None else None
                ),
                "total_volume_24h": (
                    float(total_volume_24h) if total_volume_24h is not None else None
                ),
            }

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching CoinGecko global data: {e.response.status_code}")
            return {}
        except httpx.RequestError as e:
            logger.error(f"Request error fetching CoinGecko global data: {e}")
            return {}
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error parsing CoinGecko global data: {e}")
            return {}

    async def _fetch_coingecko_movers(
        self, client: httpx.AsyncClient
    ) -> dict[str, float | int | None]:
        """
        Fetch top gainers and losers from CoinGecko.

        Args:
            client: HTTP client to use for requests

        Returns:
            Dict with top_gainers and top_losers lists

        Requirements:
            - 1.1.1: Fetch top 10 gainers/losers
        """
        try:
            # Fetch market data sorted by 24h price change
            url = f"{self.config.base_url}/coins/markets"
            params: dict[str, Any] = {
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 100,  # Fetch more to find top movers
                "page": 1,
                "sparkline": False,
                "price_change_percentage": "24h",
            }

            response = await client.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            if not data:
                logger.warning("CoinGecko markets API returned empty data")
                return {}

            # Sort by 24h price change to find gainers and losers
            coins_with_change = [
                coin
                for coin in data
                if coin.get("price_change_percentage_24h") is not None
            ]

            # Top gainers (highest positive change)
            gainers = sorted(
                coins_with_change,
                key=lambda x: x.get("price_change_percentage_24h", 0),
                reverse=True,
            )[: self.config.top_movers_limit]

            # Top losers (highest negative change)
            losers = sorted(
                coins_with_change,
                key=lambda x: x.get("price_change_percentage_24h", 0),
            )[: self.config.top_movers_limit]

            # Format as lists of dicts with symbol and change percentage
            top_gainers = [
                {
                    "symbol": coin.get("symbol", "").upper(),
                    "name": coin.get("name", ""),
                    "change_24h": coin.get("price_change_percentage_24h", 0),
                }
                for coin in gainers
            ]

            top_losers = [
                {
                    "symbol": coin.get("symbol", "").upper(),
                    "name": coin.get("name", ""),
                    "change_24h": coin.get("price_change_percentage_24h", 0),
                }
                for coin in losers
            ]

            logger.info(
                f"Fetched CoinGecko movers: {len(top_gainers)} gainers, {len(top_losers)} losers"
            )

            return {
                "top_gainers": top_gainers,  # type: ignore[dict-item]
                "top_losers": top_losers,  # type: ignore[dict-item]
            }

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching CoinGecko movers: {e.response.status_code}")
            return {}
        except httpx.RequestError as e:
            logger.error(f"Request error fetching CoinGecko movers: {e}")
            return {}
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error parsing CoinGecko movers: {e}")
            return {}

    async def _fetch_coinmarketcap(self) -> list[ExternalMetrics]:
        """
        Fetch market data from CoinMarketCap API.

        CoinMarketCap requires an API key for all endpoints.

        Returns:
            List containing ExternalMetrics with CoinMarketCap data

        Requirements:
            - 1.1.1: Fetch BTC dominance, global market cap, total 24h volume,
                     top 10 gainers/losers
            - 1.1.3: Return None on API failure with error logging
            - 1.1.4: Support API key configuration
        """
        if not self.config.api_key:
            error_msg = "CoinMarketCap API key not configured"
            logger.error(error_msg)
            return [
                ExternalMetrics(
                    source_name="coinmarketcap",
                    symbol=None,
                    metrics={},
                    is_stale=True,
                    error_message=error_msg,
                )
            ]

        metrics: dict[str, float | int | None] = {}
        error_message: str | None = None
        is_stale = False

        try:
            client = await self._get_http_client()

            # Fetch global metrics
            global_data = await self._fetch_coinmarketcap_global(client)
            if global_data:
                metrics.update(global_data)
            else:
                is_stale = True

            # Fetch top gainers/losers
            movers_data = await self._fetch_coinmarketcap_movers(client)
            if movers_data:
                metrics.update(movers_data)
            else:
                is_stale = True

            if is_stale and not metrics:
                error_message = "Failed to fetch any data from CoinMarketCap"
                logger.error(error_message)

        except Exception as e:
            error_message = f"Error fetching CoinMarketCap data: {e}"
            logger.exception(error_message)
            is_stale = True

        return [
            ExternalMetrics(
                source_name="coinmarketcap",
                symbol=None,
                metrics=metrics,
                is_stale=is_stale,
                error_message=error_message,
            )
        ]

    async def _fetch_coinmarketcap_global(
        self, client: httpx.AsyncClient
    ) -> dict[str, float | int | None]:
        """
        Fetch global metrics from CoinMarketCap.

        Args:
            client: HTTP client to use for requests

        Returns:
            Dict with btc_dominance, global_market_cap, total_volume_24h

        Requirements:
            - 1.1.1: Fetch BTC dominance, global market cap, total 24h volume
        """
        try:
            url = f"{self.config.base_url}/global-metrics/quotes/latest"
            headers = {"X-CMC_PRO_API_KEY": self.config.api_key or ""}

            response = await client.get(url, headers=headers)
            response.raise_for_status()

            data = response.json()
            if not data or "data" not in data:
                logger.warning("CoinMarketCap global API returned empty data")
                return {}

            global_data = data["data"]

            # Extract metrics
            btc_dominance = global_data.get("btc_dominance")
            global_market_cap = global_data.get("quote", {}).get("USD", {}).get("total_market_cap")
            total_volume_24h = global_data.get("quote", {}).get("USD", {}).get("total_volume_24h")

            logger.info(
                f"Fetched CoinMarketCap global data: BTC dominance={btc_dominance}%, "
                f"market cap=${global_market_cap}, volume=${total_volume_24h}"
            )

            return {
                "btc_dominance": float(btc_dominance) if btc_dominance is not None else None,
                "global_market_cap": (
                    float(global_market_cap) if global_market_cap is not None else None
                ),
                "total_volume_24h": (
                    float(total_volume_24h) if total_volume_24h is not None else None
                ),
            }

        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error fetching CoinMarketCap global data: {e.response.status_code}"
            )
            return {}
        except httpx.RequestError as e:
            logger.error(f"Request error fetching CoinMarketCap global data: {e}")
            return {}
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error parsing CoinMarketCap global data: {e}")
            return {}

    async def _fetch_coinmarketcap_movers(
        self, client: httpx.AsyncClient
    ) -> dict[str, float | int | None]:
        """
        Fetch top gainers and losers from CoinMarketCap.

        Args:
            client: HTTP client to use for requests

        Returns:
            Dict with top_gainers and top_losers lists

        Requirements:
            - 1.1.1: Fetch top 10 gainers/losers
        """
        try:
            # Fetch gainers
            gainers_url = f"{self.config.base_url}/cryptocurrency/trending/gainers-losers"
            headers = {"X-CMC_PRO_API_KEY": self.config.api_key or ""}

            response = await client.get(gainers_url, headers=headers)
            response.raise_for_status()

            data = response.json()
            if not data or "data" not in data:
                logger.warning("CoinMarketCap gainers/losers API returned empty data")
                return {}

            # Extract gainers and losers
            gainers = data["data"].get("gainers", [])
            losers = data["data"].get("losers", [])

            # Format as lists of dicts
            top_gainers = [
                {
                    "symbol": coin.get("symbol", ""),
                    "name": coin.get("name", ""),
                    "change_24h": coin.get("quote", {}).get("USD", {}).get("percent_change_24h", 0),
                }
                for coin in gainers[: self.config.top_movers_limit]
            ]

            top_losers = [
                {
                    "symbol": coin.get("symbol", ""),
                    "name": coin.get("name", ""),
                    "change_24h": coin.get("quote", {}).get("USD", {}).get("percent_change_24h", 0),
                }
                for coin in losers[: self.config.top_movers_limit]
            ]

            logger.info(
                f"Fetched CoinMarketCap movers: {len(top_gainers)} gainers, {len(top_losers)} losers"
            )

            return {
                "top_gainers": top_gainers,  # type: ignore[dict-item]
                "top_losers": top_losers,  # type: ignore[dict-item]
            }

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching CoinMarketCap movers: {e.response.status_code}")
            return {}
        except httpx.RequestError as e:
            logger.error(f"Request error fetching CoinMarketCap movers: {e}")
            return {}
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error parsing CoinMarketCap movers: {e}")
            return {}

    async def close(self) -> None:
        """
        Close the HTTP client and release resources.

        Only closes the client if it was created by this instance
        (not provided externally).

        Requirements:
            - 1.1.2: Proper resource management with httpx.AsyncClient
        """
        if self._http_client is not None and self._owned_client:
            await self._http_client.aclose()
            self._http_client = None
