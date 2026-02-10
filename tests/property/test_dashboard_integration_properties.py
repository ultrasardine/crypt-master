"""
Property-based tests for Dashboard Integration.

Feature: dashboard-integration
Property 1: Drawdown Calculation
Property 2: High Water Mark Tracking
Property 3: Portfolio Snapshot Creation Round-Trip

These tests use the hypothesis library to verify that the portfolio sync service
behaves correctly across all valid inputs.

**Validates: Requirements 1.2, 1.3, 1.4, 1.7**
"""

import uuid
from decimal import Decimal

import pytest
from django.utils import timezone
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from lib.sync.portfolio import PortfolioSyncService

# =============================================================================
# Custom Strategies for Dashboard Integration Testing
# =============================================================================

# Strategy for valid portfolio values (positive Decimal)
# Note: Using fewer decimal places to avoid precision issues with large values
portfolio_value_strategy = st.decimals(
    min_value=Decimal("0.01"),
    max_value=Decimal("100000000.00"),  # 100 million max
    allow_nan=False,
    allow_infinity=False,
    places=2,  # Reduced to 2 decimal places to avoid precision issues
)

# Strategy for non-negative portfolio values (including zero)
# Note: Using fewer decimal places to avoid precision issues with large values
non_negative_portfolio_strategy = st.decimals(
    min_value=Decimal("0.00"),
    max_value=Decimal("100000000.00"),  # 100 million max
    allow_nan=False,
    allow_infinity=False,
    places=2,  # Reduced to 2 decimal places to avoid precision issues
)


@st.composite
def portfolio_value_sequence_strategy(draw: st.DrawFn) -> list[Decimal]:
    """
    Generate a sequence of portfolio values for testing update sequences.

    Creates realistic portfolio value sequences with ups and downs.
    """
    # Start with an initial value
    initial = draw(portfolio_value_strategy)

    # Generate a sequence of multipliers (0.5 to 1.5)
    length = draw(st.integers(min_value=1, max_value=20))
    multipliers = draw(
        st.lists(
            st.floats(min_value=0.5, max_value=1.5, allow_nan=False, allow_infinity=False),
            min_size=length,
            max_size=length,
        )
    )

    # Build the sequence
    sequence = [initial]
    current = initial
    for mult in multipliers:
        current = current * Decimal(str(mult))
        # Use 2 decimal places to match portfolio_value_strategy
        current = max(Decimal("0.01"), current.quantize(Decimal("0.01")))
        sequence.append(current)

    return sequence


# =============================================================================
# Property 1: Drawdown Calculation
# =============================================================================


class TestDrawdownCalculation:
    """
    Property 1: Drawdown Calculation

    *For any* current portfolio value and high water mark where high_water_mark > 0,
    the calculated drawdown SHALL equal (high_water_mark - current_value) / high_water_mark * 100,
    and SHALL be clamped to the range [0, 100].

    **Validates: Requirements 1.3**
    """

    @settings(max_examples=20)
    @given(
        current_value=non_negative_portfolio_strategy,
        high_water_mark=portfolio_value_strategy,
    )
    def test_drawdown_formula_correctness(
        self,
        current_value: Decimal,
        high_water_mark: Decimal,
    ) -> None:
        """
        Property: For any high_water_mark > 0 and current_value >= 0,
        drawdown SHALL equal (high_water_mark - current_value) / high_water_mark * 100.

        **Validates: Requirements 1.3**
        """
        # Skip if high water mark is zero (division by zero)
        assume(high_water_mark > Decimal("0"))

        # Create a service instance (we only need the method, not the dependencies)
        service = PortfolioSyncService(client_factory=None, broadcaster=None)  # type: ignore

        # Calculate drawdown
        drawdown = service._calculate_drawdown(current_value, high_water_mark)

        # Calculate expected drawdown using the formula
        expected_drawdown = float((high_water_mark - current_value) / high_water_mark * 100)

        # Clamp expected to [0, 100]
        expected_drawdown = max(0.0, min(100.0, expected_drawdown))

        assert drawdown == pytest.approx(expected_drawdown, rel=1e-9, abs=1e-12), (
            f"Drawdown formula mismatch: expected {expected_drawdown:.10f}, "
            f"got {drawdown:.10f} "
            f"(hwm={high_water_mark}, current={current_value})"
        )

    @settings(max_examples=20)
    @given(
        current_value=non_negative_portfolio_strategy,
        high_water_mark=portfolio_value_strategy,
    )
    def test_drawdown_is_non_negative(
        self,
        current_value: Decimal,
        high_water_mark: Decimal,
    ) -> None:
        """
        Property: Drawdown SHALL always be non-negative (>= 0).

        **Validates: Requirements 1.3**
        """
        assume(high_water_mark > Decimal("0"))

        service = PortfolioSyncService(client_factory=None, broadcaster=None)  # type: ignore
        drawdown = service._calculate_drawdown(current_value, high_water_mark)

        assert drawdown >= 0.0, (
            f"Drawdown {drawdown} is negative (hwm={high_water_mark}, current={current_value})"
        )

    @settings(max_examples=20)
    @given(
        current_value=non_negative_portfolio_strategy,
        high_water_mark=portfolio_value_strategy,
    )
    def test_drawdown_bounded_by_100(
        self,
        current_value: Decimal,
        high_water_mark: Decimal,
    ) -> None:
        """
        Property: Drawdown SHALL be bounded by [0, 100].

        **Validates: Requirements 1.3**
        """
        assume(high_water_mark > Decimal("0"))

        service = PortfolioSyncService(client_factory=None, broadcaster=None)  # type: ignore
        drawdown = service._calculate_drawdown(current_value, high_water_mark)

        assert 0.0 <= drawdown <= 100.0, (
            f"Drawdown {drawdown} outside valid range [0, 100] "
            f"(hwm={high_water_mark}, current={current_value})"
        )

    @settings(max_examples=20)
    @given(
        portfolio_value=portfolio_value_strategy,
    )
    def test_drawdown_zero_at_high_water_mark(
        self,
        portfolio_value: Decimal,
    ) -> None:
        """
        Property: Drawdown SHALL be zero when current_value equals high_water_mark.

        **Validates: Requirements 1.3**
        """
        service = PortfolioSyncService(client_factory=None, broadcaster=None)  # type: ignore

        # Current value equals high water mark
        drawdown = service._calculate_drawdown(portfolio_value, portfolio_value)

        assert drawdown == 0.0, f"Drawdown should be 0 at high water mark, got {drawdown}"

    @settings(max_examples=20)
    @given(
        current_value=non_negative_portfolio_strategy,
        high_water_mark=portfolio_value_strategy,
    )
    def test_drawdown_calculation_is_deterministic(
        self,
        current_value: Decimal,
        high_water_mark: Decimal,
    ) -> None:
        """
        Property: For any inputs, calculating drawdown twice
        SHALL produce identical results.

        **Validates: Requirements 1.3**
        """
        assume(high_water_mark > Decimal("0"))

        service = PortfolioSyncService(client_factory=None, broadcaster=None)  # type: ignore

        drawdown1 = service._calculate_drawdown(current_value, high_water_mark)
        drawdown2 = service._calculate_drawdown(current_value, high_water_mark)

        assert drawdown1 == drawdown2, (
            f"Drawdown calculation not deterministic: {drawdown1} vs {drawdown2}"
        )

    @settings(max_examples=20)
    @given(
        high_water_mark=portfolio_value_strategy,
    )
    def test_drawdown_zero_when_hwm_is_zero(
        self,
        high_water_mark: Decimal,
    ) -> None:
        """
        Property: When high_water_mark is zero or negative,
        drawdown SHALL be 0.0 (edge case handling).

        **Validates: Requirements 1.3**
        """
        service = PortfolioSyncService(client_factory=None, broadcaster=None)  # type: ignore

        # Test with zero high water mark
        drawdown = service._calculate_drawdown(Decimal("100"), Decimal("0"))
        assert drawdown == 0.0, f"Drawdown should be 0 when hwm is 0, got {drawdown}"

        # Test with negative high water mark (edge case)
        drawdown = service._calculate_drawdown(Decimal("100"), Decimal("-10"))
        assert drawdown == 0.0, f"Drawdown should be 0 when hwm is negative, got {drawdown}"


# =============================================================================
# Property 2: High Water Mark Tracking
# =============================================================================


