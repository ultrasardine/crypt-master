"""
Unit tests for DryRunSimulator.

Tests the dry-run simulation functionality including balance management,
order simulation, and bot simulation.

Requirements:
- 2.1: Simulate all order operations without calling real Pionex order endpoint
- 2.2: Maintain a simulated balance ledger tracking virtual positions
- 2.3: Update simulated balance ledger as if orders filled at current market price
- 2.4: Log all simulated trades with timestamps, prices, quantities, and simulated P&L
- 10.12: Simulate bot operations without creating real bots on Pionex
"""

import pytest
from decimal import Decimal

from lib.simulation import (
    DryRunSimulator,
    SimulatedBalance,
    SimulatedOrderStatus,
    SimulatedBotStatus,
    SimulatedBotType,
)


class TestBalanceManagement:
    """Tests for balance management functionality."""
    
    def test_set_balance(self) -> None:
        """Test setting a balance for a currency."""
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", Decimal("10000.00"))
        
        balance = simulator.get_balance("USDT")
        assert balance.currency == "USDT"
        assert balance.free == Decimal("10000.00")
        assert balance.locked == Decimal("0")
        assert balance.total == Decimal("10000.00")
    
    def test_set_balance_negative_raises(self) -> None:
        """Test that setting negative balance raises ValueError."""
        simulator = DryRunSimulator()
        
        with pytest.raises(ValueError, match="non-negative"):
            simulator.set_balance("USDT", Decimal("-100"))
    
    def test_get_balance_unset_returns_zero(self) -> None:
        """Test that getting unset balance returns zero."""
        simulator = DryRunSimulator()
        
        balance = simulator.get_balance("BTC")
        assert balance.currency == "BTC"
        assert balance.free == Decimal("0")
        assert balance.total == Decimal("0")
    
    def test_get_all_balances(self) -> None:
        """Test getting all non-zero balances."""
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", Decimal("10000.00"))
        simulator.set_balance("BTC", Decimal("0.5"))
        simulator.set_balance("ETH", Decimal("0"))  # Should not appear
        
        balances = simulator.get_all_balances()
        assert len(balances) == 2
        currencies = {b.currency for b in balances}
        assert currencies == {"USDT", "BTC"}
    
    def test_ledger_tracks_balance_changes(self) -> None:
        """Test that ledger tracks all balance changes."""
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", Decimal("10000.00"))
        simulator.set_balance("USDT", Decimal("15000.00"))
        
        ledger = simulator.get_ledger()
        assert len(ledger) == 2
        
        # First entry: set to 10000
        assert ledger[0].currency == "USDT"
        assert ledger[0].change == Decimal("10000.00")
        assert ledger[0].balance_after == Decimal("10000.00")
        
        # Second entry: change from 10000 to 15000
        assert ledger[1].currency == "USDT"
        assert ledger[1].change == Decimal("5000.00")
        assert ledger[1].balance_after == Decimal("15000.00")


