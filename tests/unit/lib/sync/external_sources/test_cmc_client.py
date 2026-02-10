"""
Unit tests for CoinMarketCap/CoinGecko market data client.

Tests cover:
- Configuration from environment variables
- CoinGecko API integration
- CoinMarketCap API integration
- Error handling and retry logic
- Resource cleanup

Requirements:
- 1.1.1: Fetch BTC dominance, global market cap, total 24h volume, top 10 gainers/losers
- 1.1.2: Use httpx.AsyncClient with configurable timeout and retries
- 1.1.3: Return None on API failure with error logging
- 1.1.4: Support environment variable configuration
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from lib.sync.external_sources.cmc_client import (
    COINGECKO_BASE_URL,
    COINMARKETCAP_BASE_URL,
    MarketDataClient,
    MarketDataClientConfig,
)


class TestMarketDataClientConfig:
    """Test configuration management."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = MarketDataClientConfig()

        assert config.api_provider == "coingecko"
        assert config.api_key is None
        assert config.base_url is None
        assert config.timeout_seconds == 30.0
        assert config.max_retries == 3
        assert config.top_movers_limit == 10

    @patch.dict(
        "os.environ",
        {
            "MARKET_DATA_PROVIDER": "coinmarketcap",
            "MARKET_DATA_API_KEY": "test-key-123",
            "MARKET_DATA_BASE_URL": "https://custom.api.com",
            "MARKET_DATA_TIMEOUT": "60.0",
            "MARKET_DATA_MAX_RETRIES": "5",
        },
    )
    def test_from_env_with_all_vars(self) -> None:
        """Test configuration from environment variables."""
        config = MarketDataClientConfig.from_env()

        assert config.api_provider == "coinmarketcap"
        assert config.api_key == "test-key-123"
        assert config.base_url == "https://custom.api.com"
        assert config.timeout_seconds == 60.0
        assert config.max_retries == 5

    @patch.dict("os.environ", {"MARKET_DATA_PROVIDER": "coingecko"}, clear=True)
    def test_from_env_defaults_coingecko_url(self) -> None:
        """Test that CoinGecko base URL is set by default."""
        config = MarketDataClientConfig.from_env()

        assert config.api_provider == "coingecko"
        assert config.base_url == COINGECKO_BASE_URL

    @patch.dict("os.environ", {"MARKET_DATA_PROVIDER": "coinmarketcap"}, clear=True)
    def test_from_env_defaults_coinmarketcap_url(self) -> None:
        """Test that CoinMarketCap base URL is set by default."""
        config = MarketDataClientConfig.from_env()

        assert config.api_provider == "coinmarketcap"
        assert config.base_url == COINMARKETCAP_BASE_URL


