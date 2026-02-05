"""Dashboard views."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from apps.bots.models import Bot
from apps.core.models import PortfolioSnapshot
from apps.trading.models import Signal, Trade


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

        return context

    def _get_dry_run_status(self) -> bool:
        """Check if system is in dry-run mode."""
        from apps.core.models import SystemConfig

        return SystemConfig.get_value("dry_run_mode", default=True)
