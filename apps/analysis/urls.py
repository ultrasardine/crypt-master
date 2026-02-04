"""Analysis URL configuration."""

from django.urls import path

from .views import AnalysisView, BacktestView, IndicatorDetailView, RunBacktestView

app_name = "analysis"

urlpatterns = [
    path("", AnalysisView.as_view(), name="analysis"),
    path("indicator/<str:indicator>/", IndicatorDetailView.as_view(), name="indicator_detail"),
    path("backtest/", BacktestView.as_view(), name="backtest"),
    path("backtest/run/", RunBacktestView.as_view(), name="run_backtest"),
]
