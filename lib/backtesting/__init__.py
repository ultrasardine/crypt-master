"""
Backtesting Library.

This module provides backtesting capabilities for validating trading strategies
against historical market data.

Requirements:
- 7.1: Replay historical price data through the Market_Analyzer and Risk_Manager
- 7.2: Calculate performance metrics: total return, win rate, profit factor,
       max drawdown, Sharpe ratio, and Sortino ratio
- 7.3: Simulate order fills at historical prices with configurable slippage
- 7.4: Respect the same confidence threshold and risk limits as live trading
- 7.5: Generate a report with trade-by-trade breakdown and equity curve data
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

import numpy as np

from lib.analysis.confidence import ConfidenceScorer, IndicatorScore
from lib.analysis.signal import Signal, SignalGenerator
from lib.analysis.technical import SignalDirection, TechnicalAnalyzer
from lib.pionex.models import Candle
from lib.risk import (
    DrawdownTracker,
    PositionSizer,
    RiskManager,
    RiskManagerConfig,
)


logger = logging.getLogger(__name__)


class TradeDirection(Enum):
    """Direction of a backtest trade."""
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass
class BacktestTrade:
    """
    A single trade in the backtest.
    
    Attributes:
        trade_id: Unique identifier for the trade
        symbol: Trading pair symbol
        direction: Trade direction (LONG or SHORT)
        entry_time: Entry timestamp
        entry_price: Entry price
        exit_time: Exit timestamp (None if still open)
        exit_price: Exit price (None if still open)
        quantity: Trade quantity
        pnl: Realized profit/loss
        pnl_percent: P&L as percentage of entry value
        signal_confidence: Confidence score of the entry signal
        stop_loss: Stop-loss price
        is_winner: Whether the trade was profitable
        slippage_cost: Total slippage cost incurred
    """
    trade_id: str
    symbol: str
    direction: TradeDirection
    entry_time: datetime
    entry_price: Decimal
    exit_time: datetime | None
    exit_price: Decimal | None
    quantity: Decimal
    pnl: Decimal
    pnl_percent: float
    signal_confidence: float
    stop_loss: Decimal
    is_winner: bool
    slippage_cost: Decimal = field(default_factory=lambda: Decimal("0"))


@dataclass
class EquityPoint:
    """
    A point on the equity curve.
    
    Attributes:
        timestamp: Time of the equity snapshot
        equity: Total portfolio value
        drawdown: Current drawdown percentage
        position_value: Value of open positions
        cash: Available cash
    """
    timestamp: datetime
    equity: Decimal
    drawdown: float
    position_value: Decimal
    cash: Decimal


@dataclass(frozen=True)
class BacktestMetrics:
    """
    Performance metrics from a backtest.
    
    Attributes:
        total_return: Total return as percentage
        total_pnl: Total profit/loss in quote currency
        win_rate: Percentage of winning trades
        profit_factor: Gross profit / gross loss
        max_drawdown: Maximum drawdown percentage
        sharpe_ratio: Risk-adjusted return (annualized)
        sortino_ratio: Downside risk-adjusted return (annualized)
        total_trades: Total number of trades
        winning_trades: Number of winning trades
        losing_trades: Number of losing trades
        avg_win: Average winning trade P&L
        avg_loss: Average losing trade P&L
        avg_trade: Average trade P&L
        largest_win: Largest winning trade
        largest_loss: Largest losing trade
        avg_holding_period_hours: Average trade duration in hours
        exposure_time_percent: Percentage of time with open positions
    """
    total_return: float
    total_pnl: Decimal
    win_rate: float
    profit_factor: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: Decimal
    avg_loss: Decimal
    avg_trade: Decimal
    largest_win: Decimal
    largest_loss: Decimal
    avg_holding_period_hours: float
    exposure_time_percent: float


@dataclass
class BacktestResult:
    """
    Complete result of a backtest run.
    
    Attributes:
        symbol: Trading pair symbol
        start_time: Backtest start time
        end_time: Backtest end time
        initial_capital: Starting capital
        final_capital: Ending capital
        metrics: Performance metrics
        trades: List of all trades
        equity_curve: Equity curve data points
        config: Configuration used for the backtest
    """
    symbol: str
    start_time: datetime
    end_time: datetime
    initial_capital: Decimal
    final_capital: Decimal
    metrics: BacktestMetrics
    trades: list[BacktestTrade]
    equity_curve: list[EquityPoint]
    config: dict[str, Any]


@dataclass
class BacktesterConfig:
    """
    Configuration for the Backtester.
    
    Attributes:
        initial_capital: Starting capital for the backtest
        slippage_pct: Slippage as percentage of price (default 0.1%)
        commission_pct: Commission as percentage of trade value (default 0.1%)
        min_confidence: Minimum confidence to execute trades (default 85%)
        max_position_pct: Maximum position as percentage of portfolio (default 10%)
        max_risk_per_trade_pct: Maximum risk per trade (default 2%)
        max_drawdown_pct: Maximum allowed drawdown (default 20%)
        risk_free_rate: Annual risk-free rate for Sharpe calculation (default 2%)
    """
    initial_capital: Decimal = field(default_factory=lambda: Decimal("10000"))
    slippage_pct: float = 0.001  # 0.1%
    commission_pct: float = 0.001  # 0.1%
    min_confidence: float = 85.0
    max_position_pct: float = 0.10
    max_risk_per_trade_pct: float = 0.02
    max_drawdown_pct: float = 0.20
    risk_free_rate: float = 0.02  # 2% annual
    
    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.initial_capital <= 0:
            raise ValueError(f"initial_capital must be positive, got {self.initial_capital}")
        if not 0 <= self.slippage_pct < 1:
            raise ValueError(f"slippage_pct must be in [0, 1), got {self.slippage_pct}")
        if not 0 <= self.commission_pct < 1:
            raise ValueError(f"commission_pct must be in [0, 1), got {self.commission_pct}")
        if not 0 <= self.min_confidence <= 100:
            raise ValueError(f"min_confidence must be in [0, 100], got {self.min_confidence}")


class Backtester:
    """
    Backtester for validating trading strategies against historical data.
    
    The Backtester replays historical price data through the technical analyzer
    and signal generator, simulating trades with configurable slippage and
    respecting the same risk limits as live trading.
    
    Requirements:
        - 7.1: Replay historical price data through Market_Analyzer and Risk_Manager
        - 7.2: Calculate performance metrics (return, win rate, Sharpe, Sortino, max drawdown)
        - 7.3: Simulate order fills at historical prices with configurable slippage
        - 7.4: Respect the same confidence threshold and risk limits as live trading
        - 7.5: Generate report with trade-by-trade breakdown and equity curve data
    
    Example:
        >>> from decimal import Decimal
        >>> config = BacktesterConfig(initial_capital=Decimal("10000"))
        >>> backtester = Backtester(config)
        >>> result = backtester.run(candles, symbol="BTC_USDT")
        >>> print(f"Total return: {result.metrics.total_return:.2f}%")
    """
    
    def __init__(self, config: BacktesterConfig | None = None) -> None:
        """
        Initialize the Backtester.
        
        Args:
            config: Optional configuration. Uses defaults if not provided.
        """
        self.config = config or BacktesterConfig()
        
        # Initialize components
        self._technical_analyzer = TechnicalAnalyzer()
        self._signal_generator = SignalGenerator()
        
        # Initialize risk manager with matching config
        risk_config = RiskManagerConfig(
            max_position_pct=self.config.max_position_pct,
            max_risk_per_trade_pct=self.config.max_risk_per_trade_pct,
            max_drawdown_pct=self.config.max_drawdown_pct,
            min_confidence=self.config.min_confidence,
        )
        self._risk_manager = RiskManager(config=risk_config)
        
        # State tracking
        self._reset_state()
    
    def _reset_state(self) -> None:
        """Reset internal state for a new backtest run."""
        self._cash = self.config.initial_capital
        self._position: Decimal = Decimal("0")
        self._position_entry_price: Decimal = Decimal("0")
        self._position_entry_time: datetime | None = None
        self._position_stop_loss: Decimal = Decimal("0")
        self._position_confidence: float = 0.0
        self._trades: list[BacktestTrade] = []
        self._equity_curve: list[EquityPoint] = []
        self._trade_counter = 0
        self._high_water_mark = self.config.initial_capital
        self._max_drawdown = 0.0

    
    def run(
        self,
        candles: list[Candle],
        symbol: str,
    ) -> BacktestResult:
        """
        Run a backtest on historical candle data.
        
        Args:
            candles: List of OHLCV candles (must be sorted by timestamp ascending)
            symbol: Trading pair symbol
            
        Returns:
            BacktestResult with metrics, trades, and equity curve
            
        Raises:
            ValueError: If candles list is empty or too short
            
        Requirements:
            - 7.1: Replay historical price data through Market_Analyzer and Risk_Manager
            - 7.3: Simulate order fills at historical prices with configurable slippage
            - 7.4: Respect the same confidence threshold and risk limits as live trading
        """
        if len(candles) < 50:
            raise ValueError("Need at least 50 candles for backtesting")
        
        # Reset state
        self._reset_state()
        
        # Sort candles by timestamp
        sorted_candles = sorted(candles, key=lambda c: c.timestamp)
        
        # Extract price arrays for technical analysis
        closes = np.array([c.close for c in sorted_candles])
        highs = np.array([c.high for c in sorted_candles])
        lows = np.array([c.low for c in sorted_candles])
        volumes = np.array([c.volume for c in sorted_candles])
        
        # Minimum lookback for indicators
        min_lookback = 35  # Enough for MACD (26+9) and other indicators
        
        # Process each candle
        for i in range(min_lookback, len(sorted_candles)):
            candle = sorted_candles[i]
            current_price = Decimal(str(candle.close))
            
            # Get price history up to this point
            price_history = closes[:i + 1]
            high_history = highs[:i + 1]
            low_history = lows[:i + 1]
            volume_history = volumes[:i + 1]
            
            # Check stop-loss first
            if self._position != 0:
                self._check_stop_loss(candle, symbol)
            
            # Generate signal if no position
            if self._position == 0:
                signal = self._generate_signal(
                    symbol=symbol,
                    prices=price_history,
                    highs=high_history,
                    lows=low_history,
                    volumes=volume_history,
                )
                
                # Execute trade if signal meets criteria
                if signal and signal.meets_threshold:
                    self._execute_entry(signal, candle, symbol)
            
            # Record equity point
            self._record_equity(candle)
        
        # Close any remaining position at the end
        if self._position != 0:
            last_candle = sorted_candles[-1]
            self._close_position(
                exit_price=Decimal(str(last_candle.close)),
                exit_time=last_candle.timestamp,
                reason="End of backtest",
            )
        
        # Calculate metrics
        metrics = self._calculate_metrics(sorted_candles)
        
        return BacktestResult(
            symbol=symbol,
            start_time=sorted_candles[min_lookback].timestamp,
            end_time=sorted_candles[-1].timestamp,
            initial_capital=self.config.initial_capital,
            final_capital=self._cash,
            metrics=metrics,
            trades=self._trades,
            equity_curve=self._equity_curve,
            config={
                "initial_capital": str(self.config.initial_capital),
                "slippage_pct": self.config.slippage_pct,
                "commission_pct": self.config.commission_pct,
                "min_confidence": self.config.min_confidence,
                "max_position_pct": self.config.max_position_pct,
                "max_risk_per_trade_pct": self.config.max_risk_per_trade_pct,
                "max_drawdown_pct": self.config.max_drawdown_pct,
            },
        )

    
    def _generate_signal(
        self,
        symbol: str,
        prices: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        volumes: np.ndarray,
    ) -> Signal | None:
        """
        Generate a trading signal from price data.
        
        Args:
            symbol: Trading pair symbol
            prices: Close price history
            highs: High price history
            lows: Low price history
            volumes: Volume history
            
        Returns:
            Signal if generated, None otherwise
        """
        # Calculate technical indicators
        rsi_result = self._technical_analyzer.calculate_rsi(prices)
        macd_result = self._technical_analyzer.calculate_macd(prices)
        bb_result = self._technical_analyzer.calculate_bollinger_bands(prices)
        adx_result = self._technical_analyzer.calculate_adx(highs, lows, prices)
        stoch_result = self._technical_analyzer.calculate_stochastic(highs, lows, prices)
        volume_result = self._technical_analyzer.analyze_volume(volumes)
        
        # Build indicator scores
        technical_scores: list[IndicatorScore] = []
        
        if not rsi_result.data_insufficient and rsi_result.value is not None:
            technical_scores.append(IndicatorScore(
                name="RSI",
                signal=rsi_result.signal,
                confidence=self._rsi_to_confidence(rsi_result.value),
                weight=0.20,
                value=rsi_result.value,
            ))
        
        if not macd_result.data_insufficient:
            technical_scores.append(IndicatorScore(
                name="MACD",
                signal=macd_result.signal,
                confidence=80.0 if macd_result.signal != SignalDirection.HOLD else 50.0,
                weight=0.25,
                value=macd_result.histogram,
            ))
        
        if not bb_result.data_insufficient:
            technical_scores.append(IndicatorScore(
                name="Bollinger",
                signal=bb_result.signal,
                confidence=75.0 if bb_result.signal != SignalDirection.HOLD else 50.0,
                weight=0.15,
                value=bb_result.middle_band,
            ))
        
        if not adx_result.data_insufficient and adx_result.adx is not None:
            technical_scores.append(IndicatorScore(
                name="ADX",
                signal=adx_result.signal,
                confidence=min(100.0, adx_result.adx * 2),
                weight=0.20,
                value=adx_result.adx,
            ))
        
        if not stoch_result.data_insufficient and stoch_result.k is not None:
            technical_scores.append(IndicatorScore(
                name="Stochastic",
                signal=stoch_result.signal,
                confidence=self._stoch_to_confidence(stoch_result.k),
                weight=0.20,
                value=stoch_result.k,
            ))
        
        if not technical_scores:
            return None
        
        # Generate signal
        return self._signal_generator.generate_signal(
            symbol=symbol,
            technical_scores=technical_scores,
        )
    
    def _rsi_to_confidence(self, rsi: float) -> float:
        """Convert RSI value to confidence score."""
        if rsi <= 30:
            return 70.0 + (30 - rsi)  # Higher confidence for lower RSI
        elif rsi >= 70:
            return 70.0 + (rsi - 70)  # Higher confidence for higher RSI
        return 50.0
    
    def _stoch_to_confidence(self, k: float) -> float:
        """Convert Stochastic %K to confidence score."""
        if k <= 20:
            return 70.0 + (20 - k)
        elif k >= 80:
            return 70.0 + (k - 80)
        return 50.0

    
    def _apply_slippage(
        self,
        price: Decimal,
        is_buy: bool,
    ) -> Decimal:
        """
        Apply slippage to a price.
        
        Args:
            price: Original price
            is_buy: True for buy orders, False for sell orders
            
        Returns:
            Price with slippage applied
            
        Requirements:
            - 7.3: Simulate order fills at historical prices with configurable slippage
        """
        slippage = price * Decimal(str(self.config.slippage_pct))
        if is_buy:
            return price + slippage  # Pay more when buying
        return price - slippage  # Receive less when selling
    
    def _calculate_commission(self, value: Decimal) -> Decimal:
        """Calculate commission for a trade value."""
        return value * Decimal(str(self.config.commission_pct))
    
    def _execute_entry(
        self,
        signal: Signal,
        candle: Candle,
        symbol: str,
    ) -> None:
        """
        Execute a trade entry based on a signal.
        
        Args:
            signal: Trading signal
            candle: Current candle
            symbol: Trading pair symbol
            
        Requirements:
            - 7.4: Respect the same confidence threshold and risk limits as live trading
        """
        if signal.direction == SignalDirection.HOLD:
            return
        
        is_buy = signal.direction == SignalDirection.BUY
        entry_price = self._apply_slippage(Decimal(str(candle.close)), is_buy)
        
        # Calculate position size based on risk
        max_position_value = self._cash * Decimal(str(self.config.max_position_pct))
        quantity = max_position_value / entry_price
        
        # Calculate stop-loss
        risk_pct = Decimal(str(self.config.max_risk_per_trade_pct))
        if is_buy:
            stop_loss = entry_price * (1 - risk_pct)
        else:
            stop_loss = entry_price * (1 + risk_pct)
        
        # Calculate commission
        trade_value = entry_price * quantity
        commission = self._calculate_commission(trade_value)
        
        # Check if we have enough cash
        total_cost = trade_value + commission
        if total_cost > self._cash:
            return
        
        # Execute entry
        self._cash -= total_cost
        self._position = quantity if is_buy else -quantity
        self._position_entry_price = entry_price
        self._position_entry_time = candle.timestamp
        self._position_stop_loss = stop_loss
        self._position_confidence = signal.confidence
        
        logger.debug(
            f"Entry: {'BUY' if is_buy else 'SELL'} {quantity:.8f} @ {entry_price:.2f}, "
            f"stop-loss @ {stop_loss:.2f}"
        )

    
    def _check_stop_loss(self, candle: Candle, symbol: str) -> None:
        """
        Check if stop-loss has been triggered.
        
        Args:
            candle: Current candle
            symbol: Trading pair symbol
        """
        if self._position == 0:
            return
        
        is_long = self._position > 0
        
        if is_long:
            # Long position: stop-loss triggered if low <= stop-loss
            if Decimal(str(candle.low)) <= self._position_stop_loss:
                self._close_position(
                    exit_price=self._position_stop_loss,
                    exit_time=candle.timestamp,
                    reason="Stop-loss triggered",
                )
        else:
            # Short position: stop-loss triggered if high >= stop-loss
            if Decimal(str(candle.high)) >= self._position_stop_loss:
                self._close_position(
                    exit_price=self._position_stop_loss,
                    exit_time=candle.timestamp,
                    reason="Stop-loss triggered",
                )
    
    def _close_position(
        self,
        exit_price: Decimal,
        exit_time: datetime,
        reason: str,
    ) -> None:
        """
        Close the current position.
        
        Args:
            exit_price: Exit price
            exit_time: Exit timestamp
            reason: Reason for closing
        """
        if self._position == 0:
            return
        
        is_long = self._position > 0
        quantity = abs(self._position)
        
        # Apply slippage (opposite direction)
        slipped_exit = self._apply_slippage(exit_price, not is_long)
        
        # Calculate P&L
        if is_long:
            pnl = (slipped_exit - self._position_entry_price) * quantity
        else:
            pnl = (self._position_entry_price - slipped_exit) * quantity
        
        # Calculate commission
        exit_value = slipped_exit * quantity
        commission = self._calculate_commission(exit_value)
        pnl -= commission
        
        # Calculate slippage cost
        entry_slippage = abs(self._position_entry_price - exit_price) * Decimal(str(self.config.slippage_pct)) * quantity
        exit_slippage = abs(slipped_exit - exit_price) * quantity
        total_slippage = entry_slippage + exit_slippage
        
        # Update cash
        self._cash += exit_value - commission
        
        # Calculate P&L percentage
        entry_value = self._position_entry_price * quantity
        pnl_percent = float(pnl / entry_value) * 100 if entry_value > 0 else 0.0
        
        # Record trade
        self._trade_counter += 1
        trade = BacktestTrade(
            trade_id=f"BT-{self._trade_counter:06d}",
            symbol="",  # Will be set by caller
            direction=TradeDirection.LONG if is_long else TradeDirection.SHORT,
            entry_time=self._position_entry_time or exit_time,
            entry_price=self._position_entry_price,
            exit_time=exit_time,
            exit_price=slipped_exit,
            quantity=quantity,
            pnl=pnl,
            pnl_percent=pnl_percent,
            signal_confidence=self._position_confidence,
            stop_loss=self._position_stop_loss,
            is_winner=pnl > 0,
            slippage_cost=total_slippage,
        )
        self._trades.append(trade)
        
        logger.debug(f"Exit: {reason}, P&L: {pnl:.2f} ({pnl_percent:.2f}%)")
        
        # Reset position
        self._position = Decimal("0")
        self._position_entry_price = Decimal("0")
        self._position_entry_time = None
        self._position_stop_loss = Decimal("0")
        self._position_confidence = 0.0

    
    def _record_equity(self, candle: Candle) -> None:
        """
        Record an equity curve point.
        
        Args:
            candle: Current candle
        """
        current_price = Decimal(str(candle.close))
        
        # Calculate position value
        if self._position != 0:
            position_value = abs(self._position) * current_price
            if self._position < 0:
                # Short position: value is entry value - current value
                entry_value = abs(self._position) * self._position_entry_price
                unrealized_pnl = entry_value - position_value
                position_value = entry_value + unrealized_pnl
        else:
            position_value = Decimal("0")
        
        # Calculate total equity
        equity = self._cash + position_value
        
        # Update high water mark and max drawdown
        if equity > self._high_water_mark:
            self._high_water_mark = equity
        
        drawdown = 0.0
        if self._high_water_mark > 0:
            drawdown = float((self._high_water_mark - equity) / self._high_water_mark)
            if drawdown > self._max_drawdown:
                self._max_drawdown = drawdown
        
        # Record point
        point = EquityPoint(
            timestamp=candle.timestamp,
            equity=equity,
            drawdown=drawdown,
            position_value=position_value,
            cash=self._cash,
        )
        self._equity_curve.append(point)
    
    def _calculate_metrics(self, candles: list[Candle]) -> BacktestMetrics:
        """
        Calculate performance metrics from the backtest results.
        
        Args:
            candles: List of candles used in the backtest
            
        Returns:
            BacktestMetrics with all performance statistics
            
        Requirements:
            - 7.2: Calculate performance metrics (return, win rate, profit factor,
                   max drawdown, Sharpe ratio, Sortino ratio)
        """
        total_trades = len(self._trades)
        
        if total_trades == 0:
            return BacktestMetrics(
                total_return=0.0,
                total_pnl=Decimal("0"),
                win_rate=0.0,
                profit_factor=0.0,
                max_drawdown=self._max_drawdown,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                avg_win=Decimal("0"),
                avg_loss=Decimal("0"),
                avg_trade=Decimal("0"),
                largest_win=Decimal("0"),
                largest_loss=Decimal("0"),
                avg_holding_period_hours=0.0,
                exposure_time_percent=0.0,
            )
        
        # Calculate basic stats
        winning_trades = [t for t in self._trades if t.is_winner]
        losing_trades = [t for t in self._trades if not t.is_winner]
        
        total_pnl = sum((t.pnl for t in self._trades), Decimal("0"))
        gross_profit = sum((t.pnl for t in winning_trades), Decimal("0"))
        gross_loss = abs(sum((t.pnl for t in losing_trades), Decimal("0")))
        
        # Win rate
        win_rate = len(winning_trades) / total_trades * 100 if total_trades > 0 else 0.0
        
        # Profit factor
        profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else float("inf")
        
        # Average trade stats
        avg_win = gross_profit / len(winning_trades) if winning_trades else Decimal("0")
        avg_loss = gross_loss / len(losing_trades) if losing_trades else Decimal("0")
        avg_trade = total_pnl / total_trades if total_trades > 0 else Decimal("0")
        
        # Largest win/loss
        largest_win = max((t.pnl for t in winning_trades), default=Decimal("0"))
        largest_loss = min((t.pnl for t in losing_trades), default=Decimal("0"))
        
        # Total return
        total_return = float((self._cash - self.config.initial_capital) / self.config.initial_capital) * 100
        
        # Average holding period
        holding_periods = []
        for trade in self._trades:
            if trade.exit_time and trade.entry_time:
                duration = (trade.exit_time - trade.entry_time).total_seconds() / 3600
                holding_periods.append(duration)
        avg_holding_period = sum(holding_periods) / len(holding_periods) if holding_periods else 0.0
        
        # Exposure time
        exposure_time = self._calculate_exposure_time(candles)
        
        # Sharpe and Sortino ratios
        sharpe_ratio = self._calculate_sharpe_ratio()
        sortino_ratio = self._calculate_sortino_ratio()
        
        return BacktestMetrics(
            total_return=total_return,
            total_pnl=total_pnl,
            win_rate=win_rate,
            profit_factor=profit_factor,
            max_drawdown=self._max_drawdown,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            total_trades=total_trades,
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            avg_win=avg_win,
            avg_loss=avg_loss,
            avg_trade=avg_trade,
            largest_win=largest_win,
            largest_loss=largest_loss,
            avg_holding_period_hours=avg_holding_period,
            exposure_time_percent=exposure_time,
        )

    
    def _calculate_exposure_time(self, candles: list[Candle]) -> float:
        """
        Calculate the percentage of time with open positions.
        
        Args:
            candles: List of candles
            
        Returns:
            Exposure time as percentage
        """
        if not self._equity_curve:
            return 0.0
        
        exposed_points = sum(1 for p in self._equity_curve if p.position_value > 0)
        return exposed_points / len(self._equity_curve) * 100
    
    def _calculate_sharpe_ratio(self) -> float:
        """
        Calculate the annualized Sharpe ratio.
        
        Returns:
            Sharpe ratio (risk-adjusted return)
            
        Requirements:
            - 7.2: Calculate Sharpe ratio
        """
        if len(self._equity_curve) < 2:
            return 0.0
        
        # Calculate returns
        returns = []
        for i in range(1, len(self._equity_curve)):
            prev_equity = self._equity_curve[i - 1].equity
            curr_equity = self._equity_curve[i].equity
            if prev_equity > 0:
                ret = float((curr_equity - prev_equity) / prev_equity)
                returns.append(ret)
        
        if not returns:
            return 0.0
        
        # Calculate mean and std of returns
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        
        if std_return == 0:
            return 0.0
        
        # Annualize (assuming daily returns, 252 trading days)
        # Adjust based on actual data frequency
        periods_per_year = 252  # Approximate for daily data
        
        annualized_return = mean_return * periods_per_year
        annualized_std = std_return * math.sqrt(periods_per_year)
        
        # Sharpe = (return - risk_free) / std
        sharpe = (annualized_return - self.config.risk_free_rate) / annualized_std
        
        return sharpe
    
    def _calculate_sortino_ratio(self) -> float:
        """
        Calculate the annualized Sortino ratio.
        
        Returns:
            Sortino ratio (downside risk-adjusted return)
            
        Requirements:
            - 7.2: Calculate Sortino ratio
        """
        if len(self._equity_curve) < 2:
            return 0.0
        
        # Calculate returns
        returns = []
        for i in range(1, len(self._equity_curve)):
            prev_equity = self._equity_curve[i - 1].equity
            curr_equity = self._equity_curve[i].equity
            if prev_equity > 0:
                ret = float((curr_equity - prev_equity) / prev_equity)
                returns.append(ret)
        
        if not returns:
            return 0.0
        
        # Calculate mean return
        mean_return = np.mean(returns)
        
        # Calculate downside deviation (only negative returns)
        negative_returns = [r for r in returns if r < 0]
        if not negative_returns:
            return float("inf") if mean_return > 0 else 0.0
        
        downside_std = np.std(negative_returns)
        
        if downside_std == 0:
            return 0.0
        
        # Annualize
        periods_per_year = 252
        annualized_return = mean_return * periods_per_year
        annualized_downside_std = downside_std * math.sqrt(periods_per_year)
        
        # Sortino = (return - risk_free) / downside_std
        sortino = (annualized_return - self.config.risk_free_rate) / annualized_downside_std
        
        return sortino
    
    def generate_report(self, result: BacktestResult) -> dict[str, Any]:
        """
        Generate a detailed backtest report.
        
        Args:
            result: BacktestResult from a backtest run
            
        Returns:
            Dictionary with complete report data
            
        Requirements:
            - 7.5: Generate report with trade-by-trade breakdown and equity curve data
        """
        return {
            "summary": {
                "symbol": result.symbol,
                "start_time": result.start_time.isoformat(),
                "end_time": result.end_time.isoformat(),
                "initial_capital": str(result.initial_capital),
                "final_capital": str(result.final_capital),
            },
            "metrics": {
                "total_return": result.metrics.total_return,
                "total_pnl": str(result.metrics.total_pnl),
                "win_rate": result.metrics.win_rate,
                "profit_factor": result.metrics.profit_factor,
                "max_drawdown": result.metrics.max_drawdown,
                "sharpe_ratio": result.metrics.sharpe_ratio,
                "sortino_ratio": result.metrics.sortino_ratio,
                "total_trades": result.metrics.total_trades,
                "winning_trades": result.metrics.winning_trades,
                "losing_trades": result.metrics.losing_trades,
                "avg_win": str(result.metrics.avg_win),
                "avg_loss": str(result.metrics.avg_loss),
                "avg_trade": str(result.metrics.avg_trade),
                "largest_win": str(result.metrics.largest_win),
                "largest_loss": str(result.metrics.largest_loss),
                "avg_holding_period_hours": result.metrics.avg_holding_period_hours,
                "exposure_time_percent": result.metrics.exposure_time_percent,
            },
            "trades": [
                {
                    "trade_id": t.trade_id,
                    "direction": t.direction.value,
                    "entry_time": t.entry_time.isoformat(),
                    "entry_price": str(t.entry_price),
                    "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                    "exit_price": str(t.exit_price) if t.exit_price else None,
                    "quantity": str(t.quantity),
                    "pnl": str(t.pnl),
                    "pnl_percent": t.pnl_percent,
                    "is_winner": t.is_winner,
                }
                for t in result.trades
            ],
            "equity_curve": [
                {
                    "timestamp": p.timestamp.isoformat(),
                    "equity": str(p.equity),
                    "drawdown": p.drawdown,
                }
                for p in result.equity_curve
            ],
            "config": result.config,
        }


# Export public API
__all__ = [
    "Backtester",
    "BacktesterConfig",
    "BacktestResult",
    "BacktestMetrics",
    "BacktestTrade",
    "EquityPoint",
    "TradeDirection",
]
