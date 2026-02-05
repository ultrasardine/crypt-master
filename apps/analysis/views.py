"""Analysis views."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View
from django.views.generic import TemplateView

from apps.core.models import TradingPair
from apps.trading.models import Signal
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
