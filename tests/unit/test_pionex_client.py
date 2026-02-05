"""
Unit tests for Pionex API Client.

Tests the PionexClient class for:
- Market data methods (get_symbols, get_candles, get_depth, get_trades)
- Error handling and structured errors
- Retry logic for transient failures

Requirements:
- 1.2: Retrieve available SPOT and PERP symbols from /api/v1/common/symbols
- 1.5: Retrieve recent trades for a symbol from /api/v1/market/trades
- 1.6: Retrieve bid/ask depth from /api/v1/market/depth
- 1.7: Return structured errors with status code, message, and retry eligibility
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from lib.pionex.client import PionexClient
from lib.pionex.models import (
    Balance,
    CancelOrderResponse,
    Candle,
    OrderBook,
    OrderBookLevel,
    OrderRequest,
    OrderResponse,
    OrderSide,
    OrderStatus,
    OrderType,
    PionexAPIError,
    PionexError,
    Symbol,
    SymbolType,
    TimeInForce,
    Trade,
)

# Sample API responses for mocking
SAMPLE_SYMBOLS_RESPONSE = {
    "result": True,
    "data": {
        "symbols": [
            {
                "symbol": "BTC_USDT",
                "baseCurrency": "BTC",
                "quoteCurrency": "USDT",
                "type": "SPOT",
                "basePrecision": 8,
                "quotePrecision": 2,
                "minAmount": "0.0001",
                "minNotional": "10",
                "enable": True,
            },
            {
                "symbol": "ETH_USDT",
                "baseCurrency": "ETH",
                "quoteCurrency": "USDT",
                "type": "SPOT",
                "basePrecision": 8,
                "quotePrecision": 2,
                "minAmount": "0.001",
                "minNotional": "10",
                "enable": True,
            },
            {
                "symbol": "BTC_USDT_PERP",
                "baseCurrency": "BTC",
                "quoteCurrency": "USDT",
                "type": "PERP",
                "basePrecision": 8,
                "quotePrecision": 2,
                "minAmount": "0.001",
                "minNotional": "5",
                "enable": True,
            },
        ]
    },
}

SAMPLE_CANDLES_RESPONSE = {
    "result": True,
    "data": {
        "klines": [
            {
                "time": 1700000000000,
                "open": "35000.00",
                "high": "35500.00",
                "low": "34800.00",
                "close": "35200.00",
                "volume": "100.5",
            },
            {
                "time": 1700003600000,
                "open": "35200.00",
                "high": "35800.00",
                "low": "35100.00",
                "close": "35600.00",
                "volume": "150.2",
            },
        ]
    },
}

SAMPLE_DEPTH_RESPONSE = {
    "result": True,
    "data": {
        "bids": [
            ["35000.00", "1.5"],
            ["34999.00", "2.0"],
            ["34998.00", "0.8"],
        ],
        "asks": [
            ["35001.00", "1.2"],
            ["35002.00", "1.8"],
            ["35003.00", "2.5"],
        ],
        "timestamp": 1700000000000,
    },
}

SAMPLE_TRADES_RESPONSE = {
    "result": True,
    "data": {
        "trades": [
            {
                "id": "trade_001",
                "price": "35000.00",
                "quantity": "0.5",
                "side": "BUY",
                "timestamp": 1700000000000,
            },
            {
                "id": "trade_002",
                "price": "35001.00",
                "quantity": "0.3",
                "side": "SELL",
                "timestamp": 1700000001000,
            },
        ]
    },
}

SAMPLE_BALANCES_RESPONSE = {
    "result": True,
    "data": {
        "balances": [
            {
                "coin": "BTC",
                "free": "1.5",
                "locked": "0.5",
            },
            {
                "coin": "USDT",
                "free": "10000.00",
                "locked": "500.00",
            },
            {
                "coin": "ETH",
                "free": "5.0",
                "locked": "0",
            },
            {
                "coin": "DOGE",
                "free": "0",
                "locked": "0",
            },
        ]
    },
}

SAMPLE_CREATE_ORDER_RESPONSE = {
    "result": True,
    "data": {
        "orderId": "123456789",
        "clientOrderId": "my-order-001",
        "symbol": "BTC_USDT",
        "side": "BUY",
        "type": "LIMIT",
        "price": "35000.00",
        "amount": "0.001",
        "filledAmount": "0",
        "status": "NEW",
        "timestamp": 1700000000000,
    },
}

SAMPLE_CREATE_MARKET_ORDER_RESPONSE = {
    "result": True,
    "data": {
        "orderId": "123456790",
        "symbol": "BTC_USDT",
        "side": "SELL",
        "type": "MARKET",
        "amount": "0.001",
        "filledAmount": "0.001",
        "status": "FILLED",
        "timestamp": 1700000001000,
    },
}

SAMPLE_CANCEL_ORDER_RESPONSE = {
    "result": True,
    "data": {
        "orderId": "123456789",
        "symbol": "BTC_USDT",
        "status": "CANCELED",
    },
}


class TestPionexClientInit:
    """Tests for PionexClient initialization."""

    def test_init_with_valid_credentials(self) -> None:
        """Test client initializes with valid credentials."""
        client = PionexClient(api_key="test_key", api_secret="test_secret")
        assert client.base_url == "https://api.pionex.com"
        assert client.timeout == 30.0

    def test_init_with_custom_base_url(self) -> None:
        """Test client accepts custom base URL."""
        client = PionexClient(
            api_key="key",
            api_secret="secret",
            base_url="https://custom.api.com/",
        )
        assert client.base_url == "https://custom.api.com"

    def test_init_with_custom_timeout(self) -> None:
        """Test client accepts custom timeout."""
        client = PionexClient(
            api_key="key",
            api_secret="secret",
            timeout=60.0,
        )
        assert client.timeout == 60.0

    def test_init_with_empty_api_key_raises(self) -> None:
        """Test client raises ValueError for empty API key."""
        with pytest.raises(ValueError, match="API key cannot be empty"):
            PionexClient(api_key="", api_secret="secret")

    def test_init_with_empty_api_secret_raises(self) -> None:
        """Test client raises ValueError for empty API secret."""
        with pytest.raises(ValueError, match="API secret cannot be empty"):
            PionexClient(api_key="key", api_secret="")


class TestPionexClientContextManager:
    """Tests for async context manager functionality."""

    @pytest.mark.asyncio
    async def test_context_manager_creates_client(self) -> None:
        """Test context manager creates HTTP client on enter."""
        async with PionexClient(api_key="key", api_secret="secret") as client:
            assert client._client is not None
            assert not client._client.is_closed

    @pytest.mark.asyncio
    async def test_context_manager_closes_client(self) -> None:
        """Test context manager closes HTTP client on exit."""
        client = PionexClient(api_key="key", api_secret="secret")
        async with client:
            http_client = client._client

        assert http_client is not None
        assert http_client.is_closed


class TestPionexError:
    """Tests for PionexError structured error."""

    def test_from_response_with_error_data(self) -> None:
        """Test creating error from API response."""
        response_data = {
            "code": 1001,
            "message": "Invalid symbol",
        }
        error = PionexError.from_response(
            status_code=400,
            response_data=response_data,
        )

        assert error.status_code == 400
        assert error.error_code == 1001
        assert error.message == "Invalid symbol"
        assert error.is_retryable is False

    def test_from_response_rate_limited(self) -> None:
        """Test rate limit error is retryable."""
        error = PionexError.from_response(
            status_code=429,
            response_data={"message": "Rate limited"},
            retry_after=60,
        )

        assert error.status_code == 429
        assert error.is_retryable is True
        assert error.retry_after == 60

    def test_from_response_server_error(self) -> None:
        """Test server error is retryable."""
        error = PionexError.from_response(
            status_code=500,
            response_data={"message": "Internal server error"},
        )

        assert error.status_code == 500
        assert error.is_retryable is True

    def test_from_response_client_error_not_retryable(self) -> None:
        """Test client error (4xx except 429) is not retryable."""
        error = PionexError.from_response(
            status_code=401,
            response_data={"message": "Unauthorized"},
        )

        assert error.status_code == 401
        assert error.is_retryable is False


class TestGetSymbols:
    """Tests for get_symbols method."""

    @pytest.mark.asyncio
    async def test_get_symbols_returns_list(self) -> None:
        """Test get_symbols returns list of Symbol objects."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_SYMBOLS_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            symbols = await client.get_symbols()

        assert isinstance(symbols, list)
        assert len(symbols) == 3
        assert all(isinstance(s, Symbol) for s in symbols)

    @pytest.mark.asyncio
    async def test_get_symbols_parses_spot_symbol(self) -> None:
        """Test SPOT symbol is parsed correctly."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_SYMBOLS_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            symbols = await client.get_symbols()

        btc_symbol = next(s for s in symbols if s.symbol == "BTC_USDT")
        assert btc_symbol.base_currency == "BTC"
        assert btc_symbol.quote_currency == "USDT"
        assert btc_symbol.symbol_type == SymbolType.SPOT
        assert btc_symbol.base_precision == 8
        assert btc_symbol.quote_precision == 2
        assert btc_symbol.min_amount == Decimal("0.0001")
        assert btc_symbol.min_notional == Decimal("10")
        assert btc_symbol.is_active is True

    @pytest.mark.asyncio
    async def test_get_symbols_parses_perp_symbol(self) -> None:
        """Test PERP symbol is parsed correctly."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_SYMBOLS_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            symbols = await client.get_symbols()

        perp_symbol = next(s for s in symbols if s.symbol == "BTC_USDT_PERP")
        assert perp_symbol.symbol_type == SymbolType.PERP


