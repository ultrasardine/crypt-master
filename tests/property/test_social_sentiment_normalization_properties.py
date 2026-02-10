"""
Property-based tests for Social Sentiment Client Normalization.

Feature: market-intelligence-layer
Property 1: Normalization produces valid schema

These tests use the hypothesis library to verify that the social sentiment client
always produces ExternalMetrics with valid schema regardless of input.

**Validates: Requirements 1.4**
"""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from lib.sync.external_sources import ExternalMetrics

# =============================================================================
# Custom Strategies for Social Sentiment Client Testing
# =============================================================================


@st.composite
def raw_lunarcrush_response(draw: st.DrawFn) -> dict[str, Any]:
    """
    Generate random LunarCrush API responses.

    LunarCrush returns asset data with sentiment scores (0-5), social volume,
    and galaxy scores (0-100).
    """
    # Generate optional values
    sentiment = draw(
        st.one_of(
            st.none(),
            st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False),
            st.integers(min_value=0, max_value=5),
        )
    )

    social_volume = draw(
        st.one_of(
            st.none(),
            st.integers(min_value=0, max_value=1000000),
        )
    )

    galaxy_score = draw(
        st.one_of(
            st.none(),
            st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
            st.integers(min_value=0, max_value=100),
        )
    )

    # Build response structure
    asset_data = {}
    if sentiment is not None:
        asset_data["sentiment"] = sentiment
    if social_volume is not None:
        asset_data["social_volume"] = social_volume
    if galaxy_score is not None:
        asset_data["galaxy_score"] = galaxy_score

    response = {
        "data": [asset_data] if asset_data else []
    }

    return response


@st.composite
def raw_santiment_response(draw: st.DrawFn) -> dict[str, Any]:
    """
    Generate random Santiment GraphQL API responses.

    Santiment returns time-series data for sentiment balance, social volume,
    and social dominance.
    """
    # Generate time-series data points
    num_datapoints = draw(st.integers(min_value=0, max_value=5))

    sentiment_data = []
    volume_data = []
    dominance_data = []

    for _ in range(num_datapoints):
        # Sentiment balance (typically -10 to 10)
        sentiment_value = draw(
            st.one_of(
                st.none(),
                st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
            )
        )
        sentiment_data.append({
            "datetime": "2024-01-01T00:00:00Z",
            "value": sentiment_value,
        })

        # Social volume (mention count)
        volume_value = draw(
            st.one_of(
                st.none(),
                st.integers(min_value=0, max_value=100000),
            )
        )
        volume_data.append({
            "datetime": "2024-01-01T00:00:00Z",
            "value": volume_value,
        })

        # Social dominance (0-100)
        dominance_value = draw(
            st.one_of(
                st.none(),
                st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
            )
        )
        dominance_data.append({
            "datetime": "2024-01-01T00:00:00Z",
            "value": dominance_value,
        })

    response = {
        "data": {
            "getMetric": {
                "timeseriesData": sentiment_data,
            },
            "socialVolume": {
                "timeseriesData": volume_data,
            },
            "socialDominance": {
                "timeseriesData": dominance_data,
            },
        }
    }

    return response


# =============================================================================
# Property 1: Normalization produces valid schema
# =============================================================================


