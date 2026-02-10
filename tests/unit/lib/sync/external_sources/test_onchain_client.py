"""
Unit tests for on-chain metrics client.

Tests cover:
- Configuration from environment variables
- Glassnode API integration
- IntoTheBlock API integration
- Error handling and retry logic
- Resource cleanup

Requirements:
- 1.2.1: Async client class for on-chain metrics
- 1.2.2: Fetch active addresses, exchange flow, whale transactions, DeFi TVL
- 1.2.3: Return typed dataclass with float | None fields and fetched_at timestamp
- 1.2.4: Return None on API failure with error logging
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from lib.sync.external_sources.onchain_client import (
    GLASSNODE_BASE_URL,
    INTOTHEBLOCK_BASE_URL,
    OnChainClient,
    OnChainClientConfig,
)


class TestOnChainClientConfig:
    """Test configuration management."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = OnChainClientConfig()

        assert config.api_provider == "glassnode"
        assert config.api_key is None
        assert config.base_url is None
        assert config.timeout_seconds == 30.0
        assert config.max_retries == 3

    @patch.dict(
        "os.environ",
        {
            "ONCHAIN_PROVIDER": "intotheblock",
            "ONCHAIN_API_KEY": "test-key-123",
            "ONCHAIN_BASE_URL": "https://custom.api.com",
            "ONCHAIN_TIMEOUT": "60.0",
            "ONCHAIN_MAX_RETRIES": "5",
        },
    )
    def test_from_env_with_all_vars(self) -> None:
        """Test configuration from environment variables."""
        config = OnChainClientConfig.from_env()

        assert config.api_provider == "intotheblock"
        assert config.api_key == "test-key-123"
        assert config.base_url == "https://custom.api.com"
        assert config.timeout_seconds == 60.0
        assert config.max_retries == 5

    @patch.dict("os.environ", {"ONCHAIN_PROVIDER": "glassnode"}, clear=True)
    def test_from_env_defaults_glassnode_url(self) -> None:
        """Test that Glassnode base URL is set by default."""
        config = OnChainClientConfig.from_env()

        assert config.api_provider == "glassnode"
        assert config.base_url == GLASSNODE_BASE_URL

    @patch.dict("os.environ", {"ONCHAIN_PROVIDER": "intotheblock"}, clear=True)
    def test_from_env_defaults_intotheblock_url(self) -> None:
        """Test that IntoTheBlock base URL is set by default."""
        config = OnChainClientConfig.from_env()

        assert config.api_provider == "intotheblock"
        assert config.base_url == INTOTHEBLOCK_BASE_URL


