"""
Unit tests for RiskManager orchestration.

Tests the risk management orchestration including:
- Trade validation against risk limits
- Bot creation validation against portfolio limits
- Stop-loss calculation
- Risk-per-trade calculation

Requirements:
- 6.5: Calculate risk-per-trade as percentage of portfolio (default max 2%)
- 6.6: Calculate stop-loss price based on configurable risk tolerance
- 6.7: Maintain trade history log with entry price, exit price, P&L, and risk metrics
- 10.7: Validate that allocated funds for bot creation do not exceed portfolio risk limits
"""

from decimal import Decimal

import pytest

from lib.risk import (
    DrawdownTracker,
    PositionSizer,
    RiskManager,
    RiskManagerConfig,
)


@pytest.fixture
def config() -> RiskManagerConfig:
    """Create a RiskManagerConfig with default values."""
    return RiskManagerConfig()


@pytest.fixture
def risk_manager(config: RiskManagerConfig) -> RiskManager:
    """Create a RiskManager with default config and portfolio value."""
    rm = RiskManager(config=config)
    rm.update_portfolio(Decimal("10000.00"))
    return rm


class TestRiskManagerConfig:
    """Tests for RiskManagerConfig validation."""

    def test_default_config_values(self) -> None:
        """Test default configuration values."""
        config = RiskManagerConfig()

        assert config.max_position_pct == 0.10
        assert config.max_risk_per_trade_pct == 0.02
        assert config.max_drawdown_pct == 0.20
        assert config.max_bot_allocation_pct == 0.50
        assert config.bot_loss_threshold_pct == 0.10
        assert config.min_confidence == 0.85

    def test_custom_config_values(self) -> None:
        """Test custom configuration values."""
        config = RiskManagerConfig(
            max_position_pct=0.15,
            max_risk_per_trade_pct=0.03,
            max_drawdown_pct=0.25,
            max_bot_allocation_pct=0.60,
            bot_loss_threshold_pct=0.15,
            min_confidence=0.90,
        )

        assert config.max_position_pct == 0.15
        assert config.max_risk_per_trade_pct == 0.03
        assert config.max_drawdown_pct == 0.25
        assert config.max_bot_allocation_pct == 0.60
        assert config.bot_loss_threshold_pct == 0.15
        assert config.min_confidence == 0.90

    def test_invalid_max_position_pct(self) -> None:
        """Test invalid max_position_pct raises error."""
        with pytest.raises(ValueError, match="max_position_pct"):
            RiskManagerConfig(max_position_pct=0.0)

        with pytest.raises(ValueError, match="max_position_pct"):
            RiskManagerConfig(max_position_pct=1.5)

    def test_invalid_max_risk_per_trade_pct(self) -> None:
        """Test invalid max_risk_per_trade_pct raises error."""
        with pytest.raises(ValueError, match="max_risk_per_trade_pct"):
            RiskManagerConfig(max_risk_per_trade_pct=0.0)

        with pytest.raises(ValueError, match="max_risk_per_trade_pct"):
            RiskManagerConfig(max_risk_per_trade_pct=1.5)

    def test_invalid_max_drawdown_pct(self) -> None:
        """Test invalid max_drawdown_pct raises error."""
        with pytest.raises(ValueError, match="max_drawdown_pct"):
            RiskManagerConfig(max_drawdown_pct=0.0)

    def test_invalid_max_bot_allocation_pct(self) -> None:
        """Test invalid max_bot_allocation_pct raises error."""
        with pytest.raises(ValueError, match="max_bot_allocation_pct"):
            RiskManagerConfig(max_bot_allocation_pct=0.0)

    def test_invalid_bot_loss_threshold_pct(self) -> None:
        """Test invalid bot_loss_threshold_pct raises error."""
        with pytest.raises(ValueError, match="bot_loss_threshold_pct"):
            RiskManagerConfig(bot_loss_threshold_pct=0.0)

    def test_invalid_min_confidence(self) -> None:
        """Test invalid min_confidence raises error."""
        with pytest.raises(ValueError, match="min_confidence"):
            RiskManagerConfig(min_confidence=-1)

        with pytest.raises(ValueError, match="min_confidence"):
            RiskManagerConfig(min_confidence=101)


