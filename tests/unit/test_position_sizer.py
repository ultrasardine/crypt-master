"""
Unit tests for PositionSizer.

Tests the position sizing system using Kelly Criterion including
optimal fraction calculation, position capping, and edge cases.

Requirements tested:
- 6.1: Calculate position size using Kelly Criterion: f* = (p * b - q) / b
       where p=win_probability, q=1-p, b=win/loss_ratio
- 6.2: Cap position size at configurable maximum (default 10% of portfolio)
"""

from decimal import Decimal

import pytest

from lib.risk import (
    PositionSizer,
    PositionSizerConfig,
)


@pytest.fixture
def config() -> PositionSizerConfig:
    """Create a PositionSizerConfig with default values."""
    return PositionSizerConfig()


@pytest.fixture
def sizer(config: PositionSizerConfig) -> PositionSizer:
    """Create a PositionSizer with default config."""
    return PositionSizer(config=config)


class TestKellyFractionCalculation:
    """Tests for Kelly Criterion calculation - Requirement 6.1."""

    def test_kelly_formula_basic(self, sizer: PositionSizer) -> None:
        """Test basic Kelly formula: f* = (p * b - q) / b."""
        # With p=0.6, b=1.0: f* = (0.6 * 1.0 - 0.4) / 1.0 = 0.2
        kelly = sizer.calculate_kelly_fraction(
            win_probability=0.6,
            win_loss_ratio=1.0,
        )
        assert kelly == pytest.approx(0.2, rel=0.001)

    def test_kelly_with_favorable_odds(self, sizer: PositionSizer) -> None:
        """Test Kelly with favorable win/loss ratio."""
        # With p=0.5, b=2.0: f* = (0.5 * 2.0 - 0.5) / 2.0 = 0.25
        kelly = sizer.calculate_kelly_fraction(
            win_probability=0.5,
            win_loss_ratio=2.0,
        )
        assert kelly == pytest.approx(0.25, rel=0.001)

    def test_kelly_with_high_win_probability(self, sizer: PositionSizer) -> None:
        """Test Kelly with high win probability."""
        # With p=0.7, b=1.5: f* = (0.7 * 1.5 - 0.3) / 1.5 = 0.5
        kelly = sizer.calculate_kelly_fraction(
            win_probability=0.7,
            win_loss_ratio=1.5,
        )
        assert kelly == pytest.approx(0.5, rel=0.001)

    def test_kelly_negative_edge(self, sizer: PositionSizer) -> None:
        """Test Kelly returns negative when no edge exists."""
        # With p=0.4, b=1.0: f* = (0.4 * 1.0 - 0.6) / 1.0 = -0.2
        kelly = sizer.calculate_kelly_fraction(
            win_probability=0.4,
            win_loss_ratio=1.0,
        )
        assert kelly == pytest.approx(-0.2, rel=0.001)
        assert kelly < 0

    def test_kelly_zero_edge(self, sizer: PositionSizer) -> None:
        """Test Kelly returns zero when edge is exactly zero."""
        # With p=0.5, b=1.0: f* = (0.5 * 1.0 - 0.5) / 1.0 = 0.0
        kelly = sizer.calculate_kelly_fraction(
            win_probability=0.5,
            win_loss_ratio=1.0,
        )
        assert kelly == pytest.approx(0.0, rel=0.001)

    def test_kelly_can_exceed_one(self, sizer: PositionSizer) -> None:
        """Test Kelly can exceed 1.0 with very favorable conditions."""
        # With p=0.9, b=2.0: f* = (0.9 * 2.0 - 0.1) / 2.0 = 0.85
        # With p=0.95, b=3.0: f* = (0.95 * 3.0 - 0.05) / 3.0 = 0.933
        kelly = sizer.calculate_kelly_fraction(
            win_probability=0.95,
            win_loss_ratio=3.0,
        )
        assert kelly > 0.9

    def test_kelly_with_extreme_win_probability(self, sizer: PositionSizer) -> None:
        """Test Kelly with win probability of 1.0."""
        # With p=1.0, b=1.0: f* = (1.0 * 1.0 - 0.0) / 1.0 = 1.0
        kelly = sizer.calculate_kelly_fraction(
            win_probability=1.0,
            win_loss_ratio=1.0,
        )
        assert kelly == pytest.approx(1.0, rel=0.001)

    def test_kelly_with_zero_win_probability(self, sizer: PositionSizer) -> None:
        """Test Kelly with win probability of 0.0."""
        # With p=0.0, b=1.0: f* = (0.0 * 1.0 - 1.0) / 1.0 = -1.0
        kelly = sizer.calculate_kelly_fraction(
            win_probability=0.0,
            win_loss_ratio=1.0,
        )
        assert kelly == pytest.approx(-1.0, rel=0.001)