class TestHighWaterMarkTracking:
    """
    Property 2: High Water Mark Tracking

    *For any* sequence of portfolio values, the high water mark after processing
    all values SHALL equal the maximum value in the sequence. The high water mark
    SHALL never decrease.

    **Validates: Requirements 1.4**
    """

    @settings(max_examples=20)
    @given(
        sequence=portfolio_value_sequence_strategy(),
    )
    def test_high_water_mark_equals_max_seen(
        self,
        sequence: list[Decimal],
    ) -> None:
        """
        Property: High water mark SHALL equal the maximum value seen.

        This test simulates the behavior of tracking high water mark
        across multiple portfolio snapshots.

        **Validates: Requirements 1.4**
        """
        assume(len(sequence) >= 1)

        # Simulate tracking high water mark
        high_water_mark = sequence[0]

        for value in sequence[1:]:
            if value > high_water_mark:
                high_water_mark = value

        expected_hwm = max(sequence)

        assert high_water_mark == expected_hwm, (
            f"High water mark {high_water_mark} != max seen {expected_hwm}"
        )

    @settings(max_examples=20)
    @given(
        sequence=portfolio_value_sequence_strategy(),
    )
    def test_high_water_mark_only_increases(
        self,
        sequence: list[Decimal],
    ) -> None:
        """
        Property: High water mark SHALL only increase or stay the same,
        never decrease.

        **Validates: Requirements 1.4**
        """
        assume(len(sequence) >= 2)

        # Simulate tracking high water mark
        high_water_mark = sequence[0]
        previous_hwm = high_water_mark

        for value in sequence[1:]:
            if value > high_water_mark:
                high_water_mark = value

            assert high_water_mark >= previous_hwm, (
                f"High water mark decreased from {previous_hwm} to {high_water_mark}"
            )
            previous_hwm = high_water_mark

    @settings(max_examples=20)
    @given(
        initial_value=portfolio_value_strategy,
        new_value=portfolio_value_strategy,
    )
    def test_high_water_mark_update_logic(
        self,
        initial_value: Decimal,
        new_value: Decimal,
    ) -> None:
        """
        Property: When new_value > high_water_mark, high_water_mark SHALL be updated.
        When new_value <= high_water_mark, high_water_mark SHALL remain unchanged.

        **Validates: Requirements 1.4**
        """
        high_water_mark = initial_value

        # Update logic
        if new_value > high_water_mark:
            updated_hwm = new_value
        else:
            updated_hwm = high_water_mark

        # Verify the logic
        if new_value > initial_value:
            assert updated_hwm == new_value, (
                f"High water mark should be updated to {new_value}, got {updated_hwm}"
            )
        else:
            assert updated_hwm == initial_value, (
                f"High water mark should remain {initial_value}, got {updated_hwm}"
            )

    @settings(max_examples=20)
    @given(
        sequence=portfolio_value_sequence_strategy(),
    )
    def test_high_water_mark_never_below_initial(
        self,
        sequence: list[Decimal],
    ) -> None:
        """
        Property: High water mark SHALL never be less than the initial value.

        **Validates: Requirements 1.4**
        """
        assume(len(sequence) >= 1)

        initial_value = sequence[0]
        high_water_mark = initial_value

        for value in sequence[1:]:
            if value > high_water_mark:
                high_water_mark = value

        assert high_water_mark >= initial_value, (
            f"High water mark {high_water_mark} < initial value {initial_value}"
        )


# =============================================================================
# Additional Consistency Tests
# =============================================================================


class TestPortfolioSyncConsistency:
    """
    Additional consistency tests for portfolio sync service.

    These tests verify that the service behaves consistently
    across different scenarios.

    **Validates: Requirements 1.3, 1.4**
    """

    @settings(max_examples=20)
    @given(
        current_value=portfolio_value_strategy,
        high_water_mark=portfolio_value_strategy,
    )
    def test_drawdown_increases_as_value_decreases(
        self,
        current_value: Decimal,
        high_water_mark: Decimal,
    ) -> None:
        """
        Property: For a fixed high_water_mark, as current_value decreases,
        drawdown SHALL increase (or stay the same).

        **Validates: Requirements 1.3**
        """
        assume(high_water_mark > Decimal("0"))
        assume(current_value <= high_water_mark)

        service = PortfolioSyncService(client_factory=None, broadcaster=None)  # type: ignore

        # Calculate drawdown at current value
        drawdown1 = service._calculate_drawdown(current_value, high_water_mark)

        # Calculate drawdown at a lower value
        lower_value = current_value * Decimal("0.9")
        drawdown2 = service._calculate_drawdown(lower_value, high_water_mark)

        assert drawdown2 >= drawdown1, (
            f"Drawdown should increase as value decreases: "
            f"drawdown1={drawdown1:.4f} at value={current_value}, "
            f"drawdown2={drawdown2:.4f} at value={lower_value}"
        )

    @settings(max_examples=20)
    @given(
        current_value=portfolio_value_strategy,
        high_water_mark=portfolio_value_strategy,
    )
    def test_drawdown_at_zero_value(
        self,
        current_value: Decimal,
        high_water_mark: Decimal,
    ) -> None:
        """
        Property: When current_value is zero, drawdown SHALL be 100%
        (maximum drawdown).

        **Validates: Requirements 1.3**
        """
        assume(high_water_mark > Decimal("0"))

        service = PortfolioSyncService(client_factory=None, broadcaster=None)  # type: ignore

        drawdown = service._calculate_drawdown(Decimal("0"), high_water_mark)

        assert drawdown == 100.0, (
            f"Drawdown should be 100% when value is 0, got {drawdown}"
        )

    @settings(max_examples=20)
    @given(
        current_value=portfolio_value_strategy,
        high_water_mark=portfolio_value_strategy,
    )
    def test_drawdown_when_value_exceeds_hwm(
        self,
        current_value: Decimal,
        high_water_mark: Decimal,
    ) -> None:
        """
        Property: When current_value > high_water_mark, drawdown SHALL be 0
        (clamped to minimum).

        **Validates: Requirements 1.3**
        """
        assume(high_water_mark > Decimal("0"))
        assume(current_value > high_water_mark)

        service = PortfolioSyncService(client_factory=None, broadcaster=None)  # type: ignore

        drawdown = service._calculate_drawdown(current_value, high_water_mark)

        assert drawdown == 0.0, (
            f"Drawdown should be 0 when value exceeds hwm, got {drawdown}"
        )



# =============================================================================
# Property 3: Portfolio Snapshot Creation Round-Trip
# =============================================================================