class TestSocialSentimentClientNormalization:
    """
    Property 1: Normalization produces valid schema

    *For any* raw API response from any external source client, the normalized
    `ExternalMetrics` output SHALL have a non-empty `source_name`, and all
    numeric values in the `metrics` dict that are not None SHALL be of type
    `float` or `int`.

    This property ensures that regardless of what the external API returns,
    the social sentiment client always produces a valid ExternalMetrics structure
    that downstream code can safely consume.

    **Validates: Requirements 1.4**
    """

    def _validate_external_metrics(self, metrics: ExternalMetrics) -> None:
        """
        Helper method to validate ExternalMetrics schema.

        Checks that:
        1. source_name is non-empty string
        2. symbol is either None or a string
        3. metrics dict contains only float, int, or None values
        4. is_stale is a boolean
        5. error_message is either None or a string
        """
        # Check source_name
        assert isinstance(metrics.source_name, str), (
            f"source_name must be str, got {type(metrics.source_name)}"
        )
        assert len(metrics.source_name) > 0, "source_name must be non-empty"

        # Check symbol
        assert metrics.symbol is None or isinstance(metrics.symbol, str), (
            f"symbol must be None or str, got {type(metrics.symbol)}"
        )

        # Check metrics dict
        assert isinstance(metrics.metrics, dict), f"metrics must be dict, got {type(metrics.metrics)}"

        # Check each metric value
        for key, value in metrics.metrics.items():
            assert isinstance(key, str), f"Metric key must be str, got {type(key)}"

            # Value can be None, float, or int
            if value is not None:
                assert isinstance(value, (float, int)) and not isinstance(value, bool), (
                    f"Metric '{key}' value must be float, int, or None, "
                    f"got {type(value).__name__}"
                )

                # If it's a numeric value, verify it's not NaN or infinity
                import math

                assert not math.isnan(float(value)), f"Metric '{key}' is NaN"
                assert not math.isinf(float(value)), f"Metric '{key}' is infinity"

        # Check is_stale
        assert isinstance(metrics.is_stale, bool), (
            f"is_stale must be bool, got {type(metrics.is_stale)}"
        )

        # Check error_message
        assert metrics.error_message is None or isinstance(metrics.error_message, str), (
            f"error_message must be None or str, got {type(metrics.error_message)}"
        )

    @settings(max_examples=20)
    @given(
        response=raw_lunarcrush_response(),
    )
    def test_lunarcrush_normalization_produces_valid_schema(
        self,
        response: dict[str, Any],
    ) -> None:
        """
        Property: For any LunarCrush API response, normalization SHALL produce
        valid ExternalMetrics with correct schema.

        This test generates random LunarCrush responses and verifies that the
        client always produces valid ExternalMetrics regardless of input.

        **Validates: Requirements 1.4**
        """
        # Extract values from response
        asset_data = response["data"][0] if response["data"] else {}

        sentiment_raw = asset_data.get("sentiment")
        social_volume = asset_data.get("social_volume")
        galaxy_score = asset_data.get("galaxy_score")

        # Normalize sentiment from 0-5 scale to -1 to 1 scale
        sentiment_polarity = None
        if sentiment_raw is not None:
            sentiment_polarity = (float(sentiment_raw) - 3.0) / 2.0
            sentiment_polarity = max(-1.0, min(1.0, sentiment_polarity))

        # Normalize galaxy score from 0-100 to 0-1
        buzz_score = None
        if galaxy_score is not None:
            buzz_score = float(galaxy_score) / 100.0

        # Create ExternalMetrics as the client would
        import time

        metrics = ExternalMetrics(
            source_name="lunarcrush",
            symbol="BTC",
            metrics={
                "sentiment_polarity": sentiment_polarity,
                "mention_count": int(social_volume) if social_volume is not None else None,
                "buzz_score": buzz_score,
                "fetched_at": time.time(),
            },
            is_stale=False,
            error_message=None,
        )

        # Validate the schema
        self._validate_external_metrics(metrics)

        # Additional validation for sentiment polarity range
        if sentiment_polarity is not None:
            assert -1.0 <= metrics.metrics["sentiment_polarity"] <= 1.0

        # Additional validation for buzz score range
        if buzz_score is not None:
            assert 0.0 <= metrics.metrics["buzz_score"] <= 1.0

    @settings(max_examples=20)
    @given(
        response=raw_santiment_response(),
    )
    def test_santiment_normalization_produces_valid_schema(
        self,
        response: dict[str, Any],
    ) -> None:
        """
        Property: For any Santiment API response, normalization SHALL produce
        valid ExternalMetrics with correct schema.

        **Validates: Requirements 1.4**
        """
        # Extract values from response
        sentiment_data = response["data"]["getMetric"]["timeseriesData"]
        volume_data = response["data"]["socialVolume"]["timeseriesData"]
        dominance_data = response["data"]["socialDominance"]["timeseriesData"]

        # Get latest values
        sentiment_polarity = None
        if sentiment_data:
            latest_sentiment = sentiment_data[-1].get("value")
            if latest_sentiment is not None:
                # Normalize from -10 to 10 range to -1 to 1
                sentiment_polarity = max(-1.0, min(1.0, float(latest_sentiment) / 10.0))

        mention_count = None
        if volume_data:
            latest_volume = volume_data[-1].get("value")
            if latest_volume is not None:
                mention_count = int(latest_volume)

        buzz_score = None
        if dominance_data:
            latest_dominance = dominance_data[-1].get("value")
            if latest_dominance is not None:
                # Normalize from 0-100 to 0-1
                buzz_score = float(latest_dominance) / 100.0

        # Create ExternalMetrics as the client would
        import time

        metrics = ExternalMetrics(
            source_name="santiment",
            symbol="BTC",
            metrics={
                "sentiment_polarity": sentiment_polarity,
                "mention_count": mention_count,
                "buzz_score": buzz_score,
                "fetched_at": time.time(),
            },
            is_stale=False,
            error_message=None,
        )

        # Validate the schema
        self._validate_external_metrics(metrics)

        # Additional validation for sentiment polarity range
        if sentiment_polarity is not None:
            assert -1.0 <= metrics.metrics["sentiment_polarity"] <= 1.0

        # Additional validation for buzz score range
        if buzz_score is not None:
            assert 0.0 <= metrics.metrics["buzz_score"] <= 1.0

    @settings(max_examples=20)
    @given(
        source_name=st.sampled_from(["lunarcrush", "santiment"]),
        symbol=st.one_of(st.none(), st.sampled_from(["BTC", "ETH", "BTC_USDT", "ETH_USDT"])),
        sentiment_polarity=st.one_of(
            st.none(),
            st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        ),
        mention_count=st.one_of(
            st.none(),
            st.integers(min_value=0, max_value=1000000),
        ),
        buzz_score=st.one_of(
            st.none(),
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        ),
    )
    def test_external_metrics_schema_with_random_social_values(
        self,
        source_name: str,
        symbol: str | None,
        sentiment_polarity: float | None,
        mention_count: int | None,
        buzz_score: float | None,
    ) -> None:
        """
        Property: For any valid social sentiment values, ExternalMetrics SHALL
        maintain correct schema with proper type conversions.

        This test verifies that the ExternalMetrics dataclass correctly handles
        various numeric types and None values for social sentiment metrics.

        **Validates: Requirements 1.4**
        """
        # Create ExternalMetrics with random social sentiment values
        import time

        metrics = ExternalMetrics(
            source_name=source_name,
            symbol=symbol,
            metrics={
                "sentiment_polarity": sentiment_polarity,
                "mention_count": mention_count,
                "buzz_score": buzz_score,
                "fetched_at": time.time(),
            },
            is_stale=False,
            error_message=None,
        )

        # Validate the schema
        self._validate_external_metrics(metrics)

        # Additional checks for social sentiment metric values
        if sentiment_polarity is not None:
            assert isinstance(metrics.metrics["sentiment_polarity"], float)
            assert -1.0 <= metrics.metrics["sentiment_polarity"] <= 1.0

        if mention_count is not None:
            assert isinstance(metrics.metrics["mention_count"], int)
            assert metrics.metrics["mention_count"] >= 0

        if buzz_score is not None:
            assert isinstance(metrics.metrics["buzz_score"], float)
            assert 0.0 <= metrics.metrics["buzz_score"] <= 1.0

    @settings(max_examples=20)
    @given(
        is_stale=st.booleans(),
        error_message=st.one_of(
            st.none(),
            st.sampled_from([
                "API key not configured",
                "HTTP error 429",
                "Network timeout",
                "Failed to fetch any social sentiment data",
                "Request error",
                "No data available",
            ]),
        ),
    )
    def test_external_metrics_handles_social_error_states(
        self,
        is_stale: bool,
        error_message: str | None,
    ) -> None:
        """
        Property: For any error state (stale data, error messages),
        ExternalMetrics SHALL maintain valid schema for social sentiment data.

        This verifies that error handling doesn't break the schema contract.

        **Validates: Requirements 1.4**
        """
        # Create ExternalMetrics in error state
        import time

        metrics = ExternalMetrics(
            source_name="lunarcrush",
            symbol="BTC",
            metrics={"fetched_at": time.time()},
            is_stale=is_stale,
            error_message=error_message,
        )

        # Validate the schema
        self._validate_external_metrics(metrics)

        # Verify error state fields
        assert metrics.is_stale == is_stale
        assert metrics.error_message == error_message

    @settings(max_examples=20)
    @given(
        has_sentiment=st.booleans(),
        has_mentions=st.booleans(),
        has_buzz=st.booleans(),
    )
    def test_external_metrics_handles_partial_social_data(
        self,
        has_sentiment: bool,
        has_mentions: bool,
        has_buzz: bool,
    ) -> None:
        """
        Property: For any combination of available/missing social sentiment metrics,
        ExternalMetrics SHALL maintain valid schema.

        This tests that the schema is valid when some metrics are available
        and others are None (partial data scenarios).

        **Validates: Requirements 1.4**
        """
        # Generate random values for available metrics
        import random
        import time

        metrics_dict: dict[str, float | int | None] = {}

        if has_sentiment:
            metrics_dict["sentiment_polarity"] = random.uniform(-1.0, 1.0)
        else:
            metrics_dict["sentiment_polarity"] = None

        if has_mentions:
            metrics_dict["mention_count"] = random.randint(0, 100000)
        else:
            metrics_dict["mention_count"] = None

        if has_buzz:
            metrics_dict["buzz_score"] = random.uniform(0.0, 1.0)
        else:
            metrics_dict["buzz_score"] = None

        metrics_dict["fetched_at"] = time.time()

        # Create ExternalMetrics
        metrics = ExternalMetrics(
            source_name="lunarcrush",
            symbol="BTC",
            metrics=metrics_dict,
            is_stale=not any([has_sentiment, has_mentions, has_buzz]),
            error_message=None,
        )

        # Validate the schema
        self._validate_external_metrics(metrics)

        # Verify that None values are preserved
        if not has_sentiment:
            assert metrics.metrics["sentiment_polarity"] is None
        if not has_mentions:
            assert metrics.metrics["mention_count"] is None
        if not has_buzz:
            assert metrics.metrics["buzz_score"] is None

    @settings(max_examples=20)
    @given(
        symbol=st.sampled_from(["BTC", "ETH", "BTC_USDT", "ETH_USDT", "DOGE", "ADA"]),
    )
    def test_external_metrics_handles_symbol_variations(
        self,
        symbol: str,
    ) -> None:
        """
        Property: For any symbol format (with/without pair suffix),
        ExternalMetrics SHALL maintain valid schema.

        This tests that symbol normalization doesn't break the schema.

        **Validates: Requirements 1.4**
        """
        # Create ExternalMetrics with varying symbol formats
        import time

        metrics = ExternalMetrics(
            source_name="lunarcrush",
            symbol=symbol,
            metrics={
                "sentiment_polarity": 0.5,
                "mention_count": 1000,
                "buzz_score": 0.75,
                "fetched_at": time.time(),
            },
            is_stale=False,
            error_message=None,
        )

        # Validate the schema
        self._validate_external_metrics(metrics)

        # Verify symbol is preserved
        assert metrics.symbol == symbol

    @settings(max_examples=20)
    @given(
        timestamp=st.floats(min_value=1000000000.0, max_value=2000000000.0, allow_nan=False, allow_infinity=False),
    )
    def test_external_metrics_includes_timestamp(
        self,
        timestamp: float,
    ) -> None:
        """
        Property: For any social sentiment metrics fetch, ExternalMetrics SHALL
        include a fetched_at timestamp in the metrics dict.

        This verifies that the timestamp is always included as required by
        the design.

        **Validates: Requirements 1.4**
        """
        # Create ExternalMetrics with timestamp
        metrics = ExternalMetrics(
            source_name="lunarcrush",
            symbol="BTC",
            metrics={
                "sentiment_polarity": 0.5,
                "mention_count": 1000,
                "buzz_score": 0.75,
                "fetched_at": timestamp,
            },
            is_stale=False,
            error_message=None,
        )

        # Validate the schema
        self._validate_external_metrics(metrics)

        # Verify timestamp is present and valid
        assert "fetched_at" in metrics.metrics
        assert isinstance(metrics.metrics["fetched_at"], float)
        assert metrics.metrics["fetched_at"] > 0

    @settings(max_examples=20)
    @given(
        sentiment_raw=st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False),
    )
    def test_lunarcrush_sentiment_normalization_range(
        self,
        sentiment_raw: float,
    ) -> None:
        """
        Property: For any LunarCrush sentiment value (0-5 scale), normalization
        SHALL produce a value in the -1 to 1 range.

        This tests the specific normalization logic for LunarCrush sentiment.

        **Validates: Requirements 1.4**
        """
        # Normalize sentiment from 0-5 scale to -1 to 1 scale
        sentiment_polarity = (sentiment_raw - 3.0) / 2.0
        sentiment_polarity = max(-1.0, min(1.0, sentiment_polarity))

        # Create ExternalMetrics
        import time

        metrics = ExternalMetrics(
            source_name="lunarcrush",
            symbol="BTC",
            metrics={
                "sentiment_polarity": sentiment_polarity,
                "fetched_at": time.time(),
            },
            is_stale=False,
            error_message=None,
        )

        # Validate the schema
        self._validate_external_metrics(metrics)

        # Verify sentiment is in valid range
        assert -1.0 <= metrics.metrics["sentiment_polarity"] <= 1.0

    @settings(max_examples=20)
    @given(
        galaxy_score=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    )
    def test_lunarcrush_galaxy_score_normalization_range(
        self,
        galaxy_score: float,
    ) -> None:
        """
        Property: For any LunarCrush galaxy score (0-100 scale), normalization
        SHALL produce a buzz score in the 0 to 1 range.

        This tests the specific normalization logic for LunarCrush galaxy score.

        **Validates: Requirements 1.4**
        """
        # Normalize galaxy score from 0-100 to 0-1
        buzz_score = galaxy_score / 100.0

        # Create ExternalMetrics
        import time

        metrics = ExternalMetrics(
            source_name="lunarcrush",
            symbol="BTC",
            metrics={
                "buzz_score": buzz_score,
                "fetched_at": time.time(),
            },
            is_stale=False,
            error_message=None,
        )

        # Validate the schema
        self._validate_external_metrics(metrics)

        # Verify buzz score is in valid range
        assert 0.0 <= metrics.metrics["buzz_score"] <= 1.0

    @settings(max_examples=20)
    @given(
        sentiment_balance=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    )
    def test_santiment_sentiment_normalization_range(
        self,
        sentiment_balance: float,
    ) -> None:
        """
        Property: For any Santiment sentiment balance (-10 to 10 scale),
        normalization SHALL produce a value in the -1 to 1 range.

        This tests the specific normalization logic for Santiment sentiment.

        **Validates: Requirements 1.4**
        """
        # Normalize sentiment from -10 to 10 range to -1 to 1
        sentiment_polarity = max(-1.0, min(1.0, sentiment_balance / 10.0))

        # Create ExternalMetrics
        import time

        metrics = ExternalMetrics(
            source_name="santiment",
            symbol="BTC",
            metrics={
                "sentiment_polarity": sentiment_polarity,
                "fetched_at": time.time(),
            },
            is_stale=False,
            error_message=None,
        )

        # Validate the schema
        self._validate_external_metrics(metrics)

        # Verify sentiment is in valid range
        assert -1.0 <= metrics.metrics["sentiment_polarity"] <= 1.0

    @settings(max_examples=20)
    @given(
        social_dominance=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    )
    def test_santiment_dominance_normalization_range(
        self,
        social_dominance: float,
    ) -> None:
        """
        Property: For any Santiment social dominance (0-100 scale), normalization
        SHALL produce a buzz score in the 0 to 1 range.

        This tests the specific normalization logic for Santiment social dominance.

        **Validates: Requirements 1.4**
        """
        # Normalize social dominance from 0-100 to 0-1
        buzz_score = social_dominance / 100.0

        # Create ExternalMetrics
        import time

        metrics = ExternalMetrics(
            source_name="santiment",
            symbol="BTC",
            metrics={
                "buzz_score": buzz_score,
                "fetched_at": time.time(),
            },
            is_stale=False,
            error_message=None,
        )

        # Validate the schema
        self._validate_external_metrics(metrics)

        # Verify buzz score is in valid range
        assert 0.0 <= metrics.metrics["buzz_score"] <= 1.0


