"""
External Data Sources Module.

This module provides the infrastructure for fetching market intelligence data
from external sources including market data aggregators, on-chain metrics providers,
and social sentiment APIs.

The module defines:
- ExternalMetrics: Normalized data structure for external source responses
- ExternalSourceClient: Protocol defining the interface for external source clients

Requirements:
- 1.1.1: Market data aggregator client interface
- 1.2.1: On-chain metrics client interface
- 1.3.1: Social sentiment client interface
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ExternalMetrics:
    """
    Normalized metrics from an external data source.

    This dataclass provides a standardized format for data returned by
    external source clients, ensuring consistent handling across different
    data providers.

    Attributes:
        source_name: Identifier for the data source (e.g., "coingecko", "glassnode")
        symbol: Trading pair symbol (e.g., "BTC_USDT"), None for global metrics
        metrics: Dictionary mapping metric names to their values
                 Values should be float, int, or None for missing data
        is_stale: Whether the data is stale due to API failure or timeout
        error_message: Error description if fetch failed, None otherwise

    Requirements:
        - 1.1.1: Market data aggregator client returns normalized metrics
        - 1.2.1: On-chain metrics client returns normalized metrics
        - 1.3.1: Social sentiment client returns normalized metrics

    Example:
        >>> metrics = ExternalMetrics(
        ...     source_name="coingecko",
        ...     symbol=None,
        ...     metrics={
        ...         "btc_dominance": 45.2,
        ...         "global_market_cap": 1_500_000_000_000.0,
        ...         "total_volume_24h": 85_000_000_000.0,
        ...     },
        ...     is_stale=False,
        ...     error_message=None,
        ... )
    """

    source_name: str
    symbol: str | None
    metrics: dict[str, float | int | None]
    is_stale: bool
    error_message: str | None


class ExternalSourceClient(Protocol):
    """
    Protocol defining the interface for external data source clients.

    All external source clients must implement this protocol to ensure
    consistent behavior and error handling across different data providers.

    The protocol requires:
    - Async fetch method that returns normalized metrics
    - Async close method for resource cleanup

    Requirements:
        - 1.1.2: Clients use httpx.AsyncClient with configurable timeout and retries
        - 1.1.3: On API failure, clients return None and log errors
        - 1.2.2: Clients fetch typed data with float | None fields
        - 1.3.2: Clients fetch per-symbol data as typed dataclass

    Example Implementation:
        >>> class MyClient:
        ...     async def fetch(self, symbols: list[str]) -> list[ExternalMetrics]:
        ...         # Fetch data from external API
        ...         return [ExternalMetrics(...)]
        ...
        ...     async def close(self) -> None:
        ...         # Clean up resources
        ...         pass
    """

    async def fetch(self, symbols: list[str]) -> list[ExternalMetrics]:
        """
        Fetch and return normalized metrics for the given symbols.

        This method should:
        1. Make async HTTP requests to the external API
        2. Parse and normalize the response data
        3. Handle errors gracefully by returning ExternalMetrics with is_stale=True
        4. Log errors for debugging

        Args:
            symbols: List of trading pair symbols to fetch data for
                    (e.g., ["BTC_USDT", "ETH_USDT"])
                    May be empty for global metrics

        Returns:
            List of ExternalMetrics, one per symbol or one for global data
            Returns empty list if all fetches fail

        Requirements:
            - 1.1.3: Return None on API failure with error logging
            - 1.2.4: Return None on API failure with error logging
            - 1.3.4: Return None on API failure with error logging
        """
        ...

    async def close(self) -> None:
        """
        Release resources and close connections.

        This method should:
        1. Close any open HTTP clients
        2. Clean up any other resources (file handles, connections, etc.)
        3. Be safe to call multiple times

        Requirements:
            - 1.1.2: Use httpx.AsyncClient with proper resource management
        """
        ...


__all__ = [
    "ExternalMetrics",
    "ExternalSourceClient",
    "BlockchainClient",
]

from lib.sync.external_sources.blockchain_client import BlockchainClient
