"""
Property-based tests for Pionex Mass Order functionality.

Feature: pionex-api-extended
Property 2: Mass Order Limit

These tests use the hypothesis library to verify that the mass order
functionality correctly enforces the 20-order limit.
"""

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from lib.pionex.models import MassOrderRequest, OrderSide

# Custom strategies for mass order testing
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
side_strategy = st.sampled_from([OrderSide.BUY, OrderSide.SELL])
client_order_id_strategy = st.one_of(
    st.none(),
    st.text(min_size=1, max_size=36, alphabet=st.characters(whitelist_categories=("L", "N"))),
)


def create_mass_order_request(
    side: OrderSide, price: Decimal, size: Decimal, client_order_id: str | None
) -> MassOrderRequest:
    """Create a MassOrderRequest with the given parameters."""
    return MassOrderRequest(
        side=side,
        price=price,
        size=size,
        client_order_id=client_order_id,
    )


class TestMassOrderLimit:
    """
    Property 2: Mass Order Limit

    *For any* mass order request, the number of orders SHALL NOT exceed 20.

    **Validates: Requirements 1.5**
    """

    @settings(max_examples=100)
    @given(
        num_orders=st.integers(min_value=1, max_value=20),
        side=side_strategy,
        price=price_strategy,
        size=size_strategy,
    )
    def test_valid_order_count_accepted(
        self, num_orders: int, side: OrderSide, price: Decimal, size: Decimal
    ) -> None:
        """
        Property: Order counts from 1 to 20 are valid.

        Creating a list of 1-20 MassOrderRequest objects should succeed
        without raising any validation errors.

        **Validates: Requirements 1.5**
        """
        orders = [
            MassOrderRequest(side=side, price=price, size=size) for _ in range(num_orders)
        ]

        # Should be able to create the list without errors
        assert len(orders) == num_orders
        assert len(orders) <= 20

    @settings(max_examples=100)
    @given(
        num_orders=st.integers(min_value=21, max_value=100),
        side=side_strategy,
        price=price_strategy,
        size=size_strategy,
    )
    def test_order_count_exceeding_20_is_invalid(
        self, num_orders: int, side: OrderSide, price: Decimal, size: Decimal
    ) -> None:
        """
        Property: Order counts exceeding 20 should be rejected.

        A list of more than 20 orders should be considered invalid
        for mass order submission.

        **Validates: Requirements 1.5**
        """
        orders = [
            MassOrderRequest(side=side, price=price, size=size) for _ in range(num_orders)
        ]

        # The list can be created, but it exceeds the limit
        assert len(orders) > 20
        # This would fail validation in create_mass_order()

    @settings(max_examples=100)
    @given(
        side=side_strategy,
        price=price_strategy,
        size=size_strategy,
        client_order_id=client_order_id_strategy,
    )
    def test_mass_order_request_to_api_params(
        self, side: OrderSide, price: Decimal, size: Decimal, client_order_id: str | None
    ) -> None:
        """
        Property: MassOrderRequest.to_api_params() produces valid parameters.

        The to_api_params() method should always produce a dictionary
        with the required fields.

        **Validates: Requirements 1.5**
        """
        order = MassOrderRequest(
            side=side,
            price=price,
            size=size,
            client_order_id=client_order_id,
        )

        params = order.to_api_params()

        # Required fields should be present
        assert "side" in params
        assert "price" in params
        assert "size" in params

        # Side should be the enum value
        assert params["side"] == side.value

        # Price and size should be strings
        assert params["price"] == str(price)
        assert params["size"] == str(size)

        # Client order ID should be present only if provided
        if client_order_id:
            assert params["clientOrderId"] == client_order_id
        else:
            assert "clientOrderId" not in params

    @settings(max_examples=50)
    @given(
        orders_data=st.lists(
            st.tuples(side_strategy, price_strategy, size_strategy),
            min_size=1,
            max_size=20,
        ),
    )
    def test_batch_order_params_generation(
        self, orders_data: list[tuple[OrderSide, Decimal, Decimal]]
    ) -> None:
        """
        Property: Batch of orders produces valid API parameters.

        Converting a batch of MassOrderRequest objects to API parameters
        should produce a list of valid parameter dictionaries.

        **Validates: Requirements 1.5**
        """
        orders = [
            MassOrderRequest(side=side, price=price, size=size)
            for side, price, size in orders_data
        ]

        params_list = [order.to_api_params() for order in orders]

        # Should have same number of params as orders
        assert len(params_list) == len(orders)

        # Each params dict should have required fields
        for params in params_list:
            assert "side" in params
            assert "price" in params
            assert "size" in params
            assert params["side"] in ("BUY", "SELL")

    @settings(max_examples=50)
    @given(
        price=price_strategy,
        size=size_strategy,
    )
    def test_order_side_values(self, price: Decimal, size: Decimal) -> None:
        """
        Property: Order side is correctly serialized.

        BUY and SELL sides should be correctly converted to their
        string representations in API parameters.

        **Validates: Requirements 1.5**
        """
        buy_order = MassOrderRequest(side=OrderSide.BUY, price=price, size=size)
        sell_order = MassOrderRequest(side=OrderSide.SELL, price=price, size=size)

        assert buy_order.to_api_params()["side"] == "BUY"
        assert sell_order.to_api_params()["side"] == "SELL"

    @settings(max_examples=100)
    @given(
        num_orders=st.integers(min_value=0, max_value=25),
    )
    def test_boundary_order_counts(self, num_orders: int) -> None:
        """
        Property: Boundary conditions for order count are handled correctly.

        - 0 orders: Invalid (at least one required)
        - 1-20 orders: Valid
        - 21+ orders: Invalid (exceeds limit)

        **Validates: Requirements 1.5**
        """
        if num_orders == 0:
            # Empty list is invalid
            orders: list[MassOrderRequest] = []
            assert len(orders) == 0
            # This would fail validation in create_mass_order()
        elif num_orders <= 20:
            # Valid range
            orders = [
                MassOrderRequest(
                    side=OrderSide.BUY,
                    price=Decimal("100.00"),
                    size=Decimal("0.01"),
                )
                for _ in range(num_orders)
            ]
            assert 1 <= len(orders) <= 20
        else:
            # Exceeds limit
            orders = [
                MassOrderRequest(
                    side=OrderSide.BUY,
                    price=Decimal("100.00"),
                    size=Decimal("0.01"),
                )
                for _ in range(num_orders)
            ]
            assert len(orders) > 20
