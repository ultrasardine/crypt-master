"""
Technical Analysis Library using TA-Lib.

This module provides technical indicator calculations for market analysis,
including RSI, MACD, Bollinger Bands, SMA, EMA, ADX, Stochastic, and volume analysis.

Requirements:
- 3.1: RSI calculation with configurable period (default 14)
- 3.2: MACD calculation with configurable fast/slow/signal periods
- 3.3: Bollinger Bands with configurable period and standard deviation
- 3.4: SMA and EMA with configurable periods
- 3.5: ADX for trend strength measurement
- 3.6: Stochastic oscillator with configurable periods
- 3.7: Volume analysis with anomaly detection (>2x average = anomaly)
- 3.8: Handle insufficient data gracefully with data_insufficient flag
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

import numpy as np
import talib

if TYPE_CHECKING:
    from numpy.typing import NDArray


class SignalDirection(Enum):
    """Direction of a trading signal."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass(frozen=True)
class RSIResult:
    """
    Result of RSI calculation.

    Attributes:
        value: RSI value (0-100)
        signal: Interpreted signal direction
        data_insufficient: Whether there was insufficient data
    """

    value: float | None
    signal: SignalDirection
    data_insufficient: bool = False


@dataclass(frozen=True)
class MACDResult:
    """
    Result of MACD calculation.

    Attributes:
        macd_line: MACD line value (fast EMA - slow EMA)
        signal_line: Signal line value (EMA of MACD line)
        histogram: MACD histogram (MACD line - signal line)
        signal: Interpreted signal direction
        data_insufficient: Whether there was insufficient data
    """

    macd_line: float | None
    signal_line: float | None
    histogram: float | None
    signal: SignalDirection
    data_insufficient: bool = False


@dataclass(frozen=True)
class BollingerResult:
    """
    Result of Bollinger Bands calculation.

    Attributes:
        upper_band: Upper Bollinger Band
        middle_band: Middle band (SMA)
        lower_band: Lower Bollinger Band
        signal: Interpreted signal direction
        data_insufficient: Whether there was insufficient data
    """

    upper_band: float | None
    middle_band: float | None
    lower_band: float | None
    signal: SignalDirection
    data_insufficient: bool = False


@dataclass(frozen=True)
class ADXResult:
    """
    Result of ADX calculation.

    Attributes:
        adx: ADX value (0-100, trend strength)
        plus_di: +DI value
        minus_di: -DI value
        signal: Interpreted signal direction
        data_insufficient: Whether there was insufficient data
    """

    adx: float | None
    plus_di: float | None
    minus_di: float | None
    signal: SignalDirection
    data_insufficient: bool = False


@dataclass(frozen=True)
class StochasticResult:
    """
    Result of Stochastic Oscillator calculation.

    Attributes:
        k: %K value (fast stochastic)
        d: %D value (slow stochastic, SMA of %K)
        signal: Interpreted signal direction
        data_insufficient: Whether there was insufficient data
    """

    k: float | None
    d: float | None
    signal: SignalDirection
    data_insufficient: bool = False


@dataclass(frozen=True)
class VolumeAnalysisResult:
    """
    Result of volume analysis.

    Attributes:
        current_volume: Current period volume
        average_volume: Average volume over the lookback period
        volume_ratio: Ratio of current to average volume
        is_anomaly: Whether current volume is anomalous (>2x average)
        signal: Interpreted signal direction
        data_insufficient: Whether there was insufficient data
    """

    current_volume: float | None
    average_volume: float | None
    volume_ratio: float | None
    is_anomaly: bool
    signal: SignalDirection
    data_insufficient: bool = False


@dataclass
class IndicatorConfig:
    """
    Configuration for technical indicators.

    Attributes:
        rsi_period: Period for RSI calculation (default 14)
        macd_fast: Fast period for MACD (default 12)
        macd_slow: Slow period for MACD (default 26)
        macd_signal: Signal period for MACD (default 9)
        bb_period: Period for Bollinger Bands (default 20)
        bb_std_dev: Standard deviation multiplier for BB (default 2.0)
        adx_period: Period for ADX calculation (default 14)
        stoch_k_period: %K period for Stochastic (default 14)
        stoch_d_period: %D period for Stochastic (default 3)
        stoch_slowing: Slowing period for Stochastic (default 3)
        volume_lookback: Lookback period for volume analysis (default 20)
        volume_anomaly_threshold: Threshold for volume anomaly (default 2.0)
    """

    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bb_period: int = 20
    bb_std_dev: float = 2.0
    adx_period: int = 14
    stoch_k_period: int = 14
    stoch_d_period: int = 3
    stoch_slowing: int = 3
    volume_lookback: int = 20
    volume_anomaly_threshold: float = 2.0