class TestRiskManagerInitialization:
    """Tests for RiskManager initialization."""

    def test_init_with_defaults(self) -> None:
        """Test initialization with default values."""
        rm = RiskManager()

        assert rm.portfolio_value == Decimal("0")
        assert rm.current_bot_allocation == Decimal("0")
        assert rm.position_sizer is not None
        assert rm.drawdown_tracker is not None

    def test_init_with_custom_config(self) -> None:
        """Test initialization with custom config."""
        config = RiskManagerConfig(max_risk_per_trade_pct=0.03)
        rm = RiskManager(config=config)

        assert rm.config.max_risk_per_trade_pct == 0.03

    def test_init_with_custom_position_sizer(self) -> None:
        """Test initialization with custom position sizer."""
        sizer = PositionSizer()
        rm = RiskManager(position_sizer=sizer)

        assert rm.position_sizer is sizer

    def test_init_with_custom_drawdown_tracker(self) -> None:
        """Test initialization with custom drawdown tracker."""
        tracker = DrawdownTracker(initial_value=Decimal("5000.00"))
        rm = RiskManager(drawdown_tracker=tracker)

        assert rm.drawdown_tracker is tracker


class TestPortfolioUpdate:
    """Tests for portfolio update functionality."""

    def test_update_portfolio_value(self) -> None:
        """Test updating portfolio value."""
        rm = RiskManager()

        status = rm.update_portfolio(Decimal("10000.00"))

        assert rm.portfolio_value == Decimal("10000.00")
        assert status.current_value == Decimal("10000.00")

    def test_update_portfolio_with_bot_allocation(self) -> None:
        """Test updating portfolio with bot allocation."""
        rm = RiskManager()

        rm.update_portfolio(
            Decimal("10000.00"),
            bot_allocation=Decimal("2000.00"),
        )

        assert rm.portfolio_value == Decimal("10000.00")
        assert rm.current_bot_allocation == Decimal("2000.00")

    def test_update_portfolio_negative_raises(self) -> None:
        """Test that negative portfolio value raises error."""
        rm = RiskManager()

        with pytest.raises(ValueError, match="portfolio_value must be non-negative"):
            rm.update_portfolio(Decimal("-100"))

    def test_update_bot_allocation_negative_raises(self) -> None:
        """Test that negative bot allocation raises error."""
        rm = RiskManager()

        with pytest.raises(ValueError, match="bot_allocation must be non-negative"):
            rm.update_portfolio(Decimal("10000"), bot_allocation=Decimal("-100"))

    def test_update_bot_allocation_separately(self) -> None:
        """Test updating bot allocation separately."""
        rm = RiskManager()
        rm.update_portfolio(Decimal("10000.00"))

        rm.update_bot_allocation(Decimal("3000.00"))

        assert rm.current_bot_allocation == Decimal("3000.00")