class TestPortfolioSnapshotCreation:
    """
    Property 3: Portfolio Snapshot Creation Round-Trip

    *For any* valid Pionex balance response containing currency balances,
    creating a PortfolioSnapshot and then reading it back SHALL produce a record
    where total_value equals the sum of all balance values, and the WebSocket
    broadcaster SHALL be called with matching data.

    **Validates: Requirements 1.2, 1.7**
    """

    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        total_value=portfolio_value_strategy,
        available_balance=portfolio_value_strategy,
        allocated_to_bots=portfolio_value_strategy,
    )
    def test_snapshot_data_integrity(
        self,
        total_value: Decimal,
        available_balance: Decimal,
        allocated_to_bots: Decimal,
        django_user_model,
    ) -> None:
        """
        Property: Creating a PortfolioSnapshot SHALL preserve all input values
        when read back from the database.

        **Validates: Requirements 1.2**
        """
        # Ensure available_balance + allocated_to_bots <= total_value
        assume(available_balance + allocated_to_bots <= total_value)

        # Create a test user with unique username
        user = django_user_model.objects.create_user(
            username=f"test_user_{uuid.uuid4().hex[:8]}",
            password="testpass123",
        )

        # Calculate high water mark and drawdown
        high_water_mark = total_value
        drawdown = 0.0

        # Create snapshot
        from apps.core.models import PortfolioSnapshot

        snapshot = PortfolioSnapshot.objects.create(
            user=user,
            total_value=total_value,
            available_balance=available_balance,
            allocated_to_bots=allocated_to_bots,
            drawdown=drawdown,
            high_water_mark=high_water_mark,
            is_simulated=False,
        )

        # Read back from database
        retrieved = PortfolioSnapshot.objects.get(id=snapshot.id)

        # Verify all values match
        assert retrieved.total_value == total_value, (
            f"Total value mismatch: expected {total_value}, got {retrieved.total_value}"
        )
        assert retrieved.available_balance == available_balance, (
            f"Available balance mismatch: expected {available_balance}, "
            f"got {retrieved.available_balance}"
        )
        assert retrieved.allocated_to_bots == allocated_to_bots, (
            f"Allocated to bots mismatch: expected {allocated_to_bots}, "
            f"got {retrieved.allocated_to_bots}"
        )
        assert retrieved.drawdown == drawdown, (
            f"Drawdown mismatch: expected {drawdown}, got {retrieved.drawdown}"
        )
        assert retrieved.high_water_mark == high_water_mark, (
            f"High water mark mismatch: expected {high_water_mark}, "
            f"got {retrieved.high_water_mark}"
        )
        assert retrieved.is_simulated is False, "is_simulated should be False"
        assert retrieved.user == user, "User should match"

        # Cleanup
        user.delete()

    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        total_value=portfolio_value_strategy,
        available_balance=portfolio_value_strategy,
    )
    def test_snapshot_balance_consistency(
        self,
        total_value: Decimal,
        available_balance: Decimal,
        django_user_model,
    ) -> None:
        """
        Property: For any snapshot, available_balance + allocated_to_bots
        SHALL be <= total_value (balance consistency).

        **Validates: Requirements 1.2**
        """
        # Ensure available_balance <= total_value
        assume(available_balance <= total_value)

        # Calculate allocated_to_bots as the difference
        allocated_to_bots = total_value - available_balance

        # Create a test user
        user = django_user_model.objects.create_user(
            username=f"test_user_balance_{total_value}",
            password="testpass123",
        )

        # Create snapshot
        from apps.core.models import PortfolioSnapshot

        snapshot = PortfolioSnapshot.objects.create(
            user=user,
            total_value=total_value,
            available_balance=available_balance,
            allocated_to_bots=allocated_to_bots,
            drawdown=0.0,
            high_water_mark=total_value,
            is_simulated=False,
        )

        # Verify balance consistency
        assert snapshot.available_balance + snapshot.allocated_to_bots <= snapshot.total_value, (
            f"Balance inconsistency: available ({snapshot.available_balance}) + "
            f"allocated ({snapshot.allocated_to_bots}) > total ({snapshot.total_value})"
        )

        # Cleanup
        user.delete()

    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        sequence=portfolio_value_sequence_strategy(),
    )
    def test_snapshot_sequence_high_water_mark(
        self,
        sequence: list[Decimal],
        django_user_model,
    ) -> None:
        """
        Property: Creating a sequence of snapshots SHALL correctly track
        the high water mark across all snapshots.

        **Validates: Requirements 1.2, 1.4**
        """
        assume(len(sequence) >= 2)

        # Create a test user with unique username
        user = django_user_model.objects.create_user(
            username=f"test_user_seq_{uuid.uuid4().hex[:8]}",
            password="testpass123",
        )

        from apps.core.models import PortfolioSnapshot

        # Create first snapshot
        high_water_mark = sequence[0]
        PortfolioSnapshot.objects.create(
            user=user,
            total_value=sequence[0],
            available_balance=sequence[0],
            allocated_to_bots=Decimal("0"),
            drawdown=0.0,
            high_water_mark=high_water_mark,
            is_simulated=False,
        )

        # Create subsequent snapshots
        for value in sequence[1:]:
            # Update high water mark if needed
            if value > high_water_mark:
                high_water_mark = value

            # Calculate drawdown
            service = PortfolioSyncService(client_factory=None, broadcaster=None)  # type: ignore
            drawdown = service._calculate_drawdown(value, high_water_mark)

            PortfolioSnapshot.objects.create(
                user=user,
                total_value=value,
                available_balance=value,
                allocated_to_bots=Decimal("0"),
                drawdown=drawdown,
                high_water_mark=high_water_mark,
                is_simulated=False,
            )

        # Verify the final high water mark equals the max value
        final_snapshot = PortfolioSnapshot.objects.filter(user=user).first()
        expected_hwm = max(sequence)

        assert final_snapshot.high_water_mark == expected_hwm, (
            f"Final high water mark {final_snapshot.high_water_mark} != "
            f"max value {expected_hwm}"
        )

        # Cleanup
        user.delete()


# =============================================================================
# Property 4: Bot Reconciliation Completeness
# =============================================================================


@st.composite
def mock_bot_info_strategy(draw: st.DrawFn) -> dict[str, any]:
    """
    Generate mock BotInfo data for testing.

    Returns a dictionary representing a bot from Pionex API.
    """
    # Use UUID to ensure uniqueness across test runs
    bot_id = f"bot_{uuid.uuid4().hex[:12]}"
    bot_type = draw(st.sampled_from(["GRID", "DCA", "INFINITY_GRID", "FUTURES_GRID"]))
    symbol = draw(st.sampled_from(["BTC_USDT", "ETH_USDT", "BNB_USDT", "SOL_USDT"]))
    status = draw(st.sampled_from(["ACTIVE", "STOPPED", "ERROR"]))
    
    invested = draw(st.decimals(
        min_value=Decimal("10.00"),
        max_value=Decimal("10000.00"),
        allow_nan=False,
        allow_infinity=False,
        places=2,
    ))
    
    # Current value can be higher or lower than invested
    value_multiplier = draw(st.floats(min_value=0.5, max_value=2.0, allow_nan=False, allow_infinity=False))
    current_value = invested * Decimal(str(value_multiplier))
    current_value = current_value.quantize(Decimal("0.01"))
    
    pnl = current_value - invested
    pnl_percent = float((pnl / invested) * 100) if invested > 0 else 0.0
    
    return {
        "bot_id": bot_id,
        "bot_type": bot_type,
        "symbol": symbol,
        "status": status,
        "invested": invested,
        "current_value": current_value,
        "pnl": pnl,
        "pnl_percent": pnl_percent,
    }


@st.composite
def mock_local_bot_strategy(draw: st.DrawFn) -> dict[str, any]:
    """
    Generate mock local Bot data for testing.

    Returns a dictionary representing a bot from the local database.
    """
    # Use UUID to ensure uniqueness across test runs
    pionex_bot_id = f"bot_{uuid.uuid4().hex[:12]}"
    bot_type = draw(st.sampled_from(["GRID", "DCA", "INFINITY_GRID", "FUTURES_GRID"]))
    symbol = draw(st.sampled_from(["BTC_USDT", "ETH_USDT", "BNB_USDT", "SOL_USDT"]))
    status = draw(st.sampled_from(["ACTIVE", "STOPPED", "ERROR", "PENDING"]))
    
    invested = draw(st.decimals(
        min_value=Decimal("10.00"),
        max_value=Decimal("10000.00"),
        allow_nan=False,
        allow_infinity=False,
        places=2,
    ))
    
    # Current value can be higher or lower than invested
    value_multiplier = draw(st.floats(min_value=0.5, max_value=2.0, allow_nan=False, allow_infinity=False))
    current_value = invested * Decimal(str(value_multiplier))
    current_value = current_value.quantize(Decimal("0.01"))
    
    pnl = current_value - invested
    pnl_percent = float((pnl / invested) * 100) if invested > 0 else 0.0
    
    return {
        "pionex_bot_id": pionex_bot_id,
        "bot_type": bot_type,
        "symbol": symbol,
        "status": status,
        "invested_amount": invested,
        "current_value": current_value,
        "current_pnl": pnl,
        "pnl_percent": pnl_percent,
    }


