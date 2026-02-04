"""
Messaging module for inter-service communication.

Provides Redis pub/sub functionality for signal distribution between
the market analysis agent and bot management agent, as well as WebSocket
broadcasting utilities for real-time dashboard updates.
"""

from lib.messaging.signals import (
    SIGNALS_CHANNEL,
    SignalMessage,
    SignalPublisher,
    SignalSubscriber,
    signal_from_json,
    signal_to_json,
)
from lib.messaging.websocket import (
    WebSocketBroadcaster,
    get_broadcaster,
)

__all__ = [
    # Redis pub/sub
    "SIGNALS_CHANNEL",
    "SignalMessage",
    "SignalPublisher",
    "SignalSubscriber",
    "signal_from_json",
    "signal_to_json",
    # WebSocket broadcasting
    "WebSocketBroadcaster",
    "get_broadcaster",
]
