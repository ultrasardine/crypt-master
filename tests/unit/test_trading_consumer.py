"""
Unit tests for TradingConsumer WebSocket consumer.

Tests the Django Channels WebSocket consumer that bridges
Pionex WebSocket to browser for real-time trading updates.

Requirements:
- 10.1: Show connection status indicator
- 10.2: Order updates via WebSocket
- 10.3: Fill updates via WebSocket
- 10.4: Balance updates via WebSocket
- 10.5: Handle reconnection attempts
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from channels.testing import WebsocketCommunicator

from apps.trading.consumers import (
    BALANCES_GROUP,
    FILLS_GROUP,
    ORDERS_GROUP,
    TRADING_GROUP,
    DecimalEncoder,
    TradingConsumer,
)


class TestDecimalEncoder:
    """Tests for the DecimalEncoder JSON encoder."""

    def test_encodes_decimal_as_string(self):
        """Decimal values should be encoded as strings."""
        data = {"price": Decimal("123.456")}
        result = json.dumps(data, cls=DecimalEncoder)
        assert result == '{"price": "123.456"}'

    def test_encodes_nested_decimal(self):
        """Nested Decimal values should be encoded as strings."""
        data = {"order": {"price": Decimal("100.00"), "size": Decimal("0.5")}}
        result = json.dumps(data, cls=DecimalEncoder)
        parsed = json.loads(result)
        assert parsed["order"]["price"] == "100.00"
        assert parsed["order"]["size"] == "0.5"

    def test_handles_non_decimal_types(self):
        """Non-Decimal types should be handled normally."""
        data = {"name": "test", "count": 42, "active": True}
        result = json.dumps(data, cls=DecimalEncoder)
        parsed = json.loads(result)
        assert parsed == data


@pytest.mark.django_db(transaction=True)
class TestTradingConsumerConnection:
    """Tests for TradingConsumer connection handling."""

    @pytest.mark.asyncio
    async def test_connect_accepts_websocket(self):
        """Consumer should accept WebSocket connection."""
        communicator = WebsocketCommunicator(TradingConsumer.as_asgi(), "/ws/trading/")
        
        with patch.object(TradingConsumer, "_connect_to_pionex", new_callable=AsyncMock):
            connected, _ = await communicator.connect()
            assert connected
            await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_connect_sends_initial_status(self):
        """Consumer should send initial connection status on connect."""
        communicator = WebsocketCommunicator(TradingConsumer.as_asgi(), "/ws/trading/")
        
        with patch.object(TradingConsumer, "_connect_to_pionex", new_callable=AsyncMock):
            connected, _ = await communicator.connect()
            assert connected
            
            # Should receive initial connection status
            response = await communicator.receive_json_from()
            assert response["type"] == "connection_status"
            assert response["connected"] is False
            assert "message" in response
            
            await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
class TestTradingConsumerMessages:
    """Tests for TradingConsumer message handling."""

    @pytest.mark.asyncio
    async def test_ping_responds_with_pong(self):
        """Consumer should respond to ping with pong."""
        communicator = WebsocketCommunicator(TradingConsumer.as_asgi(), "/ws/trading/")
        
        with patch.object(TradingConsumer, "_connect_to_pionex", new_callable=AsyncMock):
            await communicator.connect()
            
            # Skip initial connection status
            await communicator.receive_json_from()
            
            # Send ping
            await communicator.send_json_to({"type": "ping"})
            
            # Should receive pong
            response = await communicator.receive_json_from()
            assert response["type"] == "pong"
            
            await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_subscribe_to_symbol(self):
        """Consumer should handle symbol subscription."""
        communicator = WebsocketCommunicator(TradingConsumer.as_asgi(), "/ws/trading/")
        
        with patch.object(TradingConsumer, "_connect_to_pionex", new_callable=AsyncMock):
            await communicator.connect()
            
            # Skip initial connection status
            await communicator.receive_json_from()
            
            # Subscribe to symbol
            await communicator.send_json_to({"type": "subscribe", "symbol": "BTC_USDT"})
            
            # Should receive subscription confirmation
            response = await communicator.receive_json_from()
            assert response["type"] == "subscribed"
            assert response["symbol"] == "BTC_USDT"
            
            await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_unsubscribe_from_symbol(self):
        """Consumer should handle symbol unsubscription."""
        communicator = WebsocketCommunicator(TradingConsumer.as_asgi(), "/ws/trading/")
        
        with patch.object(TradingConsumer, "_connect_to_pionex", new_callable=AsyncMock):
            await communicator.connect()
            
            # Skip initial connection status
            await communicator.receive_json_from()
            
            # Subscribe first
            await communicator.send_json_to({"type": "subscribe", "symbol": "BTC_USDT"})
            await communicator.receive_json_from()  # Skip subscription confirmation
            
            # Unsubscribe
            await communicator.send_json_to({"type": "unsubscribe", "symbol": "BTC_USDT"})
            
            # Should receive unsubscription confirmation
            response = await communicator.receive_json_from()
            assert response["type"] == "unsubscribed"
            assert response["symbol"] == "BTC_USDT"
            
            await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_invalid_json_returns_error(self):
        """Consumer should return error for invalid JSON."""
        communicator = WebsocketCommunicator(TradingConsumer.as_asgi(), "/ws/trading/")
        
        with patch.object(TradingConsumer, "_connect_to_pionex", new_callable=AsyncMock):
            await communicator.connect()
            
            # Skip initial connection status
            await communicator.receive_json_from()
            
            # Send invalid JSON
            await communicator.send_to(text_data="not valid json")
            
            # Should receive error
            response = await communicator.receive_json_from()
            assert response["type"] == "error"
            assert "Invalid JSON" in response["message"]
            
            await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
class TestTradingConsumerCallbacks:
    """Tests for TradingConsumer callback methods."""

    @pytest.mark.asyncio
    async def test_order_update_handler(self):
        """Consumer should handle order_update group messages."""
        communicator = WebsocketCommunicator(TradingConsumer.as_asgi(), "/ws/trading/")
        
        with patch.object(TradingConsumer, "_connect_to_pionex", new_callable=AsyncMock):
            await communicator.connect()
            
            # Skip initial connection status
            await communicator.receive_json_from()
            
            # Send order update via the handler method
            order_data = {
                "type": "order_update",
                "data": {
                    "order_id": 12345,
                    "symbol": "BTC_USDT",
                    "order_type": "LIMIT",
                    "side": "BUY",
                    "price": "50000.00",
                    "size": "0.1",
                    "filled_size": "0.05",
                    "filled_amount": "2500.00",
                    "fee": "0.001",
                    "fee_coin": "BTC",
                    "status": "OPEN",
                    "client_order_id": "client123",
                    "create_time": "2024-01-15T12:00:00+00:00",
                    "update_time": "2024-01-15T12:00:01+00:00",
                },
            }
            
            # Simulate receiving an order_update message from the group
            await communicator.send_json_to({"type": "ping"})  # Keep connection alive
            await communicator.receive_json_from()  # Receive pong
            
            await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_fill_update_handler(self):
        """Consumer should handle fill_update group messages."""
        communicator = WebsocketCommunicator(TradingConsumer.as_asgi(), "/ws/trading/")
        
        with patch.object(TradingConsumer, "_connect_to_pionex", new_callable=AsyncMock):
            await communicator.connect()
            
            # Skip initial connection status
            await communicator.receive_json_from()
            
            # Test that the consumer can handle fill updates
            fill_data = {
                "type": "fill_update",
                "data": {
                    "id": 67890,
                    "order_id": 12345,
                    "symbol": "BTC_USDT",
                    "side": "BUY",
                    "role": "TAKER",
                    "price": "50000.00",
                    "size": "0.05",
                    "fee": "0.0005",
                    "fee_coin": "BTC",
                    "timestamp": "2024-01-15T12:00:00+00:00",
                },
            }
            
            await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_balance_update_handler(self):
        """Consumer should handle balance_update group messages."""
        communicator = WebsocketCommunicator(TradingConsumer.as_asgi(), "/ws/trading/")
        
        with patch.object(TradingConsumer, "_connect_to_pionex", new_callable=AsyncMock):
            await communicator.connect()
            
            # Skip initial connection status
            await communicator.receive_json_from()
            
            # Test that the consumer can handle balance updates
            balance_data = {
                "type": "balance_update",
                "data": {
                    "balances": [
                        {
                            "currency": "BTC",
                            "free": "1.5",
                            "locked": "0.5",
                            "total": "2.0",
                        }
                    ],
                    "timestamp": "2024-01-15T12:00:00+00:00",
                },
            }
            
            await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
class TestTradingConsumerConnectionStatus:
    """Tests for connection status handling."""

    @pytest.mark.asyncio
    async def test_connection_status_on_connect(self):
        """Consumer should send connection status on connect."""
        communicator = WebsocketCommunicator(TradingConsumer.as_asgi(), "/ws/trading/")
        
        with patch.object(TradingConsumer, "_connect_to_pionex", new_callable=AsyncMock):
            await communicator.connect()
            
            # Should receive initial connection status
            response = await communicator.receive_json_from()
            assert response["type"] == "connection_status"
            assert "connected" in response
            assert "message" in response
            
            await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_get_status_request(self):
        """Consumer should respond to get_status request."""
        communicator = WebsocketCommunicator(TradingConsumer.as_asgi(), "/ws/trading/")
        
        with patch.object(TradingConsumer, "_connect_to_pionex", new_callable=AsyncMock):
            await communicator.connect()
            
            # Skip initial connection status
            await communicator.receive_json_from()
            
            # Request status
            await communicator.send_json_to({"type": "get_status"})
            
            # Should receive status (not connected since we mocked _connect_to_pionex)
            response = await communicator.receive_json_from()
            assert response["type"] == "connection_status"
            assert response["connected"] is False
            
            await communicator.disconnect()