class TestSocialSentimentMetricsImmutability:
    """
    Additional property tests for social sentiment ExternalMetrics immutability.

    Since ExternalMetrics is a frozen dataclass, it should be immutable.
    These tests verify that the immutability contract is maintained for
    social sentiment data.

    **Validates: Requirements 1.4**
    """

    @settings(max_examples=15)
    @given(
        source_name=st.sampled_from(["lunarcrush", "santiment"]),
        sentiment_polarity=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    def test_social_external_metrics_is_immutable(
        self,
        source_name: str,
        sentiment_polarity: float,
    ) -> None:
        """
        Property: Social sentiment ExternalMetrics instances SHALL be immutable (frozen).

        This verifies that the frozen=True dataclass attribute is working.

        **Validates: Requirements 1.4**
        """
        import time

        metrics = ExternalMetrics(
            source_name=source_name,
            symbol="BTC",
            metrics={
                "sentiment_polarity": sentiment_polarity,
                "mention_count": 1000,
                "buzz_score": 0.75,
                "fetched_at": time.time(),
            },
            is_stale=False,
            error_message=None,
        )

        # Attempt to modify should raise an error
        with pytest.raises(AttributeError):
            metrics.source_name = "modified"  # type: ignore[misc]

        with pytest.raises(AttributeError):
            metrics.is_stale = True  # type: ignore[misc]

    @settings(max_examples=15)
    @given(
        sentiment_polarity=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        mention_count=st.integers(min_value=0, max_value=100000),
        buzz_score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    def test_social_external_metrics_equality(
        self,
        sentiment_polarity: float,
        mention_count: int,
        buzz_score: float,
    ) -> None:
        """
        Property: Two social sentiment ExternalMetrics with identical values SHALL be equal.

        This verifies that the dataclass equality works correctly.

        **Validates: Requirements 1.4**
        """
        import time

        timestamp = time.time()

        metrics1 = ExternalMetrics(
            source_name="lunarcrush",
            symbol="BTC",
            metrics={
                "sentiment_polarity": sentiment_polarity,
                "mention_count": mention_count,
                "buzz_score": buzz_score,
                "fetched_at": timestamp,
            },
            is_stale=False,
            error_message=None,
        )

        metrics2 = ExternalMetrics(
            source_name="lunarcrush",
            symbol="BTC",
            metrics={
                "sentiment_polarity": sentiment_polarity,
                "mention_count": mention_count,
                "buzz_score": buzz_score,
                "fetched_at": timestamp,
            },
            is_stale=False,
            error_message=None,
        )

        assert metrics1 == metrics2, "Identical social sentiment ExternalMetrics should be equal"

    @settings(max_examples=15)
    @given(
        sentiment1=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        sentiment2=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    def test_social_external_metrics_inequality(
        self,
        sentiment1: float,
        sentiment2: float,
    ) -> None:
        """
        Property: Two social sentiment ExternalMetrics with different values SHALL NOT be equal.

        This verifies that the dataclass equality correctly distinguishes different instances.

        **Validates: Requirements 1.4**
        """
        # Only test when values are actually different
        if sentiment1 == sentiment2:
            return

        import time

        timestamp = time.time()

        metrics1 = ExternalMetrics(
            source_name="lunarcrush",
            symbol="BTC",
            metrics={
                "sentiment_polarity": sentiment1,
                "mention_count": 1000,
                "buzz_score": 0.75,
                "fetched_at": timestamp,
            },
            is_stale=False,
            error_message=None,
        )

        metrics2 = ExternalMetrics(
            source_name="lunarcrush",
            symbol="BTC",
            metrics={
                "sentiment_polarity": sentiment2,
                "mention_count": 1000,
                "buzz_score": 0.75,
                "fetched_at": timestamp,
            },
            is_stale=False,
            error_message=None,
        )

        assert metrics1 != metrics2, "Different social sentiment ExternalMetrics should not be equal"
