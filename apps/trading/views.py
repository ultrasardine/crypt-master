"""Trading views."""

from django.views.generic import DetailView, ListView

from apps.core.models import TradingPair

from .models import Signal, SignalDirection, Trade, TradeSide


class SignalListView(ListView):
    """List view for trading signals with filtering."""

    model = Signal
    template_name = "trading/signal_list.html"
    context_object_name = "signals"
    paginate_by = 50

    def get_queryset(self):
        """Filter signals based on query parameters."""
        queryset = Signal.objects.select_related("trading_pair").all()

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

        # Summary stats
        recent = Signal.objects.recent(hours=24)
        context["total_signals_24h"] = recent.count()
        context["buy_signals_24h"] = recent.buy_signals().count()
        context["sell_signals_24h"] = recent.sell_signals().count()
        context["avg_confidence"] = recent.average_confidence()

        return context


class SignalDetailView(DetailView):
    """Detail view for a single signal."""

    model = Signal
    template_name = "trading/signal_detail.html"
    context_object_name = "signal"

    def get_queryset(self):
        """Include related trading pair."""
        return Signal.objects.select_related("trading_pair")

    def get_context_data(self, **kwargs):
        """Add related trades to context."""
        context = super().get_context_data(**kwargs)
        context["trades"] = self.object.trades.all()
        return context


class TradeListView(ListView):
    """List view for trades with filtering and P&L display."""

    model = Trade
    template_name = "trading/trade_list.html"
    context_object_name = "trades"
    paginate_by = 50

    def get_queryset(self):
        """Filter trades based on query parameters."""
        queryset = Trade.objects.select_related("trading_pair", "signal").all()

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

        # Trade statistics for live trades
        live_stats = Trade.objects.statistics(simulated=False)
        context["live_stats"] = live_stats

        # Trade statistics for simulated trades
        sim_stats = Trade.objects.statistics(simulated=True)
        context["sim_stats"] = sim_stats

        # Recent P&L
        context["recent_pnl"] = Trade.objects.live().recent(hours=24).total_pnl()
        context["recent_volume"] = Trade.objects.live().recent(hours=24).total_volume()

        return context


class TradeDetailView(DetailView):
    """Detail view for a single trade."""

    model = Trade
    template_name = "trading/trade_detail.html"
    context_object_name = "trade"

    def get_queryset(self):
        """Include related objects."""
        return Trade.objects.select_related("trading_pair", "signal")
