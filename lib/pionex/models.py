"""
Pionex API Data Models.

This module defines the data structures used for Pionex API responses
including market data, order book, and trade information.

Requirements:
- 1.2: Retrieve available SPOT and PERP symbols
- 1.5: Retrieve recent trades for a symbol
- 1.6: Retrieve bid/ask depth
- 1.7: Return structured errors with status code, message, and retry eligibility
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class SymbolType(Enum):
    """Type of trading symbol."""

    SPOT = "SPOT"
    PERP = "PERP"


class BotType(Enum):
    """Type of trading bot.

    Requirements:
        - 10.1: Retrieve all active bots (Grid, DCA, Infinity Grid, Futures Grid)
        - 10.2: Retrieve bot type for each bot
    """

    GRID = "GRID"
    DCA = "DCA"
    INFINITY_GRID = "INFINITY_GRID"
    FUTURES_GRID = "FUTURES_GRID"


class BotStatus(Enum):
    """Status of a trading bot.

    Requirements:
        - 10.2: Retrieve bot status for each bot
    """

    ACTIVE = "ACTIVE"
    STOPPED = "STOPPED"
    ERROR = "ERROR"
    CREATING = "CREATING"
    STOPPING = "STOPPING"


class OrderSide(Enum):
    """Side of an order or trade."""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    """Type of order.

    Requirements:
        - 1.4: Submit LIMIT or MARKET orders
    """

    LIMIT = "LIMIT"
    MARKET = "MARKET"


class OrderStatus(Enum):
    """Status of an order."""

    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    PENDING_CANCEL = "PENDING_CANCEL"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class TimeInForce(Enum):
    """Time in force for an order.

    Specifies how long an order remains active before it is executed or expires.
    """

    GTC = "GTC"  # Good Till Canceled
    IOC = "IOC"  # Immediate Or Cancel
    FOK = "FOK"  # Fill Or Kill
    GTX = "GTX"  # Good Till Crossing (Post Only)


@dataclass(frozen=True)
class Symbol:
    """
    Trading symbol information from Pionex.

    Attributes:
        symbol: The trading pair symbol (e.g., "BTC_USDT")
        base_currency: The base currency (e.g., "BTC")
        quote_currency: The quote currency (e.g., "USDT")
        symbol_type: Whether this is a SPOT or PERP symbol
        base_precision: Decimal precision for base currency
        quote_precision: Decimal precision for quote currency
        min_amount: Minimum order amount
        min_notional: Minimum order value in quote currency
        is_active: Whether trading is enabled for this symbol
    """

    symbol: str
    base_currency: str
    quote_currency: str
    symbol_type: SymbolType
    base_precision: int
    quote_precision: int
    min_amount: Decimal
    min_notional: Decimal
    is_active: bool = True


@dataclass(frozen=True)
class Candle:
    """
    OHLCV candlestick data.

    Attributes:
        timestamp: The candle open time
        open: Opening price
        high: Highest price during the period
        low: Lowest price during the period
        close: Closing price
        volume: Trading volume in base currency
    """

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class OrderBookLevel:
    """
    A single price level in the order book.

    Attributes:
        price: The price at this level
        quantity: The total quantity at this price
    """

    price: Decimal
    quantity: Decimal


@dataclass(frozen=True)
class OrderBook:
    """
    Order book depth data.

    Attributes:
        symbol: The trading pair symbol
        bids: List of bid levels (buy orders), sorted by price descending
        asks: List of ask levels (sell orders), sorted by price ascending
        timestamp: When this snapshot was taken
    """

    symbol: str
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    timestamp: datetime


@dataclass(frozen=True)
class Trade:
    """
    A single trade from the market.

    Attributes:
        trade_id: Unique identifier for the trade
        symbol: The trading pair symbol
        price: The trade price
        quantity: The trade quantity
        side: Whether this was a buy or sell
        timestamp: When the trade occurred
    """

    trade_id: str
    symbol: str
    price: Decimal
    quantity: Decimal
    side: OrderSide
    timestamp: datetime


@dataclass(frozen=True)
class Balance:
    """
    Account balance for a currency.

    Represents the balance of a single currency in the user's account,
    including both available (free) and locked (in orders) amounts.

    Attributes:
        currency: The currency code (e.g., "BTC", "USDT")
        free: Available balance that can be used for trading
        locked: Balance locked in open orders
        total: Total balance (free + locked)

    Requirements:
        - 1.3: Retrieve all currency balances from /api/v1/account/balance
    """

    currency: str
    free: Decimal
    locked: Decimal

    @property
    def total(self) -> Decimal:
        """Total balance (free + locked)."""
        return self.free + self.locked


@dataclass
class OrderRequest:
    """
    Request to create a new order.

    This dataclass represents the parameters needed to submit an order
    to the Pionex exchange.

    Attributes:
        symbol: Trading pair symbol (e.g., "BTC_USDT")
        side: Order side (BUY or SELL)
        order_type: Type of order (LIMIT or MARKET)
        quantity: Amount of base currency to trade
        price: Price per unit (required for LIMIT orders, ignored for MARKET)
        client_order_id: Optional client-defined order ID for tracking
        time_in_force: How long the order remains active (default: GTC)

    Requirements:
        - 1.4: Submit LIMIT or MARKET orders with symbol, side, type, price, and quantity
    """

    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    price: Decimal | None = None
    client_order_id: str | None = None
    time_in_force: TimeInForce = field(default=TimeInForce.GTC)

    def __post_init__(self) -> None:
        """Validate order request parameters."""
        if self.order_type == OrderType.LIMIT and self.price is None:
            raise ValueError("Price is required for LIMIT orders")
        if self.quantity <= 0:
            raise ValueError("Quantity must be positive")
        if self.price is not None and self.price <= 0:
            raise ValueError("Price must be positive")

    def to_api_params(self) -> dict[str, Any]:
        """
        Convert to API request parameters.

        Returns:
            Dictionary of parameters for the API request body
        """
        params: dict[str, Any] = {
            "symbol": self.symbol,
            "side": self.side.value,
            "type": self.order_type.value,
            "amount": str(self.quantity),
        }

        if self.price is not None:
            params["price"] = str(self.price)

        if self.client_order_id:
            params["clientOrderId"] = self.client_order_id

        if self.order_type == OrderType.LIMIT:
            params["timeInForce"] = self.time_in_force.value

        return params


@dataclass(frozen=True)
class OrderResponse:
    """
    Response from creating or querying an order.

    This dataclass represents the order information returned by the
    Pionex exchange after creating an order or querying order status.

    Attributes:
        order_id: Unique order identifier assigned by the exchange
        client_order_id: Client-defined order ID (if provided)
        symbol: Trading pair symbol
        side: Order side (BUY or SELL)
        order_type: Type of order (LIMIT or MARKET)
        price: Order price (for LIMIT orders)
        quantity: Original order quantity
        executed_quantity: Amount that has been filled
        status: Current order status
        timestamp: When the order was created

    Requirements:
        - 1.4: Submit LIMIT or MARKET orders to /api/v1/trade/order
    """

    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    executed_quantity: Decimal
    status: OrderStatus
    timestamp: datetime
    client_order_id: str | None = None
    price: Decimal | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> OrderResponse:
        """
        Create an OrderResponse from API response data.

        Args:
            data: Dictionary containing order data from the API

        Returns:
            OrderResponse instance
        """
        # Parse side
        side_str = data.get("side", "BUY").upper()
        side = OrderSide.BUY if side_str == "BUY" else OrderSide.SELL

        # Parse order type
        type_str = data.get("type", "LIMIT").upper()
        order_type = OrderType.MARKET if type_str == "MARKET" else OrderType.LIMIT

        # Parse status
        status_str = data.get("status", "NEW").upper()
        try:
            status = OrderStatus(status_str)
        except ValueError:
            status = OrderStatus.NEW

        # Parse timestamp
        timestamp_ms = data.get("timestamp", data.get("time", data.get("createTime", 0)))
        if timestamp_ms:
            timestamp = datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=UTC)
        else:
            timestamp = datetime.now(tz=UTC)

        # Parse price (may be None for MARKET orders)
        price_str = data.get("price")
        price = Decimal(str(price_str)) if price_str else None

        return cls(
            order_id=str(data.get("orderId", data.get("id", ""))),
            client_order_id=data.get("clientOrderId"),
            symbol=data.get("symbol", ""),
            side=side,
            order_type=order_type,
            price=price,
            quantity=Decimal(
                str(data.get("amount", data.get("origQty", data.get("quantity", "0"))))
            ),
            executed_quantity=Decimal(
                str(
                    data.get(
                        "filledAmount", data.get("executedQty", data.get("filledQuantity", "0"))
                    )
                )
            ),
            status=status,
            timestamp=timestamp,
        )


@dataclass(frozen=True)
class CancelOrderResponse:
    """
    Response from canceling an order.

    Attributes:
        order_id: The ID of the canceled order
        symbol: Trading pair symbol
        status: Final status of the order (should be CANCELED)
        success: Whether the cancellation was successful
    """

    order_id: str
    symbol: str
    status: OrderStatus
    success: bool

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], order_id: str, symbol: str
    ) -> CancelOrderResponse:
        """
        Create a CancelOrderResponse from API response data.

        Args:
            data: Dictionary containing response data from the API
            order_id: The order ID that was requested to be canceled
            symbol: The trading pair symbol

        Returns:
            CancelOrderResponse instance
        """
        # Parse status
        status_str = data.get("status", "CANCELED").upper()
        try:
            status = OrderStatus(status_str)
        except ValueError:
            status = OrderStatus.CANCELED

        return cls(
            order_id=str(data.get("orderId", order_id)),
            symbol=data.get("symbol", symbol),
            status=status,
            success=True,
        )


@dataclass(frozen=True)
class PionexError:
    """
    Structured error from Pionex API.

    Attributes:
        status_code: HTTP status code
        error_code: Pionex-specific error code (if available)
        message: Human-readable error message
        is_retryable: Whether this error can be retried
        retry_after: Seconds to wait before retry (for rate limits)
        raw_response: The raw response data for debugging
    """

    status_code: int
    error_code: int | None
    message: str
    is_retryable: bool
    retry_after: int | None = None
    raw_response: dict[str, Any] | None = None

    @classmethod
    def from_response(
        cls,
        status_code: int,
        response_data: dict[str, Any] | None = None,
        retry_after: int | None = None,
    ) -> PionexError:
        """
        Create a PionexError from an API response.

        Args:
            status_code: HTTP status code
            response_data: Parsed JSON response body
            retry_after: Value from Retry-After header (if present)

        Returns:
            PionexError instance with appropriate retry eligibility
        """
        error_code = None
        message = "Unknown error"

        if response_data:
            error_code = response_data.get("code")
            message = response_data.get("message", response_data.get("msg", "Unknown error"))

        # Determine if error is retryable
        # 429 = Rate limited, 5xx = Server errors (retryable)
        # 4xx (except 429) = Client errors (not retryable)
        is_retryable = status_code == 429 or status_code >= 500

        return cls(
            status_code=status_code,
            error_code=error_code,
            message=message,
            is_retryable=is_retryable,
            retry_after=retry_after,
            raw_response=response_data,
        )


class PionexAPIError(Exception):
    """
    Exception raised when a Pionex API request fails.

    Attributes:
        error: The structured PionexError with details
    """

    def __init__(self, error: PionexError) -> None:
        self.error = error
        super().__init__(f"Pionex API Error [{error.status_code}]: {error.message}")


# =========================================================================
# Extended Order and Trade Models
# =========================================================================


class OrderDetailStatus(Enum):
    """Status of an order in the extended order detail response."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"


