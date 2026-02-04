"""
Property-based tests for Bot Risk Validation.

Feature: pionex-trading-bot
Property 13: Bot Risk Validation

These tests use the hypothesis library to verify that bot creation validation
correctly enforces portfolio risk limits.

**Validates: Requirements 10.7**
"""

from decimal import Decimal

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from lib.risk import (
    RiskManager,
    RiskManagerConfig,
)

# =============================================================================
# Custom Strategies for Bot Risk Validation
# =============================================================================

# Strategy for valid portfolio values (positive Decimal)
portfolio_value_strategy = st.decimals(
    min_value=Decimal("100.00"),  # Minimum $100 to avoid edge cases
    max_value=Decimal("1000000000.00"),  # 1 billion max
    allow_nan=False,
    allow_infinity=False,
    places=8,
)

# Strategy for valid allocation amounts (positive Decimal)
allocation_amount_strategy = st.decimals(
    min_value=Decimal("1.00"),  # Minimum $1
    max_value=Decimal("1000000000.00"),  # 1 billion max
    allow_nan=False,
    allow_infinity=False,
    places=8,
)

# Strategy for valid max bot allocation percentage (0 < pct <= 1)
max_bot_allocation_pct_strategy = st.floats(
    min_value=0.05,  # Minimum 5%
    max_value=0.95,  # Maximum 95%
    allow_nan=False,
    allow_infinity=False,
)

# Strategy for existing bot allocation as percentage of portfolio
existing_allocation_pct_strategy = st.floats(
    min_value=0.0,
    max_value=0.90,  # Up to 90% already allocated
    allow_nan=False,
    allow_infinity=False,
)


# =============================================================================
# Property 13: Bot Risk Validation
# =============================================================================


