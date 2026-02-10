"""
Blockchain.com Free API Client.

This module provides an async client for fetching Bitcoin network statistics
from Blockchain.com's free public API. No API key required.

Data available:
- Hash rate (TH/s)
- Transaction count (24h)
- Total BTC sent (24h)
- Miners revenue (USD)
- Network difficulty
- Market price (USD)
- Trade volume (USD)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

from lib.sync.external_sources import ExternalMetrics

logger = logging.getLogger(__name__)

# Free API endpoints (no key required)
BLOCKCHAIN_STATS_API = "https://api.blockchain.info/stats"
BLOCKCHAIN_CHARTS_API = "https://api.blockchain.info/charts"

# Conversion constant: satoshi to BTC
SATOSHI_PER_BTC = 1e8


@dataclass(frozen=True)
class BlockchainClientConfig:
    """
    Configuration for the Blockchain.com client.

    Attributes:
        timeout_seconds: Request timeout in seconds
        max_retries: Maximum number of retry attempts on failure
    """

    timeout_seconds: float = 30.0
    max_retries: int = 3

    @classmethod
    def from_env(cls) -> BlockchainClientConfig:
        """
        Create configuration from environment variables.

        Environment variables:
            BLOCKCHAIN_TIMEOUT: Request timeout in seconds (default: 30.0)
            BLOCKCHAIN_MAX_RETRIES: Maximum retry attempts (default: 3)

        Returns:
            BlockchainClientConfig instance
        """
        timeout = float(os.getenv("BLOCKCHAIN_TIMEOUT", "30.0"))
        max_retries = int(os.getenv("BLOCKCHAIN_MAX_RETRIES", "3"))
        return cls(timeout_seconds=timeout, max_retries=max_retries)


class BlockchainClient:
    """
    Async client for fetching Bitcoin network data from Blockchain.com.

    This client uses Blockchain.com's free public API (no API key required)
    to fetch on-chain metrics for Bitcoin.

    Available metrics:
    - hash_rate: Network hash rate in TH/s
    - n_tx_24h: Number of transactions in last 24h
    - n_blocks_mined_24h: Blocks mined in last 24h
    - total_btc_sent_24h: Total BTC sent in last 24h
    - miners_revenue_usd: Miners revenue in USD
    - difficulty: Current network difficulty
    - market_price_usd: Current BTC price in USD
    - trade_volume_usd: 24h trade volume in USD

    Example:
        >>> config = BlockchainClientConfig.from_env()
        >>> client = BlockchainClient(config)
        >>> metrics = await client.fetch([])
        >>> await client.close()

        # Or use as async context manager:
        >>> async with BlockchainClient() as client:
        ...     metrics = await client.fetch([])
    """

    def __init__(
        self,
        config: BlockchainClientConfig | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """
        Initialize the Blockchain.com client.

        Args:
            config: Client configuration (defaults to environment-based config)
            http_client: Optional httpx AsyncClient for making HTTP requests
                        (useful for testing with mocked client)
        """
        self.config = config or BlockchainClientConfig()
        self._http_client = http_client
        self._owned_client = http_client is None

    async def __aenter__(self) -> BlockchainClient:
        """Enter async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context manager and cleanup resources."""
        await self.close()

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            transport = httpx.AsyncHTTPTransport(retries=self.config.max_retries)
            self._http_client = httpx.AsyncClient(
                timeout=self.config.timeout_seconds,
                transport=transport,
            )
        return self._http_client

    async def fetch(self, symbols: list[str]) -> list[ExternalMetrics]:
        """
        Fetch Bitcoin network statistics from Blockchain.com.

        Args:
            symbols: Ignored (this API only provides BTC data)

        Returns:
            List containing ExternalMetrics with Bitcoin network data
        """
        metrics: dict[str, float | int | None] = {}
        error_message: str | None = None
        is_stale = False

        try:
            client = await self._get_http_client()

            # Fetch stats from the free API
            response = await client.get(BLOCKCHAIN_STATS_API)
            response.raise_for_status()

            data = response.json()
            if not data:
                logger.warning("Blockchain.com stats API returned empty data")
                is_stale = True
                error_message = "Empty response from Blockchain.com"
            else:
                # Extract available metrics
                metrics["hash_rate"] = data.get("hash_rate")
                metrics["n_tx_24h"] = data.get("n_tx")
                metrics["n_blocks_mined_24h"] = data.get("n_blocks_mined")
                metrics["total_btc_sent_24h"] = data.get("total_btc_sent")
                metrics["miners_revenue_usd"] = data.get("miners_revenue_usd")
                metrics["difficulty"] = data.get("difficulty")
                metrics["market_price_usd"] = data.get("market_price_usd")
                metrics["trade_volume_usd"] = data.get("trade_volume_usd")
                metrics["estimated_transaction_volume_usd"] = data.get(
                    "estimated_transaction_volume_usd"
                )

                # Convert total_btc_sent from satoshi to BTC
                if metrics["total_btc_sent_24h"]:
                    metrics["total_btc_sent_24h"] = (
                        float(metrics["total_btc_sent_24h"]) / SATOSHI_PER_BTC
                    )

                logger.info(
                    f"Fetched Blockchain.com stats: "
                    f"hash_rate={metrics.get('hash_rate')}, "
                    f"n_tx={metrics.get('n_tx_24h')}, "
                    f"price=${metrics.get('market_price_usd')}"
                )

        except httpx.HTTPStatusError as e:
            error_message = f"HTTP error fetching Blockchain.com data: {e.response.status_code}"
            logger.error(error_message)
            is_stale = True
        except httpx.RequestError as e:
            error_message = f"Request error fetching Blockchain.com data: {e}"
            logger.error(error_message)
            is_stale = True
        except Exception as e:
            error_message = f"Error fetching Blockchain.com data: {e}"
            logger.exception(error_message)
            is_stale = True

        return [
            ExternalMetrics(
                source_name="blockchain.com",
                symbol="BTC",
                metrics=metrics,
                is_stale=is_stale,
                error_message=error_message,
            )
        ]

    async def fetch_chart_data(
        self, chart_name: str, timespan: str = "30days"
    ) -> list[dict[str, Any]]:
        """
        Fetch historical chart data from Blockchain.com.

        Args:
            chart_name: Name of the chart (e.g., 'n-unique-addresses', 'hash-rate')
            timespan: Time period (e.g., '30days', '1year')

        Returns:
            List of data points with 'x' (timestamp) and 'y' (value) keys,
            or empty list on failure
        """
        try:
            client = await self._get_http_client()
            url = f"{BLOCKCHAIN_CHARTS_API}/{chart_name}"
            params = {"timespan": timespan, "format": "json"}

            response = await client.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            if data and "values" in data:
                return data["values"]

            return []

        except Exception as e:
            logger.error(f"Error fetching chart {chart_name}: {e}")
            return []

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._http_client is not None and self._owned_client:
            await self._http_client.aclose()
            self._http_client = None