class TestKellyFractionValidation:
    """Tests for Kelly fraction input validation."""

    def test_invalid_win_probability_above_one(self, sizer: PositionSizer) -> None:
        """Win probability above 1.0 should raise ValueError."""
        with pytest.raises(ValueError, match="win_probability must be between 0 and 1"):
            sizer.calculate_kelly_fraction(
                win_probability=1.5,
                win_loss_ratio=1.0,
            )

    def test_invalid_win_probability_negative(self, sizer: PositionSizer) -> None:
        """Negative win probability should raise ValueError."""
        with pytest.raises(ValueError, match="win_probability must be between 0 and 1"):
            sizer.calculate_kelly_fraction(
                win_probability=-0.1,
                win_loss_ratio=1.0,
            )

    def test_invalid_win_loss_ratio_zero(self, sizer: PositionSizer) -> None:
        """Zero win/loss ratio should raise ValueError."""
        with pytest.raises(ValueError, match="win_loss_ratio must be positive"):
            sizer.calculate_kelly_fraction(
                win_probability=0.5,
                win_loss_ratio=0.0,
            )

    def test_invalid_win_loss_ratio_negative(self, sizer: PositionSizer) -> None:
        """Negative win/loss ratio should raise ValueError."""
        with pytest.raises(ValueError, match="win_loss_ratio must be positive"):
            sizer.calculate_kelly_fraction(
                win_probability=0.5,
                win_loss_ratio=-1.0,
            )


class TestPositionSizeCapping:
    """Tests for position size capping - Requirement 6.2."""

    def test_default_max_position_is_ten_percent(self) -> None:
        """Default max position should be 10%."""
        config = PositionSizerConfig()
        assert config.max_position_pct == 0.10

    def test_position_capped_at_max(self, sizer: PositionSizer) -> None:
        """Position should be capped at max_position_pct."""
        # Kelly would suggest 50%, but should be capped at 10%
        result = sizer.calculate_position_size(
            win_probability=0.7,
            win_loss_ratio=1.5,
            portfolio_value=Decimal("10000.00"),
        )

        assert result.clamped_fraction == pytest.approx(0.10, rel=0.001)
        assert result.was_capped is True
        assert result.position_size == Decimal("1000.00000000")

    def test_position_not_capped_when_below_max(self, sizer: PositionSizer) -> None:
        """Position should not be capped when Kelly is below max."""
        # Kelly: (0.52 * 1.1 - 0.48) / 1.1 = 0.0836, below 10% cap
        result = sizer.calculate_position_size(
            win_probability=0.52,
            win_loss_ratio=1.1,
            portfolio_value=Decimal("10000.00"),
        )

        assert result.was_capped is False
        assert result.clamped_fraction < 0.10

    def test_custom_max_position_percentage(self) -> None:
        """Custom max position percentage should be respected."""
        config = PositionSizerConfig(max_position_pct=0.05)  # 5%
        sizer = PositionSizer(config=config)

        result = sizer.calculate_position_size(
            win_probability=0.7,
            win_loss_ratio=1.5,
            portfolio_value=Decimal("10000.00"),
        )

        assert result.clamped_fraction == pytest.approx(0.05, rel=0.001)
        assert result.was_capped is True
        assert result.position_size == Decimal("500.00000000")

    def test_negative_kelly_clamped_to_zero(self, sizer: PositionSizer) -> None:
        """Negative Kelly should be clamped to zero."""
        result = sizer.calculate_position_size(
            win_probability=0.4,
            win_loss_ratio=1.0,
            portfolio_value=Decimal("10000.00"),
        )

        assert result.kelly_fraction < 0
        assert result.clamped_fraction == 0.0
        assert result.was_negative is True
        assert result.position_size == Decimal("0.00000000")