class TestOrderSimulation:
    """Tests for order simulation functionality."""
    
    def test_simulate_buy_order(self) -> None:
        """Test simulating a BUY order."""
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", Decimal("10000.00"))
        simulator.set_balance("BTC", Decimal("0"))
        
        order = simulator.simulate_order(
            symbol="BTC_USDT",
            side="BUY",
            quantity=Decimal("0.1"),
            price=Decimal("50000.00"),
        )
        
        assert order.status == SimulatedOrderStatus.FILLED
        assert order.side == "BUY"
        assert order.quantity == Decimal("0.1")
        assert order.price == Decimal("50000.00")
        assert order.quote_amount == Decimal("5000.00")
        
        # Check balances updated correctly
        usdt_balance = simulator.get_balance("USDT")
        btc_balance = simulator.get_balance("BTC")
        assert usdt_balance.free == Decimal("5000.00")  # 10000 - 5000
        assert btc_balance.free == Decimal("0.1")
    
    def test_simulate_sell_order(self) -> None:
        """Test simulating a SELL order."""
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", Decimal("0"))
        simulator.set_balance("BTC", Decimal("0.5"))
        
        order = simulator.simulate_order(
            symbol="BTC_USDT",
            side="SELL",
            quantity=Decimal("0.1"),
            price=Decimal("50000.00"),
        )
        
        assert order.status == SimulatedOrderStatus.FILLED
        assert order.side == "SELL"
        
        # Check balances updated correctly
        usdt_balance = simulator.get_balance("USDT")
        btc_balance = simulator.get_balance("BTC")
        assert usdt_balance.free == Decimal("5000.00")  # 0 + 5000
        assert btc_balance.free == Decimal("0.4")  # 0.5 - 0.1
    
    def test_simulate_order_insufficient_balance(self) -> None:
        """Test that order is rejected with insufficient balance."""
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", Decimal("1000.00"))
        
        order = simulator.simulate_order(
            symbol="BTC_USDT",
            side="BUY",
            quantity=Decimal("0.1"),
            price=Decimal("50000.00"),  # Needs 5000 USDT
        )
        
        assert order.status == SimulatedOrderStatus.REJECTED
        
        # Balance should be unchanged
        usdt_balance = simulator.get_balance("USDT")
        assert usdt_balance.free == Decimal("1000.00")
    
    def test_simulate_order_invalid_side(self) -> None:
        """Test that invalid side raises ValueError."""
        simulator = DryRunSimulator()
        
        with pytest.raises(ValueError, match="BUY.*SELL"):
            simulator.simulate_order(
                symbol="BTC_USDT",
                side="INVALID",
                quantity=Decimal("0.1"),
                price=Decimal("50000.00"),
            )
    
    def test_simulate_order_invalid_quantity(self) -> None:
        """Test that invalid quantity raises ValueError."""
        simulator = DryRunSimulator()
        
        with pytest.raises(ValueError, match="positive"):
            simulator.simulate_order(
                symbol="BTC_USDT",
                side="BUY",
                quantity=Decimal("-0.1"),
                price=Decimal("50000.00"),
            )
    
    def test_simulate_order_invalid_price(self) -> None:
        """Test that invalid price raises ValueError."""
        simulator = DryRunSimulator()
        
        with pytest.raises(ValueError, match="positive"):
            simulator.simulate_order(
                symbol="BTC_USDT",
                side="BUY",
                quantity=Decimal("0.1"),
                price=Decimal("0"),
            )
    
    def test_get_orders(self) -> None:
        """Test getting all simulated orders."""
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", Decimal("10000.00"))
        simulator.set_balance("BTC", Decimal("0.5"))
        
        simulator.simulate_order("BTC_USDT", "BUY", Decimal("0.1"), Decimal("50000.00"))
        simulator.simulate_order("BTC_USDT", "SELL", Decimal("0.05"), Decimal("51000.00"))
        
        orders = simulator.get_orders()
        assert len(orders) == 2
        assert orders[0].side == "BUY"
        assert orders[1].side == "SELL"
    
    def test_trades_recorded(self) -> None:
        """Test that trades are recorded with P&L."""
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", Decimal("10000.00"))
        
        # Buy BTC
        simulator.simulate_order("BTC_USDT", "BUY", Decimal("0.1"), Decimal("50000.00"))
        
        # Sell BTC at higher price
        simulator.simulate_order("BTC_USDT", "SELL", Decimal("0.1"), Decimal("55000.00"))
        
        trades = simulator.get_trades()
        assert len(trades) == 2
        
        # Second trade should have P&L
        sell_trade = trades[1]
        assert sell_trade.is_closing is True
        assert sell_trade.pnl == Decimal("500.00")  # (55000 - 50000) * 0.1