class FillRole(Enum):
    """Role in a trade execution (maker or taker)."""

    TAKER = "TAKER"
    MAKER = "MAKER"


@dataclass(frozen=True)
class OrderDetail:
    """
    Extended order information from Pionex API.

    This model contains all fields returned by the order query endpoints
    including GET /api/v1/trade/order and GET /api/v1/trade/openOrders.

    Attributes:
        order_id: Unique order identifier assigned by the exchange
        symbol: Trading pair symbol (e.g., "BTC_USDT")
        order_type: Type of order (LIMIT or MARKET)
        side: Order side (BUY or SELL)
        price: Order price
        size: Order size in base currency
        amount: Order amount in quote currency (for market buy orders)
        filled_size: Amount of base currency that has been filled
        filled_amount: Amount of quote currency that has been filled
        fee: Total fee paid
        fee_coin: Currency in which fee was paid
        status: Order status (OPEN or CLOSED)
        ioc: Whether this is an Immediate-Or-Cancel order
        client_order_id: Client-defined order ID (if provided)
        source: Order source (MANUAL or API)
        create_time: When the order was created
        update_time: When the order was last updated

    Requirements:
        - 1.7: Order response includes all fields
    """

    order_id: int
    symbol: str
    order_type: OrderType
    side: OrderSide
    price: Decimal
    size: Decimal
    amount: Decimal | None
    filled_size: Decimal
    filled_amount: Decimal
    fee: Decimal
    fee_coin: str
    status: OrderDetailStatus
    ioc: bool
    client_order_id: str | None
    source: str
    create_time: datetime
    update_time: datetime

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> OrderDetail:
        """
        Create an OrderDetail from API response data.

        Args:
            data: Dictionary containing order data from the API

        Returns:
            OrderDetail instance
        """
        # Parse side
        side_str = data.get("side", "BUY").upper()
        side = OrderSide.BUY if side_str == "BUY" else OrderSide.SELL

        # Parse order type
        type_str = data.get("type", "LIMIT").upper()
        order_type = OrderType.MARKET if type_str == "MARKET" else OrderType.LIMIT

        # Parse status
        status_str = data.get("status", "OPEN").upper()
        try:
            status = OrderDetailStatus(status_str)
        except ValueError:
            status = OrderDetailStatus.OPEN

        # Parse timestamps
        create_time_ms = data.get("createTime", 0)
        update_time_ms = data.get("updateTime", create_time_ms)
        create_time = datetime.fromtimestamp(int(create_time_ms) / 1000, tz=UTC)
        update_time = datetime.fromtimestamp(int(update_time_ms) / 1000, tz=UTC)

        # Parse amount (may be None for non-market-buy orders)
        amount_str = data.get("amount")
        amount = Decimal(str(amount_str)) if amount_str else None

        return cls(
            order_id=int(data.get("orderId", 0)),
            symbol=data.get("symbol", ""),
            order_type=order_type,
            side=side,
            price=Decimal(str(data.get("price", "0"))),
            size=Decimal(str(data.get("size", "0"))),
            amount=amount,
            filled_size=Decimal(str(data.get("filledSize", "0"))),
            filled_amount=Decimal(str(data.get("filledAmount", "0"))),
            fee=Decimal(str(data.get("fee", "0"))),
            fee_coin=data.get("feeCoin", ""),
            status=status,
            ioc=data.get("IOC", False),
            client_order_id=data.get("clientOrderId"),
            source=data.get("source", "API"),
            create_time=create_time,
            update_time=update_time,
        )


