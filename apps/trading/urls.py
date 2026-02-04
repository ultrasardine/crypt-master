"""Trading URL configuration."""

from django.urls import path

from .views import SignalDetailView, SignalListView, TradeDetailView, TradeListView

app_name = "trading"

urlpatterns = [
    path("signals/", SignalListView.as_view(), name="signal_list"),
    path("signals/<int:pk>/", SignalDetailView.as_view(), name="signal_detail"),
    path("trades/", TradeListView.as_view(), name="trade_list"),
    path("trades/<int:pk>/", TradeDetailView.as_view(), name="trade_detail"),
]