class TestOnChainClientGlassnode:
    """Test Glassnode API integration."""

    @pytest.fixture
    def glassnode_config(self) -> OnChainClientConfig:
        """Create Glassnode configuration."""
        return OnChainClientConfig(
            api_provider="glassnode",
            api_key="test-api-key",
            base_url=GLASSNODE_BASE_URL,
            timeout_seconds=10.0,
            max_retries=2,
        )

    @pytest.fixture
    def mock_http_client(self) -> AsyncMock:
        """Create mock HTTP client."""
        return AsyncMock(spec=httpx.AsyncClient)

    @pytest.mark.asyncio
    async def test_fetch_glassnode_success(
        self, glassnode_config: OnChainClientConfig, mock_http_client: AsyncMock
    ) -> None:
        """Test successful fetch from Glassnode."""
        # Mock responses for different metrics
        active_addresses_response = MagicMock()
        active_addresses_response.json.return_value = [
            {"t": 1234567890, "v": 950000}
        ]

        exchange_flow_response = MagicMock()
        exchange_flow_response.json.return_value = [
            {"t": 1234567890, "v": -5000.5}
        ]

        whale_count_response = MagicMock()
        whale_count_response.json.return_value = [
            {"t": 1234567890, "v": 42}
        ]

        mock_http_client.get.side_effect = [
            active_addresses_response,
            exchange_flow_response,
            whale_count_response,
        ]

        client = OnChainClient(config=glassnode_config, http_client=mock_http_client)
        results = await client.fetch(["BTC"])

        assert len(results) == 1
        metrics = results[0]

        assert metrics.source_name == "glassnode"
        assert metrics.symbol == "BTC"
        assert metrics.is_stale is False
        assert metrics.error_message is None

        # Check on-chain metrics
        assert metrics.metrics["active_addresses"] == 950000.0
        assert metrics.metrics["net_exchange_flow"] == -5000.5
        assert metrics.metrics["whale_tx_count"] == 42.0
        assert "fetched_at" in metrics.metrics

    @pytest.mark.asyncio
    async def test_fetch_glassnode_eth_with_defi_tvl(
        self, glassnode_config: OnChainClientConfig, mock_http_client: AsyncMock
    ) -> None:
        """Test Glassnode fetch for ETH includes DeFi TVL."""
        # Mock responses for ETH metrics including DeFi TVL
        active_addresses_response = MagicMock()
        active_addresses_response.json.return_value = [
            {"t": 1234567890, "v": 500000}
        ]

        exchange_flow_response = MagicMock()
        exchange_flow_response.json.return_value = [
            {"t": 1234567890, "v": 1000.0}
        ]

        whale_count_response = MagicMock()
        whale_count_response.json.return_value = [
            {"t": 1234567890, "v": 25}
        ]

        defi_tvl_response = MagicMock()
        defi_tvl_response.json.return_value = [
            {"t": 1234567890, "v": 50000000000.0}
        ]

        mock_http_client.get.side_effect = [
            active_addresses_response,
            exchange_flow_response,
            whale_count_response,
            defi_tvl_response,
        ]

        client = OnChainClient(config=glassnode_config, http_client=mock_http_client)
        results = await client.fetch(["ETH"])

        assert len(results) == 1
        metrics = results[0]

        assert metrics.source_name == "glassnode"
        assert metrics.symbol == "ETH"
        assert metrics.is_stale is False

        # Check DeFi TVL is included for ETH
        assert "defi_tvl" in metrics.metrics
        assert metrics.metrics["defi_tvl"] == 50000000000.0

    @pytest.mark.asyncio
    async def test_fetch_glassnode_no_api_key(
        self, mock_http_client: AsyncMock
    ) -> None:
        """Test Glassnode without API key."""
        config = OnChainClientConfig(
            api_provider="glassnode",
            api_key=None,  # No API key
            base_url=GLASSNODE_BASE_URL,
        )

        client = OnChainClient(config=config, http_client=mock_http_client)
        results = await client.fetch(["BTC"])

        assert len(results) == 1
        metrics = results[0]

        assert metrics.source_name == "glassnode"
        assert metrics.is_stale is True
        assert "API key not configured" in metrics.error_message

        # Should not make any HTTP requests
        mock_http_client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_glassnode_api_failure(
        self, glassnode_config: OnChainClientConfig, mock_http_client: AsyncMock
    ) -> None:
        """Test handling of Glassnode API failure."""
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "API Error", request=MagicMock(), response=MagicMock(status_code=429)
        )

        client = OnChainClient(config=glassnode_config, http_client=mock_http_client)
        results = await client.fetch(["BTC"])

        assert len(results) == 1
        metrics = results[0]

        assert metrics.source_name == "glassnode"
        assert metrics.is_stale is True
        assert metrics.error_message is not None

    @pytest.mark.asyncio
    async def test_fetch_glassnode_empty_response(
        self, glassnode_config: OnChainClientConfig, mock_http_client: AsyncMock
    ) -> None:
        """Test handling of empty Glassnode response."""
        # Mock empty responses
        empty_response = MagicMock()
        empty_response.json.return_value = []

        mock_http_client.get.side_effect = [
            empty_response,
            empty_response,
            empty_response,
        ]

        client = OnChainClient(config=glassnode_config, http_client=mock_http_client)
        results = await client.fetch(["BTC"])

        assert len(results) == 1
        metrics = results[0]

        assert metrics.source_name == "glassnode"
        assert metrics.is_stale is True
        # Metrics should be empty or have None values
        assert "active_addresses" not in metrics.metrics or metrics.metrics["active_addresses"] is None

    @pytest.mark.asyncio
    async def test_fetch_glassnode_partial_data(
        self, glassnode_config: OnChainClientConfig, mock_http_client: AsyncMock
    ) -> None:
        """Test handling of partial Glassnode data."""
        # Mock successful response for active addresses
        active_addresses_response = MagicMock()
        active_addresses_response.json.return_value = [
            {"t": 1234567890, "v": 950000}
        ]

        # Mock failures for other metrics
        mock_http_client.get.side_effect = [
            active_addresses_response,
            httpx.RequestError("Network error"),
            httpx.RequestError("Network error"),
        ]

        client = OnChainClient(config=glassnode_config, http_client=mock_http_client)
        results = await client.fetch(["BTC"])

        assert len(results) == 1
        metrics = results[0]

        assert metrics.source_name == "glassnode"
        assert metrics.is_stale is True  # Some metrics failed
        assert metrics.metrics["active_addresses"] == 950000.0
        # Other metrics should not be present or be None

    @pytest.mark.asyncio
    async def test_fetch_glassnode_multiple_symbols(
        self, glassnode_config: OnChainClientConfig, mock_http_client: AsyncMock
    ) -> None:
        """Test fetching data for multiple symbols."""
        # Mock responses for BTC
        btc_responses = [
            MagicMock(json=lambda: [{"t": 1234567890, "v": 950000}]),
            MagicMock(json=lambda: [{"t": 1234567890, "v": -5000.5}]),
            MagicMock(json=lambda: [{"t": 1234567890, "v": 42}]),
        ]

        # Mock responses for ETH
        eth_responses = [
            MagicMock(json=lambda: [{"t": 1234567890, "v": 500000}]),
            MagicMock(json=lambda: [{"t": 1234567890, "v": 1000.0}]),
            MagicMock(json=lambda: [{"t": 1234567890, "v": 25}]),
            MagicMock(json=lambda: [{"t": 1234567890, "v": 50000000000.0}]),
        ]

        mock_http_client.get.side_effect = btc_responses + eth_responses

        client = OnChainClient(config=glassnode_config, http_client=mock_http_client)
        results = await client.fetch(["BTC", "ETH"])

        assert len(results) == 2

        # Check BTC metrics
        btc_metrics = results[0]
        assert btc_metrics.symbol == "BTC"
        assert btc_metrics.is_stale is False

        # Check ETH metrics
        eth_metrics = results[1]
        assert eth_metrics.symbol == "ETH"
        assert eth_metrics.is_stale is False
        assert "defi_tvl" in eth_metrics.metrics