class TestPositionSizeCalculation:
    """Tests for full position size calculation."""

    def test_position_size_calculation(self, sizer: PositionSizer) -> None:
        """Test complete position size calculation."""
        result = sizer.calculate_position_size(
            win_probability=0.55,
            win_loss_ratio=1.5,
            portfolio_value=Decimal("10000.00"),
        )

        # Kelly: (0.55 * 1.5 - 0.45) / 1.5 = 0.25
        # But capped at 10%
        assert result.kelly_fraction == pytest.approx(0.25, rel=0.001)
        assert result.clamped_fraction == pytest.approx(0.10, rel=0.001)
        assert result.position_size == Decimal("1000.00000000")
        assert result.was_capped is True

    def test_position_size_with_small_kelly(self, sizer: PositionSizer) -> None:
        """Test position size when Kelly is small."""
        # Kelly: (0.52 * 1.1 - 0.48) / 1.1 = 0.0836
        result = sizer.calculate_position_size(
            win_probability=0.52,
            win_loss_ratio=1.1,
            portfolio_value=Decimal("10000.00"),
        )

        expected_kelly = (0.52 * 1.1 - 0.48) / 1.1
        assert result.kelly_fraction == pytest.approx(expected_kelly, rel=0.001)
        assert result.clamped_fraction == pytest.approx(expected_kelly, rel=0.001)
        assert result.was_capped is False

    def test_position_size_with_zero_portfolio(self, sizer: PositionSizer) -> None:
        """Test position size with zero portfolio value."""
        result = sizer.calculate_position_size(
            win_probability=0.6,
            win_loss_ratio=1.5,
            portfolio_value=Decimal("0.00"),
        )

        assert result.position_size == Decimal("0")
        assert result.clamped_fraction == 0.0

    def test_position_size_with_large_portfolio(self, sizer: PositionSizer) -> None:
        """Test position size with large portfolio value."""
        result = sizer.calculate_position_size(
            win_probability=0.6,
            win_loss_ratio=1.5,
            portfolio_value=Decimal("1000000.00"),
        )

        # 10% of 1M = 100K
        assert result.position_size == Decimal("100000.00000000")

    def test_position_size_precision(self, sizer: PositionSizer) -> None:
        """Test position size has correct decimal precision."""
        result = sizer.calculate_position_size(
            win_probability=0.55,
            win_loss_ratio=1.2,
            portfolio_value=Decimal("12345.67890123"),
        )

        # Should be rounded to 8 decimal places
        assert result.position_size == result.position_size.quantize(Decimal("0.00000001"))


class TestPositionSizeResult:
    """Tests for PositionSizeResult dataclass."""

    def test_result_contains_all_fields(self, sizer: PositionSizer) -> None:
        """Result should contain all expected fields."""
        result = sizer.calculate_position_size(
            win_probability=0.6,
            win_loss_ratio=1.5,
            portfolio_value=Decimal("10000.00"),
        )

        assert hasattr(result, "kelly_fraction")
        assert hasattr(result, "clamped_fraction")
        assert hasattr(result, "position_size")
        assert hasattr(result, "portfolio_value")
        assert hasattr(result, "max_position_pct")
        assert hasattr(result, "was_capped")
        assert hasattr(result, "was_negative")
        assert hasattr(result, "reasoning")

    def test_result_is_immutable(self, sizer: PositionSizer) -> None:
        """PositionSizeResult should be immutable (frozen)."""
        result = sizer.calculate_position_size(
            win_probability=0.6,
            win_loss_ratio=1.5,
            portfolio_value=Decimal("10000.00"),
        )

        with pytest.raises(AttributeError):
            result.position_size = Decimal("5000.00")  # type: ignore

    def test_result_has_reasoning(self, sizer: PositionSizer) -> None:
        """Result should have human-readable reasoning."""
        result = sizer.calculate_position_size(
            win_probability=0.6,
            win_loss_ratio=1.5,
            portfolio_value=Decimal("10000.00"),
        )

        assert result.reasoning is not None
        assert len(result.reasoning) > 0

    def test_reasoning_mentions_capping(self, sizer: PositionSizer) -> None:
        """Reasoning should mention when position is capped."""
        result = sizer.calculate_position_size(
            win_probability=0.7,
            win_loss_ratio=1.5,
            portfolio_value=Decimal("10000.00"),
        )

        assert result.was_capped is True
        assert "capped" in result.reasoning.lower() or "maximum" in result.reasoning.lower()

    def test_reasoning_mentions_negative_edge(self, sizer: PositionSizer) -> None:
        """Reasoning should mention when no edge exists."""
        result = sizer.calculate_position_size(
            win_probability=0.4,
            win_loss_ratio=1.0,
            portfolio_value=Decimal("10000.00"),
        )

        assert result.was_negative is True
        assert "negative" in result.reasoning.lower() or "no position" in result.reasoning.lower()


