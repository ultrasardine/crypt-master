"""
Unit tests for TechnicalAnalyzer.

Tests all technical indicator calculations including RSI, MACD, Bollinger Bands,
SMA, EMA, ADX, Stochastic, and volume analysis.

Requirements tested:
- 3.1: RSI calculation with configurable period (default 14)
- 3.2: MACD calculation with configurable fast/slow/signal periods
- 3.3: Bollinger Bands with configurable period and standard deviation
- 3.4: SMA and EMA with configurable periods
- 3.5: ADX for trend strength measurement
- 3.6: Stochastic oscillator with configurable periods
- 3.7: Volume analysis with anomaly detection (>2x average = anomaly)
- 3.8: Handle insufficient data gracefully with data_insufficient flag
"""

import numpy as np
import pytest

from lib.analysis import (
    IndicatorConfig,
    SignalDirection,
    TechnicalAnalyzer,
)


@pytest.fixture
def analyzer() -> TechnicalAnalyzer:
    """Create a TechnicalAnalyzer with default config."""
    return TechnicalAnalyzer()


@pytest.fixture
def sample_prices() -> np.ndarray:
    """Generate sample price data for testing."""
    # Generate 50 data points with some trend and volatility
    np.random.seed(42)
    base = 100.0
    returns = np.random.randn(50) * 0.02  # 2% daily volatility
    prices = base * np.cumprod(1 + returns)
    return prices


