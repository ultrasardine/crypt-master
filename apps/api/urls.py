"""API URL configuration."""

from django.urls import path

from .views import (
    AnalysisView,
    BacktestView,
    BotDetailView,
    BotListView,
    ConfigView,
    PortfolioHistoryView,
    PortfolioView,
    SignalDetailView,
    SignalListView,
    TradeDetailView,
    TradeListView,
    TradeStatisticsView,
    TradingPairListView,
)

app_name = "api"

urlpatterns = [
    # Portfolio endpoints
    path("portfolio/", PortfolioView.as_view(), name="portfolio"),
    path("portfolio/history/", PortfolioHistoryView.as_view(), name="portfolio_history"),
    # Trading pairs
    path("pairs/", TradingPairListView.as_view(), name="trading_pair_list"),
    # Signals endpoints
    path("signals/", SignalListView.as_view(), name="signal_list"),
    path("signals/<int:pk>/", SignalDetailView.as_view(), name="signal_detail"),
    # Bots endpoints
    path("bots/", BotListView.as_view(), name="bot_list"),
    path("bots/<int:pk>/", BotDetailView.as_view(), name="bot_detail"),
    # Trades endpoints
    path("trades/", TradeListView.as_view(), name="trade_list"),
    path("trades/<int:pk>/", TradeDetailView.as_view(), name="trade_detail"),
    path("trades/statistics/", TradeStatisticsView.as_view(), name="trade_statistics"),
    # Analysis endpoint
    path("analysis/<str:symbol>/", AnalysisView.as_view(), name="analysis"),
    # Backtest endpoint
    path("backtest/", BacktestView.as_view(), name="backtest"),
    # Configuration endpoints
    path("config/", ConfigView.as_view(), name="config"),
]