class TestBotSimulation:
    """Tests for bot simulation functionality."""
    
    def test_simulate_grid_bot_creation(self) -> None:
        """Test simulating Grid bot creation."""
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", Decimal("10000.00"))
        
        bot = simulator.simulate_bot_creation(
            symbol="BTC_USDT",
            bot_type="GRID",
            investment=Decimal("1000.00"),
            params={"lower_price": 40000, "upper_price": 60000, "grid_count": 10},
        )
        
        assert bot.bot_type == SimulatedBotType.GRID
        assert bot.status == SimulatedBotStatus.ACTIVE
        assert bot.invested == Decimal("1000.00")
        assert bot.current_value == Decimal("1000.00")
        assert bot.pnl == Decimal("0")
        
        # Check balance: 1000 moved from free to locked
        usdt_balance = simulator.get_balance("USDT")
        assert usdt_balance.free == Decimal("9000.00")
        assert usdt_balance.locked == Decimal("1000.00")
    
    def test_simulate_dca_bot_creation(self) -> None:
        """Test simulating DCA bot creation."""
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", Decimal("5000.00"))
        
        bot = simulator.simulate_bot_creation(
            symbol="ETH_USDT",
            bot_type="DCA",
            investment=Decimal("500.00"),
        )
        
        assert bot.bot_type == SimulatedBotType.DCA
        assert bot.status == SimulatedBotStatus.ACTIVE
        assert bot.symbol == "ETH_USDT"
    
    def test_simulate_bot_creation_insufficient_balance(self) -> None:
        """Test that bot creation fails with insufficient balance."""
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", Decimal("500.00"))
        
        with pytest.raises(ValueError, match="Insufficient"):
            simulator.simulate_bot_creation(
                symbol="BTC_USDT",
                bot_type="GRID",
                investment=Decimal("1000.00"),
            )
    
    def test_simulate_bot_creation_invalid_type(self) -> None:
        """Test that invalid bot type raises ValueError."""
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", Decimal("10000.00"))
        
        with pytest.raises(ValueError, match="GRID.*DCA"):
            simulator.simulate_bot_creation(
                symbol="BTC_USDT",
                bot_type="INVALID",
                investment=Decimal("1000.00"),
            )
    
    def test_simulate_bot_stop(self) -> None:
        """Test simulating bot stop."""
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", Decimal("10000.00"))
        
        bot = simulator.simulate_bot_creation(
            symbol="BTC_USDT",
            bot_type="GRID",
            investment=Decimal("1000.00"),
        )
        
        stopped_bot = simulator.simulate_bot_stop(bot.bot_id)
        
        assert stopped_bot.status == SimulatedBotStatus.STOPPED
        
        # Check balance: funds returned to free
        usdt_balance = simulator.get_balance("USDT")
        assert usdt_balance.free == Decimal("10000.00")
        assert usdt_balance.locked == Decimal("0")
    
    def test_simulate_bot_stop_not_found(self) -> None:
        """Test that stopping non-existent bot raises ValueError."""
        simulator = DryRunSimulator()
        
        with pytest.raises(ValueError, match="not found"):
            simulator.simulate_bot_stop("INVALID-BOT-ID")
    
    def test_simulate_bot_stop_already_stopped(self) -> None:
        """Test that stopping already stopped bot raises ValueError."""
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", Decimal("10000.00"))
        
        bot = simulator.simulate_bot_creation(
            symbol="BTC_USDT",
            bot_type="GRID",
            investment=Decimal("1000.00"),
        )
        simulator.simulate_bot_stop(bot.bot_id)
        
        with pytest.raises(ValueError, match="already stopped"):
            simulator.simulate_bot_stop(bot.bot_id)
    
    def test_update_bot_value(self) -> None:
        """Test updating bot value."""
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", Decimal("10000.00"))
        
        bot = simulator.simulate_bot_creation(
            symbol="BTC_USDT",
            bot_type="GRID",
            investment=Decimal("1000.00"),
        )
        
        updated_bot = simulator.update_bot_value(bot.bot_id, Decimal("1100.00"))
        
        assert updated_bot.current_value == Decimal("1100.00")
        assert updated_bot.pnl == Decimal("100.00")
        assert updated_bot.pnl_percent == pytest.approx(10.0)
    
    def test_get_bot(self) -> None:
        """Test getting a bot by ID."""
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", Decimal("10000.00"))
        
        created_bot = simulator.simulate_bot_creation(
            symbol="BTC_USDT",
            bot_type="GRID",
            investment=Decimal("1000.00"),
        )
        
        retrieved_bot = simulator.get_bot(created_bot.bot_id)
        assert retrieved_bot is not None
        assert retrieved_bot.bot_id == created_bot.bot_id
        
        # Non-existent bot
        assert simulator.get_bot("INVALID") is None
    
    def test_get_all_bots(self) -> None:
        """Test getting all bots."""
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", Decimal("10000.00"))
        
        simulator.simulate_bot_creation("BTC_USDT", "GRID", Decimal("1000.00"))
        simulator.simulate_bot_creation("ETH_USDT", "DCA", Decimal("500.00"))
        
        bots = simulator.get_all_bots()
        assert len(bots) == 2
    
    def test_get_active_bots(self) -> None:
        """Test getting only active bots."""
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", Decimal("10000.00"))
        
        bot1 = simulator.simulate_bot_creation("BTC_USDT", "GRID", Decimal("1000.00"))
        simulator.simulate_bot_creation("ETH_USDT", "DCA", Decimal("500.00"))
        simulator.simulate_bot_stop(bot1.bot_id)
        
        active_bots = simulator.get_active_bots()
        assert len(active_bots) == 1
        assert active_bots[0].symbol == "ETH_USDT"


