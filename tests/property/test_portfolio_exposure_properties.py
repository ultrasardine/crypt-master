"""
Property-based tests for Bot Portfolio Inclusion.

Feature: pionex-trading-bot
Property 14: Bot Portfolio Inclusion

These tests use the hypothesis library to verify that portfolio exposure
calculations correctly include all active bot invested amounts.

**Validates: Requirements 10.10**
"""

from decimal import Decimal

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from lib.simulation import DryRunSimulator, SimulatedBotStatus

# =============================================================================
# Custom Strategies for Portfolio Exposure
# =============================================================================

# Strategy for valid investment amounts (positive Decimal)
investment_strategy = st.decimals(
    min_value=Decimal("10.00"),
    max_value=Decimal("1000000.00"),
    allow_nan=False,
    allow_infinity=False,
    places=2,
)

# Strategy for number of bots to create
num_bots_strategy = st.integers(min_value=1, max_value=10)

# Strategy for bot types
bot_type_strategy = st.sampled_from(["GRID", "DCA"])

# Strategy for trading symbols
symbol_strategy = st.sampled_from(
    [
        "BTC_USDT",
        "ETH_USDT",
        "SOL_USDT",
        "XRP_USDT",
        "ADA_USDT",
    ]
)

# Strategy for initial balance
balance_strategy = st.decimals(
    min_value=Decimal("10000.00"),
    max_value=Decimal("10000000.00"),
    allow_nan=False,
    allow_infinity=False,
    places=2,
)


# =============================================================================
# Property 14: Bot Portfolio Inclusion
# =============================================================================