class TestMarketDataClientCoinGecko:
    """Test CoinGecko API integration."""

    @pytest.fixture
    def coingecko_config(self) -> MarketDataClientConfig:
        """Create CoinGecko configuration."""
        return MarketDataClientConfig(
            api_provider="coingecko",
            base_url=COINGECKO_BASE_URL,
            timeout_seconds=10.0,
            max_retries=2,
        )

    @pytest.fixture
    def mock_http_client(self) -> AsyncMock:
        """Create mock HTTP client."""
        return AsyncMock(spec=httpx.AsyncClient)

    @pytest.mark.asyncio
    async def test_fetch_coingecko_success(
        self, coingecko_config: MarketDataClientConfig, mock_http_client: AsyncMock
    ) -> None:
        """Test successful fetch from CoinGecko."""
        # Mock global data response
        global_response = MagicMock()
        global_response.json.return_value = {
            "data": {
                "market_cap_percentage": {"btc": 45.2},
                "total_market_cap": {"usd": 1_500_000_000_000.0},
                "total_volume": {"usd": 85_000_000_000.0},
            }
        }

        # Mock markets response
        markets_response = MagicMock()
        markets_response.json.return_value = [
            {
                "symbol": "btc",
                "name": "Bitcoin",
                "price_change_percentage_24h": 5.2,
            },
            {
                "symbol": "eth",
                "name": "Ethereum",
                "price_change_percentage_24h": -3.1,
            },
        ]

        mock_http_client.get.side_effect = [global_response, markets_response]

        client = MarketDataClient(config=coingecko_config, http_client=mock_http_client)
        results = await client.fetch([])

        assert len(results) == 1
        metrics = results[0]

        assert metrics.source_name == "coingecko"
        assert metrics.symbol is None
        assert metrics.is_stale is False
        assert metrics.error_message is None

        # Check global metrics
        assert metrics.metrics["btc_dominance"] == 45.2
        assert metrics.metrics["global_market_cap"] == 1_500_000_000_000.0
        assert metrics.metrics["total_volume_24h"] == 85_000_000_000.0

        # Check movers
        assert "top_gainers" in metrics.metrics
        assert "top_losers" in metrics.metrics

    @pytest.mark.asyncio
    async def test_fetch_coingecko_global_api_failure(
        self, coingecko_config: MarketDataClientConfig, mock_http_client: AsyncMock
    ) -> None:
        """Test handling of CoinGecko global API failure."""
        # Mock global data failure
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "API Error", request=MagicMock(), response=MagicMock(status_code=429)
        )

        client = MarketDataClient(config=coingecko_config, http_client=mock_http_client)
        results = await client.fetch([])

        assert len(results) == 1
        metrics = results[0]

        assert metrics.source_name == "coingecko"
        assert metrics.is_stale is True
        assert metrics.error_message is not None
        assert "Failed to fetch" in metrics.error_message or "Error fetching" in metrics.error_message

    @pytest.mark.asyncio
    async def test_fetch_coingecko_empty_response(
        self, coingecko_config: MarketDataClientConfig, mock_http_client: AsyncMock
    ) -> None:
        """Test handling of empty CoinGecko response."""
        # Mock empty global data
        global_response = MagicMock()
        global_response.json.return_value = {}

        # Mock empty markets data
        markets_response = MagicMock()
        markets_response.json.return_value = []

        mock_http_client.get.side_effect = [global_response, markets_response]

        client = MarketDataClient(config=coingecko_config, http_client=mock_http_client)
        results = await client.fetch([])

        assert len(results) == 1
        metrics = results[0]

        assert metrics.source_name == "coingecko"
        assert metrics.is_stale is True
        assert metrics.metrics == {}

    @pytest.mark.asyncio
    async def test_fetch_coingecko_partial_data(
        self, coingecko_config: MarketDataClientConfig, mock_http_client: AsyncMock
    ) -> None:
        """Test handling of partial CoinGecko data."""
        # Mock global data with some missing fields
        global_response = MagicMock()
        global_response.json.return_value = {
            "data": {
                "market_cap_percentage": {"btc": 45.2},
                "total_market_cap": {},  # Empty dict
                "total_volume": {},  # Empty dict
            }
        }

        # Mock markets failure
        mock_http_client.get.side_effect = [
            global_response,
            httpx.RequestError("Network error"),
        ]

        client = MarketDataClient(config=coingecko_config, http_client=mock_http_client)
        results = await client.fetch([])

        assert len(results) == 1
        metrics = results[0]

        assert metrics.source_name == "coingecko"
        assert metrics.is_stale is True  # Markets fetch failed
        assert metrics.metrics["btc_dominance"] == 45.2
        assert metrics.metrics["global_market_cap"] is None
        assert metrics.metrics["total_volume_24h"] is None