class TestGetCandles:
    """Tests for get_candles method."""

    @pytest.mark.asyncio
    async def test_get_candles_returns_list(self) -> None:
        """Test get_candles returns list of Candle objects."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_CANDLES_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            candles = await client.get_candles("BTC_USDT", "1H")

        assert isinstance(candles, list)
        assert len(candles) == 2
        assert all(isinstance(c, Candle) for c in candles)

    @pytest.mark.asyncio
    async def test_get_candles_parses_ohlcv(self) -> None:
        """Test candle OHLCV data is parsed correctly."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_CANDLES_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            candles = await client.get_candles("BTC_USDT", "1H")

        first_candle = candles[0]
        assert first_candle.open == 35000.00
        assert first_candle.high == 35500.00
        assert first_candle.low == 34800.00
        assert first_candle.close == 35200.00
        assert first_candle.volume == 100.5
        assert first_candle.timestamp == datetime.fromtimestamp(1700000000, tz=UTC)

    @pytest.mark.asyncio
    async def test_get_candles_sorted_by_timestamp(self) -> None:
        """Test candles are sorted by timestamp ascending."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_CANDLES_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            candles = await client.get_candles("BTC_USDT", "1H")

        timestamps = [c.timestamp for c in candles]
        assert timestamps == sorted(timestamps)

    @pytest.mark.asyncio
    async def test_get_candles_with_limit(self) -> None:
        """Test get_candles respects limit parameter."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_CANDLES_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            await client.get_candles("BTC_USDT", "1H", limit=50)

            # Verify limit was passed in params
            call_args = mock_http_client.get.call_args
            assert call_args.kwargs["params"]["limit"] == 50

    @pytest.mark.asyncio
    async def test_get_candles_maps_interval_to_valid_pionex_format(self) -> None:
        """Test that interval is mapped to valid Pionex API format.

        Pionex API supports: 1M, 5M, 15M, 30M, 4H, 8H, 12H, 1D
        Note: 1H and 2H are NOT supported, so they are mapped to closest valid intervals.
        """
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_CANDLES_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            # Test 1H maps to 30M (1H not supported by Pionex)
            await client.get_candles("BTC_USDT", "1H")
            call_args = mock_http_client.get.call_args
            assert call_args.kwargs["params"]["interval"] == "30M"

    @pytest.mark.asyncio
    async def test_get_candles_maps_lowercase_intervals(self) -> None:
        """Test that lowercase intervals are mapped to uppercase Pionex format."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_CANDLES_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            # Test lowercase 4h maps to uppercase 4H
            await client.get_candles("BTC_USDT", "4h")
            call_args = mock_http_client.get.call_args
            assert call_args.kwargs["params"]["interval"] == "4H"

    @pytest.mark.asyncio
    async def test_get_candles_raises_for_invalid_interval(self) -> None:
        """Test that invalid intervals raise ValueError."""
        client = PionexClient(api_key="key", api_secret="secret")

        with pytest.raises(ValueError, match="Invalid interval"):
            await client.get_candles("BTC_USDT", "invalid")


class TestGetDepth:
    """Tests for get_depth method."""

    @pytest.mark.asyncio
    async def test_get_depth_returns_order_book(self) -> None:
        """Test get_depth returns OrderBook object."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_DEPTH_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            depth = await client.get_depth("BTC_USDT")

        assert isinstance(depth, OrderBook)
        assert depth.symbol == "BTC_USDT"

    @pytest.mark.asyncio
    async def test_get_depth_parses_bids(self) -> None:
        """Test bid levels are parsed correctly."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_DEPTH_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            depth = await client.get_depth("BTC_USDT")

        assert len(depth.bids) == 3
        assert all(isinstance(b, OrderBookLevel) for b in depth.bids)

        first_bid = depth.bids[0]
        assert first_bid.price == Decimal("35000.00")
        assert first_bid.quantity == Decimal("1.5")

    @pytest.mark.asyncio
    async def test_get_depth_parses_asks(self) -> None:
        """Test ask levels are parsed correctly."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_DEPTH_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            depth = await client.get_depth("BTC_USDT")

        assert len(depth.asks) == 3
        assert all(isinstance(a, OrderBookLevel) for a in depth.asks)

        first_ask = depth.asks[0]
        assert first_ask.price == Decimal("35001.00")
        assert first_ask.quantity == Decimal("1.2")

    @pytest.mark.asyncio
    async def test_get_depth_includes_timestamp(self) -> None:
        """Test order book includes timestamp."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_DEPTH_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            depth = await client.get_depth("BTC_USDT")

        assert depth.timestamp == datetime.fromtimestamp(1700000000, tz=UTC)


class TestGetTrades:
    """Tests for get_trades method."""

    @pytest.mark.asyncio
    async def test_get_trades_returns_list(self) -> None:
        """Test get_trades returns list of Trade objects."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_TRADES_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            trades = await client.get_trades("BTC_USDT")

        assert isinstance(trades, list)
        assert len(trades) == 2
        assert all(isinstance(t, Trade) for t in trades)

    @pytest.mark.asyncio
    async def test_get_trades_parses_trade_data(self) -> None:
        """Test trade data is parsed correctly."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_TRADES_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            trades = await client.get_trades("BTC_USDT")

        # Trades are sorted by timestamp descending, so trade_002 is first
        first_trade = trades[0]
        assert first_trade.trade_id == "trade_002"
        assert first_trade.symbol == "BTC_USDT"
        assert first_trade.price == Decimal("35001.00")
        assert first_trade.quantity == Decimal("0.3")
        assert first_trade.side == OrderSide.SELL

    @pytest.mark.asyncio
    async def test_get_trades_parses_buy_side(self) -> None:
        """Test BUY side is parsed correctly."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_TRADES_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            trades = await client.get_trades("BTC_USDT")

        buy_trade = next(t for t in trades if t.trade_id == "trade_001")
        assert buy_trade.side == OrderSide.BUY

    @pytest.mark.asyncio
    async def test_get_trades_sorted_by_timestamp_descending(self) -> None:
        """Test trades are sorted by timestamp descending."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_TRADES_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            trades = await client.get_trades("BTC_USDT")

        timestamps = [t.timestamp for t in trades]
        assert timestamps == sorted(timestamps, reverse=True)


class TestErrorHandling:
    """Tests for error handling and retry logic."""

    @pytest.mark.asyncio
    async def test_api_error_raises_pionex_api_error(self) -> None:
        """Test API error raises PionexAPIError."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = False
        mock_response.status_code = 400
        mock_response.content = b'{"result": false}'
        mock_response.json.return_value = {
            "result": False,
            "code": 1001,
            "message": "Invalid symbol",
        }
        mock_response.headers = {}

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            with pytest.raises(PionexAPIError) as exc_info:
                await client.get_symbols()

        assert exc_info.value.error.status_code == 400
        assert exc_info.value.error.error_code == 1001
        assert "Invalid symbol" in exc_info.value.error.message

    @pytest.mark.asyncio
    async def test_api_error_result_false_raises(self) -> None:
        """Test API response with result=false raises error."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True  # HTTP 200 but API error
        mock_response.status_code = 200
        mock_response.content = b'{"result": false}'
        mock_response.json.return_value = {
            "result": False,
            "code": 2001,
            "message": "Symbol not found",
        }

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            with pytest.raises(PionexAPIError) as exc_info:
                await client.get_symbols()

        assert exc_info.value.error.error_code == 2001

    @pytest.mark.asyncio
    async def test_timeout_error_is_retryable(self) -> None:
        """Test timeout errors trigger retry."""
        client = PionexClient(api_key="key", api_secret="secret")

        # First call times out, second succeeds
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = {
            "result": True,
            "data": {"symbols": []},
        }

        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.TimeoutException("Connection timeout")
            return mock_response

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = mock_get
            mock_ensure.return_value = mock_http_client

            # Should succeed after retry
            with patch("lib.pionex.client.asyncio.sleep", new_callable=AsyncMock):
                symbols = await client.get_symbols()

        assert call_count == 2
        assert symbols == []

    @pytest.mark.asyncio
    async def test_rate_limit_respects_retry_after(self) -> None:
        """Test rate limit error respects Retry-After header."""
        client = PionexClient(api_key="key", api_secret="secret")

        # First call rate limited, second succeeds
        rate_limited_response = MagicMock()
        rate_limited_response.is_success = False
        rate_limited_response.status_code = 429
        rate_limited_response.content = b'{"message": "Rate limited"}'
        rate_limited_response.json.return_value = {"message": "Rate limited"}
        rate_limited_response.headers = {"Retry-After": "5"}

        success_response = MagicMock()
        success_response.is_success = True
        success_response.content = b'{"result": true}'
        success_response.json.return_value = {
            "result": True,
            "data": {"symbols": []},
        }

        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return rate_limited_response
            return success_response

        sleep_times = []

        async def mock_sleep(seconds):
            sleep_times.append(seconds)

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = mock_get
            mock_ensure.return_value = mock_http_client

            with patch("lib.pionex.client.asyncio.sleep", side_effect=mock_sleep):
                symbols = await client.get_symbols()

        assert call_count == 2
        assert 5 in sleep_times  # Should have waited 5 seconds from Retry-After


class TestGetBalances:
    """Tests for get_balances method.

    Requirements:
        - 1.3: Retrieve all currency balances from /api/v1/account/balance
    """

    @pytest.mark.asyncio
    async def test_get_balances_returns_list(self) -> None:
        """Test get_balances returns list of Balance objects."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_BALANCES_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            balances = await client.get_balances()

        assert isinstance(balances, list)
        # Should have 3 balances (DOGE is skipped because both free and locked are 0)
        assert len(balances) == 3
        assert all(isinstance(b, Balance) for b in balances)

    @pytest.mark.asyncio
    async def test_get_balances_parses_currency_data(self) -> None:
        """Test balance data is parsed correctly."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_BALANCES_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            balances = await client.get_balances()

        btc_balance = next(b for b in balances if b.currency == "BTC")
        assert btc_balance.free == Decimal("1.5")
        assert btc_balance.locked == Decimal("0.5")
        assert btc_balance.total == Decimal("2.0")

    @pytest.mark.asyncio
    async def test_get_balances_parses_usdt(self) -> None:
        """Test USDT balance is parsed correctly."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_BALANCES_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            balances = await client.get_balances()

        usdt_balance = next(b for b in balances if b.currency == "USDT")
        assert usdt_balance.free == Decimal("10000.00")
        assert usdt_balance.locked == Decimal("500.00")
        assert usdt_balance.total == Decimal("10500.00")

    @pytest.mark.asyncio
    async def test_get_balances_skips_zero_balances(self) -> None:
        """Test zero balances are skipped."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_BALANCES_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            balances = await client.get_balances()

        # DOGE has 0 free and 0 locked, should be skipped
        currencies = [b.currency for b in balances]
        assert "DOGE" not in currencies

    @pytest.mark.asyncio
    async def test_get_balances_includes_zero_locked(self) -> None:
        """Test balance with zero locked but non-zero free is included."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_BALANCES_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            balances = await client.get_balances()

        # ETH has 5.0 free and 0 locked, should be included
        eth_balance = next(b for b in balances if b.currency == "ETH")
        assert eth_balance.free == Decimal("5.0")
        assert eth_balance.locked == Decimal("0")

    @pytest.mark.asyncio
    async def test_get_balances_is_authenticated(self) -> None:
        """Test get_balances uses authenticated request."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_BALANCES_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            await client.get_balances()

            # Verify authentication headers were included
            call_args = mock_http_client.get.call_args
            headers = call_args.kwargs.get("headers", {})
            assert "PIONEX-KEY" in headers
            assert "PIONEX-SIGNATURE" in headers

    @pytest.mark.asyncio
    async def test_get_balances_handles_alternative_field_names(self) -> None:
        """Test get_balances handles alternative API field names."""
        client = PionexClient(api_key="key", api_secret="secret")

        # Alternative field names that might be used by the API
        alternative_response = {
            "result": True,
            "data": {
                "balances": [
                    {
                        "currency": "SOL",
                        "available": "10.5",
                        "frozen": "2.5",
                    },
                ]
            },
        }

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = alternative_response

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            balances = await client.get_balances()

        assert len(balances) == 1
        sol_balance = balances[0]
        assert sol_balance.currency == "SOL"
        assert sol_balance.free == Decimal("10.5")
        assert sol_balance.locked == Decimal("2.5")

    @pytest.mark.asyncio
    async def test_get_balances_empty_response(self) -> None:
        """Test get_balances handles empty balance list."""
        client = PionexClient(api_key="key", api_secret="secret")

        empty_response = {
            "result": True,
            "data": {"balances": []},
        }

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = empty_response

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            balances = await client.get_balances()

        assert balances == []

    @pytest.mark.asyncio
    async def test_get_balances_auth_error(self) -> None:
        """Test get_balances raises error on authentication failure."""
        client = PionexClient(api_key="invalid_key", api_secret="invalid_secret")

        mock_response = MagicMock()
        mock_response.is_success = False
        mock_response.status_code = 401
        mock_response.content = b'{"result": false}'
        mock_response.json.return_value = {
            "result": False,
            "code": 1002,
            "message": "Invalid API key",
        }
        mock_response.headers = {}

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            with pytest.raises(PionexAPIError) as exc_info:
                await client.get_balances()

        assert exc_info.value.error.status_code == 401
        assert "Invalid API key" in exc_info.value.error.message


class TestOrderRequest:
    """Tests for OrderRequest model validation.

    Requirements:
        - 1.4: Submit LIMIT or MARKET orders with symbol, side, type, price, and quantity
    """

    def test_limit_order_requires_price(self) -> None:
        """Test LIMIT order raises error without price."""
        with pytest.raises(ValueError, match="Price is required for LIMIT orders"):
            OrderRequest(
                symbol="BTC_USDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=Decimal("0.001"),
                price=None,
            )

    def test_limit_order_with_price_succeeds(self) -> None:
        """Test LIMIT order with price is valid."""
        order = OrderRequest(
            symbol="BTC_USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.001"),
            price=Decimal("35000.00"),
        )
        assert order.symbol == "BTC_USDT"
        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.LIMIT
        assert order.quantity == Decimal("0.001")
        assert order.price == Decimal("35000.00")

    def test_market_order_without_price_succeeds(self) -> None:
        """Test MARKET order without price is valid."""
        order = OrderRequest(
            symbol="BTC_USDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.001"),
        )
        assert order.order_type == OrderType.MARKET
        assert order.price is None

    def test_quantity_must_be_positive(self) -> None:
        """Test quantity must be positive."""
        with pytest.raises(ValueError, match="Quantity must be positive"):
            OrderRequest(
                symbol="BTC_USDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=Decimal("0"),
            )

    def test_negative_quantity_raises(self) -> None:
        """Test negative quantity raises error."""
        with pytest.raises(ValueError, match="Quantity must be positive"):
            OrderRequest(
                symbol="BTC_USDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=Decimal("-0.001"),
            )

    def test_price_must_be_positive(self) -> None:
        """Test price must be positive when provided."""
        with pytest.raises(ValueError, match="Price must be positive"):
            OrderRequest(
                symbol="BTC_USDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=Decimal("0.001"),
                price=Decimal("0"),
            )

    def test_to_api_params_limit_order(self) -> None:
        """Test to_api_params for LIMIT order."""
        order = OrderRequest(
            symbol="BTC_USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.001"),
            price=Decimal("35000.00"),
            client_order_id="my-order-001",
        )
        params = order.to_api_params()

        assert params["symbol"] == "BTC_USDT"
        assert params["side"] == "BUY"
        assert params["type"] == "LIMIT"
        assert params["amount"] == "0.001"
        assert params["price"] == "35000.00"
        assert params["clientOrderId"] == "my-order-001"
        assert params["timeInForce"] == "GTC"

    def test_to_api_params_market_order(self) -> None:
        """Test to_api_params for MARKET order."""
        order = OrderRequest(
            symbol="ETH_USDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=Decimal("1.5"),
        )
        params = order.to_api_params()

        assert params["symbol"] == "ETH_USDT"
        assert params["side"] == "SELL"
        assert params["type"] == "MARKET"
        assert params["amount"] == "1.5"
        assert "price" not in params
        assert "timeInForce" not in params

    def test_default_time_in_force(self) -> None:
        """Test default time in force is GTC."""
        order = OrderRequest(
            symbol="BTC_USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.001"),
            price=Decimal("35000.00"),
        )
        assert order.time_in_force == TimeInForce.GTC

    def test_custom_time_in_force(self) -> None:
        """Test custom time in force."""
        order = OrderRequest(
            symbol="BTC_USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.001"),
            price=Decimal("35000.00"),
            time_in_force=TimeInForce.IOC,
        )
        assert order.time_in_force == TimeInForce.IOC
        params = order.to_api_params()
        assert params["timeInForce"] == "IOC"


class TestOrderResponse:
    """Tests for OrderResponse model parsing."""

    def test_from_api_response_limit_order(self) -> None:
        """Test parsing LIMIT order response."""
        data = {
            "orderId": "123456789",
            "clientOrderId": "my-order-001",
            "symbol": "BTC_USDT",
            "side": "BUY",
            "type": "LIMIT",
            "price": "35000.00",
            "amount": "0.001",
            "filledAmount": "0",
            "status": "NEW",
            "timestamp": 1700000000000,
        }
        response = OrderResponse.from_api_response(data)

        assert response.order_id == "123456789"
        assert response.client_order_id == "my-order-001"
        assert response.symbol == "BTC_USDT"
        assert response.side == OrderSide.BUY
        assert response.order_type == OrderType.LIMIT
        assert response.price == Decimal("35000.00")
        assert response.quantity == Decimal("0.001")
        assert response.executed_quantity == Decimal("0")
        assert response.status == OrderStatus.NEW
        assert response.timestamp == datetime.fromtimestamp(1700000000, tz=UTC)

    def test_from_api_response_market_order(self) -> None:
        """Test parsing MARKET order response."""
        data = {
            "orderId": "123456790",
            "symbol": "BTC_USDT",
            "side": "SELL",
            "type": "MARKET",
            "amount": "0.001",
            "filledAmount": "0.001",
            "status": "FILLED",
            "timestamp": 1700000001000,
        }
        response = OrderResponse.from_api_response(data)

        assert response.order_id == "123456790"
        assert response.client_order_id is None
        assert response.side == OrderSide.SELL
        assert response.order_type == OrderType.MARKET
        assert response.price is None
        assert response.executed_quantity == Decimal("0.001")
        assert response.status == OrderStatus.FILLED

    def test_from_api_response_partially_filled(self) -> None:
        """Test parsing partially filled order."""
        data = {
            "orderId": "123456791",
            "symbol": "ETH_USDT",
            "side": "BUY",
            "type": "LIMIT",
            "price": "2000.00",
            "amount": "1.0",
            "filledAmount": "0.5",
            "status": "PARTIALLY_FILLED",
            "timestamp": 1700000002000,
        }
        response = OrderResponse.from_api_response(data)

        assert response.quantity == Decimal("1.0")
        assert response.executed_quantity == Decimal("0.5")
        assert response.status == OrderStatus.PARTIALLY_FILLED


class TestCreateOrder:
    """Tests for create_order method.

    Requirements:
        - 1.4: Submit LIMIT or MARKET orders with symbol, side, type, price,
               and quantity to /api/v1/trade/order
    """

    @pytest.mark.asyncio
    async def test_create_limit_order_returns_response(self) -> None:
        """Test create_order returns OrderResponse for LIMIT order."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_CREATE_ORDER_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            order = OrderRequest(
                symbol="BTC_USDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=Decimal("0.001"),
                price=Decimal("35000.00"),
                client_order_id="my-order-001",
            )
            response = await client.create_order(order)

        assert isinstance(response, OrderResponse)
        assert response.order_id == "123456789"
        assert response.symbol == "BTC_USDT"
        assert response.side == OrderSide.BUY
        assert response.order_type == OrderType.LIMIT
        assert response.status == OrderStatus.NEW

    @pytest.mark.asyncio
    async def test_create_market_order_returns_response(self) -> None:
        """Test create_order returns OrderResponse for MARKET order."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_CREATE_MARKET_ORDER_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            order = OrderRequest(
                symbol="BTC_USDT",
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                quantity=Decimal("0.001"),
            )
            response = await client.create_order(order)

        assert isinstance(response, OrderResponse)
        assert response.order_id == "123456790"
        assert response.order_type == OrderType.MARKET
        assert response.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_create_order_is_authenticated(self) -> None:
        """Test create_order uses authenticated request."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_CREATE_ORDER_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            order = OrderRequest(
                symbol="BTC_USDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=Decimal("0.001"),
                price=Decimal("35000.00"),
            )
            await client.create_order(order)

            # Verify authentication headers were included
            call_args = mock_http_client.post.call_args
            headers = call_args.kwargs.get("headers", {})
            assert "PIONEX-KEY" in headers
            assert "PIONEX-SIGNATURE" in headers

    @pytest.mark.asyncio
    async def test_create_order_sends_correct_params(self) -> None:
        """Test create_order sends correct parameters."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_CREATE_ORDER_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            order = OrderRequest(
                symbol="BTC_USDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=Decimal("0.001"),
                price=Decimal("35000.00"),
                client_order_id="my-order-001",
            )
            await client.create_order(order)

            # Verify request body
            call_args = mock_http_client.post.call_args
            json_data = call_args.kwargs.get("json", {})
            assert json_data["symbol"] == "BTC_USDT"
            assert json_data["side"] == "BUY"
            assert json_data["type"] == "LIMIT"
            assert json_data["amount"] == "0.001"
            assert json_data["price"] == "35000.00"
            assert json_data["clientOrderId"] == "my-order-001"

    @pytest.mark.asyncio
    async def test_create_order_insufficient_balance_error(self) -> None:
        """Test create_order raises error on insufficient balance."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = False
        mock_response.status_code = 400
        mock_response.content = b'{"result": false}'
        mock_response.json.return_value = {
            "result": False,
            "code": 3001,
            "message": "Insufficient balance",
        }
        mock_response.headers = {}

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            order = OrderRequest(
                symbol="BTC_USDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=Decimal("100"),
                price=Decimal("35000.00"),
            )

            with pytest.raises(PionexAPIError) as exc_info:
                await client.create_order(order)

        assert exc_info.value.error.status_code == 400
        assert "Insufficient balance" in exc_info.value.error.message


