"""
Unit tests for Extended Pionex API Client methods.

Tests the PionexClient class for:
- Extended order methods (get_order, get_order_by_client_id, get_open_orders, get_all_orders)
- Mass order methods (create_mass_order, cancel_all_orders)
- Fill methods (get_fills, get_fills_by_order_id)
- Ticker methods (get_24hr_tickers, get_book_tickers)

Requirements:
- 1.1-1.7: Extended order management
- 2.1-2.4: Fill history
- 3.1-3.4: Market data tickers
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lib.pionex.client import PionexClient
from lib.pionex.models import (
    BookTicker,
    Fill,
    FillRole,
    MassOrderRequest,
    MassOrderResult,
    OrderDetail,
    OrderDetailStatus,
    OrderSide,
    OrderType,
    PionexAPIError,
    Ticker24hr,
)


# =============================================================================
# Sample API Responses for Mocking
# =============================================================================

SAMPLE_ORDER_RESPONSE = {
    "result": True,
    "data": {
        "orderId": 123456789,
        "symbol": "BTC_USDT",
        "type": "LIMIT",
        "side": "BUY",
        "price": "35000.00",
        "size": "0.001",
        "amount": None,
        "filledSize": "0.0005",
        "filledAmount": "17.50",
        "fee": "0.0175",
        "feeCoin": "USDT",
        "status": "OPEN",
        "IOC": False,
        "clientOrderId": "my-order-001",
        "source": "API",
        "createTime": 1700000000000,
        "updateTime": 1700000100000,
    },
}

SAMPLE_OPEN_ORDERS_RESPONSE = {
    "result": True,
    "data": {
        "orders": [
            {
                "orderId": 123456789,
                "symbol": "BTC_USDT",
                "type": "LIMIT",
                "side": "BUY",
                "price": "35000.00",
                "size": "0.001",
                "filledSize": "0",
                "filledAmount": "0",
                "fee": "0",
                "feeCoin": "USDT",
                "status": "OPEN",
                "IOC": False,
                "clientOrderId": "order-001",
                "source": "API",
                "createTime": 1700000000000,
                "updateTime": 1700000000000,
            },
            {
                "orderId": 123456790,
                "symbol": "BTC_USDT",
                "type": "LIMIT",
                "side": "SELL",
                "price": "36000.00",
                "size": "0.002",
                "filledSize": "0.001",
                "filledAmount": "36.00",
                "fee": "0.036",
                "feeCoin": "USDT",
                "status": "OPEN",
                "IOC": False,
                "clientOrderId": None,
                "source": "MANUAL",
                "createTime": 1700000100000,
                "updateTime": 1700000200000,
            },
        ]
    },
}

SAMPLE_ALL_ORDERS_RESPONSE = {
    "result": True,
    "data": {
        "orders": [
            {
                "orderId": 123456789,
                "symbol": "BTC_USDT",
                "type": "LIMIT",
                "side": "BUY",
                "price": "35000.00",
                "size": "0.001",
                "filledSize": "0.001",
                "filledAmount": "35.00",
                "fee": "0.035",
                "feeCoin": "USDT",
                "status": "CLOSED",
                "IOC": False,
                "clientOrderId": "order-001",
                "source": "API",
                "createTime": 1700000000000,
                "updateTime": 1700000500000,
            },
            {
                "orderId": 123456790,
                "symbol": "BTC_USDT",
                "type": "MARKET",
                "side": "SELL",
                "price": "0",
                "size": "0.002",
                "filledSize": "0.002",
                "filledAmount": "72.00",
                "fee": "0.072",
                "feeCoin": "USDT",
                "status": "CLOSED",
                "IOC": False,
                "clientOrderId": None,
                "source": "API",
                "createTime": 1700000100000,
                "updateTime": 1700000100000,
            },
        ]
    },
}

SAMPLE_MASS_ORDER_RESPONSE = {
    "result": True,
    "data": {
        "orders": [
            {"orderId": 123456791, "clientOrderId": "mass-001"},
            {"orderId": 123456792, "clientOrderId": "mass-002"},
            {"orderId": 123456793, "clientOrderId": None},
        ]
    },
}

SAMPLE_CANCEL_ALL_RESPONSE = {
    "result": True,
    "data": {
        "success": True,
    },
}

SAMPLE_FILLS_RESPONSE = {
    "result": True,
    "data": {
        "fills": [
            {
                "id": 987654321,
                "orderId": 123456789,
                "symbol": "BTC_USDT",
                "side": "BUY",
                "role": "TAKER",
                "price": "35000.00",
                "size": "0.0005",
                "fee": "0.0175",
                "feeCoin": "USDT",
                "timestamp": 1700000050000,
            },
            {
                "id": 987654322,
                "orderId": 123456789,
                "symbol": "BTC_USDT",
                "side": "BUY",
                "role": "MAKER",
                "price": "34999.00",
                "size": "0.0005",
                "fee": "0.00875",
                "feeCoin": "USDT",
                "timestamp": 1700000100000,
            },
        ]
    },
}

SAMPLE_24HR_TICKERS_RESPONSE = {
    "result": True,
    "data": {
        "tickers": [
            {
                "symbol": "BTC_USDT",
                "time": 1700000000000,
                "open": "34000.00",
                "close": "35000.00",
                "high": "35500.00",
                "low": "33500.00",
                "volume": "1000.5",
                "amount": "35000000.00",
                "count": 50000,
            },
            {
                "symbol": "ETH_USDT",
                "time": 1700000000000,
                "open": "2000.00",
                "close": "1950.00",
                "high": "2050.00",
                "low": "1900.00",
                "volume": "5000.0",
                "amount": "10000000.00",
                "count": 30000,
            },
        ]
    },
}

SAMPLE_BOOK_TICKERS_RESPONSE = {
    "result": True,
    "data": {
        "tickers": [
            {
                "symbol": "BTC_USDT",
                "bidPrice": "34999.00",
                "bidSize": "1.5",
                "askPrice": "35001.00",
                "askSize": "2.0",
                "timestamp": 1700000000000,
            },
            {
                "symbol": "ETH_USDT",
                "bidPrice": "1949.00",
                "bidSize": "10.0",
                "askPrice": "1951.00",
                "askSize": "15.0",
                "timestamp": 1700000000000,
            },
        ]
    },
}


# =============================================================================
# Test Classes for Order Methods
# =============================================================================


class TestGetOrder:
    """Tests for get_order method.

    Requirements:
        - 1.1: Retrieve order details by orderId from GET /api/v1/trade/order
        - 1.7: Order response includes all fields
    """

    @pytest.mark.asyncio
    async def test_get_order_returns_order_detail(self) -> None:
        """Test get_order returns OrderDetail object."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_ORDER_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            order = await client.get_order("BTC_USDT", 123456789)

        assert isinstance(order, OrderDetail)
        assert order.order_id == 123456789
        assert order.symbol == "BTC_USDT"

    @pytest.mark.asyncio
    async def test_get_order_parses_all_fields(self) -> None:
        """Test all order fields are parsed correctly."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_ORDER_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            order = await client.get_order("BTC_USDT", 123456789)

        assert order.order_type == OrderType.LIMIT
        assert order.side == OrderSide.BUY
        assert order.price == Decimal("35000.00")
        assert order.size == Decimal("0.001")
        assert order.filled_size == Decimal("0.0005")
        assert order.filled_amount == Decimal("17.50")
        assert order.fee == Decimal("0.0175")
        assert order.fee_coin == "USDT"
        assert order.status == OrderDetailStatus.OPEN
        assert order.ioc is False
        assert order.client_order_id == "my-order-001"
        assert order.source == "API"
        assert order.create_time == datetime.fromtimestamp(1700000000, tz=UTC)
        assert order.update_time == datetime.fromtimestamp(1700000100, tz=UTC)

    @pytest.mark.asyncio
    async def test_get_order_passes_correct_params(self) -> None:
        """Test get_order passes correct parameters to API."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_ORDER_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            await client.get_order("BTC_USDT", 123456789)

            call_args = mock_http_client.get.call_args
            assert call_args.kwargs["params"]["symbol"] == "BTC_USDT"
            assert call_args.kwargs["params"]["orderId"] == 123456789


