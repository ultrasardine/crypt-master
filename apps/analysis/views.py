"""Analysis views."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Avg
from django.http import JsonResponse
from django.views import View
from django.views.generic import TemplateView

from apps.core.models import MarketContextSnapshot, MarketSentimentData, TradingPair
from apps.trading.models import Signal, SignalOutcome, StrategyPattern
from lib.analysis.context import Regime
from lib.backtesting import Backtester, BacktesterConfig
from lib.pionex.models import Candle


class AnalysisView(LoginRequiredMixin, TemplateView):
    """View for displaying market analysis with live indicators and signal history."""

    template_name = "analysis/analysis.html"

    def get_context_data(self, **kwargs):
        """Add analysis data to context. Filtered by user's active pairs."""
        context = super().get_context_data(**kwargs)

        # Get selected trading pair or default
        symbol = self.request.GET.get("symbol", "BTC_USDT")
        context["current_symbol"] = symbol
        context["trading_pairs"] = TradingPair.objects.active()

        # Verify user has access to this pair
        active_pairs = []
        if hasattr(self.request.user, "profile"):
            active_pairs = self.request.user.profile.active_trading_pairs or []

        if active_pairs and symbol not in active_pairs:
            # User doesn't have this pair in their active list
            context["trading_pair"] = None
            context["access_denied"] = True
            return context

        # Get the trading pair
        try:
            trading_pair = TradingPair.objects.get(symbol=symbol)
            context["trading_pair"] = trading_pair
        except TradingPair.DoesNotExist:
            context["trading_pair"] = None
            return context

        # Get recent signals for this pair
        context["recent_signals"] = Signal.objects.for_pair(symbol)[:20]

        # Get latest signal with full indicator breakdown
        latest_signal = Signal.objects.latest_for_pair(symbol)
        context["latest_signal"] = latest_signal

        if latest_signal and latest_signal.indicators:
            # Parse indicator data from the signal
            # indicators is a list of dicts: [{"name": "RSI", "signal": "BUY", ...}, ...]
            indicators = latest_signal.indicators
            context["indicators"] = indicators

            # Group indicators by type for display
            technical_indicators = {}
            sentiment_indicators = {}
            volume_indicators = {}

            for ind in indicators:
                if isinstance(ind, dict):
                    name = ind.get("name", "").upper()
                    # Categorize indicators
                    if name in ("RSI", "MACD", "BB", "ADX", "STOCH"):
                        technical_indicators[name.lower()] = ind
                    elif name in ("FGI", "NEWS"):
                        sentiment_indicators[name.lower()] = ind
                    elif name == "VOL":
                        volume_indicators[name.lower()] = ind
                    else:
                        # Default to technical
                        technical_indicators[name.lower()] = ind

            context["technical"] = technical_indicators
            context["sentiment"] = sentiment_indicators
            context["volume"] = volume_indicators

        # Signal statistics for this pair
        pair_signals = Signal.objects.for_pair(symbol)
        context["total_signals"] = pair_signals.count()
        context["buy_signals"] = pair_signals.buy_signals().count()
        context["sell_signals"] = pair_signals.sell_signals().count()
        context["avg_confidence"] = pair_signals.average_confidence()

        return context


class IndicatorDetailView(LoginRequiredMixin, TemplateView):
    """Detailed view for a specific indicator."""

    template_name = "analysis/indicator_detail.html"

    def get_context_data(self, **kwargs):
        """Add indicator details to context."""
        context = super().get_context_data(**kwargs)

        indicator_name = self.kwargs.get("indicator", "rsi")
        symbol = self.request.GET.get("symbol", "BTC_USDT")

        context["indicator_name"] = indicator_name
        context["current_symbol"] = symbol
        context["trading_pairs"] = TradingPair.objects.active()

        # Get signals with this indicator data
        signals = Signal.objects.for_pair(symbol)[:50]
        indicator_history = []

        for signal in signals:
            if signal.indicators:
                # indicators is a list of dicts
                for ind in signal.indicators:
                    if isinstance(ind, dict) and ind.get("name", "").lower() == indicator_name:
                        indicator_history.append(
                            {
                                "timestamp": signal.created_at,
                                "value": ind.get("value"),
                                "signal_direction": signal.direction,
                                "confidence": signal.confidence,
                            }
                        )

        context["indicator_history"] = indicator_history

        # Indicator descriptions
        indicator_info = {
            "rsi": {
                "name": "Relative Strength Index (RSI)",
                "description": "Momentum oscillator measuring speed and magnitude of price changes. Values above 70 indicate overbought, below 30 indicate oversold.",
                "range": "0-100",
            },
            "macd": {
                "name": "MACD",
                "description": "Trend-following momentum indicator showing relationship between two EMAs. Bullish when MACD crosses above signal line.",
                "range": "Variable",
            },
            "bollinger": {
                "name": "Bollinger Bands",
                "description": "Volatility indicator with upper and lower bands around a moving average. Price near upper band may indicate overbought.",
                "range": "Variable",
            },
            "adx": {
                "name": "Average Directional Index (ADX)",
                "description": "Trend strength indicator. Values above 25 indicate strong trend, below 20 indicate weak/no trend.",
                "range": "0-100",
            },
            "stochastic": {
                "name": "Stochastic Oscillator",
                "description": "Momentum indicator comparing closing price to price range. Values above 80 indicate overbought, below 20 indicate oversold.",
                "range": "0-100",
            },
        }

        context["indicator_info"] = indicator_info.get(
            indicator_name,
            {
                "name": indicator_name.upper(),
                "description": "Technical indicator",
                "range": "Variable",
            },
        )

        return context


