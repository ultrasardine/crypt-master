"""
Property-based tests for Technical Analysis Module.

Feature: pionex-trading-bot
Properties:
- Property 3: RSI Calculation Bounds
- Property 4: MACD Calculation Correctness
- Property 5: Bollinger Bands Ordering

These tests use the hypothesis library to verify that technical indicators
behave correctly across a wide range of inputs.

**Validates: Requirements 3.1, 3.2, 3.3**
"""

import numpy as np
import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from lib.analysis.technical import TechnicalAnalyzer, IndicatorConfig


# =============================================================================
# Custom Strategies for Generating Realistic Price Data
# =============================================================================

def price_series_strategy(
    min_size: int = 50,
    max_size: int = 200,
    min_price: float = 1.0,
    max_price: float = 100000.0,
) -> st.SearchStrategy:
    """
    Generate realistic price series data.
    
    Prices are positive values within reasonable cryptocurrency ranges.
    The series simulates price movements with random walk behavior.
    """
    return st.lists(
        st.floats(
            min_value=min_price,
            max_value=max_price,
            allow_nan=False,
            allow_infinity=False,
        ),
        min_size=min_size,
        max_size=max_size,
    ).filter(lambda x: all(p > 0 for p in x))


def random_walk_prices_strategy(
    min_size: int = 50,
    max_size: int = 200,
    base_price: float = 100.0,
    volatility: float = 0.05,
) -> st.SearchStrategy:
    """
    Generate price series using random walk model.
    
    This produces more realistic price data that mimics actual market behavior.
    """
    @st.composite
    def _random_walk(draw: st.DrawFn) -> list[float]:
        size = draw(st.integers(min_value=min_size, max_value=max_size))
        # Generate returns between -volatility and +volatility
        returns = draw(
            st.lists(
                st.floats(
                    min_value=-volatility,
                    max_value=volatility,
                    allow_nan=False,
                    allow_infinity=False,
                ),
                min_size=size,
                max_size=size,
            )
        )
        
        # Build price series from returns
        prices = [base_price]
        for r in returns[:-1]:  # Use size-1 returns to get size prices
            new_price = prices[-1] * (1 + r)
            # Ensure price stays positive
            new_price = max(new_price, 0.01)
            prices.append(new_price)
        
        return prices
    
    return _random_walk()


# Strategy for RSI period (must be positive, reasonable range)
rsi_period_strategy = st.integers(min_value=2, max_value=50)

# Strategy for MACD periods (fast < slow, all positive)
@st.composite
def macd_periods_strategy(draw: st.DrawFn) -> tuple[int, int, int]:
    """Generate valid MACD periods where fast < slow."""
    fast = draw(st.integers(min_value=2, max_value=20))
    slow = draw(st.integers(min_value=fast + 1, max_value=50))
    signal = draw(st.integers(min_value=2, max_value=20))
    return fast, slow, signal


# Strategy for Bollinger Bands parameters
bb_period_strategy = st.integers(min_value=2, max_value=50)
bb_std_dev_strategy = st.floats(
    min_value=0.5,
    max_value=4.0,
    allow_nan=False,
    allow_infinity=False,
)


# =============================================================================
# Property 3: RSI Calculation Bounds
# =============================================================================

