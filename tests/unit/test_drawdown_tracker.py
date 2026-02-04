"""
Unit tests for DrawdownTracker.

Tests the drawdown tracking functionality including:
- High water mark tracking
- Drawdown calculation
- Trading halt when limit breached
- Reset functionality

Requirements:
- 6.3: Track portfolio high water mark and current drawdown percentage
- 6.4: Halt all trading when drawdown exceeds configurable limit (default 20%)
"""

from decimal import Decimal

import pytest

from lib.risk import DrawdownTracker, DrawdownTrackerConfig


class TestDrawdownTrackerConfig:
    """Tests for DrawdownTrackerConfig validation."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = DrawdownTrackerConfig()
        assert config.max_drawdown_pct == 0.20

    def test_custom_max_drawdown(self) -> None:
        """Test custom max drawdown percentage."""
        config = DrawdownTrackerConfig(max_drawdown_pct=0.15)
        assert config.max_drawdown_pct == 0.15

    def test_max_drawdown_at_boundary(self) -> None:
        """Test max drawdown at 100%."""
        config = DrawdownTrackerConfig(max_drawdown_pct=1.0)
        assert config.max_drawdown_pct == 1.0

    def test_invalid_max_drawdown_zero(self) -> None:
        """Test that zero max drawdown raises error."""
        with pytest.raises(ValueError, match="max_drawdown_pct must be between"):
            DrawdownTrackerConfig(max_drawdown_pct=0.0)

    def test_invalid_max_drawdown_negative(self) -> None:
        """Test that negative max drawdown raises error."""
        with pytest.raises(ValueError, match="max_drawdown_pct must be between"):
            DrawdownTrackerConfig(max_drawdown_pct=-0.1)

    def test_invalid_max_drawdown_over_one(self) -> None:
        """Test that max drawdown over 100% raises error."""
        with pytest.raises(ValueError, match="max_drawdown_pct must be between"):
            DrawdownTrackerConfig(max_drawdown_pct=1.5)


class TestDrawdownTrackerInitialization:
    """Tests for DrawdownTracker initialization."""

    def test_init_without_initial_value(self) -> None:
        """Test initialization without initial value."""
        tracker = DrawdownTracker()
        assert tracker.high_water_mark is None
        assert tracker.current_value is None
        assert tracker.is_halted is False

    def test_init_with_initial_value(self) -> None:
        """Test initialization with initial value."""
        tracker = DrawdownTracker(initial_value=Decimal("10000.00"))
        assert tracker.high_water_mark == Decimal("10000.00")
        assert tracker.current_value == Decimal("10000.00")
        assert tracker.is_halted is False

    def test_init_with_custom_config(self) -> None:
        """Test initialization with custom config."""
        config = DrawdownTrackerConfig(max_drawdown_pct=0.15)
        tracker = DrawdownTracker(config=config)
        assert tracker.max_drawdown_pct == 0.15

    def test_init_with_zero_value(self) -> None:
        """Test initialization with zero value."""
        tracker = DrawdownTracker(initial_value=Decimal("0"))
        assert tracker.high_water_mark == Decimal("0")
        assert tracker.current_value == Decimal("0")

    def test_init_with_negative_value_raises(self) -> None:
        """Test that negative initial value raises error."""
        with pytest.raises(ValueError, match="initial_value must be non-negative"):
            DrawdownTracker(initial_value=Decimal("-100"))


class TestDrawdownTrackerUpdate:
    """Tests for DrawdownTracker.update() method."""

    def test_update_increases_high_water_mark(self) -> None:
        """Test that update increases high water mark when value rises."""
        tracker = DrawdownTracker(initial_value=Decimal("10000.00"))

        status = tracker.update(Decimal("11000.00"))

        assert tracker.high_water_mark == Decimal("11000.00")
        assert tracker.current_value == Decimal("11000.00")
        assert status.drawdown_pct == 0.0

    def test_update_maintains_high_water_mark_on_decrease(self) -> None:
        """Test that high water mark is maintained when value decreases."""
        tracker = DrawdownTracker(initial_value=Decimal("10000.00"))

        status = tracker.update(Decimal("9000.00"))

        assert tracker.high_water_mark == Decimal("10000.00")
        assert tracker.current_value == Decimal("9000.00")
        assert status.drawdown_pct == pytest.approx(0.10)

    def test_update_calculates_correct_drawdown(self) -> None:
        """Test drawdown calculation accuracy."""
        tracker = DrawdownTracker(initial_value=Decimal("10000.00"))

        # 15% drawdown
        status = tracker.update(Decimal("8500.00"))

        assert status.drawdown_amount == Decimal("1500.00")
        assert status.drawdown_pct == pytest.approx(0.15)

    def test_update_with_negative_value_raises(self) -> None:
        """Test that negative portfolio value raises error."""
        tracker = DrawdownTracker(initial_value=Decimal("10000.00"))

        with pytest.raises(ValueError, match="portfolio_value must be non-negative"):
            tracker.update(Decimal("-100"))

    def test_update_sequence(self) -> None:
        """Test a sequence of updates."""
        tracker = DrawdownTracker(initial_value=Decimal("10000.00"))

        # Value increases
        tracker.update(Decimal("12000.00"))
        assert tracker.high_water_mark == Decimal("12000.00")

        # Value decreases
        tracker.update(Decimal("11000.00"))
        assert tracker.high_water_mark == Decimal("12000.00")
        assert tracker.current_value == Decimal("11000.00")

        # Value increases again but not to new high
        tracker.update(Decimal("11500.00"))
        assert tracker.high_water_mark == Decimal("12000.00")

        # Value reaches new high
        tracker.update(Decimal("13000.00"))
        assert tracker.high_water_mark == Decimal("13000.00")


class TestDrawdownCalculation:
    """Tests for drawdown calculation."""

    def test_zero_drawdown(self) -> None:
        """Test zero drawdown when at high water mark."""
        tracker = DrawdownTracker(initial_value=Decimal("10000.00"))

        assert tracker.calculate_drawdown() == 0.0

    def test_drawdown_percentage(self) -> None:
        """Test drawdown percentage calculation."""
        tracker = DrawdownTracker(initial_value=Decimal("10000.00"))
        tracker.update(Decimal("8000.00"))

        # (10000 - 8000) / 10000 = 0.20
        assert tracker.calculate_drawdown() == pytest.approx(0.20)

    def test_drawdown_with_no_values(self) -> None:
        """Test drawdown returns 0 when no values recorded."""
        tracker = DrawdownTracker()

        assert tracker.calculate_drawdown() == 0.0

    def test_drawdown_with_zero_high_water_mark(self) -> None:
        """Test drawdown with zero high water mark."""
        tracker = DrawdownTracker(initial_value=Decimal("0"))

        assert tracker.calculate_drawdown() == 0.0


class TestTradingHalt:
    """Tests for trading halt functionality."""

    def test_trading_allowed_within_limit(self) -> None:
        """Test trading is allowed when within drawdown limit."""
        tracker = DrawdownTracker(initial_value=Decimal("10000.00"))
        tracker.update(Decimal("9000.00"))  # 10% drawdown

        assert tracker.is_trading_allowed() is True
        assert tracker.is_halted is False

    def test_trading_halted_when_limit_breached(self) -> None:
        """Test trading is halted when drawdown exceeds limit."""
        tracker = DrawdownTracker(initial_value=Decimal("10000.00"))

        # 25% drawdown exceeds default 20% limit
        status = tracker.update(Decimal("7500.00"))

        assert status.is_breached is True
        assert status.is_trading_allowed is False
        assert tracker.is_halted is True
        assert tracker.is_trading_allowed() is False

    def test_trading_remains_halted_after_recovery(self) -> None:
        """Test trading remains halted even if value recovers."""
        tracker = DrawdownTracker(initial_value=Decimal("10000.00"))

        # Breach the limit
        tracker.update(Decimal("7500.00"))
        assert tracker.is_halted is True

        # Value recovers
        tracker.update(Decimal("9500.00"))

        # Still halted - requires manual reset
        assert tracker.is_halted is True
        assert tracker.is_trading_allowed() is False

    def test_trading_halted_at_exact_limit(self) -> None:
        """Test trading is NOT halted at exactly the limit (only when exceeded)."""
        config = DrawdownTrackerConfig(max_drawdown_pct=0.20)
        tracker = DrawdownTracker(
            initial_value=Decimal("10000.00"),
            config=config,
        )

        # Exactly 20% drawdown - at limit but not exceeded
        status = tracker.update(Decimal("8000.00"))

        assert status.drawdown_pct == pytest.approx(0.20)
        assert status.is_breached is False
        assert tracker.is_trading_allowed() is True

    def test_trading_halted_just_over_limit(self) -> None:
        """Test trading is halted when just over the limit."""
        config = DrawdownTrackerConfig(max_drawdown_pct=0.20)
        tracker = DrawdownTracker(
            initial_value=Decimal("10000.00"),
            config=config,
        )

        # 20.01% drawdown - just over limit
        status = tracker.update(Decimal("7999.00"))

        assert status.is_breached is True
        assert tracker.is_trading_allowed() is False

    def test_custom_drawdown_limit(self) -> None:
        """Test with custom drawdown limit."""
        config = DrawdownTrackerConfig(max_drawdown_pct=0.10)
        tracker = DrawdownTracker(
            initial_value=Decimal("10000.00"),
            config=config,
        )

        # 15% drawdown exceeds 10% limit
        status = tracker.update(Decimal("8500.00"))

        assert status.is_breached is True
        assert tracker.is_trading_allowed() is False


class TestDrawdownTrackerReset:
    """Tests for DrawdownTracker.reset() method."""

    def test_reset_clears_halted_state(self) -> None:
        """Test that reset clears the halted state."""
        tracker = DrawdownTracker(initial_value=Decimal("10000.00"))

        # Breach the limit
        tracker.update(Decimal("7500.00"))
        assert tracker.is_halted is True

        # Reset
        status = tracker.reset()

        assert tracker.is_halted is False
        assert status.is_trading_allowed is True

    def test_reset_updates_high_water_mark_to_current(self) -> None:
        """Test that reset updates high water mark to current value."""
        tracker = DrawdownTracker(initial_value=Decimal("10000.00"))
        tracker.update(Decimal("7500.00"))

        status = tracker.reset()

        assert tracker.high_water_mark == Decimal("7500.00")
        assert status.drawdown_pct == 0.0

    def test_reset_with_new_value(self) -> None:
        """Test reset with a new value."""
        tracker = DrawdownTracker(initial_value=Decimal("10000.00"))
        tracker.update(Decimal("7500.00"))

        status = tracker.reset(new_value=Decimal("8000.00"))

        assert tracker.high_water_mark == Decimal("8000.00")
        assert tracker.current_value == Decimal("8000.00")
        assert status.drawdown_pct == 0.0

    def test_reset_with_negative_value_raises(self) -> None:
        """Test that reset with negative value raises error."""
        tracker = DrawdownTracker(initial_value=Decimal("10000.00"))

        with pytest.raises(ValueError, match="new_value must be non-negative"):
            tracker.reset(new_value=Decimal("-100"))


class TestDrawdownStatus:
    """Tests for DrawdownStatus dataclass."""

    def test_get_status_returns_correct_values(self) -> None:
        """Test get_status returns correct DrawdownStatus."""
        tracker = DrawdownTracker(initial_value=Decimal("10000.00"))
        tracker.update(Decimal("8500.00"))

        status = tracker.get_status()

        assert status.high_water_mark == Decimal("10000.00")
        assert status.current_value == Decimal("8500.00")
        assert status.drawdown_amount == Decimal("1500.00")
        assert status.drawdown_pct == pytest.approx(0.15)
        assert status.max_drawdown_pct == 0.20
        assert status.is_breached is False
        assert status.is_trading_allowed is True
        assert "within limits" in status.reasoning.lower()

    def test_status_reasoning_warning(self) -> None:
        """Test status reasoning shows warning when approaching limit."""
        tracker = DrawdownTracker(initial_value=Decimal("10000.00"))

        # 17% drawdown - above 80% of 20% limit
        tracker.update(Decimal("8300.00"))

        status = tracker.get_status()
        assert "warning" in status.reasoning.lower()

    def test_status_reasoning_breached(self) -> None:
        """Test status reasoning shows breach message."""
        tracker = DrawdownTracker(initial_value=Decimal("10000.00"))
        tracker.update(Decimal("7500.00"))

        status = tracker.get_status()
        assert "halted" in status.reasoning.lower()

    def test_status_with_no_values(self) -> None:
        """Test status when no values have been recorded."""
        tracker = DrawdownTracker()

        status = tracker.get_status()

        assert status.high_water_mark == Decimal("0")
        assert status.current_value == Decimal("0")
        assert status.drawdown_pct == 0.0
        assert status.is_trading_allowed is True


class TestSetHighWaterMark:
    """Tests for set_high_water_mark method."""

    def test_set_high_water_mark(self) -> None:
        """Test manually setting high water mark."""
        tracker = DrawdownTracker()

        tracker.set_high_water_mark(Decimal("15000.00"))

        assert tracker.high_water_mark == Decimal("15000.00")

    def test_set_high_water_mark_negative_raises(self) -> None:
        """Test that negative high water mark raises error."""
        tracker = DrawdownTracker()

        with pytest.raises(ValueError, match="value must be non-negative"):
            tracker.set_high_water_mark(Decimal("-100"))

    def test_set_high_water_mark_affects_drawdown(self) -> None:
        """Test that setting high water mark affects drawdown calculation."""
        tracker = DrawdownTracker(initial_value=Decimal("10000.00"))

        # Set a higher high water mark
        tracker.set_high_water_mark(Decimal("12000.00"))

        # Now drawdown is calculated from 12000
        # (12000 - 10000) / 12000 = 0.1667
        assert tracker.calculate_drawdown() == pytest.approx(0.1667, rel=0.01)


class TestEdgeCases:
    """Tests for edge cases."""

    def test_very_small_values(self) -> None:
        """Test with very small portfolio values."""
        tracker = DrawdownTracker(initial_value=Decimal("0.00000001"))
        tracker.update(Decimal("0.000000008"))

        assert tracker.calculate_drawdown() == pytest.approx(0.20)

    def test_very_large_values(self) -> None:
        """Test with very large portfolio values."""
        tracker = DrawdownTracker(initial_value=Decimal("1000000000000.00"))
        tracker.update(Decimal("800000000000.00"))

        assert tracker.calculate_drawdown() == pytest.approx(0.20)

    def test_decimal_precision(self) -> None:
        """Test decimal precision is maintained."""
        tracker = DrawdownTracker(initial_value=Decimal("10000.12345678"))
        tracker.update(Decimal("8000.12345678"))

        status = tracker.get_status()
        assert status.drawdown_amount == Decimal("2000.00000000")

    def test_multiple_breaches(self) -> None:
        """Test behavior with multiple drawdown breaches."""
        tracker = DrawdownTracker(initial_value=Decimal("10000.00"))

        # First breach
        tracker.update(Decimal("7500.00"))
        assert tracker.is_halted is True

        # Reset
        tracker.reset()
        assert tracker.is_halted is False

        # Second breach
        tracker.update(Decimal("5000.00"))
        assert tracker.is_halted is True
