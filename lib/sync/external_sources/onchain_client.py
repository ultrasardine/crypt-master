"""
On-Chain Metrics Client.

This module provides an async client for fetching on-chain metrics from
third-party APIs such as Glassnode or IntoTheBlock. The client fetches
active addresses, exchange inflows/outflows, whale transactions, and DeFi TVL.

Requirements:
- 1.2.1: Async client class for on-chain metrics
- 1.2.2: Fetch active address count, net exchange flow, whale transaction count (>$100k),
         total DeFi TVL
- 1.2.3: Return typed dataclass with float | None fields and fetched_at timestamp
- 1.2.4: Return None on API failure with error logging
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
GLASSNODE_BASE_URL = "https://api.glassnode.com/v1"
INTOTHEBLOCK_BASE_URL = "https://api.intotheblock.com/v1"


@dataclass(frozen=True)
class OnChainClientConfig:
    """
    Configuration for the on-chain metrics client.

    Attributes:
        api_provider: Which API to use ("glassnode" or "intotheblock")
        api_key: API key for authenticated endpoints
        base_url: Base URL for the API (defaults to provider's public endpoint)
        timeout_seconds: Request timeout in seconds
        max_retries: Maximum number of retry attempts on failure

    Requirements:
        - 1.2.1: Configurable timeout and retries
        - 1.2.4: Environment variable configuration
    """

    api_provider: str = "glassnode"  # "glassnode" or "intotheblock"
    api_key: str | None = None
    base_url: str | None = None
    timeout_seconds: float = 30.0
    max_retries: int = 3

    @classmethod
    def from_env(cls) -> OnChainClientConfig:
        """
        Create configuration from environment variables.

        Environment variables:
            ONCHAIN_PROVIDER: API provider ("glassnode" or "intotheblock")
            ONCHAIN_API_KEY: API key for authenticated endpoints
            ONCHAIN_BASE_URL: Custom base URL (optional)
            ONCHAIN_TIMEOUT: Request timeout in seconds
            ONCHAIN_MAX_RETRIES: Maximum retry attempts

        Returns:
            OnChainClientConfig instance

        Requirements:
            - 1.2.4: Support environment variable configuration
        """
        provider = os.getenv("ONCHAIN_PROVIDER", "glassnode").lower()
        api_key = os.getenv("ONCHAIN_API_KEY")
        base_url = os.getenv("ONCHAIN_BASE_URL")
        timeout = float(os.getenv("ONCHAIN_TIMEOUT", "30.0"))
        max_retries = int(os.getenv("ONCHAIN_MAX_RETRIES", "3"))

        # Set default base URL based on provider if not specified
        if base_url is None:
            base_url = (
                GLASSNODE_BASE_URL if provider == "glassnode" else INTOTHEBLOCK_BASE_URL
            )

        return cls(
            api_provider=provider,
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout,
            max_retries=max_retries,
        )


class OnChainClient:
    """
    Async client for fetching on-chain metrics from Glassnode or IntoTheBlock.

    This client provides methods to fetch:
    - Active address count
    - Net exchange flow (inflow minus outflow)
    - Whale transaction count (transactions > $100k)
    - Total DeFi TVL (Total Value Locked)

    The client uses httpx.AsyncClient with configurable timeout and retries,
    and handles API failures gracefully by returning None and logging errors.

    Requirements:
        - 1.2.1: Async client class for on-chain metrics
        - 1.2.2: Fetch active addresses, exchange flow, whale transactions, DeFi TVL
        - 1.2.3: Return typed dataclass with float | None fields and fetched_at timestamp
        - 1.2.4: Return None on API failure with error logging

    Example:
        >>> config = OnChainClientConfig.from_env()
        >>> client = OnChainClient(config)
        >>> metrics = await client.fetch(["BTC"])
        >>> await client.close()
    """

    def __init__(
        self,
        config: OnChainClientConfig | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """
        Initialize the on-chain metrics client.

        Args:
            config: Client configuration (defaults to environment-based config)
            http_client: Optional httpx AsyncClient for making HTTP requests
                        (useful for testing with mocked client)

        Requirements:
            - 1.2.1: Use httpx.AsyncClient with configurable timeout
            - 1.2.4: Support environment variable configuration
        """
        self.config = config or OnChainClientConfig.from_env()
        self._http_client = http_client
        self._owned_client = http_client is None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """
        Get or create HTTP client with retry configuration.

        Returns:
            Configured httpx.AsyncClient instance

        Requirements:
            - 1.2.1: Use httpx.AsyncClient with configurable timeout and retries
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
        Fetch on-chain metrics from the configured API provider.

        This method fetches on-chain metrics for the specified symbols.
        For Bitcoin-focused metrics, the symbol list typically contains ["BTC"].

        Args:
            symbols: List of trading pair symbols (e.g., ["BTC", "ETH"])

        Returns:
            List of ExternalMetrics, one per symbol with on-chain data,
            or empty list if fetch fails

        Requirements:
            - 1.2.2: Fetch active addresses, exchange flow, whale transactions, DeFi TVL
            - 1.2.3: Return typed dataclass with float | None fields and fetched_at timestamp
            - 1.2.4: Return None on API failure with error logging
        """
        try:
            if self.config.api_provider == "glassnode":
                return await self._fetch_glassnode(symbols)
            elif self.config.api_provider == "intotheblock":
                return await self._fetch_intotheblock(symbols)
            else:
                logger.error(f"Unknown on-chain API provider: {self.config.api_provider}")
                return []

        except Exception as e:
            logger.exception(f"Unexpected error fetching on-chain data: {e}")
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

    async def _fetch_glassnode(self, symbols: list[str]) -> list[ExternalMetrics]:
        """
        Fetch on-chain metrics from Glassnode API.

        Glassnode requires an API key for all endpoints.

        Args:
            symbols: List of symbols to fetch data for

        Returns:
            List of ExternalMetrics with Glassnode data

        Requirements:
            - 1.2.2: Fetch active addresses, exchange flow, whale transactions, DeFi TVL
            - 1.2.3: Return typed dataclass with float | None fields and fetched_at timestamp
            - 1.2.4: Return None on API failure with error logging
        """
        if not self.config.api_key:
            error_msg = "Glassnode API key not configured"
            logger.error(error_msg)
            return [
                ExternalMetrics(
                    source_name="glassnode",
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
                # Normalize symbol for Glassnode (e.g., "BTC" -> "BTC")
                asset = symbol.split("_")[0] if "_" in symbol else symbol

                # Fetch active addresses
                active_addresses = await self._fetch_glassnode_metric(
                    client, asset, "addresses/active_count"
                )
                if active_addresses is not None:
                    metrics["active_addresses"] = float(active_addresses)
                else:
                    is_stale = True

                # Fetch net exchange flow
                exchange_flow = await self._fetch_glassnode_metric(
                    client, asset, "transactions/transfers_volume_exchanges_net"
                )
                if exchange_flow is not None:
                    metrics["net_exchange_flow"] = float(exchange_flow)
                else:
                    is_stale = True

                # Fetch whale transaction count
                whale_count = await self._fetch_glassnode_metric(
                    client, asset, "transactions/transfers_volume_to_exchanges_whale_count"
                )
                if whale_count is not None:
                    metrics["whale_tx_count"] = float(whale_count)
                else:
                    is_stale = True

                # Note: DeFi TVL is typically a global metric, not per-asset
                # For now, we'll fetch it for ETH as a proxy
                if asset.upper() == "ETH":
                    defi_tvl = await self._fetch_glassnode_metric(
                        client, asset, "defi/total_value_locked"
                    )
                    if defi_tvl is not None:
                        metrics["defi_tvl"] = float(defi_tvl)
                    else:
                        is_stale = True

                # Add timestamp
                metrics["fetched_at"] = fetched_at.timestamp()

                # Set error message if we failed to fetch meaningful data
                if is_stale and len([k for k, v in metrics.items() if k != "fetched_at" and v is not None]) == 0:
                    error_message = f"Failed to fetch any on-chain data for {symbol}"
                    logger.error(error_message)

                logger.info(
                    f"Fetched Glassnode data for {symbol}: "
                    f"{len([k for k, v in metrics.items() if v is not None])} metrics"
                )

            except Exception as e:
                error_message = f"Error fetching Glassnode data for {symbol}: {e}"
                logger.exception(error_message)
                is_stale = True

            results.append(
                ExternalMetrics(
                    source_name="glassnode",
                    symbol=symbol,
                    metrics=metrics,
                    is_stale=is_stale,
                    error_message=error_message,
                )
            )

        return results

    async def _fetch_glassnode_metric(
        self, client: httpx.AsyncClient, asset: str, metric_path: str
    ) -> float | None:
        """
        Fetch a single metric from Glassnode API.

        Args:
            client: HTTP client to use for requests
            asset: Asset symbol (e.g., "BTC", "ETH")
            metric_path: Glassnode metric path (e.g., "addresses/active_count")

        Returns:
            Metric value as float, or None if fetch fails

        Requirements:
            - 1.2.2: Fetch individual on-chain metrics
            - 1.2.4: Return None on API failure with error logging
        """
        try:
            url = f"{self.config.base_url}/metrics/{metric_path}"
            params: dict[str, Any] = {
                "a": asset.upper(),
                "api_key": self.config.api_key,
                "i": "24h",  # 24-hour interval
                "c": "native",  # Native units
            }

            response = await client.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            if not data or not isinstance(data, list) or len(data) == 0:
                logger.warning(f"Glassnode {metric_path} returned empty data for {asset}")
                return None

            # Get the most recent value
            latest = data[-1]
            value = latest.get("v")

            if value is None:
                logger.warning(f"Glassnode {metric_path} returned null value for {asset}")
                return None

            return float(value)

        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error fetching Glassnode {metric_path} for {asset}: "
                f"{e.response.status_code}"
            )
            return None
        except httpx.RequestError as e:
            logger.error(f"Request error fetching Glassnode {metric_path} for {asset}: {e}")
            return None
        except (KeyError, ValueError, TypeError, IndexError) as e:
            logger.error(f"Error parsing Glassnode {metric_path} for {asset}: {e}")
            return None

    async def _fetch_intotheblock(self, symbols: list[str]) -> list[ExternalMetrics]:
        """
        Fetch on-chain metrics from IntoTheBlock API.

        IntoTheBlock requires an API key for all endpoints.

        Args:
            symbols: List of symbols to fetch data for

        Returns:
            List of ExternalMetrics with IntoTheBlock data

        Requirements:
            - 1.2.2: Fetch active addresses, exchange flow, whale transactions, DeFi TVL
            - 1.2.3: Return typed dataclass with float | None fields and fetched_at timestamp
            - 1.2.4: Return None on API failure with error logging
        """
        if not self.config.api_key:
            error_msg = "IntoTheBlock API key not configured"
            logger.error(error_msg)
            return [
                ExternalMetrics(
                    source_name="intotheblock",
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
                # Normalize symbol for IntoTheBlock (e.g., "BTC" -> "btc")
                asset = symbol.split("_")[0].lower() if "_" in symbol else symbol.lower()

                # Fetch active addresses
                active_addresses = await self._fetch_intotheblock_metric(
                    client, asset, "active-addresses"
                )
                if active_addresses is not None:
                    metrics["active_addresses"] = float(active_addresses)
                else:
                    is_stale = True

                # Fetch exchange flow
                exchange_flow = await self._fetch_intotheblock_metric(
                    client, asset, "exchange-flow"
                )
                if exchange_flow is not None:
                    metrics["net_exchange_flow"] = float(exchange_flow)
                else:
                    is_stale = True

                # Fetch whale transactions
                whale_count = await self._fetch_intotheblock_metric(
                    client, asset, "large-transactions"
                )
                if whale_count is not None:
                    metrics["whale_tx_count"] = float(whale_count)
                else:
                    is_stale = True

                # Fetch DeFi TVL (if available for this asset)
                if asset in ["eth", "ethereum"]:
                    defi_tvl = await self._fetch_intotheblock_metric(client, asset, "defi-tvl")
                    if defi_tvl is not None:
                        metrics["defi_tvl"] = float(defi_tvl)
                    else:
                        is_stale = True

                # Add timestamp
                metrics["fetched_at"] = fetched_at.timestamp()

                # Set error message if we failed to fetch meaningful data
                if is_stale and len([k for k, v in metrics.items() if k != "fetched_at" and v is not None]) == 0:
                    error_message = f"Failed to fetch any on-chain data for {symbol}"
                    logger.error(error_message)

                logger.info(
                    f"Fetched IntoTheBlock data for {symbol}: "
                    f"{len([k for k, v in metrics.items() if v is not None])} metrics"
                )

            except Exception as e:
                error_message = f"Error fetching IntoTheBlock data for {symbol}: {e}"
                logger.exception(error_message)
                is_stale = True

            results.append(
                ExternalMetrics(
                    source_name="intotheblock",
                    symbol=symbol,
                    metrics=metrics,
                    is_stale=is_stale,
                    error_message=error_message,
                )
            )

        return results

    async def _fetch_intotheblock_metric(
        self, client: httpx.AsyncClient, asset: str, metric_type: str
    ) -> float | None:
        """
        Fetch a single metric from IntoTheBlock API.

        Args:
            client: HTTP client to use for requests
            asset: Asset symbol (e.g., "btc", "eth")
            metric_type: IntoTheBlock metric type (e.g., "active-addresses")

        Returns:
            Metric value as float, or None if fetch fails

        Requirements:
            - 1.2.2: Fetch individual on-chain metrics
            - 1.2.4: Return None on API failure with error logging
        """
        try:
            url = f"{self.config.base_url}/market/{asset}/{metric_type}"
            headers = {"Authorization": f"Bearer {self.config.api_key}"}

            response = await client.get(url, headers=headers)
            response.raise_for_status()

            data = response.json()
            if not data or "data" not in data:
                logger.warning(f"IntoTheBlock {metric_type} returned empty data for {asset}")
                return None

            # Extract value based on metric type
            metric_data = data["data"]
            value = None

            if metric_type == "active-addresses":
                value = metric_data.get("count")
            elif metric_type == "exchange-flow":
                # Net flow = inflow - outflow
                inflow = metric_data.get("inflow", 0)
                outflow = metric_data.get("outflow", 0)
                value = inflow - outflow
            elif metric_type == "large-transactions":
                value = metric_data.get("count")
            elif metric_type == "defi-tvl":
                value = metric_data.get("total_value_locked")

            if value is None:
                logger.warning(f"IntoTheBlock {metric_type} returned null value for {asset}")
                return None

            return float(value)

        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error fetching IntoTheBlock {metric_type} for {asset}: "
                f"{e.response.status_code}"
            )
            return None
        except httpx.RequestError as e:
            logger.error(f"Request error fetching IntoTheBlock {metric_type} for {asset}: {e}")
            return None
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error parsing IntoTheBlock {metric_type} for {asset}: {e}")
            return None

    async def close(self) -> None:
        """
        Close the HTTP client and release resources.

        Only closes the client if it was created by this instance
        (not provided externally).

        Requirements:
            - 1.2.1: Proper resource management with httpx.AsyncClient
        """
        if self._http_client is not None and self._owned_client:
            await self._http_client.aclose()
            self._http_client = None