class TestRSICalculationBounds:
    """
    Property 3: RSI Calculation Bounds
    
    *For any* valid price series with sufficient data, RSI SHALL produce
    a value in [0, 100].
    
    **Validates: Requirements 3.1**
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(
        prices=price_series_strategy(min_size=50, max_size=200),
        period=rsi_period_strategy,
    )
    def test_rsi_always_in_bounds(
        self,
        prices: list[float],
        period: int,
    ) -> None:
        """
        Property: RSI value is always within [0, 100] for any valid price series.
        
        **Validates: Requirements 3.1**
        """
        # Ensure we have enough data for the given period
        assume(len(prices) >= period + 1)
        
        analyzer = TechnicalAnalyzer()
        result = analyzer.calculate_rsi(prices, period=period)
        
        # If we have sufficient data, RSI should be calculated
        if not result.data_insufficient and result.value is not None:
            assert 0 <= result.value <= 100, (
                f"RSI value {result.value} is outside [0, 100] bounds "
                f"for period={period}, prices length={len(prices)}"
            )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(prices=random_walk_prices_strategy(min_size=50, max_size=200))
    def test_rsi_bounds_with_random_walk_prices(
        self,
        prices: list[float],
    ) -> None:
        """
        Property: RSI is bounded [0, 100] for realistic random walk price data.
        
        **Validates: Requirements 3.1**
        """
        analyzer = TechnicalAnalyzer()
        result = analyzer.calculate_rsi(prices)
        
        if not result.data_insufficient and result.value is not None:
            assert 0 <= result.value <= 100, (
                f"RSI value {result.value} is outside [0, 100] bounds"
            )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(
        base_price=st.floats(min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        trend_factor=st.floats(min_value=0.001, max_value=0.1, allow_nan=False, allow_infinity=False),
        size=st.integers(min_value=50, max_value=150),
    )
    def test_rsi_bounds_with_trending_prices(
        self,
        base_price: float,
        trend_factor: float,
        size: int,
    ) -> None:
        """
        Property: RSI is bounded [0, 100] even for strongly trending prices.
        
        Strong uptrends should push RSI toward 100, strong downtrends toward 0,
        but never exceed these bounds.
        
        **Validates: Requirements 3.1**
        """
        # Generate uptrending prices
        uptrend_prices = [base_price * (1 + trend_factor) ** i for i in range(size)]
        
        # Generate downtrending prices
        downtrend_prices = [base_price * (1 - trend_factor * 0.5) ** i for i in range(size)]
        # Ensure prices stay positive
        downtrend_prices = [max(p, 0.01) for p in downtrend_prices]
        
        analyzer = TechnicalAnalyzer()
        
        # Test uptrend
        result_up = analyzer.calculate_rsi(uptrend_prices)
        if not result_up.data_insufficient and result_up.value is not None:
            assert 0 <= result_up.value <= 100, (
                f"RSI {result_up.value} out of bounds for uptrend"
            )
        
        # Test downtrend
        result_down = analyzer.calculate_rsi(downtrend_prices)
        if not result_down.data_insufficient and result_down.value is not None:
            assert 0 <= result_down.value <= 100, (
                f"RSI {result_down.value} out of bounds for downtrend"
            )


# =============================================================================
# Property 4: MACD Calculation Correctness
# =============================================================================

class TestMACDCalculationCorrectness:
    """
    Property 4: MACD Calculation Correctness
    
    *For any* price series with fast < slow, MACD histogram SHALL equal
    MACD line minus signal line.
    
    **Validates: Requirements 3.2**
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(
        prices=price_series_strategy(min_size=60, max_size=200),
        periods=macd_periods_strategy(),
    )
    def test_macd_histogram_equals_macd_minus_signal(
        self,
        prices: list[float],
        periods: tuple[int, int, int],
    ) -> None:
        """
        Property: MACD histogram = MACD line - signal line.
        
        **Validates: Requirements 3.2**
        """
        fast, slow, signal = periods
        
        # Ensure we have enough data
        min_required = slow + signal
        assume(len(prices) >= min_required)
        
        analyzer = TechnicalAnalyzer()
        result = analyzer.calculate_macd(
            prices,
            fast_period=fast,
            slow_period=slow,
            signal_period=signal,
        )
        
        if not result.data_insufficient:
            if (result.macd_line is not None and 
                result.signal_line is not None and 
                result.histogram is not None):
                
                expected_histogram = result.macd_line - result.signal_line
                
                # Allow small floating point tolerance
                assert abs(result.histogram - expected_histogram) < 1e-10, (
                    f"MACD histogram {result.histogram} != "
                    f"MACD line {result.macd_line} - signal line {result.signal_line} "
                    f"(expected {expected_histogram})"
                )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(prices=random_walk_prices_strategy(min_size=60, max_size=200))
    def test_macd_histogram_correctness_with_random_walk(
        self,
        prices: list[float],
    ) -> None:
        """
        Property: MACD histogram calculation is correct for random walk prices.
        
        **Validates: Requirements 3.2**
        """
        analyzer = TechnicalAnalyzer()
        result = analyzer.calculate_macd(prices)
        
        if not result.data_insufficient:
            if (result.macd_line is not None and 
                result.signal_line is not None and 
                result.histogram is not None):
                
                expected_histogram = result.macd_line - result.signal_line
                
                assert abs(result.histogram - expected_histogram) < 1e-10, (
                    f"MACD histogram calculation incorrect: "
                    f"got {result.histogram}, expected {expected_histogram}"
                )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(prices=random_walk_prices_strategy(min_size=60, max_size=200))
    def test_macd_components_are_finite(
        self,
        prices: list[float],
    ) -> None:
        """
        Property: MACD components are always finite numbers when calculated.
        
        This verifies that MACD calculations don't produce NaN or infinity
        for any valid price series.
        
        **Validates: Requirements 3.2**
        """
        analyzer = TechnicalAnalyzer()
        result = analyzer.calculate_macd(prices)
        
        if not result.data_insufficient:
            if result.macd_line is not None:
                assert np.isfinite(result.macd_line), (
                    f"MACD line is not finite: {result.macd_line}"
                )
            if result.signal_line is not None:
                assert np.isfinite(result.signal_line), (
                    f"Signal line is not finite: {result.signal_line}"
                )
            if result.histogram is not None:
                assert np.isfinite(result.histogram), (
                    f"Histogram is not finite: {result.histogram}"
                )


# =============================================================================
# Property 5: Bollinger Bands Ordering
# =============================================================================