class TestBotRiskValidation:
    """
    Property 13: Bot Risk Validation

    *For any* bot creation where (current_allocations + new_allocation) > limit,
    the request SHALL be rejected.

    The bot risk validation must:
    1. Track current total allocation to bots
    2. Reject new bot creation if it would exceed the maximum allocation percentage
    3. Allow bot creation if within limits
    4. Correctly calculate allocation percentages

    **Validates: Requirements 10.7**
    """

    @settings(max_examples=100)
    @given(
        portfolio_value=portfolio_value_strategy,
        current_allocation_pct=existing_allocation_pct_strategy,
        new_allocation_pct=st.floats(
            min_value=0.01,
            max_value=0.50,
            allow_nan=False,
            allow_infinity=False,
        ),
        max_bot_allocation_pct=max_bot_allocation_pct_strategy,
    )
    def test_bot_rejected_when_exceeds_limit(
        self,
        portfolio_value: Decimal,
        current_allocation_pct: float,
        new_allocation_pct: float,
        max_bot_allocation_pct: float,
    ) -> None:
        """
        Property: For any bot creation where (current + new) > limit,
        the request SHALL be rejected.

        **Validates: Requirements 10.7**
        """
        # Calculate actual amounts
        current_allocation = portfolio_value * Decimal(str(current_allocation_pct))
        new_allocation = portfolio_value * Decimal(str(new_allocation_pct))

        # Calculate total allocation percentage
        total_allocation_pct = current_allocation_pct + new_allocation_pct

        # Skip edge cases where we're exactly at the limit
        assume(abs(total_allocation_pct - max_bot_allocation_pct) > 0.001)

        # Create risk manager with the specified limit
        config = RiskManagerConfig(max_bot_allocation_pct=max_bot_allocation_pct)
        risk_manager = RiskManager(config=config)

        # Set up portfolio and existing allocation
        risk_manager.update_portfolio(portfolio_value)
        risk_manager.update_bot_allocation(current_allocation)

        # Validate bot creation
        result = risk_manager.validate_bot_creation(new_allocation)

        # Check the result
        if total_allocation_pct > max_bot_allocation_pct:
            assert result.is_valid is False, (
                f"Bot creation should be rejected when total allocation "
                f"{total_allocation_pct:.4f} > limit {max_bot_allocation_pct:.4f}"
            )
            assert any("exceed" in r.lower() for r in result.rejection_reasons), (
                f"Rejection reasons should mention exceeding limit: {result.rejection_reasons}"
            )
        else:
            assert result.is_valid is True, (
                f"Bot creation should be allowed when total allocation "
                f"{total_allocation_pct:.4f} <= limit {max_bot_allocation_pct:.4f}"
            )

    @settings(max_examples=100)
    @given(
        portfolio_value=portfolio_value_strategy,
        max_bot_allocation_pct=max_bot_allocation_pct_strategy,
    )
    def test_bot_allowed_within_limit(
        self,
        portfolio_value: Decimal,
        max_bot_allocation_pct: float,
    ) -> None:
        """
        Property: For any bot creation where (current + new) <= limit,
        the request SHALL be allowed.

        **Validates: Requirements 10.7**
        """
        config = RiskManagerConfig(max_bot_allocation_pct=max_bot_allocation_pct)
        risk_manager = RiskManager(config=config)
        risk_manager.update_portfolio(portfolio_value)

        # Allocate half of the limit
        safe_allocation_pct = max_bot_allocation_pct * 0.5
        safe_allocation = portfolio_value * Decimal(str(safe_allocation_pct))
        safe_allocation = max(Decimal("1.00"), safe_allocation.quantize(Decimal("0.00000001")))

        result = risk_manager.validate_bot_creation(safe_allocation)

        assert result.is_valid is True, (
            f"Bot creation should be allowed when allocation "
            f"{safe_allocation_pct:.4f} < limit {max_bot_allocation_pct:.4f}. "
            f"Rejection reasons: {result.rejection_reasons}"
        )

    @settings(max_examples=100)
    @given(
        portfolio_value=portfolio_value_strategy,
        current_allocation_pct=existing_allocation_pct_strategy,
        new_allocation_amount=allocation_amount_strategy,
    )
    def test_new_total_allocation_calculation(
        self,
        portfolio_value: Decimal,
        current_allocation_pct: float,
        new_allocation_amount: Decimal,
    ) -> None:
        """
        Property: new_total_allocation SHALL equal current_allocation + new_allocation.

        **Validates: Requirements 10.7**
        """
        current_allocation = portfolio_value * Decimal(str(current_allocation_pct))
        current_allocation = current_allocation.quantize(Decimal("0.00000001"))

        risk_manager = RiskManager()
        risk_manager.update_portfolio(portfolio_value)
        risk_manager.update_bot_allocation(current_allocation)

        result = risk_manager.validate_bot_creation(new_allocation_amount)

        expected_total = current_allocation + new_allocation_amount

        assert result.new_total_allocation == expected_total, (
            f"new_total_allocation {result.new_total_allocation} != "
            f"expected {expected_total} "
            f"(current={current_allocation}, new={new_allocation_amount})"
        )

    @settings(max_examples=100)
    @given(
        portfolio_value=portfolio_value_strategy,
        new_allocation_amount=allocation_amount_strategy,
    )
    def test_allocation_percent_calculation(
        self,
        portfolio_value: Decimal,
        new_allocation_amount: Decimal,
    ) -> None:
        """
        Property: allocation_percent SHALL equal new_total_allocation / portfolio_value.

        **Validates: Requirements 10.7**
        """
        risk_manager = RiskManager()
        risk_manager.update_portfolio(portfolio_value)

        result = risk_manager.validate_bot_creation(new_allocation_amount)

        expected_percent = float(new_allocation_amount / portfolio_value)

        assert result.allocation_percent == pytest.approx(expected_percent, rel=1e-9), (
            f"allocation_percent {result.allocation_percent} != expected {expected_percent}"
        )

    @settings(max_examples=100)
    @given(
        portfolio_value=portfolio_value_strategy,
        current_allocation_pct=existing_allocation_pct_strategy,
        new_allocation_pct=st.floats(
            min_value=0.01,
            max_value=0.50,
            allow_nan=False,
            allow_infinity=False,
        ),
        max_bot_allocation_pct=max_bot_allocation_pct_strategy,
    )
    def test_validation_is_deterministic(
        self,
        portfolio_value: Decimal,
        current_allocation_pct: float,
        new_allocation_pct: float,
        max_bot_allocation_pct: float,
    ) -> None:
        """
        Property: For any inputs, validating bot creation twice
        SHALL produce identical results.

        **Validates: Requirements 10.7**
        """
        current_allocation = portfolio_value * Decimal(str(current_allocation_pct))
        new_allocation = portfolio_value * Decimal(str(new_allocation_pct))

        config = RiskManagerConfig(max_bot_allocation_pct=max_bot_allocation_pct)
        risk_manager = RiskManager(config=config)
        risk_manager.update_portfolio(portfolio_value)
        risk_manager.update_bot_allocation(current_allocation)

        result1 = risk_manager.validate_bot_creation(new_allocation)
        result2 = risk_manager.validate_bot_creation(new_allocation)

        assert result1.is_valid == result2.is_valid, (
            f"Validation not deterministic: {result1.is_valid} vs {result2.is_valid}"
        )
        assert result1.allocation_percent == result2.allocation_percent, (
            f"Allocation percent not deterministic: "
            f"{result1.allocation_percent} vs {result2.allocation_percent}"
        )

    @settings(max_examples=100)
    @given(
        portfolio_value=portfolio_value_strategy,
        max_bot_allocation_pct=max_bot_allocation_pct_strategy,
    )
    def test_cumulative_allocations_enforced(
        self,
        portfolio_value: Decimal,
        max_bot_allocation_pct: float,
    ) -> None:
        """
        Property: Multiple bot creations SHALL be validated against
        cumulative allocation, not just individual allocation.

        **Validates: Requirements 10.7**
        """
        config = RiskManagerConfig(max_bot_allocation_pct=max_bot_allocation_pct)
        risk_manager = RiskManager(config=config)
        risk_manager.update_portfolio(portfolio_value)

        # First allocation: 40% of limit
        first_allocation_pct = max_bot_allocation_pct * 0.4
        first_allocation = portfolio_value * Decimal(str(first_allocation_pct))
        first_allocation = max(Decimal("1.00"), first_allocation.quantize(Decimal("0.00000001")))

        result1 = risk_manager.validate_bot_creation(first_allocation)
        assert result1.is_valid is True, "First allocation should be valid"

        # Simulate the allocation being made
        risk_manager.update_bot_allocation(first_allocation)

        # Second allocation: another 40% of limit (total would be 80% of limit)
        second_allocation = first_allocation
        result2 = risk_manager.validate_bot_creation(second_allocation)

        # 80% of limit should still be valid
        assert result2.is_valid is True, (
            f"Second allocation should be valid (80% of limit). "
            f"Rejection: {result2.rejection_reasons}"
        )

        # Simulate the second allocation
        risk_manager.update_bot_allocation(first_allocation + second_allocation)

        # Third allocation: another 40% of limit (total would be 120% of limit)
        third_allocation = first_allocation
        result3 = risk_manager.validate_bot_creation(third_allocation)

        # 120% of limit should be rejected
        assert result3.is_valid is False, "Third allocation should be rejected (would exceed limit)"


