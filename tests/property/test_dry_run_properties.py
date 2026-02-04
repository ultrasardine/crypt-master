"""
Property-based tests for Dry-Run Simulator.

Feature: pionex-trading-bot
Property 2: Simulated Balance Ledger Correctness
Property 15: Dry-Run Isolation

These tests use the hypothesis library to verify that the dry-run simulator
behaves correctly across all valid inputs.

**Validates: Requirements 2.2, 2.3, 10.12**
"""

import pytest
from decimal import Decimal
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from lib.simulation import (
    DryRunSimulator,
    SimulatedOrderStatus,
    SimulatedBotStatus,
)


# =============================================================================
# Custom Strategies for Dry-Run Simulation
# =============================================================================

# Strategy for valid currency codes
currency_strategy = st.sampled_from(["BTC", "ETH", "USDT", "SOL", "XRP", "ADA"])

# Strategy for valid trading symbols
symbol_strategy = st.sampled_from([
    "BTC_USDT", "ETH_USDT", "SOL_USDT", "XRP_USDT", "ADA_USDT"
])

# Strategy for order side
side_strategy = st.sampled_from(["BUY", "SELL"])

# Strategy for bot type
bot_type_strategy = st.sampled_from(["GRID", "DCA"])

# Strategy for valid positive amounts (Decimal)
positive_amount_strategy = st.decimals(
    min_value=Decimal("0.00000001"),
    max_value=Decimal("1000000.00"),
    allow_nan=False,
    allow_infinity=False,
    places=8,
)

# Strategy for valid prices (Decimal)
price_strategy = st.decimals(
    min_value=Decimal("0.01"),
    max_value=Decimal("1000000.00"),
    allow_nan=False,
    allow_infinity=False,
    places=8,
)

# Strategy for valid balance amounts (Decimal)
balance_strategy = st.decimals(
    min_value=Decimal("0.00"),
    max_value=Decimal("1000000000.00"),
    allow_nan=False,
    allow_infinity=False,
    places=8,
)


@st.composite
def order_params_strategy(draw: st.DrawFn) -> dict:
    """
    Generate valid order parameters.
    
    Creates order parameters with random but valid values for testing
    the balance ledger properties.
    """
    symbol = draw(symbol_strategy)
    side = draw(side_strategy)
    quantity = draw(positive_amount_strategy)
    price = draw(price_strategy)
    
    return {
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "price": price,
    }


@st.composite
def order_sequence_strategy(draw: st.DrawFn) -> list[dict]:
    """
    Generate a sequence of valid order parameters.
    
    Creates a list of orders for testing balance ledger correctness
    across multiple operations.
    """
    num_orders = draw(st.integers(min_value=1, max_value=10))
    orders = []
    
    for _ in range(num_orders):
        order = draw(order_params_strategy())
        orders.append(order)
    
    return orders


# =============================================================================
# Property 2: Simulated Balance Ledger Correctness
# =============================================================================