class TestPositionSizerConfig:
    """Tests for PositionSizerConfig validation."""

    def test_default_config_values(self) -> None:
        """Default config should have correct values."""
        config = PositionSizerConfig()

        assert config.max_position_pct == 0.10
        assert config.kelly_fraction_multiplier == 1.0

    def test_invalid_max_position_pct_zero(self) -> None:
        """Zero max_position_pct should raise ValueError."""
        with pytest.raises(ValueError, match="max_position_pct"):
            PositionSizerConfig(max_position_pct=0.0)

    def test_invalid_max_position_pct_negative(self) -> None:
        """Negative max_position_pct should raise ValueError."""
        with pytest.raises(ValueError, match="max_position_pct"):
            PositionSizerConfig(max_position_pct=-0.1)

    def test_invalid_max_position_pct_above_one(self) -> None:
        """max_position_pct above 1.0 should raise ValueError."""
        with pytest.raises(ValueError, match="max_position_pct"):
            PositionSizerConfig(max_position_pct=1.5)

    def test_valid_max_position_pct_one(self) -> None:
        """max_position_pct of 1.0 should be valid."""
        config = PositionSizerConfig(max_position_pct=1.0)
        assert config.max_position_pct == 1.0

    def test_invalid_kelly_multiplier_zero(self) -> None:
        """Zero kelly_fraction_multiplier should raise ValueError."""
        with pytest.raises(ValueError, match="kelly_fraction_multiplier"):
            PositionSizerConfig(kelly_fraction_multiplier=0.0)

    def test_invalid_kelly_multiplier_negative(self) -> None:
        """Negative kelly_fraction_multiplier should raise ValueError."""
        with pytest.raises(ValueError, match="kelly_fraction_multiplier"):
            PositionSizerConfig(kelly_fraction_multiplier=-0.5)

    def test_invalid_kelly_multiplier_above_one(self) -> None:
        """kelly_fraction_multiplier above 1.0 should raise ValueError."""
        with pytest.raises(ValueError, match="kelly_fraction_multiplier"):
            PositionSizerConfig(kelly_fraction_multiplier=1.5)


class TestKellyFractionMultiplier:
    """Tests for Kelly fraction multiplier (fractional Kelly)."""

    def test_half_kelly(self) -> None:
        """Half Kelly should reduce position by 50%."""
        config = PositionSizerConfig(
            max_position_pct=1.0,  # No cap
            kelly_fraction_multiplier=0.5,
        )
        sizer = PositionSizer(config=config)

        # Full Kelly would be 0.2
        result = sizer.calculate_position_size(
            win_probability=0.6,
            win_loss_ratio=1.0,
            portfolio_value=Decimal("10000.00"),
        )

        # Half Kelly: 0.2 * 0.5 = 0.1
        assert result.clamped_fraction == pytest.approx(0.1, rel=0.001)
        assert result.position_size == Decimal("1000.00000000")

    def test_quarter_kelly(self) -> None:
        """Quarter Kelly should reduce position by 75%."""
        config = PositionSizerConfig(
            max_position_pct=1.0,  # No cap
            kelly_fraction_multiplier=0.25,
        )
        sizer = PositionSizer(config=config)

        # Full Kelly would be 0.2
        result = sizer.calculate_position_size(
            win_probability=0.6,
            win_loss_ratio=1.0,
            portfolio_value=Decimal("10000.00"),
        )

        # Quarter Kelly: 0.2 * 0.25 = 0.05
        assert result.clamped_fraction == pytest.approx(0.05, rel=0.001)


class TestMaxPositionValue:
    """Tests for get_max_position_value method."""

    def test_max_position_value(self, sizer: PositionSizer) -> None:
        """Test max position value calculation."""
        max_value = sizer.get_max_position_value(Decimal("10000.00"))

        # 10% of 10000 = 1000
        assert max_value == Decimal("1000.00000000")

    def test_max_position_value_with_custom_config(self) -> None:
        """Test max position value with custom config."""
        config = PositionSizerConfig(max_position_pct=0.25)
        sizer = PositionSizer(config=config)

        max_value = sizer.get_max_position_value(Decimal("10000.00"))

        # 25% of 10000 = 2500
        assert max_value == Decimal("2500.00000000")

    def test_max_position_value_zero_portfolio(self, sizer: PositionSizer) -> None:
        """Test max position value with zero portfolio."""
        max_value = sizer.get_max_position_value(Decimal("0.00"))
        assert max_value == Decimal("0.00000000")

    def test_max_position_value_negative_portfolio_raises(self, sizer: PositionSizer) -> None:
        """Negative portfolio value should raise ValueError."""
        with pytest.raises(ValueError, match="portfolio_value must be non-negative"):
            sizer.get_max_position_value(Decimal("-1000.00"))