class BacktestView(LoginRequiredMixin, TemplateView):
    """View for running backtests and displaying results."""

    template_name = "analysis/backtest.html"

    def get_context_data(self, **kwargs):
        """Add backtest form data to context."""
        context = super().get_context_data(**kwargs)

        # Get trading pairs for the form
        context["trading_pairs"] = TradingPair.objects.active()
        context["current_symbol"] = self.request.GET.get("symbol", "BTC_USDT")

        # Default configuration values
        context["default_config"] = {
            "initial_capital": "10000",
            "slippage_pct": "0.1",
            "commission_pct": "0.1",
            "min_confidence": "85",
            "max_position_pct": "10",
            "max_risk_per_trade_pct": "2",
            "max_drawdown_pct": "20",
        }

        # Available intervals
        context["intervals"] = [
            {"value": "1H", "label": "1 Hour"},
            {"value": "4H", "label": "4 Hours"},
            {"value": "1D", "label": "1 Day"},
        ]

        return context


class RunBacktestView(LoginRequiredMixin, View):
    """API endpoint for running a backtest."""

    def post(self, request):
        """Run a backtest with the provided parameters."""
        try:
            # Parse request data
            data = json.loads(request.body)

            symbol = data.get("symbol", "BTC_USDT")
            interval = data.get("interval", "1H")
            num_candles = int(data.get("num_candles", 500))

            # Parse configuration
            config = BacktesterConfig(
                initial_capital=Decimal(data.get("initial_capital", "10000")),
                slippage_pct=float(data.get("slippage_pct", "0.1")) / 100,
                commission_pct=float(data.get("commission_pct", "0.1")) / 100,
                min_confidence=float(data.get("min_confidence", "85")),
                max_position_pct=float(data.get("max_position_pct", "10")) / 100,
                max_risk_per_trade_pct=float(data.get("max_risk_per_trade_pct", "2")) / 100,
                max_drawdown_pct=float(data.get("max_drawdown_pct", "20")) / 100,
            )

            # Generate synthetic candles for demo (in production, fetch from Pionex)
            candles = self._generate_demo_candles(num_candles, interval)

            # Run backtest
            backtester = Backtester(config)
            result = backtester.run(candles, symbol=symbol)

            # Generate report
            report = backtester.generate_report(result)

            return JsonResponse({"success": True, "report": report})

        except ValueError as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)
        except Exception as e:
            return JsonResponse({"success": False, "error": f"Backtest failed: {e}"}, status=500)

    def _generate_demo_candles(self, num_candles: int, interval: str) -> list[Candle]:
        """Generate demo candle data for backtesting."""
        import random

        # Determine time delta based on interval
        interval_deltas = {
            "1H": timedelta(hours=1),
            "4H": timedelta(hours=4),
            "1D": timedelta(days=1),
        }
        delta = interval_deltas.get(interval, timedelta(hours=1))

        start_time = datetime.now(tz=UTC) - (delta * num_candles)
        candles = []
        price = 50000.0  # Starting price (e.g., BTC)

        for i in range(num_candles):
            # Random walk with slight upward bias
            change = random.uniform(-0.02, 0.022)
            price = price * (1 + change)

            # Generate OHLC
            open_price = price * (1 + random.uniform(-0.005, 0.005))
            high_price = max(open_price, price) * (1 + random.uniform(0, 0.01))
            low_price = min(open_price, price) * (1 - random.uniform(0, 0.01))
            close_price = price
            volume = random.uniform(100, 1000)

            candle = Candle(
                timestamp=start_time + (delta * i),
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume,
            )
            candles.append(candle)

        return candles