@pytest.fixture
def ohlcv_data() -> dict[str, np.ndarray]:
    """Generate sample OHLCV data for testing."""
    np.random.seed(42)
    n = 50
    
    # Generate close prices
    base = 100.0
    returns = np.random.randn(n) * 0.02
    close = base * np.cumprod(1 + returns)
    
    # Generate high/low around close
    high = close * (1 + np.abs(np.random.randn(n) * 0.01))
    low = close * (1 - np.abs(np.random.randn(n) * 0.01))
    
    # Generate volume
    volume = np.random.uniform(1000, 5000, n)
    
    return {
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


class TestRSI:
    """Tests for RSI calculation - Requirement 3.1."""
    
    def test_rsi_with_sufficient_data(
        self, analyzer: TechnicalAnalyzer, sample_prices: np.ndarray
    ) -> None:
        """RSI should return valid value with sufficient data."""
        result = analyzer.calculate_rsi(sample_prices)
        
        assert result.value is not None
        assert 0 <= result.value <= 100
        assert result.data_insufficient is False
    
    def test_rsi_with_insufficient_data(self, analyzer: TechnicalAnalyzer) -> None:
        """RSI should return data_insufficient=True with too few data points."""
        prices = [100.0, 101.0, 102.0]  # Only 3 points, need 15 for period=14
        result = analyzer.calculate_rsi(prices)
        
        assert result.value is None
        assert result.data_insufficient is True
        assert result.signal == SignalDirection.HOLD
    
    def test_rsi_custom_period(self, analyzer: TechnicalAnalyzer) -> None:
        """RSI should work with custom period."""
        prices = list(range(100, 130))  # 30 data points
        result = analyzer.calculate_rsi(prices, period=7)
        
        assert result.value is not None
        assert result.data_insufficient is False

    
    def test_rsi_overbought_signal(self, analyzer: TechnicalAnalyzer) -> None:
        """RSI >= 70 should generate SELL signal (overbought)."""
        # Create strongly uptrending prices to get high RSI
        prices = [100.0 + i * 2 for i in range(30)]  # Strong uptrend
        result = analyzer.calculate_rsi(prices)
        
        # With strong uptrend, RSI should be high
        assert result.value is not None
        if result.value >= 70:
            assert result.signal == SignalDirection.SELL
    
    def test_rsi_oversold_signal(self, analyzer: TechnicalAnalyzer) -> None:
        """RSI <= 30 should generate BUY signal (oversold)."""
        # Create strongly downtrending prices to get low RSI
        prices = [200.0 - i * 2 for i in range(30)]  # Strong downtrend
        result = analyzer.calculate_rsi(prices)
        
        # With strong downtrend, RSI should be low
        assert result.value is not None
        if result.value <= 30:
            assert result.signal == SignalDirection.BUY


class TestMACD:
    """Tests for MACD calculation - Requirement 3.2."""
    
    def test_macd_with_sufficient_data(
        self, analyzer: TechnicalAnalyzer, sample_prices: np.ndarray
    ) -> None:
        """MACD should return valid values with sufficient data."""
        result = analyzer.calculate_macd(sample_prices)
        
        assert result.macd_line is not None
        assert result.signal_line is not None
        assert result.histogram is not None
        assert result.data_insufficient is False
    
    def test_macd_with_insufficient_data(self, analyzer: TechnicalAnalyzer) -> None:
        """MACD should return data_insufficient=True with too few data points."""
        prices = [100.0 + i for i in range(20)]  # Only 20 points, need 35
        result = analyzer.calculate_macd(prices)
        
        assert result.data_insufficient is True
        assert result.signal == SignalDirection.HOLD
    
    def test_macd_custom_periods(
        self, analyzer: TechnicalAnalyzer, sample_prices: np.ndarray
    ) -> None:
        """MACD should work with custom periods."""
        result = analyzer.calculate_macd(
            sample_prices, fast_period=8, slow_period=17, signal_period=9
        )
        
        assert result.macd_line is not None
        assert result.data_insufficient is False
    
    def test_macd_histogram_calculation(
        self, analyzer: TechnicalAnalyzer, sample_prices: np.ndarray
    ) -> None:
        """MACD histogram should equal MACD line minus signal line."""
        result = analyzer.calculate_macd(sample_prices)
        
        if result.macd_line is not None and result.signal_line is not None:
            expected_hist = result.macd_line - result.signal_line
            assert result.histogram is not None
            assert abs(result.histogram - expected_hist) < 0.0001


class TestBollingerBands:
    """Tests for Bollinger Bands calculation - Requirement 3.3."""
    
    def test_bollinger_with_sufficient_data(
        self, analyzer: TechnicalAnalyzer, sample_prices: np.ndarray
    ) -> None:
        """Bollinger Bands should return valid values with sufficient data."""
        result = analyzer.calculate_bollinger_bands(sample_prices)
        
        assert result.upper_band is not None
        assert result.middle_band is not None
        assert result.lower_band is not None
        assert result.data_insufficient is False
    
    def test_bollinger_band_ordering(
        self, analyzer: TechnicalAnalyzer, sample_prices: np.ndarray
    ) -> None:
        """Bollinger Bands should maintain lower < middle < upper ordering."""
        result = analyzer.calculate_bollinger_bands(sample_prices)
        
        assert result.lower_band is not None
        assert result.middle_band is not None
        assert result.upper_band is not None
        assert result.lower_band < result.middle_band < result.upper_band
    
    def test_bollinger_with_insufficient_data(
        self, analyzer: TechnicalAnalyzer
    ) -> None:
        """Bollinger Bands should return data_insufficient with too few points."""
        prices = [100.0 + i for i in range(10)]  # Only 10 points, need 20
        result = analyzer.calculate_bollinger_bands(prices)
        
        assert result.data_insufficient is True
        assert result.signal == SignalDirection.HOLD
    
    def test_bollinger_custom_params(
        self, analyzer: TechnicalAnalyzer, sample_prices: np.ndarray
    ) -> None:
        """Bollinger Bands should work with custom period and std dev."""
        result = analyzer.calculate_bollinger_bands(
            sample_prices, period=10, std_dev=1.5
        )
        
        assert result.upper_band is not None
        assert result.data_insufficient is False


class TestSMAEMA:
    """Tests for SMA and EMA calculations - Requirement 3.4."""
    
    def test_sma_with_sufficient_data(
        self, analyzer: TechnicalAnalyzer, sample_prices: np.ndarray
    ) -> None:
        """SMA should return valid value with sufficient data."""
        result = analyzer.calculate_sma(sample_prices, period=20)
        
        assert result is not None
    
    def test_sma_with_insufficient_data(self, analyzer: TechnicalAnalyzer) -> None:
        """SMA should return None with insufficient data."""
        prices = [100.0, 101.0, 102.0]
        result = analyzer.calculate_sma(prices, period=20)
        
        assert result is None
    
    def test_ema_with_sufficient_data(
        self, analyzer: TechnicalAnalyzer, sample_prices: np.ndarray
    ) -> None:
        """EMA should return valid value with sufficient data."""
        result = analyzer.calculate_ema(sample_prices, period=20)
        
        assert result is not None
    
    def test_ema_with_insufficient_data(self, analyzer: TechnicalAnalyzer) -> None:
        """EMA should return None with insufficient data."""
        prices = [100.0, 101.0, 102.0]
        result = analyzer.calculate_ema(prices, period=20)
        
        assert result is None


class TestADX:
    """Tests for ADX calculation - Requirement 3.5."""
    
    def test_adx_with_sufficient_data(
        self, analyzer: TechnicalAnalyzer, ohlcv_data: dict[str, np.ndarray]
    ) -> None:
        """ADX should return valid values with sufficient data."""
        result = analyzer.calculate_adx(
            ohlcv_data["high"], ohlcv_data["low"], ohlcv_data["close"]
        )
        
        assert result.adx is not None
        assert result.plus_di is not None
        assert result.minus_di is not None
        assert result.data_insufficient is False
    
    def test_adx_with_insufficient_data(self, analyzer: TechnicalAnalyzer) -> None:
        """ADX should return data_insufficient with too few data points."""
        high = [100.0 + i for i in range(10)]
        low = [99.0 + i for i in range(10)]
        close = [99.5 + i for i in range(10)]
        
        result = analyzer.calculate_adx(high, low, close)
        
        assert result.data_insufficient is True
        assert result.signal == SignalDirection.HOLD
    
    def test_adx_custom_period(
        self, analyzer: TechnicalAnalyzer, ohlcv_data: dict[str, np.ndarray]
    ) -> None:
        """ADX should work with custom period."""
        result = analyzer.calculate_adx(
            ohlcv_data["high"], ohlcv_data["low"], ohlcv_data["close"],
            period=7
        )
        
        assert result.adx is not None
        assert result.data_insufficient is False


class TestStochastic:
    """Tests for Stochastic Oscillator calculation - Requirement 3.6."""
    
    def test_stochastic_with_sufficient_data(
        self, analyzer: TechnicalAnalyzer, ohlcv_data: dict[str, np.ndarray]
    ) -> None:
        """Stochastic should return valid values with sufficient data."""
        result = analyzer.calculate_stochastic(
            ohlcv_data["high"], ohlcv_data["low"], ohlcv_data["close"]
        )
        
        assert result.k is not None
        assert result.d is not None
        assert result.data_insufficient is False
    
    def test_stochastic_bounds(
        self, analyzer: TechnicalAnalyzer, ohlcv_data: dict[str, np.ndarray]
    ) -> None:
        """Stochastic %K and %D should be between 0 and 100."""
        result = analyzer.calculate_stochastic(
            ohlcv_data["high"], ohlcv_data["low"], ohlcv_data["close"]
        )
        
        assert result.k is not None
        assert result.d is not None
        assert 0 <= result.k <= 100
        assert 0 <= result.d <= 100
    
    def test_stochastic_with_insufficient_data(
        self, analyzer: TechnicalAnalyzer
    ) -> None:
        """Stochastic should return data_insufficient with too few points."""
        high = [100.0 + i for i in range(10)]
        low = [99.0 + i for i in range(10)]
        close = [99.5 + i for i in range(10)]
        
        result = analyzer.calculate_stochastic(high, low, close)
        
        assert result.data_insufficient is True
        assert result.signal == SignalDirection.HOLD


class TestVolumeAnalysis:
    """Tests for Volume Analysis - Requirement 3.7."""
    
    def test_volume_analysis_with_sufficient_data(
        self, analyzer: TechnicalAnalyzer, ohlcv_data: dict[str, np.ndarray]
    ) -> None:
        """Volume analysis should return valid values with sufficient data."""
        result = analyzer.analyze_volume(ohlcv_data["volume"])
        
        assert result.current_volume is not None
        assert result.average_volume is not None
        assert result.volume_ratio is not None
        assert result.data_insufficient is False
    
    def test_volume_anomaly_detection(self, analyzer: TechnicalAnalyzer) -> None:
        """Volume > 2x average should be flagged as anomaly."""
        # Create volume data where last value is 3x the average
        volumes = [1000.0] * 21  # 21 values of 1000
        volumes[-1] = 3000.0  # Last value is 3x average
        
        result = analyzer.analyze_volume(volumes)
        
        assert result.is_anomaly is True
        assert result.volume_ratio is not None
        assert result.volume_ratio >= 2.0
    
    def test_volume_no_anomaly(self, analyzer: TechnicalAnalyzer) -> None:
        """Volume < 2x average should not be flagged as anomaly."""
        # Create volume data where last value is 1.5x the average
        volumes = [1000.0] * 21
        volumes[-1] = 1500.0  # Last value is 1.5x average
        
        result = analyzer.analyze_volume(volumes)
        
        assert result.is_anomaly is False
        assert result.volume_ratio is not None
        assert result.volume_ratio < 2.0
    
    def test_volume_with_insufficient_data(self, analyzer: TechnicalAnalyzer) -> None:
        """Volume analysis should return data_insufficient with too few points."""
        volumes = [1000.0, 1100.0, 1200.0]  # Only 3 points
        
        result = analyzer.analyze_volume(volumes)
        
        assert result.data_insufficient is True
    
    def test_volume_custom_threshold(self, analyzer: TechnicalAnalyzer) -> None:
        """Volume analysis should work with custom anomaly threshold."""
        volumes = [1000.0] * 21
        volumes[-1] = 1600.0  # 1.6x average
        
        # With threshold of 1.5, this should be an anomaly
        result = analyzer.analyze_volume(volumes, anomaly_threshold=1.5)
        
        assert result.is_anomaly is True


class TestIndicatorConfig:
    """Tests for IndicatorConfig."""
    
    def test_default_config(self) -> None:
        """Default config should have expected values."""
        config = IndicatorConfig()
        
        assert config.rsi_period == 14
        assert config.macd_fast == 12
        assert config.macd_slow == 26
        assert config.macd_signal == 9
        assert config.bb_period == 20
        assert config.bb_std_dev == 2.0
        assert config.adx_period == 14
        assert config.stoch_k_period == 14
        assert config.stoch_d_period == 3
        assert config.volume_lookback == 20
        assert config.volume_anomaly_threshold == 2.0
    
    def test_custom_config(self) -> None:
        """Custom config should override defaults."""
        config = IndicatorConfig(rsi_period=7, bb_period=10)
        analyzer = TechnicalAnalyzer(config)
        
        assert analyzer.config.rsi_period == 7
        assert analyzer.config.bb_period == 10
        # Other values should remain default
        assert analyzer.config.macd_fast == 12