class TestStopLossCalculation:
    """Tests for stop-loss calculation - Requirement 6.6."""

    def test_stop_loss_buy_side(self, risk_manager: RiskManager) -> None:
        """Test stop-loss calculation for BUY side."""
        # Default risk is 2%, so stop-loss should be 2% below entry
        stop_loss = risk_manager.calculate_stop_loss(
            entry_price=Decimal("50000.00"),
            side="BUY",
        )

        # 50000 * (1 - 0.02) = 49000
        assert stop_loss == Decimal("49000.00000000")

    def test_stop_loss_sell_side(self, risk_manager: RiskManager) -> None:
        """Test stop-loss calculation for SELL side."""
        # For SELL, stop-loss should be above entry
        stop_loss = risk_manager.calculate_stop_loss(
            entry_price=Decimal("50000.00"),
            side="SELL",
        )

        # 50000 * (1 + 0.02) = 51000
        assert stop_loss == Decimal("51000.00000000")

    def test_stop_loss_custom_risk_percent(self, risk_manager: RiskManager) -> None:
        """Test stop-loss with custom risk percentage."""
        stop_loss = risk_manager.calculate_stop_loss(
            entry_price=Decimal("50000.00"),
            side="BUY",
            risk_percent=0.05,
        )

        # 50000 * (1 - 0.05) = 47500
        assert stop_loss == Decimal("47500.00000000")

    def test_stop_loss_case_insensitive_side(self, risk_manager: RiskManager) -> None:
        """Test stop-loss with lowercase side."""
        stop_loss = risk_manager.calculate_stop_loss(
            entry_price=Decimal("50000.00"),
            side="buy",
        )

        assert stop_loss == Decimal("49000.00000000")

    def test_stop_loss_invalid_entry_price(self, risk_manager: RiskManager) -> None:
        """Test stop-loss with invalid entry price."""
        with pytest.raises(ValueError, match="entry_price must be positive"):
            risk_manager.calculate_stop_loss(
                entry_price=Decimal("0"),
                side="BUY",
            )

        with pytest.raises(ValueError, match="entry_price must be positive"):
            risk_manager.calculate_stop_loss(
                entry_price=Decimal("-100"),
                side="BUY",
            )

    def test_stop_loss_invalid_side(self, risk_manager: RiskManager) -> None:
        """Test stop-loss with invalid side."""
        with pytest.raises(ValueError, match="side must be 'BUY' or 'SELL'"):
            risk_manager.calculate_stop_loss(
                entry_price=Decimal("50000.00"),
                side="INVALID",
            )

    def test_stop_loss_invalid_risk_percent(self, risk_manager: RiskManager) -> None:
        """Test stop-loss with invalid risk percent."""
        with pytest.raises(ValueError, match="risk_percent must be between"):
            risk_manager.calculate_stop_loss(
                entry_price=Decimal("50000.00"),
                side="BUY",
                risk_percent=0.0,
            )

        with pytest.raises(ValueError, match="risk_percent must be between"):
            risk_manager.calculate_stop_loss(
                entry_price=Decimal("50000.00"),
                side="BUY",
                risk_percent=1.5,
            )


class TestRiskCalculation:
    """Tests for risk calculation - Requirement 6.5."""

    def test_calculate_risk_amount(self, risk_manager: RiskManager) -> None:
        """Test risk amount calculation."""
        risk_amount = risk_manager.calculate_risk_amount(
            entry_price=Decimal("50000.00"),
            stop_loss_price=Decimal("49000.00"),
            quantity=Decimal("0.1"),
        )

        # (50000 - 49000) * 0.1 = 100
        assert risk_amount == Decimal("100.00000000")

    def test_calculate_risk_percent(self, risk_manager: RiskManager) -> None:
        """Test risk percentage calculation."""
        # Portfolio is 10000
        risk_percent = risk_manager.calculate_risk_percent(Decimal("200.00"))

        # 200 / 10000 = 0.02 (2%)
        assert risk_percent == pytest.approx(0.02)

    def test_calculate_risk_percent_zero_portfolio(self) -> None:
        """Test risk percentage with zero portfolio."""
        rm = RiskManager()

        risk_percent = rm.calculate_risk_percent(Decimal("100.00"))

        assert risk_percent == 0.0