class TestBotPortfolioInclusion:
    """
    Property 14: Bot Portfolio Inclusion

    *For any* exposure calculation, total SHALL include all active bot
    invested_amounts.

    The portfolio exposure calculation must:
    1. Include all active bot investments in the total
    2. Exclude stopped bot investments from the total
    3. Correctly sum multiple bot investments
    4. Handle bot creation and stopping correctly

    **Validates: Requirements 10.10**
    """

    @settings(max_examples=20)
    @given(
        initial_balance=balance_strategy,
        investment=investment_strategy,
        bot_type=bot_type_strategy,
        symbol=symbol_strategy,
    )
    def test_single_bot_included_in_allocation(
        self,
        initial_balance: Decimal,
        investment: Decimal,
        bot_type: str,
        symbol: str,
    ) -> None:
        """
        Property: For any single active bot, its invested_amount SHALL be
        included in the total bot allocation.

        **Validates: Requirements 10.10**
        """
        # Ensure investment is less than balance
        assume(investment < initial_balance)

        simulator = DryRunSimulator()
        simulator.set_balance("USDT", initial_balance)

        # Create a bot
        bot = simulator.simulate_bot_creation(
            symbol=symbol,
            bot_type=bot_type,
            investment=investment,
        )

        # Get total allocation
        total_allocation = simulator.get_bot_allocation()

        # Verify the bot's investment is included
        assert total_allocation == investment, (
            f"Bot allocation {total_allocation} should equal invested amount {investment}"
        )

        # Verify the bot is active
        assert bot.status == SimulatedBotStatus.ACTIVE

    @settings(max_examples=20)
    @given(
        initial_balance=balance_strategy,
        investments=st.lists(
            investment_strategy,
            min_size=2,
            max_size=5,
        ),
    )
    def test_multiple_bots_summed_in_allocation(
        self,
        initial_balance: Decimal,
        investments: list[Decimal],
    ) -> None:
        """
        Property: For any set of active bots, the total allocation SHALL
        equal the sum of all invested_amounts.

        **Validates: Requirements 10.10**
        """
        # Ensure total investments don't exceed balance
        total_investment = sum(investments)
        assume(total_investment < initial_balance)

        simulator = DryRunSimulator()
        simulator.set_balance("USDT", initial_balance)

        symbols = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "XRP_USDT", "ADA_USDT"]

        # Create multiple bots
        for i, investment in enumerate(investments):
            symbol = symbols[i % len(symbols)]
            simulator.simulate_bot_creation(
                symbol=symbol,
                bot_type="GRID" if i % 2 == 0 else "DCA",
                investment=investment,
            )

        # Get total allocation
        total_allocation = simulator.get_bot_allocation()

        # Verify total equals sum of all investments
        expected_total = sum(investments)
        assert total_allocation == expected_total, (
            f"Total allocation {total_allocation} should equal sum of investments {expected_total}"
        )

    @settings(max_examples=20)
    @given(
        initial_balance=balance_strategy,
        investment=investment_strategy,
    )
    def test_stopped_bot_excluded_from_allocation(
        self,
        initial_balance: Decimal,
        investment: Decimal,
    ) -> None:
        """
        Property: For any stopped bot, its invested_amount SHALL NOT be
        included in the total bot allocation.

        **Validates: Requirements 10.10**
        """
        assume(investment < initial_balance)

        simulator = DryRunSimulator()
        simulator.set_balance("USDT", initial_balance)

        # Create and then stop a bot
        bot = simulator.simulate_bot_creation(
            symbol="BTC_USDT",
            bot_type="GRID",
            investment=investment,
        )

        # Verify allocation includes the bot
        assert simulator.get_bot_allocation() == investment

        # Stop the bot
        simulator.simulate_bot_stop(bot.bot_id)

        # Verify allocation no longer includes the stopped bot
        total_allocation = simulator.get_bot_allocation()
        assert total_allocation == Decimal("0"), (
            f"Stopped bot should not be in allocation, got {total_allocation}"
        )

    @settings(max_examples=20)
    @given(
        initial_balance=balance_strategy,
        investments=st.lists(
            investment_strategy,
            min_size=2,
            max_size=5,
        ),
        stop_indices=st.lists(
            st.integers(min_value=0, max_value=4),
            min_size=0,
            max_size=3,
            unique=True,
        ),
    )
    def test_mixed_active_stopped_bots(
        self,
        initial_balance: Decimal,
        investments: list[Decimal],
        stop_indices: list[int],
    ) -> None:
        """
        Property: For any mix of active and stopped bots, the total allocation
        SHALL equal the sum of only active bot invested_amounts.

        **Validates: Requirements 10.10**
        """
        # Filter stop_indices to valid range
        stop_indices = [i for i in stop_indices if i < len(investments)]

        # Ensure total investments don't exceed balance
        total_investment = sum(investments)
        assume(total_investment < initial_balance)

        simulator = DryRunSimulator()
        simulator.set_balance("USDT", initial_balance)

        symbols = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "XRP_USDT", "ADA_USDT"]
        bots = []

        # Create all bots
        for i, investment in enumerate(investments):
            symbol = symbols[i % len(symbols)]
            bot = simulator.simulate_bot_creation(
                symbol=symbol,
                bot_type="GRID",
                investment=investment,
            )
            bots.append((bot, investment))

        # Stop some bots
        for i in stop_indices:
            if i < len(bots):
                simulator.simulate_bot_stop(bots[i][0].bot_id)

        # Calculate expected allocation (only active bots)
        expected_allocation = sum(inv for j, (_, inv) in enumerate(bots) if j not in stop_indices)

        # Get actual allocation
        total_allocation = simulator.get_bot_allocation()

        assert total_allocation == expected_allocation, (
            f"Total allocation {total_allocation} should equal "
            f"sum of active bot investments {expected_allocation}"
        )

    @settings(max_examples=20)
    @given(
        initial_balance=balance_strategy,
        investment=investment_strategy,
    )
    def test_allocation_deterministic(
        self,
        initial_balance: Decimal,
        investment: Decimal,
    ) -> None:
        """
        Property: For any portfolio state, calling get_bot_allocation()
        multiple times SHALL return identical results.

        **Validates: Requirements 10.10**
        """
        assume(investment < initial_balance)

        simulator = DryRunSimulator()
        simulator.set_balance("USDT", initial_balance)

        simulator.simulate_bot_creation(
            symbol="BTC_USDT",
            bot_type="GRID",
            investment=investment,
        )

        # Call multiple times
        result1 = simulator.get_bot_allocation()
        result2 = simulator.get_bot_allocation()
        result3 = simulator.get_bot_allocation()

        assert result1 == result2 == result3, (
            f"Allocation should be deterministic: {result1}, {result2}, {result3}"
        )

    @settings(max_examples=20)
    @given(
        initial_balance=balance_strategy,
    )
    def test_empty_portfolio_zero_allocation(
        self,
        initial_balance: Decimal,
    ) -> None:
        """
        Property: For any portfolio with no bots, the total allocation
        SHALL be zero.

        **Validates: Requirements 10.10**
        """
        simulator = DryRunSimulator()
        simulator.set_balance("USDT", initial_balance)

        # No bots created
        total_allocation = simulator.get_bot_allocation()

        assert total_allocation == Decimal("0"), (
            f"Empty portfolio should have zero allocation, got {total_allocation}"
        )


