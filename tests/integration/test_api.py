"""Integration tests for REST API endpoints."""

import json
from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.bots.models import Bot, BotEvent, BotStatus, BotType
from apps.core.models import PortfolioSnapshot, SystemConfig, TradingPair
from apps.trading.models import Signal, SignalDirection, Trade, TradeSide


@pytest.fixture
def api_client():
    """Create an API client for testing."""
    return APIClient()


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
def portfolio_snapshot(db):
    """Create a test portfolio snapshot."""
    return PortfolioSnapshot.objects.create(
        total_value=Decimal("10000.00"),
        available_balance=Decimal("5000.00"),
        allocated_to_bots=Decimal("5000.00"),
        drawdown=0.05,
        high_water_mark=Decimal("10500.00"),
        is_simulated=False,
    )


@pytest.fixture
def simulated_portfolio_snapshot(db):
    """Create a simulated portfolio snapshot."""
    return PortfolioSnapshot.objects.create(
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
def bot(db, trading_pair):
    """Create a test bot."""
    return Bot.objects.create(
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
def simulated_bot(db, trading_pair):
    """Create a simulated bot."""
    return Bot.objects.create(
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
def trade(db, trading_pair, signal):
    """Create a test trade."""
    return Trade.objects.create(
        signal=signal,
        trading_pair=trading_pair,
        side=TradeSide.BUY,
        entry_price=Decimal("45000.00"),
        quantity=Decimal("0.1"),
        is_simulated=False,
        order_id="order_123",
    )


@pytest.fixture
def closed_trade(db, trading_pair):
    """Create a closed trade with P&L."""
    from django.utils import timezone
    return Trade.objects.create(
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
def system_config(db):
    """Create test system configuration."""
    return SystemConfig.objects.create(
        key="min_confidence",
        value=85.0,
        description="Minimum confidence threshold for trading",
    )


class TestPortfolioAPI:
    """Tests for portfolio endpoints."""

    def test_get_portfolio_success(self, api_client, portfolio_snapshot):
        """Test getting current portfolio snapshot."""
        url = reverse("api:portfolio")
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert Decimal(response.data["total_value"]) == Decimal("10000.00")
        assert response.data["is_simulated"] is False

    def test_get_portfolio_simulated(self, api_client, simulated_portfolio_snapshot):
        """Test getting simulated portfolio snapshot."""
        url = reverse("api:portfolio")
        response = api_client.get(url, {"simulated": "true"})
        
        assert response.status_code == status.HTTP_200_OK
        assert Decimal(response.data["total_value"]) == Decimal("50000.00")
        assert response.data["is_simulated"] is True

    def test_get_portfolio_not_found(self, api_client, db):
        """Test getting portfolio when none exists."""
        url = reverse("api:portfolio")
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_portfolio_history(self, api_client, portfolio_snapshot):
        """Test getting portfolio history."""
        url = reverse("api:portfolio_history")
        response = api_client.get(url)
        
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
    """Tests for bot endpoints."""

    def test_list_bots(self, api_client, bot, simulated_bot):
        """Test listing bots."""
        url = reverse("api:bot_list")
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 2

    def test_filter_bots_by_status(self, api_client, bot):
        """Test filtering bots by status."""
        url = reverse("api:bot_list")
        response = api_client.get(url, {"status": "ACTIVE"})
        
        assert response.status_code == status.HTTP_200_OK
        assert all(b["status"] == "ACTIVE" for b in response.data["results"])

    def test_filter_bots_by_type(self, api_client, bot, simulated_bot):
        """Test filtering bots by type."""
        url = reverse("api:bot_list")
        response = api_client.get(url, {"type": "GRID"})
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["bot_type"] == "GRID"

    def test_filter_bots_by_simulated(self, api_client, bot, simulated_bot):
        """Test filtering bots by simulated status."""
        url = reverse("api:bot_list")
        response = api_client.get(url, {"simulated": "true"})
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["is_simulated"] is True

    def test_create_bot(self, api_client, trading_pair):
        """Test creating a new bot."""
        url = reverse("api:bot_list")
        data = {
            "bot_type": "GRID",
            "trading_pair_id": trading_pair.pk,
            "invested_amount": "1000.00",
            "params": {"lower_price": 40000, "upper_price": 50000, "grid_count": 10},
            "is_simulated": True,
        }
        response = api_client.post(url, data, format="json")
        
        assert response.status_code == status.HTTP_201_CREATED
        assert Bot.objects.count() == 1
        
        bot = Bot.objects.first()
        assert bot.status == BotStatus.ACTIVE
        assert bot.is_simulated is True
        assert BotEvent.objects.filter(bot=bot, event_type="CREATED").exists()

    def test_create_bot_invalid_type(self, api_client, trading_pair):
        """Test creating bot with invalid type."""
        url = reverse("api:bot_list")
        data = {
            "bot_type": "INVALID",
            "trading_pair_id": trading_pair.pk,
            "invested_amount": "1000.00",
        }
        response = api_client.post(url, data, format="json")
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_bot_negative_amount(self, api_client, trading_pair):
        """Test creating bot with negative invested amount."""
        url = reverse("api:bot_list")
        data = {
            "bot_type": "GRID",
            "trading_pair_id": trading_pair.pk,
            "invested_amount": "-100.00",
        }
        response = api_client.post(url, data, format="json")
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_get_bot_detail(self, api_client, bot):
        """Test getting bot details."""
        url = reverse("api:bot_detail", kwargs={"pk": bot.pk})
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data["pionex_bot_id"] == "bot_test123"
        assert response.data["bot_type"] == "GRID"

    def test_stop_bot(self, api_client, bot):
        """Test stopping a bot."""
        url = reverse("api:bot_detail", kwargs={"pk": bot.pk})
        response = api_client.delete(url, {"reason": "Test stop"}, format="json")
        
        assert response.status_code == status.HTTP_200_OK
        
        bot.refresh_from_db()
        assert bot.status == BotStatus.STOPPED
        assert bot.stop_reason == "Test stop"
        assert BotEvent.objects.filter(bot=bot, event_type="STOPPED").exists()

    def test_stop_already_stopped_bot(self, api_client, bot):
        """Test stopping an already stopped bot."""
        bot.status = BotStatus.STOPPED
        bot.save()
        
        url = reverse("api:bot_detail", kwargs={"pk": bot.pk})
        response = api_client.delete(url)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestTradeAPI:
    """Tests for trade endpoints."""

    def test_list_trades(self, api_client, trade, closed_trade):
        """Test listing trades."""
        url = reverse("api:trade_list")
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 2

    def test_filter_trades_by_side(self, api_client, trade, closed_trade):
        """Test filtering trades by side."""
        url = reverse("api:trade_list")
        response = api_client.get(url, {"side": "BUY"})
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["side"] == "BUY"

    def test_filter_trades_by_status(self, api_client, trade, closed_trade):
        """Test filtering trades by open/closed status."""
        url = reverse("api:trade_list")
        response = api_client.get(url, {"status": "closed"})
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["exit_price"] is not None

    def test_get_trade_detail(self, api_client, trade):
        """Test getting trade details."""
        url = reverse("api:trade_detail", kwargs={"pk": trade.pk})
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data["side"] == "BUY"
        assert Decimal(response.data["entry_price"]) == Decimal("45000.00")

    def test_get_trade_statistics(self, api_client, trade, closed_trade):
        """Test getting trade statistics."""
        url = reverse("api:trade_statistics")
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data["total_trades"] == 2
        assert response.data["closed_trades"] == 1
        assert response.data["open_positions"] == 1


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