@dataclass(frozen=True)
class Fill:
    """
    Trade execution record.

    Represents a single fill (trade execution) from the Pionex API.
    Fills are created when orders are matched and executed.

    Attributes:
        id: Unique fill identifier
        order_id: ID of the order that was filled
        symbol: Trading pair symbol
        side: Trade side (BUY or SELL)
        role: Role in the trade (TAKER or MAKER)
        price: Execution price
        size: Execution size in base currency
        fee: Fee paid for this fill
        fee_coin: Currency in which fee was paid
        timestamp: When the fill occurred

    Requirements:
        - 2.3: Fill response includes all fields
    """

    id: int
    order_id: int
    symbol: str
    side: OrderSide
    role: FillRole
    price: Decimal
    size: Decimal
    fee: Decimal
    fee_coin: str
    timestamp: datetime

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> Fill:
        """
        Create a Fill from API response data.

        Args:
            data: Dictionary containing fill data from the API

        Returns:
            Fill instance
        """
        # Parse side
        side_str = data.get("side", "BUY").upper()
        side = OrderSide.BUY if side_str == "BUY" else OrderSide.SELL

        # Parse role
        role_str = data.get("role", "TAKER").upper()
        try:
            role = FillRole(role_str)
        except ValueError:
            role = FillRole.TAKER

        # Parse timestamp
        timestamp_ms = data.get("timestamp", 0)
        timestamp = datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=UTC)

        return cls(
            id=int(data.get("id", 0)),
            order_id=int(data.get("orderId", 0)),
            symbol=data.get("symbol", ""),
            side=side,
            role=role,
            price=Decimal(str(data.get("price", "0"))),
            size=Decimal(str(data.get("size", "0"))),
            fee=Decimal(str(data.get("fee", "0"))),
            fee_coin=data.get("feeCoin", ""),
            timestamp=timestamp,
        )