class RegimeDetectorView(LoginRequiredMixin, TemplateView):
    """
    View for displaying market regime detection and context scores.

    Shows current regime with color-coded badge, timeline of regime changes,
    and context scores as progress bars.

    Requirements:
    - 4.1.1: View at URL /analysis/regimes/
    - 4.1.2: Display current regime with color-coded badge
    - 4.1.3: Show timeline/chart of regime changes over last 7/30 days
    - 4.1.4: Display current context scores as progress bars
    - 4.1.5: Follow Tailwind design system
    - 4.1.6: User-isolated with LoginRequiredMixin
    """

    template_name = "analysis/regimes.html"

    # Regime color mapping for badges
    REGIME_COLORS = {
        Regime.RISK_ON.value: {
            "bg": "bg-emerald-900/50",
            "text": "text-emerald-400",
            "border": "border-emerald-500/50",
            "dot": "bg-emerald-400",
        },
        Regime.RISK_OFF.value: {
            "bg": "bg-red-900/50",
            "text": "text-red-400",
            "border": "border-red-500/50",
            "dot": "bg-red-400",
        },
        Regime.RANGE_BOUND.value: {
            "bg": "bg-slate-600",
            "text": "text-slate-300",
            "border": "border-slate-500/50",
            "dot": "bg-slate-400",
        },
        Regime.TRENDING_UP.value: {
            "bg": "bg-sky-900/50",
            "text": "text-sky-400",
            "border": "border-sky-500/50",
            "dot": "bg-sky-400",
        },
        Regime.TRENDING_DOWN.value: {
            "bg": "bg-amber-900/50",
            "text": "text-amber-400",
            "border": "border-amber-500/50",
            "dot": "bg-amber-400",
        },
        Regime.UNKNOWN.value: {
            "bg": "bg-slate-700",
            "text": "text-slate-400",
            "border": "border-slate-600",
            "dot": "bg-slate-500",
        },
    }

    def get_context_data(self, **kwargs):
        """Add regime detection data to context."""
        context = super().get_context_data(**kwargs)

        # Get time range from query params (default: 7 days)
        days = self._get_days_param()
        context["selected_days"] = days
        context["time_range_options"] = [
            {"value": 7, "label": "Last 7 Days"},
            {"value": 30, "label": "Last 30 Days"},
        ]

        # Get latest snapshot for current regime
        latest_snapshot = MarketContextSnapshot.objects.order_by("-timestamp").first()
        context["latest_snapshot"] = latest_snapshot

        if latest_snapshot:
            # Get regime colors for display
            regime_value = latest_snapshot.regime or Regime.UNKNOWN.value
            context["regime_colors"] = self.REGIME_COLORS.get(
                regime_value, self.REGIME_COLORS[Regime.UNKNOWN.value]
            )
            context["regime_display"] = self._format_regime_display(regime_value)

            # Context scores for progress bars
            context["context_scores"] = {
                "trend_strength": {
                    "value": latest_snapshot.trend_strength_score,
                    "percentage": self._to_percentage(latest_snapshot.trend_strength_score),
                    "label": "Trend Strength",
                },
                "risk_regime": {
                    "value": latest_snapshot.risk_regime_score,
                    "percentage": self._to_percentage(latest_snapshot.risk_regime_score),
                    "label": "Risk Regime",
                },
                "sentiment_regime": {
                    "value": latest_snapshot.sentiment_regime_score,
                    "percentage": self._to_percentage(latest_snapshot.sentiment_regime_score),
                    "label": "Sentiment Regime",
                },
            }

        # Get regime history for timeline
        cutoff = datetime.now(tz=UTC) - timedelta(days=days)
        regime_history = (
            MarketContextSnapshot.objects.filter(timestamp__gte=cutoff)
            .order_by("timestamp")
            .values("timestamp", "regime", "trend_strength_score", "risk_regime_score", "sentiment_regime_score")
        )

        # Process regime history for chart
        context["regime_history"] = self._process_regime_history(list(regime_history))
        context["regime_transitions"] = self._get_regime_transitions(list(regime_history))

        # All regime colors for legend
        context["all_regime_colors"] = self.REGIME_COLORS

        return context

    def _get_days_param(self) -> int:
        """Get and validate days parameter from request."""
        try:
            days = int(self.request.GET.get("days", 7))
            if days not in [7, 30]:
                days = 7
        except (ValueError, TypeError):
            days = 7
        return days

    def _to_percentage(self, value: float | None) -> int:
        """Convert 0.0-1.0 score to percentage."""
        if value is None:
            return 0
        return int(value * 100)

    def _format_regime_display(self, regime: str) -> str:
        """Format regime value for display."""
        return regime.replace("_", " ").title()

    def _process_regime_history(self, history: list[dict]) -> str:
        """Process regime history for Chart.js timeline."""
        if not history:
            return json.dumps([])

        chart_data = []
        for entry in history:
            chart_data.append({
                "timestamp": entry["timestamp"].isoformat() if entry["timestamp"] else None,
                "regime": entry["regime"] or Regime.UNKNOWN.value,
                "trend_strength": entry["trend_strength_score"],
                "risk_regime": entry["risk_regime_score"],
                "sentiment_regime": entry["sentiment_regime_score"],
            })

        return json.dumps(chart_data)

    def _get_regime_transitions(self, history: list[dict]) -> list[dict]:
        """Extract regime transitions from history."""
        if not history:
            return []

        transitions = []
        prev_regime = None

        for entry in history:
            current_regime = entry["regime"] or Regime.UNKNOWN.value
            if prev_regime is not None and current_regime != prev_regime:
                transitions.append({
                    "timestamp": entry["timestamp"],
                    "from_regime": prev_regime,
                    "to_regime": current_regime,
                    "from_colors": self.REGIME_COLORS.get(
                        prev_regime, self.REGIME_COLORS[Regime.UNKNOWN.value]
                    ),
                    "to_colors": self.REGIME_COLORS.get(
                        current_regime, self.REGIME_COLORS[Regime.UNKNOWN.value]
                    ),
                    "from_display": self._format_regime_display(prev_regime),
                    "to_display": self._format_regime_display(current_regime),
                })
            prev_regime = current_regime

        # Return most recent transitions first
        return list(reversed(transitions))[:10]