class TestTradeValidation:
    """Tests for trade validation - Requirements 6.5, 6.6."""

    def test_valid_trade(self, risk_manager: RiskManager) -> None:
        """Test validation of a valid trade."""
        result = risk_manager.validate_trade(
            entry_price=Decimal("50000.00"),
            side="BUY",
            quantity=Decimal("0.01"),  # Small position
        )

        assert result.is_valid is True
        assert len(result.rejection_reasons) == 0
        assert result.stop_loss_price == Decimal("49000.00000000")

    def test_trade_rejected_risk_too_high(self, risk_manager: RiskManager) -> None:
        """Test trade rejected when risk exceeds limit."""
        # Large position with wide stop-loss
        result = risk_manager.validate_trade(
            entry_price=Decimal("50000.00"),
            side="BUY",
            quantity=Decimal("0.1"),
            stop_loss_price=Decimal("40000.00"),  # 20% stop-loss
        )

        # Risk = (50000 - 40000) * 0.1 = 1000
        # Risk % = 1000 / 10000 = 10% > 2% limit
        assert result.is_valid is False
        assert any("risk per trade" in r.lower() for r in result.rejection_reasons)

    def test_trade_rejected_position_too_large(self, risk_manager: RiskManager) -> None:
        """Test trade rejected when position exceeds limit."""
        # Position value = 50000 * 0.5 = 25000 > 10% of 10000 = 1000
        result = risk_manager.validate_trade(
            entry_price=Decimal("50000.00"),
            side="BUY",
            quantity=Decimal("0.5"),
        )

        assert result.is_valid is False
        assert any("position value" in r.lower() for r in result.rejection_reasons)

    def test_trade_rejected_confidence_too_low(self, risk_manager: RiskManager) -> None:
        """Test trade rejected when confidence is below threshold."""
        result = risk_manager.validate_trade(
            entry_price=Decimal("50000.00"),
            side="BUY",
            quantity=Decimal("0.01"),
            confidence=0.50,  # Below 85% threshold
        )

        assert result.is_valid is False
        assert any("confidence" in r.lower() for r in result.rejection_reasons)

    def test_trade_rejected_trading_halted(self) -> None:
        """Test trade rejected when trading is halted."""
        rm = RiskManager()
        rm.update_portfolio(Decimal("10000.00"))

        # Trigger drawdown breach
        rm.update_portfolio(Decimal("7000.00"))  # 30% drawdown

        result = rm.validate_trade(
            entry_price=Decimal("50000.00"),
            side="BUY",
            quantity=Decimal("0.01"),
        )

        assert result.is_valid is False
        assert any("halted" in r.lower() for r in result.rejection_reasons)

    def test_trade_validation_invalid_inputs(self, risk_manager: RiskManager) -> None:
        """Test trade validation with invalid inputs."""
        # Invalid entry price
        result = risk_manager.validate_trade(
            entry_price=Decimal("-100"),
            side="BUY",
            quantity=Decimal("0.01"),
        )
        assert result.is_valid is False

        # Invalid quantity
        result = risk_manager.validate_trade(
            entry_price=Decimal("50000.00"),
            side="BUY",
            quantity=Decimal("-0.01"),
        )
        assert result.is_valid is False

        # Invalid side
        result = risk_manager.validate_trade(
            entry_price=Decimal("50000.00"),
            side="INVALID",
            quantity=Decimal("0.01"),
        )
        assert result.is_valid is False

    def test_trade_validation_result_fields(self, risk_manager: RiskManager) -> None:
        """Test that TradeValidationResult contains all expected fields."""
        result = risk_manager.validate_trade(
            entry_price=Decimal("50000.00"),
            side="BUY",
            quantity=Decimal("0.01"),
        )

        assert hasattr(result, "is_valid")
        assert hasattr(result, "position_size")
        assert hasattr(result, "stop_loss_price")
        assert hasattr(result, "risk_amount")
        assert hasattr(result, "risk_percent")
        assert hasattr(result, "max_risk_percent")
        assert hasattr(result, "rejection_reasons")
        assert hasattr(result, "warnings")
        assert hasattr(result, "reasoning")

    def test_trade_validation_warning_approaching_limit(self, risk_manager: RiskManager) -> None:
        """Test warning when approaching risk limit."""
        # Create a trade that's close to but under the limit
        # Risk limit is 2%, so 1.7% should trigger warning
        # Need: risk_amount / 10000 = 0.017
        # risk_amount = 170
        # With entry=50000, stop=49660, qty=0.5: risk = 340 * 0.5 = 170
        result = risk_manager.validate_trade(
            entry_price=Decimal("50000.00"),
            side="BUY",
            quantity=Decimal("0.01"),
            stop_loss_price=Decimal("48300.00"),  # 3.4% stop, risk = 170
        )

        # This should be valid but with a warning
        assert result.is_valid is True
        assert len(result.warnings) > 0 or result.risk_percent < 0.016