@dataclass(frozen=True)
class Ticker24hr:
    """
    24-hour rolling window price statistics.

    Contains price and volume statistics for a trading pair over
    the last 24 hours.

    Attributes:
        symbol: Trading pair symbol
        time: Timestamp of the ticker data
        open: Opening price (24h ago)
        close: Current/closing price
        high: Highest price in 24h
        low: Lowest price in 24h
        volume: Trading volume in base currency
        amount: Trading volume in quote currency
        count: Number of trades in 24h

    Requirements:
        - 3.3: 24hr ticker includes all fields and change calculation
    """

    symbol: str
    time: datetime
    open: Decimal
    close: Decimal
    high: Decimal
    low: Decimal
    volume: Decimal
    amount: Decimal
    count: int

    @property
    def change_percent(self) -> float:
        """
        Calculate 24hr price change percentage.

        Returns:
            Price change as a percentage (e.g., 2.5 for +2.5%)
        """
        if self.open == 0:
            return 0.0
        return float((self.close - self.open) / self.open * 100)

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> Ticker24hr:
        """
        Create a Ticker24hr from API response data.

        Args:
            data: Dictionary containing ticker data from the API

        Returns:
            Ticker24hr instance
        """
        # Parse timestamp
        time_ms = data.get("time", 0)
        time = datetime.fromtimestamp(int(time_ms) / 1000, tz=UTC)

        return cls(
            symbol=data.get("symbol", ""),
            time=time,
            open=Decimal(str(data.get("open", "0"))),
            close=Decimal(str(data.get("close", "0"))),
            high=Decimal(str(data.get("high", "0"))),
            low=Decimal(str(data.get("low", "0"))),
            volume=Decimal(str(data.get("volume", "0"))),
            amount=Decimal(str(data.get("amount", "0"))),
            count=int(data.get("count", 0)),
        )


