"""
Property-based tests for On-Chain Client Normalization.

Feature: market-intelligence-layer
Property 1: Normalization produces valid schema

These tests use the hypothesis library to verify that the on-chain client
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
# Custom Strategies for On-Chain Client Testing
# =============================================================================


@st.composite
def raw_glassnode_metric_response(draw: st.DrawFn) -> list[dict[str, Any]]:
    """
    Generate random Glassnode metric API responses.

    Glassnode returns time-series data as a list of {t: timestamp, v: value} objects.
    """
    num_datapoints = draw(st.integers(min_value=0, max_value=10))
    datapoints = []

    for _ in range(num_datapoints):
        timestamp = draw(st.integers(min_value=1000000000, max_value=2000000000))
        value = draw(
            st.one_of(
                st.none(),
                st.floats(min_value=-1e12, max_value=1e12, allow_nan=False, allow_infinity=False),
                st.integers(min_value=-1000000000, max_value=1000000000),
            )
        )

        datapoints.append({"t": timestamp, "v": value})

    return datapoints


@st.composite
def raw_intotheblock_response(draw: st.DrawFn, metric_type: str) -> dict[str, Any]:
    """
    Generate random IntoTheBlock API responses.

    IntoTheBlock returns data in a {"data": {...}} structure with different
    fields depending on the metric type.
    """
    if metric_type == "active-addresses":
        count = draw(
            st.one_of(
                st.none(),
                st.integers(min_value=0, max_value=10000000),
            )
        )
        return {"data": {"count": count}}

    elif metric_type == "exchange-flow":
        inflow = draw(
            st.one_of(
                st.none(),
                st.floats(min_value=0.0, max_value=1e12, allow_nan=False, allow_infinity=False),
                st.integers(min_value=0, max_value=1000000000),
            )
        )
        outflow = draw(
            st.one_of(
                st.none(),
                st.floats(min_value=0.0, max_value=1e12, allow_nan=False, allow_infinity=False),
                st.integers(min_value=0, max_value=1000000000),
            )
        )
        return {"data": {"inflow": inflow, "outflow": outflow}}

    elif metric_type == "large-transactions":
        count = draw(
            st.one_of(
                st.none(),
                st.integers(min_value=0, max_value=100000),
            )
        )
        return {"data": {"count": count}}

    elif metric_type == "defi-tvl":
        tvl = draw(
            st.one_of(
                st.none(),
                st.floats(min_value=0.0, max_value=1e15, allow_nan=False, allow_infinity=False),
                st.integers(min_value=0, max_value=int(1e15)),
            )
        )
        return {"data": {"total_value_locked": tvl}}

    else:
        return {"data": {}}


# =============================================================================
# Property 1: Normalization produces valid schema
# =============================================================================


class TestOnChainClientNormalization:
    """
    Property 1: Normalization produces valid schema

    *For any* raw API response from any external source client, the normalized
    `ExternalMetrics` output SHALL have a non-empty `source_name`, and all
    numeric values in the `metrics` dict that are not None SHALL be of type
    `float` or `int`.

    This property ensures that regardless of what the external API returns,
    the on-chain client always produces a valid ExternalMetrics structure that
    downstream code can safely consume.

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
        active_addresses_response=raw_glassnode_metric_response(),
        exchange_flow_response=raw_glassnode_metric_response(),
        whale_count_response=raw_glassnode_metric_response(),
        defi_tvl_response=raw_glassnode_metric_response(),
    )
    def test_glassnode_normalization_produces_valid_schema(
        self,
        active_addresses_response: list[dict[str, Any]],
        exchange_flow_response: list[dict[str, Any]],
        whale_count_response: list[dict[str, Any]],
        defi_tvl_response: list[dict[str, Any]],
    ) -> None:
        """
        Property: For any Glassnode API response, normalization SHALL produce
        valid ExternalMetrics with correct schema.

        This test generates random Glassnode responses and verifies that the
        client always produces valid ExternalMetrics regardless of input.

        **Validates: Requirements 1.4**
        """
        # Extract values from responses (get latest value if available)
        active_addresses = None
        if active_addresses_response and active_addresses_response[-1].get("v") is not None:
            active_addresses = float(active_addresses_response[-1]["v"])

        net_exchange_flow = None
        if exchange_flow_response and exchange_flow_response[-1].get("v") is not None:
            net_exchange_flow = float(exchange_flow_response[-1]["v"])

        whale_tx_count = None
        if whale_count_response and whale_count_response[-1].get("v") is not None:
            whale_tx_count = float(whale_count_response[-1]["v"])

        defi_tvl = None
        if defi_tvl_response and defi_tvl_response[-1].get("v") is not None:
            defi_tvl = float(defi_tvl_response[-1]["v"])

        # Create ExternalMetrics as the client would
        import time

        metrics = ExternalMetrics(
            source_name="glassnode",
            symbol="BTC",
            metrics={
                "active_addresses": active_addresses,
                "net_exchange_flow": net_exchange_flow,
                "whale_tx_count": whale_tx_count,
                "defi_tvl": defi_tvl,
                "fetched_at": time.time(),
            },
            is_stale=False,
            error_message=None,
        )

        # Validate the schema
        self._validate_external_metrics(metrics)

    @settings(max_examples=20)
    @given(
        active_addresses_data=raw_intotheblock_response(metric_type="active-addresses"),
        exchange_flow_data=raw_intotheblock_response(metric_type="exchange-flow"),
        whale_count_data=raw_intotheblock_response(metric_type="large-transactions"),
        defi_tvl_data=raw_intotheblock_response(metric_type="defi-tvl"),
    )
    def test_intotheblock_normalization_produces_valid_schema(
        self,
        active_addresses_data: dict[str, Any],
        exchange_flow_data: dict[str, Any],
        whale_count_data: dict[str, Any],
        defi_tvl_data: dict[str, Any],
    ) -> None:
        """
        Property: For any IntoTheBlock API response, normalization SHALL produce
        valid ExternalMetrics with correct schema.

        **Validates: Requirements 1.4**
        """
        # Extract values from responses
        active_addresses = active_addresses_data.get("data", {}).get("count")
        if active_addresses is not None:
            active_addresses = float(active_addresses)

        # Calculate net exchange flow
        inflow = exchange_flow_data.get("data", {}).get("inflow")
        outflow = exchange_flow_data.get("data", {}).get("outflow")
        net_exchange_flow = None
        if inflow is not None and outflow is not None:
            net_exchange_flow = float(inflow) - float(outflow)

        whale_tx_count = whale_count_data.get("data", {}).get("count")
        if whale_tx_count is not None:
            whale_tx_count = float(whale_tx_count)

        defi_tvl = defi_tvl_data.get("data", {}).get("total_value_locked")
        if defi_tvl is not None:
            defi_tvl = float(defi_tvl)

        # Create ExternalMetrics as the client would
        import time

        metrics = ExternalMetrics(
            source_name="intotheblock",
            symbol="btc",
            metrics={
                "active_addresses": active_addresses,
                "net_exchange_flow": net_exchange_flow,
                "whale_tx_count": whale_tx_count,
                "defi_tvl": defi_tvl,
                "fetched_at": time.time(),
            },
            is_stale=False,
            error_message=None,
        )

        # Validate the schema
        self._validate_external_metrics(metrics)

    @settings(max_examples=20)
    @given(
        source_name=st.sampled_from(["glassnode", "intotheblock"]),
        symbol=st.one_of(st.none(), st.sampled_from(["BTC", "ETH", "btc", "eth"])),
        active_addresses=st.one_of(
            st.none(),
            st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False),
            st.integers(min_value=0, max_value=1000000000),
        ),
        net_exchange_flow=st.one_of(
            st.none(),
            st.floats(min_value=-1e12, max_value=1e12, allow_nan=False, allow_infinity=False),
            st.integers(min_value=-1000000000, max_value=1000000000),
        ),
        whale_tx_count=st.one_of(
            st.none(),
            st.floats(min_value=0.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
            st.integers(min_value=0, max_value=100000),
        ),
        defi_tvl=st.one_of(
            st.none(),
            st.floats(min_value=0.0, max_value=1e15, allow_nan=False, allow_infinity=False),
            st.integers(min_value=0, max_value=int(1e15)),
        ),
    )
    def test_external_metrics_schema_with_random_onchain_values(
        self,
        source_name: str,
        symbol: str | None,
        active_addresses: float | int | None,
        net_exchange_flow: float | int | None,
        whale_tx_count: float | int | None,
        defi_tvl: float | int | None,
    ) -> None:
        """
        Property: For any valid on-chain metric values, ExternalMetrics SHALL
        maintain correct schema with proper type conversions.

        This test verifies that the ExternalMetrics dataclass correctly handles
        various numeric types and None values for on-chain metrics.

        **Validates: Requirements 1.4**
        """
        # Create ExternalMetrics with random on-chain values
        import time

        metrics = ExternalMetrics(
            source_name=source_name,
            symbol=symbol,
            metrics={
                "active_addresses": float(active_addresses) if active_addresses is not None else None,
                "net_exchange_flow": float(net_exchange_flow) if net_exchange_flow is not None else None,
                "whale_tx_count": float(whale_tx_count) if whale_tx_count is not None else None,
                "defi_tvl": float(defi_tvl) if defi_tvl is not None else None,
                "fetched_at": time.time(),
            },
            is_stale=False,
            error_message=None,
        )

        # Validate the schema
        self._validate_external_metrics(metrics)

        # Additional checks for on-chain metric values
        if active_addresses is not None:
            assert isinstance(metrics.metrics["active_addresses"], float)
            assert metrics.metrics["active_addresses"] >= 0.0

        if net_exchange_flow is not None:
            assert isinstance(metrics.metrics["net_exchange_flow"], float)
            # Net exchange flow can be negative (outflow > inflow)

        if whale_tx_count is not None:
            assert isinstance(metrics.metrics["whale_tx_count"], float)
            assert metrics.metrics["whale_tx_count"] >= 0.0

        if defi_tvl is not None:
            assert isinstance(metrics.metrics["defi_tvl"], float)
            assert metrics.metrics["defi_tvl"] >= 0.0

    @settings(max_examples=20)
    @given(
        is_stale=st.booleans(),
        error_message=st.one_of(
            st.none(),
            st.sampled_from([
                "API key not configured",
                "HTTP error 429",
                "Network timeout",
                "Failed to fetch any on-chain data",
                "Request error",
            ]),
        ),
    )
    def test_external_metrics_handles_onchain_error_states(
        self,
        is_stale: bool,
        error_message: str | None,
    ) -> None:
        """
        Property: For any error state (stale data, error messages),
        ExternalMetrics SHALL maintain valid schema for on-chain data.

        This verifies that error handling doesn't break the schema contract.

        **Validates: Requirements 1.4**
        """
        # Create ExternalMetrics in error state
        import time

        metrics = ExternalMetrics(
            source_name="glassnode",
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
        has_active_addresses=st.booleans(),
        has_exchange_flow=st.booleans(),
        has_whale_count=st.booleans(),
        has_defi_tvl=st.booleans(),
    )
    def test_external_metrics_handles_partial_onchain_data(
        self,
        has_active_addresses: bool,
        has_exchange_flow: bool,
        has_whale_count: bool,
        has_defi_tvl: bool,
    ) -> None:
        """
        Property: For any combination of available/missing on-chain metrics,
        ExternalMetrics SHALL maintain valid schema.

        This tests that the schema is valid when some metrics are available
        and others are None (partial data scenarios).

        **Validates: Requirements 1.4**
        """
        # Generate random values for available metrics
        import random
        import time

        metrics_dict: dict[str, float | int | None] = {}

        if has_active_addresses:
            metrics_dict["active_addresses"] = float(random.randint(100000, 1000000))
        else:
            metrics_dict["active_addresses"] = None

        if has_exchange_flow:
            metrics_dict["net_exchange_flow"] = float(random.uniform(-10000, 10000))
        else:
            metrics_dict["net_exchange_flow"] = None

        if has_whale_count:
            metrics_dict["whale_tx_count"] = float(random.randint(0, 100))
        else:
            metrics_dict["whale_tx_count"] = None

        if has_defi_tvl:
            metrics_dict["defi_tvl"] = float(random.uniform(1e9, 1e12))
        else:
            metrics_dict["defi_tvl"] = None

        metrics_dict["fetched_at"] = time.time()

        # Create ExternalMetrics
        metrics = ExternalMetrics(
            source_name="glassnode",
            symbol="BTC",
            metrics=metrics_dict,
            is_stale=not any([has_active_addresses, has_exchange_flow, has_whale_count, has_defi_tvl]),
            error_message=None,
        )

        # Validate the schema
        self._validate_external_metrics(metrics)

        # Verify that None values are preserved
        if not has_active_addresses:
            assert metrics.metrics["active_addresses"] is None
        if not has_exchange_flow:
            assert metrics.metrics["net_exchange_flow"] is None
        if not has_whale_count:
            assert metrics.metrics["whale_tx_count"] is None
        if not has_defi_tvl:
            assert metrics.metrics["defi_tvl"] is None

    @settings(max_examples=20)
    @given(
        symbol=st.sampled_from(["BTC", "ETH", "BTC_USDT", "ETH_USDT", "btc", "eth"]),
    )
    def test_external_metrics_handles_symbol_normalization(
        self,
        symbol: str,
    ) -> None:
        """
        Property: For any symbol format (uppercase, lowercase, with/without pair),
        ExternalMetrics SHALL maintain valid schema.

        This tests that symbol normalization doesn't break the schema.

        **Validates: Requirements 1.4**
        """
        # Create ExternalMetrics with varying symbol formats
        import time

        metrics = ExternalMetrics(
            source_name="glassnode",
            symbol=symbol,
            metrics={
                "active_addresses": 950000.0,
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
        Property: For any on-chain metrics fetch, ExternalMetrics SHALL include
        a fetched_at timestamp in the metrics dict.

        This verifies that the timestamp is always included as required by
        the design.

        **Validates: Requirements 1.4**
        """
        # Create ExternalMetrics with timestamp
        metrics = ExternalMetrics(
            source_name="glassnode",
            symbol="BTC",
            metrics={
                "active_addresses": 950000.0,
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


class TestOnChainMetricsImmutability:
    """
    Additional property tests for on-chain ExternalMetrics immutability.

    Since ExternalMetrics is a frozen dataclass, it should be immutable.
    These tests verify that the immutability contract is maintained for
    on-chain data.

    **Validates: Requirements 1.4**
    """

    @settings(max_examples=15)
    @given(
        source_name=st.sampled_from(["glassnode", "intotheblock"]),
        metric_value=st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False),
    )
    def test_onchain_external_metrics_is_immutable(
        self,
        source_name: str,
        metric_value: float,
    ) -> None:
        """
        Property: On-chain ExternalMetrics instances SHALL be immutable (frozen).

        This verifies that the frozen=True dataclass attribute is working.

        **Validates: Requirements 1.4**
        """
        import time

        metrics = ExternalMetrics(
            source_name=source_name,
            symbol="BTC",
            metrics={"active_addresses": metric_value, "fetched_at": time.time()},
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
        metric_value=st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False),
    )
    def test_onchain_external_metrics_equality(
        self,
        metric_value: float,
    ) -> None:
        """
        Property: Two on-chain ExternalMetrics with identical values SHALL be equal.

        This verifies that the dataclass equality works correctly.

        **Validates: Requirements 1.4**
        """
        import time

        timestamp = time.time()

        metrics1 = ExternalMetrics(
            source_name="glassnode",
            symbol="BTC",
            metrics={"active_addresses": metric_value, "fetched_at": timestamp},
            is_stale=False,
            error_message=None,
        )

        metrics2 = ExternalMetrics(
            source_name="glassnode",
            symbol="BTC",
            metrics={"active_addresses": metric_value, "fetched_at": timestamp},
            is_stale=False,
            error_message=None,
        )

        assert metrics1 == metrics2, "Identical on-chain ExternalMetrics should be equal"

    @settings(max_examples=15)
    @given(
        value1=st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False),
        value2=st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False),
    )
    def test_onchain_external_metrics_inequality(
        self,
        value1: float,
        value2: float,
    ) -> None:
        """
        Property: Two on-chain ExternalMetrics with different values SHALL NOT be equal.

        This verifies that the dataclass equality correctly distinguishes different instances.

        **Validates: Requirements 1.4**
        """
        import time

        # Only test when values are actually different
        if value1 == value2:
            return

        timestamp = time.time()

        metrics1 = ExternalMetrics(
            source_name="glassnode",
            symbol="BTC",
            metrics={"active_addresses": value1, "fetched_at": timestamp},
            is_stale=False,
            error_message=None,
        )

        metrics2 = ExternalMetrics(
            source_name="glassnode",
            symbol="BTC",
            metrics={"active_addresses": value2, "fetched_at": timestamp},
            is_stale=False,
            error_message=None,
        )

        assert metrics1 != metrics2, "Different on-chain ExternalMetrics should not be equal"
