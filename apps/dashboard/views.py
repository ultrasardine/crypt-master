"""Dashboard views."""

import json
import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from apps.bots.models import Bot
from apps.core.models import MarketContextSnapshot, MarketSentimentData, PortfolioSnapshot
from apps.trading.models import Signal, SignalAccuracyMetrics, Trade

logger = logging.getLogger(__name__)


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

        # Market context snapshot (regime, BTC dominance, social sentiment, on-chain)
        # Requirements: 4.3.1 - Include latest MarketContextSnapshot in context
        context["market_context"] = self._get_market_context()

        # Signal accuracy metrics
        context["signal_accuracy"] = self._get_signal_accuracy(user)

        # Chart data
        context["portfolio_chart_data"] = json.dumps(self._get_portfolio_chart_data(user))
        context["bot_performance_data"] = json.dumps(self._get_bot_performance_data(user))

        # Last Data Points widget - shows pipeline health at a glance
        context["last_data_points"] = self._get_last_data_points(user)

        # Rate limit usage data for dashboard widget
        # Requirements: 4.6 - Expose current usage metrics via dashboard
        context["rate_limit"] = self._get_rate_limit_data()

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

    def _get_market_context(self) -> dict | None:
        """
        Get latest market context snapshot data for dashboard cards.

        Returns:
            Dictionary with market context data or None if no data available.

        Requirements: 4.3.1 - Include latest MarketContextSnapshot in context
        """
        snapshot = MarketContextSnapshot.objects.order_by("-timestamp").first()
        if not snapshot:
            return None

        # Determine exchange flow direction for on-chain highlights
        exchange_flow_direction = None
        if snapshot.net_exchange_flow is not None:
            if snapshot.net_exchange_flow > 0:
                exchange_flow_direction = "inflow"
            elif snapshot.net_exchange_flow < 0:
                exchange_flow_direction = "outflow"
            else:
                exchange_flow_direction = "neutral"

        # Determine whale activity level
        whale_activity_level = None
        if snapshot.whale_tx_count is not None:
            if snapshot.whale_tx_count >= 100:
                whale_activity_level = "high"
            elif snapshot.whale_tx_count >= 50:
                whale_activity_level = "moderate"
            else:
                whale_activity_level = "low"

        return {
            "regime": snapshot.regime,
            "btc_dominance": snapshot.btc_dominance,
            "social_sentiment_score": snapshot.social_sentiment_score,
            "social_buzz_score": snapshot.social_buzz_score,
            "net_exchange_flow": snapshot.net_exchange_flow,
            "exchange_flow_direction": exchange_flow_direction,
            "whale_tx_count": snapshot.whale_tx_count,
            "whale_activity_level": whale_activity_level,
            "trend_strength_score": snapshot.trend_strength_score,
            "risk_regime_score": snapshot.risk_regime_score,
            "sentiment_regime_score": snapshot.sentiment_regime_score,
            "is_stale": snapshot.is_stale,
            "is_degraded": snapshot.is_degraded,
            "timestamp": snapshot.timestamp,
        }

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

    def _get_last_data_points(self, user) -> dict:
        """
        Get last data points for pipeline health widget.

        Shows at a glance whether the data pipeline is alive:
        - Last MarketContextSnapshot regime and timestamp
        - Last N signals (symbol, direction, confidence)
        - Last portfolio snapshot time

        Args:
            user: The user to get data for.

        Returns:
            Dictionary with last data points for display.
        """
        from django.utils import timezone

        result = {
            "market_context": None,
            "recent_signals": [],
            "portfolio_snapshot": None,
            "market_sentiment": None,
        }

        # Last MarketContextSnapshot
        snapshot = MarketContextSnapshot.objects.order_by("-timestamp").first()
        if snapshot:
            result["market_context"] = {
                "regime": snapshot.regime,
                "timestamp": snapshot.timestamp,
                "is_stale": snapshot.is_stale,
                "minutes_ago": int((timezone.now() - snapshot.timestamp).total_seconds() / 60),
            }

        # Last 5 signals (across all pairs for visibility)
        signals = Signal.objects.select_related("trading_pair").order_by("-created_at")[:5]
        result["recent_signals"] = [
            {
                "symbol": s.trading_pair.symbol if s.trading_pair else "N/A",
                "direction": s.direction,
                "confidence": s.confidence,
                "timestamp": s.created_at,
                "minutes_ago": int((timezone.now() - s.created_at).total_seconds() / 60),
            }
            for s in signals
        ]

        # Last portfolio snapshot for this user
        portfolio = PortfolioSnapshot.objects.filter(user=user).order_by("-created_at").first()
        if portfolio:
            result["portfolio_snapshot"] = {
                "total_value": portfolio.total_value,
                "timestamp": portfolio.created_at,
                "minutes_ago": int((timezone.now() - portfolio.created_at).total_seconds() / 60),
            }

        # Last market sentiment
        sentiment = MarketSentimentData.get_latest()
        if sentiment:
            result["market_sentiment"] = {
                "fear_greed_index": sentiment.fear_greed_index,
                "classification": sentiment.fear_greed_classification,
                "timestamp": sentiment.updated_at,
                "is_stale": sentiment.is_stale,
            }

        return result

    def _get_rate_limit_data(self) -> dict:
        """
        Get rate limit usage data for dashboard widget.

        Returns:
            Dictionary with rate limit metrics:
            - ip_usage: IP weight usage ratio (0-1)
            - account_usage: Account weight usage ratio (0-1)
            - is_banned: Whether currently rate limited
            - ban_remaining: Seconds remaining in ban
            - ip_usage_percent: IP usage as percentage (0-100)
            - account_usage_percent: Account usage as percentage (0-100)
            - status: Overall status (ok, warning, error)

        Requirements:
            - 4.6: Expose current usage metrics via dashboard
            - 4.5: Show warning when approaching limits, error when rate limited
        """
        import os

        from lib.pionex.client import PionexClient

        result = {
            "ip_usage": 0.0,
            "account_usage": 0.0,
            "is_banned": False,
            "ban_remaining": 0.0,
            "ip_usage_percent": 0,
            "account_usage_percent": 0,
            "status": "ok",
            "status_message": "API rate limits healthy",
        }

        try:
            # Get the Pionex client to access rate limiter
            # Note: In production, this would use a shared rate limiter instance
            api_key = os.environ.get("PIONEX_API_KEY", "")
            api_secret = os.environ.get("PIONEX_API_SECRET", "")

            if not api_key or not api_secret:
                result["status"] = "unknown"
                result["status_message"] = "API credentials not configured"
                return result

            # Create a client instance to access the rate limiter
            # In a real implementation, we'd use a singleton or shared instance
            client = PionexClient(api_key=api_key, api_secret=api_secret)
            rate_limiter = client.rate_limiter

            # Get usage metrics
            result["ip_usage"] = rate_limiter.ip_usage
            result["account_usage"] = rate_limiter.account_usage
            result["is_banned"] = rate_limiter.is_banned
            result["ban_remaining"] = rate_limiter.ban_remaining

            # Calculate percentages
            result["ip_usage_percent"] = int(rate_limiter.ip_usage * 100)
            result["account_usage_percent"] = int(rate_limiter.account_usage * 100)

            # Determine status
            if rate_limiter.is_banned:
                result["status"] = "error"
                result["status_message"] = f"Rate limited - {int(rate_limiter.ban_remaining)}s remaining"
            elif rate_limiter.ip_usage >= 0.8 or rate_limiter.account_usage >= 0.8:
                result["status"] = "warning"
                result["status_message"] = "Approaching rate limits"
            else:
                result["status"] = "ok"
                result["status_message"] = "API rate limits healthy"

        except Exception as e:
            logger.warning(f"Failed to get rate limit data: {e}")
            result["status"] = "unknown"
            result["status_message"] = "Unable to fetch rate limit data"

        return result
