"""
Property-based tests for MarketContextSnapshot Serialization.

Feature: market-intelligence-layer
Property 4: MarketContextSnapshot serialization round-trip

These tests use the hypothesis library to verify that MarketContextSnapshot
instances can be serialized to JSON and deserialized back without data loss.

**Validates: Requirements 2.4**
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.api.serializers import MarketContextSnapshotSerializer
from apps.core.models import MarketContextSnapshot

# =============================================================================
# Custom Strategies for MarketContextSnapshot Testing
# =============================================================================


@st.composite
def market_context_snapshot_instance(draw: st.DrawFn) -> MarketContextSnapshot:
    """
    Generate random MarketContextSnapshot instances for testing.

    Creates instances with various combinations of None and valid values
    to test serialization across all edge cases.
    """
    # Generate random values for all fields
    # For symbol, avoid whitespace-only strings, null characters, surrogates, and control chars
    symbol = draw(
        st.one_of(
            st.none(),
            st.text(
                min_size=1,
                max_size=20,
                alphabet=st.characters(
                    blacklist_categories=("Zs", "Cs", "Cc"),  # Exclude whitespace, surrogates, control
                    blacklist_characters=("\x00",),  # Exclude null character
                ),
            ).filter(lambda s: s and s.strip()),  # Ensure non-empty after stripping
        )
    )
    timestamp = timezone.now()

    btc_dominance = draw(
        st.one_of(
            st.none(),
            st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        )
    )

    global_market_cap = draw(
        st.one_of(
            st.none(),
            st.decimals(
                min_value=Decimal("0.0"),
                max_value=Decimal("1e15"),
                allow_nan=False,
                allow_infinity=False,
                places=2,
            ),
        )
    )

    total_volume_24h = draw(
        st.one_of(
            st.none(),
            st.decimals(
                min_value=Decimal("0.0"),
                max_value=Decimal("1e15"),
                allow_nan=False,
                allow_infinity=False,
                places=2,
            ),
        )
    )

    active_addresses = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=1000000)))

    net_exchange_flow = draw(
        st.one_of(
            st.none(),
            st.floats(min_value=-1e12, max_value=1e12, allow_nan=False, allow_infinity=False),
        )
    )

    whale_tx_count = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=10000)))

    defi_tvl = draw(
        st.one_of(
            st.none(),
            st.decimals(
                min_value=Decimal("0.0"),
                max_value=Decimal("1e15"),
                allow_nan=False,
                allow_infinity=False,
                places=2,
            ),
        )
    )

    social_sentiment_score = draw(
        st.one_of(
            st.none(),
            st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        )
    )

    social_mention_count = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=1000000)))

    social_buzz_score = draw(
        st.one_of(
            st.none(),
            st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        )
    )

    fear_greed_index = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=100)))

    is_stale = draw(st.booleans())

    # For stale_fields, avoid whitespace-only strings, null characters, surrogates, and control chars
    stale_fields = draw(
        st.lists(
            st.text(
                min_size=1,
                max_size=30,
                alphabet=st.characters(
                    blacklist_categories=("Zs", "Cs", "Cc"),  # Exclude whitespace, surrogates, control
                    blacklist_characters=("\x00",),
                ),
            ).filter(lambda s: s and s.strip()),
            max_size=10,
        )
    )

    regime = draw(
        st.one_of(
            st.none(),
            st.sampled_from(
                ["RISK_ON", "RISK_OFF", "RANGE_BOUND", "TRENDING_UP", "TRENDING_DOWN", "UNKNOWN"]
            ),
        )
    )

    trend_strength_score = draw(
        st.one_of(
            st.none(),
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        )
    )

    risk_regime_score = draw(
        st.one_of(
            st.none(),
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        )
    )

    sentiment_regime_score = draw(
        st.one_of(
            st.none(),
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        )
    )

    is_degraded = draw(st.booleans())

    # Create the instance
    instance = MarketContextSnapshot(
        symbol=symbol,
        timestamp=timestamp,
        btc_dominance=btc_dominance,
        global_market_cap=global_market_cap,
        total_volume_24h=total_volume_24h,
        active_addresses=active_addresses,
        net_exchange_flow=net_exchange_flow,
        whale_tx_count=whale_tx_count,
        defi_tvl=defi_tvl,
        social_sentiment_score=social_sentiment_score,
        social_mention_count=social_mention_count,
        social_buzz_score=social_buzz_score,
        fear_greed_index=fear_greed_index,
        is_stale=is_stale,
        stale_fields=stale_fields,
        regime=regime,
        trend_strength_score=trend_strength_score,
        risk_regime_score=risk_regime_score,
        sentiment_regime_score=sentiment_regime_score,
        is_degraded=is_degraded,
    )

    return instance


# =============================================================================
# Property 4: MarketContextSnapshot serialization round-trip
# =============================================================================


class TestMarketContextSnapshotSerialization:
    """
    Property 4: MarketContextSnapshot serialization round-trip

    *For any* valid `MarketContextSnapshot` instance, serializing it to JSON
    via the serializer and then deserializing the JSON back SHALL produce a
    `MarketContextSnapshot` with equivalent field values.

    This property ensures that no data is lost during serialization/deserialization
    and that the serializer correctly handles all field types including None values,
    Decimals, floats, and complex types like JSONField.

    **Validates: Requirements 2.4**
    """

    @settings(max_examples=20)
    @given(instance=market_context_snapshot_instance())
    @pytest.mark.django_db(transaction=True)
    def test_serialization_round_trip_preserves_data(
        self,
        instance: MarketContextSnapshot,
    ) -> None:
        """
        Property: For any MarketContextSnapshot instance, serialization followed
        by deserialization SHALL produce equivalent field values.

        This verifies that the serializer correctly handles all field types
        and preserves data integrity through the round-trip.

        **Validates: Requirements 2.4**
        """
        # Save the instance to get an ID
        instance.save()

        # Serialize to JSON
        serializer = MarketContextSnapshotSerializer(instance)
        serialized_data = serializer.data

        # Verify serialized data is a dict
        assert isinstance(serialized_data, dict), "Serialized data should be a dict"

        # Deserialize back to a new instance
        # We need to exclude read-only fields (id, created_at, updated_at) for creation
        create_data = {k: v for k, v in serialized_data.items() if k not in ["id", "created_at", "updated_at"]}

        deserializer = MarketContextSnapshotSerializer(data=create_data)
        assert deserializer.is_valid(), f"Deserialization failed: {deserializer.errors}"

        # Save the deserialized instance
        deserialized_instance = deserializer.save()

        # Compare field values (excluding auto-generated fields)
        assert deserialized_instance.symbol == instance.symbol
        assert deserialized_instance.timestamp == instance.timestamp

        # Compare numeric fields with appropriate tolerance
        if instance.btc_dominance is not None:
            assert deserialized_instance.btc_dominance == pytest.approx(
                instance.btc_dominance, abs=1e-6
            )
        else:
            assert deserialized_instance.btc_dominance is None

        # Compare Decimal fields
        if instance.global_market_cap is not None:
            assert deserialized_instance.global_market_cap == instance.global_market_cap
        else:
            assert deserialized_instance.global_market_cap is None

        if instance.total_volume_24h is not None:
            assert deserialized_instance.total_volume_24h == instance.total_volume_24h
        else:
            assert deserialized_instance.total_volume_24h is None

        # Compare integer fields
        assert deserialized_instance.active_addresses == instance.active_addresses
        assert deserialized_instance.whale_tx_count == instance.whale_tx_count
        assert deserialized_instance.social_mention_count == instance.social_mention_count
        assert deserialized_instance.fear_greed_index == instance.fear_greed_index

        # Compare float fields
        if instance.net_exchange_flow is not None:
            assert deserialized_instance.net_exchange_flow == pytest.approx(
                instance.net_exchange_flow, abs=1e-6
            )
        else:
            assert deserialized_instance.net_exchange_flow is None

        if instance.social_sentiment_score is not None:
            assert deserialized_instance.social_sentiment_score == pytest.approx(
                instance.social_sentiment_score, abs=1e-6
            )
        else:
            assert deserialized_instance.social_sentiment_score is None

        if instance.social_buzz_score is not None:
            assert deserialized_instance.social_buzz_score == pytest.approx(
                instance.social_buzz_score, abs=1e-6
            )
        else:
            assert deserialized_instance.social_buzz_score is None

        # Compare score fields
        if instance.trend_strength_score is not None:
            assert deserialized_instance.trend_strength_score == pytest.approx(
                instance.trend_strength_score, abs=1e-6
            )
        else:
            assert deserialized_instance.trend_strength_score is None

        if instance.risk_regime_score is not None:
            assert deserialized_instance.risk_regime_score == pytest.approx(
                instance.risk_regime_score, abs=1e-6
            )
        else:
            assert deserialized_instance.risk_regime_score is None

        if instance.sentiment_regime_score is not None:
            assert deserialized_instance.sentiment_regime_score == pytest.approx(
                instance.sentiment_regime_score, abs=1e-6
            )
        else:
            assert deserialized_instance.sentiment_regime_score is None

        # Compare boolean fields
        assert deserialized_instance.is_stale == instance.is_stale
        assert deserialized_instance.is_degraded == instance.is_degraded

        # Compare JSONField (stale_fields)
        assert deserialized_instance.stale_fields == instance.stale_fields

        # Compare string fields
        assert deserialized_instance.regime == instance.regime

        # Clean up
        instance.delete()
        deserialized_instance.delete()

    @settings(max_examples=15)
    @given(instance=market_context_snapshot_instance())
    @pytest.mark.django_db(transaction=True)
    def test_serialization_produces_valid_json_structure(
        self,
        instance: MarketContextSnapshot,
    ) -> None:
        """
        Property: For any MarketContextSnapshot instance, serialization SHALL
        produce a valid JSON-compatible dict with all expected fields.

        This verifies that the serializer output structure is correct.

        **Validates: Requirements 2.4**
        """
        # Save the instance
        instance.save()

        # Serialize
        serializer = MarketContextSnapshotSerializer(instance)
        data = serializer.data

        # Verify structure
        assert isinstance(data, dict)

        # Verify all expected fields are present
        expected_fields = {
            "id",
            "symbol",
            "timestamp",
            "btc_dominance",
            "global_market_cap",
            "total_volume_24h",
            "active_addresses",
            "net_exchange_flow",
            "whale_tx_count",
            "defi_tvl",
            "social_sentiment_score",
            "social_mention_count",
            "social_buzz_score",
            "fear_greed_index",
            "is_stale",
            "stale_fields",
            "regime",
            "trend_strength_score",
            "risk_regime_score",
            "sentiment_regime_score",
            "is_degraded",
            "created_at",
            "updated_at",
        }

        assert set(data.keys()) == expected_fields, (
            f"Serialized data missing fields: {expected_fields - set(data.keys())}"
        )

        # Verify types of non-None values
        if data["btc_dominance"] is not None:
            assert isinstance(data["btc_dominance"], (int, float))

        if data["stale_fields"] is not None:
            assert isinstance(data["stale_fields"], list)

        if data["is_stale"] is not None:
            assert isinstance(data["is_stale"], bool)

        # Clean up
        instance.delete()

    @settings(max_examples=15)
    @given(instance=market_context_snapshot_instance())
    @pytest.mark.django_db(transaction=True)
    def test_serialization_handles_none_values(
        self,
        instance: MarketContextSnapshot,
    ) -> None:
        """
        Property: For any MarketContextSnapshot instance with None values,
        serialization SHALL preserve None values correctly.

        This verifies that optional fields are handled properly.

        **Validates: Requirements 2.4**
        """
        # Save the instance
        instance.save()

        # Serialize
        serializer = MarketContextSnapshotSerializer(instance)
        data = serializer.data

        # Check that None values in the instance are preserved in serialized data
        if instance.btc_dominance is None:
            assert data["btc_dominance"] is None

        if instance.regime is None:
            assert data["regime"] is None

        if instance.trend_strength_score is None:
            assert data["trend_strength_score"] is None

        # Clean up
        instance.delete()

    @settings(max_examples=15)
    @given(instance=market_context_snapshot_instance())
    @pytest.mark.django_db(transaction=True)
    def test_deserialization_validates_data(
        self,
        instance: MarketContextSnapshot,
    ) -> None:
        """
        Property: For any valid serialized data, deserialization SHALL
        succeed and produce a valid instance.

        This verifies that the deserializer correctly validates input.

        **Validates: Requirements 2.4**
        """
        # Save the instance
        instance.save()

        # Serialize
        serializer = MarketContextSnapshotSerializer(instance)
        data = serializer.data

        # Remove read-only fields for deserialization
        create_data = {k: v for k, v in data.items() if k not in ["id", "created_at", "updated_at"]}

        # Deserialize
        deserializer = MarketContextSnapshotSerializer(data=create_data)

        # Should be valid
        assert deserializer.is_valid(), f"Deserialization validation failed: {deserializer.errors}"

        # Save should succeed
        new_instance = deserializer.save()
        assert new_instance.pk is not None

        # Clean up
        instance.delete()
        new_instance.delete()

    @settings(max_examples=15)
    @given(
        instance=market_context_snapshot_instance(),
    )
    @pytest.mark.django_db(transaction=True)
    def test_serialization_preserves_decimal_precision(
        self,
        instance: MarketContextSnapshot,
    ) -> None:
        """
        Property: For any MarketContextSnapshot with Decimal fields,
        serialization SHALL preserve decimal precision.

        This verifies that Decimal fields are handled correctly.

        **Validates: Requirements 2.4**
        """
        # Ensure we have some decimal values
        if instance.global_market_cap is None:
            instance.global_market_cap = Decimal("123456789.12")
        if instance.total_volume_24h is None:
            instance.total_volume_24h = Decimal("987654321.98")

        # Save the instance
        instance.save()

        # Serialize and deserialize
        serializer = MarketContextSnapshotSerializer(instance)
        data = serializer.data

        # Remove read-only fields
        create_data = {k: v for k, v in data.items() if k not in ["id", "created_at", "updated_at"]}

        deserializer = MarketContextSnapshotSerializer(data=create_data)
        assert deserializer.is_valid()
        new_instance = deserializer.save()

        # Verify decimal precision is preserved
        assert new_instance.global_market_cap == instance.global_market_cap
        assert new_instance.total_volume_24h == instance.total_volume_24h

        # Clean up
        instance.delete()
        new_instance.delete()

    @settings(max_examples=15)
    @given(
        instance=market_context_snapshot_instance(),
    )
    @pytest.mark.django_db(transaction=True)
    def test_serialization_preserves_jsonfield_structure(
        self,
        instance: MarketContextSnapshot,
    ) -> None:
        """
        Property: For any MarketContextSnapshot with JSONField data,
        serialization SHALL preserve the JSON structure.

        This verifies that JSONField (stale_fields) is handled correctly.

        **Validates: Requirements 2.4**
        """
        # Ensure we have some stale_fields data
        if not instance.stale_fields:
            instance.stale_fields = ["btc_dominance", "social_sentiment_score"]

        # Save the instance
        instance.save()

        # Serialize and deserialize
        serializer = MarketContextSnapshotSerializer(instance)
        data = serializer.data

        # Verify stale_fields is preserved in serialized data
        assert data["stale_fields"] == instance.stale_fields

        # Deserialize
        create_data = {k: v for k, v in data.items() if k not in ["id", "created_at", "updated_at"]}
        deserializer = MarketContextSnapshotSerializer(data=create_data)
        assert deserializer.is_valid()
        new_instance = deserializer.save()

        # Verify JSONField structure is preserved
        assert new_instance.stale_fields == instance.stale_fields

        # Clean up
        instance.delete()
        new_instance.delete()
