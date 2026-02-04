"""
Property-based tests for Position Sizer Module.

Feature: pionex-trading-bot
Property 9: Kelly Criterion Calculation
Property 10: Position Size Capping

These tests use the hypothesis library to verify that the position sizer
behaves correctly across all valid inputs.

**Validates: Requirements 6.1, 6.2**
"""

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from lib.risk import (
    PositionSizer,
    PositionSizerConfig,
)

# =============================================================================
# Custom Strategies for Position Sizing
# =============================================================================

# Strategy for valid win probability (0 to 1, inclusive)
win_probability_strategy = st.floats(
    min_value=0.0,
    max_value=1.0,
    allow_nan=False,
    allow_infinity=False,
)

# Strategy for valid win/loss ratio (positive, non-zero)
win_loss_ratio_strategy = st.floats(
    min_value=0.001,  # Small positive value to avoid division issues
    max_value=100.0,  # Reasonable upper bound
    allow_nan=False,
    allow_infinity=False,
)

# Strategy for valid portfolio values (non-negative Decimal)
portfolio_value_strategy = st.decimals(
    min_value=Decimal("0.00"),
    max_value=Decimal("1000000000.00"),  # 1 billion max
    allow_nan=False,
    allow_infinity=False,
    places=8,
)

# Strategy for valid max position percentage (0 < pct <= 1)
max_position_pct_strategy = st.floats(
    min_value=0.001,  # Small positive value
    max_value=1.0,
    allow_nan=False,
    allow_infinity=False,
)

# Strategy for valid Kelly fraction multiplier (0 < mult <= 1)
kelly_multiplier_strategy = st.floats(
    min_value=0.001,
    max_value=1.0,
    allow_nan=False,
    allow_infinity=False,
)


@st.composite
def position_sizer_config_strategy(draw: st.DrawFn) -> PositionSizerConfig:
    """
    Generate valid PositionSizerConfig instances.

    Creates configurations with random but valid values for testing
    the position sizing properties.
    """
    max_position_pct = draw(max_position_pct_strategy)
    kelly_multiplier = draw(kelly_multiplier_strategy)

    return PositionSizerConfig(
        max_position_pct=max_position_pct,
        kelly_fraction_multiplier=kelly_multiplier,
    )


# =============================================================================
# Property 9: Kelly Criterion Calculation
# =============================================================================