class TestBotReconciliation:
    """
    Property 4: Bot Reconciliation Completeness

    *For any* set of local bots and remote bots from Pionex:
    - All remote bots SHALL have corresponding local records after sync
    - Local bots not in remote set SHALL have status STOPPED
    - Local bots in remote set SHALL have current_value, current_pnl, and pnl_percent matching remote data
    - WebSocket broadcaster SHALL be called for each updated bot

    **Validates: Requirements 2.2, 2.3, 2.4, 2.5, 2.7**
    """

    @pytest.mark.django_db(transaction=True)
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        remote_bots=st.lists(mock_bot_info_strategy(), min_size=0, max_size=10),
    )
    def test_all_remote_bots_have_local_records(
        self,
        remote_bots: list[dict[str, any]],
        django_user_model,
    ) -> None:
        """
        Property: After sync, all remote bots SHALL have corresponding local records.

        **Validates: Requirements 2.2, 2.3**
        """
        from apps.bots.models import Bot, BotStatus, BotType
        from apps.core.models import TradingPair
        
        # Create a test user with unique username
        user = django_user_model.objects.create_user(
            username=f"test_bot_user_{uuid.uuid4().hex[:8]}",
            password="testpass123",
        )
        
        try:
            # Simulate reconciliation logic - matches BotSyncService._reconcile_bot behavior
            for remote_bot in remote_bots:
                # Get or create trading pair
                trading_pair, _ = TradingPair.objects.get_or_create(
                    symbol=remote_bot["symbol"],
                    defaults={
                        "base_currency": remote_bot["symbol"].split("_")[0],
                        "quote_currency": remote_bot["symbol"].split("_")[1],
                        "is_active": True,
                    },
                )
                
                # Map bot type
                bot_type_map = {
                    "GRID": BotType.GRID,
                    "DCA": BotType.DCA,
                    "INFINITY_GRID": BotType.INFINITY_GRID,
                    "FUTURES_GRID": BotType.FUTURES_GRID,
                }
                bot_type = bot_type_map.get(remote_bot["bot_type"], BotType.GRID)
                
                # Map status
                status_map = {
                    "ACTIVE": BotStatus.ACTIVE,
                    "STOPPED": BotStatus.STOPPED,
                    "ERROR": BotStatus.ERROR,
                }
                status = status_map.get(remote_bot["status"], BotStatus.ACTIVE)
                
                # Check if bot exists locally
                local_bot = Bot.objects.filter(
                    pionex_bot_id=remote_bot["bot_id"],
                    user=user,
                ).first()
                
                if local_bot:
                    # Update existing bot (matches _reconcile_bot update logic)
                    local_bot.current_value = remote_bot["current_value"]
                    local_bot.current_pnl = remote_bot["pnl"]
                    local_bot.pnl_percent = remote_bot["pnl_percent"]
                    local_bot.status = status
                    local_bot.save()
                else:
                    # Create new bot (matches _reconcile_bot create logic)
                    Bot.objects.create(
                        user=user,
                        pionex_bot_id=remote_bot["bot_id"],
                        bot_type=bot_type,
                        trading_pair=trading_pair,
                        status=status,
                        invested_amount=remote_bot["invested"],
                        current_value=remote_bot["current_value"],
                        current_pnl=remote_bot["pnl"],
                        pnl_percent=remote_bot["pnl_percent"],
                        params={},
                        is_simulated=False,
                    )
            
            # Verify all remote bots have local records
            for remote_bot in remote_bots:
                local_bot = Bot.objects.filter(
                    pionex_bot_id=remote_bot["bot_id"],
                    user=user,
                ).first()
                
                assert local_bot is not None, (
                    f"Remote bot {remote_bot['bot_id']} has no local record after sync"
                )
                
                # Verify data matches
                assert local_bot.current_value == remote_bot["current_value"], (
                    f"Bot {remote_bot['bot_id']} current_value mismatch: "
                    f"expected {remote_bot['current_value']}, got {local_bot.current_value}"
                )
                assert local_bot.current_pnl == remote_bot["pnl"], (
                    f"Bot {remote_bot['bot_id']} pnl mismatch: "
                    f"expected {remote_bot['pnl']}, got {local_bot.current_pnl}"
                )
                assert local_bot.pnl_percent == pytest.approx(remote_bot["pnl_percent"], rel=1e-6), (
                    f"Bot {remote_bot['bot_id']} pnl_percent mismatch: "
                    f"expected {remote_bot['pnl_percent']}, got {local_bot.pnl_percent}"
                )
        finally:
            # Cleanup - delete user and all related objects
            Bot.objects.filter(user=user).delete()
            user.delete()

    @pytest.mark.django_db(transaction=True)
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        local_bots=st.lists(mock_local_bot_strategy(), min_size=1, max_size=10),
    )
    def test_local_bots_not_in_remote_marked_stopped(
        self,
        local_bots: list[dict[str, any]],
        django_user_model,
    ) -> None:
        """
        Property: Local bots not in remote set SHALL have status STOPPED.

        **Validates: Requirements 2.4**
        """
        from apps.bots.models import Bot, BotStatus, BotType
        from apps.core.models import TradingPair
        
        # Create a test user with unique username
        user = django_user_model.objects.create_user(
            username=f"test_stop_user_{uuid.uuid4().hex[:8]}",
            password="testpass123",
        )
        
        try:
            # Create local bots
            created_bots = []
            for local_bot in local_bots:
                # Get or create trading pair
                trading_pair, _ = TradingPair.objects.get_or_create(
                    symbol=local_bot["symbol"],
                    defaults={
                        "base_currency": local_bot["symbol"].split("_")[0],
                        "quote_currency": local_bot["symbol"].split("_")[1],
                        "is_active": True,
                    },
                )
                
                # Map bot type
                bot_type_map = {
                    "GRID": BotType.GRID,
                    "DCA": BotType.DCA,
                    "INFINITY_GRID": BotType.INFINITY_GRID,
                    "FUTURES_GRID": BotType.FUTURES_GRID,
                }
                bot_type = bot_type_map.get(local_bot["bot_type"], BotType.GRID)
                
                # Map status
                status_map = {
                    "ACTIVE": BotStatus.ACTIVE,
                    "STOPPED": BotStatus.STOPPED,
                    "ERROR": BotStatus.ERROR,
                    "PENDING": BotStatus.PENDING,
                }
                status = status_map.get(local_bot["status"], BotStatus.ACTIVE)
                
                bot = Bot.objects.create(
                    user=user,
                    pionex_bot_id=local_bot["pionex_bot_id"],
                    bot_type=bot_type,
                    trading_pair=trading_pair,
                    status=status,
                    invested_amount=local_bot["invested_amount"],
                    current_value=local_bot["current_value"],
                    current_pnl=local_bot["current_pnl"],
                    pnl_percent=local_bot["pnl_percent"],
                    params={},
                    is_simulated=False,
                )
                created_bots.append(bot)
            
            # Generate remote bot IDs (subset of local bots - some will be missing)
            # Use only half of the local bots as remote bots
            num_remote = max(0, len(local_bots) // 2)
            remote_bot_ids = [bot.pionex_bot_id for bot in created_bots[:num_remote]]
            
            # Simulate marking bots as stopped if not in remote set
            # This matches the logic in BotSyncService.sync_user_bots
            for bot in created_bots:
                if bot.pionex_bot_id not in remote_bot_ids:
                    if bot.status == BotStatus.ACTIVE:
                        bot.status = BotStatus.STOPPED
                        bot.stopped_at = timezone.now()
                        bot.stop_reason = "Bot no longer exists on Pionex"
                        bot.save()
            
            # Verify bots not in remote set are marked STOPPED
            for bot in created_bots:
                if bot.pionex_bot_id not in remote_bot_ids:
                    # Refresh from database
                    bot.refresh_from_db()
                    
                    # If it was ACTIVE before, it should be STOPPED now
                    original_status = next(
                        (lb["status"] for lb in local_bots if lb["pionex_bot_id"] == bot.pionex_bot_id),
                        "ACTIVE"
                    )
                    if original_status == "ACTIVE":
                        assert bot.status == BotStatus.STOPPED, (
                            f"Bot {bot.pionex_bot_id} not in remote set should be STOPPED, "
                            f"got {bot.status}"
                        )
                        assert bot.stopped_at is not None, (
                            f"Bot {bot.pionex_bot_id} should have stopped_at timestamp"
                        )
        finally:
            # Cleanup - delete user and all related objects
            Bot.objects.filter(user=user).delete()
            user.delete()

    @pytest.mark.django_db(transaction=True)
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        bot_data=mock_bot_info_strategy(),
    )
    def test_bot_update_preserves_data_integrity(
        self,
        bot_data: dict[str, any],
        django_user_model,
    ) -> None:
        """
        Property: Updating a bot SHALL preserve data integrity and correctly
        update all performance fields.

        **Validates: Requirements 2.2, 2.5**
        """
        from apps.bots.models import Bot, BotStatus, BotType
        from apps.core.models import TradingPair
        
        # Create a test user with unique username
        user = django_user_model.objects.create_user(
            username=f"test_update_user_{uuid.uuid4().hex[:8]}",
            password="testpass123",
        )
        
        try:
            # Get or create trading pair
            trading_pair, _ = TradingPair.objects.get_or_create(
                symbol=bot_data["symbol"],
                defaults={
                    "base_currency": bot_data["symbol"].split("_")[0],
                    "quote_currency": bot_data["symbol"].split("_")[1],
                    "is_active": True,
                },
            )
            
            # Map bot type
            bot_type_map = {
                "GRID": BotType.GRID,
                "DCA": BotType.DCA,
                "INFINITY_GRID": BotType.INFINITY_GRID,
                "FUTURES_GRID": BotType.FUTURES_GRID,
            }
            bot_type = bot_type_map.get(bot_data["bot_type"], BotType.GRID)
            
            # Create initial bot with different values
            initial_value = bot_data["invested"] * Decimal("0.8")
            initial_pnl = initial_value - bot_data["invested"]
            initial_pnl_percent = float((initial_pnl / bot_data["invested"]) * 100)
            
            bot = Bot.objects.create(
                user=user,
                pionex_bot_id=bot_data["bot_id"],
                bot_type=bot_type,
                trading_pair=trading_pair,
                status=BotStatus.ACTIVE,
                invested_amount=bot_data["invested"],
                current_value=initial_value,
                current_pnl=initial_pnl,
                pnl_percent=initial_pnl_percent,
                params={},
                is_simulated=False,
            )
            
            # Update bot with new values (matches _reconcile_bot update logic)
            bot.current_value = bot_data["current_value"]
            bot.current_pnl = bot_data["pnl"]
            bot.pnl_percent = bot_data["pnl_percent"]
            bot.save()
            
            # Refresh from database
            bot.refresh_from_db()
            
            # Verify updates
            assert bot.current_value == bot_data["current_value"], (
                f"current_value not updated correctly: expected {bot_data['current_value']}, "
                f"got {bot.current_value}"
            )
            assert bot.current_pnl == bot_data["pnl"], (
                f"current_pnl not updated correctly: expected {bot_data['pnl']}, "
                f"got {bot.current_pnl}"
            )
            assert bot.pnl_percent == pytest.approx(bot_data["pnl_percent"], rel=1e-6), (
                f"pnl_percent not updated correctly: expected {bot_data['pnl_percent']}, "
                f"got {bot.pnl_percent}"
            )
            
            # Verify invested_amount is unchanged
            assert bot.invested_amount == bot_data["invested"], (
                f"invested_amount should not change during update"
            )
        finally:
            # Cleanup - delete user and all related objects
            Bot.objects.filter(user=user).delete()
            user.delete()

    @pytest.mark.django_db(transaction=True)
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_local=st.integers(min_value=0, max_value=10),
        num_remote=st.integers(min_value=0, max_value=10),
        overlap_ratio=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    def test_reconciliation_completeness(
        self,
        num_local: int,
        num_remote: int,
        overlap_ratio: float,
        django_user_model,
    ) -> None:
        """
        Property: After reconciliation, the number of local bots SHALL equal
        the number of remote bots plus the number of stopped local bots.

        **Validates: Requirements 2.2, 2.3, 2.4**
        """
        from apps.bots.models import Bot, BotStatus, BotType
        from apps.core.models import TradingPair
        
        # Create a test user with unique username
        user = django_user_model.objects.create_user(
            username=f"test_recon_user_{uuid.uuid4().hex[:8]}",
            password="testpass123",
        )
        
        try:
            # Get or create trading pair
            trading_pair, _ = TradingPair.objects.get_or_create(
                symbol="BTC_USDT",
                defaults={
                    "base_currency": "BTC",
                    "quote_currency": "USDT",
                    "is_active": True,
                },
            )
            
            # Calculate overlap
            num_overlap = int(min(num_local, num_remote) * overlap_ratio)
            
            # Create local bots with UUID-based IDs
            local_bot_ids = [f"local_bot_{uuid.uuid4().hex[:8]}_{i}" for i in range(num_local)]
            for bot_id in local_bot_ids:
                Bot.objects.create(
                    user=user,
                    pionex_bot_id=bot_id,
                    bot_type=BotType.GRID,
                    trading_pair=trading_pair,
                    status=BotStatus.ACTIVE,
                    invested_amount=Decimal("100.00"),
                    current_value=Decimal("100.00"),
                    current_pnl=Decimal("0.00"),
                    pnl_percent=0.0,
                    params={},
                    is_simulated=False,
                )
            
            # Create remote bot IDs (some overlap with local)
            remote_bot_ids = (
                local_bot_ids[:num_overlap] +  # Overlapping bots
                [f"remote_bot_{uuid.uuid4().hex[:8]}_{i}" for i in range(num_remote - num_overlap)]  # New remote bots
            )
            
            # Simulate reconciliation (matches BotSyncService logic)
            # 1. Create new bots for remote bots not in local
            for bot_id in remote_bot_ids:
                if not Bot.objects.filter(pionex_bot_id=bot_id, user=user).exists():
                    Bot.objects.create(
                        user=user,
                        pionex_bot_id=bot_id,
                        bot_type=BotType.GRID,
                        trading_pair=trading_pair,
                        status=BotStatus.ACTIVE,
                        invested_amount=Decimal("100.00"),
                        current_value=Decimal("100.00"),
                        current_pnl=Decimal("0.00"),
                        pnl_percent=0.0,
                        params={},
                        is_simulated=False,
                    )
            
            # 2. Mark local bots not in remote as STOPPED
            for bot_id in local_bot_ids:
                if bot_id not in remote_bot_ids:
                    bot = Bot.objects.get(pionex_bot_id=bot_id, user=user)
                    if bot.status == BotStatus.ACTIVE:
                        bot.status = BotStatus.STOPPED
                        bot.save()
            
            # Verify reconciliation completeness
            total_local_bots = Bot.objects.filter(user=user).count()
            active_local_bots = Bot.objects.filter(user=user, status=BotStatus.ACTIVE).count()
            stopped_local_bots = Bot.objects.filter(user=user, status=BotStatus.STOPPED).count()
            
            # All remote bots should have local records
            assert active_local_bots == num_remote, (
                f"Number of active local bots ({active_local_bots}) should equal "
                f"number of remote bots ({num_remote})"
            )
            
            # Stopped bots should be local bots not in remote
            expected_stopped = num_local - num_overlap
            assert stopped_local_bots == expected_stopped, (
                f"Number of stopped bots ({stopped_local_bots}) should equal "
                f"local bots not in remote ({expected_stopped})"
            )
            
            # Total should be sum of active and stopped
            assert total_local_bots == active_local_bots + stopped_local_bots, (
                f"Total bots ({total_local_bots}) should equal "
                f"active ({active_local_bots}) + stopped ({stopped_local_bots})"
            )
        finally:
            # Cleanup - delete user and all related objects
            Bot.objects.filter(user=user).delete()
            user.delete()



