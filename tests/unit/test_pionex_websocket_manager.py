"""
Unit tests for Pionex WebSocket Manager.

Tests the PionexWebSocketManager class for:
- Public stream subscriptions (TRADE, DEPTH)
- Private stream subscriptions (ORDER, FILL, BALANCE)
- Message parsing
- Authentication
- Reconnection logic

Requirements:
- 5.1-5.4: Public WebSocket streams
- 6.1-6.7: Private WebSocket streams
- 5.5: Automatic reconnection with exponential backoff
"""

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lib.pionex.models import (
    Balance,
    Fill,
    FillRole,
    OrderBook,
    OrderBookLevel,
    OrderDetail,
    OrderDetailStatus,
    OrderSide,
    OrderType,
    Trade,
)
from lib.pionex.websocket import (
    INITIAL_RECONNECT_DELAY,
    MAX_RECONNECT_DELAY,
    RECONNECT_MULTIPLIER,
    BalanceUpdate,
    PionexWebSocketManager,
    Subscription,
    WebSocketTopic,
)


# =============================================================================
# Sample WebSocket Messages for Testing
# =============================================================================

SAMPLE_TRADE_MESSAGE = {
    "topic": "TRADE",
    "symbol": "BTC_USDT",
    "data": {
        "tradeId": "123456789",
        "symbol": "BTC_USDT",
        "price": "35000.00",
        "size": "0.001",
        "side": "BUY",
        "timestamp": 1700000000000,
    },
}

SAMPLE_DEPTH_MESSAGE = {
    "topic": "DEPTH",
    "symbol": "BTC_USDT",
    "data": {
        "symbol": "BTC_USDT",
        "bids": [
            ["34999.00", "1.5"],
            ["34998.00", "2.0"],
            ["34997.00", "0.5"],
        ],
        "asks": [
            ["35001.00", "1.0"],
            ["35002.00", "1.5"],
            ["35003.00", "2.0"],
        ],
        "timestamp": 1700000000000,
    },
}