class SignalQualityView(LoginRequiredMixin, TemplateView):
    """
    View for displaying signal quality analysis by regime and indicator combination.

    Shows signal performance grouped by regime with win rate, average P&L,
    total signals, and average confidence. Also displays active StrategyPattern
    records with their performance metrics.

    Requirements:
    - 4.2.1: View at URL /analysis/signal-quality/
    - 4.2.2: Show table of signal performance grouped by regime
    - 4.2.3: Show breakdown by indicator combination
    - 4.2.4: Support filtering by date range, symbol, and regime
    - 4.2.5: Display active StrategyPattern records
    - 4.2.6: Follow Tailwind design system and user-isolated
    """

    template_name = "analysis/signal_quality.html"

    # Regime color mapping (reuse from RegimeDetectorView)
    REGIME_COLORS = {
        Regime.RISK_ON.value: {
            "bg": "bg-emerald-900/50",
            "text": "text-emerald-400",
            "border": "border-emerald-500/50",
            "dot": "bg-emerald-400",
        },
        Regime.RISK_OFF.value: {
            "bg": "bg-red-900/50",
            "text": "text-red-400",
            "border": "border-red-500/50",
            "dot": "bg-red-400",
        },
        Regime.RANGE_BOUND.value: {
            "bg": "bg-slate-600",
            "text": "text-slate-300",
            "border": "border-slate-500/50",
            "dot": "bg-slate-400",
        },
        Regime.TRENDING_UP.value: {
            "bg": "bg-sky-900/50",
            "text": "text-sky-400",
            "border": "border-sky-500/50",
            "dot": "bg-sky-400",
        },
        Regime.TRENDING_DOWN.value: {
            "bg": "bg-amber-900/50",
            "text": "text-amber-400",
            "border": "border-amber-500/50",
            "dot": "bg-amber-400",
        },
        Regime.UNKNOWN.value: {
            "bg": "bg-slate-700",
            "text": "text-slate-400",
            "border": "border-slate-600",
            "dot": "bg-slate-500",
        },
    }

    def get_context_data(self, **kwargs):
        """Add signal quality data to context."""
        context = super().get_context_data(**kwargs)

        # Get filter parameters
        days = self._get_days_param()
        symbol = self.request.GET.get("symbol", "")
        regime_filter = self.request.GET.get("regime", "")

        context["selected_days"] = days
        context["selected_symbol"] = symbol
        context["selected_regime"] = regime_filter

        # Filter options
        context["time_range_options"] = [
            {"value": 7, "label": "Last 7 Days"},
            {"value": 30, "label": "Last 30 Days"},
            {"value": 90, "label": "Last 90 Days"},
        ]
        context["trading_pairs"] = TradingPair.objects.active()
        context["regime_options"] = [
            {"value": r.value, "label": self._format_regime_display(r.value)}
            for r in Regime
        ]
        context["all_regime_colors"] = self.REGIME_COLORS

        # Get signal outcomes with filters
        cutoff = datetime.now(tz=UTC) - timedelta(days=days)
        outcomes_qs = SignalOutcome.objects.filter(
            recorded_at__gte=cutoff
        ).select_related("signal", "signal__trading_pair")

        if symbol:
            outcomes_qs = outcomes_qs.filter(signal__trading_pair__symbol=symbol)

        if regime_filter:
            outcomes_qs = outcomes_qs.filter(signal__regime=regime_filter)

        outcomes = list(outcomes_qs)

        # Calculate performance by regime
        context["regime_performance"] = self._calculate_regime_performance(outcomes)

        # Calculate performance by indicator combination
        context["indicator_performance"] = self._calculate_indicator_performance(outcomes)

        # Get active strategy patterns
        patterns_qs = StrategyPattern.objects.active()
        if regime_filter:
            patterns_qs = patterns_qs.for_regime(regime_filter)
        context["strategy_patterns"] = patterns_qs[:20]

        # Summary statistics
        context["summary_stats"] = self._calculate_summary_stats(outcomes)

        return context

    def _get_days_param(self) -> int:
        """Get and validate days parameter from request."""
        try:
            days = int(self.request.GET.get("days", 30))
            if days not in [7, 30, 90]:
                days = 30
        except (ValueError, TypeError):
            days = 30
        return days

    def _format_regime_display(self, regime: str) -> str:
        """Format regime value for display."""
        return regime.replace("_", " ").title()

    def _calculate_regime_performance(
        self, outcomes: list[SignalOutcome]
    ) -> list[dict]:
        """
        Calculate signal performance grouped by regime.

        Returns a list of dicts with regime, win_rate, avg_pnl, total_signals,
        avg_confidence, and colors for display.
        """
        # Group outcomes by regime
        regime_groups: dict[str, list[SignalOutcome]] = {}
        for outcome in outcomes:
            regime = outcome.signal.regime or Regime.UNKNOWN.value
            if regime not in regime_groups:
                regime_groups[regime] = []
            regime_groups[regime].append(outcome)

        # Calculate metrics for each regime
        performance = []
        for regime, group_outcomes in regime_groups.items():
            total = len(group_outcomes)
            if total == 0:
                continue

            profitable = sum(1 for o in group_outcomes if o.is_profitable)
            win_rate = (profitable / total) * 100 if total > 0 else 0.0

            pnl_values = [
                o.final_pnl_percent for o in group_outcomes if o.final_pnl_percent is not None
            ]
            avg_pnl = sum(pnl_values) / len(pnl_values) if pnl_values else 0.0

            confidence_values = [
                o.signal.confidence for o in group_outcomes if o.signal.confidence is not None
            ]
            avg_confidence = (
                sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
            )

            performance.append({
                "regime": regime,
                "regime_display": self._format_regime_display(regime),
                "win_rate": round(win_rate, 1),
                "avg_pnl": round(avg_pnl, 2),
                "total_signals": total,
                "avg_confidence": round(avg_confidence, 1),
                "colors": self.REGIME_COLORS.get(regime, self.REGIME_COLORS[Regime.UNKNOWN.value]),
            })

        # Sort by win rate descending
        performance.sort(key=lambda x: x["win_rate"], reverse=True)
        return performance

    def _calculate_indicator_performance(
        self, outcomes: list[SignalOutcome]
    ) -> list[dict]:
        """
        Calculate signal performance grouped by indicator combination.

        Groups signals by their key indicator states (e.g., RSI oversold + FGI fear)
        and calculates win rate and average P&L for each combination.
        """
        # Group outcomes by indicator combination
        combo_groups: dict[str, list[SignalOutcome]] = {}

        for outcome in outcomes:
            combo_key = self._extract_indicator_combo(outcome.signal)
            if combo_key not in combo_groups:
                combo_groups[combo_key] = []
            combo_groups[combo_key].append(outcome)

        # Calculate metrics for each combination
        performance = []
        for combo_key, group_outcomes in combo_groups.items():
            total = len(group_outcomes)
            if total < 3:  # Skip combinations with too few samples
                continue

            profitable = sum(1 for o in group_outcomes if o.is_profitable)
            win_rate = (profitable / total) * 100 if total > 0 else 0.0

            pnl_values = [
                o.final_pnl_percent for o in group_outcomes if o.final_pnl_percent is not None
            ]
            avg_pnl = sum(pnl_values) / len(pnl_values) if pnl_values else 0.0

            performance.append({
                "combination": combo_key,
                "win_rate": round(win_rate, 1),
                "avg_pnl": round(avg_pnl, 2),
                "total_signals": total,
            })

        # Sort by win rate descending
        performance.sort(key=lambda x: x["win_rate"], reverse=True)
        return performance[:15]  # Return top 15 combinations

    def _extract_indicator_combo(self, signal: Signal) -> str:
        """
        Extract a human-readable indicator combination key from a signal.

        Analyzes the signal's indicators and context to create a descriptive key
        like "RSI oversold + FGI fear" or "MACD bullish + ADX strong".
        """
        parts = []

        # Extract from indicators if available
        if signal.indicators:
            indicators = signal.indicators
            if isinstance(indicators, list):
                for ind in indicators:
                    if isinstance(ind, dict):
                        name = ind.get("name", "").upper()
                        signal_dir = ind.get("signal", "").upper()
                        value = ind.get("value")

                        if name == "RSI" and value is not None:
                            if value < 30:
                                parts.append("RSI oversold")
                            elif value > 70:
                                parts.append("RSI overbought")
                        elif name == "FGI" and value is not None:
                            if value < 25:
                                parts.append("FGI extreme fear")
                            elif value < 45:
                                parts.append("FGI fear")
                            elif value > 75:
                                parts.append("FGI extreme greed")
                            elif value > 55:
                                parts.append("FGI greed")
                        elif name == "MACD":
                            if signal_dir == "BUY":
                                parts.append("MACD bullish")
                            elif signal_dir == "SELL":
                                parts.append("MACD bearish")
                        elif name == "ADX" and value is not None:
                            if value > 25:
                                parts.append("ADX strong trend")
                            elif value < 20:
                                parts.append("ADX weak trend")

        # Add regime if available
        if signal.regime:
            regime_display = self._format_regime_display(signal.regime)
            parts.append(regime_display)

        if not parts:
            return "Unknown combination"

        return " + ".join(parts[:3])  # Limit to 3 parts for readability

    def _calculate_summary_stats(self, outcomes: list[SignalOutcome]) -> dict:
        """Calculate overall summary statistics."""
        total = len(outcomes)
        if total == 0:
            return {
                "total_signals": 0,
                "overall_win_rate": 0.0,
                "overall_avg_pnl": 0.0,
                "profitable_signals": 0,
                "unprofitable_signals": 0,
            }

        profitable = sum(1 for o in outcomes if o.is_profitable)
        unprofitable = sum(1 for o in outcomes if o.is_profitable is False)
        win_rate = (profitable / total) * 100 if total > 0 else 0.0

        pnl_values = [o.final_pnl_percent for o in outcomes if o.final_pnl_percent is not None]
        avg_pnl = sum(pnl_values) / len(pnl_values) if pnl_values else 0.0

        return {
            "total_signals": total,
            "overall_win_rate": round(win_rate, 1),
            "overall_avg_pnl": round(avg_pnl, 2),
            "profitable_signals": profitable,
            "unprofitable_signals": unprofitable,
        }