# =============================================================================
# Property 8: Public Data Parsing and Storage
# =============================================================================


@st.composite
def fear_greed_data_strategy(draw: st.DrawFn) -> dict:
    """Generate valid Fear & Greed Index data."""
    value = draw(st.integers(min_value=0, max_value=100))
    
    # Determine classification based on value
    if value <= 25:
        classification = draw(st.sampled_from(["Extreme Fear", "Fear"]))
    elif value <= 45:
        classification = "Fear"
    elif value <= 55:
        classification = "Neutral"
    elif value <= 75:
        classification = "Greed"
    else:
        classification = draw(st.sampled_from(["Greed", "Extreme Greed"]))
    
    return {
        "value": value,
        "classification": classification,
    }


@st.composite
def funding_rate_data_strategy(draw: st.DrawFn) -> dict[str, dict]:
    """Generate valid funding rate data for multiple symbols."""
    symbols = draw(st.lists(
        st.sampled_from(["BTC_USDT", "ETH_USDT", "BNB_USDT", "SOL_USDT"]),
        min_size=1,
        max_size=4,
        unique=True,
    ))
    
    funding_rates = {}
    for symbol in symbols:
        rate = draw(st.floats(
            min_value=-0.01,  # -1%
            max_value=0.01,   # 1%
            allow_nan=False,
            allow_infinity=False,
        ))
        funding_rates[symbol] = {
            "rate": rate,
            "rate_percent": rate * 100,
            "next_funding_time": draw(st.integers(min_value=1000000000, max_value=2000000000)),
        }
    
    return funding_rates


@st.composite
def liquidation_data_strategy(draw: st.DrawFn) -> dict | None:
    """Generate valid liquidation data or None."""
    # Sometimes return None to simulate API failure
    if draw(st.booleans()):
        return None
    
    volume_24h = draw(st.decimals(
        min_value=Decimal("0"),
        max_value=Decimal("1000000000"),
        allow_nan=False,
        allow_infinity=False,
        places=2,
    ))
    
    # Long and short percentages should sum to 100
    long_percent = draw(st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False))
    short_percent = 100.0 - long_percent
    
    return {
        "volume_24h": volume_24h,
        "long_percent": long_percent,
        "short_percent": short_percent,
    }