@dataclass(frozen=True)
class BookTicker:
    """
    Best bid/ask prices.

    Contains the current best bid and ask prices and quantities
    for a trading pair.

    Attributes:
        symbol: Trading pair symbol
        bid_price: Best bid price
        bid_size: Size at best bid
        ask_price: Best ask price
        ask_size: Size at best ask
        timestamp: When this data was captured

    Requirements:
        - 3.4: Book ticker includes all fields and spread calculation
    """

    symbol: str
    bid_price: Decimal
    bid_size: Decimal
    ask_price: Decimal
    ask_size: Decimal
    timestamp: datetime

    @property
    def spread(self) -> Decimal:
        """
        Calculate bid-ask spread.

        Returns:
            The difference between ask and bid prices
        """
        return self.ask_price - self.bid_price

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> BookTicker:
        """
        Create a BookTicker from API response data.

        Args:
            data: Dictionary containing book ticker data from the API

        Returns:
            BookTicker instance
        """
        # Parse timestamp
        timestamp_ms = data.get("timestamp", data.get("time", 0))
        timestamp = datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=UTC)

        return cls(
            symbol=data.get("symbol", ""),
            bid_price=Decimal(str(data.get("bidPrice", "0"))),
            bid_size=Decimal(str(data.get("bidSize", "0"))),
            ask_price=Decimal(str(data.get("askPrice", "0"))),
            ask_size=Decimal(str(data.get("askSize", "0"))),
            timestamp=timestamp,
        )