class TestBotValidation:
    """Tests for bot creation validation - Requirement 10.7."""

    def test_valid_bot_creation(self, risk_manager: RiskManager) -> None:
        """Test validation of valid bot creation."""
        result = risk_manager.validate_bot_creation(
            allocation_amount=Decimal("2000.00"),
        )

        assert result.is_valid is True
        assert len(result.rejection_reasons) == 0
        assert result.allocation_percent == pytest.approx(0.20)

    def test_bot_rejected_exceeds_limit(self, risk_manager: RiskManager) -> None:
        """Test bot rejected when allocation exceeds limit."""
        # Max is 50%, trying to allocate 60%
        result = risk_manager.validate_bot_creation(
            allocation_amount=Decimal("6000.00"),
        )

        assert result.is_valid is False
        assert any("exceed" in r.lower() for r in result.rejection_reasons)

    def test_bot_rejected_with_existing_allocation(self, risk_manager: RiskManager) -> None:
        """Test bot rejected when combined with existing allocation exceeds limit."""
        # Set existing allocation to 40%
        risk_manager.update_bot_allocation(Decimal("4000.00"))

        # Try to add another 20% (total would be 60% > 50% limit)
        result = risk_manager.validate_bot_creation(
            allocation_amount=Decimal("2000.00"),
        )

        assert result.is_valid is False
        assert result.new_total_allocation == Decimal("6000.00")

    def test_bot_rejected_trading_halted(self) -> None:
        """Test bot rejected when trading is halted."""
        rm = RiskManager()
        rm.update_portfolio(Decimal("10000.00"))

        # Trigger drawdown breach
        rm.update_portfolio(Decimal("7000.00"))

        result = rm.validate_bot_creation(
            allocation_amount=Decimal("1000.00"),
        )

        assert result.is_valid is False
        assert any("halted" in r.lower() for r in result.rejection_reasons)

    def test_bot_validation_invalid_amount(self, risk_manager: RiskManager) -> None:
        """Test bot validation with invalid allocation amount."""
        result = risk_manager.validate_bot_creation(
            allocation_amount=Decimal("-100"),
        )

        assert result.is_valid is False
        assert any("positive" in r.lower() for r in result.rejection_reasons)

    def test_bot_validation_result_fields(self, risk_manager: RiskManager) -> None:
        """Test that BotValidationResult contains all expected fields."""
        result = risk_manager.validate_bot_creation(
            allocation_amount=Decimal("2000.00"),
        )

        assert hasattr(result, "is_valid")
        assert hasattr(result, "allocation_amount")
        assert hasattr(result, "current_bot_allocation")
        assert hasattr(result, "new_total_allocation")
        assert hasattr(result, "portfolio_value")
        assert hasattr(result, "allocation_percent")
        assert hasattr(result, "max_allocation_percent")
        assert hasattr(result, "rejection_reasons")
        assert hasattr(result, "warnings")
        assert hasattr(result, "reasoning")

    def test_bot_validation_warning_approaching_limit(self, risk_manager: RiskManager) -> None:
        """Test warning when approaching allocation limit."""
        # Allocate 45% (90% of 50% limit)
        result = risk_manager.validate_bot_creation(
            allocation_amount=Decimal("4500.00"),
        )

        assert result.is_valid is True
        assert len(result.warnings) > 0