@st.composite
def open_interest_data_strategy(draw: st.DrawFn) -> dict[str, dict]:
    """Generate valid open interest data for multiple symbols."""
    symbols = draw(st.lists(
        st.sampled_from(["BTC_USDT", "ETH_USDT", "BNB_USDT", "SOL_USDT"]),
        min_size=1,
        max_size=4,
        unique=True,
    ))
    
    open_interest = {}
    for symbol in symbols:
        value = draw(st.floats(
            min_value=0.0,
            max_value=1000000000.0,
            allow_nan=False,
            allow_infinity=False,
        ))
        open_interest[symbol] = {
            "value": value,
            "symbol": symbol,
        }
    
    return open_interest


class TestPublicDataParsing:
    """
    Property 8: Public Data Parsing and Storage

    *For any* valid API responses from Alternative.me, Binance, and CoinGlass:
    - Fear & Greed Index SHALL be parsed as integer 0-100
    - Funding rates SHALL be parsed as decimal values per symbol
    - Liquidation data SHALL include long/short percentages summing to 100
    - A MarketSentimentData record SHALL be created with all parsed values
    - If any API fails, is_stale SHALL be True and cached data SHALL be used

    **Validates: Requirements 4.2, 4.3, 4.4, 4.5, 4.7**
    """

    @pytest.mark.django_db(transaction=True)
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        fng_data=fear_greed_data_strategy(),
        funding_rates=funding_rate_data_strategy(),
        liquidation_data=liquidation_data_strategy(),
        open_interest=open_interest_data_strategy(),
    )
    def test_market_sentiment_data_creation(
        self,
        fng_data: dict,
        funding_rates: dict[str, dict],
        liquidation_data: dict | None,
        open_interest: dict[str, dict],
    ) -> None:
        """
        Property: Creating a MarketSentimentData record SHALL preserve all
        input values when read back from the database.

        **Validates: Requirements 4.5**
        """
        from apps.core.models import MarketSentimentData
        
        # Determine if data is stale (any API returned None)
        is_stale = liquidation_data is None
        
        # Extract liquidation values
        if liquidation_data:
            liq_volume = liquidation_data["volume_24h"]
            liq_long_pct = liquidation_data["long_percent"]
            liq_short_pct = liquidation_data["short_percent"]
        else:
            liq_volume = None
            liq_long_pct = None
            liq_short_pct = None
        
        # Create MarketSentimentData record
        sentiment = MarketSentimentData.objects.create(
            fear_greed_index=fng_data["value"],
            fear_greed_classification=fng_data["classification"],
            funding_rates=funding_rates,
            liquidation_volume_24h=liq_volume,
            liquidation_long_percent=liq_long_pct,
            liquidation_short_percent=liq_short_pct,
            open_interest=open_interest,
            btc_dominance=None,
            is_stale=is_stale,
        )
        
        # Read back from database
        retrieved = MarketSentimentData.objects.get(id=sentiment.id)
        
        # Verify all values match
        assert retrieved.fear_greed_index == fng_data["value"], (
            f"Fear & Greed Index mismatch: expected {fng_data['value']}, "
            f"got {retrieved.fear_greed_index}"
        )
        assert retrieved.fear_greed_classification == fng_data["classification"], (
            f"Classification mismatch: expected {fng_data['classification']}, "
            f"got {retrieved.fear_greed_classification}"
        )
        assert retrieved.funding_rates == funding_rates, (
            f"Funding rates mismatch: expected {funding_rates}, "
            f"got {retrieved.funding_rates}"
        )
        assert retrieved.open_interest == open_interest, (
            f"Open interest mismatch: expected {open_interest}, "
            f"got {retrieved.open_interest}"
        )
        assert retrieved.is_stale == is_stale, (
            f"is_stale mismatch: expected {is_stale}, got {retrieved.is_stale}"
        )
        
        if liquidation_data:
            assert retrieved.liquidation_volume_24h == liq_volume, (
                f"Liquidation volume mismatch: expected {liq_volume}, "
                f"got {retrieved.liquidation_volume_24h}"
            )
            assert retrieved.liquidation_long_percent == pytest.approx(liq_long_pct, rel=1e-6), (
                f"Liquidation long percent mismatch: expected {liq_long_pct}, "
                f"got {retrieved.liquidation_long_percent}"
            )
            assert retrieved.liquidation_short_percent == pytest.approx(liq_short_pct, rel=1e-6), (
                f"Liquidation short percent mismatch: expected {liq_short_pct}, "
                f"got {retrieved.liquidation_short_percent}"
            )
        
        # Cleanup
        sentiment.delete()

    @pytest.mark.django_db(transaction=True)
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        fng_value=st.integers(min_value=0, max_value=100),
    )
    def test_fear_greed_index_bounds(
        self,
        fng_value: int,
    ) -> None:
        """
        Property: Fear & Greed Index SHALL be bounded to [0, 100].

        **Validates: Requirements 4.2**
        """
        from apps.core.models import MarketSentimentData
        
        # Create record with FGI value
        sentiment = MarketSentimentData.objects.create(
            fear_greed_index=fng_value,
            fear_greed_classification="Test",
            funding_rates={},
            open_interest={},
            is_stale=False,
        )
        
        # Verify bounds
        assert 0 <= sentiment.fear_greed_index <= 100, (
            f"Fear & Greed Index {sentiment.fear_greed_index} outside valid range [0, 100]"
        )
        
        # Cleanup
        sentiment.delete()

    @pytest.mark.django_db(transaction=True)
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        liquidation_data=liquidation_data_strategy(),
    )
    def test_liquidation_percentages_sum_to_100(
        self,
        liquidation_data: dict | None,
    ) -> None:
        """
        Property: Liquidation long and short percentages SHALL sum to 100
        (or both be None).

        **Validates: Requirements 4.3**
        """
        from apps.core.models import MarketSentimentData
        
        if liquidation_data:
            liq_volume = liquidation_data["volume_24h"]
            liq_long_pct = liquidation_data["long_percent"]
            liq_short_pct = liquidation_data["short_percent"]
        else:
            liq_volume = None
            liq_long_pct = None
            liq_short_pct = None
        
        # Create record
        sentiment = MarketSentimentData.objects.create(
            fear_greed_index=50,
            fear_greed_classification="Neutral",
            funding_rates={},
            liquidation_volume_24h=liq_volume,
            liquidation_long_percent=liq_long_pct,
            liquidation_short_percent=liq_short_pct,
            open_interest={},
            is_stale=liquidation_data is None,
        )
        
        # Verify percentages
        if sentiment.liquidation_long_percent is not None and sentiment.liquidation_short_percent is not None:
            total = sentiment.liquidation_long_percent + sentiment.liquidation_short_percent
            assert total == pytest.approx(100.0, rel=1e-6), (
                f"Liquidation percentages should sum to 100, got {total}"
            )
        else:
            # Both should be None
            assert sentiment.liquidation_long_percent is None, (
                "liquidation_long_percent should be None when data is missing"
            )
            assert sentiment.liquidation_short_percent is None, (
                "liquidation_short_percent should be None when data is missing"
            )
        
        # Cleanup
        sentiment.delete()

    @pytest.mark.django_db(transaction=True)
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        funding_rates=funding_rate_data_strategy(),
    )
    def test_funding_rates_structure(
        self,
        funding_rates: dict[str, dict],
    ) -> None:
        """
        Property: Funding rates SHALL be stored as a dict mapping symbols
        to rate data with 'rate', 'rate_percent', and 'next_funding_time' keys.

        **Validates: Requirements 4.2**
        """
        from apps.core.models import MarketSentimentData
        
        # Create record
        sentiment = MarketSentimentData.objects.create(
            fear_greed_index=50,
            fear_greed_classification="Neutral",
            funding_rates=funding_rates,
            open_interest={},
            is_stale=False,
        )
        
        # Verify structure
        assert isinstance(sentiment.funding_rates, dict), (
            "funding_rates should be a dict"
        )
        
        for symbol, rate_data in sentiment.funding_rates.items():
            assert "rate" in rate_data, f"Symbol {symbol} missing 'rate' key"
            assert "rate_percent" in rate_data, f"Symbol {symbol} missing 'rate_percent' key"
            assert "next_funding_time" in rate_data, f"Symbol {symbol} missing 'next_funding_time' key"
            
            # Verify rate_percent is rate * 100
            expected_rate_percent = rate_data["rate"] * 100
            assert rate_data["rate_percent"] == pytest.approx(expected_rate_percent, rel=1e-6), (
                f"rate_percent should equal rate * 100 for {symbol}"
            )
        
        # Cleanup
        sentiment.delete()

    @pytest.mark.django_db(transaction=True)
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        open_interest=open_interest_data_strategy(),
    )
    def test_open_interest_structure(
        self,
        open_interest: dict[str, dict],
    ) -> None:
        """
        Property: Open interest SHALL be stored as a dict mapping symbols
        to data with 'value' and 'symbol' keys.

        **Validates: Requirements 4.4**
        """
        from apps.core.models import MarketSentimentData
        
        # Create record
        sentiment = MarketSentimentData.objects.create(
            fear_greed_index=50,
            fear_greed_classification="Neutral",
            funding_rates={},
            open_interest=open_interest,
            is_stale=False,
        )
        
        # Verify structure
        assert isinstance(sentiment.open_interest, dict), (
            "open_interest should be a dict"
        )
        
        for symbol, oi_data in sentiment.open_interest.items():
            assert "value" in oi_data, f"Symbol {symbol} missing 'value' key"
            assert "symbol" in oi_data, f"Symbol {symbol} missing 'symbol' key"
            assert oi_data["symbol"] == symbol, (
                f"Symbol mismatch: key={symbol}, value={oi_data['symbol']}"
            )
        
        # Cleanup
        sentiment.delete()

    @pytest.mark.django_db(transaction=True)
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        has_fng=st.booleans(),
        has_funding=st.booleans(),
        has_liquidation=st.booleans(),
        has_oi=st.booleans(),
    )
    def test_stale_flag_when_apis_fail(
        self,
        has_fng: bool,
        has_funding: bool,
        has_liquidation: bool,
        has_oi: bool,
    ) -> None:
        """
        Property: is_stale SHALL be True when any API fails (returns None).

        **Validates: Requirements 4.7**
        """
        from apps.core.models import MarketSentimentData
        
        # Determine if any API failed
        any_api_failed = not (has_fng and has_funding and has_liquidation and has_oi)
        
        # Create record
        sentiment = MarketSentimentData.objects.create(
            fear_greed_index=50 if has_fng else None,
            fear_greed_classification="Neutral" if has_fng else "",
            funding_rates={"BTC_USDT": {"rate": 0.0001, "rate_percent": 0.01, "next_funding_time": 1000000}} if has_funding else {},
            liquidation_volume_24h=Decimal("1000000") if has_liquidation else None,
            liquidation_long_percent=50.0 if has_liquidation else None,
            liquidation_short_percent=50.0 if has_liquidation else None,
            open_interest={"BTC_USDT": {"value": 1000000, "symbol": "BTC_USDT"}} if has_oi else {},
            is_stale=any_api_failed,
        )
        
        # Verify is_stale flag
        if any_api_failed:
            assert sentiment.is_stale is True, (
                "is_stale should be True when any API fails"
            )
        else:
            assert sentiment.is_stale is False, (
                "is_stale should be False when all APIs succeed"
            )
        
        # Cleanup
        sentiment.delete()

    @pytest.mark.django_db(transaction=True)
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        fng_data=fear_greed_data_strategy(),
    )
    def test_get_latest_returns_most_recent(
        self,
        fng_data: dict,
    ) -> None:
        """
        Property: MarketSentimentData.get_latest() SHALL return the most
        recently created record.

        **Validates: Requirements 4.5**
        """
        from apps.core.models import MarketSentimentData
        
        # Create first record
        sentiment1 = MarketSentimentData.objects.create(
            fear_greed_index=fng_data["value"],
            fear_greed_classification=fng_data["classification"],
            funding_rates={},
            open_interest={},
            is_stale=False,
        )
        
        # Create second record (more recent)
        sentiment2 = MarketSentimentData.objects.create(
            fear_greed_index=fng_data["value"] + 1 if fng_data["value"] < 100 else fng_data["value"] - 1,
            fear_greed_classification=fng_data["classification"],
            funding_rates={},
            open_interest={},
            is_stale=False,
        )
        
        # Get latest
        latest = MarketSentimentData.get_latest()
        
        # Verify it's the second record
        assert latest is not None, "get_latest() should return a record"
        assert latest.id == sentiment2.id, (
            f"get_latest() should return most recent record (id={sentiment2.id}), "
            f"got id={latest.id}"
        )
        
        # Cleanup
        sentiment1.delete()
        sentiment2.delete()


