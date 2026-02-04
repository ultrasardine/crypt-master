"""
Property-based tests for Drawdown Tracker Module.

Feature: pionex-trading-bot
Property 11: Drawdown Calculation
Property 12: Drawdown Limit Enforcement

These tests use the hypothesis library to verify that the drawdown tracker
behaves correctly across all valid inputs.

**Validates: Requirements 6.3, 6.4**
"""

from decimal import Decimal

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from lib.risk import (
    DrawdownTracker,
    DrawdownTrackerConfig,
)

# =============================================================================
# Custom Strategies for Drawdown Testing
# =============================================================================

# Strategy for valid portfolio values (positive Decimal)
# Using larger minimum to avoid precision issues with very small values
portfolio_value_strategy = st.decimals(
    min_value=Decimal("1.00"),  # Minimum $1 to avoid precision issues
    max_value=Decimal("1000000000.00"),  # 1 billion max
    allow_nan=False,
    allow_infinity=False,
    places=8,
)

# Strategy for non-negative portfolio values (including zero)
non_negative_portfolio_strategy = st.decimals(
    min_value=Decimal("0.00"),
    max_value=Decimal("1000000000.00"),
    allow_nan=False,
    allow_infinity=False,
    places=8,
)

# Strategy for valid max drawdown percentage (0 < pct < 1)
# Using max_value < 1.0 to avoid edge case where we can't exceed 100% drawdown
max_drawdown_pct_strategy = st.floats(
    min_value=0.05,  # Reasonable minimum
    max_value=0.95,  # Less than 100% to allow exceeding the limit
    allow_nan=False,
    allow_infinity=False,
)

# Strategy for drawdown percentage (0 to 1)
drawdown_pct_strategy = st.floats(
    min_value=0.0,
    max_value=0.99,  # Less than 100% to keep current_value positive
    allow_nan=False,
    allow_infinity=False,
)


@st.composite
def high_water_mark_and_current_strategy(draw: st.DrawFn) -> tuple[Decimal, Decimal]:
    """
    Generate valid high water mark and current value pairs.

    Ensures current_value <= high_water_mark (drawdown is non-negative).
    """
    high_water_mark = draw(portfolio_value_strategy)

    # Generate a drawdown percentage
    drawdown_pct = draw(drawdown_pct_strategy)

    # Calculate current value based on drawdown
    current_value = high_water_mark * Decimal(str(1 - drawdown_pct))
    current_value = max(Decimal("0"), current_value.quantize(Decimal("0.00000001")))

    return high_water_mark, current_value


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
        current = max(Decimal("0.00000001"), current.quantize(Decimal("0.00000001")))
        sequence.append(current)

    return sequence


# =============================================================================
# Property 11: Drawdown Calculation
# =============================================================================


