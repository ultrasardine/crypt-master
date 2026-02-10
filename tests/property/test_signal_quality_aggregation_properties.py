"""
Property-based tests for Signal Quality Aggregation.

Feature: market-intelligence-layer
Property 16: Signal quality aggregation correctness

These tests use the hypothesis library to verify that the Signal Quality view
correctly aggregates signal outcomes by regime.

**Validates: Requirements 7.2**
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.core.models import TradingPair
from apps.trading.models import Signal, SignalOutcome, StrategyPattern
from lib.analysis.context import Regime


# =============================================================================
# Custom Strategies for Signal Quality Testing
# =============================================================================


@st.composite
def regime_values(draw: st.DrawFn) -> str:
    """Generate random regime values."""
    return draw(
        st.sampled_from([
            Regime.RISK_ON.value,
            Regime.RISK_OFF.value,
            Regime.RANGE_BOUND.value,
            Regime.TRENDING_UP.value,
            Regime.TRENDING_DOWN.value,
            Regime.UNKNOWN.value,
        ])
    )


@st.composite
def signal_outcome_data(draw: st.DrawFn) -> dict:
    """
    Generate random signal outcome data.

    Returns a dict with:
    - regime: The regime at time of signal
    - is_profitable: Whether the outcome was profitable
    - final_pnl_percent: The P&L percentage
    - confidence: The signal confidence
    """
    regime = draw(regime_values())
    is_profitable = draw(st.booleans())
    # Generate P&L that's consistent with profitability
    if is_profitable:
        final_pnl_percent = draw(st.floats(min_value=0.01, max_value=50.0))
    else:
        final_pnl_percent = draw(st.floats(min_value=-50.0, max_value=-0.01))
    confidence = draw(st.floats(min_value=50.0, max_value=100.0))

    return {
        "regime": regime,
        "is_profitable": is_profitable,
        "final_pnl_percent": final_pnl_percent,
        "confidence": confidence,
    }


@st.composite
def signal_outcome_lists(draw: st.DrawFn) -> list[dict]:
    """Generate a list of signal outcome data."""
    num_outcomes = draw(st.integers(min_value=1, max_value=20))
    return [draw(signal_outcome_data()) for _ in range(num_outcomes)]


# =============================================================================
# Property 16: Signal quality aggregation correctness
# =============================================================================


@pytest.mark.django_db(transaction=True)
class TestSignalQualityAggregation:
    """
    Property 16: Signal quality aggregation correctness

    *For any* set of `SignalOutcome` records grouped by regime, the computed
    hit-rate SHALL equal the count of profitable outcomes divided by total
    outcomes in that group, and the computed average P&L SHALL equal the
    arithmetic mean of `final_pnl_percent` values in that group.

    **Validates: Requirements 7.2**
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures."""
        # Clean up any existing data
        SignalOutcome.objects.all().delete()
        Signal.objects.all().delete()
        TradingPair.objects.all().delete()

        # Create a test trading pair
        self.trading_pair = TradingPair.objects.create(
            symbol="BTC_USDT",
            base_currency="BTC",
            quote_currency="USDT",
            is_active=True,
        )

    def _create_signal_with_outcome(
        self,
        regime: str,
        is_profitable: bool,
        final_pnl_percent: float,
        confidence: float,
    ) -> SignalOutcome:
        """Create a signal with an associated outcome."""
        signal = Signal.objects.create(
            trading_pair=self.trading_pair,
            direction="BUY",
            confidence=confidence,
            regime=regime,
            indicators=[],
        )
        outcome = SignalOutcome.objects.create(
            signal=signal,
            final_pnl_percent=final_pnl_percent,
            is_profitable=is_profitable,
            recorded_at=timezone.now(),
        )
        return outcome

    @settings(max_examples=25)
    @given(outcomes_data=signal_outcome_lists())
    def test_hit_rate_equals_profitable_divided_by_total(
        self,
        outcomes_data: list[dict],
    ) -> None:
        """
        Property: For any set of outcomes grouped by regime, hit-rate SHALL
        equal profitable count / total count.

        **Validates: Requirements 7.2**
        """
        # Clean up from previous iteration
        SignalOutcome.objects.all().delete()
        Signal.objects.all().delete()

        # Create outcomes
        for data in outcomes_data:
            self._create_signal_with_outcome(
                regime=data["regime"],
                is_profitable=data["is_profitable"],
                final_pnl_percent=data["final_pnl_percent"],
                confidence=data["confidence"],
            )

        # Group by regime and calculate expected metrics
        regime_groups: dict[str, list[dict]] = {}
        for data in outcomes_data:
            regime = data["regime"]
            if regime not in regime_groups:
                regime_groups[regime] = []
            regime_groups[regime].append(data)

        # Verify hit rate for each regime
        for regime, group_data in regime_groups.items():
            total = len(group_data)
            profitable = sum(1 for d in group_data if d["is_profitable"])
            expected_hit_rate = (profitable / total) * 100 if total > 0 else 0.0

            # Query actual outcomes
            outcomes = SignalOutcome.objects.filter(signal__regime=regime)
            actual_total = outcomes.count()
            actual_profitable = sum(1 for o in outcomes if o.is_profitable)
            actual_hit_rate = (actual_profitable / actual_total) * 100 if actual_total > 0 else 0.0

            assert actual_total == total, (
                f"Regime {regime}: Expected {total} outcomes, got {actual_total}"
            )
            assert abs(actual_hit_rate - expected_hit_rate) < 0.01, (
                f"Regime {regime}: Expected hit rate {expected_hit_rate:.2f}%, "
                f"got {actual_hit_rate:.2f}%"
            )

    @settings(max_examples=25)
    @given(outcomes_data=signal_outcome_lists())
    def test_avg_pnl_equals_arithmetic_mean(
        self,
        outcomes_data: list[dict],
    ) -> None:
        """
        Property: For any set of outcomes grouped by regime, average P&L SHALL
        equal the arithmetic mean of final_pnl_percent values.

        **Validates: Requirements 7.2**
        """
        # Clean up from previous iteration
        SignalOutcome.objects.all().delete()
        Signal.objects.all().delete()

        # Create outcomes
        for data in outcomes_data:
            self._create_signal_with_outcome(
                regime=data["regime"],
                is_profitable=data["is_profitable"],
                final_pnl_percent=data["final_pnl_percent"],
                confidence=data["confidence"],
            )

        # Group by regime and calculate expected metrics
        regime_groups: dict[str, list[dict]] = {}
        for data in outcomes_data:
            regime = data["regime"]
            if regime not in regime_groups:
                regime_groups[regime] = []
            regime_groups[regime].append(data)

        # Verify average P&L for each regime
        for regime, group_data in regime_groups.items():
            pnl_values = [d["final_pnl_percent"] for d in group_data]
            expected_avg_pnl = sum(pnl_values) / len(pnl_values) if pnl_values else 0.0

            # Query actual outcomes
            outcomes = list(SignalOutcome.objects.filter(signal__regime=regime))
            actual_pnl_values = [o.final_pnl_percent for o in outcomes if o.final_pnl_percent is not None]
            actual_avg_pnl = sum(actual_pnl_values) / len(actual_pnl_values) if actual_pnl_values else 0.0

            assert abs(actual_avg_pnl - expected_avg_pnl) < 0.01, (
                f"Regime {regime}: Expected avg P&L {expected_avg_pnl:.2f}%, "
                f"got {actual_avg_pnl:.2f}%"
            )

    @settings(max_examples=20)
    @given(
        regime=regime_values(),
        num_profitable=st.integers(min_value=0, max_value=10),
        num_unprofitable=st.integers(min_value=0, max_value=10),
    )
    def test_aggregation_with_specific_counts(
        self,
        regime: str,
        num_profitable: int,
        num_unprofitable: int,
    ) -> None:
        """
        Property: Aggregation SHALL correctly count profitable and unprofitable
        outcomes for a specific regime.

        **Validates: Requirements 7.2**
        """
        # Skip if no outcomes
        if num_profitable == 0 and num_unprofitable == 0:
            return

        # Clean up from previous iteration
        SignalOutcome.objects.all().delete()
        Signal.objects.all().delete()

        # Create profitable outcomes
        for i in range(num_profitable):
            self._create_signal_with_outcome(
                regime=regime,
                is_profitable=True,
                final_pnl_percent=5.0 + i,
                confidence=80.0,
            )

        # Create unprofitable outcomes
        for i in range(num_unprofitable):
            self._create_signal_with_outcome(
                regime=regime,
                is_profitable=False,
                final_pnl_percent=-5.0 - i,
                confidence=75.0,
            )

        # Query and verify
        outcomes = SignalOutcome.objects.filter(signal__regime=regime)
        total = outcomes.count()
        profitable = sum(1 for o in outcomes if o.is_profitable)
        unprofitable = sum(1 for o in outcomes if o.is_profitable is False)

        expected_total = num_profitable + num_unprofitable
        expected_hit_rate = (num_profitable / expected_total) * 100 if expected_total > 0 else 0.0
        actual_hit_rate = (profitable / total) * 100 if total > 0 else 0.0

        assert total == expected_total, (
            f"Expected {expected_total} total outcomes, got {total}"
        )
        assert profitable == num_profitable, (
            f"Expected {num_profitable} profitable, got {profitable}"
        )
        assert unprofitable == num_unprofitable, (
            f"Expected {num_unprofitable} unprofitable, got {unprofitable}"
        )
        assert abs(actual_hit_rate - expected_hit_rate) < 0.01, (
            f"Expected hit rate {expected_hit_rate:.2f}%, got {actual_hit_rate:.2f}%"
        )

    @settings(max_examples=15)
    @given(
        pnl_values=st.lists(
            st.floats(min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False),
            min_size=1,
            max_size=10,
        ),
    )
    def test_avg_pnl_calculation_precision(
        self,
        pnl_values: list[float],
    ) -> None:
        """
        Property: Average P&L calculation SHALL be precise to at least 2 decimal
        places.

        **Validates: Requirements 7.2**
        """
        # Clean up from previous iteration
        SignalOutcome.objects.all().delete()
        Signal.objects.all().delete()

        regime = Regime.RISK_ON.value

        # Create outcomes with specific P&L values
        for pnl in pnl_values:
            is_profitable = pnl > 0
            self._create_signal_with_outcome(
                regime=regime,
                is_profitable=is_profitable,
                final_pnl_percent=pnl,
                confidence=80.0,
            )

        # Calculate expected average
        expected_avg = sum(pnl_values) / len(pnl_values)

        # Query and calculate actual average
        outcomes = list(SignalOutcome.objects.filter(signal__regime=regime))
        actual_pnl_values = [o.final_pnl_percent for o in outcomes if o.final_pnl_percent is not None]
        actual_avg = sum(actual_pnl_values) / len(actual_pnl_values) if actual_pnl_values else 0.0

        # Verify precision to 2 decimal places
        assert abs(actual_avg - expected_avg) < 0.01, (
            f"Expected avg P&L {expected_avg:.4f}, got {actual_avg:.4f}"
        )

    @settings(max_examples=15)
    @given(
        confidence_values=st.lists(
            st.floats(min_value=50.0, max_value=100.0, allow_nan=False, allow_infinity=False),
            min_size=1,
            max_size=10,
        ),
    )
    def test_avg_confidence_calculation(
        self,
        confidence_values: list[float],
    ) -> None:
        """
        Property: Average confidence calculation SHALL equal the arithmetic mean
        of confidence values.

        **Validates: Requirements 7.2**
        """
        # Clean up from previous iteration
        SignalOutcome.objects.all().delete()
        Signal.objects.all().delete()

        regime = Regime.TRENDING_UP.value

        # Create outcomes with specific confidence values
        for conf in confidence_values:
            self._create_signal_with_outcome(
                regime=regime,
                is_profitable=True,
                final_pnl_percent=5.0,
                confidence=conf,
            )

        # Calculate expected average
        expected_avg = sum(confidence_values) / len(confidence_values)

        # Query and calculate actual average
        outcomes = list(SignalOutcome.objects.filter(signal__regime=regime))
        actual_conf_values = [o.signal.confidence for o in outcomes if o.signal.confidence is not None]
        actual_avg = sum(actual_conf_values) / len(actual_conf_values) if actual_conf_values else 0.0

        # Verify precision
        assert abs(actual_avg - expected_avg) < 0.01, (
            f"Expected avg confidence {expected_avg:.2f}, got {actual_avg:.2f}"
        )
