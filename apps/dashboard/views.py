"""Dashboard views."""

import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from apps.bots.models import Bot
from apps.core.models import MarketSentimentData, PortfolioSnapshot
from apps.trading.models import Signal, SignalAccuracyMetrics, Trade


class DashboardHomeView(LoginRequiredMixin, TemplateView):
    """Main dashboard home view with portfolio overview. User-isolated."""

    template_name = "dashboard/home.html"

    def get_context_data(self, **kwargs):
        """Add portfolio, bots, and signals data to context. All user-isolated."""
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Portfolio overview - user's snapshots only
        latest_snapshot = PortfolioSnapshot.objects.filter(user=user).live().first()
        context["portfolio"] = latest_snapshot
        context["portfolio_history"] = list(
            PortfolioSnapshot.objects.filter(user=user).recent(hours=24).values(
                "created_at", "total_value", "drawdown"
            )[:24]
        )

        # Active bots summary - user's bots only
        user_bots = Bot.objects.filter(user=user)
        active_bots = user_bots.active()
        context["active_bots"] = active_bots[:10]
        context["active_bots_count"] = active_bots.count()
        context["total_invested"] = active_bots.total_invested()
        context["total_bots_pnl"] = active_bots.total_pnl()

        # Bot type breakdown - user's bots only
        context["grid_bots_count"] = active_bots.by_type("GRID").count()
        context["dca_bots_count"] = active_bots.by_type("DCA").count()

        # Recent signals - filtered by user's active trading pairs
        active_pairs = []
        if hasattr(user, "profile"):
            active_pairs = user.profile.active_trading_pairs or []

        if active_pairs:
            user_signals = Signal.objects.filter(trading_pair__symbol__in=active_pairs)
            context["recent_signals"] = user_signals.recent(hours=24)[:10]
            context["actionable_signals_count"] = user_signals.actionable_recent(hours=24).count()
            context["high_confidence_signals_count"] = user_signals.high_confidence_recent(
                hours=24
            ).count()
        else:
            context["recent_signals"] = Signal.objects.none()
            context["actionable_signals_count"] = 0
            context["high_confidence_signals_count"] = 0

        # Trade statistics - user's trades only
        user_trades = Trade.objects.filter(user=user)
        trade_stats = user_trades.live().statistics()
        context["trade_stats"] = trade_stats
        context["recent_trades"] = user_trades.live().recent(hours=24)[:5]

        # System status
        context["dry_run_mode"] = self._get_dry_run_status()

        # Market sentiment data
        context["market_sentiment"] = self._get_market_sentiment()

        # Signal accuracy metrics
        context["signal_accuracy"] = self._get_signal_accuracy(user)

        # Chart data
        context["portfolio_chart_data"] = json.dumps(self._get_portfolio_chart_data(user))
        context["bot_performance_data"] = json.dumps(self._get_bot_performance_data(user))

        return context

    def _get_dry_run_status(self) -> bool:
        """Check if system is in dry-run mode."""
        from apps.core.models import SystemConfig

        return SystemConfig.get_value("dry_run_mode", default=True)

    def _get_market_sentiment(self) -> MarketSentimentData | None:
        """
        Get latest market sentiment data.

        Returns:
            Latest MarketSentimentData or None if no data available.

        Requirements: 4.8, 4.9, 4.10
        """
        return MarketSentimentData.get_latest()

    def _get_signal_accuracy(self, user) -> dict:
        """
        Get signal accuracy metrics for user.

        Args:
            user: The user to get accuracy metrics for.

        Returns:
            Dictionary with accuracy metrics or empty dict if no data available.

        Requirements: 3.6
        """
        try:
            metrics = SignalAccuracyMetrics.objects.filter(user=user).latest("calculated_at")
            return {
                "overall_accuracy": metrics.overall_accuracy,
                "buy_accuracy": metrics.buy_accuracy,
                "sell_accuracy": metrics.sell_accuracy,
                "confidence_correlation": metrics.confidence_correlation,
                "total_executed_signals": metrics.total_executed_signals,
                "profitable_signals": metrics.profitable_signals,
                "unprofitable_signals": metrics.unprofitable_signals,
                "average_pnl_percent": metrics.average_pnl_percent,
                "calculated_at": metrics.calculated_at,
            }
        except SignalAccuracyMetrics.DoesNotExist:
            return {}

    def _get_portfolio_chart_data(self, user) -> list[dict]:
        """
        Get portfolio value history for charts.

        Args:
            user: The user to get portfolio history for.

        Returns:
            List of dictionaries with timestamp, total_value, and drawdown.

        Requirements: 5.1, 5.2, 5.3, 5.4
        """
        # Get snapshots for the last 30 days
        snapshots = PortfolioSnapshot.objects.filter(user=user).live().recent(hours=24 * 30)

        return [
            {
                "timestamp": snapshot.created_at.isoformat(),
                "total_value": float(snapshot.total_value),
                "drawdown": snapshot.drawdown,
                "high_water_mark": float(snapshot.high_water_mark),
            }
            for snapshot in snapshots
        ]

    def _get_bot_performance_data(self, user) -> list[dict]:
        """
        Get bot P&L history for charts.

        Args:
            user: The user to get bot performance for.

        Returns:
            List of dictionaries with bot performance data.

        Requirements: 5.1, 5.2, 5.3, 5.4
        """
        # Get active and recently stopped bots
        bots = Bot.objects.filter(user=user).filter(
            status__in=["ACTIVE", "STOPPED"]
        ).order_by("-created_at")[:20]

        return [
            {
                "bot_id": bot.id,
                "bot_type": bot.bot_type,
                "trading_pair": bot.trading_pair.symbol if bot.trading_pair else "N/A",
                "current_pnl": float(bot.current_pnl) if bot.current_pnl else 0.0,
                "pnl_percent": bot.pnl_percent or 0.0,
                "status": bot.status,
                "created_at": bot.created_at.isoformat(),
                "stopped_at": bot.stopped_at.isoformat() if bot.stopped_at else None,
            }
            for bot in bots
        ]
