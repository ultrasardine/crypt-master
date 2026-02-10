"""
Property-Based Tests for Market Data Hub Client Failure Handling.

Feature: market-intelligence-layer
Property 2: Client failure triggers stale fallback

This module tests that when external source clients fail, the Market Data Hub
produces a MarketContextSnapshot with stale fields tracked appropriately.

Requirements:
- 1.5: External Data Sync Celery Task
- Property 2: Client failure triggers stale fallback

Validates: Requirements 1.5
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from lib.sync.external_sources import ExternalMetrics
from lib.sync.hub import HubConfig, MarketDataHub


# Strategy for generating ExternalMetrics with various stale states
@st.composite
def external_metrics_strategy(draw: Any) -> ExternalMetrics:
    """Generate ExternalMetrics with random stale states."""
    source_names = ["coingecko", "glassnode", "lunarcrush"]
    source_name = draw(st.sampled_from(source_names))

    symbol = draw(st.one_of(st.none(), st.sampled_from(["BTC", "ETH", "BTC_USDT"])))

    # Generate random metrics
    metrics = {}
    metric_keys = {
        "coingecko": ["btc_dominance", "global_market_cap", "total_volume_24h"],
        "glassnode": ["active_addresses", "net_exchange_flow", "whale_tx_count", "defi_tvl"],
        "lunarcrush": ["sentiment_polarity", "mention_count", "buzz_score"],
    }

    for key in metric_keys.get(source_name, []):
        # Randomly include or exclude metrics
        if draw(st.booleans()):
            if "count" in key or "addresses" in key:
                metrics[key] = draw(st.integers(min_value=0, max_value=1000000))
            else:
                metrics[key] = draw(st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False))

    is_stale = draw(st.booleans())
    error_message = draw(st.one_of(st.none(), st.text(min_size=1, max_size=100)))

    return ExternalMetrics(
        source_name=source_name,
        symbol=symbol,
        metrics=metrics,
        is_stale=is_stale,
        error_message=error_message,
    )


# Strategy for generating lists of client results (mix of success and failure)
@st.composite
def client_results_strategy(draw: Any) -> list[list[ExternalMetrics] | Exception]:
    """Generate a list of client results with some failures."""
    num_clients = draw(st.integers(min_value=1, max_value=5))
    results: list[list[ExternalMetrics] | Exception] = []

    for _ in range(num_clients):
        # Randomly decide if this client fails
        if draw(st.booleans()):
            # Client raises an exception
            error_types = [
                RuntimeError("API connection failed"),
                TimeoutError("Request timed out"),
                ValueError("Invalid response format"),
            ]
            results.append(draw(st.sampled_from(error_types)))
        else:
            # Client returns metrics (possibly stale)
            num_metrics = draw(st.integers(min_value=0, max_value=3))
            metrics = [draw(external_metrics_strategy()) for _ in range(num_metrics)]
            results.append(metrics)

    return results


class MockClient:
    """Mock external source client for testing."""

    def __init__(self, result: list[ExternalMetrics] | Exception):
        self.result = result
        self.fetch_called = False

    async def fetch(self, symbols: list[str]) -> list[ExternalMetrics]:
        """Mock fetch that returns predefined result or raises exception."""
        self.fetch_called = True
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    async def close(self) -> None:
        """Mock close method."""
        pass


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@given(client_results=client_results_strategy())
@settings(max_examples=25, deadline=None)
async def test_client_failure_triggers_stale_fallback(client_results: list[list[ExternalMetrics] | Exception]) -> None:
    """
    Property 2: Client failure triggers stale fallback.

    For any external source client that raises an exception during fetch,
    the MarketDataHub SHALL produce a MarketContextSnapshot where the fields
    corresponding to that client's data are present (from cache or None) and
    those field names appear in the stale_fields list.

    Validates: Requirements 1.5
    """
    # Create mock clients with predefined results
    mock_clients = [MockClient(result) for result in client_results]

    # Create hub with mock clients
    config = HubConfig(symbols=["BTC_USDT"])
    hub = MarketDataHub(config=config, clients=mock_clients)  # type: ignore[arg-type]

    # Run sync
    snapshot = await hub.sync()

    # Verify snapshot was created
    assert snapshot is not None
    assert snapshot.id is not None

    # Count how many clients failed
    num_failures = sum(1 for result in client_results if isinstance(result, Exception))

    # Count how many clients returned stale metrics
    num_stale = 0
    for result in client_results:
        if isinstance(result, list):
            for metric in result:
                if metric.is_stale:
                    num_stale += 1
                    break  # Count each client only once

    # If any client failed or returned stale data, snapshot should be marked stale
    if num_failures > 0 or num_stale > 0:
        assert snapshot.is_stale is True, "Snapshot should be marked stale when clients fail"
        assert len(snapshot.stale_fields) > 0, "Stale fields should be tracked"
    else:
        # All clients succeeded with fresh data
        # Snapshot may still be stale if some metrics are None
        pass

    # Verify all mock clients were called
    for client in mock_clients:
        assert client.fetch_called, "All clients should be called even if some fail"

    # Clean up
    await hub.close()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@given(
    num_failing_clients=st.integers(min_value=1, max_value=3),
    num_successful_clients=st.integers(min_value=0, max_value=2),
)
@settings(max_examples=20, deadline=None)
async def test_partial_client_failure_still_creates_snapshot(
    num_failing_clients: int,
    num_successful_clients: int,
) -> None:
    """
    Test that partial client failures still result in a valid snapshot.

    Even if some clients fail, the hub should create a snapshot with
    data from successful clients and mark failed fields as stale.

    Validates: Requirements 1.5
    """
    # Create mix of failing and successful clients
    clients: list[MockClient] = []

    # Add failing clients
    for i in range(num_failing_clients):
        clients.append(MockClient(RuntimeError(f"Client {i} failed")))

    # Add successful clients
    for i in range(num_successful_clients):
        metrics = [
            ExternalMetrics(
                source_name=f"source_{i}",
                symbol="BTC_USDT",
                metrics={"test_metric": 42.0},
                is_stale=False,
                error_message=None,
            )
        ]
        clients.append(MockClient(metrics))

    # Create hub with mock clients
    config = HubConfig(symbols=["BTC_USDT"])
    hub = MarketDataHub(config=config, clients=clients)  # type: ignore[arg-type]

    # Run sync
    snapshot = await hub.sync()

    # Verify snapshot was created despite failures
    assert snapshot is not None
    assert snapshot.id is not None

    # Snapshot should be marked stale if any client failed
    if num_failing_clients > 0:
        assert snapshot.is_stale is True
        assert len(snapshot.stale_fields) > 0

    # Clean up
    await hub.close()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_all_clients_fail_creates_stale_snapshot() -> None:
    """
    Test that when all clients fail, a stale snapshot is still created.

    This ensures the system degrades gracefully and doesn't crash when
    all external APIs are unavailable.

    Validates: Requirements 1.5.4
    """
    # Create clients that all fail
    clients = [
        MockClient(RuntimeError("Market data API failed")),
        MockClient(TimeoutError("On-chain API timed out")),
        MockClient(ValueError("Social sentiment API error")),
    ]

    # Create hub with failing clients
    config = HubConfig(symbols=["BTC_USDT"])
    hub = MarketDataHub(config=config, clients=clients)  # type: ignore[arg-type]

    # Run sync
    snapshot = await hub.sync()

    # Verify snapshot was created
    assert snapshot is not None
    assert snapshot.id is not None

    # Snapshot should be marked stale
    assert snapshot.is_stale is True
    assert snapshot.is_degraded is True

    # All fields should be tracked as stale
    assert len(snapshot.stale_fields) > 0

    # Clean up
    await hub.close()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_stale_metrics_tracked_in_snapshot() -> None:
    """
    Test that metrics marked as stale are tracked in the snapshot.

    Even if a client succeeds but returns stale data, those fields
    should be tracked in stale_fields.

    Validates: Requirements 1.5.4
    """
    # Create client that returns stale metrics
    stale_metrics = [
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

    clients = [MockClient(stale_metrics)]

    # Create hub with client returning stale data
    config = HubConfig(symbols=["BTC_USDT"])
    hub = MarketDataHub(config=config, clients=clients)  # type: ignore[arg-type]

    # Run sync
    snapshot = await hub.sync()

    # Verify snapshot was created
    assert snapshot is not None
    assert snapshot.id is not None

    # Snapshot should be marked stale
    assert snapshot.is_stale is True

    # Stale fields should be tracked
    assert len(snapshot.stale_fields) > 0

    # Clean up
    await hub.close()