@dataclass
class MassOrderRequest:
    """
    Request for batch order creation.

    Used to submit multiple orders in a single API call to
    POST /api/v1/trade/massOrder.

    Attributes:
        side: Order side (BUY or SELL)
        price: Order price
        size: Order size in base currency
        client_order_id: Optional client-defined order ID

    Requirements:
        - 1.5: Mass order request parameters
    """

    side: OrderSide
    price: Decimal
    size: Decimal
    client_order_id: str | None = None

    def to_api_params(self) -> dict[str, Any]:
        """
        Convert to API request parameters.

        Returns:
            Dictionary of parameters for the API request
        """
        params: dict[str, Any] = {
            "side": self.side.value,
            "price": str(self.price),
            "size": str(self.size),
        }
        if self.client_order_id:
            params["clientOrderId"] = self.client_order_id
        return params


@dataclass(frozen=True)
class MassOrderResult:
    """
    Result from batch order creation.

    Represents the result of a single order in a mass order request.

    Attributes:
        order_id: Unique order identifier assigned by the exchange
        client_order_id: Client-defined order ID (if provided)

    Requirements:
        - 1.5: Mass order result fields
    """

    order_id: int
    client_order_id: str | None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> MassOrderResult:
        """
        Create a MassOrderResult from API response data.

        Args:
            data: Dictionary containing order result from the API

        Returns:
            MassOrderResult instance
        """
        return cls(
            order_id=int(data.get("orderId", 0)),
            client_order_id=data.get("clientOrderId"),
        )


# =========================================================================
# Bot Management Models
# =========================================================================


@dataclass
class GridBotParams:
    """
    Parameters for creating a Grid trading bot.

    Grid bots place buy and sell orders at regular price intervals within
    a defined price range, profiting from price oscillations.

    Attributes:
        symbol: Trading pair symbol (e.g., "BTC_USDT")
        lower_price: Lower bound of the grid price range
        upper_price: Upper bound of the grid price range
        grid_count: Number of grid levels (orders) to place
        investment: Total investment amount in quote currency

    Requirements:
        - 10.3: Create a new Grid Bot with calculated price range and grid count
    """

    symbol: str
    lower_price: float
    upper_price: float
    grid_count: int
    investment: Decimal

    def __post_init__(self) -> None:
        """Validate grid bot parameters."""
        if self.lower_price <= 0:
            raise ValueError("Lower price must be positive")
        if self.upper_price <= 0:
            raise ValueError("Upper price must be positive")
        if self.lower_price >= self.upper_price:
            raise ValueError("Lower price must be less than upper price")
        if self.grid_count < 2:
            raise ValueError("Grid count must be at least 2")
        if self.investment <= 0:
            raise ValueError("Investment must be positive")

    def to_api_params(self) -> dict[str, Any]:
        """
        Convert to API request parameters.

        Returns:
            Dictionary of parameters for the API request body
        """
        return {
            "symbol": self.symbol,
            "lowerPrice": str(self.lower_price),
            "upperPrice": str(self.upper_price),
            "gridCount": self.grid_count,
            "investment": str(self.investment),
        }


@dataclass
class DCABotParams:
    """
    Parameters for creating a DCA (Dollar Cost Averaging) bot.

    DCA bots automatically purchase a fixed amount of cryptocurrency
    at regular intervals, averaging the purchase price over time.

    Attributes:
        symbol: Trading pair symbol (e.g., "BTC_USDT")
        investment_per_order: Amount to invest per order in quote currency
        interval_hours: Hours between each purchase
        total_investment: Total investment budget in quote currency

    Requirements:
        - 10.4: Create a new DCA Bot with calculated investment intervals
    """

    symbol: str
    investment_per_order: Decimal
    interval_hours: int
    total_investment: Decimal

    def __post_init__(self) -> None:
        """Validate DCA bot parameters."""
        if self.investment_per_order <= 0:
            raise ValueError("Investment per order must be positive")
        if self.interval_hours < 1:
            raise ValueError("Interval hours must be at least 1")
        if self.total_investment <= 0:
            raise ValueError("Total investment must be positive")
        if self.investment_per_order > self.total_investment:
            raise ValueError("Investment per order cannot exceed total investment")

    def to_api_params(self) -> dict[str, Any]:
        """
        Convert to API request parameters.

        Returns:
            Dictionary of parameters for the API request body
        """
        return {
            "symbol": self.symbol,
            "investmentPerOrder": str(self.investment_per_order),
            "intervalHours": self.interval_hours,
            "totalInvestment": str(self.total_investment),
        }