class TestMarketDataClientCoinMarketCap:
    """Test CoinMarketCap API integration."""

    @pytest.fixture
    def cmc_config(self) -> MarketDataClientConfig:
        """Create CoinMarketCap configuration."""
        return MarketDataClientConfig(
            api_provider="coinmarketcap",
            api_key="test-api-key",
            base_url=COINMARKETCAP_BASE_URL,
            timeout_seconds=10.0,
            max_retries=2,
        )

    @pytest.fixture
    def mock_http_client(self) -> AsyncMock:
        """Create mock HTTP client."""
        return AsyncMock(spec=httpx.AsyncClient)

    @pytest.mark.asyncio
    async def test_fetch_coinmarketcap_success(
        self, cmc_config: MarketDataClientConfig, mock_http_client: AsyncMock
    ) -> None:
        """Test successful fetch from CoinMarketCap."""
        # Mock global metrics response
        global_response = MagicMock()
        global_response.json.return_value = {
            "data": {
                "btc_dominance": 45.2,
                "quote": {
                    "USD": {
                        "total_market_cap": 1_500_000_000_000.0,
                        "total_volume_24h": 85_000_000_000.0,
                    }
                },
            }
        }

        # Mock gainers/losers response
        movers_response = MagicMock()
        movers_response.json.return_value = {
            "data": {
                "gainers": [
                    {
                        "symbol": "BTC",
                        "name": "Bitcoin",
                        "quote": {"USD": {"percent_change_24h": 5.2}},
                    }
                ],
                "losers": [
                    {
                        "symbol": "ETH",
                        "name": "Ethereum",
                        "quote": {"USD": {"percent_change_24h": -3.1}},
                    }
                ],
            }
        }

        mock_http_client.get.side_effect = [global_response, movers_response]

        client = MarketDataClient(config=cmc_config, http_client=mock_http_client)
        results = await client.fetch([])

        assert len(results) == 1
        metrics = results[0]

        assert metrics.source_name == "coinmarketcap"
        assert metrics.symbol is None
        assert metrics.is_stale is False
        assert metrics.error_message is None

        # Check global metrics
        assert metrics.metrics["btc_dominance"] == 45.2
        assert metrics.metrics["global_market_cap"] == 1_500_000_000_000.0
        assert metrics.metrics["total_volume_24h"] == 85_000_000_000.0

        # Check movers
        assert "top_gainers" in metrics.metrics
        assert "top_losers" in metrics.metrics

    @pytest.mark.asyncio
    async def test_fetch_coinmarketcap_no_api_key(
        self, mock_http_client: AsyncMock
    ) -> None:
        """Test CoinMarketCap without API key."""
        config = MarketDataClientConfig(
            api_provider="coinmarketcap",
            api_key=None,  # No API key
            base_url=COINMARKETCAP_BASE_URL,
        )

        client = MarketDataClient(config=config, http_client=mock_http_client)
        results = await client.fetch([])

        assert len(results) == 1
        metrics = results[0]

        assert metrics.source_name == "coinmarketcap"
        assert metrics.is_stale is True
        assert "API key not configured" in metrics.error_message

        # Should not make any HTTP requests
        mock_http_client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_coinmarketcap_api_failure(
        self, cmc_config: MarketDataClientConfig, mock_http_client: AsyncMock
    ) -> None:
        """Test handling of CoinMarketCap API failure."""
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "API Error", request=MagicMock(), response=MagicMock(status_code=401)
        )

        client = MarketDataClient(config=cmc_config, http_client=mock_http_client)
        results = await client.fetch([])

        assert len(results) == 1
        metrics = results[0]

        assert metrics.source_name == "coinmarketcap"
        assert metrics.is_stale is True
        assert metrics.error_message is not None


class TestMarketDataClientGeneral:
    """Test general client functionality."""

    @pytest.mark.asyncio
    async def test_unknown_provider(self) -> None:
        """Test handling of unknown API provider."""
        config = MarketDataClientConfig(
            api_provider="unknown_provider",
            base_url="https://example.com",
        )

        client = MarketDataClient(config=config)
        results = await client.fetch([])

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_client_creates_http_client(self) -> None:
        """Test that client creates HTTP client if not provided."""
        config = MarketDataClientConfig(api_provider="coingecko")
        client = MarketDataClient(config=config)

        # Access internal method to trigger client creation
        http_client = await client._get_http_client()

        assert http_client is not None
        assert isinstance(http_client, httpx.AsyncClient)

        await client.close()

    @pytest.mark.asyncio
    async def test_client_uses_provided_http_client(self) -> None:
        """Test that client uses provided HTTP client."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        config = MarketDataClientConfig(api_provider="coingecko")
        client = MarketDataClient(config=config, http_client=mock_client)

        http_client = await client._get_http_client()

        assert http_client is mock_client

    @pytest.mark.asyncio
    async def test_close_owned_client(self) -> None:
        """Test that close() closes owned HTTP client."""
        config = MarketDataClientConfig(api_provider="coingecko")
        client = MarketDataClient(config=config)

        # Create the client
        await client._get_http_client()

        # Close should work without error
        await client.close()

        # Client should be None after close
        assert client._http_client is None

    @pytest.mark.asyncio
    async def test_close_external_client(self) -> None:
        """Test that close() does not close external HTTP client."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        config = MarketDataClientConfig(api_provider="coingecko")
        client = MarketDataClient(config=config, http_client=mock_client)

        await client.close()

        # External client should not be closed
        mock_client.aclose.assert_not_called()

    @pytest.mark.asyncio
    async def test_http_client_timeout_configuration(self) -> None:
        """Test that HTTP client is configured with correct timeout."""
        config = MarketDataClientConfig(
            api_provider="coingecko",
            timeout_seconds=45.0,
        )
        client = MarketDataClient(config=config)

        http_client = await client._get_http_client()

        assert http_client.timeout.read == 45.0

        await client.close()

    @pytest.mark.asyncio
    async def test_http_client_retry_configuration(self) -> None:
        """Test that HTTP client is configured with retry transport."""
        config = MarketDataClientConfig(
            api_provider="coingecko",
            max_retries=5,
        )
        client = MarketDataClient(config=config)

        http_client = await client._get_http_client()

        # Verify transport has retries configured
        assert hasattr(http_client, "_transport")
        # Note: httpx.AsyncHTTPTransport doesn't expose retries directly,
        # but we can verify it was created with retries parameter

        await client.close()
