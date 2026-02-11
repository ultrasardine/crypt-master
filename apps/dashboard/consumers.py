"""
WebSocket consumers for real-time dashboard updates.

This module implements Django Channels WebSocket consumers for:
- Dashboard updates (portfolio, signals, bots)
- Analysis updates (live indicator data)

Requirements:
- 8.1: Real-time dashboard updates via WebSocket
- 10.11: Publish bot events and alerts to WebSocket
"""

from __future__ import annotations

import json
import logging
from typing import Any

from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


# WebSocket group names
DASHBOARD_GROUP = "dashboard"
ANALYSIS_GROUP = "analysis"
BOT_EVENTS_GROUP = "bot_events"
ALERTS_GROUP = "alerts"


class DashboardConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time dashboard updates.

    Handles portfolio updates, signal updates, bot status changes,
    and system alerts for the main dashboard view.

    Groups:
        - dashboard: General dashboard updates
        - bot_events: Bot lifecycle events
        - alerts: System alerts and notifications

    Message Types (outbound):
        - portfolio_update: Portfolio value and allocation changes
        - signal_update: New trading signals
        - bot_update: Bot status changes
        - bot_created: New bot created
        - bot_stopped: Bot stopped
        - bot_performance: Bot performance update
        - alert: System alerts
        - pong: Response to ping

    Requirements:
        - 8.1: Real-time dashboard updates
        - 10.11: Publish bot events to WebSocket
    """

    async def connect(self) -> None:
        """Handle WebSocket connection."""
        # Join all relevant groups
        await self.channel_layer.group_add(DASHBOARD_GROUP, self.channel_name)
        await self.channel_layer.group_add(BOT_EVENTS_GROUP, self.channel_name)
        await self.channel_layer.group_add(ALERTS_GROUP, self.channel_name)

        await self.accept()

        logger.debug(f"Dashboard WebSocket connected: {self.channel_name}")

    async def disconnect(self, close_code: int) -> None:
        """Handle WebSocket disconnection."""
        # Leave all groups
        await self.channel_layer.group_discard(DASHBOARD_GROUP, self.channel_name)
        await self.channel_layer.group_discard(BOT_EVENTS_GROUP, self.channel_name)
        await self.channel_layer.group_discard(ALERTS_GROUP, self.channel_name)

        logger.debug(f"Dashboard WebSocket disconnected: {self.channel_name}")

    async def receive(self, text_data: str) -> None:
        """
        Handle incoming WebSocket messages.

        Supported message types:
            - ping: Health check, responds with pong
            - subscribe: Subscribe to specific symbol updates
            - unsubscribe: Unsubscribe from symbol updates
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
            # Subscribe to symbol-specific updates
            symbol = data.get("symbol")
            if symbol:
                group_name = f"symbol_{symbol}"
                await self.channel_layer.group_add(group_name, self.channel_name)
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "subscribed",
                            "symbol": symbol,
                        }
                    )
                )

        elif message_type == "unsubscribe":
            # Unsubscribe from symbol-specific updates
            symbol = data.get("symbol")
            if symbol:
                group_name = f"symbol_{symbol}"
                await self.channel_layer.group_discard(group_name, self.channel_name)
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "unsubscribed",
                            "symbol": symbol,
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

    # -------------------------------------------------------------------------
    # Portfolio Updates
    # -------------------------------------------------------------------------

    async def portfolio_update(self, event: dict[str, Any]) -> None:
        """
        Send portfolio update to WebSocket.

        Event data:
            - total_value: Total portfolio value
            - available_balance: Available balance
            - allocated_to_bots: Amount allocated to bots
            - drawdown: Current drawdown percentage
            - high_water_mark: Portfolio high water mark
            - timestamp: Update timestamp
        """
        await self.send(text_data=json.dumps(event))

    # -------------------------------------------------------------------------
    # Signal Updates
    # -------------------------------------------------------------------------

    async def signal_update(self, event: dict[str, Any]) -> None:
        """
        Send signal update to WebSocket.

        Event data:
            - symbol: Trading pair symbol
            - direction: Signal direction (BUY/SELL/HOLD)
            - confidence: Confidence score (0-100)
            - timestamp: Signal timestamp
            - meets_threshold: Whether signal meets confidence threshold
            - indicators: List of indicator contributions
        """
        await self.send(text_data=json.dumps(event))

    # -------------------------------------------------------------------------
    # Bot Updates
    # -------------------------------------------------------------------------

    async def bot_update(self, event: dict[str, Any]) -> None:
        """
        Send bot status update to WebSocket.

        Event data:
            - bot_id: Pionex bot ID
            - status: Bot status (ACTIVE/STOPPED/ERROR)
            - symbol: Trading pair symbol
            - invested: Investment amount
            - current_value: Current value
            - pnl: Profit/loss amount
            - pnl_percent: P&L percentage
        """
        await self.send(text_data=json.dumps(event))

    async def bot_created(self, event: dict[str, Any]) -> None:
        """
        Send bot created notification to WebSocket.

        Event data:
            - bot_id: Pionex bot ID
            - bot_type: Type of bot (GRID/DCA)
            - symbol: Trading pair symbol
            - invested: Investment amount
            - params: Bot parameters
            - reasoning: Reason for creation
            - timestamp: Creation timestamp

        Requirements:
            - 10.11: Log all bot creation events
        """
        await self.send(text_data=json.dumps(event))

    async def bot_stopped(self, event: dict[str, Any]) -> None:
        """
        Send bot stopped notification to WebSocket.

        Event data:
            - bot_id: Pionex bot ID
            - symbol: Trading pair symbol
            - reason: Reason for stopping
            - final_pnl: Final P&L
            - timestamp: Stop timestamp

        Requirements:
            - 10.11: Log all bot termination events
        """
        await self.send(text_data=json.dumps(event))

    async def bot_performance(self, event: dict[str, Any]) -> None:
        """
        Send bot performance update to WebSocket.

        Event data:
            - bot_id: Pionex bot ID
            - symbol: Trading pair symbol
            - pnl: Current P&L
            - pnl_percent: P&L percentage
            - current_value: Current value
            - is_underperforming: Whether bot is underperforming
        """
        await self.send(text_data=json.dumps(event))

    # -------------------------------------------------------------------------
    # Alerts
    # -------------------------------------------------------------------------

    async def alert(self, event: dict[str, Any]) -> None:
        """
        Send alert to WebSocket.

        Event data:
            - level: Alert level (info/warning/error/critical)
            - title: Alert title
            - message: Alert message
            - timestamp: Alert timestamp
            - source: Source of the alert
        """
        await self.send(text_data=json.dumps(event))

    async def trade_executed(self, event: dict[str, Any]) -> None:
        """
        Send trade executed notification to WebSocket.

        Event data:
            - trade_id: Trade ID
            - symbol: Trading pair symbol
            - side: Trade side (BUY/SELL)
            - price: Execution price
            - quantity: Trade quantity
            - is_simulated: Whether trade is simulated
            - timestamp: Execution timestamp
        """
        await self.send(text_data=json.dumps(event))

    # -------------------------------------------------------------------------
    # Rate Limit Updates
    # -------------------------------------------------------------------------

    async def rate_limit_update(self, event: dict[str, Any]) -> None:
        """
        Send rate limit update to WebSocket.

        Event data:
            - type: "rate_limit_update"
            - ip_usage: IP weight usage ratio (0-1)
            - account_usage: Account weight usage ratio (0-1)
            - ip_usage_percent: IP usage as percentage (0-100)
            - account_usage_percent: Account usage as percentage (0-100)
            - is_banned: Whether currently rate limited
            - ban_remaining: Seconds remaining in ban
            - status: Overall status (ok, warning, error)
            - status_message: Human-readable status message
            - timestamp: Update timestamp

        Requirements:
            - 4.6: Expose current usage metrics via dashboard
        """
        await self.send(text_data=json.dumps(event))

    async def rate_limit_alert(self, event: dict[str, Any]) -> None:
        """
        Send rate limit alert to WebSocket.

        Event data:
            - type: "rate_limit_alert"
            - level: Alert level (warning, error)
            - title: Alert title
            - message: Alert message
            - ban_remaining: Seconds remaining in ban (if rate limited)
            - timestamp: Alert timestamp

        Requirements:
            - 4.5: Log rate limit events and notify via WebSocket alert
        """
        await self.send(text_data=json.dumps(event))

    # -------------------------------------------------------------------------
    # Market Context Updates
    # -------------------------------------------------------------------------

    async def market_context_update(self, event: dict[str, Any]) -> None:
        """
        Send market context snapshot update to WebSocket.

        Event data:
            - snapshot_id: MarketContextSnapshot ID
            - symbol: Trading pair symbol (nullable for global)
            - regime: Detected regime label
            - btc_dominance: BTC dominance percentage
            - social_sentiment_score: Social sentiment polarity (-1.0 to 1.0)
            - net_exchange_flow: Net exchange flow
            - whale_tx_count: Whale transaction count
            - trend_strength_score: Trend strength score (0.0-1.0)
            - risk_regime_score: Risk regime score (0.0-1.0)
            - sentiment_regime_score: Sentiment regime score (0.0-1.0)
            - is_stale: Whether data is stale
            - is_degraded: Whether data is degraded
            - timestamp: Snapshot timestamp

        Requirements:
            - 4.3.2: WebSocket updates for context cards
        """
        await self.send(text_data=json.dumps(event))


class AnalysisConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time analysis updates.

    Handles live indicator updates and analysis data for the
    market analysis view.

    Groups:
        - analysis: General analysis updates
        - analysis_{symbol}: Symbol-specific analysis updates

    Message Types (outbound):
        - indicator_update: Technical indicator values
        - sentiment_update: Sentiment analysis data
        - analysis_complete: Full analysis cycle complete
        - pong: Response to ping

    Requirements:
        - 8.1: Real-time indicator updates
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._subscribed_symbols: set[str] = set()

    async def connect(self) -> None:
        """Handle WebSocket connection."""
        # Join general analysis group
        await self.channel_layer.group_add(ANALYSIS_GROUP, self.channel_name)

        await self.accept()

        logger.debug(f"Analysis WebSocket connected: {self.channel_name}")

    async def disconnect(self, close_code: int) -> None:
        """Handle WebSocket disconnection."""
        # Leave general analysis group
        await self.channel_layer.group_discard(ANALYSIS_GROUP, self.channel_name)

        # Leave all symbol-specific groups
        for symbol in self._subscribed_symbols:
            group_name = f"analysis_{symbol}"
            await self.channel_layer.group_discard(group_name, self.channel_name)

        self._subscribed_symbols.clear()

        logger.debug(f"Analysis WebSocket disconnected: {self.channel_name}")

    async def receive(self, text_data: str) -> None:
        """
        Handle incoming WebSocket messages.

        Supported message types:
            - ping: Health check, responds with pong
            - subscribe: Subscribe to symbol-specific analysis
            - unsubscribe: Unsubscribe from symbol analysis
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
            if symbol and symbol not in self._subscribed_symbols:
                group_name = f"analysis_{symbol}"
                await self.channel_layer.group_add(group_name, self.channel_name)
                self._subscribed_symbols.add(symbol)
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "subscribed",
                            "symbol": symbol,
                        }
                    )
                )

        elif message_type == "unsubscribe":
            symbol = data.get("symbol")
            if symbol and symbol in self._subscribed_symbols:
                group_name = f"analysis_{symbol}"
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

    # -------------------------------------------------------------------------
    # Indicator Updates
    # -------------------------------------------------------------------------

    async def indicator_update(self, event: dict[str, Any]) -> None:
        """
        Send indicator update to WebSocket.

        Event data:
            - symbol: Trading pair symbol
            - indicators: Dict of indicator name -> value
            - timestamp: Update timestamp
        """
        await self.send(text_data=json.dumps(event))

    async def sentiment_update(self, event: dict[str, Any]) -> None:
        """
        Send sentiment update to WebSocket.

        Event data:
            - fear_greed_index: Fear & Greed Index value (0-100)
            - signal: Sentiment signal (BUY/SELL/HOLD)
            - classification: Text classification (Extreme Fear, etc.)
            - timestamp: Update timestamp
        """
        await self.send(text_data=json.dumps(event))

    async def analysis_complete(self, event: dict[str, Any]) -> None:
        """
        Send analysis complete notification to WebSocket.

        Event data:
            - symbol: Trading pair symbol
            - signal: Generated signal data
            - indicators: All indicator values
            - sentiment: Sentiment data
            - timestamp: Completion timestamp
        """
        await self.send(text_data=json.dumps(event))

    async def signal_update(self, event: dict[str, Any]) -> None:
        """
        Send signal update to WebSocket (for analysis view).

        Event data:
            - symbol: Trading pair symbol
            - direction: Signal direction
            - confidence: Confidence score
            - indicators: Contributing indicators
            - timestamp: Signal timestamp
        """
        await self.send(text_data=json.dumps(event))
