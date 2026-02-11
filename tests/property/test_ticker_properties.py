"""
Property-based tests for Pionex Ticker Models.

Feature: pionex-api-extended
Property 6: Ticker Change Calculation
Property 7: Book Ticker Spread

These tests use the hypothesis library to verify that ticker models
correctly calculate derived values.
"""

from datetime import UTC, datetime
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from lib.pionex.models import BookTicker, Ticker24hr

# Custom strategies for ticker testing
# Use positive decimals for prices to avoid division by zero
positive_decimal_strategy = st.decimals(
    min_value=Decimal("0.00000001"),
    max_value=Decimal("1000000"),
    allow_nan=False,
    allow_infinity=False,
    places=8,
)

# Non-negative decimal strategy for sizes/volumes
non_negative_decimal_strategy = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("1000000000"),
    allow_nan=False,
    allow_infinity=False,
    places=8,
)

# Zero decimal for edge case testing
zero_decimal = st.just(Decimal("0"))

# Symbol strategy
symbol_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Nd"), whitelist_characters="_"),
    min_size=3,
    max_size=20,
)


class TestTickerChangeCalculation:
    """
    Property 6: Ticker Change Calculation

    *For any* 24hr ticker, change_percent = (close - open) / open * 100.

    **Validates: Requirements 3.3**
    """

    @settings(max_examples=100)
    @given(
        open_price=positive_decimal_strategy,
        close_price=positive_decimal_strategy,
    )
    def test_change_percent_formula(
        self, open_price: Decimal, close_price: Decimal
    ) -> None:
        """
        Property: change_percent equals (close - open) / open * 100.

        For any valid open and close prices, the change_percent property
        should correctly calculate the percentage change.

        **Validates: Requirements 3.3**
        """
        ticker = Ticker24hr(
            symbol="BTC_USDT",
            time=datetime.now(tz=UTC),
            open=open_price,
            close=close_price,
            high=max(open_price, close_price),
            low=min(open_price, close_price),
            volume=Decimal("1000"),
            amount=Decimal("50000"),
            count=100,
        )

        # Calculate expected change percent
        expected = float((close_price - open_price) / open_price * 100)

        # Allow small floating point tolerance
        assert abs(ticker.change_percent - expected) < 0.0001, (
            f"change_percent {ticker.change_percent} != expected {expected} "
            f"for open={open_price}, close={close_price}"
        )

    @settings(max_examples=100)
    @given(
        price=positive_decimal_strategy,
    )
    def test_change_percent_zero_when_unchanged(self, price: Decimal) -> None:
        """
        Property: change_percent is 0 when open equals close.

        When the price hasn't changed, the percentage change should be 0.

        **Validates: Requirements 3.3**
        """
        ticker = Ticker24hr(
            symbol="BTC_USDT",
            time=datetime.now(tz=UTC),
            open=price,
            close=price,
            high=price,
            low=price,
            volume=Decimal("1000"),
            amount=Decimal("50000"),
            count=100,
        )

        assert ticker.change_percent == 0.0, (
            f"change_percent should be 0 when open=close, got {ticker.change_percent}"
        )

    @settings(max_examples=50)
    @given(
        open_price=positive_decimal_strategy,
    )
    def test_change_percent_positive_when_price_increases(
        self, open_price: Decimal
    ) -> None:
        """
        Property: change_percent is positive when close > open.

        When the price increases, the percentage change should be positive.

        **Validates: Requirements 3.3**
        """
        # Ensure close is higher than open
        close_price = open_price * Decimal("1.1")

        ticker = Ticker24hr(
            symbol="BTC_USDT",
            time=datetime.now(tz=UTC),
            open=open_price,
            close=close_price,
            high=close_price,
            low=open_price,
            volume=Decimal("1000"),
            amount=Decimal("50000"),
            count=100,
        )

        assert ticker.change_percent > 0, (
            f"change_percent should be positive when close > open, "
            f"got {ticker.change_percent} for open={open_price}, close={close_price}"
        )

    @settings(max_examples=50)
    @given(
        open_price=positive_decimal_strategy,
    )
    def test_change_percent_negative_when_price_decreases(
        self, open_price: Decimal
    ) -> None:
        """
        Property: change_percent is negative when close < open.

        When the price decreases, the percentage change should be negative.

        **Validates: Requirements 3.3**
        """
        # Ensure close is lower than open
        close_price = open_price * Decimal("0.9")

        ticker = Ticker24hr(
            symbol="BTC_USDT",
            time=datetime.now(tz=UTC),
            open=open_price,
            close=close_price,
            high=open_price,
            low=close_price,
            volume=Decimal("1000"),
            amount=Decimal("50000"),
            count=100,
        )

        assert ticker.change_percent < 0, (
            f"change_percent should be negative when close < open, "
            f"got {ticker.change_percent} for open={open_price}, close={close_price}"
        )

    def test_change_percent_zero_when_open_is_zero(self) -> None:
        """
        Property: change_percent is 0 when open is 0 (edge case).

        Division by zero should be handled gracefully by returning 0.

        **Validates: Requirements 3.3**
        """
        ticker = Ticker24hr(
            symbol="BTC_USDT",
            time=datetime.now(tz=UTC),
            open=Decimal("0"),
            close=Decimal("100"),
            high=Decimal("100"),
            low=Decimal("0"),
            volume=Decimal("1000"),
            amount=Decimal("50000"),
            count=100,
        )

        assert ticker.change_percent == 0.0, (
            f"change_percent should be 0 when open=0, got {ticker.change_percent}"
        )