class TestSimulatedBalanceLedgerCorrectness:
    """
    Property 2: Simulated Balance Ledger Correctness
    
    *For any* sequence of simulated orders, the balance ledger SHALL correctly
    reflect currency changes (BUY decreases quote, increases base; SELL vice versa).
    
    **Validates: Requirements 2.2, 2.3**
    """

    @settings(max_examples=100)
    @given(
        initial_quote=balance_strategy,
        initial_base=balance_strategy,
        quantity=positive_amount_strategy,
        price=price_strategy,
    )
    def test_buy_order_balance_changes(
        self,
        initial_quote: Decimal,
        initial_base: Decimal,
        quantity: Decimal,
        price: Decimal,
    ) -> None:
        """
        Property: For any BUY order, quote currency SHALL decrease by (price * quantity)
        and base currency SHALL increase by quantity.
        
        **Validates: Requirements 2.2, 2.3**
        """
        quote_amount = price * quantity
        
        # Skip if insufficient balance
        assume(initial_quote >= quote_amount)
        
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", initial_quote)
        simulator.set_balance("BTC", initial_base)
        
        order = simulator.simulate_order(
            symbol="BTC_USDT",
            side="BUY",
            quantity=quantity,
            price=price,
        )
        
        # Order should be filled
        assert order.status == SimulatedOrderStatus.FILLED, (
            f"Order should be filled with sufficient balance"
        )
        
        # Check quote currency decreased correctly
        final_quote = simulator.get_balance("USDT").free
        expected_quote = initial_quote - quote_amount
        assert final_quote == expected_quote, (
            f"Quote currency mismatch: expected {expected_quote}, got {final_quote}"
        )
        
        # Check base currency increased correctly
        final_base = simulator.get_balance("BTC").free
        expected_base = initial_base + quantity
        assert final_base == expected_base, (
            f"Base currency mismatch: expected {expected_base}, got {final_base}"
        )

    @settings(max_examples=100)
    @given(
        initial_quote=balance_strategy,
        initial_base=balance_strategy,
        quantity=positive_amount_strategy,
        price=price_strategy,
    )
    def test_sell_order_balance_changes(
        self,
        initial_quote: Decimal,
        initial_base: Decimal,
        quantity: Decimal,
        price: Decimal,
    ) -> None:
        """
        Property: For any SELL order, base currency SHALL decrease by quantity
        and quote currency SHALL increase by (price * quantity).
        
        **Validates: Requirements 2.2, 2.3**
        """
        quote_amount = price * quantity
        
        # Skip if insufficient balance
        assume(initial_base >= quantity)
        
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", initial_quote)
        simulator.set_balance("BTC", initial_base)
        
        order = simulator.simulate_order(
            symbol="BTC_USDT",
            side="SELL",
            quantity=quantity,
            price=price,
        )
        
        # Order should be filled
        assert order.status == SimulatedOrderStatus.FILLED, (
            f"Order should be filled with sufficient balance"
        )
        
        # Check base currency decreased correctly
        final_base = simulator.get_balance("BTC").free
        expected_base = initial_base - quantity
        assert final_base == expected_base, (
            f"Base currency mismatch: expected {expected_base}, got {final_base}"
        )
        
        # Check quote currency increased correctly
        final_quote = simulator.get_balance("USDT").free
        expected_quote = initial_quote + quote_amount
        assert final_quote == expected_quote, (
            f"Quote currency mismatch: expected {expected_quote}, got {final_quote}"
        )

    @settings(max_examples=100)
    @given(
        initial_balance=balance_strategy,
        quantity=positive_amount_strategy,
        price=price_strategy,
    )
    def test_insufficient_balance_rejects_order(
        self,
        initial_balance: Decimal,
        quantity: Decimal,
        price: Decimal,
    ) -> None:
        """
        Property: For any order where required balance exceeds available,
        order SHALL be rejected and balances SHALL remain unchanged.
        
        **Validates: Requirements 2.2, 2.3**
        """
        quote_amount = price * quantity
        
        # Ensure insufficient balance
        assume(initial_balance < quote_amount)
        
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", initial_balance)
        simulator.set_balance("BTC", Decimal("0"))
        
        order = simulator.simulate_order(
            symbol="BTC_USDT",
            side="BUY",
            quantity=quantity,
            price=price,
        )
        
        # Order should be rejected
        assert order.status == SimulatedOrderStatus.REJECTED, (
            f"Order should be rejected with insufficient balance"
        )
        
        # Balances should be unchanged
        final_quote = simulator.get_balance("USDT").free
        final_base = simulator.get_balance("BTC").free
        
        assert final_quote == initial_balance, (
            f"Quote balance should be unchanged: expected {initial_balance}, got {final_quote}"
        )
        assert final_base == Decimal("0"), (
            f"Base balance should be unchanged: expected 0, got {final_base}"
        )

    @settings(max_examples=100)
    @given(
        initial_quote=balance_strategy,
        initial_base=balance_strategy,
        quantity=positive_amount_strategy,
        price=price_strategy,
        side=side_strategy,
    )
    def test_balance_conservation(
        self,
        initial_quote: Decimal,
        initial_base: Decimal,
        quantity: Decimal,
        price: Decimal,
        side: str,
    ) -> None:
        """
        Property: For any filled order, total value (in quote currency) SHALL be conserved.
        
        Total value = quote_balance + (base_balance * price)
        
        **Validates: Requirements 2.2, 2.3**
        """
        quote_amount = price * quantity
        
        # Ensure sufficient balance for the order
        if side == "BUY":
            assume(initial_quote >= quote_amount)
        else:
            assume(initial_base >= quantity)
        
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", initial_quote)
        simulator.set_balance("BTC", initial_base)
        
        # Calculate initial total value
        initial_total = initial_quote + (initial_base * price)
        
        order = simulator.simulate_order(
            symbol="BTC_USDT",
            side=side,
            quantity=quantity,
            price=price,
        )
        
        # Only check conservation for filled orders
        if order.status == SimulatedOrderStatus.FILLED:
            final_quote = simulator.get_balance("USDT").free
            final_base = simulator.get_balance("BTC").free
            
            # Calculate final total value
            final_total = final_quote + (final_base * price)
            
            # Total value should be conserved (within rounding tolerance)
            assert final_total == pytest.approx(initial_total, rel=Decimal("1e-8")), (
                f"Value not conserved: initial={initial_total}, final={final_total}"
            )

    @settings(max_examples=100)
    @given(
        initial_quote=balance_strategy,
        initial_base=balance_strategy,
        quantity=positive_amount_strategy,
        price=price_strategy,
        side=side_strategy,
    )
    def test_ledger_entries_match_balance_changes(
        self,
        initial_quote: Decimal,
        initial_base: Decimal,
        quantity: Decimal,
        price: Decimal,
        side: str,
    ) -> None:
        """
        Property: For any order, ledger entries SHALL accurately reflect
        all balance changes.
        
        **Validates: Requirements 2.2, 2.3**
        """
        quote_amount = price * quantity
        
        # Ensure sufficient balance for the order
        if side == "BUY":
            assume(initial_quote >= quote_amount)
        else:
            assume(initial_base >= quantity)
        
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", initial_quote)
        simulator.set_balance("BTC", initial_base)
        
        # Get ledger entries before order
        ledger_before = len(simulator.get_ledger())
        
        order = simulator.simulate_order(
            symbol="BTC_USDT",
            side=side,
            quantity=quantity,
            price=price,
        )
        
        ledger_after = simulator.get_ledger()
        
        if order.status == SimulatedOrderStatus.FILLED:
            # Should have 2 new entries (one for each currency)
            new_entries = ledger_after[ledger_before:]
            assert len(new_entries) == 2, (
                f"Expected 2 new ledger entries, got {len(new_entries)}"
            )
            
            # Verify entries have correct reference ID
            for entry in new_entries:
                assert entry.reference_id == order.order_id, (
                    f"Ledger entry reference_id mismatch"
                )


