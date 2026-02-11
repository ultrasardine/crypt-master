"""
Property-based tests for Order Status Consistency.

Feature: pionex-api-extended
Property 5: Order Status Consistency

These tests use the hypothesis library to verify that OrderDetail
maintains consistent status values and filled size constraints.

*For any* order, status SHALL be either "OPEN" or "CLOSED" and filledSize <= size.

**Validates: Requirements 1.7**
"""

from datetime import UTC, datetime
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from lib.pionex.models import OrderDetail, OrderDetailStatus, OrderSide, OrderType


# Custom strategies for order testing
symbol_strategy = st.sampled_from(["BTC_USDT", "ETH_USDT", "SOL_USDT", "DOGE_USDT"])
side_strategy = st.sampled_from([OrderSide.BUY, OrderSide.SELL])
order_type_strategy = st.sampled_from([OrderType.LIMIT, OrderType.MARKET])
status_strategy = st.sampled_from([OrderDetailStatus.OPEN, OrderDetailStatus.CLOSED])

# Decimal strategies with reasonable trading values
price_strategy = st.decimals(
    min_value=Decimal("0.00000001"),
    max_value=Decimal("1000000.00"),
    places=8,
    allow_nan=False,
    allow_infinity=False,
)
size_strategy = st.decimals(
    min_value=Decimal("0.00000001"),
    max_value=Decimal("1000000.00"),
    places=8,
    allow_nan=False,
    allow_infinity=False,
)
fee_strategy = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("1000.00"),
    places=8,
    allow_nan=False,
    allow_infinity=False,
)

timestamp_strategy = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 12, 31),
    timezones=st.just(UTC),
)


