"""
WebSocket Broadcasting Utilities.

This module provides utilities for broadcasting messages to WebSocket
consumers from agents and background tasks.

Requirements:
- 8.1: Real-time dashboard updates
- 10.11: Publish bot events and alerts to WebSocket
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


# WebSocket group names (must match consumers.py)
DASHBOARD_GROUP = "dashboard"
ANALYSIS_GROUP = "analysis"
BOT_EVENTS_GROUP = "bot_events"
ALERTS_GROUP = "alerts"


def _serialize_value(value: Any) -> Any:
    """Serialize a value for JSON transmission."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _serialize_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively serialize a dictionary for JSON transmission."""
    return {
        key: _serialize_value(val) if not isinstance(val, dict) else _serialize_dict(val)
        for key, val in data.items()
    }


class WebSocketBroadcaster:
    """
    Utility class for broadcasting messages to WebSocket consumers.

    Provides methods for sending various types of updates to connected
    WebSocket clients via Django Channels.

    Example:
        >>> broadcaster = WebSocketBroadcaster()
        >>> await broadcaster.broadcast_signal_update(signal_data)
        >>> # Or synchronously:
        >>> broadcaster.broadcast_signal_update_sync(signal_data)

    Requirements:
        - 8.1: Real-time dashboard updates
        - 10.11: Publish bot events to WebSocket
    """

    def __init__(self) -> None:
        """Initialize the broadcaster."""
        self._channel_layer = None

    def _get_channel_layer(self):
        """Get the channel layer (lazy initialization)."""
        if self._channel_layer is None:
            self._channel_layer = get_channel_layer()
        return self._channel_layer

    # -------------------------------------------------------------------------
    # Portfolio Updates
    # -------------------------------------------------------------------------

    async def broadcast_portfolio_update(
        self,
        total_value: Decimal,
        available_balance: Decimal,
        allocated_to_bots: Decimal,
        drawdown: float,
        high_water_mark: Decimal,
    ) -> None:
        """
        Broadcast portfolio update to dashboard consumers.

        Args:
            total_value: Total portfolio value
            available_balance: Available balance
            allocated_to_bots: Amount allocated to bots
            drawdown: Current drawdown percentage
            high_water_mark: Portfolio high water mark
        """
        channel_layer = self._get_channel_layer()

        await channel_layer.group_send(
            DASHBOARD_GROUP,
            {
                "type": "portfolio_update",
                "total_value": str(total_value),
                "available_balance": str(available_balance),
                "allocated_to_bots": str(allocated_to_bots),
                "drawdown": drawdown,
                "high_water_mark": str(high_water_mark),
                "timestamp": datetime.now(tz=UTC).isoformat(),
            },
        )

    def broadcast_portfolio_update_sync(
        self,
        total_value: Decimal,
        available_balance: Decimal,
        allocated_to_bots: Decimal,
        drawdown: float,
        high_water_mark: Decimal,
    ) -> None:
        """Synchronous version of broadcast_portfolio_update."""
        async_to_sync(self.broadcast_portfolio_update)(
            total_value,
            available_balance,
            allocated_to_bots,
            drawdown,
            high_water_mark,
        )

    # -------------------------------------------------------------------------
    # Signal Updates
    # -------------------------------------------------------------------------

    async def broadcast_signal_update(
        self,
        symbol: str,
        direction: str,
        confidence: float,
        meets_threshold: bool,
        indicators: list[dict[str, Any]] | None = None,
        reasoning: str | None = None,
    ) -> None:
        """
        Broadcast signal update to dashboard and analysis consumers.

        Args:
            symbol: Trading pair symbol
            direction: Signal direction (BUY/SELL/HOLD)
            confidence: Confidence score (0-100)
            meets_threshold: Whether signal meets confidence threshold
            indicators: List of indicator contributions
            reasoning: Signal reasoning text
        """
        channel_layer = self._get_channel_layer()

        message = {
            "type": "signal_update",
            "symbol": symbol,
            "direction": direction,
            "confidence": confidence,
            "meets_threshold": meets_threshold,
            "indicators": indicators or [],
            "reasoning": reasoning,
            "timestamp": datetime.now(tz=UTC).isoformat(),
        }

        # Send to dashboard group
        await channel_layer.group_send(DASHBOARD_GROUP, message)

        # Send to analysis group
        await channel_layer.group_send(ANALYSIS_GROUP, message)

        # Send to symbol-specific analysis group
        await channel_layer.group_send(f"analysis_{symbol}", message)

    def broadcast_signal_update_sync(
        self,
        symbol: str,
        direction: str,
        confidence: float,
        meets_threshold: bool,
        indicators: list[dict[str, Any]] | None = None,
        reasoning: str | None = None,
    ) -> None:
        """Synchronous version of broadcast_signal_update."""
        async_to_sync(self.broadcast_signal_update)(
            symbol,
            direction,
            confidence,
            meets_threshold,
            indicators,
            reasoning,
        )

    # -------------------------------------------------------------------------
    # Bot Updates
    # -------------------------------------------------------------------------

    async def broadcast_bot_created(
        self,
        bot_id: str,
        bot_type: str,
        symbol: str,
        invested: Decimal,
        params: dict[str, Any],
        reasoning: str,
        is_simulated: bool = False,
    ) -> None:
        """
        Broadcast bot created event to dashboard consumers.

        Args:
            bot_id: Pionex bot ID
            bot_type: Type of bot (GRID/DCA)
            symbol: Trading pair symbol
            invested: Investment amount
            params: Bot parameters
            reasoning: Reason for creation
            is_simulated: Whether bot is simulated (dry-run)

        Requirements:
            - 10.11: Log all bot creation events
        """
        channel_layer = self._get_channel_layer()

        await channel_layer.group_send(
            BOT_EVENTS_GROUP,
            {
                "type": "bot_created",
                "bot_id": bot_id,
                "bot_type": bot_type,
                "symbol": symbol,
                "invested": str(invested),
                "params": _serialize_dict(params),
                "reasoning": reasoning,
                "is_simulated": is_simulated,
                "timestamp": datetime.now(tz=UTC).isoformat(),
            },
        )

        # Also send to dashboard group
        await channel_layer.group_send(
            DASHBOARD_GROUP,
            {
                "type": "bot_created",
                "bot_id": bot_id,
                "bot_type": bot_type,
                "symbol": symbol,
                "invested": str(invested),
                "params": _serialize_dict(params),
                "reasoning": reasoning,
                "is_simulated": is_simulated,
                "timestamp": datetime.now(tz=UTC).isoformat(),
            },
        )

    def broadcast_bot_created_sync(
        self,
        bot_id: str,
        bot_type: str,
        symbol: str,
        invested: Decimal,
        params: dict[str, Any],
        reasoning: str,
        is_simulated: bool = False,
    ) -> None:
        """Synchronous version of broadcast_bot_created."""
        async_to_sync(self.broadcast_bot_created)(
            bot_id,
            bot_type,
            symbol,
            invested,
            params,
            reasoning,
            is_simulated,
        )

    async def broadcast_bot_stopped(
        self,
        bot_id: str,
        symbol: str,
        reason: str,
        final_pnl: Decimal | None = None,
        is_simulated: bool = False,
    ) -> None:
        """
        Broadcast bot stopped event to dashboard consumers.

        Args:
            bot_id: Pionex bot ID
            symbol: Trading pair symbol
            reason: Reason for stopping
            final_pnl: Final P&L (if available)
            is_simulated: Whether bot was simulated

        Requirements:
            - 10.11: Log all bot termination events
        """
        channel_layer = self._get_channel_layer()

        message = {
            "type": "bot_stopped",
            "bot_id": bot_id,
            "symbol": symbol,
            "reason": reason,
            "final_pnl": str(final_pnl) if final_pnl is not None else None,
            "is_simulated": is_simulated,
            "timestamp": datetime.now(tz=UTC).isoformat(),
        }

        await channel_layer.group_send(BOT_EVENTS_GROUP, message)
        await channel_layer.group_send(DASHBOARD_GROUP, message)

    def broadcast_bot_stopped_sync(
        self,
        bot_id: str,
        symbol: str,
        reason: str,
        final_pnl: Decimal | None = None,
        is_simulated: bool = False,
    ) -> None:
        """Synchronous version of broadcast_bot_stopped."""
        async_to_sync(self.broadcast_bot_stopped)(
            bot_id,
            symbol,
            reason,
            final_pnl,
            is_simulated,
        )

    async def broadcast_bot_performance(
        self,
        bot_id: str,
        symbol: str,
        pnl: Decimal,
        pnl_percent: float,
        current_value: Decimal,
        is_underperforming: bool = False,
    ) -> None:
        """
        Broadcast bot performance update to dashboard consumers.

        Args:
            bot_id: Pionex bot ID
            symbol: Trading pair symbol
            pnl: Current P&L
            pnl_percent: P&L percentage
            current_value: Current value
            is_underperforming: Whether bot is underperforming
        """
        channel_layer = self._get_channel_layer()

        message = {
            "type": "bot_performance",
            "bot_id": bot_id,
            "symbol": symbol,
            "pnl": str(pnl),
            "pnl_percent": pnl_percent,
            "current_value": str(current_value),
            "is_underperforming": is_underperforming,
            "timestamp": datetime.now(tz=UTC).isoformat(),
        }

        await channel_layer.group_send(BOT_EVENTS_GROUP, message)
        await channel_layer.group_send(DASHBOARD_GROUP, message)

    def broadcast_bot_performance_sync(
        self,
        bot_id: str,
        symbol: str,
        pnl: Decimal,
        pnl_percent: float,
        current_value: Decimal,
        is_underperforming: bool = False,
    ) -> None:
        """Synchronous version of broadcast_bot_performance."""
        async_to_sync(self.broadcast_bot_performance)(
            bot_id,
            symbol,
            pnl,
            pnl_percent,
            current_value,
            is_underperforming,
        )

    async def broadcast_bot_update(
        self,
        bot_id: str,
        status: str,
        symbol: str,
        invested: Decimal,
        current_value: Decimal,
        pnl: Decimal,
        pnl_percent: float,
    ) -> None:
        """
        Broadcast general bot status update to dashboard consumers.

        Args:
            bot_id: Pionex bot ID
            status: Bot status (ACTIVE/STOPPED/ERROR)
            symbol: Trading pair symbol
            invested: Investment amount
            current_value: Current value
            pnl: Profit/loss amount
            pnl_percent: P&L percentage
        """
        channel_layer = self._get_channel_layer()

        await channel_layer.group_send(
            DASHBOARD_GROUP,
            {
                "type": "bot_update",
                "bot_id": bot_id,
                "status": status,
                "symbol": symbol,
                "invested": str(invested),
                "current_value": str(current_value),
                "pnl": str(pnl),
                "pnl_percent": pnl_percent,
                "timestamp": datetime.now(tz=UTC).isoformat(),
            },
        )

    def broadcast_bot_update_sync(
        self,
        bot_id: str,
        status: str,
        symbol: str,
        invested: Decimal,
        current_value: Decimal,
        pnl: Decimal,
        pnl_percent: float,
    ) -> None:
        """Synchronous version of broadcast_bot_update."""
        async_to_sync(self.broadcast_bot_update)(
            bot_id,
            status,
            symbol,
            invested,
            current_value,
            pnl,
            pnl_percent,
        )

    # -------------------------------------------------------------------------
    # Indicator Updates
    # -------------------------------------------------------------------------

    async def broadcast_indicator_update(
        self,
        symbol: str,
        indicators: dict[str, Any],
    ) -> None:
        """
        Broadcast indicator update to analysis consumers.

        Args:
            symbol: Trading pair symbol
            indicators: Dict of indicator name -> value
        """
        channel_layer = self._get_channel_layer()

        message = {
            "type": "indicator_update",
            "symbol": symbol,
            "indicators": _serialize_dict(indicators),
            "timestamp": datetime.now(tz=UTC).isoformat(),
        }

        # Send to general analysis group
        await channel_layer.group_send(ANALYSIS_GROUP, message)

        # Send to symbol-specific group
        await channel_layer.group_send(f"analysis_{symbol}", message)

    def broadcast_indicator_update_sync(
        self,
        symbol: str,
        indicators: dict[str, Any],
    ) -> None:
        """Synchronous version of broadcast_indicator_update."""
        async_to_sync(self.broadcast_indicator_update)(symbol, indicators)

    async def broadcast_sentiment_update(
        self,
        fear_greed_index: int,
        signal: str,
        classification: str,
    ) -> None:
        """
        Broadcast sentiment update to analysis consumers.

        Args:
            fear_greed_index: Fear & Greed Index value (0-100)
            signal: Sentiment signal (BUY/SELL/HOLD)
            classification: Text classification (Extreme Fear, etc.)
        """
        channel_layer = self._get_channel_layer()

        await channel_layer.group_send(
            ANALYSIS_GROUP,
            {
                "type": "sentiment_update",
                "fear_greed_index": fear_greed_index,
                "signal": signal,
                "classification": classification,
                "timestamp": datetime.now(tz=UTC).isoformat(),
            },
        )

    def broadcast_sentiment_update_sync(
        self,
        fear_greed_index: int,
        signal: str,
        classification: str,
    ) -> None:
        """Synchronous version of broadcast_sentiment_update."""
        async_to_sync(self.broadcast_sentiment_update)(
            fear_greed_index,
            signal,
            classification,
        )

    # -------------------------------------------------------------------------
    # Market Context Updates
    # -------------------------------------------------------------------------

    async def broadcast_market_context_update(
        self,
        context_data: dict[str, Any],
    ) -> None:
        """
        Broadcast market context snapshot update to dashboard consumers.

        Args:
            context_data: Dict containing market context snapshot data
                         (snapshot_id, symbol, regime, is_stale, etc.)

        Requirements:
            - 1.5.5: Broadcast WebSocket update after creating snapshot
        """
        channel_layer = self._get_channel_layer()

        message = {
            "type": "market_context_update",
            **_serialize_dict(context_data),
            "timestamp": datetime.now(tz=UTC).isoformat(),
        }

        # Send to dashboard group
        await channel_layer.group_send(DASHBOARD_GROUP, message)

        # Send to analysis group
        await channel_layer.group_send(ANALYSIS_GROUP, message)

    def broadcast_market_context_update_sync(
        self,
        context_data: dict[str, Any],
    ) -> None:
        """Synchronous version of broadcast_market_context_update."""
        async_to_sync(self.broadcast_market_context_update)(context_data)

    # -------------------------------------------------------------------------
    # Alerts
    # -------------------------------------------------------------------------

    async def broadcast_alert(
        self,
        level: str,
        title: str,
        message: str,
        source: str = "system",
    ) -> None:
        """
        Broadcast alert to dashboard consumers.

        Args:
            level: Alert level (info/warning/error/critical)
            title: Alert title
            message: Alert message
            source: Source of the alert
        """
        channel_layer = self._get_channel_layer()

        await channel_layer.group_send(
            ALERTS_GROUP,
            {
                "type": "alert",
                "level": level,
                "title": title,
                "message": message,
                "source": source,
                "timestamp": datetime.now(tz=UTC).isoformat(),
            },
        )

        # Also send to dashboard group
        await channel_layer.group_send(
            DASHBOARD_GROUP,
            {
                "type": "alert",
                "level": level,
                "title": title,
                "message": message,
                "source": source,
                "timestamp": datetime.now(tz=UTC).isoformat(),
            },
        )

    def broadcast_alert_sync(
        self,
        level: str,
        title: str,
        message: str,
        source: str = "system",
    ) -> None:
        """Synchronous version of broadcast_alert."""
        async_to_sync(self.broadcast_alert)(level, title, message, source)

    # -------------------------------------------------------------------------
    # Trade Updates
    # -------------------------------------------------------------------------

    async def broadcast_trade_executed(
        self,
        trade_id: int,
        symbol: str,
        side: str,
        price: Decimal,
        quantity: Decimal,
        is_simulated: bool = False,
    ) -> None:
        """
        Broadcast trade executed notification to dashboard consumers.

        Args:
            trade_id: Trade ID
            symbol: Trading pair symbol
            side: Trade side (BUY/SELL)
            price: Execution price
            quantity: Trade quantity
            is_simulated: Whether trade is simulated
        """
        channel_layer = self._get_channel_layer()

        await channel_layer.group_send(
            DASHBOARD_GROUP,
            {
                "type": "trade_executed",
                "trade_id": trade_id,
                "symbol": symbol,
                "side": side,
                "price": str(price),
                "quantity": str(quantity),
                "is_simulated": is_simulated,
                "timestamp": datetime.now(tz=UTC).isoformat(),
            },
        )

    def broadcast_trade_executed_sync(
        self,
        trade_id: int,
        symbol: str,
        side: str,
        price: Decimal,
        quantity: Decimal,
        is_simulated: bool = False,
    ) -> None:
        """Synchronous version of broadcast_trade_executed."""
        async_to_sync(self.broadcast_trade_executed)(
            trade_id,
            symbol,
            side,
            price,
            quantity,
            is_simulated,
        )


# Global broadcaster instance for convenience
_broadcaster: WebSocketBroadcaster | None = None


def get_broadcaster() -> WebSocketBroadcaster:
    """Get the global WebSocket broadcaster instance."""
    global _broadcaster
    if _broadcaster is None:
        _broadcaster = WebSocketBroadcaster()
    return _broadcaster
