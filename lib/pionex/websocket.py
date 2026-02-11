"""
Pionex WebSocket Manager.

This module provides WebSocket connectivity for real-time data streams
from the Pionex exchange, including public market data and private
account updates.

Requirements:
- 5.1: Subscribe to TRADE topic for real-time trade data
- 5.2: Subscribe to DEPTH topic with configurable limit
- 5.3: Trade data includes symbol, tradeId, price, size, side, timestamp
- 5.4: Depth data includes bids and asks arrays
- 5.5: Automatic reconnection with exponential backoff
- 6.1: Subscribe to ORDER topic with authentication
- 6.2: Subscribe to FILL topic with authentication
- 6.3: Subscribe to BALANCE topic with authentication
- 6.4: Order update message format
- 6.5: Fill message format
- 6.6: Balance update message format
- 6.7: HMAC-SHA256 authentication for private connections
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Coroutine

import websockets
from websockets.asyncio.client import ClientConnection
from websockets.exceptions import ConnectionClosed

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

logger = logging.getLogger(__name__)


# WebSocket URLs
PUBLIC_WS_URL = "wss://ws.pionex.com/ws"
PRIVATE_WS_URL = "wss://ws.pionex.com/wsPri"

# Reconnection configuration
INITIAL_RECONNECT_DELAY = 1.0  # seconds
MAX_RECONNECT_DELAY = 30.0  # seconds
RECONNECT_MULTIPLIER = 2.0


class WebSocketTopic(Enum):
    """WebSocket subscription topics."""

    # Public topics
    TRADE = "TRADE"
    DEPTH = "DEPTH"

    # Private topics
    ORDER = "ORDER"
    FILL = "FILL"
    BALANCE = "BALANCE"


@dataclass
class Subscription:
    """Represents an active WebSocket subscription."""

    topic: WebSocketTopic
    symbol: str | None = None
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class BalanceUpdate:
    """Balance update from WebSocket stream."""

    balances: list[Balance]
    timestamp: datetime

    @classmethod
    def from_ws_message(cls, data: dict[str, Any]) -> BalanceUpdate:
        """Create BalanceUpdate from WebSocket message data."""
        balances = []
        for item in data.get("balances", []):
            balances.append(
                Balance(
                    currency=item.get("coin", ""),
                    free=Decimal(str(item.get("free", "0"))),
                    locked=Decimal(str(item.get("frozen", "0"))),
                )
            )

        timestamp_ms = data.get("timestamp", int(time.time() * 1000))
        timestamp = datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=UTC)

        return cls(balances=balances, timestamp=timestamp)


# Type aliases for callbacks
TradeCallback = Callable[[Trade], Coroutine[Any, Any, None]]
DepthCallback = Callable[[OrderBook], Coroutine[Any, Any, None]]
OrderCallback = Callable[[OrderDetail], Coroutine[Any, Any, None]]
FillCallback = Callable[[Fill], Coroutine[Any, Any, None]]
BalanceCallback = Callable[[BalanceUpdate], Coroutine[Any, Any, None]]


class PionexWebSocketManager:
    """
    Manages WebSocket connections to Pionex for real-time data.

    Public streams (no auth): TRADE, DEPTH
    Private streams (auth required): ORDER, FILL, BALANCE

    The manager handles:
    - Connection establishment and authentication
    - Subscription management
    - Message parsing and callback dispatch
    - Automatic reconnection with exponential backoff
    - Re-subscription after reconnection

    Example:
        >>> async def on_trade(trade: Trade):
        ...     print(f"Trade: {trade.symbol} {trade.price}")
        ...
        >>> manager = PionexWebSocketManager(
        ...     api_key="key",
        ...     api_secret="secret",
        ...     on_trade=on_trade,
        ... )
        >>> await manager.connect_public()
        >>> await manager.subscribe_trade("BTC_USDT")

    Requirements:
        - 5.1, 5.2: Public stream subscriptions
        - 6.1, 6.2, 6.3: Private stream subscriptions
        - 6.7: HMAC-SHA256 authentication
        - 5.5: Automatic reconnection with exponential backoff
    """

    PUBLIC_WS_URL = PUBLIC_WS_URL
    PRIVATE_WS_URL = PRIVATE_WS_URL

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        on_trade: TradeCallback | None = None,
        on_depth: DepthCallback | None = None,
        on_order: OrderCallback | None = None,
        on_fill: FillCallback | None = None,
        on_balance: BalanceCallback | None = None,
    ) -> None:
        """
        Initialize the WebSocket manager.

        Args:
            api_key: Pionex API key (required for private streams)
            api_secret: Pionex API secret (required for private streams)
            on_trade: Callback for trade updates
            on_depth: Callback for depth updates
            on_order: Callback for order updates (private)
            on_fill: Callback for fill updates (private)
            on_balance: Callback for balance updates (private)
        """
        self._api_key = api_key
        self._api_secret = api_secret

        # Callbacks
        self._on_trade = on_trade
        self._on_depth = on_depth
        self._on_order = on_order
        self._on_fill = on_fill
        self._on_balance = on_balance

        # Connection state
        self._public_ws: ClientConnection | None = None
        self._private_ws: ClientConnection | None = None
        self._public_connected = False
        self._private_connected = False

        # Subscription tracking for reconnection
        self._public_subscriptions: list[Subscription] = []
        self._private_subscriptions: list[Subscription] = []

        # Reconnection state
        self._public_reconnect_delay = INITIAL_RECONNECT_DELAY
        self._private_reconnect_delay = INITIAL_RECONNECT_DELAY
        self._should_reconnect = True

        # Message handling tasks
        self._public_task: asyncio.Task[None] | None = None
        self._private_task: asyncio.Task[None] | None = None


    # =========================================================================
    # Connection Methods
    # =========================================================================

    async def connect_public(self) -> None:
        """
        Connect to the public WebSocket endpoint.

        Establishes a connection to the public WebSocket for market data
        streams (TRADE, DEPTH).

        Requirements:
            - 5.1: Connect to public WebSocket for TRADE topic
            - 5.2: Connect to public WebSocket for DEPTH topic
        """
        if self._public_connected:
            logger.debug("Public WebSocket already connected")
            return

        try:
            logger.info(f"Connecting to public WebSocket: {self.PUBLIC_WS_URL}")
            self._public_ws = await websockets.connect(self.PUBLIC_WS_URL)
            self._public_connected = True
            self._public_reconnect_delay = INITIAL_RECONNECT_DELAY

            # Start message handling task
            self._public_task = asyncio.create_task(
                self._handle_public_messages(),
                name="pionex_public_ws",
            )

            logger.info("Public WebSocket connected successfully")

        except Exception as e:
            logger.error(f"Failed to connect to public WebSocket: {e}")
            self._public_connected = False
            raise

    async def connect_private(self) -> None:
        """
        Connect to the private WebSocket endpoint with authentication.

        Establishes a connection to the private WebSocket for account
        streams (ORDER, FILL, BALANCE) and authenticates using HMAC-SHA256.

        Raises:
            ValueError: If API key or secret is not provided

        Requirements:
            - 6.1, 6.2, 6.3: Connect to private WebSocket
            - 6.7: Authenticate using HMAC-SHA256 signature
        """
        if self._private_connected:
            logger.debug("Private WebSocket already connected")
            return

        if not self._api_key or not self._api_secret:
            raise ValueError("API key and secret required for private WebSocket")

        try:
            logger.info(f"Connecting to private WebSocket: {self.PRIVATE_WS_URL}")
            self._private_ws = await websockets.connect(self.PRIVATE_WS_URL)

            # Authenticate
            await self._authenticate()

            self._private_connected = True
            self._private_reconnect_delay = INITIAL_RECONNECT_DELAY

            # Start message handling task
            self._private_task = asyncio.create_task(
                self._handle_private_messages(),
                name="pionex_private_ws",
            )

            logger.info("Private WebSocket connected and authenticated successfully")

        except Exception as e:
            logger.error(f"Failed to connect to private WebSocket: {e}")
            self._private_connected = False
            raise


    async def _authenticate(self) -> None:
        """
        Authenticate the private WebSocket connection.

        Sends an authentication message with HMAC-SHA256 signature.

        Requirements:
            - 6.7: HMAC-SHA256 authentication for private connections
        """
        if not self._private_ws or not self._api_key or not self._api_secret:
            raise ValueError("Private WebSocket not connected or credentials missing")

        timestamp = int(time.time() * 1000)

        # Build signature message: "timestamp={timestamp}"
        message = f"timestamp={timestamp}"
        signature = hmac.new(
            key=self._api_secret.encode("utf-8"),
            msg=message.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        auth_message = {
            "op": "AUTH",
            "key": self._api_key,
            "timestamp": timestamp,
            "sign": signature,
        }

        await self._private_ws.send(json.dumps(auth_message))
        logger.debug("Sent authentication message to private WebSocket")

        # Wait for auth response
        response = await self._private_ws.recv()
        data = json.loads(response)

        if data.get("op") == "AUTH" and data.get("success"):
            logger.info("Private WebSocket authentication successful")
        else:
            error_msg = data.get("message", "Unknown authentication error")
            logger.error(f"Private WebSocket authentication failed: {error_msg}")
            raise ConnectionError(f"Authentication failed: {error_msg}")

    async def disconnect(self) -> None:
        """
        Disconnect from all WebSocket connections.

        Closes both public and private connections and cancels
        message handling tasks.
        """
        self._should_reconnect = False

        # Cancel tasks
        if self._public_task and not self._public_task.done():
            self._public_task.cancel()
            try:
                await self._public_task
            except asyncio.CancelledError:
                pass

        if self._private_task and not self._private_task.done():
            self._private_task.cancel()
            try:
                await self._private_task
            except asyncio.CancelledError:
                pass

        # Close connections
        if self._public_ws:
            await self._public_ws.close()
            self._public_ws = None
            self._public_connected = False

        if self._private_ws:
            await self._private_ws.close()
            self._private_ws = None
            self._private_connected = False

        logger.info("WebSocket connections closed")


    # =========================================================================
    # Public Stream Subscriptions
    # =========================================================================

    async def subscribe_trade(self, symbol: str) -> None:
        """
        Subscribe to trade stream for a symbol.

        Receives real-time trade data including price, size, and side.

        Args:
            symbol: Trading pair symbol (e.g., "BTC_USDT")

        Requirements:
            - 5.1: Subscribe to TRADE topic
            - 5.3: Trade data includes symbol, tradeId, price, size, side, timestamp
        """
        if not self._public_connected:
            await self.connect_public()

        subscription = Subscription(
            topic=WebSocketTopic.TRADE,
            symbol=symbol,
        )

        message = {
            "op": "SUBSCRIBE",
            "topic": "TRADE",
            "symbol": symbol,
        }

        if self._public_ws:
            await self._public_ws.send(json.dumps(message))
            self._public_subscriptions.append(subscription)
            logger.info(f"Subscribed to TRADE stream for {symbol}")

    async def subscribe_depth(self, symbol: str, limit: int = 20) -> None:
        """
        Subscribe to depth stream for a symbol.

        Receives real-time order book updates with configurable depth.

        Args:
            symbol: Trading pair symbol (e.g., "BTC_USDT")
            limit: Number of price levels (1-100, default: 20)

        Requirements:
            - 5.2: Subscribe to DEPTH topic with configurable limit
            - 5.4: Depth data includes bids and asks arrays
        """
        if not self._public_connected:
            await self.connect_public()

        # Clamp limit to valid range
        limit = max(1, min(100, limit))

        subscription = Subscription(
            topic=WebSocketTopic.DEPTH,
            symbol=symbol,
            params={"limit": limit},
        )

        message = {
            "op": "SUBSCRIBE",
            "topic": "DEPTH",
            "symbol": symbol,
            "limit": limit,
        }

        if self._public_ws:
            await self._public_ws.send(json.dumps(message))
            self._public_subscriptions.append(subscription)
            logger.info(f"Subscribed to DEPTH stream for {symbol} (limit={limit})")


    # =========================================================================
    # Private Stream Subscriptions
    # =========================================================================

    async def subscribe_order(self, symbol: str) -> None:
        """
        Subscribe to order updates for a symbol.

        Receives real-time order status updates including fills.

        Args:
            symbol: Trading pair symbol (e.g., "BTC_USDT")

        Requirements:
            - 6.1: Subscribe to ORDER topic with authentication
            - 6.4: Order update message format
        """
        if not self._private_connected:
            await self.connect_private()

        subscription = Subscription(
            topic=WebSocketTopic.ORDER,
            symbol=symbol,
        )

        message = {
            "op": "SUBSCRIBE",
            "topic": "ORDER",
            "symbol": symbol,
        }

        if self._private_ws:
            await self._private_ws.send(json.dumps(message))
            self._private_subscriptions.append(subscription)
            logger.info(f"Subscribed to ORDER stream for {symbol}")

    async def subscribe_fill(self, symbol: str) -> None:
        """
        Subscribe to fill updates for a symbol.

        Receives real-time fill notifications when orders are executed.

        Args:
            symbol: Trading pair symbol (e.g., "BTC_USDT")

        Requirements:
            - 6.2: Subscribe to FILL topic with authentication
            - 6.5: Fill message format
        """
        if not self._private_connected:
            await self.connect_private()

        subscription = Subscription(
            topic=WebSocketTopic.FILL,
            symbol=symbol,
        )

        message = {
            "op": "SUBSCRIBE",
            "topic": "FILL",
            "symbol": symbol,
        }

        if self._private_ws:
            await self._private_ws.send(json.dumps(message))
            self._private_subscriptions.append(subscription)
            logger.info(f"Subscribed to FILL stream for {symbol}")

    async def subscribe_balance(self) -> None:
        """
        Subscribe to balance updates.

        Receives real-time balance changes for all currencies.

        Requirements:
            - 6.3: Subscribe to BALANCE topic with authentication
            - 6.6: Balance update message format
        """
        if not self._private_connected:
            await self.connect_private()

        subscription = Subscription(
            topic=WebSocketTopic.BALANCE,
        )

        message = {
            "op": "SUBSCRIBE",
            "topic": "BALANCE",
        }

        if self._private_ws:
            await self._private_ws.send(json.dumps(message))
            self._private_subscriptions.append(subscription)
            logger.info("Subscribed to BALANCE stream")


    # =========================================================================
    # Message Handling
    # =========================================================================

    async def _handle_public_messages(self) -> None:
        """
        Handle incoming messages from the public WebSocket.

        Parses messages and dispatches to appropriate callbacks.
        Handles reconnection on connection loss.
        """
        while self._should_reconnect:
            try:
                if not self._public_ws:
                    break

                async for message in self._public_ws:
                    await self._process_public_message(message)

            except ConnectionClosed as e:
                logger.warning(f"Public WebSocket connection closed: {e}")
                self._public_connected = False
                if self._should_reconnect:
                    await self._reconnect(is_private=False)

            except Exception as e:
                logger.error(f"Error handling public WebSocket message: {e}")
                if self._should_reconnect:
                    await asyncio.sleep(1)

    async def _handle_private_messages(self) -> None:
        """
        Handle incoming messages from the private WebSocket.

        Parses messages and dispatches to appropriate callbacks.
        Handles reconnection on connection loss.
        """
        while self._should_reconnect:
            try:
                if not self._private_ws:
                    break

                async for message in self._private_ws:
                    await self._process_private_message(message)

            except ConnectionClosed as e:
                logger.warning(f"Private WebSocket connection closed: {e}")
                self._private_connected = False
                if self._should_reconnect:
                    await self._reconnect(is_private=True)

            except Exception as e:
                logger.error(f"Error handling private WebSocket message: {e}")
                if self._should_reconnect:
                    await asyncio.sleep(1)

    async def _process_public_message(self, message: str) -> None:
        """Process a message from the public WebSocket."""
        try:
            data = json.loads(message)
            topic = data.get("topic")

            if topic == "TRADE":
                await self._handle_trade_message(data)
            elif topic == "DEPTH":
                await self._handle_depth_message(data)
            elif data.get("op") == "SUBSCRIBE":
                # Subscription confirmation
                logger.debug(f"Subscription confirmed: {data}")
            elif data.get("op") == "PONG":
                # Ping/pong response
                pass
            else:
                logger.debug(f"Unknown public message: {data}")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse public WebSocket message: {e}")

    async def _process_private_message(self, message: str) -> None:
        """Process a message from the private WebSocket."""
        try:
            data = json.loads(message)
            topic = data.get("topic")

            if topic == "ORDER":
                await self._handle_order_message(data)
            elif topic == "FILL":
                await self._handle_fill_message(data)
            elif topic == "BALANCE":
                await self._handle_balance_message(data)
            elif data.get("op") in ("AUTH", "SUBSCRIBE", "PONG"):
                # Auth/subscription confirmation or ping/pong
                logger.debug(f"Private message: {data.get('op')}")
            else:
                logger.debug(f"Unknown private message: {data}")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse private WebSocket message: {e}")


    async def _handle_trade_message(self, data: dict[str, Any]) -> None:
        """
        Handle a trade message from the WebSocket.

        Requirements:
            - 5.3: Trade data includes symbol, tradeId, price, size, side, timestamp
        """
        if not self._on_trade:
            return

        try:
            trade_data = data.get("data", {})
            symbol = data.get("symbol", trade_data.get("symbol", ""))

            # Parse side
            side_str = str(trade_data.get("side", "BUY")).upper()
            side = OrderSide.BUY if side_str == "BUY" else OrderSide.SELL

            # Parse timestamp
            timestamp_ms = trade_data.get("timestamp", int(time.time() * 1000))
            timestamp = datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=UTC)

            trade = Trade(
                trade_id=str(trade_data.get("tradeId", trade_data.get("id", ""))),
                symbol=symbol,
                price=Decimal(str(trade_data.get("price", "0"))),
                quantity=Decimal(str(trade_data.get("size", trade_data.get("amount", "0")))),
                side=side,
                timestamp=timestamp,
            )

            await self._on_trade(trade)

        except Exception as e:
            logger.error(f"Error processing trade message: {e}")

    async def _handle_depth_message(self, data: dict[str, Any]) -> None:
        """
        Handle a depth message from the WebSocket.

        Requirements:
            - 5.4: Depth data includes bids and asks arrays with [price, size] format
        """
        if not self._on_depth:
            return

        try:
            depth_data = data.get("data", {})
            symbol = data.get("symbol", depth_data.get("symbol", ""))

            # Parse bids
            bids: list[OrderBookLevel] = []
            for item in depth_data.get("bids", []):
                if isinstance(item, list) and len(item) >= 2:
                    bids.append(
                        OrderBookLevel(
                            price=Decimal(str(item[0])),
                            quantity=Decimal(str(item[1])),
                        )
                    )

            # Parse asks
            asks: list[OrderBookLevel] = []
            for item in depth_data.get("asks", []):
                if isinstance(item, list) and len(item) >= 2:
                    asks.append(
                        OrderBookLevel(
                            price=Decimal(str(item[0])),
                            quantity=Decimal(str(item[1])),
                        )
                    )

            # Parse timestamp
            timestamp_ms = depth_data.get("timestamp", int(time.time() * 1000))
            timestamp = datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=UTC)

            order_book = OrderBook(
                symbol=symbol,
                bids=bids,
                asks=asks,
                timestamp=timestamp,
            )

            await self._on_depth(order_book)

        except Exception as e:
            logger.error(f"Error processing depth message: {e}")


    async def _handle_order_message(self, data: dict[str, Any]) -> None:
        """
        Handle an order update message from the WebSocket.

        Requirements:
            - 6.4: Order update includes orderId, symbol, type, side, price, size,
                   filledSize, filledAmount, fee, status, clientOrderId
        """
        if not self._on_order:
            return

        try:
            order_data = data.get("data", {})

            # Parse side
            side_str = str(order_data.get("side", "BUY")).upper()
            side = OrderSide.BUY if side_str == "BUY" else OrderSide.SELL

            # Parse order type
            type_str = str(order_data.get("type", "LIMIT")).upper()
            order_type = OrderType.MARKET if type_str == "MARKET" else OrderType.LIMIT

            # Parse status
            status_str = str(order_data.get("status", "OPEN")).upper()
            try:
                status = OrderDetailStatus(status_str)
            except ValueError:
                status = OrderDetailStatus.OPEN

            # Parse timestamps
            create_time_ms = order_data.get("createTime", int(time.time() * 1000))
            update_time_ms = order_data.get("updateTime", create_time_ms)
            create_time = datetime.fromtimestamp(int(create_time_ms) / 1000, tz=UTC)
            update_time = datetime.fromtimestamp(int(update_time_ms) / 1000, tz=UTC)

            # Parse amount (may be None)
            amount_str = order_data.get("amount")
            amount = Decimal(str(amount_str)) if amount_str else None

            order = OrderDetail(
                order_id=int(order_data.get("orderId", 0)),
                symbol=order_data.get("symbol", ""),
                order_type=order_type,
                side=side,
                price=Decimal(str(order_data.get("price", "0"))),
                size=Decimal(str(order_data.get("size", "0"))),
                amount=amount,
                filled_size=Decimal(str(order_data.get("filledSize", "0"))),
                filled_amount=Decimal(str(order_data.get("filledAmount", "0"))),
                fee=Decimal(str(order_data.get("fee", "0"))),
                fee_coin=order_data.get("feeCoin", ""),
                status=status,
                ioc=order_data.get("IOC", False),
                client_order_id=order_data.get("clientOrderId"),
                source=order_data.get("source", "API"),
                create_time=create_time,
                update_time=update_time,
            )

            await self._on_order(order)

        except Exception as e:
            logger.error(f"Error processing order message: {e}")

    async def _handle_fill_message(self, data: dict[str, Any]) -> None:
        """
        Handle a fill message from the WebSocket.

        Requirements:
            - 6.5: Fill includes id, orderId, symbol, side, role, price, size,
                   fee, feeCoin, timestamp
        """
        if not self._on_fill:
            return

        try:
            fill_data = data.get("data", {})

            # Parse side
            side_str = str(fill_data.get("side", "BUY")).upper()
            side = OrderSide.BUY if side_str == "BUY" else OrderSide.SELL

            # Parse role
            role_str = str(fill_data.get("role", "TAKER")).upper()
            try:
                role = FillRole(role_str)
            except ValueError:
                role = FillRole.TAKER

            # Parse timestamp
            timestamp_ms = fill_data.get("timestamp", int(time.time() * 1000))
            timestamp = datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=UTC)

            fill = Fill(
                id=int(fill_data.get("id", 0)),
                order_id=int(fill_data.get("orderId", 0)),
                symbol=fill_data.get("symbol", ""),
                side=side,
                role=role,
                price=Decimal(str(fill_data.get("price", "0"))),
                size=Decimal(str(fill_data.get("size", "0"))),
                fee=Decimal(str(fill_data.get("fee", "0"))),
                fee_coin=fill_data.get("feeCoin", ""),
                timestamp=timestamp,
            )

            await self._on_fill(fill)

        except Exception as e:
            logger.error(f"Error processing fill message: {e}")


    async def _handle_balance_message(self, data: dict[str, Any]) -> None:
        """
        Handle a balance update message from the WebSocket.

        Requirements:
            - 6.6: Balance update includes balances array with coin, free, frozen
        """
        if not self._on_balance:
            return

        try:
            balance_data = data.get("data", {})
            balance_update = BalanceUpdate.from_ws_message(balance_data)
            await self._on_balance(balance_update)

        except Exception as e:
            logger.error(f"Error processing balance message: {e}")

    # =========================================================================
    # Reconnection Logic
    # =========================================================================

    async def _reconnect(self, is_private: bool) -> None:
        """
        Reconnect to WebSocket with exponential backoff.

        After reconnection, re-subscribes to all previous topics.

        Args:
            is_private: Whether to reconnect the private WebSocket

        Requirements:
            - 5.5: Automatic reconnection with exponential backoff (1s, 2s, 4s, 8s, max 30s)
        """
        if not self._should_reconnect:
            return

        if is_private:
            delay = self._private_reconnect_delay
            subscriptions = self._private_subscriptions.copy()
        else:
            delay = self._public_reconnect_delay
            subscriptions = self._public_subscriptions.copy()

        logger.info(
            f"Reconnecting {'private' if is_private else 'public'} WebSocket "
            f"in {delay:.1f}s..."
        )

        await asyncio.sleep(delay)

        # Update delay for next reconnection attempt (exponential backoff)
        new_delay = min(delay * RECONNECT_MULTIPLIER, MAX_RECONNECT_DELAY)
        if is_private:
            self._private_reconnect_delay = new_delay
        else:
            self._public_reconnect_delay = new_delay

        try:
            if is_private:
                self._private_subscriptions.clear()
                await self.connect_private()
            else:
                self._public_subscriptions.clear()
                await self.connect_public()

            # Re-subscribe to previous topics
            await self._resubscribe(subscriptions, is_private)

            logger.info(
                f"{'Private' if is_private else 'Public'} WebSocket reconnected "
                f"and re-subscribed to {len(subscriptions)} topics"
            )

        except Exception as e:
            logger.error(f"Reconnection failed: {e}")
            # Will retry on next iteration of message handler loop

    async def _resubscribe(
        self, subscriptions: list[Subscription], is_private: bool
    ) -> None:
        """
        Re-subscribe to topics after reconnection.

        Args:
            subscriptions: List of subscriptions to restore
            is_private: Whether these are private subscriptions
        """
        for sub in subscriptions:
            try:
                if sub.topic == WebSocketTopic.TRADE and sub.symbol:
                    await self.subscribe_trade(sub.symbol)
                elif sub.topic == WebSocketTopic.DEPTH and sub.symbol:
                    limit = sub.params.get("limit", 20)
                    await self.subscribe_depth(sub.symbol, limit)
                elif sub.topic == WebSocketTopic.ORDER and sub.symbol:
                    await self.subscribe_order(sub.symbol)
                elif sub.topic == WebSocketTopic.FILL and sub.symbol:
                    await self.subscribe_fill(sub.symbol)
                elif sub.topic == WebSocketTopic.BALANCE:
                    await self.subscribe_balance()

            except Exception as e:
                logger.error(f"Failed to re-subscribe to {sub.topic}: {e}")


    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def is_public_connected(self) -> bool:
        """Check if public WebSocket is connected."""
        return self._public_connected

    @property
    def is_private_connected(self) -> bool:
        """Check if private WebSocket is connected."""
        return self._private_connected

    @property
    def public_subscriptions(self) -> list[Subscription]:
        """Get list of active public subscriptions."""
        return self._public_subscriptions.copy()

    @property
    def private_subscriptions(self) -> list[Subscription]:
        """Get list of active private subscriptions."""
        return self._private_subscriptions.copy()

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def get_reconnect_delay(self, is_private: bool) -> float:
        """
        Get the current reconnection delay.

        Args:
            is_private: Whether to get private or public delay

        Returns:
            Current reconnection delay in seconds
        """
        if is_private:
            return self._private_reconnect_delay
        return self._public_reconnect_delay

    def reset_reconnect_delay(self, is_private: bool) -> None:
        """
        Reset the reconnection delay to initial value.

        Args:
            is_private: Whether to reset private or public delay
        """
        if is_private:
            self._private_reconnect_delay = INITIAL_RECONNECT_DELAY
        else:
            self._public_reconnect_delay = INITIAL_RECONNECT_DELAY

    async def send_ping(self, is_private: bool = False) -> None:
        """
        Send a ping message to keep the connection alive.

        Args:
            is_private: Whether to ping private or public WebSocket
        """
        message = {"op": "PING"}

        if is_private and self._private_ws:
            await self._private_ws.send(json.dumps(message))
        elif not is_private and self._public_ws:
            await self._public_ws.send(json.dumps(message))
