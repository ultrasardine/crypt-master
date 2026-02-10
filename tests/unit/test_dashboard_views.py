"""Unit tests for dashboard views."""

import pytest
from decimal import Decimal
from django.contrib.auth.models import User
from django.test import RequestFactory
from django.utils import timezone

from apps.bots.models import Bot
from apps.core.models import MarketContextSnapshot, MarketSentimentData, PortfolioSnapshot, TradingPair
from apps.dashboard.views import DashboardHomeView
from apps.trading.models import SignalAccuracyMetrics


@pytest.mark.django_db
class TestDashboardHomeView:
    """Test DashboardHomeView context data methods."""

    @pytest.fixture
    def user(self):
        """Create a test user."""
        return User.objects.create_user(username="testuser", password="testpass")

    @pytest.fixture
    def trading_pair(self):
        """Create a test trading pair."""
        return TradingPair.objects.create(
            symbol="BTC_USDT",
            base_currency="BTC",
            quote_currency="USDT",
            is_active=True,
        )

    @pytest.fixture
    def view(self):
        """Create a view instance."""
        factory = RequestFactory()
        request = factory.get("/dashboard/")
        view = DashboardHomeView()
        view.request = request
        return view

    def test_get_market_sentiment_returns_latest(self, view):
        """Test _get_market_sentiment returns latest data."""
        # Create market sentiment data
        sentiment = MarketSentimentData.objects.create(
            fear_greed_index=50,
            fear_greed_classification="Neutral",
        )

        result = view._get_market_sentiment()

        assert result is not None
        assert result.fear_greed_index == 50
        assert result.fear_greed_classification == "Neutral"

    def test_get_market_sentiment_returns_none_when_no_data(self, view):
        """Test _get_market_sentiment returns None when no data exists."""
        result = view._get_market_sentiment()
        assert result is None

    def test_get_signal_accuracy_returns_metrics(self, view, user):
        """Test _get_signal_accuracy returns user metrics."""
        # Create accuracy metrics
        metrics = SignalAccuracyMetrics.objects.create(
            user=user,
            period_days=30,
            total_executed_signals=100,
            profitable_signals=60,
            unprofitable_signals=40,
            overall_accuracy=60.0,
            buy_accuracy=65.0,
            sell_accuracy=55.0,
            confidence_correlation=0.75,
            average_pnl_percent=2.5,
        )

        result = view._get_signal_accuracy(user)

        assert result["overall_accuracy"] == 60.0
        assert result["buy_accuracy"] == 65.0
        assert result["sell_accuracy"] == 55.0
        assert result["confidence_correlation"] == 0.75
        assert result["total_executed_signals"] == 100

    def test_get_signal_accuracy_returns_empty_dict_when_no_data(self, view, user):
        """Test _get_signal_accuracy returns empty dict when no data exists."""
        result = view._get_signal_accuracy(user)
        assert result == {}

    def test_get_portfolio_chart_data_returns_snapshots(self, view, user):
        """Test _get_portfolio_chart_data returns snapshot history."""
        # Create portfolio snapshots
        snapshot1 = PortfolioSnapshot.objects.create(
            user=user,
            total_value=Decimal("10000.00"),
            available_balance=Decimal("5000.00"),
            allocated_to_bots=Decimal("5000.00"),
            drawdown=0.0,
            high_water_mark=Decimal("10000.00"),
            is_simulated=False,
        )
        snapshot2 = PortfolioSnapshot.objects.create(
            user=user,
            total_value=Decimal("11000.00"),
            available_balance=Decimal("5500.00"),
            allocated_to_bots=Decimal("5500.00"),
            drawdown=0.0,
            high_water_mark=Decimal("11000.00"),
            is_simulated=False,
        )

        result = view._get_portfolio_chart_data(user)

        assert len(result) == 2
        assert result[0]["total_value"] == 11000.0  # Most recent first
        assert result[1]["total_value"] == 10000.0
        assert "timestamp" in result[0]
        assert "drawdown" in result[0]

    def test_get_portfolio_chart_data_returns_empty_list_when_no_data(self, view, user):
        """Test _get_portfolio_chart_data returns empty list when no data exists."""
        result = view._get_portfolio_chart_data(user)
        assert result == []

    def test_get_bot_performance_data_returns_bots(self, view, user, trading_pair):
        """Test _get_bot_performance_data returns bot performance."""
        # Create bots
        bot1 = Bot.objects.create(
            user=user,
            trading_pair=trading_pair,
            pionex_bot_id="bot1",
            bot_type="GRID",
            status="ACTIVE",
            invested_amount=Decimal("1000.00"),
            current_value=Decimal("1100.00"),
            current_pnl=Decimal("100.00"),
            pnl_percent=10.0,
        )
        bot2 = Bot.objects.create(
            user=user,
            trading_pair=trading_pair,
            pionex_bot_id="bot2",
            bot_type="DCA",
            status="STOPPED",
            invested_amount=Decimal("2000.00"),
            current_value=Decimal("1900.00"),
            current_pnl=Decimal("-100.00"),
            pnl_percent=-5.0,
            stopped_at=timezone.now(),
        )

        result = view._get_bot_performance_data(user)

        assert len(result) == 2
        assert result[0]["bot_type"] == "DCA"  # Most recent first
        assert result[0]["current_pnl"] == -100.0
        assert result[1]["bot_type"] == "GRID"
        assert result[1]["current_pnl"] == 100.0

    def test_get_bot_performance_data_returns_empty_list_when_no_data(self, view, user):
        """Test _get_bot_performance_data returns empty list when no data exists."""
        result = view._get_bot_performance_data(user)
        assert result == []

    def test_get_context_data_includes_all_new_fields(self, user, trading_pair):
        """Test get_context_data includes market sentiment, accuracy, and chart data."""
        import json
        
        # Create test data
        MarketSentimentData.objects.create(
            fear_greed_index=50,
            fear_greed_classification="Neutral",
        )
        SignalAccuracyMetrics.objects.create(
            user=user,
            overall_accuracy=60.0,
        )
        PortfolioSnapshot.objects.create(
            user=user,
            total_value=Decimal("10000.00"),
            available_balance=Decimal("5000.00"),
            allocated_to_bots=Decimal("5000.00"),
            drawdown=0.0,
            high_water_mark=Decimal("10000.00"),
            is_simulated=False,
        )
        Bot.objects.create(
            user=user,
            trading_pair=trading_pair,
            pionex_bot_id="test_bot",
            bot_type="GRID",
            status="ACTIVE",
            invested_amount=Decimal("1000.00"),
        )

        # Create view and request
        factory = RequestFactory()
        request = factory.get("/dashboard/")
        request.user = user

        view = DashboardHomeView()
        view.request = request
        view.setup(request)

        context = view.get_context_data()

        # Verify new context keys exist
        assert "market_sentiment" in context
        assert "signal_accuracy" in context
        assert "portfolio_chart_data" in context
        assert "bot_performance_data" in context

        # Verify data is correct
        assert context["market_sentiment"].fear_greed_index == 50
        assert context["signal_accuracy"]["overall_accuracy"] == 60.0
        
        # Chart data is JSON-encoded for the template
        portfolio_data = json.loads(context["portfolio_chart_data"])
        bot_data = json.loads(context["bot_performance_data"])
        
        assert len(portfolio_data) == 1
        assert len(bot_data) == 1


    def test_get_market_context_returns_latest_snapshot(self, view):
        """Test _get_market_context returns latest MarketContextSnapshot data.
        
        Requirements: 4.3.1 - Include latest MarketContextSnapshot in context
        """
        # Create market context snapshot
        snapshot = MarketContextSnapshot.objects.create(
            symbol=None,
            timestamp=timezone.now(),
            regime="RISK_ON",
            btc_dominance=45.5,
            social_sentiment_score=0.35,
            social_buzz_score=0.7,
            net_exchange_flow=-1000.0,
            whale_tx_count=75,
            trend_strength_score=0.65,
            risk_regime_score=0.7,
            sentiment_regime_score=0.6,
            is_stale=False,
            is_degraded=False,
        )

        result = view._get_market_context()

        assert result is not None
        assert result["regime"] == "RISK_ON"
        assert result["btc_dominance"] == 45.5
        assert result["social_sentiment_score"] == 0.35
        assert result["net_exchange_flow"] == -1000.0
        assert result["whale_tx_count"] == 75
        assert result["exchange_flow_direction"] == "outflow"
        assert result["whale_activity_level"] == "moderate"
        assert result["is_stale"] is False

    def test_get_market_context_returns_none_when_no_data(self, view):
        """Test _get_market_context returns None when no snapshot exists."""
        # Clean up any existing snapshots from other tests
        MarketContextSnapshot.objects.all().delete()
        result = view._get_market_context()
        assert result is None

    def test_get_market_context_exchange_flow_inflow(self, view):
        """Test _get_market_context correctly identifies inflow direction."""
        MarketContextSnapshot.objects.create(
            symbol=None,
            timestamp=timezone.now(),
            net_exchange_flow=5000.0,  # Positive = inflow
            is_stale=False,
        )

        result = view._get_market_context()

        assert result["exchange_flow_direction"] == "inflow"

    def test_get_market_context_exchange_flow_neutral(self, view):
        """Test _get_market_context correctly identifies neutral flow."""
        MarketContextSnapshot.objects.create(
            symbol=None,
            timestamp=timezone.now(),
            net_exchange_flow=0.0,  # Zero = neutral
            is_stale=False,
        )

        result = view._get_market_context()

        assert result["exchange_flow_direction"] == "neutral"

    def test_get_market_context_whale_activity_high(self, view):
        """Test _get_market_context correctly identifies high whale activity."""
        MarketContextSnapshot.objects.create(
            symbol=None,
            timestamp=timezone.now(),
            whale_tx_count=150,  # >= 100 = high
            is_stale=False,
        )

        result = view._get_market_context()

        assert result["whale_activity_level"] == "high"

    def test_get_market_context_whale_activity_low(self, view):
        """Test _get_market_context correctly identifies low whale activity."""
        MarketContextSnapshot.objects.create(
            symbol=None,
            timestamp=timezone.now(),
            whale_tx_count=25,  # < 50 = low
            is_stale=False,
        )

        result = view._get_market_context()

        assert result["whale_activity_level"] == "low"

    def test_get_market_context_stale_indicator(self, view):
        """Test _get_market_context includes stale indicator.
        
        Requirements: 4.3.4 - Display stale indicator if snapshot is marked is_stale=True
        """
        MarketContextSnapshot.objects.create(
            symbol=None,
            timestamp=timezone.now(),
            regime="UNKNOWN",
            is_stale=True,
            is_degraded=True,
        )

        result = view._get_market_context()

        assert result["is_stale"] is True
        assert result["is_degraded"] is True

    def test_get_context_data_includes_market_context(self, user, trading_pair):
        """Test get_context_data includes market_context key.
        
        Requirements: 4.3.1 - Include latest MarketContextSnapshot in context
        """
        # Create market context snapshot
        MarketContextSnapshot.objects.create(
            symbol=None,
            timestamp=timezone.now(),
            regime="TRENDING_UP",
            btc_dominance=48.0,
            social_sentiment_score=0.5,
            net_exchange_flow=-500.0,
            whale_tx_count=80,
            is_stale=False,
        )

        # Create required portfolio snapshot for the view
        PortfolioSnapshot.objects.create(
            user=user,
            total_value=Decimal("10000.00"),
            available_balance=Decimal("5000.00"),
            allocated_to_bots=Decimal("5000.00"),
            drawdown=0.0,
            high_water_mark=Decimal("10000.00"),
            is_simulated=False,
        )

        # Create view and request
        factory = RequestFactory()
        request = factory.get("/dashboard/")
        request.user = user

        view = DashboardHomeView()
        view.request = request
        view.setup(request)

        context = view.get_context_data()

        # Verify market_context is in context
        assert "market_context" in context
        assert context["market_context"] is not None
        assert context["market_context"]["regime"] == "TRENDING_UP"
        assert context["market_context"]["btc_dominance"] == 48.0
        assert context["market_context"]["exchange_flow_direction"] == "outflow"
        assert context["market_context"]["whale_activity_level"] == "moderate"