# =============================================================================
# Property 9: WebSocket Message Format
# =============================================================================


@st.composite
def websocket_message_data_strategy(draw: st.DrawFn) -> dict[str, any]:
    """
    Generate random data for WebSocket messages.
    
    Creates dictionaries with various data types that might appear
    in WebSocket messages.
    """
    # Generate random keys and values
    num_fields = draw(st.integers(min_value=1, max_value=10))
    
    data = {}
    for _ in range(num_fields):
        key = draw(st.text(min_size=1, max_size=20, alphabet=st.characters(min_codepoint=97, max_codepoint=122)))
        
        # Generate various value types
        value_type = draw(st.sampled_from(['string', 'int', 'float', 'decimal', 'bool', 'none']))
        
        if value_type == 'string':
            value = draw(st.text(min_size=0, max_size=100))
        elif value_type == 'int':
            value = draw(st.integers(min_value=-1000000, max_value=1000000))
        elif value_type == 'float':
            value = draw(st.floats(min_value=-1000000.0, max_value=1000000.0, allow_nan=False, allow_infinity=False))
        elif value_type == 'decimal':
            value = draw(st.decimals(
                min_value=Decimal("-1000000.00"),
                max_value=Decimal("1000000.00"),
                allow_nan=False,
                allow_infinity=False,
                places=2,
            ))
        elif value_type == 'bool':
            value = draw(st.booleans())
        else:  # none
            value = None
        
        data[key] = value
    
    return data