class TestOnChainClientIntoTheBlock:
    """Test IntoTheBlock API integration."""

    @pytest.fixture
    def intotheblock_config(self) -> OnChainClientConfig:
        """Create IntoTheBlock configuration."""
        return OnChainClientConfig(
            api_provider="intotheblock",
            api_key="test-api-key",
            base_url=INTOTHEBLOCK_BASE_URL,
            timeout_seconds=10.0,
            max_retries=2,
        )

    @pytest.fixture
    def mock_http_client(self) -> AsyncMock:
        """Create mock HTTP client."""
        return AsyncMock(spec=httpx.AsyncClient)

    @pytest.mark.asyncio
    async def test_fetch_intotheblock_success(
        self, intotheblock_config: OnChainClientConfig, mock_http_client: AsyncMock
    ) -> None:
        """Test successful fetch from IntoTheBlock."""
        # Mock responses for different metrics
        active_addresses_response = MagicMock()
        active_addresses_response.json.return_value = {
            "data": {"count": 850000}
        }

        exchange_flow_response = MagicMock()
        exchange_flow_response.json.return_value = {
            "data": {"inflow": 10000.0, "outflow": 15000.0}
        }

        whale_count_response = MagicMock()
        whale_count_response.json.return_value = {
            "data": {"count": 38}
        }

        mock_http_client.get.side_effect = [
            active_addresses_response,
            exchange_flow_response,
            whale_count_response,
        ]

        client = OnChainClient(config=intotheblock_config, http_client=mock_http_client)
        results = await client.fetch(["BTC"])

        assert len(results) == 1
        metrics = results[0]

        assert metrics.source_name == "intotheblock"
        assert metrics.symbol == "BTC"
        assert metrics.is_stale is False
        assert metrics.error_message is None

        # Check on-chain metrics
        assert metrics.metrics["active_addresses"] == 850000.0
        assert metrics.metrics["net_exchange_flow"] == -5000.0  # 10000 - 15000
        assert metrics.metrics["whale_tx_count"] == 38.0
        assert "fetched_at" in metrics.metrics

    @pytest.mark.asyncio
    async def test_fetch_intotheblock_eth_with_defi_tvl(
        self, intotheblock_config: OnChainClientConfig, mock_http_client: AsyncMock
    ) -> None:
        """Test IntoTheBlock fetch for ETH includes DeFi TVL."""
        # Mock responses for ETH metrics including DeFi TVL
        active_addresses_response = MagicMock()
        active_addresses_response.json.return_value = {
            "data": {"count": 450000}
        }

        exchange_flow_response = MagicMock()
        exchange_flow_response.json.return_value = {
            "data": {"inflow": 5000.0, "outflow": 4000.0}
        }

        whale_count_response = MagicMock()
        whale_count_response.json.return_value = {
            "data": {"count": 20}
        }

        defi_tvl_response = MagicMock()
        defi_tvl_response.json.return_value = {
            "data": {"total_value_locked": 45000000000.0}
        }

        mock_http_client.get.side_effect = [
            active_addresses_response,
            exchange_flow_response,
            whale_count_response,
            defi_tvl_response,
        ]

        client = OnChainClient(config=intotheblock_config, http_client=mock_http_client)
        results = await client.fetch(["eth"])

        assert len(results) == 1
        metrics = results[0]

        assert metrics.source_name == "intotheblock"
        assert metrics.symbol == "eth"
        assert metrics.is_stale is False

        # Check DeFi TVL is included for ETH
        assert "defi_tvl" in metrics.metrics
        assert metrics.metrics["defi_tvl"] == 45000000000.0

    @pytest.mark.asyncio
    async def test_fetch_intotheblock_no_api_key(
        self, mock_http_client: AsyncMock
    ) -> None:
        """Test IntoTheBlock without API key."""
        config = OnChainClientConfig(
            api_provider="intotheblock",
            api_key=None,  # No API key
            base_url=INTOTHEBLOCK_BASE_URL,
        )

        client = OnChainClient(config=config, http_client=mock_http_client)
        results = await client.fetch(["BTC"])

        assert len(results) == 1
        metrics = results[0]

        assert metrics.source_name == "intotheblock"
        assert metrics.is_stale is True
        assert "API key not configured" in metrics.error_message

        # Should not make any HTTP requests
        mock_http_client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_intotheblock_api_failure(
        self, intotheblock_config: OnChainClientConfig, mock_http_client: AsyncMock
    ) -> None:
        """Test handling of IntoTheBlock API failure."""
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "API Error", request=MagicMock(), response=MagicMock(status_code=401)
        )

        client = OnChainClient(config=intotheblock_config, http_client=mock_http_client)
        results = await client.fetch(["BTC"])

        assert len(results) == 1
        metrics = results[0]

        assert metrics.source_name == "intotheblock"
        assert metrics.is_stale is True
        assert metrics.error_message is not None

    @pytest.mark.asyncio
    async def test_fetch_intotheblock_empty_response(
        self, intotheblock_config: OnChainClientConfig, mock_http_client: AsyncMock
    ) -> None:
        """Test handling of empty IntoTheBlock response."""
        # Mock empty responses
        empty_response = MagicMock()
        empty_response.json.return_value = {}

        mock_http_client.get.side_effect = [
            empty_response,
            empty_response,
            empty_response,
        ]

        client = OnChainClient(config=intotheblock_config, http_client=mock_http_client)
        results = await client.fetch(["BTC"])

        assert len(results) == 1
        metrics = results[0]

        assert metrics.source_name == "intotheblock"
        assert metrics.is_stale is True


