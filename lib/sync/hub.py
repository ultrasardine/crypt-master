"""
Market Data Hub.

This module orchestrates all external source clients and the existing PublicDataService
to create unified MarketContextSnapshot records. The hub fans out to all clients
concurrently, normalizes scores, merges results, and tracks stale fields when clients fail.

Requirements:
- 1.5.1: Celery task calls MarketDataHub.sync()
- 1.5.2: Hub fans out to all clients using asyncio.gather(return_exceptions=True)
- 1.5.4: Track stale fields when clients fail
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from asgiref.sync import sync_to_async
from django.utils import timezone as django_timezone

from apps.core.models import MarketContextSnapshot, TradingPair
from lib.sync.external_sources import ExternalMetrics, ExternalSourceClient
from lib.sync.external_sources.cmc_client import MarketDataClient
from lib.sync.external_sources.onchain_client import OnChainClient
from lib.sync.external_sources.social_sentiment_client import SocialSentimentClient

logger = logging.getLogger(__name__)


@dataclass
class HubConfig:
    """
    Configuration for the Market Data Hub.

    Attributes:
        sync_interval_seconds: How often to sync data (default: 15 minutes)
        source_timeout_seconds: Timeout for individual source clients
        symbols: List of trading pair symbols to fetch data for
                 (defaults to active TradingPairs if None)

    Requirements:
        - 1.5.2: Configurable timeout for source clients
    """

    sync_interval_seconds: int = 900  # 15 minutes
    source_timeout_seconds: float = 30.0
    symbols: list[str] | None = None


class MarketDataHub:
    """
    Orchestrates external data source clients to create MarketContextSnapshot records.

    The hub:
    1. Fans out to all external source clients concurrently
    2. Normalizes scores to 0.0-1.0 range
    3. Merges results from all sources
    4. Creates MarketContextSnapshot records
    5. Tracks stale fields when clients fail

    Requirements:
        - 1.5.1: Hub provides sync() method for Celery task
        - 1.5.2: Fans out to all clients using asyncio.gather(return_exceptions=True)
        - 1.5.4: Tracks stale fields when clients fail

    Example:
        >>> config = HubConfig(symbols=["BTC_USDT"])
        >>> hub = MarketDataHub(config)
        >>> snapshot = await hub.sync()
        >>> await hub.close()
    """

    def __init__(
        self,
        config: HubConfig | None = None,
        clients: list[ExternalSourceClient] | None = None,
    ) -> None:
        """
        Initialize the Market Data Hub.

        Args:
            config: Hub configuration (defaults to HubConfig())
            clients: Optional list of external source clients
                    (defaults to MarketDataClient, OnChainClient, SocialSentimentClient)

        Requirements:
            - 1.5.1: Initialize hub with configurable clients
        """
        self.config = config or HubConfig()
        self._clients = clients or self._create_default_clients()
        self._owned_clients = clients is None

    def _create_default_clients(self) -> list[ExternalSourceClient]:
        """
        Create default external source clients.

        Returns:
            List of default clients (MarketDataClient, OnChainClient, SocialSentimentClient)

        Requirements:
            - 1.5.1: Hub uses all three external source clients
        """
        return [
            MarketDataClient(),
            OnChainClient(),
            SocialSentimentClient(),
        ]

    def _get_symbols(self) -> list[str]:
        """
        Get the list of symbols to fetch data for.

        Returns:
            List of trading pair symbols (from config or active TradingPairs)

        Requirements:
            - 1.5.1: Default to active TradingPairs if symbols not configured
        """
        if self.config.symbols:
            return self.config.symbols

        # Get active trading pairs from database (sync operation)
        active_pairs = TradingPair.objects.active().values_list("symbol", flat=True)
        return list(active_pairs)

    async def _get_symbols_async(self) -> list[str]:
        """
        Get the list of symbols to fetch data for (async-safe version).

        Returns:
            List of trading pair symbols (from config or active TradingPairs)

        Requirements:
            - 1.5.1: Default to active TradingPairs if symbols not configured
        """
        if self.config.symbols:
            return self.config.symbols

        # Get active trading pairs from database using sync_to_async
        return await sync_to_async(self._get_symbols_sync)()

    def _get_symbols_sync(self) -> list[str]:
        """Sync helper for getting symbols from database."""
        active_pairs = TradingPair.objects.active().values_list("symbol", flat=True)
        return list(active_pairs)

    async def sync(self) -> MarketContextSnapshot:
        """
        Fetch data from all external sources and create MarketContextSnapshot.

        This method:
        1. Fans out to all clients concurrently using asyncio.gather
        2. Normalizes scores to 0.0-1.0 range
        3. Merges results from all sources
        4. Creates and saves MarketContextSnapshot record
        5. Tracks stale fields when clients fail

        Returns:
            Created MarketContextSnapshot instance

        Requirements:
            - 1.5.1: Sync method for Celery task
            - 1.5.2: Fan out to all clients using asyncio.gather(return_exceptions=True)
            - 1.5.4: Track stale fields when clients fail
        """
        logger.info("Starting Market Data Hub sync")

        # Get symbols to fetch (async-safe)
        symbols = await self._get_symbols_async()
        if not symbols:
            logger.warning("No symbols configured for Market Data Hub sync")
            symbols = []

        # Fan out to all clients concurrently
        # Use return_exceptions=True so one client failure doesn't block others
        tasks = [
            self._fetch_from_client(client, symbols)
            for client in self._clients
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results and track failures
        all_metrics: list[ExternalMetrics] = []
        stale_sources: list[str] = []

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Client raised an exception
                client_name = self._clients[i].__class__.__name__
                logger.error(f"Client {client_name} failed: {result}")
                stale_sources.append(client_name)
            elif isinstance(result, list):
                # Client returned list of ExternalMetrics
                all_metrics.extend(result)
                # Check for stale metrics
                for metric in result:
                    if metric.is_stale:
                        stale_sources.append(metric.source_name)
            else:
                # Unexpected result type
                client_name = self._clients[i].__class__.__name__
                logger.warning(f"Client {client_name} returned unexpected result: {type(result)}")
                stale_sources.append(client_name)

        # Merge metrics and create snapshot (async-safe)
        snapshot = await self._create_snapshot_async(all_metrics, stale_sources, symbols)

        logger.info(
            f"Market Data Hub sync complete: "
            f"snapshot_id={snapshot.id}, "
            f"is_stale={snapshot.is_stale}, "
            f"stale_sources={len(stale_sources)}"
        )

        return snapshot

    async def _fetch_from_client(
        self,
        client: ExternalSourceClient,
        symbols: list[str],
    ) -> list[ExternalMetrics]:
        """
        Fetch data from a single client with timeout.

        Args:
            client: External source client to fetch from
            symbols: List of symbols to fetch

        Returns:
            List of ExternalMetrics from the client

        Requirements:
            - 1.5.2: Fetch from clients with configurable timeout
        """
        try:
            # Apply timeout to client fetch
            result = await asyncio.wait_for(
                client.fetch(symbols),
                timeout=self.config.source_timeout_seconds,
            )
            return result
        except asyncio.TimeoutError:
            client_name = client.__class__.__name__
            logger.error(f"Client {client_name} timed out after {self.config.source_timeout_seconds}s")
            # Re-raise as a regular exception so it's tracked as a failure
            raise RuntimeError(f"Client {client_name} timed out")
        except Exception as e:
            client_name = client.__class__.__name__
            logger.exception(f"Error fetching from client {client_name}: {e}")
            raise

    async def _create_snapshot_async(
        self,
        all_metrics: list[ExternalMetrics],
        stale_sources: list[str],
        symbols: list[str],
    ) -> MarketContextSnapshot:
        """
        Create MarketContextSnapshot from merged metrics (async-safe version).

        Args:
            all_metrics: List of ExternalMetrics from all sources
            stale_sources: List of source names that failed or returned stale data
            symbols: List of symbols that were requested

        Returns:
            Created and saved MarketContextSnapshot instance

        Requirements:
            - 1.5.2: Merge results and create MarketContextSnapshot record
            - 1.5.4: Track stale fields when clients fail
        """
        # Merge metrics by source
        merged = self._merge_metrics(all_metrics)

        # Normalize scores to 0.0-1.0 range
        normalized = self._normalize_scores(merged)

        # Track which fields are stale
        stale_fields = self._identify_stale_fields(normalized, stale_sources)

        # Determine if snapshot is stale (any source failed)
        is_stale = len(stale_sources) > 0

        # Use first symbol if available, otherwise None for global metrics
        symbol = symbols[0] if symbols else None

        # Get Fear & Greed Index (async-safe)
        fear_greed_index = await self._get_fear_greed_index_async()

        # Create snapshot using sync_to_async
        snapshot = await sync_to_async(self._create_snapshot_sync)(
            symbol=symbol,
            normalized=normalized,
            stale_fields=stale_fields,
            is_stale=is_stale,
            fear_greed_index=fear_greed_index,
        )

        return snapshot

    def _create_snapshot_sync(
        self,
        symbol: str | None,
        normalized: dict[str, Any],
        stale_fields: list[str],
        is_stale: bool,
        fear_greed_index: int | None,
    ) -> MarketContextSnapshot:
        """Sync helper for creating MarketContextSnapshot."""
        return MarketContextSnapshot.objects.create(
            symbol=symbol,
            timestamp=django_timezone.now(),
            # Macro market metrics
            btc_dominance=normalized.get("btc_dominance"),
            global_market_cap=normalized.get("global_market_cap"),
            total_volume_24h=normalized.get("total_volume_24h"),
            # On-chain metrics
            active_addresses=normalized.get("active_addresses"),
            net_exchange_flow=normalized.get("net_exchange_flow"),
            whale_tx_count=normalized.get("whale_tx_count"),
            defi_tvl=normalized.get("defi_tvl"),
            # Social sentiment metrics
            social_sentiment_score=normalized.get("sentiment_polarity"),
            social_mention_count=normalized.get("mention_count"),
            social_buzz_score=normalized.get("buzz_score"),
            # Fear & Greed Index (if available from existing MarketSentimentData)
            fear_greed_index=fear_greed_index,
            # Data quality tracking
            is_stale=is_stale,
            stale_fields=stale_fields,
            # Regime scores will be computed later by ContextScorer
            regime=None,
            trend_strength_score=None,
            risk_regime_score=None,
            sentiment_regime_score=None,
            is_degraded=is_stale,
        )

    def _create_snapshot(
        self,
        all_metrics: list[ExternalMetrics],
        stale_sources: list[str],
        symbols: list[str],
    ) -> MarketContextSnapshot:
        """
        Create MarketContextSnapshot from merged metrics.

        Args:
            all_metrics: List of ExternalMetrics from all sources
            stale_sources: List of source names that failed or returned stale data
            symbols: List of symbols that were requested

        Returns:
            Created and saved MarketContextSnapshot instance

        Requirements:
            - 1.5.2: Merge results and create MarketContextSnapshot record
            - 1.5.4: Track stale fields when clients fail
        """
        # Merge metrics by source
        merged = self._merge_metrics(all_metrics)

        # Normalize scores to 0.0-1.0 range
        normalized = self._normalize_scores(merged)

        # Track which fields are stale
        stale_fields = self._identify_stale_fields(normalized, stale_sources)

        # Determine if snapshot is stale (any source failed)
        is_stale = len(stale_sources) > 0

        # Create snapshot
        # Use first symbol if available, otherwise None for global metrics
        symbol = symbols[0] if symbols else None

        snapshot = MarketContextSnapshot.objects.create(
            symbol=symbol,
            timestamp=django_timezone.now(),
            # Macro market metrics
            btc_dominance=normalized.get("btc_dominance"),
            global_market_cap=normalized.get("global_market_cap"),
            total_volume_24h=normalized.get("total_volume_24h"),
            # On-chain metrics
            active_addresses=normalized.get("active_addresses"),
            net_exchange_flow=normalized.get("net_exchange_flow"),
            whale_tx_count=normalized.get("whale_tx_count"),
            defi_tvl=normalized.get("defi_tvl"),
            # Social sentiment metrics
            social_sentiment_score=normalized.get("sentiment_polarity"),
            social_mention_count=normalized.get("mention_count"),
            social_buzz_score=normalized.get("buzz_score"),
            # Fear & Greed Index (if available from existing MarketSentimentData)
            fear_greed_index=self._get_fear_greed_index(),
            # Data quality tracking
            is_stale=is_stale,
            stale_fields=stale_fields,
            # Regime scores will be computed later by ContextScorer
            regime=None,
            trend_strength_score=None,
            risk_regime_score=None,
            sentiment_regime_score=None,
            is_degraded=is_stale,
        )

        return snapshot

    def _merge_metrics(self, all_metrics: list[ExternalMetrics]) -> dict[str, Any]:
        """
        Merge metrics from all sources into a single dict.

        Args:
            all_metrics: List of ExternalMetrics from all sources

        Returns:
            Dict mapping metric names to values

        Requirements:
            - 1.5.2: Merge results from all sources
        """
        merged: dict[str, Any] = {}

        for metric in all_metrics:
            # Merge all metrics from this source
            for key, value in metric.metrics.items():
                if value is not None:
                    # Use the first non-None value for each metric
                    if key not in merged or merged[key] is None:
                        merged[key] = value

        return merged

    def _normalize_scores(self, metrics: dict[str, Any]) -> dict[str, Any]:
        """
        Normalize scores to 0.0-1.0 range where applicable.

        Args:
            metrics: Dict of raw metrics

        Returns:
            Dict with normalized scores

        Requirements:
            - 1.5.2: Normalize scores to 0.0-1.0 range
        """
        normalized = metrics.copy()

        # Sentiment polarity is already -1.0 to 1.0, normalize to 0.0-1.0
        if "sentiment_polarity" in normalized and normalized["sentiment_polarity"] is not None:
            # Convert from [-1, 1] to [0, 1]
            normalized["sentiment_polarity"] = (float(normalized["sentiment_polarity"]) + 1.0) / 2.0

        # Buzz score should already be 0.0-1.0, but clamp just in case
        if "buzz_score" in normalized and normalized["buzz_score"] is not None:
            normalized["buzz_score"] = max(0.0, min(1.0, float(normalized["buzz_score"])))

        # Other metrics (btc_dominance, market_cap, volume, etc.) are kept as-is
        # They will be normalized by ContextScorer when computing regime scores

        return normalized

    def _identify_stale_fields(
        self,
        metrics: dict[str, Any],
        stale_sources: list[str],
    ) -> list[str]:
        """
        Identify which fields are stale based on failed sources.

        Args:
            metrics: Dict of merged metrics
            stale_sources: List of source names that failed

        Returns:
            List of field names that are stale

        Requirements:
            - 1.5.4: Track stale fields when clients fail
        """
        stale_fields: list[str] = []

        # Map source names to field names
        source_field_map = {
            "coingecko": ["btc_dominance", "global_market_cap", "total_volume_24h"],
            "coinmarketcap": ["btc_dominance", "global_market_cap", "total_volume_24h"],
            "MarketDataClient": ["btc_dominance", "global_market_cap", "total_volume_24h"],
            "glassnode": ["active_addresses", "net_exchange_flow", "whale_tx_count", "defi_tvl"],
            "intotheblock": ["active_addresses", "net_exchange_flow", "whale_tx_count", "defi_tvl"],
            "OnChainClient": ["active_addresses", "net_exchange_flow", "whale_tx_count", "defi_tvl"],
            "lunarcrush": ["sentiment_polarity", "mention_count", "buzz_score"],
            "santiment": ["sentiment_polarity", "mention_count", "buzz_score"],
            "SocialSentimentClient": ["sentiment_polarity", "mention_count", "buzz_score"],
        }

        # Add fields from stale sources
        for source in stale_sources:
            if source in source_field_map:
                stale_fields.extend(source_field_map[source])

        # Also check for None values in metrics
        for field_name in [
            "btc_dominance", "global_market_cap", "total_volume_24h",
            "active_addresses", "net_exchange_flow", "whale_tx_count", "defi_tvl",
            "sentiment_polarity", "mention_count", "buzz_score",
        ]:
            if field_name not in metrics or metrics[field_name] is None:
                if field_name not in stale_fields:
                    stale_fields.append(field_name)

        return stale_fields

    def _get_fear_greed_index(self) -> int | None:
        """
        Get the latest Fear & Greed Index from MarketSentimentData.

        Returns:
            Fear & Greed Index value (0-100), or None if not available

        Requirements:
            - 1.5.2: Include existing public data in snapshot
        """
        try:
            from apps.core.models import MarketSentimentData

            latest = MarketSentimentData.get_latest()
            if latest and not latest.is_stale:
                return latest.fear_greed_index
        except Exception as e:
            logger.warning(f"Error fetching Fear & Greed Index: {e}")

        return None

    async def _get_fear_greed_index_async(self) -> int | None:
        """
        Get the latest Fear & Greed Index from MarketSentimentData (async-safe version).

        Returns:
            Fear & Greed Index value (0-100), or None if not available

        Requirements:
            - 1.5.2: Include existing public data in snapshot
        """
        return await sync_to_async(self._get_fear_greed_index)()

    async def close(self) -> None:
        """
        Close all clients and release resources.

        Only closes clients if they were created by this instance
        (not provided externally).

        Requirements:
            - 1.5.1: Proper resource management
        """
        if self._owned_clients:
            for client in self._clients:
                try:
                    await client.close()
                except Exception as e:
                    client_name = client.__class__.__name__
                    logger.warning(f"Error closing client {client_name}: {e}")