class TestGetOrderByClientId:
    """Tests for get_order_by_client_id method.

    Requirements:
        - 1.2: Retrieve order details from GET /api/v1/trade/orderByClientOrderId
    """

    @pytest.mark.asyncio
    async def test_get_order_by_client_id_returns_order_detail(self) -> None:
        """Test get_order_by_client_id returns OrderDetail object."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_ORDER_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            order = await client.get_order_by_client_id("BTC_USDT", "my-order-001")

        assert isinstance(order, OrderDetail)
        assert order.client_order_id == "my-order-001"

    @pytest.mark.asyncio
    async def test_get_order_by_client_id_passes_correct_params(self) -> None:
        """Test get_order_by_client_id passes correct parameters to API."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_ORDER_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            await client.get_order_by_client_id("BTC_USDT", "my-order-001")

            call_args = mock_http_client.get.call_args
            assert call_args.kwargs["params"]["symbol"] == "BTC_USDT"
            assert call_args.kwargs["params"]["clientOrderId"] == "my-order-001"


class TestGetOpenOrders:
    """Tests for get_open_orders method.

    Requirements:
        - 1.3: Retrieve all open orders from GET /api/v1/trade/openOrders
    """

    @pytest.mark.asyncio
    async def test_get_open_orders_returns_list(self) -> None:
        """Test get_open_orders returns list of OrderDetail objects."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_OPEN_ORDERS_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            orders = await client.get_open_orders("BTC_USDT")

        assert isinstance(orders, list)
        assert len(orders) == 2
        assert all(isinstance(o, OrderDetail) for o in orders)

    @pytest.mark.asyncio
    async def test_get_open_orders_parses_multiple_orders(self) -> None:
        """Test multiple orders are parsed correctly."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_OPEN_ORDERS_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            orders = await client.get_open_orders("BTC_USDT")

        # First order
        assert orders[0].order_id == 123456789
        assert orders[0].side == OrderSide.BUY
        assert orders[0].price == Decimal("35000.00")

        # Second order
        assert orders[1].order_id == 123456790
        assert orders[1].side == OrderSide.SELL
        assert orders[1].price == Decimal("36000.00")

    @pytest.mark.asyncio
    async def test_get_open_orders_empty_list(self) -> None:
        """Test get_open_orders returns empty list when no orders."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = {"result": True, "data": {"orders": []}}

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            orders = await client.get_open_orders("BTC_USDT")

        assert orders == []


class TestGetAllOrders:
    """Tests for get_all_orders method.

    Requirements:
        - 1.4: Retrieve all orders from GET /api/v1/trade/allOrders with pagination
    """

    @pytest.mark.asyncio
    async def test_get_all_orders_returns_list(self) -> None:
        """Test get_all_orders returns list of OrderDetail objects."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_ALL_ORDERS_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            orders = await client.get_all_orders("BTC_USDT")

        assert isinstance(orders, list)
        assert len(orders) == 2
        assert all(isinstance(o, OrderDetail) for o in orders)

    @pytest.mark.asyncio
    async def test_get_all_orders_includes_closed_orders(self) -> None:
        """Test get_all_orders includes closed orders."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_ALL_ORDERS_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            orders = await client.get_all_orders("BTC_USDT")

        assert all(o.status == OrderDetailStatus.CLOSED for o in orders)

    @pytest.mark.asyncio
    async def test_get_all_orders_with_time_range(self) -> None:
        """Test get_all_orders passes time range parameters."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_ALL_ORDERS_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            await client.get_all_orders(
                "BTC_USDT",
                start_time=1700000000000,
                end_time=1700100000000,
                limit=100,
            )

            call_args = mock_http_client.get.call_args
            assert call_args.kwargs["params"]["startTime"] == 1700000000000
            assert call_args.kwargs["params"]["endTime"] == 1700100000000
            assert call_args.kwargs["params"]["limit"] == 100

    @pytest.mark.asyncio
    async def test_get_all_orders_limit_capped_at_100(self) -> None:
        """Test get_all_orders caps limit at 100."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_ALL_ORDERS_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            await client.get_all_orders("BTC_USDT", limit=500)

            call_args = mock_http_client.get.call_args
            assert call_args.kwargs["params"]["limit"] == 100


class TestCreateMassOrder:
    """Tests for create_mass_order method.

    Requirements:
        - 1.5: Submit up to 20 LIMIT orders via POST /api/v1/trade/massOrder
    """

    @pytest.mark.asyncio
    async def test_create_mass_order_returns_results(self) -> None:
        """Test create_mass_order returns list of MassOrderResult objects."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_MASS_ORDER_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            orders = [
                MassOrderRequest(
                    side=OrderSide.BUY,
                    price=Decimal("35000.00"),
                    size=Decimal("0.001"),
                    client_order_id="mass-001",
                ),
                MassOrderRequest(
                    side=OrderSide.BUY,
                    price=Decimal("34500.00"),
                    size=Decimal("0.001"),
                    client_order_id="mass-002",
                ),
                MassOrderRequest(
                    side=OrderSide.SELL,
                    price=Decimal("36000.00"),
                    size=Decimal("0.001"),
                ),
            ]

            results = await client.create_mass_order("BTC_USDT", orders)

        assert isinstance(results, list)
        assert len(results) == 3
        assert all(isinstance(r, MassOrderResult) for r in results)

    @pytest.mark.asyncio
    async def test_create_mass_order_parses_results(self) -> None:
        """Test mass order results are parsed correctly."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_MASS_ORDER_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            orders = [
                MassOrderRequest(
                    side=OrderSide.BUY,
                    price=Decimal("35000.00"),
                    size=Decimal("0.001"),
                ),
            ]

            results = await client.create_mass_order("BTC_USDT", orders)

        assert results[0].order_id == 123456791
        assert results[0].client_order_id == "mass-001"
        assert results[2].client_order_id is None

    @pytest.mark.asyncio
    async def test_create_mass_order_raises_for_more_than_20(self) -> None:
        """Test create_mass_order raises ValueError for more than 20 orders."""
        client = PionexClient(api_key="key", api_secret="secret")

        orders = [
            MassOrderRequest(
                side=OrderSide.BUY,
                price=Decimal("35000.00"),
                size=Decimal("0.001"),
            )
            for _ in range(21)
        ]

        with pytest.raises(ValueError, match="cannot exceed 20 orders"):
            await client.create_mass_order("BTC_USDT", orders)

    @pytest.mark.asyncio
    async def test_create_mass_order_raises_for_empty_list(self) -> None:
        """Test create_mass_order raises ValueError for empty list."""
        client = PionexClient(api_key="key", api_secret="secret")

        with pytest.raises(ValueError, match="At least one order is required"):
            await client.create_mass_order("BTC_USDT", [])


class TestCancelAllOrders:
    """Tests for cancel_all_orders method.

    Requirements:
        - 1.6: Cancel all open orders via DELETE /api/v1/trade/allOrders
    """

    @pytest.mark.asyncio
    async def test_cancel_all_orders_returns_true(self) -> None:
        """Test cancel_all_orders returns True on success."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_CANCEL_ALL_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.delete = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            result = await client.cancel_all_orders("BTC_USDT")

        assert result is True

    @pytest.mark.asyncio
    async def test_cancel_all_orders_passes_symbol(self) -> None:
        """Test cancel_all_orders passes symbol parameter."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_CANCEL_ALL_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.delete = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            await client.cancel_all_orders("ETH_USDT")

            call_args = mock_http_client.delete.call_args
            assert call_args.kwargs["params"]["symbol"] == "ETH_USDT"



# =============================================================================
# Test Classes for Fill Methods
# =============================================================================


class TestGetFills:
    """Tests for get_fills method.

    Requirements:
        - 2.1: Retrieve fill history from GET /api/v1/trade/fills
        - 2.4: Return max 100 fills
    """

    @pytest.mark.asyncio
    async def test_get_fills_returns_list(self) -> None:
        """Test get_fills returns list of Fill objects."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_FILLS_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            fills = await client.get_fills("BTC_USDT")

        assert isinstance(fills, list)
        assert len(fills) == 2
        assert all(isinstance(f, Fill) for f in fills)

    @pytest.mark.asyncio
    async def test_get_fills_parses_all_fields(self) -> None:
        """Test all fill fields are parsed correctly."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_FILLS_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            fills = await client.get_fills("BTC_USDT")

        first_fill = fills[0]
        assert first_fill.id == 987654321
        assert first_fill.order_id == 123456789
        assert first_fill.symbol == "BTC_USDT"
        assert first_fill.side == OrderSide.BUY
        assert first_fill.role == FillRole.TAKER
        assert first_fill.price == Decimal("35000.00")
        assert first_fill.size == Decimal("0.0005")
        assert first_fill.fee == Decimal("0.0175")
        assert first_fill.fee_coin == "USDT"
        assert first_fill.timestamp == datetime.fromtimestamp(1700000050, tz=UTC)

    @pytest.mark.asyncio
    async def test_get_fills_parses_maker_role(self) -> None:
        """Test MAKER role is parsed correctly."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_FILLS_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            fills = await client.get_fills("BTC_USDT")

        second_fill = fills[1]
        assert second_fill.role == FillRole.MAKER

    @pytest.mark.asyncio
    async def test_get_fills_with_time_range(self) -> None:
        """Test get_fills passes time range parameters."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_FILLS_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            await client.get_fills(
                "BTC_USDT",
                start_time=1700000000000,
                end_time=1700100000000,
            )

            call_args = mock_http_client.get.call_args
            assert call_args.kwargs["params"]["startTime"] == 1700000000000
            assert call_args.kwargs["params"]["endTime"] == 1700100000000

    @pytest.mark.asyncio
    async def test_get_fills_empty_list(self) -> None:
        """Test get_fills returns empty list when no fills."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = {"result": True, "data": {"fills": []}}

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            fills = await client.get_fills("BTC_USDT")

        assert fills == []


