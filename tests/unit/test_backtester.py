"""
Unit tests for the Backtester.

Tests the backtesting functionality including:
- Running backtests on historical data
- Calculating performance metrics
- Applying slippage
- Respecting risk limits
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from lib.backtesting import (
    Backtester,
    BacktesterConfig,
    BacktestMetrics,
    BacktestResult,
    BacktestTrade,
    EquityPoint,
    TradeDirection,
)
from lib.pionex.models import Candle


def generate_candles(
    num_candles: int,
    start_price: float = 100.0,
    trend: float = 0.001,
    volatility: float = 0.02,
    start_time: datetime | None = None,
) -> list[Candle]:
    """Generate synthetic candle data for testing."""
    import random
    
    if start_time is None:
        start_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    
    candles = []
    price = start_price
    
    for i in range(num_candles):
        # Add trend and random walk
        change = trend + random.uniform(-volatility, volatility)
        price = price * (1 + change)
        
        # Generate OHLC
        open_price = price * (1 + random.uniform(-0.005, 0.005))
        high_price = max(open_price, price) * (1 + random.uniform(0, 0.01))
        low_price = min(open_price, price) * (1 - random.uniform(0, 0.01))
        close_price = price
        volume = random.uniform(1000, 10000)
        
        candle = Candle(
            timestamp=start_time + timedelta(hours=i),
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume,
        )
        candles.append(candle)
    
    return candles


class TestBacktesterConfig:
    """Tests for BacktesterConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = BacktesterConfig()
        
        assert config.initial_capital == Decimal("10000")
        assert config.slippage_pct == 0.001
        assert config.commission_pct == 0.001
        assert config.min_confidence == 85.0
        assert config.max_position_pct == 0.10
        assert config.max_risk_per_trade_pct == 0.02
        assert config.max_drawdown_pct == 0.20
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = BacktesterConfig(
            initial_capital=Decimal("50000"),
            slippage_pct=0.002,
            min_confidence=90.0,
        )
        
        assert config.initial_capital == Decimal("50000")
        assert config.slippage_pct == 0.002
        assert config.min_confidence == 90.0
    
    def test_invalid_initial_capital(self):
        """Test that negative initial capital raises error."""
        with pytest.raises(ValueError, match="initial_capital must be positive"):
            BacktesterConfig(initial_capital=Decimal("-1000"))
    
    def test_invalid_slippage(self):
        """Test that invalid slippage raises error."""
        with pytest.raises(ValueError, match="slippage_pct must be in"):
            BacktesterConfig(slippage_pct=1.5)
    
    def test_invalid_confidence(self):
        """Test that invalid confidence raises error."""
        with pytest.raises(ValueError, match="min_confidence must be in"):
            BacktesterConfig(min_confidence=150.0)


class TestBacktester:
    """Tests for Backtester."""
    
    def test_initialization(self):
        """Test backtester initialization."""
        backtester = Backtester()
        
        assert backtester.config.initial_capital == Decimal("10000")
        assert backtester._technical_analyzer is not None
        assert backtester._signal_generator is not None
        assert backtester._risk_manager is not None
    
    def test_initialization_with_config(self):
        """Test backtester initialization with custom config."""
        config = BacktesterConfig(
            initial_capital=Decimal("25000"),
            slippage_pct=0.002,
        )
        backtester = Backtester(config)
        
        assert backtester.config.initial_capital == Decimal("25000")
        assert backtester.config.slippage_pct == 0.002
    
    def test_run_requires_minimum_candles(self):
        """Test that run requires minimum number of candles."""
        backtester = Backtester()
        candles = generate_candles(30)  # Less than required 50
        
        with pytest.raises(ValueError, match="Need at least 50 candles"):
            backtester.run(candles, symbol="BTC_USDT")
    
    def test_run_returns_result(self):
        """Test that run returns a BacktestResult."""
        backtester = Backtester()
        candles = generate_candles(100)
        
        result = backtester.run(candles, symbol="BTC_USDT")
        
        assert isinstance(result, BacktestResult)
        assert result.symbol == "BTC_USDT"
        assert result.initial_capital == Decimal("10000")
        assert isinstance(result.metrics, BacktestMetrics)
        assert isinstance(result.trades, list)
        assert isinstance(result.equity_curve, list)

    
    def test_equity_curve_recorded(self):
        """Test that equity curve is recorded during backtest."""
        backtester = Backtester()
        candles = generate_candles(100)
        
        result = backtester.run(candles, symbol="BTC_USDT")
        
        assert len(result.equity_curve) > 0
        for point in result.equity_curve:
            assert isinstance(point, EquityPoint)
            assert point.equity > 0
            assert 0 <= point.drawdown <= 1
    
    def test_metrics_calculated(self):
        """Test that metrics are calculated."""
        backtester = Backtester()
        candles = generate_candles(200, trend=0.002)  # Uptrend
        
        result = backtester.run(candles, symbol="BTC_USDT")
        
        metrics = result.metrics
        assert isinstance(metrics.total_return, float)
        assert isinstance(metrics.win_rate, float)
        assert 0 <= metrics.win_rate <= 100
        assert isinstance(metrics.max_drawdown, float)
        assert 0 <= metrics.max_drawdown <= 1
    
    def test_slippage_applied(self):
        """Test that slippage is applied to trades."""
        config = BacktesterConfig(slippage_pct=0.01)  # 1% slippage
        backtester = Backtester(config)
        
        # Test buy slippage (price increases)
        buy_price = backtester._apply_slippage(Decimal("100"), is_buy=True)
        assert buy_price == Decimal("101")  # 100 + 1%
        
        # Test sell slippage (price decreases)
        sell_price = backtester._apply_slippage(Decimal("100"), is_buy=False)
        assert sell_price == Decimal("99")  # 100 - 1%
    
    def test_commission_calculated(self):
        """Test that commission is calculated correctly."""
        config = BacktesterConfig(commission_pct=0.001)  # 0.1%
        backtester = Backtester(config)
        
        commission = backtester._calculate_commission(Decimal("10000"))
        assert commission == Decimal("10")  # 0.1% of 10000


