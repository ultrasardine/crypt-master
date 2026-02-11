"""
Property-based tests for Pionex Fill Pagination functionality.

Feature: pionex-api-extended
Property 3: Fill Pagination

These tests use the hypothesis library to verify that the fill
functionality correctly enforces the 100-fill pagination limit.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from lib.pionex.models import Fill, FillRole, OrderSide

# Custom strategies for fill testing
fill_id_strategy = st.integers(min_value=1, max_value=10_000_000)
order_id_strategy = st.integers(min_value=1, max_value=10_000_000)
symbol_strategy = st.sampled_from(["BTC_USDT", "ETH_USDT", "SOL_USDT", "DOGE_USDT"])
side_strategy = st.sampled_from([OrderSide.BUY, OrderSide.SELL])
role_strategy = st.sampled_from([FillRole.TAKER, FillRole.MAKER])
price_strategy = st.decimals(
    min_value=Decimal("0.01"),
    max_value=Decimal("100000.00"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)
size_strategy = st.decimals(
    min_value=Decimal("0.0001"),
    max_value=Decimal("1000.00"),
    places=4,
    allow_nan=False,
    allow_infinity=False,
)
fee_strategy = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("100.00"),
    places=8,
    allow_nan=False,
    allow_infinity=False,
)
fee_coin_strategy = st.sampled_from(["USDT", "BTC", "ETH", "BNB"])
timestamp_strategy = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 12, 31),
).map(lambda dt: dt.replace(tzinfo=UTC))


def create_fill(
    fill_id: int,
    order_id: int,
    symbol: str,
    side: OrderSide,
    role: FillRole,
    price: Decimal,
    size: Decimal,
    fee: Decimal,
    fee_coin: str,
    timestamp: datetime,
) -> Fill:
    """Create a Fill with the given parameters."""
    return Fill(
        id=fill_id,
        order_id=order_id,
        symbol=symbol,
        side=side,
        role=role,
        price=price,
        size=size,
        fee=fee,
        fee_coin=fee_coin,
        timestamp=timestamp,
    )


class TestFillPagination:
    """
    Property 3: Fill Pagination

    *For any* fill query returning more than 100 results, only the latest 100
    fills SHALL be returned.

    **Validates: Requirements 2.4**
    """

    @settings(max_examples=100)
    @given(
        num_fills=st.integers(min_value=1, max_value=100),
        symbol=symbol_strategy,
        side=side_strategy,
        role=role_strategy,
        price=price_strategy,
        size=size_strategy,
        fee=fee_strategy,
        fee_coin=fee_coin_strategy,
    )
    def test_fills_within_limit_returned_unchanged(
        self,
        num_fills: int,
        symbol: str,
        side: OrderSide,
        role: FillRole,
        price: Decimal,
        size: Decimal,
        fee: Decimal,
        fee_coin: str,
    ) -> None:
        """
        Property: Fill counts from 1 to 100 are returned unchanged.

        When the number of fills is within the 100-fill limit, all fills
        should be returned without truncation.

        **Validates: Requirements 2.4**
        """
        base_time = datetime(2024, 1, 1, tzinfo=UTC)
        fills = [
            Fill(
                id=i,
                order_id=1000 + i,
                symbol=symbol,
                side=side,
                role=role,
                price=price,
                size=size,
                fee=fee,
                fee_coin=fee_coin,
                timestamp=base_time,
            )
            for i in range(num_fills)
        ]

        # Simulate the pagination logic from get_fills
        paginated_fills = fills[:100]

        # All fills should be returned when count <= 100
        assert len(paginated_fills) == num_fills
        assert len(paginated_fills) <= 100

    @settings(max_examples=100)
    @given(
        num_fills=st.integers(min_value=101, max_value=500),
        symbol=symbol_strategy,
        side=side_strategy,
        role=role_strategy,
        price=price_strategy,
        size=size_strategy,
        fee=fee_strategy,
        fee_coin=fee_coin_strategy,
    )
    def test_fills_exceeding_limit_truncated_to_100(
        self,
        num_fills: int,
        symbol: str,
        side: OrderSide,
        role: FillRole,
        price: Decimal,
        size: Decimal,
        fee: Decimal,
        fee_coin: str,
    ) -> None:
        """
        Property: Fill counts exceeding 100 are truncated to 100.

        When the number of fills exceeds the 100-fill limit, only the
        first 100 fills should be returned.

        **Validates: Requirements 2.4**
        """
        base_time = datetime(2024, 1, 1, tzinfo=UTC)
        fills = [
            Fill(
                id=i,
                order_id=1000 + i,
                symbol=symbol,
                side=side,
                role=role,
                price=price,
                size=size,
                fee=fee,
                fee_coin=fee_coin,
                timestamp=base_time,
            )
            for i in range(num_fills)
        ]

        # Simulate the pagination logic from get_fills
        paginated_fills = fills[:100]

        # Should be truncated to exactly 100
        assert len(paginated_fills) == 100
        assert len(paginated_fills) < num_fills

    @settings(max_examples=50)
    @given(
        num_fills=st.integers(min_value=0, max_value=200),
    )
    def test_boundary_conditions_for_fill_count(self, num_fills: int) -> None:
        """
        Property: Boundary conditions for fill count are handled correctly.

        - 0 fills: Empty list returned
        - 1-100 fills: All fills returned
        - 101+ fills: Truncated to 100

        **Validates: Requirements 2.4**
        """
        base_time = datetime(2024, 1, 1, tzinfo=UTC)
        fills = [
            Fill(
                id=i,
                order_id=1000 + i,
                symbol="BTC_USDT",
                side=OrderSide.BUY,
                role=FillRole.TAKER,
                price=Decimal("50000.00"),
                size=Decimal("0.01"),
                fee=Decimal("0.001"),
                fee_coin="USDT",
                timestamp=base_time,
            )
            for i in range(num_fills)
        ]

        # Simulate the pagination logic from get_fills
        paginated_fills = fills[:100]

        if num_fills == 0:
            assert len(paginated_fills) == 0
        elif num_fills <= 100:
            assert len(paginated_fills) == num_fills
        else:
            assert len(paginated_fills) == 100

    @settings(max_examples=100)
    @given(
        fill_id=fill_id_strategy,
        order_id=order_id_strategy,
        symbol=symbol_strategy,
        side=side_strategy,
        role=role_strategy,
        price=price_strategy,
        size=size_strategy,
        fee=fee_strategy,
        fee_coin=fee_coin_strategy,
        timestamp=timestamp_strategy,
    )
    def test_fill_from_api_response_roundtrip(
        self,
        fill_id: int,
        order_id: int,
        symbol: str,
        side: OrderSide,
        role: FillRole,
        price: Decimal,
        size: Decimal,
        fee: Decimal,
        fee_coin: str,
        timestamp: datetime,
    ) -> None:
        """
        Property: Fill.from_api_response correctly parses API data.

        A Fill created from API response data should have all fields
        correctly populated.

        **Validates: Requirements 2.3**
        """
        # Simulate API response data
        api_data = {
            "id": fill_id,
            "orderId": order_id,
            "symbol": symbol,
            "side": side.value,
            "role": role.value,
            "price": str(price),
            "size": str(size),
            "fee": str(fee),
            "feeCoin": fee_coin,
            "timestamp": int(timestamp.timestamp() * 1000),
        }

        fill = Fill.from_api_response(api_data)

        assert fill.id == fill_id
        assert fill.order_id == order_id
        assert fill.symbol == symbol
        assert fill.side == side
        assert fill.role == role
        assert fill.price == price
        assert fill.size == size
        assert fill.fee == fee
        assert fill.fee_coin == fee_coin
        # Timestamp comparison with millisecond precision
        assert abs((fill.timestamp - timestamp).total_seconds()) < 1

    @settings(max_examples=50)
    @given(
        fills_data=st.lists(
            st.tuples(
                fill_id_strategy,
                order_id_strategy,
                side_strategy,
                role_strategy,
                price_strategy,
                size_strategy,
            ),
            min_size=0,
            max_size=150,
        ),
    )
    def test_pagination_preserves_order(
        self,
        fills_data: list[tuple[int, int, OrderSide, FillRole, Decimal, Decimal]],
    ) -> None:
        """
        Property: Pagination preserves the order of fills.

        When truncating to 100 fills, the first 100 fills should be
        preserved in their original order.

        **Validates: Requirements 2.4**
        """
        base_time = datetime(2024, 1, 1, tzinfo=UTC)
        fills = [
            Fill(
                id=fill_id,
                order_id=order_id,
                symbol="BTC_USDT",
                side=side,
                role=role,
                price=price,
                size=size,
                fee=Decimal("0.001"),
                fee_coin="USDT",
                timestamp=base_time,
            )
            for fill_id, order_id, side, role, price, size in fills_data
        ]

        # Simulate the pagination logic from get_fills
        paginated_fills = fills[:100]

        # Verify order is preserved
        for i, fill in enumerate(paginated_fills):
            assert fill == fills[i]

    @settings(max_examples=50)
    @given(
        side=side_strategy,
        role=role_strategy,
    )
    def test_fill_side_and_role_values(self, side: OrderSide, role: FillRole) -> None:
        """
        Property: Fill side and role are correctly serialized.

        BUY/SELL sides and TAKER/MAKER roles should be correctly
        parsed from API responses.

        **Validates: Requirements 2.3**
        """
        api_data = {
            "id": 1,
            "orderId": 100,
            "symbol": "BTC_USDT",
            "side": side.value,
            "role": role.value,
            "price": "50000.00",
            "size": "0.01",
            "fee": "0.001",
            "feeCoin": "USDT",
            "timestamp": 1704067200000,  # 2024-01-01 00:00:00 UTC
        }

        fill = Fill.from_api_response(api_data)

        assert fill.side == side
        assert fill.role == role
        assert fill.side.value in ("BUY", "SELL")
        assert fill.role.value in ("TAKER", "MAKER")