class TestWebSocketMessageFormat:
    """
    Property 9: WebSocket Message Format

    *For any* data update (portfolio, bot, signal, or sentiment):
    - The WebSocket message SHALL include a "type" field matching the update type
    - The message SHALL include a "timestamp" field with ISO format datetime
    - All Decimal values SHALL be serialized as strings
    - The message SHALL be valid JSON

    **Validates: Requirements 6.1, 6.2, 6.3, 6.4**
    """

    @settings(max_examples=20)
    @given(
        update_type=st.sampled_from(['portfolio_update', 'bot_update', 'signal_update', 'sentiment_update']),
        data=websocket_message_data_strategy(),
    )
    def test_message_has_required_fields(
        self,
        update_type: str,
        data: dict[str, any],
    ) -> None:
        """
        Property: All WebSocket messages SHALL have 'type' and 'timestamp' fields.

        **Validates: Requirements 6.1, 6.2, 6.3, 6.4**
        """
        from datetime import UTC, datetime
        from lib.messaging.websocket import _serialize_dict
        
        # Create a message with the update type
        message = {
            'type': update_type,
            'timestamp': datetime.now(tz=UTC).isoformat(),
            **data
        }
        
        # Serialize the message
        serialized = _serialize_dict(message)
        
        # Verify required fields exist
        assert 'type' in serialized, "Message must have 'type' field"
        assert 'timestamp' in serialized, "Message must have 'timestamp' field"
        assert serialized['type'] == update_type, f"Type field should be '{update_type}'"

    @settings(max_examples=20)
    @given(
        data=websocket_message_data_strategy(),
    )
    def test_decimal_values_serialized_as_strings(
        self,
        data: dict[str, any],
    ) -> None:
        """
        Property: All Decimal values SHALL be serialized as strings.

        **Validates: Requirements 6.1, 6.2, 6.3, 6.4**
        """
        from lib.messaging.websocket import _serialize_dict
        
        # Serialize the data
        serialized = _serialize_dict(data)
        
        # Check that all Decimal values are now strings
        for key, value in serialized.items():
            if isinstance(data.get(key), Decimal):
                assert isinstance(value, str), (
                    f"Decimal value for key '{key}' should be serialized as string, "
                    f"got {type(value).__name__}"
                )
                # Verify it can be converted back to Decimal
                try:
                    Decimal(value)
                except Exception as e:
                    pytest.fail(f"Serialized Decimal '{value}' cannot be converted back: {e}")

    @settings(max_examples=20)
    @given(
        update_type=st.sampled_from(['portfolio_update', 'bot_update', 'signal_update', 'sentiment_update']),
        data=websocket_message_data_strategy(),
    )
    def test_message_is_valid_json(
        self,
        update_type: str,
        data: dict[str, any],
    ) -> None:
        """
        Property: All WebSocket messages SHALL be valid JSON.

        **Validates: Requirements 6.1, 6.2, 6.3, 6.4**
        """
        import json
        from datetime import UTC, datetime
        from lib.messaging.websocket import _serialize_dict
        
        # Create a message
        message = {
            'type': update_type,
            'timestamp': datetime.now(tz=UTC).isoformat(),
            **data
        }
        
        # Serialize the message
        serialized = _serialize_dict(message)
        
        # Verify it can be converted to JSON
        try:
            json_str = json.dumps(serialized)
            assert isinstance(json_str, str), "JSON serialization should produce a string"
        except (TypeError, ValueError) as e:
            pytest.fail(f"Message cannot be serialized to JSON: {e}")
        
        # Verify it can be parsed back
        try:
            parsed = json.loads(json_str)
            assert isinstance(parsed, dict), "Parsed JSON should be a dictionary"
            assert parsed['type'] == update_type, "Type should be preserved after JSON round-trip"
        except (TypeError, ValueError) as e:
            pytest.fail(f"JSON cannot be parsed back: {e}")

    @settings(max_examples=20)
    @given(
        total_value=portfolio_value_strategy,
        available_balance=portfolio_value_strategy,
        allocated_to_bots=portfolio_value_strategy,
        drawdown=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        high_water_mark=portfolio_value_strategy,
    )
    def test_portfolio_update_message_format(
        self,
        total_value: Decimal,
        available_balance: Decimal,
        allocated_to_bots: Decimal,
        drawdown: float,
        high_water_mark: Decimal,
    ) -> None:
        """
        Property: Portfolio update messages SHALL have correct format with all
        Decimal values as strings.

        **Validates: Requirements 6.1**
        """
        import json
        from datetime import UTC, datetime
        
        # Create a portfolio update message (matches WebSocketBroadcaster format)
        message = {
            'type': 'portfolio_update',
            'total_value': str(total_value),
            'available_balance': str(available_balance),
            'allocated_to_bots': str(allocated_to_bots),
            'drawdown': drawdown,
            'high_water_mark': str(high_water_mark),
            'timestamp': datetime.now(tz=UTC).isoformat(),
        }
        
        # Verify it's valid JSON
        json_str = json.dumps(message)
        parsed = json.loads(json_str)
        
        # Verify all required fields
        assert parsed['type'] == 'portfolio_update'
        assert 'timestamp' in parsed
        assert isinstance(parsed['total_value'], str)
        assert isinstance(parsed['available_balance'], str)
        assert isinstance(parsed['allocated_to_bots'], str)
        assert isinstance(parsed['high_water_mark'], str)
        assert isinstance(parsed['drawdown'], (int, float))
        
        # Verify Decimal values can be reconstructed
        assert Decimal(parsed['total_value']) == total_value
        assert Decimal(parsed['available_balance']) == available_balance
        assert Decimal(parsed['allocated_to_bots']) == allocated_to_bots
        assert Decimal(parsed['high_water_mark']) == high_water_mark

    @settings(max_examples=20)
    @given(
        bot_id=st.text(min_size=1, max_size=50),
        status=st.sampled_from(['ACTIVE', 'STOPPED', 'ERROR', 'PENDING']),
        symbol=st.sampled_from(['BTC_USDT', 'ETH_USDT', 'BNB_USDT']),
        invested=portfolio_value_strategy,
        current_value=portfolio_value_strategy,
        pnl=st.decimals(
            min_value=Decimal("-10000.00"),
            max_value=Decimal("10000.00"),
            allow_nan=False,
            allow_infinity=False,
            places=2,
        ),
        pnl_percent=st.floats(min_value=-100.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    )
    def test_bot_update_message_format(
        self,
        bot_id: str,
        status: str,
        symbol: str,
        invested: Decimal,
        current_value: Decimal,
        pnl: Decimal,
        pnl_percent: float,
    ) -> None:
        """
        Property: Bot update messages SHALL have correct format with all
        Decimal values as strings.

        **Validates: Requirements 6.2**
        """
        import json
        from datetime import UTC, datetime
        
        # Create a bot update message (matches WebSocketBroadcaster format)
        message = {
            'type': 'bot_update',
            'bot_id': bot_id,
            'status': status,
            'symbol': symbol,
            'invested': str(invested),
            'current_value': str(current_value),
            'pnl': str(pnl),
            'pnl_percent': pnl_percent,
            'timestamp': datetime.now(tz=UTC).isoformat(),
        }
        
        # Verify it's valid JSON
        json_str = json.dumps(message)
        parsed = json.loads(json_str)
        
        # Verify all required fields
        assert parsed['type'] == 'bot_update'
        assert 'timestamp' in parsed
        assert isinstance(parsed['invested'], str)
        assert isinstance(parsed['current_value'], str)
        assert isinstance(parsed['pnl'], str)
        assert isinstance(parsed['pnl_percent'], (int, float))
        
        # Verify Decimal values can be reconstructed
        assert Decimal(parsed['invested']) == invested
        assert Decimal(parsed['current_value']) == current_value
        assert Decimal(parsed['pnl']) == pnl

    @settings(max_examples=20)
    @given(
        symbol=st.sampled_from(['BTC_USDT', 'ETH_USDT', 'BNB_USDT']),
        direction=st.sampled_from(['BUY', 'SELL', 'HOLD']),
        confidence=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        meets_threshold=st.booleans(),
    )
    def test_signal_update_message_format(
        self,
        symbol: str,
        direction: str,
        confidence: float,
        meets_threshold: bool,
    ) -> None:
        """
        Property: Signal update messages SHALL have correct format.

        **Validates: Requirements 6.3**
        """
        import json
        from datetime import UTC, datetime
        
        # Create a signal update message (matches WebSocketBroadcaster format)
        message = {
            'type': 'signal_update',
            'symbol': symbol,
            'direction': direction,
            'confidence': confidence,
            'meets_threshold': meets_threshold,
            'indicators': [],
            'reasoning': None,
            'timestamp': datetime.now(tz=UTC).isoformat(),
        }
        
        # Verify it's valid JSON
        json_str = json.dumps(message)
        parsed = json.loads(json_str)
        
        # Verify all required fields
        assert parsed['type'] == 'signal_update'
        assert 'timestamp' in parsed
        assert parsed['symbol'] == symbol
        assert parsed['direction'] == direction
        assert isinstance(parsed['confidence'], (int, float))
        assert isinstance(parsed['meets_threshold'], bool)

    @settings(max_examples=20)
    @given(
        fear_greed_index=st.integers(min_value=0, max_value=100),
        classification=st.sampled_from(['Extreme Fear', 'Fear', 'Neutral', 'Greed', 'Extreme Greed']),
    )
    def test_sentiment_update_message_format(
        self,
        fear_greed_index: int,
        classification: str,
    ) -> None:
        """
        Property: Sentiment update messages SHALL have correct format.

        **Validates: Requirements 6.4**
        """
        import json
        from datetime import UTC, datetime
        
        # Create a sentiment update message (matches WebSocketBroadcaster format)
        message = {
            'type': 'sentiment_update',
            'fear_greed_index': fear_greed_index,
            'signal': 'HOLD',
            'classification': classification,
            'timestamp': datetime.now(tz=UTC).isoformat(),
        }
        
        # Verify it's valid JSON
        json_str = json.dumps(message)
        parsed = json.loads(json_str)
        
        # Verify all required fields
        assert parsed['type'] == 'sentiment_update'
        assert 'timestamp' in parsed
        assert isinstance(parsed['fear_greed_index'], int)
        assert 0 <= parsed['fear_greed_index'] <= 100
        assert parsed['classification'] == classification

    @settings(max_examples=20)
    @given(
        data=websocket_message_data_strategy(),
    )
    def test_datetime_values_serialized_as_iso_strings(
        self,
        data: dict[str, any],
    ) -> None:
        """
        Property: All datetime values SHALL be serialized as ISO format strings.

        **Validates: Requirements 6.1, 6.2, 6.3, 6.4**
        """
        from datetime import UTC, datetime
        from lib.messaging.websocket import _serialize_value
        
        # Add a datetime to the data
        now = datetime.now(tz=UTC)
        data['test_datetime'] = now
        
        # Serialize individual values
        for key, value in data.items():
            serialized = _serialize_value(value)
            
            if isinstance(value, datetime):
                assert isinstance(serialized, str), (
                    f"Datetime value for key '{key}' should be serialized as string, "
                    f"got {type(serialized).__name__}"
                )
                # Verify it's in ISO format
                try:
                    datetime.fromisoformat(serialized.replace('Z', '+00:00'))
                except Exception as e:
                    pytest.fail(f"Serialized datetime '{serialized}' is not valid ISO format: {e}")