class TestGetFillsByOrderId:
    """Tests for get_fills_by_order_id method.

    Requirements:
        - 2.2: Retrieve fills for a specific orderId from GET /api/v1/trade/fillsByOrderId
    """

    @pytest.mark.asyncio
    async def test_get_fills_by_order_id_returns_list(self) -> None:
        """Test get_fills_by_order_id returns list of Fill objects."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_FILLS_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            fills = await client.get_fills_by_order_id("BTC_USDT", 123456789)

        assert isinstance(fills, list)
        assert len(fills) == 2
        assert all(isinstance(f, Fill) for f in fills)

    @pytest.mark.asyncio
    async def test_get_fills_by_order_id_passes_correct_params(self) -> None:
        """Test get_fills_by_order_id passes correct parameters."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_FILLS_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            await client.get_fills_by_order_id("BTC_USDT", 123456789, from_id=100)

            call_args = mock_http_client.get.call_args
            assert call_args.kwargs["params"]["symbol"] == "BTC_USDT"
            assert call_args.kwargs["params"]["orderId"] == 123456789
            assert call_args.kwargs["params"]["fromId"] == 100

    @pytest.mark.asyncio
    async def test_get_fills_by_order_id_all_fills_have_same_order_id(self) -> None:
        """Test all returned fills have the same order ID."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_FILLS_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            fills = await client.get_fills_by_order_id("BTC_USDT", 123456789)

        assert all(f.order_id == 123456789 for f in fills)


# =============================================================================
# Test Classes for Ticker Methods
# =============================================================================


class TestGet24hrTickers:
    """Tests for get_24hr_tickers method.

    Requirements:
        - 3.1: Retrieve ticker data from GET /api/v1/market/tickers
        - 3.3: 24hr ticker includes all fields and change calculation
    """

    @pytest.mark.asyncio
    async def test_get_24hr_tickers_returns_list(self) -> None:
        """Test get_24hr_tickers returns list of Ticker24hr objects."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_24HR_TICKERS_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            tickers = await client.get_24hr_tickers()

        assert isinstance(tickers, list)
        assert len(tickers) == 2
        assert all(isinstance(t, Ticker24hr) for t in tickers)

    @pytest.mark.asyncio
    async def test_get_24hr_tickers_parses_all_fields(self) -> None:
        """Test all ticker fields are parsed correctly."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_24HR_TICKERS_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            tickers = await client.get_24hr_tickers()

        btc_ticker = next(t for t in tickers if t.symbol == "BTC_USDT")
        assert btc_ticker.open == Decimal("34000.00")
        assert btc_ticker.close == Decimal("35000.00")
        assert btc_ticker.high == Decimal("35500.00")
        assert btc_ticker.low == Decimal("33500.00")
        assert btc_ticker.volume == Decimal("1000.5")
        assert btc_ticker.amount == Decimal("35000000.00")
        assert btc_ticker.count == 50000
        assert btc_ticker.time == datetime.fromtimestamp(1700000000, tz=UTC)

    @pytest.mark.asyncio
    async def test_get_24hr_tickers_change_percent_positive(self) -> None:
        """Test change_percent calculation for positive change."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_24HR_TICKERS_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            tickers = await client.get_24hr_tickers()

        btc_ticker = next(t for t in tickers if t.symbol == "BTC_USDT")
        # (35000 - 34000) / 34000 * 100 = 2.94%
        assert abs(btc_ticker.change_percent - 2.94) < 0.01

    @pytest.mark.asyncio
    async def test_get_24hr_tickers_change_percent_negative(self) -> None:
        """Test change_percent calculation for negative change."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_24HR_TICKERS_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            tickers = await client.get_24hr_tickers()

        eth_ticker = next(t for t in tickers if t.symbol == "ETH_USDT")
        # (1950 - 2000) / 2000 * 100 = -2.5%
        assert abs(eth_ticker.change_percent - (-2.5)) < 0.01

    @pytest.mark.asyncio
    async def test_get_24hr_tickers_with_symbol_filter(self) -> None:
        """Test get_24hr_tickers passes symbol parameter."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_24HR_TICKERS_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            await client.get_24hr_tickers(symbol="BTC_USDT")

            call_args = mock_http_client.get.call_args
            assert call_args.kwargs["params"]["symbol"] == "BTC_USDT"

    @pytest.mark.asyncio
    async def test_get_24hr_tickers_with_market_type(self) -> None:
        """Test get_24hr_tickers passes market type parameter."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_24HR_TICKERS_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            await client.get_24hr_tickers(market_type="PERP")

            call_args = mock_http_client.get.call_args
            assert call_args.kwargs["params"]["marketType"] == "PERP"


class TestGetBookTickers:
    """Tests for get_book_tickers method.

    Requirements:
        - 3.2: Retrieve best bid/ask from GET /api/v1/market/bookTickers
        - 3.4: Book ticker includes all fields and spread calculation
    """

    @pytest.mark.asyncio
    async def test_get_book_tickers_returns_list(self) -> None:
        """Test get_book_tickers returns list of BookTicker objects."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_BOOK_TICKERS_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            book_tickers = await client.get_book_tickers()

        assert isinstance(book_tickers, list)
        assert len(book_tickers) == 2
        assert all(isinstance(bt, BookTicker) for bt in book_tickers)

    @pytest.mark.asyncio
    async def test_get_book_tickers_parses_all_fields(self) -> None:
        """Test all book ticker fields are parsed correctly."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_BOOK_TICKERS_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            book_tickers = await client.get_book_tickers()

        btc_book = next(bt for bt in book_tickers if bt.symbol == "BTC_USDT")
        assert btc_book.bid_price == Decimal("34999.00")
        assert btc_book.bid_size == Decimal("1.5")
        assert btc_book.ask_price == Decimal("35001.00")
        assert btc_book.ask_size == Decimal("2.0")
        assert btc_book.timestamp == datetime.fromtimestamp(1700000000, tz=UTC)

    @pytest.mark.asyncio
    async def test_get_book_tickers_spread_calculation(self) -> None:
        """Test spread calculation is correct."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_BOOK_TICKERS_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            book_tickers = await client.get_book_tickers()

        btc_book = next(bt for bt in book_tickers if bt.symbol == "BTC_USDT")
        # spread = ask_price - bid_price = 35001 - 34999 = 2
        assert btc_book.spread == Decimal("2.00")

        eth_book = next(bt for bt in book_tickers if bt.symbol == "ETH_USDT")
        # spread = 1951 - 1949 = 2
        assert eth_book.spread == Decimal("2.00")

    @pytest.mark.asyncio
    async def test_get_book_tickers_with_symbol_filter(self) -> None:
        """Test get_book_tickers passes symbol parameter."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_BOOK_TICKERS_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            await client.get_book_tickers(symbol="BTC_USDT")

            call_args = mock_http_client.get.call_args
            assert call_args.kwargs["params"]["symbol"] == "BTC_USDT"

    @pytest.mark.asyncio
    async def test_get_book_tickers_with_market_type(self) -> None:
        """Test get_book_tickers passes market type parameter."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = SAMPLE_BOOK_TICKERS_RESPONSE

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            await client.get_book_tickers(market_type="PERP")

            call_args = mock_http_client.get.call_args
            assert call_args.kwargs["params"]["marketType"] == "PERP"

    @pytest.mark.asyncio
    async def test_get_book_tickers_empty_list(self) -> None:
        """Test get_book_tickers returns empty list when no tickers."""
        client = PionexClient(api_key="key", api_secret="secret")

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.content = b'{"result": true}'
        mock_response.json.return_value = {"result": True, "data": {"tickers": []}}

        with patch.object(client, "_ensure_client") as mock_ensure:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_ensure.return_value = mock_http_client

            book_tickers = await client.get_book_tickers()

        assert book_tickers == []