class TestBookTickerSpread:
    """
    Property 7: Book Ticker Spread

    *For any* book ticker, spread = ask_price - bid_price >= 0.

    **Validates: Requirements 3.4**
    """

    @settings(max_examples=100)
    @given(
        bid_price=positive_decimal_strategy,
        ask_price=positive_decimal_strategy,
    )
    def test_spread_formula(self, bid_price: Decimal, ask_price: Decimal) -> None:
        """
        Property: spread equals ask_price - bid_price.

        For any bid and ask prices, the spread property should correctly
        calculate the difference.

        **Validates: Requirements 3.4**
        """
        book_ticker = BookTicker(
            symbol="BTC_USDT",
            bid_price=bid_price,
            bid_size=Decimal("1.0"),
            ask_price=ask_price,
            ask_size=Decimal("1.0"),
            timestamp=datetime.now(tz=UTC),
        )

        expected_spread = ask_price - bid_price

        assert book_ticker.spread == expected_spread, (
            f"spread {book_ticker.spread} != expected {expected_spread} "
            f"for bid={bid_price}, ask={ask_price}"
        )

    @settings(max_examples=100)
    @given(
        bid_price=positive_decimal_strategy,
    )
    def test_spread_non_negative_when_ask_gte_bid(self, bid_price: Decimal) -> None:
        """
        Property: spread >= 0 when ask_price >= bid_price.

        In a normal market, ask price is always >= bid price,
        so spread should be non-negative.

        **Validates: Requirements 3.4**
        """
        # Ask price is at least bid price (normal market condition)
        ask_price = bid_price * Decimal("1.001")

        book_ticker = BookTicker(
            symbol="BTC_USDT",
            bid_price=bid_price,
            bid_size=Decimal("1.0"),
            ask_price=ask_price,
            ask_size=Decimal("1.0"),
            timestamp=datetime.now(tz=UTC),
        )

        assert book_ticker.spread >= 0, (
            f"spread should be >= 0 when ask >= bid, "
            f"got {book_ticker.spread} for bid={bid_price}, ask={ask_price}"
        )

    @settings(max_examples=50)
    @given(
        price=positive_decimal_strategy,
    )
    def test_spread_zero_when_bid_equals_ask(self, price: Decimal) -> None:
        """
        Property: spread is 0 when bid_price equals ask_price.

        When bid and ask are the same (locked market), spread should be 0.

        **Validates: Requirements 3.4**
        """
        book_ticker = BookTicker(
            symbol="BTC_USDT",
            bid_price=price,
            bid_size=Decimal("1.0"),
            ask_price=price,
            ask_size=Decimal("1.0"),
            timestamp=datetime.now(tz=UTC),
        )

        assert book_ticker.spread == Decimal("0"), (
            f"spread should be 0 when bid=ask, got {book_ticker.spread}"
        )

    @settings(max_examples=50)
    @given(
        bid_price=positive_decimal_strategy,
        spread_amount=positive_decimal_strategy,
    )
    def test_spread_equals_difference(
        self, bid_price: Decimal, spread_amount: Decimal
    ) -> None:
        """
        Property: spread equals the actual difference between ask and bid.

        For any given spread amount, the calculated spread should match.

        **Validates: Requirements 3.4**
        """
        ask_price = bid_price + spread_amount

        book_ticker = BookTicker(
            symbol="BTC_USDT",
            bid_price=bid_price,
            bid_size=Decimal("1.0"),
            ask_price=ask_price,
            ask_size=Decimal("1.0"),
            timestamp=datetime.now(tz=UTC),
        )

        assert book_ticker.spread == spread_amount, (
            f"spread {book_ticker.spread} != expected {spread_amount}"
        )

    @settings(max_examples=50)
    @given(
        bid_price=positive_decimal_strategy,
        bid_size=non_negative_decimal_strategy,
        ask_size=non_negative_decimal_strategy,
    )
    def test_spread_independent_of_sizes(
        self, bid_price: Decimal, bid_size: Decimal, ask_size: Decimal
    ) -> None:
        """
        Property: spread calculation is independent of bid/ask sizes.

        The spread should only depend on prices, not quantities.

        **Validates: Requirements 3.4**
        """
        ask_price = bid_price * Decimal("1.01")

        book_ticker = BookTicker(
            symbol="BTC_USDT",
            bid_price=bid_price,
            bid_size=bid_size,
            ask_price=ask_price,
            ask_size=ask_size,
            timestamp=datetime.now(tz=UTC),
        )

        expected_spread = ask_price - bid_price

        assert book_ticker.spread == expected_spread, (
            f"spread should be independent of sizes, "
            f"got {book_ticker.spread} != expected {expected_spread}"
        )