class TestEdgeCases:
    """Tests for edge cases."""

    def test_very_small_win_probability(self, sizer: PositionSizer) -> None:
        """Test with very small win probability."""
        result = sizer.calculate_position_size(
            win_probability=0.01,
            win_loss_ratio=1.0,
            portfolio_value=Decimal("10000.00"),
        )

        assert result.was_negative is True
        assert result.position_size == Decimal("0.00000000")

    def test_very_high_win_loss_ratio(self, sizer: PositionSizer) -> None:
        """Test with very high win/loss ratio."""
        result = sizer.calculate_position_size(
            win_probability=0.5,
            win_loss_ratio=10.0,
            portfolio_value=Decimal("10000.00"),
        )

        # Kelly: (0.5 * 10 - 0.5) / 10 = 0.45
        # Capped at 10%
        assert result.kelly_fraction == pytest.approx(0.45, rel=0.001)
        assert result.clamped_fraction == pytest.approx(0.10, rel=0.001)
        assert result.was_capped is True

    def test_very_small_win_loss_ratio(self, sizer: PositionSizer) -> None:
        """Test with very small win/loss ratio."""
        result = sizer.calculate_position_size(
            win_probability=0.8,
            win_loss_ratio=0.1,
            portfolio_value=Decimal("10000.00"),
        )

        # Kelly: (0.8 * 0.1 - 0.2) / 0.1 = -1.2
        assert result.kelly_fraction < 0
        assert result.was_negative is True
        assert result.position_size == Decimal("0.00000000")

    def test_negative_portfolio_value_raises(self, sizer: PositionSizer) -> None:
        """Negative portfolio value should raise ValueError."""
        with pytest.raises(ValueError, match="portfolio_value must be non-negative"):
            sizer.calculate_position_size(
                win_probability=0.6,
                win_loss_ratio=1.5,
                portfolio_value=Decimal("-1000.00"),
            )

    def test_boundary_win_probability_zero(self, sizer: PositionSizer) -> None:
        """Test with win probability of exactly 0."""
        result = sizer.calculate_position_size(
            win_probability=0.0,
            win_loss_ratio=1.0,
            portfolio_value=Decimal("10000.00"),
        )

        assert result.kelly_fraction == pytest.approx(-1.0, rel=0.001)
        assert result.was_negative is True
        assert result.position_size == Decimal("0.00000000")

    def test_boundary_win_probability_one(self, sizer: PositionSizer) -> None:
        """Test with win probability of exactly 1."""
        result = sizer.calculate_position_size(
            win_probability=1.0,
            win_loss_ratio=1.0,
            portfolio_value=Decimal("10000.00"),
        )

        assert result.kelly_fraction == pytest.approx(1.0, rel=0.001)
        # Capped at 10%
        assert result.clamped_fraction == pytest.approx(0.10, rel=0.001)
        assert result.was_capped is True


class TestClampKellyFraction:
    """Tests for clamp_kelly_fraction method."""

    def test_clamp_negative_to_zero(self, sizer: PositionSizer) -> None:
        """Negative Kelly should be clamped to zero."""
        clamped = sizer.clamp_kelly_fraction(-0.5)
        assert clamped == 0.0

    def test_clamp_above_one_to_max(self, sizer: PositionSizer) -> None:
        """Kelly above 1.0 should be clamped to max_position_pct."""
        clamped = sizer.clamp_kelly_fraction(1.5)
        assert clamped == pytest.approx(0.10, rel=0.001)

    def test_clamp_above_max_to_max(self, sizer: PositionSizer) -> None:
        """Kelly above max_position_pct should be clamped."""
        clamped = sizer.clamp_kelly_fraction(0.5)
        assert clamped == pytest.approx(0.10, rel=0.001)

    def test_clamp_below_max_unchanged(self, sizer: PositionSizer) -> None:
        """Kelly below max_position_pct should be unchanged."""
        clamped = sizer.clamp_kelly_fraction(0.05)
        assert clamped == pytest.approx(0.05, rel=0.001)

    def test_clamp_zero_unchanged(self, sizer: PositionSizer) -> None:
        """Zero Kelly should remain zero."""
        clamped = sizer.clamp_kelly_fraction(0.0)
        assert clamped == 0.0
