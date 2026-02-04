"""
WebSocket routing for dashboard and analysis.

Defines URL patterns for WebSocket connections:
- /ws/dashboard/ - Real-time dashboard updates
- /ws/analysis/ - Real-time analysis/indicator updates
"""

from django.urls import path

from .consumers import AnalysisConsumer, DashboardConsumer

websocket_urlpatterns = [
    path("ws/dashboard/", DashboardConsumer.as_asgi()),
    path("ws/analysis/", AnalysisConsumer.as_asgi()),
]