class TestDrawdownCalculation:
    """
    Property 11: Drawdown Calculation

    *For any* portfolio history, drawdown SHALL equal:
        (high_water_mark - current_value) / high_water_mark

    The drawdown calculation must:
    1. Track the highest portfolio value seen (high water mark)
    2. Calculate drawdown as percentage from high water mark
    3. Return 0 when at or above high water mark
    4. Handle edge cases (zero values, very small values)

    **Validates: Requirements 6.3**
    """

    @settings(max_examples=100)
    @given(
        hwm_and_current=high_water_mark_and_current_strategy(),
    )
    def test_drawdown_formula_correctness(
        self,
        hwm_and_current: tuple[Decimal, Decimal],
    ) -> None:
        """
        Property: For any high_water_mark and current_value,
        drawdown SHALL equal (high_water_mark - current_value) / high_water_mark.

        **Validates: Requirements 6.3**
        """
        high_water_mark, current_value = hwm_and_current

        # Skip if high water mark is zero (division by zero)
        assume(high_water_mark > Decimal("0"))

        tracker = DrawdownTracker(initial_value=high_water_mark)
        tracker.update(current_value)

        # Calculate expected drawdown using the formula
        expected_drawdown = float((high_water_mark - current_value) / high_water_mark)

        actual_drawdown = tracker.calculate_drawdown()

        assert actual_drawdown == pytest.approx(expected_drawdown, rel=1e-9, abs=1e-12), (
            f"Drawdown formula mismatch: expected {expected_drawdown:.10f}, "
            f"got {actual_drawdown:.10f} "
            f"(hwm={high_water_mark}, current={current_value})"
        )

    @settings(max_examples=100)
    @given(
        hwm_and_current=high_water_mark_and_current_strategy(),
    )
    def test_drawdown_is_non_negative(
        self,
        hwm_and_current: tuple[Decimal, Decimal],
    ) -> None:
        """
        Property: Drawdown SHALL always be non-negative (>= 0).

        Since current_value <= high_water_mark by definition,
        drawdown should never be negative.

        **Validates: Requirements 6.3**
        """
        high_water_mark, current_value = hwm_and_current

        tracker = DrawdownTracker(initial_value=high_water_mark)
        tracker.update(current_value)

        drawdown = tracker.calculate_drawdown()

        assert drawdown >= 0.0, (
            f"Drawdown {drawdown} is negative (hwm={high_water_mark}, current={current_value})"
        )

    @settings(max_examples=100)
    @given(
        hwm_and_current=high_water_mark_and_current_strategy(),
    )
    def test_drawdown_bounded_by_one(
        self,
        hwm_and_current: tuple[Decimal, Decimal],
    ) -> None:
        """
        Property: Drawdown SHALL be bounded by [0, 1].

        Drawdown cannot exceed 100% (would require negative current value).

        **Validates: Requirements 6.3**
        """
        high_water_mark, current_value = hwm_and_current

        tracker = DrawdownTracker(initial_value=high_water_mark)
        tracker.update(current_value)

        drawdown = tracker.calculate_drawdown()

        assert 0.0 <= drawdown <= 1.0, (
            f"Drawdown {drawdown} outside valid range [0, 1] "
            f"(hwm={high_water_mark}, current={current_value})"
        )

    @settings(max_examples=100)
    @given(
        portfolio_value=portfolio_value_strategy,
    )
    def test_drawdown_zero_at_high_water_mark(
        self,
        portfolio_value: Decimal,
    ) -> None:
        """
        Property: Drawdown SHALL be zero when current_value equals high_water_mark.

        **Validates: Requirements 6.3**
        """
        tracker = DrawdownTracker(initial_value=portfolio_value)

        # Current value equals high water mark
        drawdown = tracker.calculate_drawdown()

        assert drawdown == 0.0, f"Drawdown should be 0 at high water mark, got {drawdown}"

    @settings(max_examples=100)
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

        **Validates: Requirements 6.3**
        """
        assume(len(sequence) >= 2)

        tracker = DrawdownTracker(initial_value=sequence[0])
        previous_hwm = tracker.high_water_mark

        for value in sequence[1:]:
            tracker.update(value)
            current_hwm = tracker.high_water_mark

            assert current_hwm >= previous_hwm, (
                f"High water mark decreased from {previous_hwm} to {current_hwm}"
            )
            previous_hwm = current_hwm

    @settings(max_examples=100)
    @given(
        sequence=portfolio_value_sequence_strategy(),
    )
    def test_high_water_mark_equals_max_seen(
        self,
        sequence: list[Decimal],
    ) -> None:
        """
        Property: High water mark SHALL equal the maximum value seen.

        **Validates: Requirements 6.3**
        """
        assume(len(sequence) >= 1)

        tracker = DrawdownTracker(initial_value=sequence[0])

        for value in sequence[1:]:
            tracker.update(value)

        expected_hwm = max(sequence)

        assert tracker.high_water_mark == expected_hwm, (
            f"High water mark {tracker.high_water_mark} != max seen {expected_hwm}"
        )

    @settings(max_examples=100)
    @given(
        hwm_and_current=high_water_mark_and_current_strategy(),
    )
    def test_drawdown_calculation_is_deterministic(
        self,
        hwm_and_current: tuple[Decimal, Decimal],
    ) -> None:
        """
        Property: For any inputs, calculating drawdown twice
        SHALL produce identical results.

        **Validates: Requirements 6.3**
        """
        high_water_mark, current_value = hwm_and_current

        tracker = DrawdownTracker(initial_value=high_water_mark)
        tracker.update(current_value)

        drawdown1 = tracker.calculate_drawdown()
        drawdown2 = tracker.calculate_drawdown()

        assert drawdown1 == drawdown2, (
            f"Drawdown calculation not deterministic: {drawdown1} vs {drawdown2}"
        )

    @settings(max_examples=100)
    @given(
        hwm_and_current=high_water_mark_and_current_strategy(),
    )
    def test_status_drawdown_matches_calculate_drawdown(
        self,
        hwm_and_current: tuple[Decimal, Decimal],
    ) -> None:
        """
        Property: get_status().drawdown_pct SHALL equal calculate_drawdown().

        **Validates: Requirements 6.3**
        """
        high_water_mark, current_value = hwm_and_current

        tracker = DrawdownTracker(initial_value=high_water_mark)
        tracker.update(current_value)

        status = tracker.get_status()
        calculated = tracker.calculate_drawdown()

        assert status.drawdown_pct == pytest.approx(calculated, rel=1e-9), (
            f"Status drawdown {status.drawdown_pct} != calculated {calculated}"
        )

    @settings(max_examples=100)
    @given(
        hwm_and_current=high_water_mark_and_current_strategy(),
    )
    def test_drawdown_amount_consistency(
        self,
        hwm_and_current: tuple[Decimal, Decimal],
    ) -> None:
        """
        Property: drawdown_amount SHALL equal high_water_mark - current_value.

        **Validates: Requirements 6.3**
        """
        high_water_mark, current_value = hwm_and_current

        tracker = DrawdownTracker(initial_value=high_water_mark)
        tracker.update(current_value)

        status = tracker.get_status()
        expected_amount = high_water_mark - current_value

        assert status.drawdown_amount == expected_amount, (
            f"Drawdown amount {status.drawdown_amount} != expected {expected_amount}"
        )


# =============================================================================
# Property 12: Drawdown Limit Enforcement
# =============================================================================


class TestDrawdownLimitEnforcement:
    """
    Property 12: Drawdown Limit Enforcement

    *For any* state where drawdown > max_drawdown, is_trading_allowed() SHALL return False.

    The drawdown limit enforcement must:
    1. Halt trading when drawdown exceeds the configured limit
    2. Keep trading halted until manual reset
    3. Correctly report breach status

    **Validates: Requirements 6.4**
    """

    @settings(max_examples=100)
    @given(
        high_water_mark=portfolio_value_strategy,
        max_drawdown_pct=max_drawdown_pct_strategy,
        actual_drawdown_pct=drawdown_pct_strategy,
    )
    def test_trading_halted_when_limit_exceeded(
        self,
        high_water_mark: Decimal,
        max_drawdown_pct: float,
        actual_drawdown_pct: float,
    ) -> None:
        """
        Property: When drawdown > max_drawdown_pct, is_trading_allowed() SHALL return False.

        **Validates: Requirements 6.4**
        """
        # Skip edge cases where drawdown is exactly at limit
        assume(abs(actual_drawdown_pct - max_drawdown_pct) > 0.001)

        config = DrawdownTrackerConfig(max_drawdown_pct=max_drawdown_pct)
        tracker = DrawdownTracker(initial_value=high_water_mark, config=config)

        # Calculate current value to achieve the desired drawdown
        current_value = high_water_mark * Decimal(str(1 - actual_drawdown_pct))
        current_value = max(Decimal("0"), current_value.quantize(Decimal("0.00000001")))

        tracker.update(current_value)

        if actual_drawdown_pct > max_drawdown_pct:
            assert tracker.is_trading_allowed() is False, (
                f"Trading should be halted when drawdown {actual_drawdown_pct:.4f} "
                f"> limit {max_drawdown_pct:.4f}"
            )
        else:
            assert tracker.is_trading_allowed() is True, (
                f"Trading should be allowed when drawdown {actual_drawdown_pct:.4f} "
                f"<= limit {max_drawdown_pct:.4f}"
            )

    @settings(max_examples=100)
    @given(
        high_water_mark=portfolio_value_strategy,
        max_drawdown_pct=max_drawdown_pct_strategy,
    )
    def test_trading_allowed_within_limit(
        self,
        high_water_mark: Decimal,
        max_drawdown_pct: float,
    ) -> None:
        """
        Property: When drawdown <= max_drawdown_pct, is_trading_allowed() SHALL return True.

        **Validates: Requirements 6.4**
        """
        config = DrawdownTrackerConfig(max_drawdown_pct=max_drawdown_pct)
        tracker = DrawdownTracker(initial_value=high_water_mark, config=config)

        # Set drawdown to half the limit (safely within)
        safe_drawdown = max_drawdown_pct * 0.5
        current_value = high_water_mark * Decimal(str(1 - safe_drawdown))
        current_value = max(Decimal("0.00000001"), current_value.quantize(Decimal("0.00000001")))

        tracker.update(current_value)

        assert tracker.is_trading_allowed() is True, (
            f"Trading should be allowed when drawdown {safe_drawdown:.4f} "
            f"< limit {max_drawdown_pct:.4f}"
        )

    @settings(max_examples=100)
    @given(
        high_water_mark=portfolio_value_strategy,
        max_drawdown_pct=max_drawdown_pct_strategy,
    )
    def test_is_breached_flag_accuracy(
        self,
        high_water_mark: Decimal,
        max_drawdown_pct: float,
    ) -> None:
        """
        Property: is_breached flag SHALL be True if and only if
        drawdown > max_drawdown_pct.

        **Validates: Requirements 6.4**
        """
        config = DrawdownTrackerConfig(max_drawdown_pct=max_drawdown_pct)
        tracker = DrawdownTracker(initial_value=high_water_mark, config=config)

        # Test with drawdown exceeding limit
        exceeding_drawdown = min(0.99, max_drawdown_pct + 0.05)
        current_value = high_water_mark * Decimal(str(1 - exceeding_drawdown))
        current_value = max(Decimal("0"), current_value.quantize(Decimal("0.00000001")))

        status = tracker.update(current_value)

        assert status.is_breached is True, (
            f"is_breached should be True when drawdown {exceeding_drawdown:.4f} "
            f"> limit {max_drawdown_pct:.4f}"
        )

    @settings(max_examples=100)
    @given(
        high_water_mark=portfolio_value_strategy,
        max_drawdown_pct=max_drawdown_pct_strategy,
    )
    def test_trading_remains_halted_after_recovery(
        self,
        high_water_mark: Decimal,
        max_drawdown_pct: float,
    ) -> None:
        """
        Property: Once trading is halted, it SHALL remain halted even if
        portfolio value recovers, until manual reset.

        **Validates: Requirements 6.4**
        """
        config = DrawdownTrackerConfig(max_drawdown_pct=max_drawdown_pct)
        tracker = DrawdownTracker(initial_value=high_water_mark, config=config)

        # Breach the limit
        exceeding_drawdown = min(0.99, max_drawdown_pct + 0.05)
        breach_value = high_water_mark * Decimal(str(1 - exceeding_drawdown))
        breach_value = max(Decimal("0"), breach_value.quantize(Decimal("0.00000001")))
        tracker.update(breach_value)

        assert tracker.is_halted is True, "Trading should be halted after breach"

        # Recover to a value within limits
        recovery_value = high_water_mark * Decimal("0.95")  # 5% drawdown
        tracker.update(recovery_value)

        # Should still be halted
        assert tracker.is_halted is True, (
            "Trading should remain halted after recovery until manual reset"
        )
        assert tracker.is_trading_allowed() is False, (
            "is_trading_allowed should return False until manual reset"
        )

    @settings(max_examples=100)
    @given(
        high_water_mark=portfolio_value_strategy,
        max_drawdown_pct=max_drawdown_pct_strategy,
    )
    def test_reset_clears_halted_state(
        self,
        high_water_mark: Decimal,
        max_drawdown_pct: float,
    ) -> None:
        """
        Property: After reset(), is_trading_allowed() SHALL return True
        (assuming current drawdown is within limits).

        **Validates: Requirements 6.4**
        """
        config = DrawdownTrackerConfig(max_drawdown_pct=max_drawdown_pct)
        tracker = DrawdownTracker(initial_value=high_water_mark, config=config)

        # Breach the limit
        exceeding_drawdown = min(0.99, max_drawdown_pct + 0.05)
        breach_value = high_water_mark * Decimal(str(1 - exceeding_drawdown))
        breach_value = max(Decimal("0"), breach_value.quantize(Decimal("0.00000001")))
        tracker.update(breach_value)

        assert tracker.is_halted is True, "Trading should be halted after breach"

        # Reset
        tracker.reset()

        assert tracker.is_halted is False, "Trading should be unhalted after reset"
        assert tracker.is_trading_allowed() is True, (
            "is_trading_allowed should return True after reset"
        )

    @settings(max_examples=100)
    @given(
        high_water_mark=portfolio_value_strategy,
        max_drawdown_pct=max_drawdown_pct_strategy,
    )
    def test_status_is_trading_allowed_consistency(
        self,
        high_water_mark: Decimal,
        max_drawdown_pct: float,
    ) -> None:
        """
        Property: get_status().is_trading_allowed SHALL equal is_trading_allowed().

        **Validates: Requirements 6.4**
        """
        config = DrawdownTrackerConfig(max_drawdown_pct=max_drawdown_pct)
        tracker = DrawdownTracker(initial_value=high_water_mark, config=config)

        # Test within limits
        safe_value = high_water_mark * Decimal("0.95")
        tracker.update(safe_value)

        status = tracker.get_status()
        method_result = tracker.is_trading_allowed()

        assert status.is_trading_allowed == method_result, (
            f"Status.is_trading_allowed ({status.is_trading_allowed}) != "
            f"is_trading_allowed() ({method_result})"
        )

    @settings(max_examples=100)
    @given(
        high_water_mark=portfolio_value_strategy,
        max_drawdown_pct=max_drawdown_pct_strategy,
    )
    def test_at_exact_limit_not_breached(
        self,
        high_water_mark: Decimal,
        max_drawdown_pct: float,
    ) -> None:
        """
        Property: When drawdown equals exactly max_drawdown_pct,
        is_breached SHALL be False (only breached when exceeded).

        **Validates: Requirements 6.4**
        """
        config = DrawdownTrackerConfig(max_drawdown_pct=max_drawdown_pct)
        tracker = DrawdownTracker(initial_value=high_water_mark, config=config)

        # Set drawdown to exactly the limit
        # Use high precision to ensure we hit exactly the limit
        current_value = high_water_mark * Decimal(str(1 - max_drawdown_pct))
        current_value = current_value.quantize(Decimal("0.00000001"))

        # Ensure current_value is non-negative
        assume(current_value >= Decimal("0"))

        status = tracker.update(current_value)

        # Calculate actual drawdown to verify we're at the limit
        actual_drawdown = float((high_water_mark - current_value) / high_water_mark)

        # Only assert if we're actually at or below the limit (accounting for precision)
        if actual_drawdown <= max_drawdown_pct:
            assert status.is_breached is False, (
                f"At or below the limit ({actual_drawdown:.6f} <= {max_drawdown_pct:.6f}), "
                f"is_breached should be False"
            )
            assert tracker.is_trading_allowed() is True, (
                "At or below the limit, trading should still be allowed"
            )


class TestDrawdownTrackerConsistency:
    """
    Additional consistency tests for drawdown tracking.

    These tests verify that the drawdown tracker behaves consistently
    across different scenarios and configurations.

    **Validates: Requirements 6.3, 6.4**
    """

    @settings(max_examples=100)
    @given(
        sequence=portfolio_value_sequence_strategy(),
        max_drawdown_pct=max_drawdown_pct_strategy,
    )
    def test_update_sequence_consistency(
        self,
        sequence: list[Decimal],
        max_drawdown_pct: float,
    ) -> None:
        """
        Property: For any sequence of updates, the tracker state
        SHALL remain consistent.

        **Validates: Requirements 6.3, 6.4**
        """
        assume(len(sequence) >= 1)

        config = DrawdownTrackerConfig(max_drawdown_pct=max_drawdown_pct)
        tracker = DrawdownTracker(initial_value=sequence[0], config=config)

        for value in sequence[1:]:
            status = tracker.update(value)

            # Verify consistency
            assert status.high_water_mark == tracker.high_water_mark
            assert status.current_value == tracker.current_value
            assert status.drawdown_pct == pytest.approx(tracker.calculate_drawdown(), rel=1e-9)
            assert status.is_trading_allowed == tracker.is_trading_allowed()

    @settings(max_examples=100)
    @given(
        hwm_and_current=high_water_mark_and_current_strategy(),
        max_drawdown_pct=max_drawdown_pct_strategy,
    )
    def test_multiple_trackers_same_result(
        self,
        hwm_and_current: tuple[Decimal, Decimal],
        max_drawdown_pct: float,
    ) -> None:
        """
        Property: Multiple DrawdownTracker instances with same config
        SHALL produce identical results for the same inputs.

        **Validates: Requirements 6.3, 6.4**
        """
        high_water_mark, current_value = hwm_and_current

        config = DrawdownTrackerConfig(max_drawdown_pct=max_drawdown_pct)

        tracker1 = DrawdownTracker(initial_value=high_water_mark, config=config)
        tracker2 = DrawdownTracker(initial_value=high_water_mark, config=config)

        tracker1.update(current_value)
        tracker2.update(current_value)

        assert tracker1.calculate_drawdown() == tracker2.calculate_drawdown(), (
            "Different tracker instances produced different drawdown values"
        )
        assert tracker1.is_trading_allowed() == tracker2.is_trading_allowed(), (
            "Different tracker instances produced different trading allowed status"
        )

    @settings(max_examples=100)
    @given(
        hwm_and_current=high_water_mark_and_current_strategy(),
    )
    def test_status_contains_all_required_fields(
        self,
        hwm_and_current: tuple[Decimal, Decimal],
    ) -> None:
        """
        Property: DrawdownStatus SHALL contain all required fields
        with valid values.

        **Validates: Requirements 6.3, 6.4**
        """
        high_water_mark, current_value = hwm_and_current

        tracker = DrawdownTracker(initial_value=high_water_mark)
        tracker.update(current_value)

        status = tracker.get_status()

        # Verify all fields exist and have valid types
        assert isinstance(status.high_water_mark, Decimal), "high_water_mark should be Decimal"
        assert isinstance(status.current_value, Decimal), "current_value should be Decimal"
        assert isinstance(status.drawdown_amount, Decimal), "drawdown_amount should be Decimal"
        assert isinstance(status.drawdown_pct, float), "drawdown_pct should be float"
        assert isinstance(status.max_drawdown_pct, float), "max_drawdown_pct should be float"
        assert isinstance(status.is_breached, bool), "is_breached should be bool"
        assert isinstance(status.is_trading_allowed, bool), "is_trading_allowed should be bool"
        assert isinstance(status.reasoning, str), "reasoning should be str"
        assert len(status.reasoning) > 0, "reasoning should not be empty"

    @settings(max_examples=100)
    @given(
        high_water_mark=portfolio_value_strategy,
        new_high=portfolio_value_strategy,
    )
    def test_new_high_resets_drawdown_to_zero(
        self,
        high_water_mark: Decimal,
        new_high: Decimal,
    ) -> None:
        """
        Property: When portfolio reaches a new high, drawdown SHALL be zero.

        **Validates: Requirements 6.3**
        """
        # Ensure new_high is actually higher
        assume(new_high > high_water_mark)

        tracker = DrawdownTracker(initial_value=high_water_mark)

        # First go down
        lower_value = high_water_mark * Decimal("0.9")
        tracker.update(lower_value)

        # Then reach new high
        tracker.update(new_high)

        assert tracker.calculate_drawdown() == 0.0, (
            f"Drawdown should be 0 at new high, got {tracker.calculate_drawdown()}"
        )
        assert tracker.high_water_mark == new_high, (
            f"High water mark should be updated to {new_high}, got {tracker.high_water_mark}"
        )