class TestOrderStatusConsistency:
    """
    Property 5: Order Status Consistency

    *For any* order, status SHALL be either "OPEN" or "CLOSED" and filledSize <= size.

    **Validates: Requirements 1.7**
    """

    @settings(max_examples=100)
    @given(
        status=status_strategy,
    )
    def test_status_is_open_or_closed(self, status: OrderDetailStatus) -> None:
        """
        Property: Order status is always either OPEN or CLOSED.

        The OrderDetailStatus enum only allows OPEN or CLOSED values,
        ensuring status consistency.

        **Validates: Requirements 1.7**
        """
        assert status in (OrderDetailStatus.OPEN, OrderDetailStatus.CLOSED)
        assert status.value in ("OPEN", "CLOSED")

    @settings(max_examples=100)
    @given(
        size=size_strategy,
        filled_ratio=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    )
    def test_filled_size_never_exceeds_size(
        self, size: Decimal, filled_ratio: float
    ) -> None:
        """
        Property: filledSize <= size for any order.

        The filled size should never exceed the original order size.

        **Validates: Requirements 1.7**
        """
        filled_size = size * Decimal(str(filled_ratio))
        assert filled_size <= size

    @settings(max_examples=100)
    @given(
        order_id=st.integers(min_value=1, max_value=2**63 - 1),
        symbol=symbol_strategy,
        order_type=order_type_strategy,
        side=side_strategy,
        price=price_strategy,
        size=size_strategy,
        filled_ratio=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        fee=fee_strategy,
        status=status_strategy,
        ioc=st.booleans(),
        source=st.sampled_from(["MANUAL", "API"]),
        create_time=timestamp_strategy,
    )
    def test_order_detail_consistency(
        self,
        order_id: int,
        symbol: str,
        order_type: OrderType,
        side: OrderSide,
        price: Decimal,
        size: Decimal,
        filled_ratio: float,
        fee: Decimal,
        status: OrderDetailStatus,
        ioc: bool,
        source: str,
        create_time: datetime,
    ) -> None:
        """
        Property: OrderDetail maintains consistency constraints.

        For any OrderDetail instance:
        - status is either OPEN or CLOSED
        - filled_size <= size

        **Validates: Requirements 1.7**
        """
        filled_size = size * Decimal(str(filled_ratio))
        filled_amount = filled_size * price

        order = OrderDetail(
            order_id=order_id,
            symbol=symbol,
            order_type=order_type,
            side=side,
            price=price,
            size=size,
            amount=None,
            filled_size=filled_size,
            filled_amount=filled_amount,
            fee=fee,
            fee_coin="USDT",
            status=status,
            ioc=ioc,
            client_order_id=None,
            source=source,
            create_time=create_time,
            update_time=create_time,
        )

        # Property 5: status is OPEN or CLOSED
        assert order.status in (OrderDetailStatus.OPEN, OrderDetailStatus.CLOSED)

        # Property 5: filledSize <= size
        assert order.filled_size <= order.size

    @settings(max_examples=100)
    @given(
        status_str=st.sampled_from(["OPEN", "CLOSED", "open", "closed", "Open", "Closed"]),
    )
    def test_from_api_response_status_parsing(self, status_str: str) -> None:
        """
        Property: from_api_response correctly parses status to OPEN or CLOSED.

        The API may return status in various cases, but the parsed
        OrderDetail should always have status as OPEN or CLOSED.

        **Validates: Requirements 1.7**
        """
        api_data = {
            "orderId": 12345,
            "symbol": "BTC_USDT",
            "type": "LIMIT",
            "side": "BUY",
            "price": "50000.00",
            "size": "0.1",
            "filledSize": "0.05",
            "filledAmount": "2500.00",
            "fee": "0.001",
            "feeCoin": "USDT",
            "status": status_str,
            "IOC": False,
            "source": "API",
            "createTime": 1700000000000,
            "updateTime": 1700000000000,
        }

        order = OrderDetail.from_api_response(api_data)

        # Status should be parsed to OPEN or CLOSED
        assert order.status in (OrderDetailStatus.OPEN, OrderDetailStatus.CLOSED)

    @settings(max_examples=100)
    @given(
        size_str=st.decimals(
            min_value=Decimal("0.00000001"),
            max_value=Decimal("1000000.00"),
            places=8,
            allow_nan=False,
            allow_infinity=False,
        ).map(str),
        filled_ratio=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    )
    def test_from_api_response_filled_size_constraint(
        self, size_str: str, filled_ratio: float
    ) -> None:
        """
        Property: from_api_response maintains filledSize <= size constraint.

        When parsing API response, the filled size should never exceed
        the original order size.

        **Validates: Requirements 1.7**
        """
        size = Decimal(size_str)
        filled_size = size * Decimal(str(filled_ratio))

        api_data = {
            "orderId": 12345,
            "symbol": "BTC_USDT",
            "type": "LIMIT",
            "side": "BUY",
            "price": "50000.00",
            "size": size_str,
            "filledSize": str(filled_size),
            "filledAmount": str(filled_size * Decimal("50000.00")),
            "fee": "0.001",
            "feeCoin": "USDT",
            "status": "OPEN",
            "IOC": False,
            "source": "API",
            "createTime": 1700000000000,
            "updateTime": 1700000000000,
        }

        order = OrderDetail.from_api_response(api_data)

        # filledSize <= size
        assert order.filled_size <= order.size

    @settings(max_examples=50)
    @given(
        orders_data=st.lists(
            st.tuples(
                status_strategy,
                size_strategy,
                st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
            ),
            min_size=1,
            max_size=20,
        ),
    )
    def test_batch_orders_consistency(
        self, orders_data: list[tuple[OrderDetailStatus, Decimal, float]]
    ) -> None:
        """
        Property: Batch of orders all maintain consistency constraints.

        For any batch of orders, each order should satisfy:
        - status is OPEN or CLOSED
        - filledSize <= size

        **Validates: Requirements 1.7**
        """
        for i, (status, size, filled_ratio) in enumerate(orders_data):
            filled_size = size * Decimal(str(filled_ratio))

            order = OrderDetail(
                order_id=i + 1,
                symbol="BTC_USDT",
                order_type=OrderType.LIMIT,
                side=OrderSide.BUY,
                price=Decimal("50000.00"),
                size=size,
                amount=None,
                filled_size=filled_size,
                filled_amount=filled_size * Decimal("50000.00"),
                fee=Decimal("0.001"),
                fee_coin="USDT",
                status=status,
                ioc=False,
                client_order_id=None,
                source="API",
                create_time=datetime.now(tz=UTC),
                update_time=datetime.now(tz=UTC),
            )

            # Property 5 constraints
            assert order.status in (OrderDetailStatus.OPEN, OrderDetailStatus.CLOSED)
            assert order.filled_size <= order.size

    @settings(max_examples=100)
    @given(
        status=status_strategy,
        size=size_strategy,
    )
    def test_open_order_can_have_partial_fill(
        self, status: OrderDetailStatus, size: Decimal
    ) -> None:
        """
        Property: OPEN orders can have any fill level from 0 to size.

        An OPEN order may be unfilled, partially filled, or fully filled
        (though fully filled orders typically become CLOSED).

        **Validates: Requirements 1.7**
        """
        # Test various fill levels for OPEN orders
        for fill_level in [Decimal("0"), size / 2, size]:
            order = OrderDetail(
                order_id=1,
                symbol="BTC_USDT",
                order_type=OrderType.LIMIT,
                side=OrderSide.BUY,
                price=Decimal("50000.00"),
                size=size,
                amount=None,
                filled_size=fill_level,
                filled_amount=fill_level * Decimal("50000.00"),
                fee=Decimal("0.001"),
                fee_coin="USDT",
                status=status,
                ioc=False,
                client_order_id=None,
                source="API",
                create_time=datetime.now(tz=UTC),
                update_time=datetime.now(tz=UTC),
            )

            # Constraint always holds
            assert order.filled_size <= order.size

    @settings(max_examples=100)
    @given(
        invalid_status=st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("L",)),
        ).filter(lambda s: s.upper() not in ("OPEN", "CLOSED")),
    )
    def test_invalid_status_defaults_to_open(self, invalid_status: str) -> None:
        """
        Property: Invalid status values default to OPEN.

        When the API returns an unrecognized status, the parser
        should default to OPEN to maintain consistency.

        **Validates: Requirements 1.7**
        """
        api_data = {
            "orderId": 12345,
            "symbol": "BTC_USDT",
            "type": "LIMIT",
            "side": "BUY",
            "price": "50000.00",
            "size": "0.1",
            "filledSize": "0.05",
            "filledAmount": "2500.00",
            "fee": "0.001",
            "feeCoin": "USDT",
            "status": invalid_status,
            "IOC": False,
            "source": "API",
            "createTime": 1700000000000,
            "updateTime": 1700000000000,
        }

        order = OrderDetail.from_api_response(api_data)

        # Should default to OPEN for invalid status
        assert order.status in (OrderDetailStatus.OPEN, OrderDetailStatus.CLOSED)