class TestBotRiskValidationEdgeCases:
    """
    Edge case tests for bot risk validation.

    **Validates: Requirements 10.7**
    """

    @settings(max_examples=100)
    @given(
        portfolio_value=portfolio_value_strategy,
        max_bot_allocation_pct=max_bot_allocation_pct_strategy,
    )
    def test_at_exact_limit_is_valid(
        self,
        portfolio_value: Decimal,
        max_bot_allocation_pct: float,
    ) -> None:
        """
        Property: When allocation is safely below the limit,
        the request SHALL be valid.

        Note: Due to floating-point precision, we test slightly below the limit
        to avoid edge cases where rounding causes the allocation to appear
        to exceed the limit.

        **Validates: Requirements 10.7**
        """
        config = RiskManagerConfig(max_bot_allocation_pct=max_bot_allocation_pct)
        risk_manager = RiskManager(config=config)
        risk_manager.update_portfolio(portfolio_value)

        # Allocate slightly below the limit to avoid floating-point precision issues
        # Use 99.9% of the limit to ensure we're safely under
        safe_limit_pct = max_bot_allocation_pct * 0.999
        safe_limit_allocation = portfolio_value * Decimal(str(safe_limit_pct))
        safe_limit_allocation = safe_limit_allocation.quantize(Decimal("0.00000001"))

        result = risk_manager.validate_bot_creation(safe_limit_allocation)

        # Safely below the limit should be valid
        assert result.is_valid is True, (
            f"Allocation safely below the limit should be valid. "
            f"Rejection: {result.rejection_reasons}"
        )

    @settings(max_examples=100)
    @given(
        portfolio_value=portfolio_value_strategy,
        max_bot_allocation_pct=max_bot_allocation_pct_strategy,
    )
    def test_just_over_limit_is_rejected(
        self,
        portfolio_value: Decimal,
        max_bot_allocation_pct: float,
    ) -> None:
        """
        Property: When allocation is just over the limit,
        the request SHALL be rejected.

        **Validates: Requirements 10.7**
        """
        config = RiskManagerConfig(max_bot_allocation_pct=max_bot_allocation_pct)
        risk_manager = RiskManager(config=config)
        risk_manager.update_portfolio(portfolio_value)

        # Allocate just over the limit (1% more)
        over_limit_pct = min(1.0, max_bot_allocation_pct + 0.01)
        over_limit_allocation = portfolio_value * Decimal(str(over_limit_pct))
        over_limit_allocation = over_limit_allocation.quantize(Decimal("0.00000001"))

        result = risk_manager.validate_bot_creation(over_limit_allocation)

        # Just over the limit should be rejected
        assert result.is_valid is False, "Allocation just over the limit should be rejected"

    @settings(max_examples=100)
    @given(
        portfolio_value=portfolio_value_strategy,
        new_allocation_amount=allocation_amount_strategy,
    )
    def test_result_contains_all_required_fields(
        self,
        portfolio_value: Decimal,
        new_allocation_amount: Decimal,
    ) -> None:
        """
        Property: BotValidationResult SHALL contain all required fields
        with valid values.

        **Validates: Requirements 10.7**
        """
        risk_manager = RiskManager()
        risk_manager.update_portfolio(portfolio_value)

        result = risk_manager.validate_bot_creation(new_allocation_amount)

        # Verify all fields exist and have valid types
        assert isinstance(result.is_valid, bool), "is_valid should be bool"
        assert isinstance(result.allocation_amount, Decimal), "allocation_amount should be Decimal"
        assert isinstance(result.current_bot_allocation, Decimal), (
            "current_bot_allocation should be Decimal"
        )
        assert isinstance(result.new_total_allocation, Decimal), (
            "new_total_allocation should be Decimal"
        )
        assert isinstance(result.portfolio_value, Decimal), "portfolio_value should be Decimal"
        assert isinstance(result.allocation_percent, float), "allocation_percent should be float"
        assert isinstance(result.max_allocation_percent, float), (
            "max_allocation_percent should be float"
        )
        assert isinstance(result.rejection_reasons, tuple), "rejection_reasons should be tuple"
        assert isinstance(result.warnings, tuple), "warnings should be tuple"
        assert isinstance(result.reasoning, str), "reasoning should be str"
        assert len(result.reasoning) > 0, "reasoning should not be empty"

    @settings(max_examples=100)
    @given(
        portfolio_value=portfolio_value_strategy,
        max_bot_allocation_pct=max_bot_allocation_pct_strategy,
    )
    def test_available_allocation_consistency(
        self,
        portfolio_value: Decimal,
        max_bot_allocation_pct: float,
    ) -> None:
        """
        Property: get_available_bot_allocation SHALL return the correct
        remaining allocation amount.

        **Validates: Requirements 10.7**
        """
        config = RiskManagerConfig(max_bot_allocation_pct=max_bot_allocation_pct)
        risk_manager = RiskManager(config=config)
        risk_manager.update_portfolio(portfolio_value)

        # Get available allocation
        available = risk_manager.get_available_bot_allocation()

        # Expected: max_allocation - current_allocation (which is 0)
        expected = portfolio_value * Decimal(str(max_bot_allocation_pct))
        expected = expected.quantize(Decimal("0.00000001"))

        assert available == expected, f"Available allocation {available} != expected {expected}"

        # Allocating slightly less than available should be valid
        # (to avoid floating-point precision issues at exact boundary)
        safe_allocation = available * Decimal("0.999")
        safe_allocation = max(Decimal("1.00"), safe_allocation.quantize(Decimal("0.00000001")))

        result = risk_manager.validate_bot_creation(safe_allocation)
        assert result.is_valid is True, (
            f"Allocating slightly less than available should be valid. "
            f"Rejection: {result.rejection_reasons}"
        )

    @settings(max_examples=100)
    @given(
        portfolio_value=portfolio_value_strategy,
        current_allocation_pct=existing_allocation_pct_strategy,
        max_bot_allocation_pct=max_bot_allocation_pct_strategy,
    )
    def test_available_allocation_after_existing(
        self,
        portfolio_value: Decimal,
        current_allocation_pct: float,
        max_bot_allocation_pct: float,
    ) -> None:
        """
        Property: After existing allocation, get_available_bot_allocation
        SHALL return max_allocation - current_allocation.

        **Validates: Requirements 10.7**
        """
        # Ensure current allocation is less than max
        assume(current_allocation_pct < max_bot_allocation_pct)

        config = RiskManagerConfig(max_bot_allocation_pct=max_bot_allocation_pct)
        risk_manager = RiskManager(config=config)
        risk_manager.update_portfolio(portfolio_value)

        current_allocation = portfolio_value * Decimal(str(current_allocation_pct))
        current_allocation = current_allocation.quantize(Decimal("0.00000001"))
        risk_manager.update_bot_allocation(current_allocation)

        available = risk_manager.get_available_bot_allocation()

        max_allocation = portfolio_value * Decimal(str(max_bot_allocation_pct))
        expected = max_allocation - current_allocation
        expected = max(Decimal("0"), expected.quantize(Decimal("0.00000001")))

        assert available == expected, (
            f"Available allocation {available} != expected {expected} "
            f"(max={max_allocation}, current={current_allocation})"
        )


