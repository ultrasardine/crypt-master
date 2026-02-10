"""
Unit Tests for Market Data Hub.

This module tests the Market Data Hub integration with mocked client responses,
stale field tracking, and WebSocket broadcast functionality.

Requirements:
- 1.5: External Data Sync Celery Task
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lib.sync.external_sources import ExternalMetrics
from lib.sync.hub import HubConfig, MarketDataHub


class MockClient:
    """Mock external source client for testing."""

    def __init__(self, metrics: list[ExternalMetrics]):
        self.metrics = metrics
        self.fetch_called = False
        self.close_called = False

    async def fetch(self, symbols: list[str]) -> list[ExternalMetrics]:
        """Mock fetch that returns predefined metrics."""
        self.fetch_called = True
        return self.metrics

    async def close(self) -> None:
        """Mock close method."""
        self.close_called = True


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_hub_with_successful_clients():
    """Test hub with all clients returning successful data."""
    # Create mock clients with successful metrics
    market_data_metrics = [
        ExternalMetrics(
            source_name="coingecko",
            symbol=None,
            metrics={
                "btc_dominance": 45.0,
                "global_market_cap": 1500000000000.0,
                "total_volume_24h": 85000000000.0,
            },
            is_stale=False,
            error_message=None,
        )
    ]

    onchain_metrics = [
        ExternalMetrics(
            source_name="glassnode",
            symbol="BTC_USDT",
            metrics={
                "active_addresses": 1000000,
                "net_exchange_flow": -5000.0,
                "whale_tx_count": 150,
                "defi_tvl": 50000000000.0,
            },
            is_stale=False,
            error_message=None,
        )
    ]

    social_metrics = [
        ExternalMetrics(
            source_name="lunarcrush",
            symbol="BTC_USDT",
            metrics={
                "sentiment_polarity": 0.6,
                "mention_count": 50000,
                "buzz_score": 0.75,
            },
            is_stale=False,
            error_message=None,
        )
    ]

    clients = [
        MockClient(market_data_metrics),
        MockClient(onchain_metrics),
        MockClient(social_metrics),
    ]

    # Create hub with mock clients
    config = HubConfig(symbols=["BTC_USDT"])
    hub = MarketDataHub(config=config, clients=clients)  # type: ignore[arg-type]

    # Run sync
    snapshot = await hub.sync()

    # Verify snapshot was created
    assert snapshot is not None
    assert snapshot.id is not None
    assert snapshot.symbol == "BTC_USDT"

    # Verify data was merged correctly
    assert snapshot.btc_dominance == 45.0
    assert snapshot.global_market_cap == Decimal("1500000000000.0")
    assert snapshot.total_volume_24h == Decimal("85000000000.0")
    assert snapshot.active_addresses == 1000000
    assert snapshot.net_exchange_flow == -5000.0
    assert snapshot.whale_tx_count == 150
    assert snapshot.defi_tvl == Decimal("50000000000.0")

    # Verify sentiment was normalized (0.6 -> 0.8 on 0-1 scale)
    assert snapshot.social_sentiment_score is not None
    assert 0.0 <= snapshot.social_sentiment_score <= 1.0

    assert snapshot.social_mention_count == 50000
    assert snapshot.social_buzz_score == 0.75

    # Verify snapshot is not stale
    assert snapshot.is_stale is False
    assert len(snapshot.stale_fields) == 0

    # Verify all clients were called
    for client in clients:
        assert client.fetch_called

    # Clean up
    await hub.close()

    # Verify clients were NOT closed (they were provided externally)
    # The hub only closes clients it creates itself
    for client in clients:
        assert not client.close_called


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_hub_with_stale_metrics():
    """Test hub with clients returning stale metrics."""
    # Create mock clients with stale metrics
    stale_market_data = [
        ExternalMetrics(
            source_name="coingecko",
            symbol=None,
            metrics={
                "btc_dominance": 45.0,
                "global_market_cap": 1500000000000.0,
            },
            is_stale=True,
            error_message="Using cached data",
        )
    ]

    fresh_onchain = [
        ExternalMetrics(
            source_name="glassnode",
            symbol="BTC_USDT",
            metrics={
                "active_addresses": 1000000,
                "net_exchange_flow": -5000.0,
            },
            is_stale=False,
            error_message=None,
        )
    ]

    clients = [
        MockClient(stale_market_data),
        MockClient(fresh_onchain),
    ]

    # Create hub with mock clients
    config = HubConfig(symbols=["BTC_USDT"])
    hub = MarketDataHub(config=config, clients=clients)  # type: ignore[arg-type]

    # Run sync
    snapshot = await hub.sync()

    # Verify snapshot was created
    assert snapshot is not None
    assert snapshot.id is not None

    # Verify snapshot is marked stale
    assert snapshot.is_stale is True
    assert snapshot.is_degraded is True

    # Verify stale fields are tracked
    assert len(snapshot.stale_fields) > 0
    assert "btc_dominance" in snapshot.stale_fields or "global_market_cap" in snapshot.stale_fields

    # Clean up
    await hub.close()


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_hub_with_failing_client():
    """Test hub with one client failing."""
    # Create mock clients with one failing
    successful_metrics = [
        ExternalMetrics(
            source_name="coingecko",
            symbol=None,
            metrics={
                "btc_dominance": 45.0,
            },
            is_stale=False,
            error_message=None,
        )
    ]

    class FailingClient:
        async def fetch(self, symbols: list[str]) -> list[ExternalMetrics]:
            raise RuntimeError("API connection failed")

        async def close(self) -> None:
            pass

    clients = [
        MockClient(successful_metrics),
        FailingClient(),
    ]

    # Create hub with mock clients
    config = HubConfig(symbols=["BTC_USDT"])
    hub = MarketDataHub(config=config, clients=clients)  # type: ignore[arg-type]

    # Run sync
    snapshot = await hub.sync()

    # Verify snapshot was created despite failure
    assert snapshot is not None
    assert snapshot.id is not None

    # Verify snapshot is marked stale
    assert snapshot.is_stale is True

    # Verify stale fields are tracked
    assert len(snapshot.stale_fields) > 0

    # Clean up
    await hub.close()


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_hub_normalizes_scores():
    """Test that hub normalizes scores to 0.0-1.0 range."""
    # Create mock client with sentiment that needs normalization
    metrics = [
        ExternalMetrics(
            source_name="lunarcrush",
            symbol="BTC_USDT",
            metrics={
                "sentiment_polarity": -0.5,  # Should be normalized to 0.25
                "buzz_score": 0.8,  # Should stay 0.8
            },
            is_stale=False,
            error_message=None,
        )
    ]

    clients = [MockClient(metrics)]

    # Create hub with mock clients
    config = HubConfig(symbols=["BTC_USDT"])
    hub = MarketDataHub(config=config, clients=clients)  # type: ignore[arg-type]

    # Run sync
    snapshot = await hub.sync()

    # Verify sentiment was normalized
    assert snapshot.social_sentiment_score is not None
    assert 0.0 <= snapshot.social_sentiment_score <= 1.0
    # -0.5 on [-1, 1] scale -> 0.25 on [0, 1] scale
    assert abs(snapshot.social_sentiment_score - 0.25) < 0.01

    # Verify buzz score is in range
    assert snapshot.social_buzz_score == 0.8

    # Clean up
    await hub.close()


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_hub_tracks_stale_fields_for_none_values():
    """Test that hub tracks fields as stale when they are None."""
    # Create mock client with partial metrics
    metrics = [
        ExternalMetrics(
            source_name="coingecko",
            symbol=None,
            metrics={
                "btc_dominance": 45.0,
                # Missing global_market_cap and total_volume_24h
            },
            is_stale=False,
            error_message=None,
        )
    ]

    clients = [MockClient(metrics)]

    # Create hub with mock clients
    config = HubConfig(symbols=["BTC_USDT"])
    hub = MarketDataHub(config=config, clients=clients)  # type: ignore[arg-type]

    # Run sync
    snapshot = await hub.sync()

    # Verify snapshot was created
    assert snapshot is not None

    # Verify missing fields are tracked as stale
    assert "global_market_cap" in snapshot.stale_fields
    assert "total_volume_24h" in snapshot.stale_fields

    # Clean up
    await hub.close()


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_hub_with_empty_symbols():
    """Test hub with no symbols configured."""
    # Create mock client
    metrics = [
        ExternalMetrics(
            source_name="coingecko",
            symbol=None,
            metrics={"btc_dominance": 45.0},
            is_stale=False,
            error_message=None,
        )
    ]

    clients = [MockClient(metrics)]

    # Create hub with empty symbols
    config = HubConfig(symbols=[])
    hub = MarketDataHub(config=config, clients=clients)  # type: ignore[arg-type]

    # Run sync
    snapshot = await hub.sync()

    # Verify snapshot was created with None symbol
    assert snapshot is not None
    assert snapshot.symbol is None

    # Clean up
    await hub.close()


@pytest.mark.django_db
def test_celery_task_fetch_external_market_data():
    """Test the Celery task for fetching external market data."""
    from apps.core.tasks import fetch_external_market_data

    # Mock the hub and its dependencies
    with patch("lib.sync.hub.MarketDataHub") as mock_hub_class:
        mock_hub = MagicMock()
        mock_hub_class.return_value = mock_hub

        # Mock snapshot
        mock_snapshot = MagicMock()
        mock_snapshot.id = 123
        mock_snapshot.symbol = "BTC_USDT"
        mock_snapshot.regime = "RISK_ON"
        mock_snapshot.is_stale = False
        mock_snapshot.is_degraded = False
        mock_snapshot.timestamp = datetime.now(timezone.utc)

        # Mock sync method to return the snapshot
        async def mock_sync():
            return mock_snapshot

        mock_hub.sync = mock_sync

        # Mock close method
        async def mock_close():
            pass

        mock_hub.close = mock_close

        # Mock WebSocketBroadcaster
        with patch("lib.messaging.websocket.WebSocketBroadcaster") as mock_broadcaster_class:
            mock_broadcaster = MagicMock()
            mock_broadcaster_class.return_value = mock_broadcaster

            # Mock broadcast method
            async def mock_broadcast(data):
                pass

            mock_broadcaster.broadcast_market_context_update = mock_broadcast

            # Call the task
            result = fetch_external_market_data()

            # Verify task succeeded
            assert result["status"] == "success"
            assert result["snapshot_id"] == 123
            assert result["regime"] == "RISK_ON"
            assert result["is_stale"] is False


@pytest.mark.django_db
def test_celery_task_handles_failure():
    """Test that Celery task handles failures gracefully."""
    from apps.core.tasks import fetch_external_market_data

    # Mock the hub to raise an exception
    with patch("lib.sync.hub.MarketDataHub") as mock_hub_class:
        mock_hub = MagicMock()
        mock_hub_class.return_value = mock_hub

        # Mock sync to raise an exception
        async def mock_sync():
            raise RuntimeError("All APIs failed")

        mock_hub.sync = mock_sync

        # Mock MarketContextSnapshot.objects.create for fallback
        with patch("apps.core.models.MarketContextSnapshot") as mock_snapshot_class:
            mock_snapshot = MagicMock()
            mock_snapshot.id = 456
            mock_snapshot_class.objects.create.return_value = mock_snapshot

            # Call the task
            result = fetch_external_market_data()

            # Verify task created fallback snapshot
            assert result["status"] == "degraded"
            assert result["snapshot_id"] == 456
            assert result["is_stale"] is True
            assert "error" in result