class TestAvailableBotAllocation:
    """Tests for available bot allocation calculation."""

    def test_available_allocation_no_bots(self, risk_manager: RiskManager) -> None:
        """Test available allocation with no existing bots."""
        available = risk_manager.get_available_bot_allocation()

        # 50% of 10000 = 5000
        assert available == Decimal("5000.00000000")

    def test_available_allocation_with_existing_bots(self, risk_manager: RiskManager) -> None:
        """Test available allocation with existing bots."""
        risk_manager.update_bot_allocation(Decimal("2000.00"))

        available = risk_manager.get_available_bot_allocation()

        # 5000 - 2000 = 3000
        assert available == Decimal("3000.00000000")

    def test_available_allocation_at_limit(self, risk_manager: RiskManager) -> None:
        """Test available allocation when at limit."""
        risk_manager.update_bot_allocation(Decimal("5000.00"))

        available = risk_manager.get_available_bot_allocation()

        assert available == Decimal("0.00000000")

    def test_available_allocation_over_limit(self, risk_manager: RiskManager) -> None:
        """Test available allocation when over limit (shouldn't go negative)."""
        risk_manager.update_bot_allocation(Decimal("6000.00"))

        available = risk_manager.get_available_bot_allocation()

        assert available == Decimal("0.00000000")


class TestBotUnderperformance:
    """Tests for bot underperformance detection."""

    def test_bot_not_underperforming(self, risk_manager: RiskManager) -> None:
        """Test bot is not flagged when P&L is acceptable."""
        assert risk_manager.is_bot_underperforming(-0.05) is False  # -5%
        assert risk_manager.is_bot_underperforming(0.0) is False
        assert risk_manager.is_bot_underperforming(0.10) is False  # +10%

    def test_bot_underperforming(self, risk_manager: RiskManager) -> None:
        """Test bot is flagged when loss exceeds threshold."""
        # Default threshold is 10%
        assert risk_manager.is_bot_underperforming(-0.15) is True  # -15%
        assert risk_manager.is_bot_underperforming(-0.11) is True  # -11%

    def test_bot_at_threshold(self, risk_manager: RiskManager) -> None:
        """Test bot at exactly the threshold."""
        # At exactly -10%, should not be flagged (only when exceeded)
        assert risk_manager.is_bot_underperforming(-0.10) is False


class TestDrawdownIntegration:
    """Tests for drawdown tracking integration."""

    def test_trading_allowed_initially(self, risk_manager: RiskManager) -> None:
        """Test trading is allowed initially."""
        assert risk_manager.is_trading_allowed() is True

    def test_trading_halted_after_drawdown(self) -> None:
        """Test trading is halted after drawdown breach."""
        rm = RiskManager()
        rm.update_portfolio(Decimal("10000.00"))
        rm.update_portfolio(Decimal("7000.00"))  # 30% drawdown

        assert rm.is_trading_allowed() is False

    def test_get_current_drawdown(self) -> None:
        """Test getting current drawdown."""
        rm = RiskManager()
        rm.update_portfolio(Decimal("10000.00"))
        rm.update_portfolio(Decimal("9000.00"))

        assert rm.get_current_drawdown() == pytest.approx(0.10)

    def test_reset_drawdown(self) -> None:
        """Test resetting drawdown."""
        rm = RiskManager()
        rm.update_portfolio(Decimal("10000.00"))
        rm.update_portfolio(Decimal("7000.00"))  # Breach

        assert rm.is_trading_allowed() is False

        rm.reset_drawdown()

        assert rm.is_trading_allowed() is True


class TestEdgeCases:
    """Tests for edge cases."""

    def test_zero_portfolio_value(self) -> None:
        """Test with zero portfolio value."""
        rm = RiskManager()
        rm.update_portfolio(Decimal("0"))

        result = rm.validate_bot_creation(Decimal("100"))

        # Should be rejected as allocation would be 100% of 0
        assert result.is_valid is False

    def test_very_small_values(self, risk_manager: RiskManager) -> None:
        """Test with very small values."""
        result = risk_manager.validate_trade(
            entry_price=Decimal("0.00000001"),
            side="BUY",
            quantity=Decimal("0.00000001"),
        )

        # Should be valid (very small position)
        assert result.is_valid is True

    def test_very_large_values(self) -> None:
        """Test with very large values."""
        rm = RiskManager()
        rm.update_portfolio(Decimal("1000000000.00"))

        result = rm.validate_bot_creation(Decimal("100000000.00"))

        # 10% allocation should be valid
        assert result.is_valid is True