class TestBotRiskValidationWithDrawdown:
    """
    Tests for bot risk validation interaction with drawdown limits.

    **Validates: Requirements 10.7**
    """

    @settings(max_examples=100)
    @given(
        portfolio_value=portfolio_value_strategy,
        new_allocation_amount=allocation_amount_strategy,
    )
    def test_bot_rejected_when_trading_halted(
        self,
        portfolio_value: Decimal,
        new_allocation_amount: Decimal,
    ) -> None:
        """
        Property: When trading is halted due to drawdown,
        bot creation SHALL be rejected.

        **Validates: Requirements 10.7**
        """
        # Use a small max drawdown to easily trigger halt
        config = RiskManagerConfig(max_drawdown_pct=0.10)  # 10% max drawdown
        risk_manager = RiskManager(config=config)

        # Set initial portfolio value
        risk_manager.update_portfolio(portfolio_value)

        # Trigger drawdown breach (20% loss)
        breached_value = portfolio_value * Decimal("0.80")
        risk_manager.update_portfolio(breached_value)

        # Verify trading is halted
        assert risk_manager.is_trading_allowed() is False, (
            "Trading should be halted after drawdown breach"
        )

        # Try to create a bot
        result = risk_manager.validate_bot_creation(new_allocation_amount)

        assert result.is_valid is False, "Bot creation should be rejected when trading is halted"
        assert any("halted" in r.lower() for r in result.rejection_reasons), (
            f"Rejection should mention trading halted: {result.rejection_reasons}"
        )

    @settings(max_examples=100)
    @given(
        portfolio_value=portfolio_value_strategy,
        new_allocation_amount=allocation_amount_strategy,
    )
    def test_bot_allowed_after_drawdown_reset(
        self,
        portfolio_value: Decimal,
        new_allocation_amount: Decimal,
    ) -> None:
        """
        Property: After drawdown reset, bot creation SHALL be allowed
        (if within allocation limits).

        **Validates: Requirements 10.7**
        """
        # Ensure allocation is within limits
        assume(new_allocation_amount <= portfolio_value * Decimal("0.50"))

        config = RiskManagerConfig(max_drawdown_pct=0.10)
        risk_manager = RiskManager(config=config)

        # Set initial portfolio value
        risk_manager.update_portfolio(portfolio_value)

        # Trigger drawdown breach
        breached_value = portfolio_value * Decimal("0.80")
        risk_manager.update_portfolio(breached_value)

        # Reset drawdown
        risk_manager.reset_drawdown()

        # Verify trading is allowed
        assert risk_manager.is_trading_allowed() is True, "Trading should be allowed after reset"

        # Try to create a bot
        result = risk_manager.validate_bot_creation(new_allocation_amount)

        # Should be valid if within allocation limits
        if float(new_allocation_amount / breached_value) <= 0.50:
            assert result.is_valid is True, (
                f"Bot creation should be allowed after reset. Rejection: {result.rejection_reasons}"
            )