class TestBollingerBandsOrdering:
    """
    Property 5: Bollinger Bands Ordering
    
    *For any* valid price series, lower_band < middle_band < upper_band.
    
    **Validates: Requirements 3.3**
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(
        prices=price_series_strategy(min_size=30, max_size=200),
        period=bb_period_strategy,
        std_dev=bb_std_dev_strategy,
    )
    def test_bollinger_bands_ordering(
        self,
        prices: list[float],
        period: int,
        std_dev: float,
    ) -> None:
        """
        Property: Bollinger Bands maintain lower <= middle <= upper ordering.
        
        Note: With zero variance (constant prices), bands converge to the same value,
        so we use <= instead of <. For any price series with variance > 0,
        strict ordering (lower < middle < upper) holds.
        
        **Validates: Requirements 3.3**
        """
        # Ensure we have enough data for the period
        assume(len(prices) >= period)
        
        # Filter out constant price series (zero variance edge case)
        # The property lower < middle < upper only holds when there's price variance
        price_set = set(prices[-period:])  # Check variance in the lookback window
        assume(len(price_set) > 1)  # Require at least some price variation
        
        analyzer = TechnicalAnalyzer()
        result = analyzer.calculate_bollinger_bands(
            prices,
            period=period,
            std_dev=std_dev,
        )
        
        if not result.data_insufficient:
            if (result.lower_band is not None and 
                result.middle_band is not None and 
                result.upper_band is not None):
                
                assert result.lower_band < result.middle_band, (
                    f"Lower band {result.lower_band} >= middle band {result.middle_band}"
                )
                assert result.middle_band < result.upper_band, (
                    f"Middle band {result.middle_band} >= upper band {result.upper_band}"
                )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(prices=random_walk_prices_strategy(min_size=30, max_size=200))
    def test_bollinger_bands_ordering_with_random_walk(
        self,
        prices: list[float],
    ) -> None:
        """
        Property: Bollinger Bands ordering holds for random walk price data.
        
        Note: With zero variance (constant prices), bands converge to the same value.
        We filter out such edge cases as they are mathematically correct but
        don't satisfy the strict ordering property.
        
        **Validates: Requirements 3.3**
        """
        # Filter out constant price series
        price_set = set(prices[-20:])  # Check variance in default BB period window
        assume(len(price_set) > 1)  # Require at least some price variation
        
        analyzer = TechnicalAnalyzer()
        result = analyzer.calculate_bollinger_bands(prices)
        
        if not result.data_insufficient:
            if (result.lower_band is not None and 
                result.middle_band is not None and 
                result.upper_band is not None):
                
                assert result.lower_band < result.middle_band < result.upper_band, (
                    f"Bollinger Bands ordering violated: "
                    f"lower={result.lower_band}, middle={result.middle_band}, "
                    f"upper={result.upper_band}"
                )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(
        constant_price=st.floats(
            min_value=1.0,
            max_value=10000.0,
            allow_nan=False,
            allow_infinity=False,
        ),
        size=st.integers(min_value=30, max_value=100),
        period=bb_period_strategy,
    )
    def test_bollinger_bands_with_constant_prices(
        self,
        constant_price: float,
        size: int,
        period: int,
    ) -> None:
        """
        Property: Bollinger Bands handle constant prices gracefully.
        
        With constant prices, standard deviation is 0, so bands should converge
        to the middle band (or the implementation should handle this edge case).
        
        **Validates: Requirements 3.3**
        """
        assume(size >= period)
        
        # Create constant price series
        prices = [constant_price] * size
        
        analyzer = TechnicalAnalyzer()
        result = analyzer.calculate_bollinger_bands(prices, period=period)
        
        if not result.data_insufficient:
            if (result.lower_band is not None and 
                result.middle_band is not None and 
                result.upper_band is not None):
                
                # With constant prices, all bands should equal the price
                # (since std dev is 0)
                assert abs(result.middle_band - constant_price) < 0.01, (
                    f"Middle band {result.middle_band} != constant price {constant_price}"
                )
                # Lower and upper should also equal middle when std dev is 0
                assert abs(result.lower_band - result.middle_band) < 0.01, (
                    f"Lower band {result.lower_band} != middle band {result.middle_band} "
                    f"for constant prices"
                )
                assert abs(result.upper_band - result.middle_band) < 0.01, (
                    f"Upper band {result.upper_band} != middle band {result.middle_band} "
                    f"for constant prices"
                )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(
        prices=price_series_strategy(min_size=30, max_size=200),
        period=bb_period_strategy,
        std_dev=bb_std_dev_strategy,
    )
    def test_bollinger_bands_symmetry(
        self,
        prices: list[float],
        period: int,
        std_dev: float,
    ) -> None:
        """
        Property: Bollinger Bands are symmetric around the middle band.
        
        The distance from middle to upper should equal the distance from
        middle to lower (both are std_dev * standard_deviation).
        
        **Validates: Requirements 3.3**
        """
        assume(len(prices) >= period)
        
        analyzer = TechnicalAnalyzer()
        result = analyzer.calculate_bollinger_bands(
            prices,
            period=period,
            std_dev=std_dev,
        )
        
        if not result.data_insufficient:
            if (result.lower_band is not None and 
                result.middle_band is not None and 
                result.upper_band is not None):
                
                upper_distance = result.upper_band - result.middle_band
                lower_distance = result.middle_band - result.lower_band
                
                # Distances should be equal (symmetric)
                assert abs(upper_distance - lower_distance) < 1e-10, (
                    f"Bollinger Bands not symmetric: "
                    f"upper distance={upper_distance}, lower distance={lower_distance}"
                )