class TestKellyCriterionCalculation:
    """
    Property 9: Kelly Criterion Calculation

    *For any* valid win_probability (p) and win_loss_ratio (b),
    Kelly fraction SHALL equal (p * b - q) / b where q = 1 - p,
    clamped to [0, 1] before applying max_position_pct cap.

    The Kelly Criterion formula:
        f* = (p * b - q) / b

    Where:
        - f* = optimal fraction of portfolio to bet
        - p = probability of winning
        - q = probability of losing (1 - p)
        - b = win/loss ratio (average win / average loss)

    **Validates: Requirements 6.1**
    """

    @settings(max_examples=100)
    @given(
        win_probability=win_probability_strategy,
        win_loss_ratio=win_loss_ratio_strategy,
    )
    def test_kelly_formula_correctness(
        self,
        win_probability: float,
        win_loss_ratio: float,
    ) -> None:
        """
        Property: For any valid win_probability and win_loss_ratio,
        Kelly fraction SHALL equal (p * b - q) / b.

        **Validates: Requirements 6.1**
        """
        sizer = PositionSizer()

        # Calculate Kelly fraction using the implementation
        kelly = sizer.calculate_kelly_fraction(
            win_probability=win_probability,
            win_loss_ratio=win_loss_ratio,
        )

        # Calculate expected Kelly using the formula
        p = win_probability
        q = 1 - p
        b = win_loss_ratio
        expected_kelly = (p * b - q) / b

        assert kelly == pytest.approx(expected_kelly, rel=1e-9), (
            f"Kelly formula mismatch: expected {expected_kelly:.10f}, "
            f"got {kelly:.10f} "
            f"(win_prob={win_probability}, win_loss_ratio={win_loss_ratio})"
        )

    @settings(max_examples=100)
    @given(
        win_probability=win_probability_strategy,
        win_loss_ratio=win_loss_ratio_strategy,
    )
    def test_kelly_calculation_is_deterministic(
        self,
        win_probability: float,
        win_loss_ratio: float,
    ) -> None:
        """
        Property: For any inputs, calculating Kelly fraction twice
        SHALL produce identical results.

        **Validates: Requirements 6.1**
        """
        sizer = PositionSizer()

        kelly1 = sizer.calculate_kelly_fraction(
            win_probability=win_probability,
            win_loss_ratio=win_loss_ratio,
        )
        kelly2 = sizer.calculate_kelly_fraction(
            win_probability=win_probability,
            win_loss_ratio=win_loss_ratio,
        )

        assert kelly1 == kelly2, (
            f"Kelly calculation not deterministic: "
            f"{kelly1} vs {kelly2} "
            f"(win_prob={win_probability}, win_loss_ratio={win_loss_ratio})"
        )

    @settings(max_examples=100)
    @given(
        win_probability=win_probability_strategy,
        win_loss_ratio=win_loss_ratio_strategy,
    )
    def test_kelly_negative_when_no_edge(
        self,
        win_probability: float,
        win_loss_ratio: float,
    ) -> None:
        """
        Property: Kelly fraction SHALL be negative when expected value is negative
        (i.e., when p * b < q, meaning no positive edge exists).

        **Validates: Requirements 6.1**
        """
        sizer = PositionSizer()

        kelly = sizer.calculate_kelly_fraction(
            win_probability=win_probability,
            win_loss_ratio=win_loss_ratio,
        )

        p = win_probability
        q = 1 - p
        b = win_loss_ratio

        # Expected value is positive when p * b > q
        has_positive_edge = (p * b) > q

        if has_positive_edge:
            assert kelly > 0, (
                f"Kelly should be positive when edge exists: kelly={kelly}, p*b={p * b}, q={q}"
            )
        elif (p * b) < q:
            assert kelly < 0, (
                f"Kelly should be negative when no edge: kelly={kelly}, p*b={p * b}, q={q}"
            )
        else:
            # Edge case: p * b == q (exactly break-even)
            assert kelly == pytest.approx(0.0, abs=1e-9), (
                f"Kelly should be zero at break-even: kelly={kelly}"
            )

    @settings(max_examples=100)
    @given(
        win_probability=win_probability_strategy,
        win_loss_ratio=win_loss_ratio_strategy,
    )
    def test_kelly_bounded_by_theoretical_limits(
        self,
        win_probability: float,
        win_loss_ratio: float,
    ) -> None:
        """
        Property: Raw Kelly fraction SHALL be bounded by theoretical limits.

        The minimum Kelly is -1 (when p=0, q=1): f* = (0 - 1) / b = -1/b
        The maximum Kelly approaches 1 as p approaches 1.

        **Validates: Requirements 6.1**
        """
        sizer = PositionSizer()

        kelly = sizer.calculate_kelly_fraction(
            win_probability=win_probability,
            win_loss_ratio=win_loss_ratio,
        )

        # Kelly can range from -1/b (when p=0) to approaching 1 (when p=1)
        # For practical purposes, Kelly should be in a reasonable range
        min_theoretical = -1.0 / win_loss_ratio
        max_theoretical = 1.0  # When p=1, Kelly = (1*b - 0)/b = 1

        assert kelly >= min_theoretical - 1e-9, (
            f"Kelly {kelly} below theoretical minimum {min_theoretical}"
        )
        assert kelly <= max_theoretical + 1e-9, (
            f"Kelly {kelly} above theoretical maximum {max_theoretical}"
        )

    @settings(max_examples=100)
    @given(
        win_loss_ratio=win_loss_ratio_strategy,
    )
    def test_kelly_at_boundary_probabilities(
        self,
        win_loss_ratio: float,
    ) -> None:
        """
        Property: Kelly SHALL produce correct values at boundary probabilities.

        - When p=0: Kelly = (0 - 1) / b = -1/b
        - When p=1: Kelly = (b - 0) / b = 1

        **Validates: Requirements 6.1**
        """
        sizer = PositionSizer()

        # Test p=0
        kelly_at_zero = sizer.calculate_kelly_fraction(
            win_probability=0.0,
            win_loss_ratio=win_loss_ratio,
        )
        expected_at_zero = -1.0 / win_loss_ratio
        assert kelly_at_zero == pytest.approx(expected_at_zero, rel=1e-9), (
            f"Kelly at p=0 should be {expected_at_zero}, got {kelly_at_zero}"
        )

        # Test p=1
        kelly_at_one = sizer.calculate_kelly_fraction(
            win_probability=1.0,
            win_loss_ratio=win_loss_ratio,
        )
        assert kelly_at_one == pytest.approx(1.0, rel=1e-9), (
            f"Kelly at p=1 should be 1.0, got {kelly_at_one}"
        )


