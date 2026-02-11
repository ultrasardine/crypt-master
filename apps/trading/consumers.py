"""
WebSocket consumers for real-time trading updates.

This module implements Django Channels WebSocket consumers for:
- Real-time order updates from Pionex WebSocket
- Real-time fill updates from Pionex WebSocket
- Real-time balance updates from Pionex WebSocket

Requirements:
- 10.1: Show connection status indicator
- 10.2: Order updates via WebSocket
- 10.3: Fill updates via WebSocket
- 10.4: Balance updates via WebSocket
- 10.5: Handle reconnection attempts
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from decimal import Decimal
from typing import Any

from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


# WebSocket group names
TRADING_GROUP = "trading"
ORDERS_GROUP = "orders"
FILLS_GROUP = "fills"
BALANCES_GROUP = "balances"


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal types."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


class TradingConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer that bridges Pionex WebSocket to browser.

    Subscribes to:
    - Real-time order updates
    - Real-time fill updates
    - Real-time balance updates

    This consumer connects to the Pionex WebSocket when a browser connects
    and forwards updates to the browser in real-time.

    Groups:
        - trading: General trading updates
        - orders: Order status updates
        - fills: Fill notifications
        - balances: Balance changes

    Message Types (outbound):
        - connection_status: Connection status indicator
        - order_update: Order status changes
        - fill_update: New fill notifications
        - balance_update: Balance changes
        - pong: Response to ping

    Requirements:
        - 10.1: Show connection status indicator
        - 10.2: Order updates via WebSocket
        - 10.3: Fill updates via WebSocket
        - 10.4: Balance updates via WebSocket
        - 10.5: Handle reconnection attempts
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._pionex_ws_manager: Any = None
        self._pionex_task: asyncio.Task[None] | None = None
        self._subscribed_symbols: set[str] = set()
        self._is_connected_to_pionex = False

    async def connect(self) -> None:
        """
        Handle WebSocket connection from browser.

        Joins relevant groups and starts Pionex WebSocket connection.

        Requirements:
            - 10.1: Show connection status indicator
        """
        # Join all relevant groups
        await self.channel_layer.group_add(TRADING_GROUP, self.channel_name)
        await self.channel_layer.group_add(ORDERS_GROUP, self.channel_name)
        await self.channel_layer.group_add(FILLS_GROUP, self.channel_name)
        await self.channel_layer.group_add(BALANCES_GROUP, self.channel_name)

        await self.accept()

        logger.info(f"Trading WebSocket connected: {self.channel_name}")

        # Send initial connection status
        await self._send_connection_status(connected=False, message="Connecting to Pionex...")

        # Start Pionex WebSocket connection in background
        self._pionex_task = asyncio.create_task(
            self._connect_to_pionex(),
            name="pionex_ws_bridge",
        )

    async def disconnect(self, close_code: int) -> None:
        """
        Handle WebSocket disconnection from browser.

        Cleans up Pionex WebSocket connection and leaves groups.

        Requirements:
            - 10.5: Handle reconnection attempts
        """
        # Cancel Pionex WebSocket task
        if self._pionex_task and not self._pionex_task.done():
            self._pionex_task.cancel()
            try:
                await self._pionex_task
            except asyncio.CancelledError:
                pass

        # Disconnect from Pionex WebSocket
        if self._pionex_ws_manager:
            try:
                await self._pionex_ws_manager.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting from Pionex WebSocket: {e}")

        # Leave all groups
        await self.channel_layer.group_discard(TRADING_GROUP, self.channel_name)
        await self.channel_layer.group_discard(ORDERS_GROUP, self.channel_name)
        await self.channel_layer.group_discard(FILLS_GROUP, self.channel_name)
        await self.channel_layer.group_discard(BALANCES_GROUP, self.channel_name)

        # Leave symbol-specific groups
        for symbol in self._subscribed_symbols:
            group_name = f"trading_{symbol}"
            await self.channel_layer.group_discard(group_name, self.channel_name)

        self._subscribed_symbols.clear()

        logger.info(f"Trading WebSocket disconnected: {self.channel_name}")

    async def receive(self, text_data: str) -> None:
        """
        Handle incoming WebSocket messages from browser.

        Supported message types:
            - ping: Health check, responds with pong
            - subscribe: Subscribe to symbol-specific updates
            - unsubscribe: Unsubscribe from symbol updates
            - get_status: Get current connection status
        """
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self._send_error("Invalid JSON")
            return

        message_type = data.get("type", "")

        if message_type == "ping":
            await self.send(text_data=json.dumps({"type": "pong"}))

        elif message_type == "subscribe":
            symbol = data.get("symbol")
            if symbol:
                await self._subscribe_to_symbol(symbol)

        elif message_type == "unsubscribe":
            symbol = data.get("symbol")
            if symbol:
                await self._unsubscribe_from_symbol(symbol)

        elif message_type == "get_status":
            await self._send_connection_status(
                connected=self._is_connected_to_pionex,
                message="Connected to Pionex" if self._is_connected_to_pionex else "Disconnected",
            )

    # =========================================================================
    # Pionex WebSocket Connection
    # =========================================================================

    async def _connect_to_pionex(self) -> None:
        """
        Connect to Pionex WebSocket and subscribe to private streams.

        Requirements:
            - 10.1: Connect to Pionex WebSocket on browser connect
            - 10.2, 10.3, 10.4: Subscribe to ORDER, FILL, BALANCE topics
        """
        from lib.pionex.websocket import PionexWebSocketManager

        api_key = os.environ.get("PIONEX_API_KEY", "")
        api_secret = os.environ.get("PIONEX_API_SECRET", "")

        if not api_key or not api_secret:
            logger.warning("Pionex API credentials not configured")
            await self._send_connection_status(
                connected=False,
                message="API credentials not configured",
            )
            return

        try:
            # Create WebSocket manager with callbacks
            self._pionex_ws_manager = PionexWebSocketManager(
                api_key=api_key,
                api_secret=api_secret,
                on_order=self._on_order_update,
                on_fill=self._on_fill_update,
                on_balance=self._on_balance_update,
            )

            # Connect to private WebSocket
            await self._pionex_ws_manager.connect_private()

            self._is_connected_to_pionex = True
            await self._send_connection_status(
                connected=True,
                message="Connected to Pionex",
            )

            logger.info("Connected to Pionex private WebSocket")

            # Subscribe to balance updates (global, not symbol-specific)
            await self._pionex_ws_manager.subscribe_balance()

            # Keep the connection alive
            while True:
                await asyncio.sleep(30)
                # Send ping to keep connection alive
                if self._pionex_ws_manager:
                    try:
                        await self._pionex_ws_manager.send_ping(is_private=True)
                    except Exception as e:
                        logger.warning(f"Failed to send ping: {e}")

        except asyncio.CancelledError:
            logger.info("Pionex WebSocket connection cancelled")
            raise

        except Exception as e:
            logger.error(f"Failed to connect to Pionex WebSocket: {e}")
            self._is_connected_to_pionex = False
            await self._send_connection_status(
                connected=False,
                message=f"Connection failed: {e}",
            )

    async def _subscribe_to_symbol(self, symbol: str) -> None:
        """
        Subscribe to order and fill updates for a specific symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BTC_USDT")
        """
        if symbol in self._subscribed_symbols:
            return

        # Join symbol-specific group
        group_name = f"trading_{symbol}"
        await self.channel_layer.group_add(group_name, self.channel_name)
        self._subscribed_symbols.add(symbol)

        # Subscribe to Pionex WebSocket streams for this symbol
        if self._pionex_ws_manager and self._is_connected_to_pionex:
            try:
                await self._pionex_ws_manager.subscribe_order(symbol)
                await self._pionex_ws_manager.subscribe_fill(symbol)
                logger.info(f"Subscribed to ORDER and FILL streams for {symbol}")
            except Exception as e:
                logger.error(f"Failed to subscribe to {symbol}: {e}")

        await self.send(
            text_data=json.dumps(
                {
                    "type": "subscribed",
                    "symbol": symbol,
                }
            )
        )

    async def _unsubscribe_from_symbol(self, symbol: str) -> None:
        """
        Unsubscribe from order and fill updates for a specific symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BTC_USDT")
        """
        if symbol not in self._subscribed_symbols:
            return

        # Leave symbol-specific group
        group_name = f"trading_{symbol}"
        await self.channel_layer.group_discard(group_name, self.channel_name)
        self._subscribed_symbols.discard(symbol)

        await self.send(
            text_data=json.dumps(
                {
                    "type": "unsubscribed",
                    "symbol": symbol,
                }
            )
        )

    # =========================================================================
    # Pionex WebSocket Callbacks
    # =========================================================================

    async def _on_order_update(self, order: Any) -> None:
        """
        Handle order update from Pionex WebSocket.

        Broadcasts order update to browser via WebSocket.

        Args:
            order: OrderDetail instance from Pionex WebSocket

        Requirements:
            - 10.2: Send order updates to browser via WebSocket
        """
        try:
            order_data = {
                "type": "order_update",
                "data": {
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "order_type": order.order_type.value,
                    "side": order.side.value,
                    "price": str(order.price),
                    "size": str(order.size),
                    "filled_size": str(order.filled_size),
                    "filled_amount": str(order.filled_amount),
                    "fee": str(order.fee),
                    "fee_coin": order.fee_coin,
                    "status": order.status.value,
                    "client_order_id": order.client_order_id,
                    "create_time": order.create_time.isoformat(),
                    "update_time": order.update_time.isoformat(),
                },
            }

            # Send to browser
            await self.send(text_data=json.dumps(order_data, cls=DecimalEncoder))

            # Also broadcast to group for other consumers
            await self.channel_layer.group_send(
                ORDERS_GROUP,
                {
                    "type": "order_update_broadcast",
                    **order_data,
                },
            )

            logger.debug(f"Order update sent: {order.order_id} - {order.status.value}")

        except Exception as e:
            logger.error(f"Error sending order update: {e}")

    async def _on_fill_update(self, fill: Any) -> None:
        """
        Handle fill update from Pionex WebSocket.

        Broadcasts fill update to browser via WebSocket.

        Args:
            fill: Fill instance from Pionex WebSocket

        Requirements:
            - 10.3: Send fill updates to browser via WebSocket
        """
        try:
            fill_data = {
                "type": "fill_update",
                "data": {
                    "id": fill.id,
                    "order_id": fill.order_id,
                    "symbol": fill.symbol,
                    "side": fill.side.value,
                    "role": fill.role.value,
                    "price": str(fill.price),
                    "size": str(fill.size),
                    "fee": str(fill.fee),
                    "fee_coin": fill.fee_coin,
                    "timestamp": fill.timestamp.isoformat(),
                },
            }

            # Send to browser
            await self.send(text_data=json.dumps(fill_data, cls=DecimalEncoder))

            # Also broadcast to group for other consumers
            await self.channel_layer.group_send(
                FILLS_GROUP,
                {
                    "type": "fill_update_broadcast",
                    **fill_data,
                },
            )

            logger.debug(f"Fill update sent: {fill.id} - {fill.symbol}")

        except Exception as e:
            logger.error(f"Error sending fill update: {e}")

    async def _on_balance_update(self, balance_update: Any) -> None:
        """
        Handle balance update from Pionex WebSocket.

        Broadcasts balance update to browser via WebSocket.

        Args:
            balance_update: BalanceUpdate instance from Pionex WebSocket

        Requirements:
            - 10.4: Send balance updates to browser via WebSocket
        """
        try:
            balances_data = []
            for balance in balance_update.balances:
                balances_data.append(
                    {
                        "currency": balance.currency,
                        "free": str(balance.free),
                        "locked": str(balance.locked),
                        "total": str(balance.total),
                    }
                )

            balance_data = {
                "type": "balance_update",
                "data": {
                    "balances": balances_data,
                    "timestamp": balance_update.timestamp.isoformat(),
                },
            }

            # Send to browser
            await self.send(text_data=json.dumps(balance_data, cls=DecimalEncoder))

            # Also broadcast to group for other consumers
            await self.channel_layer.group_send(
                BALANCES_GROUP,
                {
                    "type": "balance_update_broadcast",
                    **balance_data,
                },
            )

            logger.debug(f"Balance update sent: {len(balances_data)} currencies")

        except Exception as e:
            logger.error(f"Error sending balance update: {e}")

    # =========================================================================
    # Group Message Handlers
    # =========================================================================

    async def order_update_broadcast(self, event: dict[str, Any]) -> None:
        """
        Handle order update broadcast from group.

        This is called when another consumer broadcasts an order update.
        We don't need to re-send since we already sent directly.
        """
        pass  # Already sent directly in _on_order_update

    async def fill_update_broadcast(self, event: dict[str, Any]) -> None:
        """
        Handle fill update broadcast from group.

        This is called when another consumer broadcasts a fill update.
        We don't need to re-send since we already sent directly.
        """
        pass  # Already sent directly in _on_fill_update

    async def balance_update_broadcast(self, event: dict[str, Any]) -> None:
        """
        Handle balance update broadcast from group.

        This is called when another consumer broadcasts a balance update.
        We don't need to re-send since we already sent directly.
        """
        pass  # Already sent directly in _on_balance_update

    # =========================================================================
    # External Message Handlers (for broadcasting from views/tasks)
    # =========================================================================

    async def order_update(self, event: dict[str, Any]) -> None:
        """
        Send order update to browser (called from external broadcast).

        Event data:
            - order_id: Order ID
            - symbol: Trading pair symbol
            - status: Order status
            - ... other order fields
        """
        await self.send(text_data=json.dumps(event, cls=DecimalEncoder))

    async def fill_update(self, event: dict[str, Any]) -> None:
        """
        Send fill update to browser (called from external broadcast).

        Event data:
            - id: Fill ID
            - order_id: Order ID
            - symbol: Trading pair symbol
            - ... other fill fields
        """
        await self.send(text_data=json.dumps(event, cls=DecimalEncoder))

    async def balance_update(self, event: dict[str, Any]) -> None:
        """
        Send balance update to browser (called from external broadcast).

        Event data:
            - balances: List of balance objects
            - timestamp: Update timestamp
        """
        await self.send(text_data=json.dumps(event, cls=DecimalEncoder))

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _send_connection_status(self, connected: bool, message: str) -> None:
        """
        Send connection status to browser.

        Args:
            connected: Whether connected to Pionex WebSocket
            message: Status message

        Requirements:
            - 10.1: Show connection status indicator
            - 10.5: Handle reconnection attempts
        """
        await self.send(
            text_data=json.dumps(
                {
                    "type": "connection_status",
                    "connected": connected,
                    "message": message,
                }
            )
        )

    async def _send_error(self, message: str) -> None:
        """Send an error message to the client."""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "error",
                    "message": message,
                }
            )
        )
