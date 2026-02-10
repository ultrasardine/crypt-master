"""
Unit tests for external sources infrastructure.

Tests the ExternalMetrics dataclass and ExternalSourceClient protocol
defined in lib/sync/external_sources/__init__.py.

Requirements:
- 1.1.1: Market data aggregator client interface
- 1.2.1: On-chain metrics client interface
- 1.3.1: Social sentiment client interface
"""

from __future__ import annotations

import pytest

from lib.sync.external_sources import ExternalMetrics, ExternalSourceClient


class TestExternalMetrics:
    """Test ExternalMetrics dataclass."""

    def test_create_global_metrics(self) -> None:
        """Test creating ExternalMetrics for global data."""
        metrics = ExternalMetrics(
            source_name="coingecko",
            symbol=None,
            metrics={
                "btc_dominance": 45.2,
                "global_market_cap": 1_500_000_000_000.0,
                "total_volume_24h": 85_000_000_000.0,
            },
            is_stale=False,
            error_message=None,
        )

        assert metrics.source_name == "coingecko"
        assert metrics.symbol is None
        assert metrics.metrics["btc_dominance"] == 45.2
        assert metrics.is_stale is False
        assert metrics.error_message is None

    def test_create_symbol_metrics(self) -> None:
        """Test creating ExternalMetrics for symbol-specific data."""
        metrics = ExternalMetrics(
            source_name="lunarcrush",
            symbol="BTC_USDT",
            metrics={
                "sentiment_score": 0.75,
                "mention_count": 12500,
                "buzz_score": 0.82,
            },
            is_stale=False,
            error_message=None,
        )

        assert metrics.source_name == "lunarcrush"
        assert metrics.symbol == "BTC_USDT"
        assert metrics.metrics["sentiment_score"] == 0.75
        assert metrics.metrics["mention_count"] == 12500
        assert metrics.is_stale is False

    def test_create_stale_metrics(self) -> None:
        """Test creating ExternalMetrics with stale data."""
        metrics = ExternalMetrics(
            source_name="glassnode",
            symbol="BTC_USDT",
            metrics={
                "active_addresses": None,
                "exchange_flow": None,
            },
            is_stale=True,
            error_message="API timeout after 30 seconds",
        )

        assert metrics.is_stale is True
        assert metrics.error_message == "API timeout after 30 seconds"
        assert metrics.metrics["active_addresses"] is None

    def test_metrics_immutable(self) -> None:
        """Test that ExternalMetrics is immutable (frozen)."""
        metrics = ExternalMetrics(
            source_name="test",
            symbol=None,
            metrics={},
            is_stale=False,
            error_message=None,
        )

        with pytest.raises(AttributeError):
            metrics.source_name = "modified"  # type: ignore[misc]

    def test_metrics_with_mixed_types(self) -> None:
        """Test ExternalMetrics with mixed value types."""
        metrics = ExternalMetrics(
            source_name="mixed",
            symbol="ETH_USDT",
            metrics={
                "float_value": 123.45,
                "int_value": 1000,
                "none_value": None,
            },
            is_stale=False,
            error_message=None,
        )

        assert isinstance(metrics.metrics["float_value"], float)
        assert isinstance(metrics.metrics["int_value"], int)
        assert metrics.metrics["none_value"] is None


class TestExternalSourceClientProtocol:
    """Test ExternalSourceClient protocol."""

    def test_protocol_implementation(self) -> None:
        """Test that a class can implement the ExternalSourceClient protocol."""

        class MockClient:
            """Mock implementation of ExternalSourceClient."""

            async def fetch(self, symbols: list[str]) -> list[ExternalMetrics]:
                """Mock fetch implementation."""
                return [
                    ExternalMetrics(
                        source_name="mock",
                        symbol=symbol,
                        metrics={"test_metric": 42.0},
                        is_stale=False,
                        error_message=None,
                    )
                    for symbol in symbols
                ]

            async def close(self) -> None:
                """Mock close implementation."""
                pass

        # Verify the mock client satisfies the protocol
        client: ExternalSourceClient = MockClient()
        assert hasattr(client, "fetch")
        assert hasattr(client, "close")

    @pytest.mark.asyncio
    async def test_protocol_usage(self) -> None:
        """Test using a protocol implementation."""

        class TestClient:
            """Test implementation of ExternalSourceClient."""

            def __init__(self) -> None:
                self.closed = False

            async def fetch(self, symbols: list[str]) -> list[ExternalMetrics]:
                """Test fetch implementation."""
                return [
                    ExternalMetrics(
                        source_name="test",
                        symbol=symbol,
                        metrics={"value": 100.0},
                        is_stale=False,
                        error_message=None,
                    )
                    for symbol in symbols
                ]

            async def close(self) -> None:
                """Test close implementation."""
                self.closed = True

        client = TestClient()
        results = await client.fetch(["BTC_USDT", "ETH_USDT"])

        assert len(results) == 2
        assert results[0].symbol == "BTC_USDT"
        assert results[1].symbol == "ETH_USDT"
        assert all(m.source_name == "test" for m in results)

        await client.close()
        assert client.closed is True
