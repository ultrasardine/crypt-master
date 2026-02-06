"""Trading views."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import DetailView, ListView

from apps.core.models import TradingPair

from .models import Signal, SignalDirection, Trade, TradeSide


class SignalListView(LoginRequiredMixin, ListView):
    """List view for trading signals with filtering. Filtered by user's active pairs."""

    model = Signal
    template_name = "trading/signal_list.html"
    context_object_name = "signals"
    paginate_by = 50

    def get_queryset(self):
        """Filter signals to user's active trading pairs."""
        queryset = Signal.objects.select_related("trading_pair").prefetch_related(
            "outcome", "outcome__bot"
        ).all()

        # Filter by user's active trading pairs
        if hasattr(self.request.user, "profile"):
            active_pairs = self.request.user.profile.active_trading_pairs
            if active_pairs:
                queryset = queryset.filter(trading_pair__symbol__in=active_pairs)
            else:
                # No pairs configured - show no signals
                queryset = queryset.none()

        # Filter by direction
        direction = self.request.GET.get("direction")
        if direction and direction in dict(SignalDirection.choices):
            queryset = queryset.filter(direction=direction)

        # Filter by executed status
        executed = self.request.GET.get("executed")
        if executed == "yes":
            queryset = queryset.executed()
        elif executed == "no":
            queryset = queryset.pending()

        # Filter by confidence threshold
        min_confidence = self.request.GET.get("min_confidence")
        if min_confidence:
            try:
                queryset = queryset.high_confidence(float(min_confidence))
            except ValueError:
                pass

        # Filter by trading pair
        symbol = self.request.GET.get("symbol")
        if symbol:
            queryset = queryset.for_pair(symbol)

        return queryset

    def get_context_data(self, **kwargs):
        """Add filter options and stats to context."""
        context = super().get_context_data(**kwargs)

        # Filter options
        context["direction_choices"] = SignalDirection.choices
        context["trading_pairs"] = TradingPair.objects.active()

        # Current filter values
        context["current_direction"] = self.request.GET.get("direction", "")
        context["current_executed"] = self.request.GET.get("executed", "")
        context["current_min_confidence"] = self.request.GET.get("min_confidence", "")
        context["current_symbol"] = self.request.GET.get("symbol", "")

        # Summary stats - filtered by user's active pairs
        active_pairs = []
        if hasattr(self.request.user, "profile"):
            active_pairs = self.request.user.profile.active_trading_pairs or []

        if active_pairs:
            recent = Signal.objects.filter(
                trading_pair__symbol__in=active_pairs
            ).recent(hours=24)
        else:
            recent = Signal.objects.none()

        context["total_signals_24h"] = recent.count()
        context["buy_signals_24h"] = recent.buy_signals().count() if active_pairs else 0
        context["sell_signals_24h"] = recent.sell_signals().count() if active_pairs else 0
        context["avg_confidence"] = recent.average_confidence() if active_pairs else None

        return context


class SignalDetailView(LoginRequiredMixin, DetailView):
    """Detail view for a single signal."""

    model = Signal
    template_name = "trading/signal_detail.html"
    context_object_name = "signal"

    def get_queryset(self):
        """Filter to user's active trading pairs."""
        queryset = Signal.objects.select_related("trading_pair")

        # Filter by user's active trading pairs
        if hasattr(self.request.user, "profile"):
            active_pairs = self.request.user.profile.active_trading_pairs
            if active_pairs:
                queryset = queryset.filter(trading_pair__symbol__in=active_pairs)
            else:
                queryset = queryset.none()

        return queryset

    def get_context_data(self, **kwargs):
        """Add related trades to context."""
        context = super().get_context_data(**kwargs)
        # Only show user's trades related to this signal
        context["trades"] = self.object.trades.filter(user=self.request.user)
        return context


class TradeListView(LoginRequiredMixin, ListView):
    """List view for trades with filtering and P&L display. User-isolated."""

    model = Trade
    template_name = "trading/trade_list.html"
    context_object_name = "trades"
    paginate_by = 50

    def get_queryset(self):
        """Filter trades to current user only."""
        queryset = Trade.objects.select_related("trading_pair", "signal").filter(
            user=self.request.user
        )

        # Filter by side
        side = self.request.GET.get("side")
        if side and side in dict(TradeSide.choices):
            queryset = queryset.filter(side=side)

        # Filter by mode (simulated/live)
        mode = self.request.GET.get("mode")
        if mode == "simulated":
            queryset = queryset.simulated()
        elif mode == "live":
            queryset = queryset.live()

        # Filter by status (open/closed)
        status = self.request.GET.get("status")
        if status == "open":
            queryset = queryset.open_positions()
        elif status == "closed":
            queryset = queryset.closed()

        # Filter by profitability
        profit = self.request.GET.get("profit")
        if profit == "profitable":
            queryset = queryset.profitable()
        elif profit == "unprofitable":
            queryset = queryset.unprofitable()

        # Filter by trading pair
        symbol = self.request.GET.get("symbol")
        if symbol:
            queryset = queryset.for_pair(symbol)

        return queryset

    def get_context_data(self, **kwargs):
        """Add filter options and trade statistics to context."""
        context = super().get_context_data(**kwargs)

        # Filter options
        context["side_choices"] = TradeSide.choices
        context["trading_pairs"] = TradingPair.objects.active()

        # Current filter values
        context["current_side"] = self.request.GET.get("side", "")
        context["current_mode"] = self.request.GET.get("mode", "")
        context["current_status"] = self.request.GET.get("status", "")
        context["current_profit"] = self.request.GET.get("profit", "")
        context["current_symbol"] = self.request.GET.get("symbol", "")

        # Trade statistics - user's trades only
        user_trades = Trade.objects.filter(user=self.request.user)

        # Live stats
        live_stats = user_trades.live().statistics()
        context["live_stats"] = live_stats

        # Simulated stats
        sim_stats = user_trades.simulated().statistics()
        context["sim_stats"] = sim_stats

        # Recent P&L - user's trades only
        context["recent_pnl"] = user_trades.live().recent(hours=24).total_pnl()
        context["recent_volume"] = user_trades.live().recent(hours=24).total_volume()

        return context


class TradeDetailView(LoginRequiredMixin, DetailView):
    """Detail view for a single trade. User-isolated."""

    model = Trade
    template_name = "trading/trade_detail.html"
    context_object_name = "trade"

    def get_queryset(self):
        """Only allow access to user's own trades."""
        return Trade.objects.select_related("trading_pair", "signal").filter(
            user=self.request.user
        )