SAMPLE_ORDER_MESSAGE = {
    "topic": "ORDER",
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

SAMPLE_FILL_MESSAGE = {
    "topic": "FILL",
    "data": {
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
}

SAMPLE_BALANCE_MESSAGE = {
    "topic": "BALANCE",
    "data": {
        "balances": [
            {"coin": "BTC", "free": "1.5", "frozen": "0.5"},
            {"coin": "USDT", "free": "10000.00", "frozen": "500.00"},
        ],
        "timestamp": 1700000000000,
    },
}

SAMPLE_AUTH_SUCCESS_RESPONSE = {
    "op": "AUTH",
    "success": True,
}

SAMPLE_AUTH_FAILURE_RESPONSE = {
    "op": "AUTH",
    "success": False,
    "message": "Invalid API key",
}

SAMPLE_SUBSCRIBE_RESPONSE = {
    "op": "SUBSCRIBE",
    "success": True,
    "topic": "TRADE",
    "symbol": "BTC_USDT",
}


# =============================================================================
# Test Classes for Public Stream Subscriptions
# =============================================================================


class TestPublicStreamSubscriptions:
    """Tests for public WebSocket stream subscriptions.

    Requirements:
        - 5.1: Subscribe to TRADE topic for real-time trade data
        - 5.2: Subscribe to DEPTH topic with configurable limit
        - 5.3: Trade data includes symbol, tradeId, price, size, side, timestamp
        - 5.4: Depth data includes bids and asks arrays
    """

    @pytest.mark.asyncio
    async def test_subscribe_trade_sends_correct_message(self) -> None:
        """Test subscribe_trade sends correct subscription message."""
        manager = PionexWebSocketManager()

        mock_ws = AsyncMock()
        manager._public_ws = mock_ws
        manager._public_connected = True

        await manager.subscribe_trade("BTC_USDT")

        mock_ws.send.assert_called_once()
        sent_message = json.loads(mock_ws.send.call_args[0][0])

        assert sent_message["op"] == "SUBSCRIBE"
        assert sent_message["topic"] == "TRADE"
        assert sent_message["symbol"] == "BTC_USDT"

    @pytest.mark.asyncio
    async def test_subscribe_trade_tracks_subscription(self) -> None:
        """Test subscribe_trade adds subscription to tracking list."""
        manager = PionexWebSocketManager()

        mock_ws = AsyncMock()
        manager._public_ws = mock_ws
        manager._public_connected = True

        await manager.subscribe_trade("BTC_USDT")

        assert len(manager.public_subscriptions) == 1
        sub = manager.public_subscriptions[0]
        assert sub.topic == WebSocketTopic.TRADE
        assert sub.symbol == "BTC_USDT"

    @pytest.mark.asyncio
    async def test_subscribe_depth_sends_correct_message(self) -> None:
        """Test subscribe_depth sends correct subscription message."""
        manager = PionexWebSocketManager()

        mock_ws = AsyncMock()
        manager._public_ws = mock_ws
        manager._public_connected = True

        await manager.subscribe_depth("BTC_USDT", limit=50)

        mock_ws.send.assert_called_once()
        sent_message = json.loads(mock_ws.send.call_args[0][0])

        assert sent_message["op"] == "SUBSCRIBE"
        assert sent_message["topic"] == "DEPTH"
        assert sent_message["symbol"] == "BTC_USDT"
        assert sent_message["limit"] == 50

    @pytest.mark.asyncio
    async def test_subscribe_depth_clamps_limit_to_valid_range(self) -> None:
        """Test subscribe_depth clamps limit to 1-100 range."""
        manager = PionexWebSocketManager()

        mock_ws = AsyncMock()
        manager._public_ws = mock_ws
        manager._public_connected = True

        # Test lower bound
        await manager.subscribe_depth("BTC_USDT", limit=0)
        sent_message = json.loads(mock_ws.send.call_args[0][0])
        assert sent_message["limit"] == 1

        mock_ws.reset_mock()
        manager._public_subscriptions.clear()

        # Test upper bound
        await manager.subscribe_depth("BTC_USDT", limit=200)
        sent_message = json.loads(mock_ws.send.call_args[0][0])
        assert sent_message["limit"] == 100

    @pytest.mark.asyncio
    async def test_subscribe_depth_tracks_subscription_with_params(self) -> None:
        """Test subscribe_depth tracks subscription with limit parameter."""
        manager = PionexWebSocketManager()

        mock_ws = AsyncMock()
        manager._public_ws = mock_ws
        manager._public_connected = True

        await manager.subscribe_depth("ETH_USDT", limit=30)

        assert len(manager.public_subscriptions) == 1
        sub = manager.public_subscriptions[0]
        assert sub.topic == WebSocketTopic.DEPTH
        assert sub.symbol == "ETH_USDT"
        assert sub.params.get("limit") == 30


class TestTradeMessageParsing:
    """Tests for trade message parsing.

    Requirements:
        - 5.3: Trade data includes symbol, tradeId, price, size, side, timestamp
    """

    @pytest.mark.asyncio
    async def test_trade_message_parsed_correctly(self) -> None:
        """Test trade message is parsed into Trade object."""
        received_trade: Trade | None = None

        async def on_trade(trade: Trade) -> None:
            nonlocal received_trade
            received_trade = trade

        manager = PionexWebSocketManager(on_trade=on_trade)

        await manager._process_public_message(json.dumps(SAMPLE_TRADE_MESSAGE))

        assert received_trade is not None
        assert received_trade.trade_id == "123456789"
        assert received_trade.symbol == "BTC_USDT"
        assert received_trade.price == Decimal("35000.00")
        assert received_trade.quantity == Decimal("0.001")
        assert received_trade.side == OrderSide.BUY
        assert received_trade.timestamp == datetime.fromtimestamp(1700000000, tz=UTC)

    @pytest.mark.asyncio
    async def test_trade_message_sell_side_parsed(self) -> None:
        """Test trade message with SELL side is parsed correctly."""
        received_trade: Trade | None = None

        async def on_trade(trade: Trade) -> None:
            nonlocal received_trade
            received_trade = trade

        manager = PionexWebSocketManager(on_trade=on_trade)

        sell_message = {
            "topic": "TRADE",
            "symbol": "BTC_USDT",
            "data": {
                "tradeId": "123456790",
                "price": "35100.00",
                "size": "0.002",
                "side": "SELL",
                "timestamp": 1700000001000,
            },
        }

        await manager._process_public_message(json.dumps(sell_message))

        assert received_trade is not None
        assert received_trade.side == OrderSide.SELL

    @pytest.mark.asyncio
    async def test_trade_callback_not_called_when_not_set(self) -> None:
        """Test no error when trade callback is not set."""
        manager = PionexWebSocketManager()

        # Should not raise any exception
        await manager._process_public_message(json.dumps(SAMPLE_TRADE_MESSAGE))


class TestDepthMessageParsing:
    """Tests for depth message parsing.

    Requirements:
        - 5.4: Depth data includes bids and asks arrays with [price, size] format
    """

    @pytest.mark.asyncio
    async def test_depth_message_parsed_correctly(self) -> None:
        """Test depth message is parsed into OrderBook object."""
        received_depth: OrderBook | None = None

        async def on_depth(order_book: OrderBook) -> None:
            nonlocal received_depth
            received_depth = order_book

        manager = PionexWebSocketManager(on_depth=on_depth)

        await manager._process_public_message(json.dumps(SAMPLE_DEPTH_MESSAGE))

        assert received_depth is not None
        assert received_depth.symbol == "BTC_USDT"
        assert len(received_depth.bids) == 3
        assert len(received_depth.asks) == 3

    @pytest.mark.asyncio
    async def test_depth_bids_parsed_correctly(self) -> None:
        """Test depth bids are parsed with correct price and quantity."""
        received_depth: OrderBook | None = None

        async def on_depth(order_book: OrderBook) -> None:
            nonlocal received_depth
            received_depth = order_book

        manager = PionexWebSocketManager(on_depth=on_depth)

        await manager._process_public_message(json.dumps(SAMPLE_DEPTH_MESSAGE))

        assert received_depth is not None
        # First bid
        assert received_depth.bids[0].price == Decimal("34999.00")
        assert received_depth.bids[0].quantity == Decimal("1.5")
        # Second bid
        assert received_depth.bids[1].price == Decimal("34998.00")
        assert received_depth.bids[1].quantity == Decimal("2.0")

    @pytest.mark.asyncio
    async def test_depth_asks_parsed_correctly(self) -> None:
        """Test depth asks are parsed with correct price and quantity."""
        received_depth: OrderBook | None = None

        async def on_depth(order_book: OrderBook) -> None:
            nonlocal received_depth
            received_depth = order_book

        manager = PionexWebSocketManager(on_depth=on_depth)

        await manager._process_public_message(json.dumps(SAMPLE_DEPTH_MESSAGE))

        assert received_depth is not None
        # First ask
        assert received_depth.asks[0].price == Decimal("35001.00")
        assert received_depth.asks[0].quantity == Decimal("1.0")
        # Second ask
        assert received_depth.asks[1].price == Decimal("35002.00")
        assert received_depth.asks[1].quantity == Decimal("1.5")

    @pytest.mark.asyncio
    async def test_depth_timestamp_parsed(self) -> None:
        """Test depth timestamp is parsed correctly."""
        received_depth: OrderBook | None = None

        async def on_depth(order_book: OrderBook) -> None:
            nonlocal received_depth
            received_depth = order_book

        manager = PionexWebSocketManager(on_depth=on_depth)

        await manager._process_public_message(json.dumps(SAMPLE_DEPTH_MESSAGE))

        assert received_depth is not None
        assert received_depth.timestamp == datetime.fromtimestamp(1700000000, tz=UTC)

    @pytest.mark.asyncio
    async def test_depth_callback_not_called_when_not_set(self) -> None:
        """Test no error when depth callback is not set."""
        manager = PionexWebSocketManager()

        # Should not raise any exception
        await manager._process_public_message(json.dumps(SAMPLE_DEPTH_MESSAGE))

    @pytest.mark.asyncio
    async def test_depth_empty_bids_asks_handled(self) -> None:
        """Test depth message with empty bids/asks is handled."""
        received_depth: OrderBook | None = None

        async def on_depth(order_book: OrderBook) -> None:
            nonlocal received_depth
            received_depth = order_book

        manager = PionexWebSocketManager(on_depth=on_depth)

        empty_depth_message = {
            "topic": "DEPTH",
            "symbol": "BTC_USDT",
            "data": {
                "symbol": "BTC_USDT",
                "bids": [],
                "asks": [],
                "timestamp": 1700000000000,
            },
        }

        await manager._process_public_message(json.dumps(empty_depth_message))

        assert received_depth is not None
        assert len(received_depth.bids) == 0
        assert len(received_depth.asks) == 0


class TestSubscriptionConfirmation:
    """Tests for subscription confirmation handling."""

    @pytest.mark.asyncio
    async def test_subscribe_confirmation_handled(self) -> None:
        """Test subscription confirmation message is handled without error."""
        manager = PionexWebSocketManager()

        # Should not raise any exception
        await manager._process_public_message(json.dumps(SAMPLE_SUBSCRIBE_RESPONSE))

    @pytest.mark.asyncio
    async def test_pong_message_handled(self) -> None:
        """Test PONG message is handled without error."""
        manager = PionexWebSocketManager()

        pong_message = {"op": "PONG"}

        # Should not raise any exception
        await manager._process_public_message(json.dumps(pong_message))

    @pytest.mark.asyncio
    async def test_unknown_message_handled(self) -> None:
        """Test unknown message is handled without error."""
        manager = PionexWebSocketManager()

        unknown_message = {"unknown": "data"}

        # Should not raise any exception
        await manager._process_public_message(json.dumps(unknown_message))

    @pytest.mark.asyncio
    async def test_invalid_json_handled(self) -> None:
        """Test invalid JSON is handled without raising exception."""
        manager = PionexWebSocketManager()

        # Should not raise any exception
        await manager._process_public_message("not valid json")



# =============================================================================
# Test Classes for Private Stream Subscriptions
# =============================================================================


class TestPrivateStreamSubscriptions:
    """Tests for private WebSocket stream subscriptions.

    Requirements:
        - 6.1: Subscribe to ORDER topic with authentication
        - 6.2: Subscribe to FILL topic with authentication
        - 6.3: Subscribe to BALANCE topic with authentication
        - 6.7: HMAC-SHA256 authentication for private connections
    """

    @pytest.mark.asyncio
    async def test_subscribe_order_sends_correct_message(self) -> None:
        """Test subscribe_order sends correct subscription message."""
        manager = PionexWebSocketManager(api_key="test_key", api_secret="test_secret")

        mock_ws = AsyncMock()
        manager._private_ws = mock_ws
        manager._private_connected = True

        await manager.subscribe_order("BTC_USDT")

        mock_ws.send.assert_called_once()
        sent_message = json.loads(mock_ws.send.call_args[0][0])

        assert sent_message["op"] == "SUBSCRIBE"
        assert sent_message["topic"] == "ORDER"
        assert sent_message["symbol"] == "BTC_USDT"

    @pytest.mark.asyncio
    async def test_subscribe_order_tracks_subscription(self) -> None:
        """Test subscribe_order adds subscription to tracking list."""
        manager = PionexWebSocketManager(api_key="test_key", api_secret="test_secret")

        mock_ws = AsyncMock()
        manager._private_ws = mock_ws
        manager._private_connected = True

        await manager.subscribe_order("BTC_USDT")

        assert len(manager.private_subscriptions) == 1
        sub = manager.private_subscriptions[0]
        assert sub.topic == WebSocketTopic.ORDER
        assert sub.symbol == "BTC_USDT"

    @pytest.mark.asyncio
    async def test_subscribe_fill_sends_correct_message(self) -> None:
        """Test subscribe_fill sends correct subscription message."""
        manager = PionexWebSocketManager(api_key="test_key", api_secret="test_secret")

        mock_ws = AsyncMock()
        manager._private_ws = mock_ws
        manager._private_connected = True

        await manager.subscribe_fill("ETH_USDT")

        mock_ws.send.assert_called_once()
        sent_message = json.loads(mock_ws.send.call_args[0][0])

        assert sent_message["op"] == "SUBSCRIBE"
        assert sent_message["topic"] == "FILL"
        assert sent_message["symbol"] == "ETH_USDT"

    @pytest.mark.asyncio
    async def test_subscribe_fill_tracks_subscription(self) -> None:
        """Test subscribe_fill adds subscription to tracking list."""
        manager = PionexWebSocketManager(api_key="test_key", api_secret="test_secret")

        mock_ws = AsyncMock()
        manager._private_ws = mock_ws
        manager._private_connected = True

        await manager.subscribe_fill("ETH_USDT")

        assert len(manager.private_subscriptions) == 1
        sub = manager.private_subscriptions[0]
        assert sub.topic == WebSocketTopic.FILL
        assert sub.symbol == "ETH_USDT"

    @pytest.mark.asyncio
    async def test_subscribe_balance_sends_correct_message(self) -> None:
        """Test subscribe_balance sends correct subscription message."""
        manager = PionexWebSocketManager(api_key="test_key", api_secret="test_secret")

        mock_ws = AsyncMock()
        manager._private_ws = mock_ws
        manager._private_connected = True

        await manager.subscribe_balance()

        mock_ws.send.assert_called_once()
        sent_message = json.loads(mock_ws.send.call_args[0][0])

        assert sent_message["op"] == "SUBSCRIBE"
        assert sent_message["topic"] == "BALANCE"

    @pytest.mark.asyncio
    async def test_subscribe_balance_tracks_subscription(self) -> None:
        """Test subscribe_balance adds subscription to tracking list."""
        manager = PionexWebSocketManager(api_key="test_key", api_secret="test_secret")

        mock_ws = AsyncMock()
        manager._private_ws = mock_ws
        manager._private_connected = True

        await manager.subscribe_balance()

        assert len(manager.private_subscriptions) == 1
        sub = manager.private_subscriptions[0]
        assert sub.topic == WebSocketTopic.BALANCE
        assert sub.symbol is None


class TestAuthentication:
    """Tests for WebSocket authentication.

    Requirements:
        - 6.7: HMAC-SHA256 authentication for private connections
    """

    @pytest.mark.asyncio
    async def test_authenticate_sends_correct_message_format(self) -> None:
        """Test authentication sends message with correct format."""
        manager = PionexWebSocketManager(api_key="test_key", api_secret="test_secret")

        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(return_value=json.dumps(SAMPLE_AUTH_SUCCESS_RESPONSE))
        manager._private_ws = mock_ws

        await manager._authenticate()

        mock_ws.send.assert_called_once()
        sent_message = json.loads(mock_ws.send.call_args[0][0])

        assert sent_message["op"] == "AUTH"
        assert sent_message["key"] == "test_key"
        assert "timestamp" in sent_message
        assert "sign" in sent_message

    @pytest.mark.asyncio
    async def test_authenticate_signature_is_hmac_sha256(self) -> None:
        """Test authentication signature is HMAC-SHA256."""
        import hashlib
        import hmac

        manager = PionexWebSocketManager(api_key="test_key", api_secret="test_secret")

        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(return_value=json.dumps(SAMPLE_AUTH_SUCCESS_RESPONSE))
        manager._private_ws = mock_ws

        await manager._authenticate()

        sent_message = json.loads(mock_ws.send.call_args[0][0])
        timestamp = sent_message["timestamp"]
        signature = sent_message["sign"]

        # Verify signature format (64 hex characters for SHA256)
        assert len(signature) == 64
        assert all(c in "0123456789abcdef" for c in signature)

        # Verify signature is correct
        message = f"timestamp={timestamp}"
        expected_signature = hmac.new(
            key=b"test_secret",
            msg=message.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        assert signature == expected_signature

    @pytest.mark.asyncio
    async def test_authenticate_raises_on_failure(self) -> None:
        """Test authentication raises ConnectionError on failure."""
        manager = PionexWebSocketManager(api_key="test_key", api_secret="test_secret")

        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(return_value=json.dumps(SAMPLE_AUTH_FAILURE_RESPONSE))
        manager._private_ws = mock_ws

        with pytest.raises(ConnectionError, match="Authentication failed"):
            await manager._authenticate()

    @pytest.mark.asyncio
    async def test_authenticate_raises_without_credentials(self) -> None:
        """Test authentication raises ValueError without credentials."""
        manager = PionexWebSocketManager()

        mock_ws = AsyncMock()
        manager._private_ws = mock_ws

        with pytest.raises(ValueError, match="credentials missing"):
            await manager._authenticate()

    @pytest.mark.asyncio
    async def test_connect_private_requires_credentials(self) -> None:
        """Test connect_private raises ValueError without credentials."""
        manager = PionexWebSocketManager()

        with pytest.raises(ValueError, match="API key and secret required"):
            await manager.connect_private()


class TestOrderMessageParsing:
    """Tests for order message parsing.

    Requirements:
        - 6.4: Order update includes orderId, symbol, type, side, price, size,
               filledSize, filledAmount, fee, status, clientOrderId
    """

    @pytest.mark.asyncio
    async def test_order_message_parsed_correctly(self) -> None:
        """Test order message is parsed into OrderDetail object."""
        received_order: OrderDetail | None = None

        async def on_order(order: OrderDetail) -> None:
            nonlocal received_order
            received_order = order

        manager = PionexWebSocketManager(on_order=on_order)

        await manager._process_private_message(json.dumps(SAMPLE_ORDER_MESSAGE))

        assert received_order is not None
        assert received_order.order_id == 123456789
        assert received_order.symbol == "BTC_USDT"
        assert received_order.order_type == OrderType.LIMIT
        assert received_order.side == OrderSide.BUY
        assert received_order.price == Decimal("35000.00")
        assert received_order.size == Decimal("0.001")

    @pytest.mark.asyncio
    async def test_order_message_parses_fill_info(self) -> None:
        """Test order message parses fill information correctly."""
        received_order: OrderDetail | None = None

        async def on_order(order: OrderDetail) -> None:
            nonlocal received_order
            received_order = order

        manager = PionexWebSocketManager(on_order=on_order)

        await manager._process_private_message(json.dumps(SAMPLE_ORDER_MESSAGE))

        assert received_order is not None
        assert received_order.filled_size == Decimal("0.0005")
        assert received_order.filled_amount == Decimal("17.50")
        assert received_order.fee == Decimal("0.0175")
        assert received_order.fee_coin == "USDT"

    @pytest.mark.asyncio
    async def test_order_message_parses_status(self) -> None:
        """Test order message parses status correctly."""
        received_order: OrderDetail | None = None

        async def on_order(order: OrderDetail) -> None:
            nonlocal received_order
            received_order = order

        manager = PionexWebSocketManager(on_order=on_order)

        await manager._process_private_message(json.dumps(SAMPLE_ORDER_MESSAGE))

        assert received_order is not None
        assert received_order.status == OrderDetailStatus.OPEN
        assert received_order.ioc is False
        assert received_order.client_order_id == "my-order-001"
        assert received_order.source == "API"

    @pytest.mark.asyncio
    async def test_order_message_parses_timestamps(self) -> None:
        """Test order message parses timestamps correctly."""
        received_order: OrderDetail | None = None

        async def on_order(order: OrderDetail) -> None:
            nonlocal received_order
            received_order = order

        manager = PionexWebSocketManager(on_order=on_order)

        await manager._process_private_message(json.dumps(SAMPLE_ORDER_MESSAGE))

        assert received_order is not None
        assert received_order.create_time == datetime.fromtimestamp(1700000000, tz=UTC)
        assert received_order.update_time == datetime.fromtimestamp(1700000100, tz=UTC)

    @pytest.mark.asyncio
    async def test_order_callback_not_called_when_not_set(self) -> None:
        """Test no error when order callback is not set."""
        manager = PionexWebSocketManager()

        # Should not raise any exception
        await manager._process_private_message(json.dumps(SAMPLE_ORDER_MESSAGE))


class TestFillMessageParsing:
    """Tests for fill message parsing.

    Requirements:
        - 6.5: Fill includes id, orderId, symbol, side, role, price, size,
               fee, feeCoin, timestamp
    """

    @pytest.mark.asyncio
    async def test_fill_message_parsed_correctly(self) -> None:
        """Test fill message is parsed into Fill object."""
        received_fill: Fill | None = None

        async def on_fill(fill: Fill) -> None:
            nonlocal received_fill
            received_fill = fill

        manager = PionexWebSocketManager(on_fill=on_fill)

        await manager._process_private_message(json.dumps(SAMPLE_FILL_MESSAGE))

        assert received_fill is not None
        assert received_fill.id == 987654321
        assert received_fill.order_id == 123456789
        assert received_fill.symbol == "BTC_USDT"
        assert received_fill.side == OrderSide.BUY
        assert received_fill.role == FillRole.TAKER

    @pytest.mark.asyncio
    async def test_fill_message_parses_trade_info(self) -> None:
        """Test fill message parses trade information correctly."""
        received_fill: Fill | None = None

        async def on_fill(fill: Fill) -> None:
            nonlocal received_fill
            received_fill = fill

        manager = PionexWebSocketManager(on_fill=on_fill)

        await manager._process_private_message(json.dumps(SAMPLE_FILL_MESSAGE))

        assert received_fill is not None
        assert received_fill.price == Decimal("35000.00")
        assert received_fill.size == Decimal("0.0005")
        assert received_fill.fee == Decimal("0.0175")
        assert received_fill.fee_coin == "USDT"

    @pytest.mark.asyncio
    async def test_fill_message_parses_maker_role(self) -> None:
        """Test fill message parses MAKER role correctly."""
        received_fill: Fill | None = None

        async def on_fill(fill: Fill) -> None:
            nonlocal received_fill
            received_fill = fill

        manager = PionexWebSocketManager(on_fill=on_fill)

        maker_fill_message = {
            "topic": "FILL",
            "data": {
                "id": 987654322,
                "orderId": 123456789,
                "symbol": "BTC_USDT",
                "side": "SELL",
                "role": "MAKER",
                "price": "35100.00",
                "size": "0.001",
                "fee": "0.0175",
                "feeCoin": "USDT",
                "timestamp": 1700000100000,
            },
        }

        await manager._process_private_message(json.dumps(maker_fill_message))

        assert received_fill is not None
        assert received_fill.role == FillRole.MAKER
        assert received_fill.side == OrderSide.SELL

    @pytest.mark.asyncio
    async def test_fill_message_parses_timestamp(self) -> None:
        """Test fill message parses timestamp correctly."""
        received_fill: Fill | None = None

        async def on_fill(fill: Fill) -> None:
            nonlocal received_fill
            received_fill = fill

        manager = PionexWebSocketManager(on_fill=on_fill)

        await manager._process_private_message(json.dumps(SAMPLE_FILL_MESSAGE))

        assert received_fill is not None
        assert received_fill.timestamp == datetime.fromtimestamp(1700000050, tz=UTC)

    @pytest.mark.asyncio
    async def test_fill_callback_not_called_when_not_set(self) -> None:
        """Test no error when fill callback is not set."""
        manager = PionexWebSocketManager()

        # Should not raise any exception
        await manager._process_private_message(json.dumps(SAMPLE_FILL_MESSAGE))


class TestBalanceMessageParsing:
    """Tests for balance message parsing.

    Requirements:
        - 6.6: Balance update includes balances array with coin, free, frozen
    """

    @pytest.mark.asyncio
    async def test_balance_message_parsed_correctly(self) -> None:
        """Test balance message is parsed into BalanceUpdate object."""
        received_balance: BalanceUpdate | None = None

        async def on_balance(balance: BalanceUpdate) -> None:
            nonlocal received_balance
            received_balance = balance

        manager = PionexWebSocketManager(on_balance=on_balance)

        await manager._process_private_message(json.dumps(SAMPLE_BALANCE_MESSAGE))

        assert received_balance is not None
        assert len(received_balance.balances) == 2

    @pytest.mark.asyncio
    async def test_balance_message_parses_currencies(self) -> None:
        """Test balance message parses currency balances correctly."""
        received_balance: BalanceUpdate | None = None

        async def on_balance(balance: BalanceUpdate) -> None:
            nonlocal received_balance
            received_balance = balance

        manager = PionexWebSocketManager(on_balance=on_balance)

        await manager._process_private_message(json.dumps(SAMPLE_BALANCE_MESSAGE))

        assert received_balance is not None

        # BTC balance
        btc_balance = next(b for b in received_balance.balances if b.currency == "BTC")
        assert btc_balance.free == Decimal("1.5")
        assert btc_balance.locked == Decimal("0.5")

        # USDT balance
        usdt_balance = next(b for b in received_balance.balances if b.currency == "USDT")
        assert usdt_balance.free == Decimal("10000.00")
        assert usdt_balance.locked == Decimal("500.00")

    @pytest.mark.asyncio
    async def test_balance_message_parses_timestamp(self) -> None:
        """Test balance message parses timestamp correctly."""
        received_balance: BalanceUpdate | None = None

        async def on_balance(balance: BalanceUpdate) -> None:
            nonlocal received_balance
            received_balance = balance

        manager = PionexWebSocketManager(on_balance=on_balance)

        await manager._process_private_message(json.dumps(SAMPLE_BALANCE_MESSAGE))

        assert received_balance is not None
        assert received_balance.timestamp == datetime.fromtimestamp(1700000000, tz=UTC)

    @pytest.mark.asyncio
    async def test_balance_callback_not_called_when_not_set(self) -> None:
        """Test no error when balance callback is not set."""
        manager = PionexWebSocketManager()

        # Should not raise any exception
        await manager._process_private_message(json.dumps(SAMPLE_BALANCE_MESSAGE))

    @pytest.mark.asyncio
    async def test_balance_empty_balances_handled(self) -> None:
        """Test balance message with empty balances is handled."""
        received_balance: BalanceUpdate | None = None

        async def on_balance(balance: BalanceUpdate) -> None:
            nonlocal received_balance
            received_balance = balance

        manager = PionexWebSocketManager(on_balance=on_balance)

        empty_balance_message = {
            "topic": "BALANCE",
            "data": {
                "balances": [],
                "timestamp": 1700000000000,
            },
        }

        await manager._process_private_message(json.dumps(empty_balance_message))

        assert received_balance is not None
        assert len(received_balance.balances) == 0


class TestPrivateMessageHandling:
    """Tests for private message handling."""

    @pytest.mark.asyncio
    async def test_auth_confirmation_handled(self) -> None:
        """Test AUTH confirmation message is handled without error."""
        manager = PionexWebSocketManager()

        auth_message = {"op": "AUTH", "success": True}

        # Should not raise any exception
        await manager._process_private_message(json.dumps(auth_message))

    @pytest.mark.asyncio
    async def test_subscribe_confirmation_handled(self) -> None:
        """Test SUBSCRIBE confirmation message is handled without error."""
        manager = PionexWebSocketManager()

        subscribe_message = {"op": "SUBSCRIBE", "success": True, "topic": "ORDER"}

        # Should not raise any exception
        await manager._process_private_message(json.dumps(subscribe_message))

    @pytest.mark.asyncio
    async def test_pong_message_handled(self) -> None:
        """Test PONG message is handled without error."""
        manager = PionexWebSocketManager()

        pong_message = {"op": "PONG"}

        # Should not raise any exception
        await manager._process_private_message(json.dumps(pong_message))

    @pytest.mark.asyncio
    async def test_unknown_message_handled(self) -> None:
        """Test unknown message is handled without error."""
        manager = PionexWebSocketManager()

        unknown_message = {"unknown": "data"}

        # Should not raise any exception
        await manager._process_private_message(json.dumps(unknown_message))

    @pytest.mark.asyncio
    async def test_invalid_json_handled(self) -> None:
        """Test invalid JSON is handled without raising exception."""
        manager = PionexWebSocketManager()

        # Should not raise any exception
        await manager._process_private_message("not valid json")



# =============================================================================
# Test Classes for Reconnection Logic
# =============================================================================


class TestReconnectionLogic:
    """Tests for WebSocket reconnection logic.

    Requirements:
        - 5.5: Automatic reconnection with exponential backoff (1s, 2s, 4s, 8s, max 30s)
    """

    def test_initial_reconnect_delay_is_correct(self) -> None:
        """Test initial reconnection delay is INITIAL_RECONNECT_DELAY."""
        manager = PionexWebSocketManager()

        assert manager.get_reconnect_delay(is_private=False) == INITIAL_RECONNECT_DELAY
        assert manager.get_reconnect_delay(is_private=True) == INITIAL_RECONNECT_DELAY

    def test_reconnect_delay_increases_exponentially(self) -> None:
        """Test reconnection delay increases with exponential backoff."""
        manager = PionexWebSocketManager()

        # Simulate first failure
        manager._public_reconnect_delay = (
            manager._public_reconnect_delay * RECONNECT_MULTIPLIER
        )
        assert manager.get_reconnect_delay(is_private=False) == 2.0

        # Simulate second failure
        manager._public_reconnect_delay = (
            manager._public_reconnect_delay * RECONNECT_MULTIPLIER
        )
        assert manager.get_reconnect_delay(is_private=False) == 4.0

        # Simulate third failure
        manager._public_reconnect_delay = (
            manager._public_reconnect_delay * RECONNECT_MULTIPLIER
        )
        assert manager.get_reconnect_delay(is_private=False) == 8.0

    def test_reconnect_delay_capped_at_max(self) -> None:
        """Test reconnection delay is capped at MAX_RECONNECT_DELAY."""
        manager = PionexWebSocketManager()

        # Simulate many failures
        for _ in range(10):
            manager._public_reconnect_delay = min(
                manager._public_reconnect_delay * RECONNECT_MULTIPLIER,
                MAX_RECONNECT_DELAY,
            )

        assert manager.get_reconnect_delay(is_private=False) == MAX_RECONNECT_DELAY

    def test_reset_reconnect_delay_restores_initial(self) -> None:
        """Test reset_reconnect_delay restores initial delay."""
        manager = PionexWebSocketManager()

        # Increase delay
        manager._public_reconnect_delay = MAX_RECONNECT_DELAY
        manager._private_reconnect_delay = MAX_RECONNECT_DELAY

        # Reset public
        manager.reset_reconnect_delay(is_private=False)
        assert manager.get_reconnect_delay(is_private=False) == INITIAL_RECONNECT_DELAY
        assert manager.get_reconnect_delay(is_private=True) == MAX_RECONNECT_DELAY

        # Reset private
        manager.reset_reconnect_delay(is_private=True)
        assert manager.get_reconnect_delay(is_private=True) == INITIAL_RECONNECT_DELAY

    def test_public_private_delays_independent(self) -> None:
        """Test public and private reconnection delays are independent."""
        manager = PionexWebSocketManager()

        # Increase public delay
        manager._public_reconnect_delay = MAX_RECONNECT_DELAY

        # Private should still be initial
        assert manager.get_reconnect_delay(is_private=True) == INITIAL_RECONNECT_DELAY

        # Increase private delay
        manager._private_reconnect_delay = 8.0

        # Public should still be max
        assert manager.get_reconnect_delay(is_private=False) == MAX_RECONNECT_DELAY


class TestResubscription:
    """Tests for re-subscription after reconnection.

    Requirements:
        - 5.5: Re-subscribe to previous topics after reconnect
    """

    def test_subscriptions_tracked_for_resubscription(self) -> None:
        """Test subscriptions are tracked for re-subscription."""
        manager = PionexWebSocketManager()

        # Add subscriptions
        manager._public_subscriptions.append(
            Subscription(topic=WebSocketTopic.TRADE, symbol="BTC_USDT")
        )
        manager._public_subscriptions.append(
            Subscription(topic=WebSocketTopic.DEPTH, symbol="ETH_USDT", params={"limit": 50})
        )

        assert len(manager.public_subscriptions) == 2

    def test_subscriptions_copy_is_returned(self) -> None:
        """Test public_subscriptions returns a copy, not the original list."""
        manager = PionexWebSocketManager()

        manager._public_subscriptions.append(
            Subscription(topic=WebSocketTopic.TRADE, symbol="BTC_USDT")
        )

        # Get copy and modify it
        subs_copy = manager.public_subscriptions
        subs_copy.clear()

        # Original should be unchanged
        assert len(manager._public_subscriptions) == 1

    def test_private_subscriptions_tracked(self) -> None:
        """Test private subscriptions are tracked for re-subscription."""
        manager = PionexWebSocketManager()

        # Add subscriptions
        manager._private_subscriptions.append(
            Subscription(topic=WebSocketTopic.ORDER, symbol="BTC_USDT")
        )
        manager._private_subscriptions.append(
            Subscription(topic=WebSocketTopic.FILL, symbol="ETH_USDT")
        )
        manager._private_subscriptions.append(
            Subscription(topic=WebSocketTopic.BALANCE)
        )

        assert len(manager.private_subscriptions) == 3

    @pytest.mark.asyncio
    async def test_resubscribe_trade(self) -> None:
        """Test _resubscribe re-subscribes to TRADE topic."""
        manager = PionexWebSocketManager()

        mock_ws = AsyncMock()
        manager._public_ws = mock_ws
        manager._public_connected = True

        subscriptions = [
            Subscription(topic=WebSocketTopic.TRADE, symbol="BTC_USDT"),
        ]

        await manager._resubscribe(subscriptions, is_private=False)

        mock_ws.send.assert_called_once()
        sent_message = json.loads(mock_ws.send.call_args[0][0])
        assert sent_message["topic"] == "TRADE"
        assert sent_message["symbol"] == "BTC_USDT"

    @pytest.mark.asyncio
    async def test_resubscribe_depth_with_limit(self) -> None:
        """Test _resubscribe re-subscribes to DEPTH topic with limit."""
        manager = PionexWebSocketManager()

        mock_ws = AsyncMock()
        manager._public_ws = mock_ws
        manager._public_connected = True

        subscriptions = [
            Subscription(topic=WebSocketTopic.DEPTH, symbol="ETH_USDT", params={"limit": 50}),
        ]

        await manager._resubscribe(subscriptions, is_private=False)

        mock_ws.send.assert_called_once()
        sent_message = json.loads(mock_ws.send.call_args[0][0])
        assert sent_message["topic"] == "DEPTH"
        assert sent_message["symbol"] == "ETH_USDT"
        assert sent_message["limit"] == 50

    @pytest.mark.asyncio
    async def test_resubscribe_order(self) -> None:
        """Test _resubscribe re-subscribes to ORDER topic."""
        manager = PionexWebSocketManager(api_key="test_key", api_secret="test_secret")

        mock_ws = AsyncMock()
        manager._private_ws = mock_ws
        manager._private_connected = True

        subscriptions = [
            Subscription(topic=WebSocketTopic.ORDER, symbol="BTC_USDT"),
        ]

        await manager._resubscribe(subscriptions, is_private=True)

        mock_ws.send.assert_called_once()
        sent_message = json.loads(mock_ws.send.call_args[0][0])
        assert sent_message["topic"] == "ORDER"
        assert sent_message["symbol"] == "BTC_USDT"

    @pytest.mark.asyncio
    async def test_resubscribe_fill(self) -> None:
        """Test _resubscribe re-subscribes to FILL topic."""
        manager = PionexWebSocketManager(api_key="test_key", api_secret="test_secret")

        mock_ws = AsyncMock()
        manager._private_ws = mock_ws
        manager._private_connected = True

        subscriptions = [
            Subscription(topic=WebSocketTopic.FILL, symbol="ETH_USDT"),
        ]

        await manager._resubscribe(subscriptions, is_private=True)

        mock_ws.send.assert_called_once()
        sent_message = json.loads(mock_ws.send.call_args[0][0])
        assert sent_message["topic"] == "FILL"
        assert sent_message["symbol"] == "ETH_USDT"

    @pytest.mark.asyncio
    async def test_resubscribe_balance(self) -> None:
        """Test _resubscribe re-subscribes to BALANCE topic."""
        manager = PionexWebSocketManager(api_key="test_key", api_secret="test_secret")

        mock_ws = AsyncMock()
        manager._private_ws = mock_ws
        manager._private_connected = True

        subscriptions = [
            Subscription(topic=WebSocketTopic.BALANCE),
        ]

        await manager._resubscribe(subscriptions, is_private=True)

        mock_ws.send.assert_called_once()
        sent_message = json.loads(mock_ws.send.call_args[0][0])
        assert sent_message["topic"] == "BALANCE"

    @pytest.mark.asyncio
    async def test_resubscribe_multiple_subscriptions(self) -> None:
        """Test _resubscribe handles multiple subscriptions."""
        manager = PionexWebSocketManager()

        mock_ws = AsyncMock()
        manager._public_ws = mock_ws
        manager._public_connected = True

        subscriptions = [
            Subscription(topic=WebSocketTopic.TRADE, symbol="BTC_USDT"),
            Subscription(topic=WebSocketTopic.TRADE, symbol="ETH_USDT"),
            Subscription(topic=WebSocketTopic.DEPTH, symbol="BTC_USDT", params={"limit": 20}),
        ]

        await manager._resubscribe(subscriptions, is_private=False)

        assert mock_ws.send.call_count == 3


class TestConnectionState:
    """Tests for connection state management."""

    def test_is_public_connected_initially_false(self) -> None:
        """Test is_public_connected is False initially."""
        manager = PionexWebSocketManager()
        assert manager.is_public_connected is False

    def test_is_private_connected_initially_false(self) -> None:
        """Test is_private_connected is False initially."""
        manager = PionexWebSocketManager()
        assert manager.is_private_connected is False

    def test_is_public_connected_reflects_state(self) -> None:
        """Test is_public_connected reflects connection state."""
        manager = PionexWebSocketManager()

        manager._public_connected = True
        assert manager.is_public_connected is True

        manager._public_connected = False
        assert manager.is_public_connected is False

    def test_is_private_connected_reflects_state(self) -> None:
        """Test is_private_connected reflects connection state."""
        manager = PionexWebSocketManager()

        manager._private_connected = True
        assert manager.is_private_connected is True

        manager._private_connected = False
        assert manager.is_private_connected is False


class TestPingPong:
    """Tests for ping/pong functionality."""

    @pytest.mark.asyncio
    async def test_send_ping_public(self) -> None:
        """Test send_ping sends PING to public WebSocket."""
        manager = PionexWebSocketManager()

        mock_ws = AsyncMock()
        manager._public_ws = mock_ws

        await manager.send_ping(is_private=False)

        mock_ws.send.assert_called_once()
        sent_message = json.loads(mock_ws.send.call_args[0][0])
        assert sent_message["op"] == "PING"

    @pytest.mark.asyncio
    async def test_send_ping_private(self) -> None:
        """Test send_ping sends PING to private WebSocket."""
        manager = PionexWebSocketManager()

        mock_ws = AsyncMock()
        manager._private_ws = mock_ws

        await manager.send_ping(is_private=True)

        mock_ws.send.assert_called_once()
        sent_message = json.loads(mock_ws.send.call_args[0][0])
        assert sent_message["op"] == "PING"

    @pytest.mark.asyncio
    async def test_send_ping_no_op_when_not_connected(self) -> None:
        """Test send_ping does nothing when not connected."""
        manager = PionexWebSocketManager()

        # Should not raise any exception
        await manager.send_ping(is_private=False)
        await manager.send_ping(is_private=True)


class TestDisconnect:
    """Tests for disconnect functionality."""

    @pytest.mark.asyncio
    async def test_disconnect_closes_public_connection(self) -> None:
        """Test disconnect closes public WebSocket connection."""
        manager = PionexWebSocketManager()

        mock_ws = AsyncMock()
        manager._public_ws = mock_ws
        manager._public_connected = True

        await manager.disconnect()

        mock_ws.close.assert_called_once()
        assert manager._public_ws is None
        assert manager._public_connected is False

    @pytest.mark.asyncio
    async def test_disconnect_closes_private_connection(self) -> None:
        """Test disconnect closes private WebSocket connection."""
        manager = PionexWebSocketManager()

        mock_ws = AsyncMock()
        manager._private_ws = mock_ws
        manager._private_connected = True

        await manager.disconnect()

        mock_ws.close.assert_called_once()
        assert manager._private_ws is None
        assert manager._private_connected is False

    @pytest.mark.asyncio
    async def test_disconnect_sets_should_reconnect_false(self) -> None:
        """Test disconnect sets _should_reconnect to False."""
        manager = PionexWebSocketManager()

        assert manager._should_reconnect is True

        await manager.disconnect()

        assert manager._should_reconnect is False

    @pytest.mark.asyncio
    async def test_disconnect_cancels_tasks(self) -> None:
        """Test disconnect cancels message handling tasks."""
        manager = PionexWebSocketManager()

        # Create a real asyncio task that we can cancel
        async def dummy_task() -> None:
            await asyncio.sleep(100)

        # Create actual tasks
        public_task = asyncio.create_task(dummy_task())
        private_task = asyncio.create_task(dummy_task())

        manager._public_task = public_task
        manager._private_task = private_task

        await manager.disconnect()

        # Tasks should be cancelled
        assert public_task.cancelled()
        assert private_task.cancelled()
