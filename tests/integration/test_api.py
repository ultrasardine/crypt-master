"""Integration tests for REST API endpoints."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.bots.models import Bot, BotEvent, BotStatus, BotType
from apps.core.models import PortfolioSnapshot, SystemConfig, TradingPair
from apps.trading.models import Signal, SignalDirection, Trade, TradeSide

User = get_user_model()


@pytest.fixture
def api_client():
    """Create an API client for testing."""
    return APIClient()


@pytest.fixture
def test_user(db):
    """Create a test user for authentication."""
    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )


@pytest.fixture
def other_user(db):
    """Create another test user for cross-user access tests."""
    return User.objects.create_user(
        username="otheruser",
        email="other@example.com",
        password="otherpass123",
    )


@pytest.fixture
def authenticated_client(api_client, test_user):
    """Create an authenticated API client."""
    api_client.force_authenticate(user=test_user)
    return api_client


@pytest.fixture
def trading_pair(db):
    """Create a test trading pair."""
    return TradingPair.objects.create(
        symbol="BTC_USDT",
        base_currency="BTC",
        quote_currency="USDT",
        is_active=True,
        min_quantity=Decimal("0.0001"),
        max_quantity=Decimal("100"),
        price_precision=2,
        quantity_precision=6,
    )


@pytest.fixture
def trading_pair_eth(db):
    """Create a second test trading pair."""
    return TradingPair.objects.create(
        symbol="ETH_USDT",
        base_currency="ETH",
        quote_currency="USDT",
        is_active=True,
    )


@pytest.fixture
def portfolio_snapshot(db, test_user):
    """Create a test portfolio snapshot owned by test_user."""
    return PortfolioSnapshot.objects.create(
        user=test_user,
        total_value=Decimal("10000.00"),
        available_balance=Decimal("5000.00"),
        allocated_to_bots=Decimal("5000.00"),
        drawdown=0.05,
        high_water_mark=Decimal("10500.00"),
        is_simulated=False,
    )


@pytest.fixture
def simulated_portfolio_snapshot(db, test_user):
    """Create a simulated portfolio snapshot owned by test_user."""
    return PortfolioSnapshot.objects.create(
        user=test_user,
        total_value=Decimal("50000.00"),
        available_balance=Decimal("25000.00"),
        allocated_to_bots=Decimal("25000.00"),
        drawdown=0.02,
        high_water_mark=Decimal("51000.00"),
        is_simulated=True,
    )


@pytest.fixture
def signal(db, trading_pair):
    """Create a test signal."""
    return Signal.objects.create(
        trading_pair=trading_pair,
        direction=SignalDirection.BUY,
        confidence=87.5,
        indicators={
            "rsi": {"value": 35, "signal": "BUY"},
            "macd": {"value": 0.5, "signal": "BUY"},
        },
        reasoning="RSI oversold, MACD bullish crossover",
        executed=False,
    )


@pytest.fixture
def executed_signal(db, trading_pair):
    """Create an executed signal."""
    from django.utils import timezone

    return Signal.objects.create(
        trading_pair=trading_pair,
        direction=SignalDirection.SELL,
        confidence=92.0,
        indicators={"rsi": {"value": 75, "signal": "SELL"}},
        reasoning="RSI overbought",
        executed=True,
        executed_at=timezone.now(),
    )


@pytest.fixture
def bot(db, trading_pair, test_user):
    """Create a test bot owned by test_user."""
    return Bot.objects.create(
        user=test_user,
        pionex_bot_id="bot_test123",
        bot_type=BotType.GRID,
        trading_pair=trading_pair,
        status=BotStatus.ACTIVE,
        invested_amount=Decimal("1000.00"),
        current_value=Decimal("1050.00"),
        current_pnl=Decimal("50.00"),
        pnl_percent=5.0,
        params={"lower_price": 40000, "upper_price": 50000, "grid_count": 10},
        is_simulated=False,
    )


@pytest.fixture
def simulated_bot(db, trading_pair, test_user):
    """Create a simulated bot owned by test_user."""
    return Bot.objects.create(
        user=test_user,
        pionex_bot_id="sim_test456",
        bot_type=BotType.DCA,
        trading_pair=trading_pair,
        status=BotStatus.ACTIVE,
        invested_amount=Decimal("500.00"),
        current_value=Decimal("480.00"),
        current_pnl=Decimal("-20.00"),
        pnl_percent=-4.0,
        params={"investment_per_order": 100, "interval_hours": 24},
        is_simulated=True,
    )


@pytest.fixture
def other_user_bot(db, trading_pair, other_user):
    """Create a bot owned by another user for cross-user access tests."""
    return Bot.objects.create(
        user=other_user,
        pionex_bot_id="bot_other789",
        bot_type=BotType.GRID,
        trading_pair=trading_pair,
        status=BotStatus.ACTIVE,
        invested_amount=Decimal("2000.00"),
        current_value=Decimal("2100.00"),
        current_pnl=Decimal("100.00"),
        pnl_percent=5.0,
        params={"lower_price": 40000, "upper_price": 50000, "grid_count": 10},
        is_simulated=False,
    )


@pytest.fixture
def trade(db, trading_pair, signal, test_user):
    """Create a test trade owned by test_user."""
    return Trade.objects.create(
        user=test_user,
        signal=signal,
        trading_pair=trading_pair,
        side=TradeSide.BUY,
        entry_price=Decimal("45000.00"),
        quantity=Decimal("0.1"),
        is_simulated=False,
        order_id="order_123",
    )


@pytest.fixture
def closed_trade(db, trading_pair, test_user):
    """Create a closed trade with P&L owned by test_user."""
    from django.utils import timezone

    return Trade.objects.create(
        user=test_user,
        trading_pair=trading_pair,
        side=TradeSide.SELL,
        entry_price=Decimal("45000.00"),
        exit_price=Decimal("47000.00"),
        quantity=Decimal("0.1"),
        pnl=Decimal("200.00"),
        pnl_percent=4.44,
        is_simulated=False,
        order_id="order_456",
        closed_at=timezone.now(),
    )


@pytest.fixture
def other_user_trade(db, trading_pair, other_user):
    """Create a trade owned by another user for cross-user access tests."""
    return Trade.objects.create(
        user=other_user,
        trading_pair=trading_pair,
        side=TradeSide.BUY,
        entry_price=Decimal("46000.00"),
        quantity=Decimal("0.2"),
        is_simulated=False,
        order_id="order_other_789",
    )


@pytest.fixture
def system_config(db):
    """Create test system configuration."""
    return SystemConfig.objects.create(
        key="min_confidence",
        value=85.0,
        description="Minimum confidence threshold for trading",
    )


class TestPortfolioAPI:
    """Tests for portfolio endpoints.

    Portfolio endpoints now enforce user isolation, so tests use authenticated client.
    """

    def test_get_portfolio_success(self, authenticated_client, portfolio_snapshot):
        """Test getting current portfolio snapshot."""
        url = reverse("api:portfolio")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert Decimal(response.data["total_value"]) == Decimal("10000.00")
        assert response.data["is_simulated"] is False

    def test_get_portfolio_simulated(self, authenticated_client, simulated_portfolio_snapshot):
        """Test getting simulated portfolio snapshot."""
        url = reverse("api:portfolio")
        response = authenticated_client.get(url, {"simulated": "true"})

        assert response.status_code == status.HTTP_200_OK
        assert Decimal(response.data["total_value"]) == Decimal("50000.00")
        assert response.data["is_simulated"] is True

    def test_get_portfolio_not_found(self, authenticated_client, db):
        """Test getting portfolio when none exists for user."""
        url = reverse("api:portfolio")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_portfolio_history(self, authenticated_client, portfolio_snapshot):
        """Test getting portfolio history."""
        url = reverse("api:portfolio_history")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1


class TestTradingPairAPI:
    """Tests for trading pair endpoints."""

    def test_list_trading_pairs(self, api_client, trading_pair, trading_pair_eth):
        """Test listing trading pairs."""
        url = reverse("api:trading_pair_list")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 2

    def test_filter_by_quote_currency(self, api_client, trading_pair, trading_pair_eth):
        """Test filtering trading pairs by quote currency."""
        url = reverse("api:trading_pair_list")
        response = api_client.get(url, {"quote": "USDT"})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 2

    def test_filter_by_base_currency(self, api_client, trading_pair, trading_pair_eth):
        """Test filtering trading pairs by base currency."""
        url = reverse("api:trading_pair_list")
        response = api_client.get(url, {"base": "BTC"})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["symbol"] == "BTC_USDT"


class TestSignalAPI:
    """Tests for signal endpoints."""

    def test_list_signals(self, api_client, signal, executed_signal):
        """Test listing signals."""
        url = reverse("api:signal_list")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 2

    def test_filter_signals_by_direction(self, api_client, signal, executed_signal):
        """Test filtering signals by direction."""
        url = reverse("api:signal_list")
        response = api_client.get(url, {"direction": "BUY"})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["direction"] == "BUY"

    def test_filter_signals_by_confidence(self, api_client, signal, executed_signal):
        """Test filtering signals by minimum confidence."""
        url = reverse("api:signal_list")
        response = api_client.get(url, {"min_confidence": "90"})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["confidence"] >= 90

    def test_filter_signals_by_executed(self, api_client, signal, executed_signal):
        """Test filtering signals by executed status."""
        url = reverse("api:signal_list")
        response = api_client.get(url, {"executed": "true"})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["executed"] is True

    def test_get_signal_detail(self, api_client, signal):
        """Test getting signal details."""
        url = reverse("api:signal_detail", kwargs={"pk": signal.pk})
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["direction"] == "BUY"
        assert response.data["confidence"] == 87.5
        assert "indicators" in response.data

    def test_get_signal_not_found(self, api_client, db):
        """Test getting non-existent signal."""
        url = reverse("api:signal_detail", kwargs={"pk": 99999})
        response = api_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestBotAPI:
    """Tests for bot endpoints.

    Bot endpoints require authentication and enforce user isolation.
    Users can only see and manage their own bots.
    """

    def test_list_bots(self, authenticated_client, bot, simulated_bot):
        """Test listing bots returns only user's bots."""
        url = reverse("api:bot_list")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 2

    def test_list_bots_excludes_other_users(self, authenticated_client, bot, other_user_bot):
        """Test listing bots excludes other users' bots."""
        url = reverse("api:bot_list")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["pionex_bot_id"] == "bot_test123"

    def test_list_bots_unauthenticated_returns_empty(self, api_client, bot):
        """Test listing bots without authentication returns empty."""
        url = reverse("api:bot_list")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 0

    def test_filter_bots_by_status(self, authenticated_client, bot):
        """Test filtering bots by status."""
        url = reverse("api:bot_list")
        response = authenticated_client.get(url, {"status": "ACTIVE"})

        assert response.status_code == status.HTTP_200_OK
        assert all(b["status"] == "ACTIVE" for b in response.data["results"])

    def test_filter_bots_by_type(self, authenticated_client, bot, simulated_bot):
        """Test filtering bots by type."""
        url = reverse("api:bot_list")
        response = authenticated_client.get(url, {"type": "GRID"})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["bot_type"] == "GRID"

    def test_filter_bots_by_simulated(self, authenticated_client, bot, simulated_bot):
        """Test filtering bots by simulated status."""
        url = reverse("api:bot_list")
        response = authenticated_client.get(url, {"simulated": "true"})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["is_simulated"] is True

    def test_create_bot(self, authenticated_client, trading_pair, test_user):
        """Test creating a new bot associates it with the authenticated user."""
        url = reverse("api:bot_list")
        data = {
            "bot_type": "GRID",
            "trading_pair_id": trading_pair.pk,
            "invested_amount": "1000.00",
            "params": {"lower_price": 40000, "upper_price": 50000, "grid_count": 10},
            "is_simulated": True,
        }
        response = authenticated_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert Bot.objects.count() == 1

        bot = Bot.objects.first()
        assert bot.status == BotStatus.ACTIVE
        assert bot.is_simulated is True
        assert bot.user == test_user  # Verify user association
        assert BotEvent.objects.filter(bot=bot, event_type="CREATED").exists()

    def test_create_bot_invalid_type(self, authenticated_client, trading_pair):
        """Test creating bot with invalid type."""
        url = reverse("api:bot_list")
        data = {
            "bot_type": "INVALID",
            "trading_pair_id": trading_pair.pk,
            "invested_amount": "1000.00",
        }
        response = authenticated_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_bot_negative_amount(self, authenticated_client, trading_pair):
        """Test creating bot with negative invested amount."""
        url = reverse("api:bot_list")
        data = {
            "bot_type": "GRID",
            "trading_pair_id": trading_pair.pk,
            "invested_amount": "-100.00",
        }
        response = authenticated_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_get_bot_detail(self, authenticated_client, bot):
        """Test getting bot details for owned bot."""
        url = reverse("api:bot_detail", kwargs={"pk": bot.pk})
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["pionex_bot_id"] == "bot_test123"
        assert response.data["bot_type"] == "GRID"

    def test_get_bot_detail_other_user_returns_404(self, authenticated_client, other_user_bot):
        """Test getting another user's bot returns 404."""
        url = reverse("api:bot_detail", kwargs={"pk": other_user_bot.pk})
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_stop_bot(self, authenticated_client, bot):
        """Test stopping an owned bot."""
        url = reverse("api:bot_detail", kwargs={"pk": bot.pk})
        response = authenticated_client.delete(url, {"reason": "Test stop"}, format="json")

        assert response.status_code == status.HTTP_200_OK

        bot.refresh_from_db()
        assert bot.status == BotStatus.STOPPED
        assert bot.stop_reason == "Test stop"
        assert BotEvent.objects.filter(bot=bot, event_type="STOPPED").exists()

    def test_stop_bot_other_user_returns_404(self, authenticated_client, other_user_bot):
        """Test stopping another user's bot returns 404."""
        url = reverse("api:bot_detail", kwargs={"pk": other_user_bot.pk})
        response = authenticated_client.delete(url, {"reason": "Test stop"}, format="json")

        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify bot was not stopped
        other_user_bot.refresh_from_db()
        assert other_user_bot.status == BotStatus.ACTIVE

    def test_stop_already_stopped_bot(self, authenticated_client, bot):
        """Test stopping an already stopped bot."""
        bot.status = BotStatus.STOPPED
        bot.save()

        url = reverse("api:bot_detail", kwargs={"pk": bot.pk})
        response = authenticated_client.delete(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestTradeAPI:
    """Tests for trade endpoints.

    Trade endpoints require authentication and enforce user isolation.
    Users can only see and manage their own trades.

    Requirements:
    - 4.2: Filter results to only include trades owned by the authenticated user
    - 4.4: Return 404 for cross-user access attempts
    - 4.5: Only include trades belonging to the requesting user in statistics
    """

    def test_list_trades(self, authenticated_client, trade, closed_trade):
        """Test listing trades returns only user's trades."""
        url = reverse("api:trade_list")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 2

    def test_list_trades_excludes_other_users(self, authenticated_client, trade, other_user_trade):
        """Test listing trades excludes other users' trades."""
        url = reverse("api:trade_list")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["order_id"] == "order_123"

    def test_list_trades_unauthenticated_returns_empty(self, api_client, trade):
        """Test listing trades without authentication returns empty."""
        url = reverse("api:trade_list")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 0

    def test_filter_trades_by_side(self, authenticated_client, trade, closed_trade):
        """Test filtering trades by side."""
        url = reverse("api:trade_list")
        response = authenticated_client.get(url, {"side": "BUY"})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["side"] == "BUY"

    def test_filter_trades_by_status(self, authenticated_client, trade, closed_trade):
        """Test filtering trades by open/closed status."""
        url = reverse("api:trade_list")
        response = authenticated_client.get(url, {"status": "closed"})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["exit_price"] is not None

    def test_get_trade_detail(self, authenticated_client, trade):
        """Test getting trade details for owned trade."""
        url = reverse("api:trade_detail", kwargs={"pk": trade.pk})
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["side"] == "BUY"
        assert Decimal(response.data["entry_price"]) == Decimal("45000.00")

    def test_get_trade_detail_other_user_returns_404(self, authenticated_client, other_user_trade):
        """Test getting another user's trade returns 404."""
        url = reverse("api:trade_detail", kwargs={"pk": other_user_trade.pk})
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_trade_statistics(self, authenticated_client, trade, closed_trade):
        """Test getting trade statistics for authenticated user."""
        url = reverse("api:trade_statistics")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["total_trades"] == 2
        assert response.data["closed_trades"] == 1
        assert response.data["open_positions"] == 1

    def test_get_trade_statistics_excludes_other_users(
        self, authenticated_client, trade, other_user_trade
    ):
        """Test trade statistics excludes other users' trades."""
        url = reverse("api:trade_statistics")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["total_trades"] == 1  # Only user's trade

    def test_get_trade_statistics_unauthenticated_returns_empty(self, api_client, trade):
        """Test trade statistics without authentication returns empty stats."""
        url = reverse("api:trade_statistics")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["total_trades"] == 0


class TestAnalysisAPI:
    """Tests for analysis endpoint."""

    def test_get_analysis_success(self, api_client, signal):
        """Test getting analysis for a symbol."""
        url = reverse("api:analysis", kwargs={"symbol": "BTC_USDT"})
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["direction"] == "BUY"

    def test_get_analysis_case_insensitive(self, api_client, signal):
        """Test analysis endpoint is case insensitive."""
        url = reverse("api:analysis", kwargs={"symbol": "btc_usdt"})
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK

    def test_get_analysis_not_found(self, api_client, trading_pair):
        """Test getting analysis for symbol with no signals."""
        url = reverse("api:analysis", kwargs={"symbol": "ETH_USDT"})
        response = api_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestConfigAPI:
    """Tests for configuration endpoints."""

    def test_get_all_config(self, api_client, system_config):
        """Test getting all configuration."""
        url = reverse("api:config")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["key"] == "min_confidence"

    def test_get_config_by_key(self, api_client, system_config):
        """Test getting specific configuration by key."""
        url = reverse("api:config")
        response = api_client.get(url, {"key": "min_confidence"})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["key"] == "min_confidence"
        assert response.data["value"] == 85.0

    def test_get_config_not_found(self, api_client, db):
        """Test getting non-existent configuration."""
        url = reverse("api:config")
        response = api_client.get(url, {"key": "nonexistent"})

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_config(self, api_client, system_config):
        """Test updating configuration."""
        url = reverse("api:config")
        data = {
            "key": "min_confidence",
            "value": 90.0,
            "description": "Updated threshold",
        }
        response = api_client.put(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["value"] == 90.0

        system_config.refresh_from_db()
        assert system_config.value == 90.0

    def test_create_new_config(self, api_client, db):
        """Test creating new configuration."""
        url = reverse("api:config")
        data = {
            "key": "max_drawdown",
            "value": 0.20,
            "description": "Maximum drawdown limit",
        }
        response = api_client.put(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert SystemConfig.objects.filter(key="max_drawdown").exists()

    def test_update_config_invalid(self, api_client, db):
        """Test updating configuration with invalid data."""
        url = reverse("api:config")
        data = {"value": 90.0}  # Missing key
        response = api_client.put(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_delete_config(self, api_client, system_config):
        """Test deleting configuration."""
        url = reverse("api:config")
        response = api_client.delete(url, QUERY_STRING="key=min_confidence")

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not SystemConfig.objects.filter(key="min_confidence").exists()

    def test_delete_config_not_found(self, api_client, db):
        """Test deleting non-existent configuration."""
        url = reverse("api:config")
        response = api_client.delete(url, QUERY_STRING="key=nonexistent")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_config_missing_key(self, api_client, db):
        """Test deleting configuration without key."""
        url = reverse("api:config")
        response = api_client.delete(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestBacktestAPI:
    """Tests for backtest endpoint."""

    def test_run_backtest(self, api_client, trading_pair):
        """Test running a backtest."""
        url = reverse("api:backtest")
        data = {
            "symbol": "BTC_USDT",
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-06-01T00:00:00Z",
            "initial_balance": "10000.00",
            "strategy_params": {"rsi_period": 14},
        }
        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["symbol"] == "BTC_USDT"
        assert "message" in response.data  # Placeholder message

    def test_run_backtest_invalid_dates(self, api_client, trading_pair):
        """Test backtest with invalid date range."""
        url = reverse("api:backtest")
        data = {
            "symbol": "BTC_USDT",
            "start_date": "2024-06-01T00:00:00Z",
            "end_date": "2024-01-01T00:00:00Z",  # End before start
            "initial_balance": "10000.00",
        }
        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_run_backtest_invalid_balance(self, api_client, trading_pair):
        """Test backtest with invalid initial balance."""
        url = reverse("api:backtest")
        data = {
            "symbol": "BTC_USDT",
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-06-01T00:00:00Z",
            "initial_balance": "-1000.00",
        }
        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_run_backtest_unknown_symbol(self, api_client, db):
        """Test backtest with unknown trading pair."""
        url = reverse("api:backtest")
        data = {
            "symbol": "UNKNOWN_PAIR",
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-06-01T00:00:00Z",
            "initial_balance": "10000.00",
        }
        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestPagination:
    """Tests for API pagination."""

    def test_signals_pagination(self, api_client, trading_pair):
        """Test signal list pagination."""
        # Create 25 signals
        for i in range(25):
            Signal.objects.create(
                trading_pair=trading_pair,
                direction=SignalDirection.BUY,
                confidence=80 + i % 20,
                indicators={},
            )

        url = reverse("api:signal_list")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "count" in response.data
        assert response.data["count"] == 25
        assert len(response.data["results"]) == 20  # Default page size
        assert "next" in response.data
        assert response.data["next"] is not None

    def test_custom_page_size(self, api_client, trading_pair):
        """Test custom page size."""
        for i in range(15):
            Signal.objects.create(
                trading_pair=trading_pair,
                direction=SignalDirection.BUY,
                confidence=85,
                indicators={},
            )

        url = reverse("api:signal_list")
        response = api_client.get(url, {"page_size": 5})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 5

    def test_max_page_size_limit(self, api_client, trading_pair):
        """Test max page size is enforced."""
        for i in range(150):
            Signal.objects.create(
                trading_pair=trading_pair,
                direction=SignalDirection.BUY,
                confidence=85,
                indicators={},
            )

        url = reverse("api:signal_list")
        response = api_client.get(url, {"page_size": 200})  # Exceeds max

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 100  # Max page size


class TestPortfolioUserIsolation:
    """Tests for portfolio user isolation.

    Portfolio endpoints enforce user isolation to ensure users only see
    their own portfolio data.

    Requirements:
    - 5.2: Filter results to only include snapshots owned by the authenticated user
    - 5.4: Return 404 for cross-user access attempts
    """

    @pytest.fixture
    def user_portfolio_snapshot(self, db, test_user):
        """Create a portfolio snapshot owned by test_user."""
        return PortfolioSnapshot.objects.create(
            user=test_user,
            total_value=Decimal("10000.00"),
            available_balance=Decimal("5000.00"),
            allocated_to_bots=Decimal("5000.00"),
            drawdown=0.05,
            high_water_mark=Decimal("10500.00"),
            is_simulated=False,
        )

    @pytest.fixture
    def user_simulated_snapshot(self, db, test_user):
        """Create a simulated portfolio snapshot owned by test_user."""
        return PortfolioSnapshot.objects.create(
            user=test_user,
            total_value=Decimal("50000.00"),
            available_balance=Decimal("25000.00"),
            allocated_to_bots=Decimal("25000.00"),
            drawdown=0.02,
            high_water_mark=Decimal("51000.00"),
            is_simulated=True,
        )

    @pytest.fixture
    def other_user_portfolio_snapshot(self, db, other_user):
        """Create a portfolio snapshot owned by another user."""
        return PortfolioSnapshot.objects.create(
            user=other_user,
            total_value=Decimal("20000.00"),
            available_balance=Decimal("10000.00"),
            allocated_to_bots=Decimal("10000.00"),
            drawdown=0.03,
            high_water_mark=Decimal("21000.00"),
            is_simulated=False,
        )

    @pytest.fixture
    def other_user_simulated_snapshot(self, db, other_user):
        """Create a simulated portfolio snapshot owned by another user."""
        return PortfolioSnapshot.objects.create(
            user=other_user,
            total_value=Decimal("100000.00"),
            available_balance=Decimal("50000.00"),
            allocated_to_bots=Decimal("50000.00"),
            drawdown=0.01,
            high_water_mark=Decimal("101000.00"),
            is_simulated=True,
        )

    # PortfolioView tests

    def test_get_portfolio_returns_user_snapshot(
        self, authenticated_client, user_portfolio_snapshot
    ):
        """Test getting portfolio returns the authenticated user's snapshot."""
        url = reverse("api:portfolio")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert Decimal(response.data["total_value"]) == Decimal("10000.00")
        assert response.data["is_simulated"] is False

    def test_get_portfolio_excludes_other_users(
        self, authenticated_client, other_user_portfolio_snapshot
    ):
        """Test getting portfolio excludes other users' snapshots."""
        url = reverse("api:portfolio")
        response = authenticated_client.get(url)

        # Should return 404 because user has no snapshots
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_portfolio_returns_own_when_others_exist(
        self, authenticated_client, user_portfolio_snapshot, other_user_portfolio_snapshot
    ):
        """Test getting portfolio returns own snapshot when others exist."""
        url = reverse("api:portfolio")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        # Should return user's snapshot (10000), not other user's (20000)
        assert Decimal(response.data["total_value"]) == Decimal("10000.00")

    def test_get_portfolio_simulated_returns_user_snapshot(
        self, authenticated_client, user_simulated_snapshot, other_user_simulated_snapshot
    ):
        """Test getting simulated portfolio returns user's simulated snapshot."""
        url = reverse("api:portfolio")
        response = authenticated_client.get(url, {"simulated": "true"})

        assert response.status_code == status.HTTP_200_OK
        # Should return user's simulated snapshot (50000), not other user's (100000)
        assert Decimal(response.data["total_value"]) == Decimal("50000.00")
        assert response.data["is_simulated"] is True

    def test_get_portfolio_unauthenticated_returns_404(
        self, api_client, user_portfolio_snapshot
    ):
        """Test getting portfolio without authentication returns 404."""
        url = reverse("api:portfolio")
        response = api_client.get(url)

        # Unauthenticated users get no results, so 404
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_portfolio_admin_sees_all(
        self, api_client, user_portfolio_snapshot, other_user_portfolio_snapshot, db
    ):
        """Test admin user can see all portfolio snapshots."""
        admin_user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="adminpass123",
        )
        api_client.force_authenticate(user=admin_user)

        url = reverse("api:portfolio")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        # Admin should see the most recent snapshot (could be either user's)
        assert response.data["total_value"] is not None

    # PortfolioHistoryView tests

    def test_get_portfolio_history_returns_user_snapshots(
        self, authenticated_client, user_portfolio_snapshot
    ):
        """Test getting portfolio history returns only user's snapshots."""
        url = reverse("api:portfolio_history")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert Decimal(response.data["results"][0]["total_value"]) == Decimal("10000.00")

    def test_get_portfolio_history_excludes_other_users(
        self, authenticated_client, user_portfolio_snapshot, other_user_portfolio_snapshot
    ):
        """Test getting portfolio history excludes other users' snapshots."""
        url = reverse("api:portfolio_history")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        # Should only contain user's snapshot
        assert Decimal(response.data["results"][0]["total_value"]) == Decimal("10000.00")

    def test_get_portfolio_history_unauthenticated_returns_empty(
        self, api_client, user_portfolio_snapshot
    ):
        """Test getting portfolio history without authentication returns empty."""
        url = reverse("api:portfolio_history")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 0

    def test_get_portfolio_history_simulated_filter(
        self, authenticated_client, user_portfolio_snapshot, user_simulated_snapshot
    ):
        """Test filtering portfolio history by simulated status."""
        url = reverse("api:portfolio_history")

        # Get live snapshots
        response = authenticated_client.get(url, {"simulated": "false"})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["is_simulated"] is False

        # Get simulated snapshots
        response = authenticated_client.get(url, {"simulated": "true"})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["is_simulated"] is True

    def test_get_portfolio_history_admin_sees_all(
        self, api_client, user_portfolio_snapshot, other_user_portfolio_snapshot, db
    ):
        """Test admin user can see all portfolio history."""
        admin_user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="adminpass123",
        )
        api_client.force_authenticate(user=admin_user)

        url = reverse("api:portfolio_history")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        # Admin should see both users' snapshots
        assert len(response.data["results"]) == 2

    def test_get_portfolio_history_multiple_snapshots(
        self, authenticated_client, test_user, db
    ):
        """Test getting portfolio history with multiple snapshots."""
        # Create multiple snapshots for the user
        for i in range(5):
            PortfolioSnapshot.objects.create(
                user=test_user,
                total_value=Decimal(f"{10000 + i * 1000}.00"),
                available_balance=Decimal("5000.00"),
                allocated_to_bots=Decimal("5000.00"),
                drawdown=0.05,
                high_water_mark=Decimal("10500.00"),
                is_simulated=False,
            )

        url = reverse("api:portfolio_history")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 5
        # All snapshots should belong to the user
        for snapshot in response.data["results"]:
            assert snapshot["is_simulated"] is False


class TestSignalUserPreferenceFiltering:
    """Tests for signal filtering by user preferences.

    Signals are shared across users (no user FK), but are filtered based on
    the authenticated user's active_trading_pairs preferences.

    Requirements:
    - 6.3: Display signals for trading pairs the user has configured
    """

    @pytest.fixture
    def btc_signal(self, db, trading_pair):
        """Create a BTC signal."""
        return Signal.objects.create(
            trading_pair=trading_pair,  # BTC_USDT
            direction=SignalDirection.BUY,
            confidence=85.0,
            indicators={"rsi": {"value": 35, "signal": "BUY"}},
            reasoning="RSI oversold",
            executed=False,
        )

    @pytest.fixture
    def eth_signal(self, db, trading_pair_eth):
        """Create an ETH signal."""
        return Signal.objects.create(
            trading_pair=trading_pair_eth,  # ETH_USDT
            direction=SignalDirection.SELL,
            confidence=90.0,
            indicators={"rsi": {"value": 75, "signal": "SELL"}},
            reasoning="RSI overbought",
            executed=False,
        )

    @pytest.fixture
    def sol_trading_pair(self, db):
        """Create a SOL trading pair."""
        return TradingPair.objects.create(
            symbol="SOL_USDT",
            base_currency="SOL",
            quote_currency="USDT",
            is_active=True,
        )

    @pytest.fixture
    def sol_signal(self, db, sol_trading_pair):
        """Create a SOL signal."""
        return Signal.objects.create(
            trading_pair=sol_trading_pair,
            direction=SignalDirection.BUY,
            confidence=75.0,
            indicators={"macd": {"value": 0.5, "signal": "BUY"}},
            reasoning="MACD bullish crossover",
            executed=False,
        )

    @pytest.fixture
    def user_with_btc_preference(self, test_user):
        """Configure test_user with BTC_USDT as active trading pair."""
        test_user.profile.active_trading_pairs = ["BTC_USDT"]
        test_user.profile.save()
        return test_user

    @pytest.fixture
    def user_with_multiple_preferences(self, test_user):
        """Configure test_user with multiple active trading pairs."""
        test_user.profile.active_trading_pairs = ["BTC_USDT", "ETH_USDT"]
        test_user.profile.save()
        return test_user

    @pytest.fixture
    def user_with_no_preferences(self, test_user):
        """Configure test_user with no active trading pairs."""
        test_user.profile.active_trading_pairs = []
        test_user.profile.save()
        return test_user

    @pytest.fixture
    def other_user_with_eth_preference(self, other_user):
        """Configure other_user with ETH_USDT as active trading pair."""
        other_user.profile.active_trading_pairs = ["ETH_USDT"]
        other_user.profile.save()
        return other_user

    # Tests for authenticated users with preferences

    def test_signals_filtered_by_single_active_pair(
        self, api_client, user_with_btc_preference, btc_signal, eth_signal
    ):
        """Test signals are filtered to user's single active trading pair."""
        api_client.force_authenticate(user=user_with_btc_preference)

        url = reverse("api:signal_list")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["trading_pair"]["symbol"] == "BTC_USDT"

    def test_signals_filtered_by_multiple_active_pairs(
        self, api_client, user_with_multiple_preferences, btc_signal, eth_signal, sol_signal
    ):
        """Test signals are filtered to user's multiple active trading pairs."""
        api_client.force_authenticate(user=user_with_multiple_preferences)

        url = reverse("api:signal_list")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 2
        symbols = {r["trading_pair"]["symbol"] for r in response.data["results"]}
        assert symbols == {"BTC_USDT", "ETH_USDT"}
        # SOL_USDT should not be included
        assert "SOL_USDT" not in symbols

    def test_signals_empty_when_no_active_pairs(
        self, api_client, user_with_no_preferences, btc_signal, eth_signal
    ):
        """Test no signals returned when user has no active trading pairs."""
        api_client.force_authenticate(user=user_with_no_preferences)

        url = reverse("api:signal_list")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 0

    def test_different_users_see_different_signals(
        self,
        api_client,
        user_with_btc_preference,
        other_user_with_eth_preference,
        btc_signal,
        eth_signal,
    ):
        """Test different users see signals based on their own preferences."""
        # User with BTC preference sees only BTC signals
        api_client.force_authenticate(user=user_with_btc_preference)
        url = reverse("api:signal_list")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["trading_pair"]["symbol"] == "BTC_USDT"

        # Other user with ETH preference sees only ETH signals
        api_client.force_authenticate(user=other_user_with_eth_preference)
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["trading_pair"]["symbol"] == "ETH_USDT"

    # Tests for unauthenticated users

    def test_unauthenticated_users_see_all_signals(
        self, api_client, btc_signal, eth_signal, sol_signal
    ):
        """Test unauthenticated users see all signals (public market data)."""
        url = reverse("api:signal_list")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 3

    # Tests for admin users

    def test_admin_sees_all_signals(
        self, api_client, btc_signal, eth_signal, sol_signal, db
    ):
        """Test admin user sees all signals regardless of preferences."""
        admin_user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="adminpass123",
        )
        # Even if admin has preferences set, they should see all signals
        admin_user.profile.active_trading_pairs = ["BTC_USDT"]
        admin_user.profile.save()

        api_client.force_authenticate(user=admin_user)

        url = reverse("api:signal_list")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 3

    # Tests for combined filtering (user preferences + query params)

    def test_signal_filtering_combined_with_direction_filter(
        self, api_client, user_with_multiple_preferences, btc_signal, eth_signal
    ):
        """Test user preference filtering works with direction query param."""
        api_client.force_authenticate(user=user_with_multiple_preferences)

        url = reverse("api:signal_list")
        # BTC signal is BUY, ETH signal is SELL
        response = api_client.get(url, {"direction": "BUY"})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["trading_pair"]["symbol"] == "BTC_USDT"
        assert response.data["results"][0]["direction"] == "BUY"

    def test_signal_filtering_combined_with_confidence_filter(
        self, api_client, user_with_multiple_preferences, btc_signal, eth_signal
    ):
        """Test user preference filtering works with confidence query param."""
        api_client.force_authenticate(user=user_with_multiple_preferences)

        url = reverse("api:signal_list")
        # BTC signal has 85% confidence, ETH signal has 90% confidence
        response = api_client.get(url, {"min_confidence": "88"})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["trading_pair"]["symbol"] == "ETH_USDT"
        assert response.data["results"][0]["confidence"] >= 88

    def test_signal_filtering_combined_with_symbol_filter(
        self, api_client, user_with_multiple_preferences, btc_signal, eth_signal
    ):
        """Test user preference filtering works with symbol query param."""
        api_client.force_authenticate(user=user_with_multiple_preferences)

        url = reverse("api:signal_list")
        response = api_client.get(url, {"symbol": "ETH_USDT"})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["trading_pair"]["symbol"] == "ETH_USDT"

    def test_symbol_filter_outside_preferences_returns_empty(
        self, api_client, user_with_btc_preference, btc_signal, eth_signal
    ):
        """Test filtering by symbol outside user's preferences returns empty."""
        api_client.force_authenticate(user=user_with_btc_preference)

        url = reverse("api:signal_list")
        # User only has BTC_USDT in preferences, but filtering for ETH_USDT
        response = api_client.get(url, {"symbol": "ETH_USDT"})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 0

    # Tests for edge cases

    def test_signals_with_nonexistent_preference_pair(
        self, api_client, test_user, btc_signal, eth_signal
    ):
        """Test user with preference for non-existent pair sees no signals."""
        test_user.profile.active_trading_pairs = ["DOGE_USDT"]  # No signals for this
        test_user.profile.save()

        api_client.force_authenticate(user=test_user)

        url = reverse("api:signal_list")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 0

    def test_signals_with_mixed_valid_invalid_preferences(
        self, api_client, test_user, btc_signal, eth_signal
    ):
        """Test user with mix of valid and invalid preferences sees valid signals."""
        test_user.profile.active_trading_pairs = ["BTC_USDT", "DOGE_USDT"]  # DOGE has no signals
        test_user.profile.save()

        api_client.force_authenticate(user=test_user)

        url = reverse("api:signal_list")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["trading_pair"]["symbol"] == "BTC_USDT"

    def test_signal_detail_accessible_regardless_of_preferences(
        self, api_client, user_with_btc_preference, eth_signal
    ):
        """Test signal detail view is accessible regardless of user preferences.

        The detail view doesn't filter by preferences - if you have the ID,
        you can view the signal details (signals are shared market data).
        """
        api_client.force_authenticate(user=user_with_btc_preference)

        url = reverse("api:signal_detail", kwargs={"pk": eth_signal.pk})
        response = api_client.get(url)

        # Signal detail should be accessible (signals are public market data)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["trading_pair"]["symbol"] == "ETH_USDT"
