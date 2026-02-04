"""
Risk Management Library.

This module provides risk management components including position sizing
using Kelly Criterion and portfolio risk controls.

Requirements:
- 6.1: Calculate position size using Kelly Criterion: f* = (p * b - q) / b
       where p=win_probability, q=1-p, b=win/loss_ratio
- 6.2: Cap position size at configurable maximum (default 10% of portfolio)
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


@dataclass(frozen=True)
class PositionSizeResult:
    """
    Result of position size calculation.
    
    Attributes:
        kelly_fraction: Raw Kelly Criterion fraction (can be negative or > 1)
        clamped_fraction: Kelly fraction clamped to [0, max_position_pct]
        position_size: Final position size in base currency
        portfolio_value: Portfolio value used in calculation
        max_position_pct: Maximum position percentage applied
        was_capped: Whether the position was capped at maximum
        was_negative: Whether the raw Kelly was negative (no edge)
        reasoning: Human-readable explanation of the calculation
    """
    kelly_fraction: float
    clamped_fraction: float
    position_size: Decimal
    portfolio_value: Decimal
    max_position_pct: float
    was_capped: bool
    was_negative: bool
    reasoning: str


@dataclass
class PositionSizerConfig:
    """
    Configuration for PositionSizer.
    
    Attributes:
        max_position_pct: Maximum position as percentage of portfolio (default 10%)
        kelly_fraction_multiplier: Multiplier to apply to Kelly fraction for
                                   more conservative sizing (default 1.0 = full Kelly)
    """
    max_position_pct: float = 0.10
    kelly_fraction_multiplier: float = 1.0
    
    def __post_init__(self) -> None:
        """Validate configuration values."""
        if not 0 < self.max_position_pct <= 1.0:
            raise ValueError(
                f"max_position_pct must be between 0 (exclusive) and 1.0 (inclusive), "
                f"got {self.max_position_pct}"
            )
        
        if not 0 < self.kelly_fraction_multiplier <= 1.0:
            raise ValueError(
                f"kelly_fraction_multiplier must be between 0 (exclusive) and 1.0 (inclusive), "
                f"got {self.kelly_fraction_multiplier}"
            )


class PositionSizer:
    """
    Position sizer using Kelly Criterion.
    
    Calculates optimal position size based on win probability and win/loss ratio
    using the Kelly Criterion formula. The result is capped at a configurable
    maximum percentage of the portfolio.
    
    Kelly Criterion Formula:
        f* = (p * b - q) / b
        
        Where:
        - f* = optimal fraction of portfolio to bet
        - p = probability of winning
        - q = probability of losing (1 - p)
        - b = win/loss ratio (average win / average loss)
    
    Requirements:
        - 6.1: Calculate position size using Kelly Criterion formula
        - 6.2: Cap position size at configurable maximum (default 10% of portfolio)
    
    Example:
        >>> sizer = PositionSizer()
        >>> result = sizer.calculate_position_size(
        ...     win_probability=0.55,
        ...     win_loss_ratio=1.5,
        ...     portfolio_value=Decimal("10000.00")
        ... )
        >>> print(f"Position size: ${result.position_size}")
    """
    
    def __init__(self, config: PositionSizerConfig | None = None) -> None:
        """
        Initialize the PositionSizer.
        
        Args:
            config: Optional configuration for position sizing.
                    Uses defaults if not provided.
        """
        self.config = config or PositionSizerConfig()
    
    @property
    def max_position_pct(self) -> float:
        """Get the maximum position percentage."""
        return self.config.max_position_pct
    
    def calculate_kelly_fraction(
        self,
        win_probability: float,
        win_loss_ratio: float,
    ) -> float:
        """
        Calculate the raw Kelly Criterion fraction.
        
        Formula: f* = (p * b - q) / b
        
        Where:
        - p = win_probability
        - q = 1 - p (loss probability)
        - b = win_loss_ratio
        
        Args:
            win_probability: Probability of winning (0 to 1)
            win_loss_ratio: Ratio of average win to average loss (> 0)
            
        Returns:
            Raw Kelly fraction (can be negative if no edge, or > 1)
            
        Raises:
            ValueError: If win_probability not in [0, 1] or win_loss_ratio <= 0
            
        Requirements:
            - 6.1: Calculate position size using Kelly Criterion formula
        """
        # Validate inputs
        if not 0 <= win_probability <= 1:
            raise ValueError(
                f"win_probability must be between 0 and 1, got {win_probability}"
            )
        
        if win_loss_ratio <= 0:
            raise ValueError(
                f"win_loss_ratio must be positive, got {win_loss_ratio}"
            )
        
        # Calculate Kelly fraction: f* = (p * b - q) / b
        p = win_probability
        q = 1 - p
        b = win_loss_ratio
        
        kelly = (p * b - q) / b
        
        return kelly
    
    def clamp_kelly_fraction(self, kelly_fraction: float) -> float:
        """
        Clamp Kelly fraction to valid range [0, max_position_pct].
        
        Args:
            kelly_fraction: Raw Kelly fraction
            
        Returns:
            Clamped fraction between 0 and max_position_pct
            
        Requirements:
            - 6.2: Cap position size at configurable maximum
        """
        # Clamp to [0, 1] first (Kelly should never exceed 100%)
        clamped = max(0.0, min(1.0, kelly_fraction))
        
        # Apply Kelly fraction multiplier for more conservative sizing
        clamped = clamped * self.config.kelly_fraction_multiplier
        
        # Cap at maximum position percentage
        clamped = min(clamped, self.config.max_position_pct)
        
        return clamped
    
    def calculate_position_size(
        self,
        win_probability: float,
        win_loss_ratio: float,
        portfolio_value: Decimal,
    ) -> PositionSizeResult:
        """
        Calculate optimal position size using Kelly Criterion.
        
        Calculates the Kelly fraction and applies it to the portfolio value,
        capping at the maximum position percentage.
        
        Args:
            win_probability: Probability of winning (0 to 1)
            win_loss_ratio: Ratio of average win to average loss (> 0)
            portfolio_value: Total portfolio value in base currency
            
        Returns:
            PositionSizeResult with position size and calculation details
            
        Raises:
            ValueError: If inputs are invalid
            
        Requirements:
            - 6.1: Calculate position size using Kelly Criterion
            - 6.2: Cap position size at configurable maximum (default 10%)
        """
        # Validate portfolio value
        if portfolio_value < 0:
            raise ValueError(
                f"portfolio_value must be non-negative, got {portfolio_value}"
            )
        
        # Handle zero portfolio value
        if portfolio_value == 0:
            return PositionSizeResult(
                kelly_fraction=0.0,
                clamped_fraction=0.0,
                position_size=Decimal("0"),
                portfolio_value=portfolio_value,
                max_position_pct=self.config.max_position_pct,
                was_capped=False,
                was_negative=False,
                reasoning="Portfolio value is zero, no position can be taken",
            )
        
        # Calculate raw Kelly fraction
        kelly_fraction = self.calculate_kelly_fraction(
            win_probability=win_probability,
            win_loss_ratio=win_loss_ratio,
        )
        
        # Track if Kelly was negative (no edge)
        was_negative = kelly_fraction < 0
        
        # Clamp to valid range
        clamped_fraction = self.clamp_kelly_fraction(kelly_fraction)
        
        # Track if position was capped
        was_capped = (
            kelly_fraction > 0 and
            kelly_fraction * self.config.kelly_fraction_multiplier > self.config.max_position_pct
        )
        
        # Calculate position size
        position_size = portfolio_value * Decimal(str(clamped_fraction))
        
        # Round to 8 decimal places (common for crypto)
        position_size = position_size.quantize(Decimal("0.00000001"))
        
        # Generate reasoning
        reasoning = self._generate_reasoning(
            kelly_fraction=kelly_fraction,
            clamped_fraction=clamped_fraction,
            was_capped=was_capped,
            was_negative=was_negative,
            win_probability=win_probability,
            win_loss_ratio=win_loss_ratio,
        )
        
        return PositionSizeResult(
            kelly_fraction=kelly_fraction,
            clamped_fraction=clamped_fraction,
            position_size=position_size,
            portfolio_value=portfolio_value,
            max_position_pct=self.config.max_position_pct,
            was_capped=was_capped,
            was_negative=was_negative,
            reasoning=reasoning,
        )
    
    def _generate_reasoning(
        self,
        kelly_fraction: float,
        clamped_fraction: float,
        was_capped: bool,
        was_negative: bool,
        win_probability: float,
        win_loss_ratio: float,
    ) -> str:
        """
        Generate human-readable reasoning for the position size.
        
        Args:
            kelly_fraction: Raw Kelly fraction
            clamped_fraction: Clamped Kelly fraction
            was_capped: Whether position was capped
            was_negative: Whether Kelly was negative
            win_probability: Win probability used
            win_loss_ratio: Win/loss ratio used
            
        Returns:
            Human-readable explanation string
        """
        if was_negative:
            return (
                f"No position recommended - negative edge detected. "
                f"Kelly fraction: {kelly_fraction:.4f} "
                f"(win_prob={win_probability:.2%}, win_loss_ratio={win_loss_ratio:.2f}). "
                f"Position size: 0%"
            )
        
        if was_capped:
            return (
                f"Position capped at maximum {self.config.max_position_pct:.1%}. "
                f"Raw Kelly: {kelly_fraction:.4f} ({kelly_fraction:.1%}), "
                f"capped to {clamped_fraction:.4f} ({clamped_fraction:.1%}). "
                f"(win_prob={win_probability:.2%}, win_loss_ratio={win_loss_ratio:.2f})"
            )
        
        return (
            f"Kelly optimal position: {clamped_fraction:.4f} ({clamped_fraction:.1%}). "
            f"(win_prob={win_probability:.2%}, win_loss_ratio={win_loss_ratio:.2f})"
        )
    
    def get_max_position_value(self, portfolio_value: Decimal) -> Decimal:
        """
        Get the maximum allowed position value.
        
        Args:
            portfolio_value: Total portfolio value
            
        Returns:
            Maximum position value based on max_position_pct
            
        Requirements:
            - 6.2: Cap position size at configurable maximum
        """
        if portfolio_value < 0:
            raise ValueError(
                f"portfolio_value must be non-negative, got {portfolio_value}"
            )
        
        max_value = portfolio_value * Decimal(str(self.config.max_position_pct))
        return max_value.quantize(Decimal("0.00000001"))


@dataclass(frozen=True)
class DrawdownStatus:
    """
    Status of current drawdown tracking.
    
    Attributes:
        high_water_mark: Highest portfolio value recorded
        current_value: Current portfolio value
        drawdown_amount: Absolute drawdown amount (high_water_mark - current_value)
        drawdown_pct: Drawdown as percentage (0.0 to 1.0)
        max_drawdown_pct: Maximum allowed drawdown percentage
        is_breached: Whether drawdown limit has been breached
        is_trading_allowed: Whether trading is currently allowed
        reasoning: Human-readable explanation of the status
    """
    high_water_mark: Decimal
    current_value: Decimal
    drawdown_amount: Decimal
    drawdown_pct: float
    max_drawdown_pct: float
    is_breached: bool
    is_trading_allowed: bool
    reasoning: str


@dataclass
class DrawdownTrackerConfig:
    """
    Configuration for DrawdownTracker.
    
    Attributes:
        max_drawdown_pct: Maximum allowed drawdown as percentage (default 20%)
                          Trading is halted when this limit is breached.
    """
    max_drawdown_pct: float = 0.20
    
    def __post_init__(self) -> None:
        """Validate configuration values."""
        if not 0 < self.max_drawdown_pct <= 1.0:
            raise ValueError(
                f"max_drawdown_pct must be between 0 (exclusive) and 1.0 (inclusive), "
                f"got {self.max_drawdown_pct}"
            )


class DrawdownTracker:
    """
    Tracks portfolio drawdown and enforces maximum drawdown limits.
    
    The drawdown tracker monitors the portfolio value and calculates the
    current drawdown from the high water mark (highest value seen). When
    the drawdown exceeds the configured maximum, trading is halted until
    manually reset.
    
    Drawdown Formula:
        drawdown = (high_water_mark - current_value) / high_water_mark
    
    Requirements:
        - 6.3: Track portfolio high water mark and current drawdown percentage
        - 6.4: Halt all trading when drawdown exceeds configurable limit (default 20%)
    
    Example:
        >>> tracker = DrawdownTracker(initial_value=Decimal("10000.00"))
        >>> tracker.update(Decimal("9500.00"))  # 5% drawdown
        >>> status = tracker.get_status()
        >>> print(f"Drawdown: {status.drawdown_pct:.1%}")
        Drawdown: 5.0%
        >>> print(f"Trading allowed: {status.is_trading_allowed}")
        Trading allowed: True
    """
    
    def __init__(
        self,
        initial_value: Decimal | None = None,
        config: DrawdownTrackerConfig | None = None,
    ) -> None:
        """
        Initialize the DrawdownTracker.
        
        Args:
            initial_value: Initial portfolio value. If provided, sets the
                          initial high water mark. If None, must call
                          update() before checking status.
            config: Optional configuration for drawdown limits.
                   Uses defaults if not provided.
        """
        self.config = config or DrawdownTrackerConfig()
        self._high_water_mark: Decimal | None = None
        self._current_value: Decimal | None = None
        self._is_halted: bool = False
        
        if initial_value is not None:
            self._validate_value(initial_value, "initial_value")
            self._high_water_mark = initial_value
            self._current_value = initial_value
    
    @property
    def high_water_mark(self) -> Decimal | None:
        """Get the current high water mark."""
        return self._high_water_mark
    
    @property
    def current_value(self) -> Decimal | None:
        """Get the current portfolio value."""
        return self._current_value
    
    @property
    def max_drawdown_pct(self) -> float:
        """Get the maximum allowed drawdown percentage."""
        return self.config.max_drawdown_pct
    
    @property
    def is_halted(self) -> bool:
        """Check if trading has been halted due to drawdown breach."""
        return self._is_halted
    
    def _validate_value(self, value: Decimal, name: str) -> None:
        """
        Validate a portfolio value.
        
        Args:
            value: The value to validate
            name: Name of the parameter for error messages
            
        Raises:
            ValueError: If value is negative
        """
        if value < 0:
            raise ValueError(f"{name} must be non-negative, got {value}")
    
    def update(self, portfolio_value: Decimal) -> DrawdownStatus:
        """
        Update the tracker with a new portfolio value.
        
        Updates the high water mark if the new value is higher, and
        calculates the current drawdown. If drawdown exceeds the limit,
        trading is halted.
        
        Args:
            portfolio_value: Current portfolio value
            
        Returns:
            DrawdownStatus with current drawdown information
            
        Raises:
            ValueError: If portfolio_value is negative
            
        Requirements:
            - 6.3: Track portfolio high water mark and current drawdown percentage
            - 6.4: Halt all trading when drawdown exceeds configurable limit
        """
        self._validate_value(portfolio_value, "portfolio_value")
        
        # Update current value
        self._current_value = portfolio_value
        
        # Update high water mark if new value is higher
        if self._high_water_mark is None or portfolio_value > self._high_water_mark:
            self._high_water_mark = portfolio_value
        
        # Calculate drawdown and check if limit is breached
        status = self._calculate_status()
        
        # Halt trading if drawdown limit is breached
        if status.is_breached:
            self._is_halted = True
        
        return status
    
    def _calculate_status(self) -> DrawdownStatus:
        """
        Calculate the current drawdown status.
        
        Returns:
            DrawdownStatus with all drawdown metrics
        """
        if self._high_water_mark is None or self._current_value is None:
            return DrawdownStatus(
                high_water_mark=Decimal("0"),
                current_value=Decimal("0"),
                drawdown_amount=Decimal("0"),
                drawdown_pct=0.0,
                max_drawdown_pct=self.config.max_drawdown_pct,
                is_breached=False,
                is_trading_allowed=not self._is_halted,
                reasoning="No portfolio value recorded yet",
            )
        
        # Calculate drawdown amount
        drawdown_amount = self._high_water_mark - self._current_value
        
        # Calculate drawdown percentage
        # Handle zero high water mark to avoid division by zero
        if self._high_water_mark == 0:
            drawdown_pct = 0.0
        else:
            drawdown_pct = float(drawdown_amount / self._high_water_mark)
        
        # Check if limit is breached
        is_breached = drawdown_pct > self.config.max_drawdown_pct
        
        # Trading is allowed only if not halted
        is_trading_allowed = not self._is_halted and not is_breached
        
        # Generate reasoning
        reasoning = self._generate_reasoning(
            drawdown_pct=drawdown_pct,
            is_breached=is_breached,
        )
        
        return DrawdownStatus(
            high_water_mark=self._high_water_mark,
            current_value=self._current_value,
            drawdown_amount=drawdown_amount,
            drawdown_pct=drawdown_pct,
            max_drawdown_pct=self.config.max_drawdown_pct,
            is_breached=is_breached,
            is_trading_allowed=is_trading_allowed,
            reasoning=reasoning,
        )
    
    def _generate_reasoning(
        self,
        drawdown_pct: float,
        is_breached: bool,
    ) -> str:
        """
        Generate human-readable reasoning for the drawdown status.
        
        Args:
            drawdown_pct: Current drawdown percentage
            is_breached: Whether the limit has been breached
            
        Returns:
            Human-readable explanation string
        """
        if self._is_halted:
            return (
                f"Trading HALTED - drawdown limit breached. "
                f"Current drawdown: {drawdown_pct:.1%}, "
                f"limit: {self.config.max_drawdown_pct:.1%}. "
                f"Manual reset required to resume trading."
            )
        
        if is_breached:
            return (
                f"Drawdown limit BREACHED! "
                f"Current drawdown: {drawdown_pct:.1%} exceeds "
                f"maximum allowed: {self.config.max_drawdown_pct:.1%}. "
                f"Trading will be halted."
            )
        
        if drawdown_pct > self.config.max_drawdown_pct * 0.8:
            return (
                f"WARNING: Approaching drawdown limit. "
                f"Current drawdown: {drawdown_pct:.1%}, "
                f"limit: {self.config.max_drawdown_pct:.1%} "
                f"({(self.config.max_drawdown_pct - drawdown_pct):.1%} remaining)."
            )
        
        return (
            f"Drawdown within limits. "
            f"Current: {drawdown_pct:.1%}, "
            f"limit: {self.config.max_drawdown_pct:.1%}."
        )
    
    def get_status(self) -> DrawdownStatus:
        """
        Get the current drawdown status without updating values.
        
        Returns:
            DrawdownStatus with current drawdown information
            
        Requirements:
            - 6.3: Track portfolio high water mark and current drawdown percentage
        """
        return self._calculate_status()
    
    def is_trading_allowed(self) -> bool:
        """
        Check if trading is currently allowed.
        
        Trading is not allowed if:
        - The drawdown limit has been breached
        - Trading has been halted and not reset
        
        Returns:
            True if trading is allowed, False otherwise
            
        Requirements:
            - 6.4: Halt all trading when drawdown exceeds configurable limit
        """
        status = self._calculate_status()
        return status.is_trading_allowed
    
    def calculate_drawdown(self) -> float:
        """
        Calculate the current drawdown percentage.
        
        Formula: drawdown = (high_water_mark - current_value) / high_water_mark
        
        Returns:
            Drawdown as a percentage (0.0 to 1.0)
            Returns 0.0 if no values have been recorded
            
        Requirements:
            - 6.3: Track portfolio high water mark and current drawdown percentage
        """
        if self._high_water_mark is None or self._current_value is None:
            return 0.0
        
        if self._high_water_mark == 0:
            return 0.0
        
        return float(
            (self._high_water_mark - self._current_value) / self._high_water_mark
        )
    
    def reset(self, new_value: Decimal | None = None) -> DrawdownStatus:
        """
        Reset the drawdown tracker and resume trading.
        
        This clears the halted state and optionally sets a new high water mark.
        Use this after manually reviewing and accepting the drawdown situation.
        
        Args:
            new_value: Optional new portfolio value to use as the new
                      high water mark. If None, uses the current value.
                      
        Returns:
            DrawdownStatus after reset
            
        Raises:
            ValueError: If new_value is negative
            
        Requirements:
            - 6.4: Halt all trading when drawdown exceeds configurable limit
                   (manual reset required to resume)
        """
        if new_value is not None:
            self._validate_value(new_value, "new_value")
            self._high_water_mark = new_value
            self._current_value = new_value
        elif self._current_value is not None:
            # Reset high water mark to current value
            self._high_water_mark = self._current_value
        
        # Clear halted state
        self._is_halted = False
        
        return self._calculate_status()
    
    def set_high_water_mark(self, value: Decimal) -> None:
        """
        Manually set the high water mark.
        
        Use this to initialize the tracker with a known historical high
        or to adjust after external portfolio changes.
        
        Args:
            value: New high water mark value
            
        Raises:
            ValueError: If value is negative
        """
        self._validate_value(value, "value")
        self._high_water_mark = value


@dataclass(frozen=True)
class TradeValidationResult:
    """
    Result of trade validation against risk limits.
    
    Attributes:
        is_valid: Whether the trade passes all risk checks
        position_size: Calculated position size (may be adjusted)
        stop_loss_price: Calculated stop-loss price
        risk_amount: Amount at risk for this trade
        risk_percent: Risk as percentage of portfolio
        max_risk_percent: Maximum allowed risk percentage
        rejection_reasons: List of reasons if trade is rejected
        warnings: List of warnings (trade may still be valid)
        reasoning: Human-readable explanation
    """
    is_valid: bool
    position_size: Decimal
    stop_loss_price: Decimal
    risk_amount: Decimal
    risk_percent: float
    max_risk_percent: float
    rejection_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    reasoning: str


@dataclass(frozen=True)
class BotValidationResult:
    """
    Result of bot creation validation against risk limits.
    
    Attributes:
        is_valid: Whether the bot creation passes all risk checks
        allocation_amount: Requested allocation amount
        current_bot_allocation: Current total allocated to bots
        new_total_allocation: Total allocation if bot is created
        portfolio_value: Total portfolio value
        allocation_percent: New allocation as percentage of portfolio
        max_allocation_percent: Maximum allowed allocation percentage
        rejection_reasons: List of reasons if bot creation is rejected
        warnings: List of warnings (bot may still be valid)
        reasoning: Human-readable explanation
    """
    is_valid: bool
    allocation_amount: Decimal
    current_bot_allocation: Decimal
    new_total_allocation: Decimal
    portfolio_value: Decimal
    allocation_percent: float
    max_allocation_percent: float
    rejection_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    reasoning: str


@dataclass
class RiskManagerConfig:
    """
    Configuration for RiskManager.
    
    Attributes:
        max_position_pct: Maximum position as percentage of portfolio (default 10%)
        max_risk_per_trade_pct: Maximum risk per trade as percentage of portfolio (default 2%)
        max_drawdown_pct: Maximum allowed drawdown percentage (default 20%)
        max_bot_allocation_pct: Maximum total allocation to bots as percentage of portfolio (default 50%)
        bot_loss_threshold_pct: P&L threshold for flagging underperforming bots (default 10%)
        min_confidence: Minimum confidence score to execute trades (default 85%)
    """
    max_position_pct: float = 0.10
    max_risk_per_trade_pct: float = 0.02
    max_drawdown_pct: float = 0.20
    max_bot_allocation_pct: float = 0.50
    bot_loss_threshold_pct: float = 0.10
    min_confidence: float = 0.85
    
    def __post_init__(self) -> None:
        """Validate configuration values."""
        if not 0 < self.max_position_pct <= 1.0:
            raise ValueError(
                f"max_position_pct must be between 0 (exclusive) and 1.0 (inclusive), "
                f"got {self.max_position_pct}"
            )
        
        if not 0 < self.max_risk_per_trade_pct <= 1.0:
            raise ValueError(
                f"max_risk_per_trade_pct must be between 0 (exclusive) and 1.0 (inclusive), "
                f"got {self.max_risk_per_trade_pct}"
            )
        
        if not 0 < self.max_drawdown_pct <= 1.0:
            raise ValueError(
                f"max_drawdown_pct must be between 0 (exclusive) and 1.0 (inclusive), "
                f"got {self.max_drawdown_pct}"
            )
        
        if not 0 < self.max_bot_allocation_pct <= 1.0:
            raise ValueError(
                f"max_bot_allocation_pct must be between 0 (exclusive) and 1.0 (inclusive), "
                f"got {self.max_bot_allocation_pct}"
            )
        
        if not 0 < self.bot_loss_threshold_pct <= 1.0:
            raise ValueError(
                f"bot_loss_threshold_pct must be between 0 (exclusive) and 1.0 (inclusive), "
                f"got {self.bot_loss_threshold_pct}"
            )
        
        if not 0 <= self.min_confidence <= 100:
            raise ValueError(
                f"min_confidence must be between 0 and 100, got {self.min_confidence}"
            )


class RiskManager:
    """
    Orchestrates risk management across trading and bot operations.
    
    The RiskManager coordinates position sizing, drawdown tracking, and
    validates all trading and bot operations against configured risk limits.
    
    Requirements:
        - 6.5: Calculate risk-per-trade as percentage of portfolio (default max 2%)
        - 6.6: Calculate stop-loss price based on configurable risk tolerance
        - 6.7: Maintain trade history log with entry price, exit price, P&L, and risk metrics
        - 10.7: Validate that allocated funds for bot creation do not exceed portfolio risk limits
    
    Example:
        >>> config = RiskManagerConfig(max_risk_per_trade_pct=0.02)
        >>> risk_manager = RiskManager(config=config)
        >>> risk_manager.update_portfolio(Decimal("10000.00"))
        >>> 
        >>> # Validate a trade
        >>> result = risk_manager.validate_trade(
        ...     entry_price=Decimal("50000.00"),
        ...     side="BUY",
        ...     quantity=Decimal("0.1"),
        ... )
        >>> print(f"Trade valid: {result.is_valid}")
        >>> 
        >>> # Validate bot creation
        >>> bot_result = risk_manager.validate_bot_creation(
        ...     allocation_amount=Decimal("2000.00"),
        ... )
        >>> print(f"Bot creation valid: {bot_result.is_valid}")
    """
    
    def __init__(
        self,
        config: RiskManagerConfig | None = None,
        position_sizer: PositionSizer | None = None,
        drawdown_tracker: DrawdownTracker | None = None,
    ) -> None:
        """
        Initialize the RiskManager.
        
        Args:
            config: Optional configuration for risk management.
                    Uses defaults if not provided.
            position_sizer: Optional PositionSizer instance.
                           Creates one with matching config if not provided.
            drawdown_tracker: Optional DrawdownTracker instance.
                             Creates one with matching config if not provided.
        """
        self.config = config or RiskManagerConfig()
        
        # Initialize position sizer with matching config
        if position_sizer is None:
            position_sizer_config = PositionSizerConfig(
                max_position_pct=self.config.max_position_pct,
            )
            self._position_sizer = PositionSizer(config=position_sizer_config)
        else:
            self._position_sizer = position_sizer
        
        # Initialize drawdown tracker with matching config
        if drawdown_tracker is None:
            drawdown_config = DrawdownTrackerConfig(
                max_drawdown_pct=self.config.max_drawdown_pct,
            )
            self._drawdown_tracker = DrawdownTracker(config=drawdown_config)
        else:
            self._drawdown_tracker = drawdown_tracker
        
        # Track current portfolio state
        self._portfolio_value: Decimal = Decimal("0")
        self._current_bot_allocation: Decimal = Decimal("0")
    
    @property
    def position_sizer(self) -> PositionSizer:
        """Get the position sizer instance."""
        return self._position_sizer
    
    @property
    def drawdown_tracker(self) -> DrawdownTracker:
        """Get the drawdown tracker instance."""
        return self._drawdown_tracker
    
    @property
    def portfolio_value(self) -> Decimal:
        """Get the current portfolio value."""
        return self._portfolio_value
    
    @property
    def current_bot_allocation(self) -> Decimal:
        """Get the current total allocation to bots."""
        return self._current_bot_allocation
    
    def update_portfolio(
        self,
        portfolio_value: Decimal,
        bot_allocation: Decimal | None = None,
    ) -> DrawdownStatus:
        """
        Update the portfolio value and bot allocation.
        
        Args:
            portfolio_value: Current total portfolio value
            bot_allocation: Current total allocated to bots (optional)
            
        Returns:
            DrawdownStatus after the update
            
        Raises:
            ValueError: If portfolio_value is negative
        """
        if portfolio_value < 0:
            raise ValueError(
                f"portfolio_value must be non-negative, got {portfolio_value}"
            )
        
        self._portfolio_value = portfolio_value
        
        if bot_allocation is not None:
            if bot_allocation < 0:
                raise ValueError(
                    f"bot_allocation must be non-negative, got {bot_allocation}"
                )
            self._current_bot_allocation = bot_allocation
        
        return self._drawdown_tracker.update(portfolio_value)
    
    def update_bot_allocation(self, bot_allocation: Decimal) -> None:
        """
        Update the current bot allocation.
        
        Args:
            bot_allocation: Current total allocated to bots
            
        Raises:
            ValueError: If bot_allocation is negative
        """
        if bot_allocation < 0:
            raise ValueError(
                f"bot_allocation must be non-negative, got {bot_allocation}"
            )
        self._current_bot_allocation = bot_allocation
    
    def is_trading_allowed(self) -> bool:
        """
        Check if trading is currently allowed.
        
        Trading is not allowed if:
        - The drawdown limit has been breached
        - Trading has been halted and not reset
        
        Returns:
            True if trading is allowed, False otherwise
            
        Requirements:
            - 6.4: Halt all trading when drawdown exceeds configurable limit
        """
        return self._drawdown_tracker.is_trading_allowed()
    
    def get_current_drawdown(self) -> float:
        """
        Get the current drawdown percentage.
        
        Returns:
            Drawdown as a percentage (0.0 to 1.0)
            
        Requirements:
            - 6.3: Track portfolio high water mark and current drawdown percentage
        """
        return self._drawdown_tracker.calculate_drawdown()
    
    def calculate_stop_loss(
        self,
        entry_price: Decimal,
        side: str,
        risk_percent: float | None = None,
    ) -> Decimal:
        """
        Calculate stop-loss price based on risk tolerance.
        
        For BUY trades, stop-loss is below entry price.
        For SELL trades, stop-loss is above entry price.
        
        Args:
            entry_price: Entry price for the trade
            side: Trade side ("BUY" or "SELL")
            risk_percent: Risk percentage (0.0 to 1.0). Uses max_risk_per_trade_pct if not provided.
            
        Returns:
            Stop-loss price
            
        Raises:
            ValueError: If entry_price is not positive or side is invalid
            
        Requirements:
            - 6.6: Calculate stop-loss price based on configurable risk tolerance
        """
        if entry_price <= 0:
            raise ValueError(
                f"entry_price must be positive, got {entry_price}"
            )
        
        side_upper = side.upper()
        if side_upper not in ("BUY", "SELL"):
            raise ValueError(
                f"side must be 'BUY' or 'SELL', got {side}"
            )
        
        if risk_percent is None:
            risk_percent = self.config.max_risk_per_trade_pct
        
        if not 0 < risk_percent <= 1.0:
            raise ValueError(
                f"risk_percent must be between 0 (exclusive) and 1.0 (inclusive), "
                f"got {risk_percent}"
            )
        
        risk_decimal = Decimal(str(risk_percent))
        
        if side_upper == "BUY":
            # For BUY, stop-loss is below entry
            stop_loss = entry_price * (1 - risk_decimal)
        else:
            # For SELL, stop-loss is above entry
            stop_loss = entry_price * (1 + risk_decimal)
        
        # Round to 8 decimal places
        return stop_loss.quantize(Decimal("0.00000001"))
    
    def calculate_risk_amount(
        self,
        entry_price: Decimal,
        stop_loss_price: Decimal,
        quantity: Decimal,
    ) -> Decimal:
        """
        Calculate the amount at risk for a trade.
        
        Args:
            entry_price: Entry price for the trade
            stop_loss_price: Stop-loss price
            quantity: Trade quantity
            
        Returns:
            Amount at risk (always positive)
            
        Requirements:
            - 6.5: Calculate risk-per-trade as percentage of portfolio
        """
        price_diff = abs(entry_price - stop_loss_price)
        risk_amount = price_diff * quantity
        return risk_amount.quantize(Decimal("0.00000001"))
    
    def calculate_risk_percent(self, risk_amount: Decimal) -> float:
        """
        Calculate risk as percentage of portfolio.
        
        Args:
            risk_amount: Amount at risk
            
        Returns:
            Risk as percentage (0.0 to 1.0)
            
        Requirements:
            - 6.5: Calculate risk-per-trade as percentage of portfolio
        """
        if self._portfolio_value == 0:
            return 0.0
        
        return float(risk_amount / self._portfolio_value)
    
    def validate_trade(
        self,
        entry_price: Decimal,
        side: str,
        quantity: Decimal,
        stop_loss_price: Decimal | None = None,
        confidence: float | None = None,
    ) -> TradeValidationResult:
        """
        Validate a trade against all risk limits.
        
        Checks:
        - Trading is allowed (drawdown not breached)
        - Risk per trade does not exceed maximum
        - Position size does not exceed maximum
        - Confidence meets minimum threshold (if provided)
        
        Args:
            entry_price: Entry price for the trade
            side: Trade side ("BUY" or "SELL")
            quantity: Trade quantity
            stop_loss_price: Optional stop-loss price. Calculated if not provided.
            confidence: Optional confidence score (0-100)
            
        Returns:
            TradeValidationResult with validation details
            
        Requirements:
            - 6.5: Calculate risk-per-trade as percentage of portfolio (default max 2%)
            - 6.6: Calculate stop-loss price based on configurable risk tolerance
        """
        rejection_reasons: list[str] = []
        warnings: list[str] = []
        
        # Validate inputs
        if entry_price <= 0:
            rejection_reasons.append(f"Entry price must be positive, got {entry_price}")
        
        if quantity <= 0:
            rejection_reasons.append(f"Quantity must be positive, got {quantity}")
        
        side_upper = side.upper()
        if side_upper not in ("BUY", "SELL"):
            rejection_reasons.append(f"Side must be 'BUY' or 'SELL', got {side}")
        
        # If basic validation fails, return early
        if rejection_reasons:
            return TradeValidationResult(
                is_valid=False,
                position_size=Decimal("0"),
                stop_loss_price=Decimal("0"),
                risk_amount=Decimal("0"),
                risk_percent=0.0,
                max_risk_percent=self.config.max_risk_per_trade_pct,
                rejection_reasons=tuple(rejection_reasons),
                warnings=tuple(warnings),
                reasoning="Trade rejected due to invalid inputs",
            )
        
        # Check if trading is allowed
        if not self.is_trading_allowed():
            rejection_reasons.append(
                "Trading is halted due to drawdown limit breach"
            )
        
        # Check confidence threshold
        if confidence is not None:
            if confidence < self.config.min_confidence:
                rejection_reasons.append(
                    f"Confidence {confidence:.1f}% is below minimum threshold "
                    f"{self.config.min_confidence:.1f}%"
                )
        
        # Calculate stop-loss if not provided
        if stop_loss_price is None:
            stop_loss_price = self.calculate_stop_loss(entry_price, side_upper)
        
        # Calculate position value
        position_value = entry_price * quantity
        
        # Check position size limit
        max_position_value = self._position_sizer.get_max_position_value(
            self._portfolio_value
        )
        if position_value > max_position_value:
            rejection_reasons.append(
                f"Position value {position_value} exceeds maximum "
                f"{max_position_value} ({self.config.max_position_pct:.0%} of portfolio)"
            )
        
        # Calculate risk
        risk_amount = self.calculate_risk_amount(entry_price, stop_loss_price, quantity)
        risk_percent = self.calculate_risk_percent(risk_amount)
        
        # Check risk per trade limit
        if risk_percent > self.config.max_risk_per_trade_pct:
            rejection_reasons.append(
                f"Risk per trade {risk_percent:.2%} exceeds maximum "
                f"{self.config.max_risk_per_trade_pct:.2%}"
            )
        
        # Add warnings for approaching limits
        if risk_percent > self.config.max_risk_per_trade_pct * 0.8:
            if risk_percent <= self.config.max_risk_per_trade_pct:
                warnings.append(
                    f"Risk per trade {risk_percent:.2%} is approaching limit "
                    f"{self.config.max_risk_per_trade_pct:.2%}"
                )
        
        is_valid = len(rejection_reasons) == 0
        
        # Generate reasoning
        if is_valid:
            reasoning = (
                f"Trade validated: {side_upper} {quantity} @ {entry_price}, "
                f"stop-loss @ {stop_loss_price}, "
                f"risk {risk_percent:.2%} of portfolio"
            )
        else:
            reasoning = f"Trade rejected: {'; '.join(rejection_reasons)}"
        
        return TradeValidationResult(
            is_valid=is_valid,
            position_size=quantity,
            stop_loss_price=stop_loss_price,
            risk_amount=risk_amount,
            risk_percent=risk_percent,
            max_risk_percent=self.config.max_risk_per_trade_pct,
            rejection_reasons=tuple(rejection_reasons),
            warnings=tuple(warnings),
            reasoning=reasoning,
        )
    
    def validate_bot_creation(
        self,
        allocation_amount: Decimal,
    ) -> BotValidationResult:
        """
        Validate bot creation against portfolio risk limits.
        
        Checks:
        - Trading is allowed (drawdown not breached)
        - New allocation does not exceed maximum bot allocation percentage
        
        Args:
            allocation_amount: Amount to allocate to the new bot
            
        Returns:
            BotValidationResult with validation details
            
        Requirements:
            - 10.7: Validate that allocated funds for bot creation do not exceed portfolio risk limits
        """
        rejection_reasons: list[str] = []
        warnings: list[str] = []
        
        # Validate input
        if allocation_amount <= 0:
            rejection_reasons.append(
                f"Allocation amount must be positive, got {allocation_amount}"
            )
            return BotValidationResult(
                is_valid=False,
                allocation_amount=allocation_amount,
                current_bot_allocation=self._current_bot_allocation,
                new_total_allocation=self._current_bot_allocation,
                portfolio_value=self._portfolio_value,
                allocation_percent=0.0,
                max_allocation_percent=self.config.max_bot_allocation_pct,
                rejection_reasons=tuple(rejection_reasons),
                warnings=tuple(warnings),
                reasoning="Bot creation rejected due to invalid allocation amount",
            )
        
        # Check if trading is allowed
        if not self.is_trading_allowed():
            rejection_reasons.append(
                "Trading is halted due to drawdown limit breach"
            )
        
        # Calculate new total allocation
        new_total_allocation = self._current_bot_allocation + allocation_amount
        
        # Calculate allocation percentage
        if self._portfolio_value == 0:
            allocation_percent = 1.0 if allocation_amount > 0 else 0.0
        else:
            allocation_percent = float(new_total_allocation / self._portfolio_value)
        
        # Check allocation limit
        if allocation_percent > self.config.max_bot_allocation_pct:
            rejection_reasons.append(
                f"New total bot allocation {allocation_percent:.1%} would exceed "
                f"maximum {self.config.max_bot_allocation_pct:.1%} of portfolio"
            )
        
        # Add warnings for approaching limits
        if allocation_percent > self.config.max_bot_allocation_pct * 0.8:
            if allocation_percent <= self.config.max_bot_allocation_pct:
                warnings.append(
                    f"Bot allocation {allocation_percent:.1%} is approaching limit "
                    f"{self.config.max_bot_allocation_pct:.1%}"
                )
        
        is_valid = len(rejection_reasons) == 0
        
        # Generate reasoning
        if is_valid:
            reasoning = (
                f"Bot creation validated: allocating {allocation_amount}, "
                f"new total allocation {new_total_allocation} "
                f"({allocation_percent:.1%} of portfolio)"
            )
        else:
            reasoning = f"Bot creation rejected: {'; '.join(rejection_reasons)}"
        
        return BotValidationResult(
            is_valid=is_valid,
            allocation_amount=allocation_amount,
            current_bot_allocation=self._current_bot_allocation,
            new_total_allocation=new_total_allocation,
            portfolio_value=self._portfolio_value,
            allocation_percent=allocation_percent,
            max_allocation_percent=self.config.max_bot_allocation_pct,
            rejection_reasons=tuple(rejection_reasons),
            warnings=tuple(warnings),
            reasoning=reasoning,
        )
    
    def get_available_bot_allocation(self) -> Decimal:
        """
        Get the remaining amount available for bot allocation.
        
        Returns:
            Amount available for new bot allocations
            
        Requirements:
            - 10.7: Validate that allocated funds for bot creation do not exceed portfolio risk limits
        """
        max_allocation = self._portfolio_value * Decimal(
            str(self.config.max_bot_allocation_pct)
        )
        available = max_allocation - self._current_bot_allocation
        return max(Decimal("0"), available).quantize(Decimal("0.00000001"))
    
    def is_bot_underperforming(self, pnl_percent: float) -> bool:
        """
        Check if a bot is underperforming based on P&L threshold.
        
        Args:
            pnl_percent: Bot's P&L as percentage (negative for losses)
            
        Returns:
            True if bot is underperforming (loss exceeds threshold)
        """
        # Underperforming if loss exceeds threshold
        return pnl_percent < -self.config.bot_loss_threshold_pct
    
    def reset_drawdown(self, new_value: Decimal | None = None) -> DrawdownStatus:
        """
        Reset the drawdown tracker and resume trading.
        
        Args:
            new_value: Optional new portfolio value to use as the new
                      high water mark. If None, uses the current value.
                      
        Returns:
            DrawdownStatus after reset
        """
        return self._drawdown_tracker.reset(new_value)


# Export public API
__all__ = [
    "PositionSizer",
    "PositionSizerConfig",
    "PositionSizeResult",
    "DrawdownTracker",
    "DrawdownTrackerConfig",
    "DrawdownStatus",
    "RiskManager",
    "RiskManagerConfig",
    "TradeValidationResult",
    "BotValidationResult",
]