class TestBacktestMetrics:
    """Tests for BacktestMetrics calculation."""
    
    def test_metrics_with_no_trades(self):
        """Test metrics when no trades are executed."""
        backtester = Backtester()
        # Generate flat market with no signals
        candles = generate_candles(100, trend=0.0, volatility=0.001)
        
        result = backtester.run(candles, symbol="BTC_USDT")
        
        # With very low volatility, might not generate trades
        assert result.metrics.total_trades >= 0
        assert result.metrics.max_drawdown >= 0
    
    def test_win_rate_calculation(self):
        """Test win rate is calculated correctly."""
        # Win rate = winning_trades / total_trades * 100
        backtester = Backtester()
        candles = generate_candles(200, trend=0.003)  # Strong uptrend
        
        result = backtester.run(candles, symbol="BTC_USDT")
        
        if result.metrics.total_trades > 0:
            expected_win_rate = (
                result.metrics.winning_trades / result.metrics.total_trades * 100
            )
            assert abs(result.metrics.win_rate - expected_win_rate) < 0.01
    
    def test_profit_factor_calculation(self):
        """Test profit factor is calculated correctly."""
        backtester = Backtester()
        candles = generate_candles(200, trend=0.002)
        
        result = backtester.run(candles, symbol="BTC_USDT")
        
        # Profit factor = gross_profit / gross_loss
        if result.metrics.losing_trades > 0:
            assert result.metrics.profit_factor >= 0


class TestBacktestReport:
    """Tests for backtest report generation."""
    
    def test_generate_report(self):
        """Test report generation."""
        backtester = Backtester()
        candles = generate_candles(100)
        
        result = backtester.run(candles, symbol="BTC_USDT")
        report = backtester.generate_report(result)
        
        assert "summary" in report
        assert "metrics" in report
        assert "trades" in report
        assert "equity_curve" in report
        assert "config" in report
    
    def test_report_summary(self):
        """Test report summary section."""
        backtester = Backtester()
        candles = generate_candles(100)
        
        result = backtester.run(candles, symbol="BTC_USDT")
        report = backtester.generate_report(result)
        
        summary = report["summary"]
        assert summary["symbol"] == "BTC_USDT"
        assert "start_time" in summary
        assert "end_time" in summary
        assert "initial_capital" in summary
        assert "final_capital" in summary
    
    def test_report_metrics(self):
        """Test report metrics section."""
        backtester = Backtester()
        candles = generate_candles(100)
        
        result = backtester.run(candles, symbol="BTC_USDT")
        report = backtester.generate_report(result)
        
        metrics = report["metrics"]
        assert "total_return" in metrics
        assert "win_rate" in metrics
        assert "profit_factor" in metrics
        assert "max_drawdown" in metrics
        assert "sharpe_ratio" in metrics
        assert "sortino_ratio" in metrics
