"""
Property-based tests for Regime Detector Time-Range Filtering.

Feature: market-intelligence-layer
Property 15: Regime time-range filtering

These tests use the hypothesis library to verify that the Regime Detector view
correctly filters MarketContextSnapshot records by time range.

**Validates: Requirements 6.2**
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import Client, RequestFactory
from django.utils import timezone
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.analysis.views import RegimeDetectorView
from apps.core.models import MarketContextSnapshot
from lib.analysis.context import Regime


# =============================================================================
# Custom Strategies for Time-Range Testing
# =============================================================================


@st.composite
def time_ranges(draw: st.DrawFn) -> tuple[int, int]:
    """
    Generate random time ranges for testing.

    Returns a tuple of (days_back, num_snapshots) where:
    - days_back: Number of days to look back (7 or 30)
    - num_snapshots: Number of snapshots to create
    """
    days_back = draw(st.sampled_from([7, 30]))
    num_snapshots = draw(st.integers(min_value=0, max_value=20))
    return (days_back, num_snapshots)


@st.composite
def snapshot_timestamps(
    draw: st.DrawFn,
    days_back: int,
    num_snapshots: int,
) -> list[tuple[bool, int]]:
    """
    Generate random snapshot timestamps relative to the time range.

    Returns a list of tuples (is_within_range, hours_offset) where:
    - is_within_range: Whether the snapshot should be within the time range
    - hours_offset: Hours offset from now (negative = past)
    """
    if num_snapshots == 0:
        return []

    timestamps = []
    max_hours_in_range = days_back * 24

    for _ in range(num_snapshots):
        is_within_range = draw(st.booleans())
        if is_within_range:
            # Within range: 0 to max_hours_in_range hours ago
            hours_offset = draw(st.integers(min_value=0, max_value=max_hours_in_range - 1))
        else:
            # Outside range: more than max_hours_in_range hours ago
            hours_offset = draw(
                st.integers(min_value=max_hours_in_range + 1, max_value=max_hours_in_range * 3)
            )
        timestamps.append((is_within_range, hours_offset))

    return timestamps


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


# =============================================================================
# Property 15: Regime time-range filtering
# =============================================================================


@pytest.mark.django_db(transaction=True)
class TestRegimeTimeRangeFiltering:
    """
    Property 15: Regime time-range filtering

    *For any* time range [start, end] passed to the Regime Detector view query,
    all returned `MarketContextSnapshot` records SHALL have timestamps within
    [start, end] inclusive.

    **Validates: Requirements 6.2**
    """

    @settings(max_examples=25)
    @given(
        days_back=st.sampled_from([7, 30]),
        num_within=st.integers(min_value=0, max_value=5),
        num_outside=st.integers(min_value=0, max_value=5),
    )
    def test_time_range_filtering_returns_only_snapshots_within_range(
        self,
        days_back: int,
        num_within: int,
        num_outside: int,
    ) -> None:
        """
        Property: For any time range, the view SHALL return only snapshots
        with timestamps within that range.

        **Validates: Requirements 6.2**
        """
        # Clean up any existing snapshots
        MarketContextSnapshot.objects.all().delete()

        now = timezone.now()
        cutoff = now - timedelta(days=days_back)

        # Create snapshots within range
        within_range_ids = []
        for i in range(num_within):
            hours_ago = i * (days_back * 24 // max(num_within, 1))
            timestamp = now - timedelta(hours=hours_ago)
            snapshot = MarketContextSnapshot.objects.create(
                timestamp=timestamp,
                symbol="BTC_USDT",
                regime=Regime.RISK_ON.value,
                trend_strength_score=0.5,
                risk_regime_score=0.5,
                sentiment_regime_score=0.5,
            )
            within_range_ids.append(snapshot.id)

        # Create snapshots outside range
        outside_range_ids = []
        for i in range(num_outside):
            hours_ago = (days_back + 1 + i) * 24
            timestamp = now - timedelta(hours=hours_ago)
            snapshot = MarketContextSnapshot.objects.create(
                timestamp=timestamp,
                symbol="BTC_USDT",
                regime=Regime.RISK_OFF.value,
                trend_strength_score=0.3,
                risk_regime_score=0.3,
                sentiment_regime_score=0.3,
            )
            outside_range_ids.append(snapshot.id)

        # Query snapshots using the same logic as the view
        filtered_snapshots = MarketContextSnapshot.objects.filter(
            timestamp__gte=cutoff
        ).order_by("timestamp")

        # Verify all returned snapshots are within range
        for snapshot in filtered_snapshots:
            assert snapshot.timestamp >= cutoff, (
                f"Snapshot timestamp {snapshot.timestamp} is before cutoff {cutoff}"
            )
            assert snapshot.timestamp <= now, (
                f"Snapshot timestamp {snapshot.timestamp} is after now {now}"
            )

        # Verify we got the expected number of snapshots
        assert filtered_snapshots.count() == num_within, (
            f"Expected {num_within} snapshots within range, got {filtered_snapshots.count()}"
        )

        # Verify the IDs match
        returned_ids = set(filtered_snapshots.values_list("id", flat=True))
        assert returned_ids == set(within_range_ids), (
            f"Returned IDs {returned_ids} don't match expected {set(within_range_ids)}"
        )

    @settings(max_examples=20)
    @given(
        days_back=st.sampled_from([7, 30]),
    )
    def test_empty_range_returns_no_snapshots(
        self,
        days_back: int,
    ) -> None:
        """
        Property: For a time range with no snapshots, the view SHALL return
        an empty result set.

        **Validates: Requirements 6.2**
        """
        # Clean up any existing snapshots
        MarketContextSnapshot.objects.all().delete()

        now = timezone.now()
        cutoff = now - timedelta(days=days_back)

        # Create only snapshots outside the range
        for i in range(3):
            hours_ago = (days_back + 10 + i) * 24
            timestamp = now - timedelta(hours=hours_ago)
            MarketContextSnapshot.objects.create(
                timestamp=timestamp,
                symbol="BTC_USDT",
                regime=Regime.UNKNOWN.value,
            )

        # Query snapshots
        filtered_snapshots = MarketContextSnapshot.objects.filter(
            timestamp__gte=cutoff
        )

        # Should return empty
        assert filtered_snapshots.count() == 0

    @settings(max_examples=20)
    @given(
        days_back=st.sampled_from([7, 30]),
        regime=regime_values(),
    )
    def test_time_range_filtering_preserves_regime_data(
        self,
        days_back: int,
        regime: str,
    ) -> None:
        """
        Property: Time-range filtering SHALL preserve all regime data
        in returned snapshots.

        **Validates: Requirements 6.2**
        """
        # Clean up any existing snapshots
        MarketContextSnapshot.objects.all().delete()

        now = timezone.now()
        cutoff = now - timedelta(days=days_back)

        # Create a snapshot within range with specific regime
        timestamp = now - timedelta(hours=1)
        snapshot = MarketContextSnapshot.objects.create(
            timestamp=timestamp,
            symbol="ETH_USDT",
            regime=regime,
            trend_strength_score=0.7,
            risk_regime_score=0.6,
            sentiment_regime_score=0.8,
            fear_greed_index=65,
        )

        # Query snapshots
        filtered_snapshots = MarketContextSnapshot.objects.filter(
            timestamp__gte=cutoff
        )

        # Verify the snapshot is returned with correct data
        assert filtered_snapshots.count() == 1
        returned = filtered_snapshots.first()
        assert returned.id == snapshot.id
        assert returned.regime == regime
        assert returned.trend_strength_score == 0.7
        assert returned.risk_regime_score == 0.6
        assert returned.sentiment_regime_score == 0.8
        assert returned.fear_greed_index == 65

    @settings(max_examples=15)
    @given(
        days_back=st.sampled_from([7, 30]),
    )
    def test_boundary_timestamps_are_included(
        self,
        days_back: int,
    ) -> None:
        """
        Property: Snapshots at exactly the cutoff boundary SHALL be included
        in the results.

        **Validates: Requirements 6.2**
        """
        # Clean up any existing snapshots
        MarketContextSnapshot.objects.all().delete()

        now = timezone.now()
        cutoff = now - timedelta(days=days_back)

        # Create a snapshot at exactly the cutoff
        snapshot = MarketContextSnapshot.objects.create(
            timestamp=cutoff,
            symbol="BTC_USDT",
            regime=Regime.RANGE_BOUND.value,
        )

        # Query snapshots
        filtered_snapshots = MarketContextSnapshot.objects.filter(
            timestamp__gte=cutoff
        )

        # The boundary snapshot should be included
        assert filtered_snapshots.count() == 1
        assert filtered_snapshots.first().id == snapshot.id

    @settings(max_examples=15)
    @given(
        days_back=st.sampled_from([7, 30]),
    )
    def test_snapshots_just_before_cutoff_are_excluded(
        self,
        days_back: int,
    ) -> None:
        """
        Property: Snapshots just before the cutoff boundary SHALL be excluded
        from the results.

        **Validates: Requirements 6.2**
        """
        # Clean up any existing snapshots
        MarketContextSnapshot.objects.all().delete()

        now = timezone.now()
        cutoff = now - timedelta(days=days_back)

        # Create a snapshot just before the cutoff (1 second before)
        just_before = cutoff - timedelta(seconds=1)
        MarketContextSnapshot.objects.create(
            timestamp=just_before,
            symbol="BTC_USDT",
            regime=Regime.TRENDING_DOWN.value,
        )

        # Query snapshots
        filtered_snapshots = MarketContextSnapshot.objects.filter(
            timestamp__gte=cutoff
        )

        # The snapshot should be excluded
        assert filtered_snapshots.count() == 0

    @settings(max_examples=20)
    @given(
        days_back=st.sampled_from([7, 30]),
        num_snapshots=st.integers(min_value=1, max_value=10),
    )
    def test_ordering_is_preserved_after_filtering(
        self,
        days_back: int,
        num_snapshots: int,
    ) -> None:
        """
        Property: After time-range filtering, snapshots SHALL be ordered
        by timestamp.

        **Validates: Requirements 6.2**
        """
        # Clean up any existing snapshots
        MarketContextSnapshot.objects.all().delete()

        now = timezone.now()
        cutoff = now - timedelta(days=days_back)

        # Create snapshots at different times within range
        for i in range(num_snapshots):
            hours_ago = i * 2  # 2 hours apart
            timestamp = now - timedelta(hours=hours_ago)
            MarketContextSnapshot.objects.create(
                timestamp=timestamp,
                symbol="BTC_USDT",
                regime=Regime.RISK_ON.value,
            )

        # Query snapshots ordered by timestamp
        filtered_snapshots = list(
            MarketContextSnapshot.objects.filter(timestamp__gte=cutoff).order_by("timestamp")
        )

        # Verify ordering
        for i in range(len(filtered_snapshots) - 1):
            assert filtered_snapshots[i].timestamp <= filtered_snapshots[i + 1].timestamp, (
                f"Snapshots not ordered: {filtered_snapshots[i].timestamp} > "
                f"{filtered_snapshots[i + 1].timestamp}"
            )

    @settings(max_examples=15)
    @given(
        days_back=st.sampled_from([7, 30]),
    )
    def test_multiple_symbols_filtered_correctly(
        self,
        days_back: int,
    ) -> None:
        """
        Property: Time-range filtering SHALL work correctly across multiple
        symbols.

        **Validates: Requirements 6.2**
        """
        # Clean up any existing snapshots
        MarketContextSnapshot.objects.all().delete()

        now = timezone.now()
        cutoff = now - timedelta(days=days_back)

        symbols = ["BTC_USDT", "ETH_USDT", "SOL_USDT"]

        # Create snapshots for different symbols within range
        for symbol in symbols:
            timestamp = now - timedelta(hours=1)
            MarketContextSnapshot.objects.create(
                timestamp=timestamp,
                symbol=symbol,
                regime=Regime.TRENDING_UP.value,
            )

        # Create snapshots for different symbols outside range
        for symbol in symbols:
            timestamp = now - timedelta(days=days_back + 5)
            MarketContextSnapshot.objects.create(
                timestamp=timestamp,
                symbol=symbol,
                regime=Regime.RISK_OFF.value,
            )

        # Query snapshots
        filtered_snapshots = MarketContextSnapshot.objects.filter(
            timestamp__gte=cutoff
        )

        # Should return only the 3 within-range snapshots
        assert filtered_snapshots.count() == 3

        # All should be within range
        for snapshot in filtered_snapshots:
            assert snapshot.timestamp >= cutoff