class TestBotPortfolioInclusionEdgeCases:
    """
    Edge case tests for bot portfolio inclusion.

    **Validates: Requirements 10.10**
    """

    @settings(max_examples=20)
    @given(
        initial_balance=balance_strategy,
        investment=investment_strategy,
    )
    def test_allocation_after_bot_value_update(
        self,
        initial_balance: Decimal,
        investment: Decimal,
    ) -> None:
        """
        Property: After updating bot value, the invested_amount (not current_value)
        SHALL be used for allocation calculation.

        **Validates: Requirements 10.10**
        """
        assume(investment < initial_balance)

        simulator = DryRunSimulator()
        simulator.set_balance("USDT", initial_balance)

        bot = simulator.simulate_bot_creation(
            symbol="BTC_USDT",
            bot_type="GRID",
            investment=investment,
        )

        # Update bot value (simulating market movement)
        new_value = investment * Decimal("1.5")  # 50% profit
        simulator.update_bot_value(bot.bot_id, new_value)

        # Allocation should still be based on invested amount
        total_allocation = simulator.get_bot_allocation()

        assert total_allocation == investment, (
            f"Allocation {total_allocation} should be based on "
            f"invested amount {investment}, not current value {new_value}"
        )

    @settings(max_examples=20)
    @given(
        initial_balance=balance_strategy,
        investments=st.lists(
            investment_strategy,
            min_size=1,
            max_size=5,
        ),
    )
    def test_allocation_equals_sum_of_active_bots(
        self,
        initial_balance: Decimal,
        investments: list[Decimal],
    ) -> None:
        """
        Property: get_bot_allocation() SHALL always equal the sum of
        invested amounts for all active bots.

        **Validates: Requirements 10.10**
        """
        total_investment = sum(investments)
        assume(total_investment < initial_balance)

        simulator = DryRunSimulator()
        simulator.set_balance("USDT", initial_balance)

        symbols = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "XRP_USDT", "ADA_USDT"]

        for i, investment in enumerate(investments):
            symbol = symbols[i % len(symbols)]
            simulator.simulate_bot_creation(
                symbol=symbol,
                bot_type="GRID",
                investment=investment,
            )

        # Get active bots and sum their investments
        active_bots = simulator.get_active_bots()
        expected_sum = sum(bot.invested for bot in active_bots)

        # Get allocation
        total_allocation = simulator.get_bot_allocation()

        assert total_allocation == expected_sum, (
            f"Allocation {total_allocation} should equal "
            f"sum of active bot investments {expected_sum}"
        )

    @settings(max_examples=20)
    @given(
        initial_balance=balance_strategy,
        investment1=investment_strategy,
        investment2=investment_strategy,
    )
    def test_allocation_order_independent(
        self,
        initial_balance: Decimal,
        investment1: Decimal,
        investment2: Decimal,
    ) -> None:
        """
        Property: The order of bot creation SHALL NOT affect the total
        allocation calculation.

        **Validates: Requirements 10.10**
        """
        assume(investment1 + investment2 < initial_balance)

        # Create bots in order 1, 2
        sim1 = DryRunSimulator()
        sim1.set_balance("USDT", initial_balance)
        sim1.simulate_bot_creation("BTC_USDT", "GRID", investment1)
        sim1.simulate_bot_creation("ETH_USDT", "DCA", investment2)
        allocation1 = sim1.get_bot_allocation()

        # Create bots in order 2, 1
        sim2 = DryRunSimulator()
        sim2.set_balance("USDT", initial_balance)
        sim2.simulate_bot_creation("ETH_USDT", "DCA", investment2)
        sim2.simulate_bot_creation("BTC_USDT", "GRID", investment1)
        allocation2 = sim2.get_bot_allocation()

        assert allocation1 == allocation2, (
            f"Allocation should be order-independent: {allocation1} vs {allocation2}"
        )