# =============================================================================
# Property 10: Position Size Capping
# =============================================================================


class TestPositionSizeCapping:
    """
    Property 10: Position Size Capping

    *For any* Kelly fraction, position size SHALL NOT exceed
    max_position_pct * portfolio_value.

    The position sizing system must:
    1. Clamp negative Kelly to 0 (no position when no edge)
    2. Clamp Kelly > 1 to 1 (never bet more than 100%)
    3. Apply Kelly fraction multiplier for conservative sizing
    4. Cap at max_position_pct (default 10%)

    **Validates: Requirements 6.2**
    """

    @settings(max_examples=100)
    @given(
        win_probability=win_probability_strategy,
        win_loss_ratio=win_loss_ratio_strategy,
        portfolio_value=portfolio_value_strategy,
    )
    def test_position_never_exceeds_max_percentage(
        self,
        win_probability: float,
        win_loss_ratio: float,
        portfolio_value: Decimal,
    ) -> None:
        """
        Property: For any inputs, position size SHALL NOT exceed
        max_position_pct * portfolio_value.

        **Validates: Requirements 6.2**
        """
        sizer = PositionSizer()  # Default max_position_pct = 0.10

        result = sizer.calculate_position_size(
            win_probability=win_probability,
            win_loss_ratio=win_loss_ratio,
            portfolio_value=portfolio_value,
        )

        max_allowed = portfolio_value * Decimal(str(sizer.max_position_pct))
        max_allowed = max_allowed.quantize(Decimal("0.00000001"))

        assert result.position_size <= max_allowed, (
            f"Position size {result.position_size} exceeds max allowed {max_allowed} "
            f"(portfolio={portfolio_value}, max_pct={sizer.max_position_pct})"
        )

    @settings(max_examples=100)
    @given(
        win_probability=win_probability_strategy,
        win_loss_ratio=win_loss_ratio_strategy,
        portfolio_value=portfolio_value_strategy,
        max_position_pct=max_position_pct_strategy,
    )
    def test_position_respects_custom_max_percentage(
        self,
        win_probability: float,
        win_loss_ratio: float,
        portfolio_value: Decimal,
        max_position_pct: float,
    ) -> None:
        """
        Property: For any custom max_position_pct, position size
        SHALL NOT exceed that percentage of portfolio.

        **Validates: Requirements 6.2**
        """
        config = PositionSizerConfig(max_position_pct=max_position_pct)
        sizer = PositionSizer(config=config)

        result = sizer.calculate_position_size(
            win_probability=win_probability,
            win_loss_ratio=win_loss_ratio,
            portfolio_value=portfolio_value,
        )

        max_allowed = portfolio_value * Decimal(str(max_position_pct))
        max_allowed = max_allowed.quantize(Decimal("0.00000001"))

        assert result.position_size <= max_allowed, (
            f"Position size {result.position_size} exceeds custom max {max_allowed} "
            f"(portfolio={portfolio_value}, max_pct={max_position_pct})"
        )

    @settings(max_examples=100)
    @given(
        win_probability=win_probability_strategy,
        win_loss_ratio=win_loss_ratio_strategy,
        portfolio_value=portfolio_value_strategy,
    )
    def test_position_is_non_negative(
        self,
        win_probability: float,
        win_loss_ratio: float,
        portfolio_value: Decimal,
    ) -> None:
        """
        Property: Position size SHALL always be non-negative.

        Even when Kelly is negative (no edge), position should be 0, not negative.

        **Validates: Requirements 6.2**
        """
        sizer = PositionSizer()

        result = sizer.calculate_position_size(
            win_probability=win_probability,
            win_loss_ratio=win_loss_ratio,
            portfolio_value=portfolio_value,
        )

        assert result.position_size >= Decimal("0"), (
            f"Position size {result.position_size} is negative (kelly={result.kelly_fraction})"
        )
        assert result.clamped_fraction >= 0.0, (
            f"Clamped fraction {result.clamped_fraction} is negative"
        )

    @settings(max_examples=100)
    @given(
        win_probability=win_probability_strategy,
        win_loss_ratio=win_loss_ratio_strategy,
        portfolio_value=portfolio_value_strategy,
    )
    def test_clamped_fraction_in_valid_range(
        self,
        win_probability: float,
        win_loss_ratio: float,
        portfolio_value: Decimal,
    ) -> None:
        """
        Property: Clamped fraction SHALL be in range [0, max_position_pct].

        **Validates: Requirements 6.2**
        """
        sizer = PositionSizer()

        result = sizer.calculate_position_size(
            win_probability=win_probability,
            win_loss_ratio=win_loss_ratio,
            portfolio_value=portfolio_value,
        )

        assert 0.0 <= result.clamped_fraction <= sizer.max_position_pct, (
            f"Clamped fraction {result.clamped_fraction} outside valid range "
            f"[0, {sizer.max_position_pct}]"
        )

    @settings(max_examples=100)
    @given(
        win_probability=win_probability_strategy,
        win_loss_ratio=win_loss_ratio_strategy,
        portfolio_value=portfolio_value_strategy,
    )
    def test_was_capped_flag_accuracy(
        self,
        win_probability: float,
        win_loss_ratio: float,
        portfolio_value: Decimal,
    ) -> None:
        """
        Property: was_capped flag SHALL be True if and only if
        Kelly fraction (after multiplier) exceeds max_position_pct.

        **Validates: Requirements 6.2**
        """
        sizer = PositionSizer()

        result = sizer.calculate_position_size(
            win_probability=win_probability,
            win_loss_ratio=win_loss_ratio,
            portfolio_value=portfolio_value,
        )

        # Kelly is capped when positive and exceeds max after multiplier
        kelly_after_multiplier = result.kelly_fraction * sizer.config.kelly_fraction_multiplier
        should_be_capped = (
            result.kelly_fraction > 0 and kelly_after_multiplier > sizer.max_position_pct
        )

        assert result.was_capped == should_be_capped, (
            f"was_capped flag incorrect: expected {should_be_capped}, "
            f"got {result.was_capped} "
            f"(kelly={result.kelly_fraction}, max_pct={sizer.max_position_pct})"
        )

    @settings(max_examples=100)
    @given(
        win_probability=win_probability_strategy,
        win_loss_ratio=win_loss_ratio_strategy,
        portfolio_value=portfolio_value_strategy,
    )
    def test_was_negative_flag_accuracy(
        self,
        win_probability: float,
        win_loss_ratio: float,
        portfolio_value: Decimal,
    ) -> None:
        """
        Property: was_negative flag SHALL be True if and only if
        raw Kelly fraction is negative.

        **Validates: Requirements 6.2**
        """
        sizer = PositionSizer()

        result = sizer.calculate_position_size(
            win_probability=win_probability,
            win_loss_ratio=win_loss_ratio,
            portfolio_value=portfolio_value,
        )

        should_be_negative = result.kelly_fraction < 0

        assert result.was_negative == should_be_negative, (
            f"was_negative flag incorrect: expected {should_be_negative}, "
            f"got {result.was_negative} "
            f"(kelly={result.kelly_fraction})"
        )

    @settings(max_examples=100)
    @given(
        win_probability=win_probability_strategy,
        win_loss_ratio=win_loss_ratio_strategy,
        portfolio_value=portfolio_value_strategy,
    )
    def test_position_size_equals_clamped_fraction_times_portfolio(
        self,
        win_probability: float,
        win_loss_ratio: float,
        portfolio_value: Decimal,
    ) -> None:
        """
        Property: Position size SHALL equal clamped_fraction * portfolio_value.

        **Validates: Requirements 6.2**
        """
        sizer = PositionSizer()

        result = sizer.calculate_position_size(
            win_probability=win_probability,
            win_loss_ratio=win_loss_ratio,
            portfolio_value=portfolio_value,
        )

        expected_position = portfolio_value * Decimal(str(result.clamped_fraction))
        expected_position = expected_position.quantize(Decimal("0.00000001"))

        assert result.position_size == expected_position, (
            f"Position size mismatch: expected {expected_position}, "
            f"got {result.position_size} "
            f"(clamped_fraction={result.clamped_fraction}, portfolio={portfolio_value})"
        )