# =============================================================================
# Property 15: Dry-Run Isolation
# =============================================================================

class TestDryRunIsolation:
    """
    Property 15: Dry-Run Isolation
    
    *For any* operation in dry_run mode, no real Pionex API mutations SHALL occur.
    
    Since we cannot directly test that no API calls are made without mocking,
    we verify that:
    1. All operations are self-contained within the simulator
    2. Multiple simulator instances are isolated from each other
    3. Reset clears all state without external effects
    
    **Validates: Requirements 2.1, 10.12**
    """

    @settings(max_examples=100)
    @given(
        balance1=balance_strategy,
        balance2=balance_strategy,
    )
    def test_simulator_instances_are_isolated(
        self,
        balance1: Decimal,
        balance2: Decimal,
    ) -> None:
        """
        Property: Multiple DryRunSimulator instances SHALL be completely isolated.
        Operations on one instance SHALL NOT affect another.
        
        **Validates: Requirements 10.12**
        """
        sim1 = DryRunSimulator()
        sim2 = DryRunSimulator()
        
        # Set different balances
        sim1.set_balance("USDT", balance1)
        sim2.set_balance("USDT", balance2)
        
        # Verify isolation
        assert sim1.get_balance("USDT").free == balance1, (
            f"Simulator 1 balance incorrect"
        )
        assert sim2.get_balance("USDT").free == balance2, (
            f"Simulator 2 balance incorrect"
        )
        
        # Modify sim1, verify sim2 unchanged
        if balance1 > Decimal("100"):
            sim1.set_balance("USDT", balance1 - Decimal("100"))
            assert sim2.get_balance("USDT").free == balance2, (
                f"Simulator 2 affected by changes to Simulator 1"
            )

    @settings(max_examples=100)
    @given(
        initial_balance=balance_strategy,
        quantity=positive_amount_strategy,
        price=price_strategy,
    )
    def test_simulated_orders_do_not_persist_after_reset(
        self,
        initial_balance: Decimal,
        quantity: Decimal,
        price: Decimal,
    ) -> None:
        """
        Property: After reset, all simulated state SHALL be cleared.
        No orders, balances, or trades SHALL persist.
        
        **Validates: Requirements 10.12**
        """
        quote_amount = price * quantity
        assume(initial_balance >= quote_amount)
        
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", initial_balance)
        simulator.set_balance("BTC", Decimal("0"))
        
        # Execute an order
        simulator.simulate_order(
            symbol="BTC_USDT",
            side="BUY",
            quantity=quantity,
            price=price,
        )
        
        # Verify state exists
        assert len(simulator.get_orders()) > 0, "Should have orders before reset"
        assert len(simulator.get_trades()) > 0, "Should have trades before reset"
        
        # Reset
        simulator.reset()
        
        # Verify all state cleared
        assert len(simulator.get_all_balances()) == 0, (
            "Balances should be cleared after reset"
        )
        assert len(simulator.get_orders()) == 0, (
            "Orders should be cleared after reset"
        )
        assert len(simulator.get_trades()) == 0, (
            "Trades should be cleared after reset"
        )
        assert len(simulator.get_ledger()) == 0, (
            "Ledger should be cleared after reset"
        )
        assert len(simulator.get_all_bots()) == 0, (
            "Bots should be cleared after reset"
        )

    @settings(max_examples=100)
    @given(
        initial_balance=balance_strategy,
        investment=positive_amount_strategy,
    )
    def test_simulated_bots_do_not_persist_after_reset(
        self,
        initial_balance: Decimal,
        investment: Decimal,
    ) -> None:
        """
        Property: After reset, all simulated bots SHALL be cleared.
        
        **Validates: Requirements 10.12**
        """
        assume(initial_balance >= investment)
        
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", initial_balance)
        
        # Create a bot
        simulator.simulate_bot_creation(
            symbol="BTC_USDT",
            bot_type="GRID",
            investment=investment,
        )
        
        # Verify bot exists
        assert len(simulator.get_all_bots()) > 0, "Should have bots before reset"
        
        # Reset
        simulator.reset()
        
        # Verify bots cleared
        assert len(simulator.get_all_bots()) == 0, (
            "Bots should be cleared after reset"
        )

    @settings(max_examples=100)
    @given(
        initial_balance=balance_strategy,
        investment=positive_amount_strategy,
    )
    def test_bot_operations_are_simulated(
        self,
        initial_balance: Decimal,
        investment: Decimal,
    ) -> None:
        """
        Property: Bot creation and stop operations SHALL only affect
        simulated state, not external systems.
        
        We verify this by checking that:
        1. Bot IDs are generated locally (start with "BOT-")
        2. Balance changes are tracked in the ledger
        3. Operations are reversible (stop returns funds)
        
        **Validates: Requirements 10.12**
        """
        assume(initial_balance >= investment)
        
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", initial_balance)
        
        # Create bot
        bot = simulator.simulate_bot_creation(
            symbol="BTC_USDT",
            bot_type="GRID",
            investment=investment,
        )
        
        # Verify simulated bot ID format
        assert bot.bot_id.startswith("BOT-"), (
            f"Simulated bot ID should start with 'BOT-', got {bot.bot_id}"
        )
        
        # Verify balance locked
        balance_after_create = simulator.get_balance("USDT")
        assert balance_after_create.free == initial_balance - investment, (
            "Free balance should decrease by investment"
        )
        assert balance_after_create.locked == investment, (
            "Locked balance should equal investment"
        )
        
        # Stop bot
        simulator.simulate_bot_stop(bot.bot_id)
        
        # Verify balance restored
        balance_after_stop = simulator.get_balance("USDT")
        assert balance_after_stop.free == initial_balance, (
            "Free balance should be restored after bot stop"
        )
        assert balance_after_stop.locked == Decimal("0"), (
            "Locked balance should be zero after bot stop"
        )

    @settings(max_examples=100)
    @given(
        initial_balance=balance_strategy,
        quantity=positive_amount_strategy,
        price=price_strategy,
    )
    def test_order_ids_are_simulated(
        self,
        initial_balance: Decimal,
        quantity: Decimal,
        price: Decimal,
    ) -> None:
        """
        Property: Order IDs SHALL be generated locally with "SIM-" prefix,
        indicating they are simulated and not from real API.
        
        **Validates: Requirements 2.1, 10.12**
        """
        quote_amount = price * quantity
        assume(initial_balance >= quote_amount)
        
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", initial_balance)
        
        order = simulator.simulate_order(
            symbol="BTC_USDT",
            side="BUY",
            quantity=quantity,
            price=price,
        )
        
        # Verify simulated order ID format
        assert order.order_id.startswith("SIM-"), (
            f"Simulated order ID should start with 'SIM-', got {order.order_id}"
        )

    @settings(max_examples=100)
    @given(
        initial_balance=balance_strategy,
        quantity=positive_amount_strategy,
        price=price_strategy,
    )
    def test_trade_ids_are_simulated(
        self,
        initial_balance: Decimal,
        quantity: Decimal,
        price: Decimal,
    ) -> None:
        """
        Property: Trade IDs SHALL be generated locally with "TRD-" prefix,
        indicating they are simulated and not from real API.
        
        **Validates: Requirements 2.1, 10.12**
        """
        quote_amount = price * quantity
        assume(initial_balance >= quote_amount)
        
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", initial_balance)
        
        simulator.simulate_order(
            symbol="BTC_USDT",
            side="BUY",
            quantity=quantity,
            price=price,
        )
        
        trades = simulator.get_trades()
        assert len(trades) > 0, "Should have trades after order"
        
        for trade in trades:
            assert trade.trade_id.startswith("TRD-"), (
                f"Simulated trade ID should start with 'TRD-', got {trade.trade_id}"
            )