class TestPortfolioAndPnL:
    """Tests for portfolio and P&L functionality."""
    
    def test_get_total_pnl(self) -> None:
        """Test getting total realized P&L."""
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", Decimal("10000.00"))
        
        # Buy and sell with profit
        simulator.simulate_order("BTC_USDT", "BUY", Decimal("0.1"), Decimal("50000.00"))
        simulator.simulate_order("BTC_USDT", "SELL", Decimal("0.1"), Decimal("55000.00"))
        
        total_pnl = simulator.get_total_pnl()
        assert total_pnl == Decimal("500.00")
    
    def test_get_bot_allocation(self) -> None:
        """Test getting total bot allocation."""
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", Decimal("10000.00"))
        
        bot1 = simulator.simulate_bot_creation("BTC_USDT", "GRID", Decimal("1000.00"))
        simulator.simulate_bot_creation("ETH_USDT", "DCA", Decimal("500.00"))
        
        allocation = simulator.get_bot_allocation()
        assert allocation == Decimal("1500.00")
        
        # Stop one bot
        simulator.simulate_bot_stop(bot1.bot_id)
        allocation = simulator.get_bot_allocation()
        assert allocation == Decimal("500.00")
    
    def test_get_portfolio_value(self) -> None:
        """Test calculating portfolio value."""
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", Decimal("5000.00"))
        simulator.set_balance("BTC", Decimal("0.1"))
        
        prices = {
            "BTC_USDT": Decimal("50000.00"),
        }
        
        portfolio_value = simulator.get_portfolio_value(prices)
        # 5000 USDT + 0.1 BTC * 50000 = 5000 + 5000 = 10000
        assert portfolio_value == Decimal("10000.00")
    
    def test_reset(self) -> None:
        """Test resetting the simulator."""
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", Decimal("10000.00"))
        simulator.simulate_order("BTC_USDT", "BUY", Decimal("0.1"), Decimal("50000.00"))
        simulator.simulate_bot_creation("ETH_USDT", "DCA", Decimal("500.00"))
        
        simulator.reset()
        
        assert len(simulator.get_all_balances()) == 0
        assert len(simulator.get_orders()) == 0
        assert len(simulator.get_all_bots()) == 0
        assert len(simulator.get_trades()) == 0
        assert len(simulator.get_ledger()) == 0