@dataclass
class BotInfo:
    """
    Information about a trading bot.

    Represents the current state and configuration of a trading bot
    on the Pionex exchange.

    Attributes:
        bot_id: Unique identifier for the bot
        bot_type: Type of bot (GRID, DCA, INFINITY_GRID, FUTURES_GRID)
        symbol: Trading pair symbol
        status: Current bot status (ACTIVE, STOPPED, ERROR)
        invested: Total amount invested in the bot
        current_value: Current value of the bot's positions
        pnl: Profit and loss in quote currency
        pnl_percent: Profit and loss as a percentage
        params: Bot-specific parameters (GridBotParams or DCABotParams)
        created_at: When the bot was created (optional)

    Requirements:
        - 10.1: Retrieve all active bots from the account
        - 10.2: Retrieve bot type, trading pair, status, invested amount,
                current P&L, and configuration parameters for each bot
    """

    bot_id: str
    bot_type: BotType
    symbol: str
    status: BotStatus
    invested: Decimal
    current_value: Decimal
    pnl: Decimal
    pnl_percent: float
    params: GridBotParams | DCABotParams | None = None
    created_at: datetime | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> BotInfo:
        """
        Create a BotInfo from API response data.

        Args:
            data: Dictionary containing bot data from the API

        Returns:
            BotInfo instance
        """
        # Parse bot type
        bot_type_str = data.get("botType", data.get("type", "GRID")).upper()
        try:
            bot_type = BotType(bot_type_str)
        except ValueError:
            # Default to GRID if unknown type
            bot_type = BotType.GRID

        # Parse status
        status_str = data.get("status", "ACTIVE").upper()
        try:
            status = BotStatus(status_str)
        except ValueError:
            status = BotStatus.ACTIVE

        # Parse amounts
        invested = Decimal(str(data.get("invested", data.get("investment", "0"))))
        current_value = Decimal(str(data.get("currentValue", data.get("value", invested))))
        pnl = Decimal(str(data.get("pnl", data.get("profit", "0"))))
        pnl_percent = float(data.get("pnlPercent", data.get("profitPercent", data.get("roi", 0))))

        # Parse bot-specific params
        params: GridBotParams | DCABotParams | None = None
        if (
            bot_type == BotType.GRID
            or bot_type == BotType.INFINITY_GRID
            or bot_type == BotType.FUTURES_GRID
        ):
            # Grid bot params
            lower_price = data.get("lowerPrice", data.get("lower_price"))
            upper_price = data.get("upperPrice", data.get("upper_price"))
            grid_count = data.get("gridCount", data.get("grid_count"))
            if lower_price and upper_price and grid_count:
                try:
                    params = GridBotParams(
                        symbol=data.get("symbol", ""),
                        lower_price=float(lower_price),
                        upper_price=float(upper_price),
                        grid_count=int(grid_count),
                        investment=invested,
                    )
                except (ValueError, TypeError):
                    pass
        elif bot_type == BotType.DCA:
            # DCA bot params
            investment_per_order = data.get("investmentPerOrder", data.get("investment_per_order"))
            interval_hours = data.get("intervalHours", data.get("interval_hours"))
            total_investment = data.get("totalInvestment", data.get("total_investment"))
            if investment_per_order and interval_hours:
                try:
                    params = DCABotParams(
                        symbol=data.get("symbol", ""),
                        investment_per_order=Decimal(str(investment_per_order)),
                        interval_hours=int(interval_hours),
                        total_investment=Decimal(str(total_investment))
                        if total_investment
                        else invested,
                    )
                except (ValueError, TypeError):
                    pass

        # Parse created_at timestamp
        created_at = None
        timestamp_ms = data.get("createdAt", data.get("createTime", data.get("timestamp")))
        if timestamp_ms:
            try:
                created_at = datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=UTC)
            except (ValueError, TypeError):
                pass

        return cls(
            bot_id=str(data.get("botId", data.get("id", ""))),
            bot_type=bot_type,
            symbol=data.get("symbol", ""),
            status=status,
            invested=invested,
            current_value=current_value,
            pnl=pnl,
            pnl_percent=pnl_percent,
            params=params,
            created_at=created_at,
        )
