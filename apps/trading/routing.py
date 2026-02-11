"""
WebSocket routing for trading.

Defines URL patterns for WebSocket connections:
- /ws/trading/ - Real-time trading updates (orders, fills, balances)
"""

from django.urls import path

from .consumers import TradingConsumer

websocket_urlpatterns = [
    path("ws/trading/", TradingConsumer.as_asgi()),
]