class TestBalanceLedgerConsistency:
    """
    Additional consistency tests for balance ledger.
    
    These tests verify that the balance ledger maintains consistency
    across various operations.
    
    **Validates: Requirements 2.2, 2.3**
    """

    @settings(max_examples=100)
    @given(
        initial_balance=balance_strategy,
        quantity=positive_amount_strategy,
        price=price_strategy,
    )
    def test_ledger_balance_after_matches_actual_balance(
        self,
        initial_balance: Decimal,
        quantity: Decimal,
        price: Decimal,
    ) -> None:
        """
        Property: The balance_after field in ledger entries SHALL match
        the actual balance at that point in time.
        
        **Validates: Requirements 2.2, 2.3**
        """
        quote_amount = price * quantity
        assume(initial_balance >= quote_amount)
        
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", initial_balance)
        simulator.set_balance("BTC", Decimal("0"))
        
        simulator.simulate_order(
            symbol="BTC_USDT",
            side="BUY",
            quantity=quantity,
            price=price,
        )
        
        # Get final balances
        final_usdt = simulator.get_balance("USDT").free
        final_btc = simulator.get_balance("BTC").free
        
        # Get last ledger entries for each currency
        ledger = simulator.get_ledger()
        usdt_entries = [e for e in ledger if e.currency == "USDT"]
        btc_entries = [e for e in ledger if e.currency == "BTC"]
        
        if usdt_entries:
            last_usdt_entry = usdt_entries[-1]
            assert last_usdt_entry.balance_after == final_usdt, (
                f"USDT ledger balance_after ({last_usdt_entry.balance_after}) "
                f"doesn't match actual balance ({final_usdt})"
            )
        
        if btc_entries:
            last_btc_entry = btc_entries[-1]
            assert last_btc_entry.balance_after == final_btc, (
                f"BTC ledger balance_after ({last_btc_entry.balance_after}) "
                f"doesn't match actual balance ({final_btc})"
            )

    @settings(max_examples=100)
    @given(
        initial_balance=balance_strategy,
    )
    def test_ledger_changes_sum_to_final_balance(
        self,
        initial_balance: Decimal,
    ) -> None:
        """
        Property: The sum of all ledger changes for a currency SHALL equal
        the final balance.
        
        **Validates: Requirements 2.2, 2.3**
        """
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", initial_balance)
        
        # Get ledger and sum changes
        ledger = simulator.get_ledger()
        usdt_changes = sum(
            (e.change for e in ledger if e.currency == "USDT"),
            Decimal("0"),
        )
        
        # Final balance should equal sum of changes
        final_balance = simulator.get_balance("USDT").free
        assert final_balance == usdt_changes, (
            f"Sum of ledger changes ({usdt_changes}) doesn't equal "
            f"final balance ({final_balance})"
        )