class MarketIntelligenceView(LoginRequiredMixin, TemplateView):
    """
    Comprehensive market intelligence view aggregating all external data sources.

    Displays market data, on-chain metrics, social sentiment, and investment insights
    independent of Pionex API availability. Provides charts and analysis to guide
    investment decisions.
    """

    template_name = "analysis/market_intelligence.html"

    # Regime color mapping
    REGIME_COLORS = {
        Regime.RISK_ON.value: {
            "bg": "bg-emerald-900/50",
            "text": "text-emerald-400",
            "border": "border-emerald-500/50",
            "dot": "bg-emerald-400",
            "chart": "rgb(16, 185, 129)",
        },
        Regime.RISK_OFF.value: {
            "bg": "bg-red-900/50",
            "text": "text-red-400",
            "border": "border-red-500/50",
            "dot": "bg-red-400",
            "chart": "rgb(239, 68, 68)",
        },
        Regime.RANGE_BOUND.value: {
            "bg": "bg-slate-600",
            "text": "text-slate-300",
            "border": "border-slate-500/50",
            "dot": "bg-slate-400",
            "chart": "rgb(100, 116, 139)",
        },
        Regime.TRENDING_UP.value: {
            "bg": "bg-sky-900/50",
            "text": "text-sky-400",
            "border": "border-sky-500/50",
            "dot": "bg-sky-400",
            "chart": "rgb(14, 165, 233)",
        },
        Regime.TRENDING_DOWN.value: {
            "bg": "bg-amber-900/50",
            "text": "text-amber-400",
            "border": "border-amber-500/50",
            "dot": "bg-amber-400",
            "chart": "rgb(245, 158, 11)",
        },
        Regime.UNKNOWN.value: {
            "bg": "bg-slate-700",
            "text": "text-slate-400",
            "border": "border-slate-600",
            "dot": "bg-slate-500",
            "chart": "rgb(71, 85, 105)",
        },
    }

    def get_context_data(self, **kwargs):
        """Build comprehensive market intelligence context."""
        context = super().get_context_data(**kwargs)

        # Get time range from query params
        days = self._get_days_param()
        context["selected_days"] = days
        context["time_range_options"] = [
            {"value": 7, "label": "Last 7 Days"},
            {"value": 30, "label": "Last 30 Days"},
        ]

        # Get trading pairs for filtering
        context["trading_pairs"] = TradingPair.objects.active()
        selected_symbol = self.request.GET.get("symbol", "")
        context["selected_symbol"] = selected_symbol

        # Get latest market context snapshot
        latest_snapshot = MarketContextSnapshot.objects.order_by("-timestamp").first()
        
        # Get latest sentiment data (Fear & Greed from public API)
        latest_sentiment = MarketSentimentData.objects.order_by("-fetched_at").first()
        
        context["latest_snapshot"] = latest_snapshot
        context["latest_sentiment"] = latest_sentiment
        context["has_data"] = latest_snapshot is not None or latest_sentiment is not None

        if latest_snapshot or latest_sentiment:
            # Current regime info
            regime_value = (latest_snapshot.regime if latest_snapshot else None) or Regime.UNKNOWN.value
            context["regime_colors"] = self.REGIME_COLORS.get(
                regime_value, self.REGIME_COLORS[Regime.UNKNOWN.value]
            )
            context["regime_display"] = self._format_regime_display(regime_value)

            # Market overview metrics (merge snapshot + sentiment)
            context["market_overview"] = self._build_market_overview(latest_snapshot, latest_sentiment)

            # On-chain metrics
            context["onchain_metrics"] = self._build_onchain_metrics(latest_snapshot)

            # Social sentiment metrics
            context["social_metrics"] = self._build_social_metrics(latest_snapshot)

            # Context scores
            context["context_scores"] = self._build_context_scores(latest_snapshot)

        # Get sentiment data (Fear & Greed history)
        context["sentiment_data"] = self._get_sentiment_history(days)

        # Get historical data for charts
        cutoff = datetime.now(tz=UTC) - timedelta(days=days)
        history = list(
            MarketContextSnapshot.objects.filter(timestamp__gte=cutoff)
            .order_by("timestamp")
            .values(
                "timestamp",
                "regime",
                "btc_dominance",
                "fear_greed_index",
                "social_sentiment_score",
                "net_exchange_flow",
                "trend_strength_score",
                "risk_regime_score",
                "sentiment_regime_score",
            )
        )
        context["chart_data"] = self._prepare_chart_data(history)

        # Investment insights based on current conditions
        if latest_snapshot:
            context["investment_insights"] = self._generate_investment_insights(
                latest_snapshot, history
            )

        # Data sources status
        context["data_sources"] = self._build_data_sources_status(latest_snapshot, latest_sentiment)

        # All regime colors for legend
        context["all_regime_colors"] = self.REGIME_COLORS

        return context

    def _get_days_param(self) -> int:
        """Get and validate days parameter."""
        try:
            days = int(self.request.GET.get("days", 7))
            if days not in [7, 30]:
                days = 7
        except (ValueError, TypeError):
            days = 7
        return days

    def _format_regime_display(self, regime: str) -> str:
        """Format regime value for display."""
        return regime.replace("_", " ").title()

    def _build_market_overview(
        self,
        snapshot: MarketContextSnapshot | None,
        sentiment: MarketSentimentData | None = None,
    ) -> dict:
        """Build market overview metrics from snapshot and sentiment data."""
        # Get Fear & Greed from sentiment data (public API) or snapshot
        fgi_value = None
        if sentiment and sentiment.fear_greed_index is not None:
            fgi_value = sentiment.fear_greed_index
        elif snapshot and snapshot.fear_greed_index is not None:
            fgi_value = snapshot.fear_greed_index

        return {
            "btc_dominance": {
                "value": snapshot.btc_dominance if snapshot else None,
                "label": "BTC Dominance",
                "format": "percent",
                "description": "Bitcoin's share of total crypto market cap",
                "trend": self._get_metric_trend("btc_dominance", snapshot.btc_dominance) if snapshot else None,
            },
            "global_market_cap": {
                "value": snapshot.global_market_cap if snapshot else None,
                "label": "Global Market Cap",
                "format": "currency_trillion",
                "description": "Total cryptocurrency market capitalization",
            },
            "total_volume_24h": {
                "value": snapshot.total_volume_24h if snapshot else None,
                "label": "24h Volume",
                "format": "currency_billion",
                "description": "Total trading volume in the last 24 hours",
            },
            "fear_greed_index": {
                "value": fgi_value,
                "label": "Fear & Greed Index",
                "format": "index",
                "description": "Market sentiment indicator (0=Extreme Fear, 100=Extreme Greed)",
                "classification": self._classify_fear_greed(fgi_value),
            },
        }

    def _build_onchain_metrics(self, snapshot: MarketContextSnapshot | None) -> dict:
        """Build on-chain metrics from snapshot."""
        if not snapshot:
            return {}
        return {
            "active_addresses": {
                "value": snapshot.active_addresses,
                "label": "Active Addresses",
                "format": "number",
                "description": "Number of unique addresses active on-chain",
                "insight": self._get_address_insight(snapshot.active_addresses),
            },
            "net_exchange_flow": {
                "value": snapshot.net_exchange_flow,
                "label": "Net Exchange Flow",
                "format": "flow",
                "description": "Net BTC flow to/from exchanges (negative = outflow = bullish)",
                "insight": self._get_exchange_flow_insight(snapshot.net_exchange_flow),
            },
            "whale_tx_count": {
                "value": snapshot.whale_tx_count,
                "label": "Whale Transactions",
                "format": "number",
                "description": "Transactions over $100k in the last 24h",
                "insight": self._get_whale_insight(snapshot.whale_tx_count),
            },
            "defi_tvl": {
                "value": snapshot.defi_tvl,
                "label": "DeFi TVL",
                "format": "currency_billion",
                "description": "Total Value Locked in DeFi protocols",
            },
        }

    def _build_social_metrics(self, snapshot: MarketContextSnapshot | None) -> dict:
        """Build social sentiment metrics from snapshot."""
        if not snapshot:
            return {}
        return {
            "social_sentiment_score": {
                "value": snapshot.social_sentiment_score,
                "label": "Sentiment Score",
                "format": "sentiment",
                "description": "Aggregate social media sentiment (-1 to +1)",
                "classification": self._classify_sentiment(snapshot.social_sentiment_score),
            },
            "social_mention_count": {
                "value": snapshot.social_mention_count,
                "label": "Social Mentions",
                "format": "number",
                "description": "Number of crypto mentions across social platforms",
            },
            "social_buzz_score": {
                "value": snapshot.social_buzz_score,
                "label": "Buzz Score",
                "format": "score",
                "description": "Relative social activity compared to baseline",
            },
        }

    def _build_context_scores(self, snapshot: MarketContextSnapshot | None) -> dict:
        """Build context scores for display."""
        if not snapshot:
            return {}
        return {
            "trend_strength": {
                "value": snapshot.trend_strength_score,
                "percentage": int((snapshot.trend_strength_score or 0) * 100),
                "label": "Trend Strength",
                "description": "Composite score from ADX, Bollinger Bands, MACD, and on-chain adoption",
            },
            "risk_regime": {
                "value": snapshot.risk_regime_score,
                "percentage": int((snapshot.risk_regime_score or 0) * 100),
                "label": "Risk Appetite",
                "description": "Combines Fear & Greed, exchange flows, DeFi TVL, and volatility",
            },
            "sentiment_regime": {
                "value": snapshot.sentiment_regime_score,
                "percentage": int((snapshot.sentiment_regime_score or 0) * 100),
                "label": "Market Sentiment",
                "description": "Aggregates social sentiment, buzz scores, and news sentiment",
            },
        }

    def _get_sentiment_history(self, days: int) -> list[dict]:
        """Get Fear & Greed Index history."""
        cutoff = datetime.now(tz=UTC) - timedelta(days=days)
        return list(
            MarketSentimentData.objects.filter(fetched_at__gte=cutoff)
            .order_by("fetched_at")
            .values("fetched_at", "fear_greed_index", "fear_greed_classification")
        )

    def _prepare_chart_data(self, history: list[dict]) -> str:
        """Prepare historical data for Chart.js."""
        if not history:
            return json.dumps([])

        chart_data = []
        for entry in history:
            chart_data.append({
                "timestamp": entry["timestamp"].isoformat() if entry["timestamp"] else None,
                "regime": entry["regime"] or Regime.UNKNOWN.value,
                "btc_dominance": entry["btc_dominance"],
                "fear_greed": entry["fear_greed_index"],
                "social_sentiment": (
                    (entry["social_sentiment_score"] + 1) * 50
                    if entry["social_sentiment_score"] is not None
                    else None
                ),  # Normalize -1 to 1 -> 0 to 100
                "exchange_flow": entry["net_exchange_flow"],
                "trend_strength": (
                    entry["trend_strength_score"] * 100
                    if entry["trend_strength_score"] is not None
                    else None
                ),
                "risk_regime": (
                    entry["risk_regime_score"] * 100
                    if entry["risk_regime_score"] is not None
                    else None
                ),
                "sentiment_regime": (
                    entry["sentiment_regime_score"] * 100
                    if entry["sentiment_regime_score"] is not None
                    else None
                ),
            })

        return json.dumps(chart_data)

    def _generate_investment_insights(
        self, snapshot: MarketContextSnapshot, history: list[dict]
    ) -> list[dict]:
        """Generate actionable investment insights based on current conditions."""
        insights = []
        regime = snapshot.regime or Regime.UNKNOWN.value

        # Regime-based insights
        if regime == Regime.RISK_ON.value:
            insights.append({
                "type": "bullish",
                "title": "Risk-On Environment",
                "description": "Market conditions favor growth assets. Consider DCA strategies for accumulation.",
                "recommendation": "DCA bots may perform well in this environment.",
                "confidence": "high" if (snapshot.risk_regime_score or 0) > 0.7 else "medium",
            })
        elif regime == Regime.RISK_OFF.value:
            insights.append({
                "type": "bearish",
                "title": "Risk-Off Environment",
                "description": "Market showing signs of fear. Consider reducing exposure or waiting for better entry points.",
                "recommendation": "Avoid aggressive positions. Consider stablecoin allocation.",
                "confidence": "high" if (snapshot.risk_regime_score or 0) < 0.3 else "medium",
            })
        elif regime == Regime.RANGE_BOUND.value:
            insights.append({
                "type": "neutral",
                "title": "Range-Bound Market",
                "description": "Market lacking clear direction. Grid trading strategies may be effective.",
                "recommendation": "Grid bots can capitalize on sideways price action.",
                "confidence": "medium",
            })
        elif regime == Regime.TRENDING_UP.value:
            insights.append({
                "type": "bullish",
                "title": "Uptrend Detected",
                "description": "Strong upward momentum. Trend-following strategies recommended.",
                "recommendation": "Consider trailing stop strategies to ride the trend.",
                "confidence": "high" if (snapshot.trend_strength_score or 0) > 0.6 else "medium",
            })
        elif regime == Regime.TRENDING_DOWN.value:
            insights.append({
                "type": "bearish",
                "title": "Downtrend Detected",
                "description": "Strong downward momentum. Exercise caution with long positions.",
                "recommendation": "Wait for trend reversal signals before entering.",
                "confidence": "high" if (snapshot.trend_strength_score or 0) > 0.6 else "medium",
            })

        # Fear & Greed insights
        fgi = snapshot.fear_greed_index
        if fgi is not None:
            if fgi <= 20:
                insights.append({
                    "type": "opportunity",
                    "title": "Extreme Fear - Potential Opportunity",
                    "description": f"Fear & Greed at {fgi}. Historically, extreme fear often precedes recoveries.",
                    "recommendation": "Consider gradual accumulation if fundamentals are sound.",
                    "confidence": "medium",
                })
            elif fgi >= 80:
                insights.append({
                    "type": "warning",
                    "title": "Extreme Greed - Exercise Caution",
                    "description": f"Fear & Greed at {fgi}. Markets may be overheated.",
                    "recommendation": "Consider taking profits or tightening stop losses.",
                    "confidence": "medium",
                })

        # Exchange flow insights
        flow = snapshot.net_exchange_flow
        if flow is not None:
            if flow < -1000:
                insights.append({
                    "type": "bullish",
                    "title": "Strong Exchange Outflows",
                    "description": "Significant BTC leaving exchanges, suggesting accumulation.",
                    "recommendation": "Reduced selling pressure may support prices.",
                    "confidence": "medium",
                })
            elif flow > 1000:
                insights.append({
                    "type": "warning",
                    "title": "Exchange Inflows Detected",
                    "description": "BTC flowing into exchanges, potentially for selling.",
                    "recommendation": "Monitor for increased selling pressure.",
                    "confidence": "medium",
                })

        # Social sentiment insights
        sentiment = snapshot.social_sentiment_score
        if sentiment is not None:
            if sentiment > 0.5:
                insights.append({
                    "type": "info",
                    "title": "Positive Social Sentiment",
                    "description": "Social media sentiment is strongly positive.",
                    "recommendation": "Positive sentiment can drive short-term momentum.",
                    "confidence": "low",
                })
            elif sentiment < -0.5:
                insights.append({
                    "type": "info",
                    "title": "Negative Social Sentiment",
                    "description": "Social media sentiment is strongly negative.",
                    "recommendation": "Contrarian opportunities may exist if fundamentals are intact.",
                    "confidence": "low",
                })

        return insights

    def _get_metric_trend(self, metric: str, current_value: float | None) -> str | None:
        """Determine if a metric is trending up or down."""
        if current_value is None:
            return None

        # Get previous value from 24h ago
        cutoff = datetime.now(tz=UTC) - timedelta(hours=24)
        prev_snapshot = (
            MarketContextSnapshot.objects.filter(timestamp__lte=cutoff)
            .order_by("-timestamp")
            .first()
        )

        if not prev_snapshot:
            return None

        prev_value = getattr(prev_snapshot, metric, None)
        if prev_value is None:
            return None

        if current_value > prev_value * 1.01:
            return "up"
        elif current_value < prev_value * 0.99:
            return "down"
        return "stable"

    def _classify_fear_greed(self, value: int | None) -> dict | None:
        """Classify Fear & Greed Index value."""
        if value is None:
            return None

        if value <= 20:
            return {"label": "Extreme Fear", "color": "text-red-400", "bg": "bg-red-900/50"}
        elif value <= 40:
            return {"label": "Fear", "color": "text-amber-400", "bg": "bg-amber-900/50"}
        elif value <= 60:
            return {"label": "Neutral", "color": "text-slate-300", "bg": "bg-slate-600"}
        elif value <= 80:
            return {"label": "Greed", "color": "text-emerald-400", "bg": "bg-emerald-900/50"}
        else:
            return {"label": "Extreme Greed", "color": "text-emerald-400", "bg": "bg-emerald-900/50"}

    def _classify_sentiment(self, value: float | None) -> dict | None:
        """Classify social sentiment score."""
        if value is None:
            return None

        if value <= -0.5:
            return {"label": "Very Negative", "color": "text-red-400"}
        elif value <= -0.2:
            return {"label": "Negative", "color": "text-amber-400"}
        elif value <= 0.2:
            return {"label": "Neutral", "color": "text-slate-300"}
        elif value <= 0.5:
            return {"label": "Positive", "color": "text-emerald-400"}
        else:
            return {"label": "Very Positive", "color": "text-emerald-400"}

    def _get_address_insight(self, value: int | None) -> str | None:
        """Generate insight for active addresses."""
        if value is None:
            return None
        if value > 1000000:
            return "High network activity indicates strong adoption"
        elif value > 500000:
            return "Moderate network activity"
        return "Lower network activity"

    def _get_exchange_flow_insight(self, value: float | None) -> str | None:
        """Generate insight for exchange flow."""
        if value is None:
            return None
        if value < -500:
            return "Outflows suggest accumulation (bullish)"
        elif value > 500:
            return "Inflows may indicate selling pressure"
        return "Balanced flow"

    def _get_whale_insight(self, value: int | None) -> str | None:
        """Generate insight for whale transactions."""
        if value is None:
            return None
        if value > 1000:
            return "High whale activity - watch for volatility"
        elif value > 500:
            return "Moderate whale activity"
        return "Low whale activity"

    def _build_data_sources_status(
        self,
        snapshot: MarketContextSnapshot | None,
        sentiment: MarketSentimentData | None,
    ) -> list[dict]:
        """Build data sources status for display."""
        sources = []

        # CoinGecko (free tier)
        coingecko_working = snapshot and snapshot.btc_dominance is not None
        sources.append({
            "name": "CoinGecko",
            "description": "Market data (BTC dominance, market cap, volume)",
            "status": "active" if coingecko_working else "unavailable",
            "requires_key": False,
            "data_available": ["BTC Dominance", "Global Market Cap", "24h Volume"],
        })

        # Blockchain.com (free, no key)
        blockchain_working = snapshot and (
            snapshot.global_market_cap is not None or snapshot.total_volume_24h is not None
        )
        sources.append({
            "name": "Blockchain.com",
            "description": "Bitcoin network statistics (hash rate, transactions)",
            "status": "active" if blockchain_working else "unavailable",
            "requires_key": False,
            "data_available": ["Hash Rate", "Transaction Count", "Network Stats"],
        })

        # Alternative.me Fear & Greed (free, no key)
        fgi_working = sentiment and sentiment.fear_greed_index is not None
        sources.append({
            "name": "Alternative.me",
            "description": "Fear & Greed Index",
            "status": "active" if fgi_working else "unavailable",
            "requires_key": False,
            "data_available": ["Fear & Greed Index"],
        })

        # Glassnode/IntoTheBlock (requires API key)
        onchain_working = snapshot and (
            snapshot.active_addresses is not None
            or snapshot.net_exchange_flow is not None
            or snapshot.whale_tx_count is not None
        )
        sources.append({
            "name": "Glassnode / IntoTheBlock",
            "description": "On-chain metrics (addresses, exchange flow, whale activity)",
            "status": "active" if onchain_working else "requires_key",
            "requires_key": True,
            "env_var": "ONCHAIN_API_KEY",
            "data_available": ["Active Addresses", "Exchange Flow", "Whale Transactions", "DeFi TVL"],
        })

        # LunarCrush/Santiment (requires API key)
        social_working = snapshot and (
            snapshot.social_sentiment_score is not None
            or snapshot.social_mention_count is not None
        )
        sources.append({
            "name": "LunarCrush / Santiment",
            "description": "Social sentiment analysis",
            "status": "active" if social_working else "requires_key",
            "requires_key": True,
            "env_var": "SOCIAL_SENTIMENT_API_KEY",
            "data_available": ["Sentiment Score", "Social Mentions", "Buzz Score"],
        })

        return sources