class TestPositionSizerConsistency:
    """
    Additional consistency tests for position sizing.

    These tests verify that the position sizer behaves consistently
    across different scenarios and configurations.

    **Validates: Requirements 6.1, 6.2**
    """

    @settings(max_examples=100)
    @given(
        win_probability=win_probability_strategy,
        win_loss_ratio=win_loss_ratio_strategy,
        portfolio_value=portfolio_value_strategy,
    )
    def test_calculation_is_deterministic(
        self,
        win_probability: float,
        win_loss_ratio: float,
        portfolio_value: Decimal,
    ) -> None:
        """
        Property: For any inputs, calculating position size twice
        SHALL produce identical results.

        **Validates: Requirements 6.1, 6.2**
        """
        sizer = PositionSizer()

        result1 = sizer.calculate_position_size(
            win_probability=win_probability,
            win_loss_ratio=win_loss_ratio,
            portfolio_value=portfolio_value,
        )
        result2 = sizer.calculate_position_size(
            win_probability=win_probability,
            win_loss_ratio=win_loss_ratio,
            portfolio_value=portfolio_value,
        )

        assert result1.kelly_fraction == result2.kelly_fraction, (
            f"Kelly fraction not deterministic: "
            f"{result1.kelly_fraction} vs {result2.kelly_fraction}"
        )
        assert result1.clamped_fraction == result2.clamped_fraction, (
            f"Clamped fraction not deterministic: "
            f"{result1.clamped_fraction} vs {result2.clamped_fraction}"
        )
        assert result1.position_size == result2.position_size, (
            f"Position size not deterministic: {result1.position_size} vs {result2.position_size}"
        )

    @settings(max_examples=100)
    @given(
        win_probability=win_probability_strategy,
        win_loss_ratio=win_loss_ratio_strategy,
        portfolio_value=portfolio_value_strategy,
    )
    def test_multiple_sizers_produce_same_result(
        self,
        win_probability: float,
        win_loss_ratio: float,
        portfolio_value: Decimal,
    ) -> None:
        """
        Property: Multiple PositionSizer instances with same config
        SHALL produce identical results for the same inputs.

        **Validates: Requirements 6.1, 6.2**
        """
        sizer1 = PositionSizer()
        sizer2 = PositionSizer()

        result1 = sizer1.calculate_position_size(
            win_probability=win_probability,
            win_loss_ratio=win_loss_ratio,
            portfolio_value=portfolio_value,
        )
        result2 = sizer2.calculate_position_size(
            win_probability=win_probability,
            win_loss_ratio=win_loss_ratio,
            portfolio_value=portfolio_value,
        )

        assert result1.position_size == result2.position_size, (
            f"Different sizer instances produced different results: "
            f"{result1.position_size} vs {result2.position_size}"
        )

    @settings(max_examples=100)
    @given(
        win_probability=win_probability_strategy,
        win_loss_ratio=win_loss_ratio_strategy,
        portfolio_value=portfolio_value_strategy,
    )
    def test_result_contains_all_required_fields(
        self,
        win_probability: float,
        win_loss_ratio: float,
        portfolio_value: Decimal,
    ) -> None:
        """
        Property: PositionSizeResult SHALL contain all required fields
        with valid values.

        **Validates: Requirements 6.1, 6.2**
        """
        sizer = PositionSizer()

        result = sizer.calculate_position_size(
            win_probability=win_probability,
            win_loss_ratio=win_loss_ratio,
            portfolio_value=portfolio_value,
        )

        # Verify all fields exist and have valid types
        assert isinstance(result.kelly_fraction, float), "kelly_fraction should be float"
        assert isinstance(result.clamped_fraction, float), "clamped_fraction should be float"
        assert isinstance(result.position_size, Decimal), "position_size should be Decimal"
        assert isinstance(result.portfolio_value, Decimal), "portfolio_value should be Decimal"
        assert isinstance(result.max_position_pct, float), "max_position_pct should be float"
        assert isinstance(result.was_capped, bool), "was_capped should be bool"
        assert isinstance(result.was_negative, bool), "was_negative should be bool"
        assert isinstance(result.reasoning, str), "reasoning should be str"
        assert len(result.reasoning) > 0, "reasoning should not be empty"

    @settings(max_examples=100)
    @given(
        win_probability=win_probability_strategy,
        win_loss_ratio=win_loss_ratio_strategy,
        portfolio_value=portfolio_value_strategy,
        kelly_multiplier=kelly_multiplier_strategy,
    )
    def test_kelly_multiplier_reduces_position(
        self,
        win_probability: float,
        win_loss_ratio: float,
        portfolio_value: Decimal,
        kelly_multiplier: float,
    ) -> None:
        """
        Property: Kelly fraction multiplier SHALL reduce the clamped fraction
        proportionally (when not capped by max_position_pct).

        **Validates: Requirements 6.1, 6.2**
        """
        # Use high max_position_pct to avoid capping interference
        config_full = PositionSizerConfig(
            max_position_pct=1.0,
            kelly_fraction_multiplier=1.0,
        )
        config_reduced = PositionSizerConfig(
            max_position_pct=1.0,
            kelly_fraction_multiplier=kelly_multiplier,
        )

        sizer_full = PositionSizer(config=config_full)
        sizer_reduced = PositionSizer(config=config_reduced)

        result_full = sizer_full.calculate_position_size(
            win_probability=win_probability,
            win_loss_ratio=win_loss_ratio,
            portfolio_value=portfolio_value,
        )
        result_reduced = sizer_reduced.calculate_position_size(
            win_probability=win_probability,
            win_loss_ratio=win_loss_ratio,
            portfolio_value=portfolio_value,
        )

        # When Kelly is positive, reduced should be <= full
        if result_full.kelly_fraction > 0:
            assert result_reduced.clamped_fraction <= result_full.clamped_fraction + 1e-9, (
                f"Reduced Kelly ({result_reduced.clamped_fraction}) should be <= "
                f"full Kelly ({result_full.clamped_fraction}) "
                f"with multiplier {kelly_multiplier}"
            )

    @settings(max_examples=100)
    @given(
        portfolio_value=portfolio_value_strategy,
    )
    def test_max_position_value_consistency(
        self,
        portfolio_value: Decimal,
    ) -> None:
        """
        Property: get_max_position_value SHALL return max_position_pct * portfolio_value.

        **Validates: Requirements 6.2**
        """
        sizer = PositionSizer()

        max_value = sizer.get_max_position_value(portfolio_value)
        expected = portfolio_value * Decimal(str(sizer.max_position_pct))
        expected = expected.quantize(Decimal("0.00000001"))

        assert max_value == expected, (
            f"Max position value mismatch: expected {expected}, got {max_value}"
        )
