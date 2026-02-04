"""Dashboard views."""


from django.views.generic import TemplateView

from apps.bots.models import Bot
from apps.core.models import PortfolioSnapshot
from apps.trading.models import Signal, Trade


class DashboardHomeView(TemplateView):
    """Main dashboard home view with portfolio overview."""

    template_name = "dashboard/home.html"

    def get_context_data(self, **kwargs):
        """Add portfolio, bots, and signals data to context."""
        context = super().get_context_data(**kwargs)

        # Portfolio overview
        latest_snapshot = PortfolioSnapshot.objects.latest_live()
        context["portfolio"] = latest_snapshot
        context["portfolio_history"] = list(
            PortfolioSnapshot.objects.recent(hours=24).values(
                "created_at", "total_value", "drawdown"
            )[:24]
        )

        # Active bots summary
        active_bots = Bot.objects.active()
        context["active_bots"] = active_bots[:10]
        context["active_bots_count"] = active_bots.count()
        context["total_invested"] = active_bots.total_invested()
        context["total_bots_pnl"] = active_bots.total_pnl()

        # Bot type breakdown
        context["grid_bots_count"] = active_bots.by_type("GRID").count()
        context["dca_bots_count"] = active_bots.by_type("DCA").count()

        # Recent signals
        context["recent_signals"] = Signal.objects.recent(hours=24)[:10]
        context["actionable_signals_count"] = Signal.objects.actionable_recent(hours=24).count()
        context["high_confidence_signals_count"] = Signal.objects.high_confidence_recent(
            hours=24
        ).count()

        # Trade statistics
        trade_stats = Trade.objects.statistics(simulated=False)
        context["trade_stats"] = trade_stats
        context["recent_trades"] = Trade.objects.live().recent(hours=24)[:5]

        # System status
        context["dry_run_mode"] = self._get_dry_run_status()

        return context

    def _get_dry_run_status(self) -> bool:
        """Check if system is in dry-run mode."""
        from apps.core.models import SystemConfig

        return SystemConfig.get_value("dry_run_mode", default=True)