class TechnicalAnalyzer:
    """
    Technical analysis calculator using TA-Lib.

    Provides methods to calculate various technical indicators from OHLCV data.
    All methods handle insufficient data gracefully by returning results with
    the data_insufficient flag set to True.

    Requirements:
        - 3.1: RSI calculation with configurable period (default 14)
        - 3.2: MACD calculation with configurable fast/slow/signal periods
        - 3.3: Bollinger Bands with configurable period and standard deviation
        - 3.4: SMA and EMA with configurable periods
        - 3.5: ADX for trend strength measurement
        - 3.6: Stochastic oscillator with configurable periods
        - 3.7: Volume analysis with anomaly detection (>2x average = anomaly)
        - 3.8: Handle insufficient data gracefully with data_insufficient flag

    Example:
        >>> analyzer = TechnicalAnalyzer()
        >>> prices = np.array([100.0, 101.0, 102.0, ...])  # At least 14 values for RSI
        >>> rsi_result = analyzer.calculate_rsi(prices)
        >>> print(f"RSI: {rsi_result.value}, Signal: {rsi_result.signal}")
    """

    def __init__(self, config: IndicatorConfig | None = None) -> None:
        """
        Initialize the TechnicalAnalyzer.

        Args:
            config: Optional configuration for indicator parameters.
                    Uses defaults if not provided.
        """
        self.config = config or IndicatorConfig()

    def _to_numpy(self, data: list[float] | NDArray[np.floating]) -> NDArray[np.float64]:
        """
        Convert input data to numpy array with float64 dtype.

        Args:
            data: Input price/volume data as list or numpy array

        Returns:
            Numpy array with float64 dtype
        """
        if isinstance(data, np.ndarray):
            return data.astype(np.float64)
        return np.array(data, dtype=np.float64)

    def calculate_rsi(
        self,
        prices: list[float] | NDArray[np.floating],
        period: int | None = None,
    ) -> RSIResult:
        """
        Calculate Relative Strength Index (RSI).

        RSI measures the speed and magnitude of recent price changes to evaluate
        overbought or oversold conditions. Values above 70 indicate overbought
        (potential sell), values below 30 indicate oversold (potential buy).

        Args:
            prices: Array of closing prices
            period: RSI period (default from config, typically 14)

        Returns:
            RSIResult with value, signal, and data_insufficient flag

        Requirements:
            - 3.1: RSI calculation with configurable period (default 14)
            - 3.8: Handle insufficient data gracefully
        """
        period = period or self.config.rsi_period
        prices_arr = self._to_numpy(prices)

        # RSI requires at least period + 1 data points
        min_required = period + 1
        if len(prices_arr) < min_required:
            return RSIResult(
                value=None,
                signal=SignalDirection.HOLD,
                data_insufficient=True,
            )

        try:
            rsi_values = talib.RSI(prices_arr, timeperiod=period)
            # Get the last non-NaN value
            rsi_value = float(rsi_values[-1]) if not np.isnan(rsi_values[-1]) else None

            if rsi_value is None:
                return RSIResult(
                    value=None,
                    signal=SignalDirection.HOLD,
                    data_insufficient=True,
                )

            # Interpret signal
            if rsi_value >= 70:
                signal = SignalDirection.SELL  # Overbought
            elif rsi_value <= 30:
                signal = SignalDirection.BUY  # Oversold
            else:
                signal = SignalDirection.HOLD

            return RSIResult(value=rsi_value, signal=signal)

        except Exception:
            return RSIResult(
                value=None,
                signal=SignalDirection.HOLD,
                data_insufficient=True,
            )

    def calculate_macd(
        self,
        prices: list[float] | NDArray[np.floating],
        fast_period: int | None = None,
        slow_period: int | None = None,
        signal_period: int | None = None,
    ) -> MACDResult:
        """
        Calculate Moving Average Convergence Divergence (MACD).

        MACD shows the relationship between two EMAs. A bullish signal occurs
        when MACD crosses above the signal line, bearish when it crosses below.

        Args:
            prices: Array of closing prices
            fast_period: Fast EMA period (default 12)
            slow_period: Slow EMA period (default 26)
            signal_period: Signal line period (default 9)

        Returns:
            MACDResult with macd_line, signal_line, histogram, and signal

        Requirements:
            - 3.2: MACD calculation with configurable fast/slow/signal periods
            - 3.8: Handle insufficient data gracefully
        """
        fast = fast_period or self.config.macd_fast
        slow = slow_period or self.config.macd_slow
        signal = signal_period or self.config.macd_signal

        prices_arr = self._to_numpy(prices)

        # MACD requires at least slow + signal - 1 data points
        min_required = slow + signal
        if len(prices_arr) < min_required:
            return MACDResult(
                macd_line=None,
                signal_line=None,
                histogram=None,
                signal=SignalDirection.HOLD,
                data_insufficient=True,
            )

        try:
            macd, macd_signal, macd_hist = talib.MACD(
                prices_arr,
                fastperiod=fast,
                slowperiod=slow,
                signalperiod=signal,
            )

            # Get the last non-NaN values
            macd_val = float(macd[-1]) if not np.isnan(macd[-1]) else None
            signal_val = float(macd_signal[-1]) if not np.isnan(macd_signal[-1]) else None
            hist_val = float(macd_hist[-1]) if not np.isnan(macd_hist[-1]) else None

            if macd_val is None or signal_val is None:
                return MACDResult(
                    macd_line=macd_val,
                    signal_line=signal_val,
                    histogram=hist_val,
                    signal=SignalDirection.HOLD,
                    data_insufficient=True,
                )

            # Interpret signal based on MACD line vs signal line
            if macd_val > signal_val:
                sig = SignalDirection.BUY  # Bullish crossover
            elif macd_val < signal_val:
                sig = SignalDirection.SELL  # Bearish crossover
            else:
                sig = SignalDirection.HOLD

            return MACDResult(
                macd_line=macd_val,
                signal_line=signal_val,
                histogram=hist_val,
                signal=sig,
            )

        except Exception:
            return MACDResult(
                macd_line=None,
                signal_line=None,
                histogram=None,
                signal=SignalDirection.HOLD,
                data_insufficient=True,
            )

    def calculate_bollinger_bands(
        self,
        prices: list[float] | NDArray[np.floating],
        period: int | None = None,
        std_dev: float | None = None,
    ) -> BollingerResult:
        """
        Calculate Bollinger Bands.

        Bollinger Bands consist of a middle band (SMA) with upper and lower bands
        at a specified number of standard deviations. Price near upper band may
        indicate overbought, near lower band may indicate oversold.

        Args:
            prices: Array of closing prices
            period: SMA period (default 20)
            std_dev: Standard deviation multiplier (default 2.0)

        Returns:
            BollingerResult with upper, middle, lower bands and signal

        Requirements:
            - 3.3: Bollinger Bands with configurable period and standard deviation
            - 3.8: Handle insufficient data gracefully
        """
        period = period or self.config.bb_period
        std_dev = std_dev or self.config.bb_std_dev

        prices_arr = self._to_numpy(prices)

        # Bollinger Bands require at least period data points
        if len(prices_arr) < period:
            return BollingerResult(
                upper_band=None,
                middle_band=None,
                lower_band=None,
                signal=SignalDirection.HOLD,
                data_insufficient=True,
            )

        try:
            upper, middle, lower = talib.BBANDS(
                prices_arr,
                timeperiod=period,
                nbdevup=std_dev,
                nbdevdn=std_dev,
                matype=0,  # SMA
            )

            upper_val = float(upper[-1]) if not np.isnan(upper[-1]) else None
            middle_val = float(middle[-1]) if not np.isnan(middle[-1]) else None
            lower_val = float(lower[-1]) if not np.isnan(lower[-1]) else None

            if upper_val is None or middle_val is None or lower_val is None:
                return BollingerResult(
                    upper_band=upper_val,
                    middle_band=middle_val,
                    lower_band=lower_val,
                    signal=SignalDirection.HOLD,
                    data_insufficient=True,
                )

            # Interpret signal based on current price position
            current_price = float(prices_arr[-1])
            if current_price >= upper_val:
                sig = SignalDirection.SELL  # At or above upper band
            elif current_price <= lower_val:
                sig = SignalDirection.BUY  # At or below lower band
            else:
                sig = SignalDirection.HOLD

            return BollingerResult(
                upper_band=upper_val,
                middle_band=middle_val,
                lower_band=lower_val,
                signal=sig,
            )

        except Exception:
            return BollingerResult(
                upper_band=None,
                middle_band=None,
                lower_band=None,
                signal=SignalDirection.HOLD,
                data_insufficient=True,
            )

    def calculate_sma(
        self,
        prices: list[float] | NDArray[np.floating],
        period: int,
    ) -> float | None:
        """
        Calculate Simple Moving Average (SMA).

        SMA is the arithmetic mean of prices over a specified period.

        Args:
            prices: Array of closing prices
            period: Number of periods for the average

        Returns:
            SMA value or None if insufficient data

        Requirements:
            - 3.4: SMA with configurable periods
            - 3.8: Handle insufficient data gracefully
        """
        prices_arr = self._to_numpy(prices)

        if len(prices_arr) < period:
            return None

        try:
            sma_values = talib.SMA(prices_arr, timeperiod=period)
            result = float(sma_values[-1])
            return result if not np.isnan(result) else None
        except Exception:
            return None

    def calculate_ema(
        self,
        prices: list[float] | NDArray[np.floating],
        period: int,
    ) -> float | None:
        """
        Calculate Exponential Moving Average (EMA).

        EMA gives more weight to recent prices, making it more responsive
        to new information than SMA.

        Args:
            prices: Array of closing prices
            period: Number of periods for the average

        Returns:
            EMA value or None if insufficient data

        Requirements:
            - 3.4: EMA with configurable periods
            - 3.8: Handle insufficient data gracefully
        """
        prices_arr = self._to_numpy(prices)

        if len(prices_arr) < period:
            return None

        try:
            ema_values = talib.EMA(prices_arr, timeperiod=period)
            result = float(ema_values[-1])
            return result if not np.isnan(result) else None
        except Exception:
            return None

    def calculate_adx(
        self,
        high: list[float] | NDArray[np.floating],
        low: list[float] | NDArray[np.floating],
        close: list[float] | NDArray[np.floating],
        period: int | None = None,
    ) -> ADXResult:
        """
        Calculate Average Directional Index (ADX).

        ADX measures trend strength regardless of direction. Values above 25
        indicate a strong trend, below 20 indicate a weak or ranging market.
        +DI and -DI indicate trend direction.

        Args:
            high: Array of high prices
            low: Array of low prices
            close: Array of closing prices
            period: ADX period (default 14)

        Returns:
            ADXResult with adx, plus_di, minus_di, and signal

        Requirements:
            - 3.5: ADX for trend strength measurement
            - 3.8: Handle insufficient data gracefully
        """
        period = period or self.config.adx_period

        high_arr = self._to_numpy(high)
        low_arr = self._to_numpy(low)
        close_arr = self._to_numpy(close)

        # ADX requires at least 2 * period data points
        min_required = 2 * period
        min_len = min(len(high_arr), len(low_arr), len(close_arr))

        if min_len < min_required:
            return ADXResult(
                adx=None,
                plus_di=None,
                minus_di=None,
                signal=SignalDirection.HOLD,
                data_insufficient=True,
            )

        try:
            adx_values = talib.ADX(high_arr, low_arr, close_arr, timeperiod=period)
            plus_di_values = talib.PLUS_DI(high_arr, low_arr, close_arr, timeperiod=period)
            minus_di_values = talib.MINUS_DI(high_arr, low_arr, close_arr, timeperiod=period)

            adx_val = float(adx_values[-1]) if not np.isnan(adx_values[-1]) else None
            plus_di_val = float(plus_di_values[-1]) if not np.isnan(plus_di_values[-1]) else None
            minus_di_val = float(minus_di_values[-1]) if not np.isnan(minus_di_values[-1]) else None

            if adx_val is None or plus_di_val is None or minus_di_val is None:
                return ADXResult(
                    adx=adx_val,
                    plus_di=plus_di_val,
                    minus_di=minus_di_val,
                    signal=SignalDirection.HOLD,
                    data_insufficient=True,
                )

            # Interpret signal: strong trend (ADX > 25) with direction
            if adx_val >= 25:
                if plus_di_val > minus_di_val:
                    sig = SignalDirection.BUY  # Strong uptrend
                else:
                    sig = SignalDirection.SELL  # Strong downtrend
            else:
                sig = SignalDirection.HOLD  # Weak trend, no clear direction

            return ADXResult(
                adx=adx_val,
                plus_di=plus_di_val,
                minus_di=minus_di_val,
                signal=sig,
            )

        except Exception:
            return ADXResult(
                adx=None,
                plus_di=None,
                minus_di=None,
                signal=SignalDirection.HOLD,
                data_insufficient=True,
            )

    def calculate_stochastic(
        self,
        high: list[float] | NDArray[np.floating],
        low: list[float] | NDArray[np.floating],
        close: list[float] | NDArray[np.floating],
        k_period: int | None = None,
        d_period: int | None = None,
        slowing: int | None = None,
    ) -> StochasticResult:
        """
        Calculate Stochastic Oscillator.

        The Stochastic Oscillator compares a closing price to its price range
        over a given period. %K above 80 indicates overbought, below 20 indicates
        oversold.

        Args:
            high: Array of high prices
            low: Array of low prices
            close: Array of closing prices
            k_period: %K period (default 14)
            d_period: %D period (default 3)
            slowing: Slowing period (default 3)

        Returns:
            StochasticResult with k, d values and signal

        Requirements:
            - 3.6: Stochastic oscillator with configurable periods
            - 3.8: Handle insufficient data gracefully
        """
        k_period = k_period or self.config.stoch_k_period
        d_period = d_period or self.config.stoch_d_period
        slowing = slowing or self.config.stoch_slowing

        high_arr = self._to_numpy(high)
        low_arr = self._to_numpy(low)
        close_arr = self._to_numpy(close)

        # Stochastic requires at least k_period + slowing + d_period data points
        min_required = k_period + slowing + d_period
        min_len = min(len(high_arr), len(low_arr), len(close_arr))

        if min_len < min_required:
            return StochasticResult(
                k=None,
                d=None,
                signal=SignalDirection.HOLD,
                data_insufficient=True,
            )

        try:
            slowk, slowd = talib.STOCH(
                high_arr,
                low_arr,
                close_arr,
                fastk_period=k_period,
                slowk_period=slowing,
                slowk_matype=0,
                slowd_period=d_period,
                slowd_matype=0,
            )

            k_val = float(slowk[-1]) if not np.isnan(slowk[-1]) else None
            d_val = float(slowd[-1]) if not np.isnan(slowd[-1]) else None

            if k_val is None or d_val is None:
                return StochasticResult(
                    k=k_val,
                    d=d_val,
                    signal=SignalDirection.HOLD,
                    data_insufficient=True,
                )

            # Interpret signal based on %K value
            if k_val >= 80:
                sig = SignalDirection.SELL  # Overbought
            elif k_val <= 20:
                sig = SignalDirection.BUY  # Oversold
            else:
                sig = SignalDirection.HOLD

            return StochasticResult(k=k_val, d=d_val, signal=sig)

        except Exception:
            return StochasticResult(
                k=None,
                d=None,
                signal=SignalDirection.HOLD,
                data_insufficient=True,
            )

    def analyze_volume(
        self,
        volumes: list[float] | NDArray[np.floating],
        lookback: int | None = None,
        anomaly_threshold: float | None = None,
    ) -> VolumeAnalysisResult:
        """
        Analyze volume for anomalies.

        Compares current volume to the average volume over a lookback period.
        Volume greater than the threshold multiplied by average is considered
        an anomaly, which may indicate significant market interest.

        Args:
            volumes: Array of volume data
            lookback: Number of periods for average calculation (default 20)
            anomaly_threshold: Multiplier for anomaly detection (default 2.0)

        Returns:
            VolumeAnalysisResult with current, average, ratio, and anomaly flag

        Requirements:
            - 3.7: Volume analysis with anomaly detection (>2x average = anomaly)
            - 3.8: Handle insufficient data gracefully
        """
        lookback = lookback or self.config.volume_lookback
        threshold = anomaly_threshold or self.config.volume_anomaly_threshold

        volumes_arr = self._to_numpy(volumes)

        # Need at least lookback + 1 data points (lookback for average, 1 for current)
        if len(volumes_arr) < lookback + 1:
            return VolumeAnalysisResult(
                current_volume=float(volumes_arr[-1]) if len(volumes_arr) > 0 else None,
                average_volume=None,
                volume_ratio=None,
                is_anomaly=False,
                signal=SignalDirection.HOLD,
                data_insufficient=True,
            )

        try:
            current_vol = float(volumes_arr[-1])
            # Calculate average of previous 'lookback' periods (excluding current)
            avg_vol = float(np.mean(volumes_arr[-lookback - 1 : -1]))

            if avg_vol <= 0:
                return VolumeAnalysisResult(
                    current_volume=current_vol,
                    average_volume=avg_vol,
                    volume_ratio=None,
                    is_anomaly=False,
                    signal=SignalDirection.HOLD,
                    data_insufficient=True,
                )

            ratio = current_vol / avg_vol
            is_anomaly = ratio >= threshold

            # High volume can indicate strong conviction in current price movement
            # We don't assign BUY/SELL based on volume alone, but flag it
            sig = SignalDirection.HOLD

            return VolumeAnalysisResult(
                current_volume=current_vol,
                average_volume=avg_vol,
                volume_ratio=ratio,
                is_anomaly=is_anomaly,
                signal=sig,
            )

        except Exception:
            return VolumeAnalysisResult(
                current_volume=None,
                average_volume=None,
                volume_ratio=None,
                is_anomaly=False,
                signal=SignalDirection.HOLD,
                data_insufficient=True,
            )
