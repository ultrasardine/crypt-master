"""Analysis URL configuration."""

from django.urls import path

from .views import (
    AnalysisView,
    BacktestView,
    IndicatorDetailView,
    MarketIntelligenceView,
    RegimeDetectorView,
    RunBacktestView,
    SignalQualityView,
)

app_name = "analysis"

urlpatterns = [
    path("", AnalysisView.as_view(), name="analysis"),
    path("market-intelligence/", MarketIntelligenceView.as_view(), name="market_intelligence"),
    path("indicator/<str:indicator>/", IndicatorDetailView.as_view(), name="indicator_detail"),
    path("backtest/", BacktestView.as_view(), name="backtest"),
    path("backtest/run/", RunBacktestView.as_view(), name="run_backtest"),
    path("regimes/", RegimeDetectorView.as_view(), name="regimes"),
    path("signal-quality/", SignalQualityView.as_view(), name="signal_quality"),
]