class TestOnChainClientGeneral:
    """Test general client functionality."""

    @pytest.mark.asyncio
    async def test_unknown_provider(self) -> None:
        """Test handling of unknown API provider."""
        config = OnChainClientConfig(
            api_provider="unknown_provider",
            base_url="https://example.com",
        )

        client = OnChainClient(config=config)
        results = await client.fetch(["BTC"])

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_client_creates_http_client(self) -> None:
        """Test that client creates HTTP client if not provided."""
        config = OnChainClientConfig(api_provider="glassnode", api_key="test-key")
        client = OnChainClient(config=config)

        # Access internal method to trigger client creation
        http_client = await client._get_http_client()

        assert http_client is not None
        assert isinstance(http_client, httpx.AsyncClient)

        await client.close()

    @pytest.mark.asyncio
    async def test_client_uses_provided_http_client(self) -> None:
        """Test that client uses provided HTTP client."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        config = OnChainClientConfig(api_provider="glassnode", api_key="test-key")
        client = OnChainClient(config=config, http_client=mock_client)

        http_client = await client._get_http_client()

        assert http_client is mock_client

    @pytest.mark.asyncio
    async def test_close_owned_client(self) -> None:
        """Test that close() closes owned HTTP client."""
        config = OnChainClientConfig(api_provider="glassnode", api_key="test-key")
        client = OnChainClient(config=config)

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
        config = OnChainClientConfig(api_provider="glassnode", api_key="test-key")
        client = OnChainClient(config=config, http_client=mock_client)

        await client.close()

        # External client should not be closed
        mock_client.aclose.assert_not_called()

    @pytest.mark.asyncio
    async def test_http_client_timeout_configuration(self) -> None:
        """Test that HTTP client is configured with correct timeout."""
        config = OnChainClientConfig(
            api_provider="glassnode",
            api_key="test-key",
            timeout_seconds=45.0,
        )
        client = OnChainClient(config=config)

        http_client = await client._get_http_client()

        assert http_client.timeout.read == 45.0

        await client.close()

    @pytest.mark.asyncio
    async def test_symbol_normalization_with_pair(self) -> None:
        """Test that trading pair symbols are normalized correctly."""
        config = OnChainClientConfig(
            api_provider="glassnode",
            api_key="test-key",
        )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = MagicMock()
        mock_response.json.return_value = [{"t": 1234567890, "v": 950000}]
        mock_client.get.return_value = mock_response

        client = OnChainClient(config=config, http_client=mock_client)
        results = await client.fetch(["BTC_USDT"])

        assert len(results) == 1
        assert results[0].symbol == "BTC_USDT"

        # Verify that the API was called with normalized symbol "BTC"
        call_args = mock_client.get.call_args_list[0]
        assert "a=BTC" in str(call_args) or call_args[1]["params"]["a"] == "BTC"