class TestCancelOrder:
    """Tests for cancel_order method."""

    @pytest.mark.asyncio
    async def test_cancel_order_by_order_id(self) -> None:
        """Test cancel_order by order ID."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_CANCEL_ORDER_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.delete = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            response = await client.cancel_order(
                symbol="BTC_USDT",
                order_id="123456789",
            )

        assert isinstance(response, CancelOrderResponse)
        assert response.order_id == "123456789"
        assert response.symbol == "BTC_USDT"
        assert response.status == OrderStatus.CANCELED
        assert response.success is True

    @pytest.mark.asyncio
    async def test_cancel_order_by_client_order_id(self) -> None:
        """Test cancel_order by client order ID."""
        client = PionexClient(api_key="key", api_secret="secret")

        cancel_response = {
            "result": True,
            "data": {
                "orderId": "123456789",
                "symbol": "BTC_USDT",
                "status": "CANCELED",
            },
        }

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = cancel_response

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.delete = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            response = await client.cancel_order(
                symbol="BTC_USDT",
                client_order_id="my-order-001",
            )

        assert response.success is True
        assert response.status == OrderStatus.CANCELED

    @pytest.mark.asyncio
    async def test_cancel_order_requires_identifier(self) -> None:
        """Test cancel_order raises error without order ID or client order ID."""
        client = PionexClient(api_key="key", api_secret="secret")

        with pytest.raises(ValueError, match="Either order_id or client_order_id must be provided"):
            await client.cancel_order(symbol="BTC_USDT")

    @pytest.mark.asyncio
    async def test_cancel_order_is_authenticated(self) -> None:
        """Test cancel_order uses authenticated request."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_CANCEL_ORDER_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.delete = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            await client.cancel_order(
                symbol="BTC_USDT",
                order_id="123456789",
            )

            # Verify authentication headers were included
            call_args = mock_http_client.delete.call_args
            headers = call_args.kwargs.get("headers", {})
            assert "PIONEX-KEY" in headers
            assert "PIONEX-SIGNATURE" in headers

    @pytest.mark.asyncio
    async def test_cancel_order_sends_correct_params(self) -> None:
        """Test cancel_order sends correct parameters."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_CANCEL_ORDER_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.delete = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            await client.cancel_order(
                symbol="BTC_USDT",
                order_id="123456789",
            )

            # Verify request params
            call_args = mock_http_client.delete.call_args
            params = call_args.kwargs.get("params", {})
            assert params["symbol"] == "BTC_USDT"
            assert params["orderId"] == "123456789"

    @pytest.mark.asyncio
    async def test_cancel_order_not_found_error(self) -> None:
        """Test cancel_order raises error when order not found."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = False
        mock_response.status_code = 400
        mock_response.content = b'{"result": false}'
        mock_response.json.return_value = {
            "result": False,
            "code": 4001,
            "message": "Order not found",
        }
        mock_response.headers = {}

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.delete = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            with pytest.raises(PionexAPIError) as exc_info:
                await client.cancel_order(
                    symbol="BTC_USDT",
                    order_id="nonexistent",
                )

        assert exc_info.value.error.status_code == 400
        assert "Order not found" in exc_info.value.error.message

    @pytest.mark.asyncio
    async def test_cancel_order_already_filled_error(self) -> None:
        """Test cancel_order raises error when order already filled."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = False
        mock_response.status_code = 400
        mock_response.content = b'{"result": false}'
        mock_response.json.return_value = {
            "result": False,
            "code": 4002,
            "message": "Order already filled",
        }
        mock_response.headers = {}

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.delete = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            with pytest.raises(PionexAPIError) as exc_info:
                await client.cancel_order(
                    symbol="BTC_USDT",
                    order_id="123456789",
                )

        assert "Order already filled" in exc_info.value.error.message
