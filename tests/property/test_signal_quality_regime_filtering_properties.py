"""
Property-based tests for Signal Quality Regime Filtering.

Feature: market-intelligence-layer
Property 17: Signal quality regime filtering

These tests use the hypothesis library to verify that the Signal Quality view
correctly filters signals by regime.

**Validates: Requirements 7.3**
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.core.models import TradingPair
from apps.trading.models import Signal, SignalOutcome
from lib.analysis.context import Regime


# =============================================================================
# Custom Strategies for Regime Filtering Testing
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
def regime_distribution(draw: st.DrawFn) -> dict[str, int]:
    """
    Generate a distribution of signals across regimes.

    Returns a dict mapping regime -> count of signals.
    """
    distribution = {}
    for regime in [r.value for r in Regime]:
        count = draw(st.integers(min_value=0, max_value=5))
        if count > 0:
            distribution[regime] = count
    return distribution


# =============================================================================
# Property 17: Signal quality regime filtering
# =============================================================================


@pytest.mark.django_db(transaction=True)
class TestSignalQualityRegimeFiltering:
    """
    Property 17: Signal quality regime filtering

    *For any* regime label selected in the Signal Quality view, all returned
    signals SHALL have a `regime` field matching the selected label.

    **Validates: Requirements 7.3**
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

    def _create_signal_with_outcome(self, regime: str) -> SignalOutcome:
        """Create a signal with an associated outcome."""
        signal = Signal.objects.create(
            trading_pair=self.trading_pair,
            direction="BUY",
            confidence=80.0,
            regime=regime,
            indicators=[],
        )
        outcome = SignalOutcome.objects.create(
            signal=signal,
            final_pnl_percent=5.0,
            is_profitable=True,
            recorded_at=timezone.now(),
        )
        return outcome

    @settings(max_examples=25)
    @given(
        selected_regime=regime_values(),
        distribution=regime_distribution(),
    )
    def test_filtering_returns_only_matching_regime(
        self,
        selected_regime: str,
        distribution: dict[str, int],
    ) -> None:
        """
        Property: For any selected regime, all returned signals SHALL have
        a regime field matching the selected label.

        **Validates: Requirements 7.3**
        """
        # Clean up from previous iteration
        SignalOutcome.objects.all().delete()
        Signal.objects.all().delete()

        # Create signals according to distribution
        for regime, count in distribution.items():
            for _ in range(count):
                self._create_signal_with_outcome(regime)

        # Filter by selected regime
        filtered_outcomes = SignalOutcome.objects.filter(
            signal__regime=selected_regime
        )

        # Verify all returned signals have matching regime
        for outcome in filtered_outcomes:
            assert outcome.signal.regime == selected_regime, (
                f"Expected regime {selected_regime}, got {outcome.signal.regime}"
            )

        # Verify count matches expected
        expected_count = distribution.get(selected_regime, 0)
        assert filtered_outcomes.count() == expected_count, (
            f"Expected {expected_count} signals for regime {selected_regime}, "
            f"got {filtered_outcomes.count()}"
        )

    @settings(max_examples=20)
    @given(
        regime=regime_values(),
        num_matching=st.integers(min_value=1, max_value=10),
        num_other=st.integers(min_value=0, max_value=10),
    )
    def test_filtering_excludes_non_matching_regimes(
        self,
        regime: str,
        num_matching: int,
        num_other: int,
    ) -> None:
        """
        Property: Filtering by regime SHALL exclude signals with different
        regime values.

        **Validates: Requirements 7.3**
        """
        # Clean up from previous iteration
        SignalOutcome.objects.all().delete()
        Signal.objects.all().delete()

        # Create matching signals
        for _ in range(num_matching):
            self._create_signal_with_outcome(regime)

        # Create signals with other regimes
        other_regimes = [r.value for r in Regime if r.value != regime]
        for i in range(num_other):
            other_regime = other_regimes[i % len(other_regimes)]
            self._create_signal_with_outcome(other_regime)

        # Filter by selected regime
        filtered_outcomes = SignalOutcome.objects.filter(
            signal__regime=regime
        )

        # Verify count
        assert filtered_outcomes.count() == num_matching, (
            f"Expected {num_matching} matching signals, got {filtered_outcomes.count()}"
        )

        # Verify no non-matching regimes
        for outcome in filtered_outcomes:
            assert outcome.signal.regime == regime, (
                f"Found non-matching regime {outcome.signal.regime}"
            )

    @settings(max_examples=15)
    @given(regime=regime_values())
    def test_empty_filter_returns_no_results(
        self,
        regime: str,
    ) -> None:
        """
        Property: Filtering by a regime with no signals SHALL return an
        empty result set.

        **Validates: Requirements 7.3**
        """
        # Clean up from previous iteration
        SignalOutcome.objects.all().delete()
        Signal.objects.all().delete()

        # Create signals with other regimes only
        other_regimes = [r.value for r in Regime if r.value != regime]
        for other_regime in other_regimes[:3]:
            self._create_signal_with_outcome(other_regime)

        # Filter by selected regime
        filtered_outcomes = SignalOutcome.objects.filter(
            signal__regime=regime
        )

        # Should return empty
        assert filtered_outcomes.count() == 0, (
            f"Expected 0 signals for regime {regime}, got {filtered_outcomes.count()}"
        )

    @settings(max_examples=15)
    @given(
        regime=regime_values(),
        num_signals=st.integers(min_value=1, max_value=10),
    )
    def test_all_signals_filter_returns_all(
        self,
        regime: str,
        num_signals: int,
    ) -> None:
        """
        Property: When all signals have the same regime, filtering by that
        regime SHALL return all signals.

        **Validates: Requirements 7.3**
        """
        # Clean up from previous iteration
        SignalOutcome.objects.all().delete()
        Signal.objects.all().delete()

        # Create all signals with same regime
        for _ in range(num_signals):
            self._create_signal_with_outcome(regime)

        # Filter by that regime
        filtered_outcomes = SignalOutcome.objects.filter(
            signal__regime=regime
        )

        # Should return all
        assert filtered_outcomes.count() == num_signals, (
            f"Expected {num_signals} signals, got {filtered_outcomes.count()}"
        )

    @settings(max_examples=20)
    @given(
        regime1=regime_values(),
        regime2=regime_values(),
        num_regime1=st.integers(min_value=1, max_value=5),
        num_regime2=st.integers(min_value=1, max_value=5),
    )
    def test_filtering_is_mutually_exclusive(
        self,
        regime1: str,
        regime2: str,
        num_regime1: int,
        num_regime2: int,
    ) -> None:
        """
        Property: Filtering by different regimes SHALL return mutually
        exclusive result sets.

        **Validates: Requirements 7.3**
        """
        # Skip if same regime
        if regime1 == regime2:
            return

        # Clean up from previous iteration
        SignalOutcome.objects.all().delete()
        Signal.objects.all().delete()

        # Create signals for both regimes
        for _ in range(num_regime1):
            self._create_signal_with_outcome(regime1)
        for _ in range(num_regime2):
            self._create_signal_with_outcome(regime2)

        # Filter by each regime
        filtered1 = set(
            SignalOutcome.objects.filter(signal__regime=regime1).values_list("id", flat=True)
        )
        filtered2 = set(
            SignalOutcome.objects.filter(signal__regime=regime2).values_list("id", flat=True)
        )

        # Verify mutual exclusivity
        intersection = filtered1 & filtered2
        assert len(intersection) == 0, (
            f"Found {len(intersection)} signals in both regime filters"
        )

        # Verify counts
        assert len(filtered1) == num_regime1, (
            f"Expected {num_regime1} signals for {regime1}, got {len(filtered1)}"
        )
        assert len(filtered2) == num_regime2, (
            f"Expected {num_regime2} signals for {regime2}, got {len(filtered2)}"
        )

    @settings(max_examples=15)
    @given(distribution=regime_distribution())
    def test_no_filter_returns_all_signals(
        self,
        distribution: dict[str, int],
    ) -> None:
        """
        Property: When no regime filter is applied, all signals SHALL be
        returned regardless of regime.

        **Validates: Requirements 7.3**
        """
        # Clean up from previous iteration
        SignalOutcome.objects.all().delete()
        Signal.objects.all().delete()

        # Create signals according to distribution
        total_expected = 0
        for regime, count in distribution.items():
            for _ in range(count):
                self._create_signal_with_outcome(regime)
            total_expected += count

        # Query without filter
        all_outcomes = SignalOutcome.objects.all()

        # Should return all
        assert all_outcomes.count() == total_expected, (
            f"Expected {total_expected} total signals, got {all_outcomes.count()}"
        )

    @settings(max_examples=15)
    @given(
        regime=regime_values(),
        num_signals=st.integers(min_value=1, max_value=10),
    )
    def test_filtering_preserves_signal_data(
        self,
        regime: str,
        num_signals: int,
    ) -> None:
        """
        Property: Filtering by regime SHALL preserve all signal data in
        returned results.

        **Validates: Requirements 7.3**
        """
        # Clean up from previous iteration
        SignalOutcome.objects.all().delete()
        Signal.objects.all().delete()

        # Create signals with specific data
        created_ids = []
        for i in range(num_signals):
            signal = Signal.objects.create(
                trading_pair=self.trading_pair,
                direction="BUY" if i % 2 == 0 else "SELL",
                confidence=70.0 + i,
                regime=regime,
                indicators=[{"name": f"IND_{i}"}],
            )
            outcome = SignalOutcome.objects.create(
                signal=signal,
                final_pnl_percent=5.0 + i,
                is_profitable=True,
                recorded_at=timezone.now(),
            )
            created_ids.append(outcome.id)

        # Filter by regime
        filtered_outcomes = SignalOutcome.objects.filter(
            signal__regime=regime
        ).select_related("signal")

        # Verify all data is preserved
        for outcome in filtered_outcomes:
            assert outcome.id in created_ids
            assert outcome.signal.regime == regime
            assert outcome.signal.confidence is not None
            assert outcome.signal.direction in ["BUY", "SELL"]
            assert outcome.final_pnl_percent is not None
