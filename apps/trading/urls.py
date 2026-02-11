"""Trading URL configuration."""

from django.urls import path

from .views import (
    CancelAllOrdersView,
    CancelOrderView,
    FillListView,
    OrderDetailView,
    OrderHistoryView,
    OrderListView,
    SignalDetailView,
    SignalListView,
    TickerListView,
    TradeDetailView,
    TradeListView,
)

app_name = "trading"

urlpatterns = [
    path("signals/", SignalListView.as_view(), name="signal_list"),
    path("signals/<int:pk>/", SignalDetailView.as_view(), name="signal_detail"),
    path("trades/", TradeListView.as_view(), name="trade_list"),
    path("trades/<int:pk>/", TradeDetailView.as_view(), name="trade_detail"),
    # Pionex Order Management
    path("orders/", OrderListView.as_view(), name="order_list"),
    path("orders/history/", OrderHistoryView.as_view(), name="order_history"),
    path(
        "orders/<str:symbol>/<int:order_id>/",
        OrderDetailView.as_view(),
        name="order_detail",
    ),
    path(
        "orders/<str:symbol>/<str:order_id>/cancel/",
        CancelOrderView.as_view(),
        name="cancel_order",
    ),
    path(
        "orders/<str:symbol>/cancel-all/",
        CancelAllOrdersView.as_view(),
        name="cancel_all_orders",
    ),
    # Pionex Fill History
    path("fills/", FillListView.as_view(), name="fill_list"),
    # Pionex Market Data
    path("tickers/", TickerListView.as_view(), name="ticker_list"),
]
