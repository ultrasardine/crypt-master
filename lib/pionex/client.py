"""
Pionex API Client.

This module provides an async HTTP client for interacting with the Pionex
exchange API. It handles authentication, request signing, error handling,
and retry logic for transient failures.

Requirements:
- 1.2: Retrieve available SPOT and PERP symbols from /api/v1/common/symbols
- 1.5: Retrieve recent trades for a symbol from /api/v1/market/trades
- 1.6: Retrieve bid/ask depth from /api/v1/market/depth
- 1.7: Return structured errors with status code, message, and retry eligibility
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from lib.pionex.auth import PionexAuthenticator
from lib.pionex.models import (
    Balance,
    BotInfo,
    BotStatus,
    BotType,
    Candle,
    CancelOrderResponse,
    DCABotParams,
    GridBotParams,
    OrderBook,
    OrderBookLevel,
    OrderRequest,
    OrderResponse,
    OrderSide,
    PionexAPIError,
    PionexError,
    Symbol,
    SymbolType,
    Trade,
)


logger = logging.getLogger(__name__)


# Pionex API base URL
PIONEX_API_BASE_URL = "https://api.pionex.com"

# Default timeout for API requests (seconds)
DEFAULT_TIMEOUT = 30.0

# Retry configuration
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 1.0  # seconds
MAX_RETRY_DELAY = 10.0  # seconds


class PionexClient:
    """
    Async HTTP client for Pionex exchange API.
    
    This client provides methods for:
    - Market data: symbols, candles, order book depth, trades
    - Account data: balances (to be implemented)
    - Trading: orders (to be implemented)
    - Bot management: list, create, stop bots (to be implemented)
    
    The client handles:
    - HMAC-SHA256 authentication for all requests
    - Automatic retry with exponential backoff for transient failures
    - Structured error responses with retry eligibility
    
    Example:
        >>> async with PionexClient(api_key="key", api_secret="secret") as client:
        ...     symbols = await client.get_symbols()
        ...     candles = await client.get_candles("BTC_USDT", "1H")
    
    Attributes:
        base_url: The Pionex API base URL
        timeout: Request timeout in seconds
    """
    
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = PIONEX_API_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """
        Initialize the Pionex client.
        
        Args:
            api_key: Pionex API key
            api_secret: Pionex API secret for signing requests
            base_url: API base URL (default: production)
            timeout: Request timeout in seconds
            
        Raises:
            ValueError: If api_key or api_secret is empty
        """
        self._authenticator = PionexAuthenticator(api_key, api_secret)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
    
    async def __aenter__(self) -> PionexClient:
        """Enter async context manager."""
        await self._ensure_client()
        return self
    
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit async context manager."""
        await self.close()
    
    async def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure HTTP client is initialized."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
        return self._client
    
    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        """
        Make an HTTP request to the Pionex API.
        
        This method handles:
        - Authentication (signing requests)
        - Retry logic with exponential backoff
        - Error parsing and structured error responses
        
        Args:
            method: HTTP method (GET, POST, DELETE)
            endpoint: API endpoint path (e.g., "/api/v1/common/symbols")
            params: Query parameters
            data: Request body for POST requests
            authenticated: Whether to sign the request
            
        Returns:
            Parsed JSON response data
            
        Raises:
            PionexAPIError: If the request fails after all retries
        """
        client = await self._ensure_client()
        
        # Prepare request parameters
        request_params = dict(params) if params else {}
        headers: dict[str, str] = {}
        
        if authenticated:
            auth_headers, request_params = self._authenticator.sign_request(request_params)
            headers.update(auth_headers)
        
        last_error: PionexError | None = None
        retry_delay = INITIAL_RETRY_DELAY
        
        for attempt in range(MAX_RETRIES + 1):
            try:
                if method.upper() == "GET":
                    response = await client.get(
                        endpoint,
                        params=request_params,
                        headers=headers,
                    )
                elif method.upper() == "POST":
                    response = await client.post(
                        endpoint,
                        params=request_params,
                        json=data,
                        headers=headers,
                    )
                elif method.upper() == "DELETE":
                    response = await client.delete(
                        endpoint,
                        params=request_params,
                        headers=headers,
                    )
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                # Parse response
                response_data = response.json() if response.content else {}
                
                # Check for success
                if response.is_success:
                    # Pionex API returns result in "data" field on success
                    # with "result" being True
                    if response_data.get("result") is True:
                        return response_data.get("data", {})
                    elif response_data.get("result") is False:
                        # API returned an error in the response body
                        error = PionexError.from_response(
                            status_code=response.status_code,
                            response_data=response_data,
                        )
                        raise PionexAPIError(error)
                    else:
                        # Some endpoints may not have "result" field
                        return response_data
                
                # Handle error response
                retry_after = None
                if "Retry-After" in response.headers:
                    try:
                        retry_after = int(response.headers["Retry-After"])
                    except ValueError:
                        pass
                
                error = PionexError.from_response(
                    status_code=response.status_code,
                    response_data=response_data,
                    retry_after=retry_after,
                )
                
                # Check if we should retry
                if error.is_retryable and attempt < MAX_RETRIES:
                    last_error = error
                    wait_time = error.retry_after if error.retry_after else retry_delay
                    logger.warning(
                        f"Retryable error on attempt {attempt + 1}/{MAX_RETRIES + 1}: "
                        f"{error.message}. Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                    retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)
                    continue
                
                raise PionexAPIError(error)
                
            except httpx.TimeoutException as e:
                last_error = PionexError(
                    status_code=0,
                    error_code=None,
                    message=f"Request timeout: {e}",
                    is_retryable=True,
                )
                if attempt < MAX_RETRIES:
                    logger.warning(
                        f"Timeout on attempt {attempt + 1}/{MAX_RETRIES + 1}. "
                        f"Retrying in {retry_delay}s..."
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)
                    continue
                raise PionexAPIError(last_error) from e
                
            except httpx.RequestError as e:
                last_error = PionexError(
                    status_code=0,
                    error_code=None,
                    message=f"Request error: {e}",
                    is_retryable=True,
                )
                if attempt < MAX_RETRIES:
                    logger.warning(
                        f"Request error on attempt {attempt + 1}/{MAX_RETRIES + 1}: {e}. "
                        f"Retrying in {retry_delay}s..."
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)
                    continue
                raise PionexAPIError(last_error) from e
        
        # Should not reach here, but just in case
        if last_error:
            raise PionexAPIError(last_error)
        raise PionexAPIError(PionexError(
            status_code=0,
            error_code=None,
            message="Unknown error after retries",
            is_retryable=False,
        ))
    
    # =========================================================================
    # Market Data Methods
    # =========================================================================
    
    async def get_symbols(self) -> list[Symbol]:
        """
        Retrieve available trading symbols from Pionex.
        
        This method fetches all SPOT and PERP symbols available for trading.
        
        Returns:
            List of Symbol objects with trading pair information
            
        Raises:
            PionexAPIError: If the API request fails
            
        Requirements:
            - 1.2: Retrieve available SPOT and PERP symbols from /api/v1/common/symbols
        """
        response = await self._request(
            method="GET",
            endpoint="/api/v1/common/symbols",
            authenticated=False,  # Public endpoint
        )
        
        symbols: list[Symbol] = []
        
        # Parse symbols from response
        symbols_data = response.get("symbols", [])
        for item in symbols_data:
            try:
                # Determine symbol type
                symbol_type_str = item.get("type", "SPOT").upper()
                symbol_type = SymbolType.PERP if symbol_type_str == "PERP" else SymbolType.SPOT
                
                symbol = Symbol(
                    symbol=item["symbol"],
                    base_currency=item.get("baseCurrency", item.get("base", "")),
                    quote_currency=item.get("quoteCurrency", item.get("quote", "")),
                    symbol_type=symbol_type,
                    base_precision=int(item.get("basePrecision", item.get("amountPrecision", 8))),
                    quote_precision=int(item.get("quotePrecision", item.get("pricePrecision", 8))),
                    min_amount=Decimal(str(item.get("minAmount", item.get("minQty", "0")))),
                    min_notional=Decimal(str(item.get("minNotional", item.get("minValue", "0")))),
                    is_active=item.get("enable", item.get("isActive", True)),
                )
                symbols.append(symbol)
            except (KeyError, ValueError) as e:
                logger.warning(f"Failed to parse symbol: {item}. Error: {e}")
                continue
        
        return symbols
    
    async def get_candles(
        self,
        symbol: str,
        interval: str,
        limit: int = 100,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[Candle]:
        """
        Retrieve candlestick (OHLCV) data for a symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., "BTC_USDT")
            interval: Candle interval (e.g., "1M", "5M", "15M", "30M", "1H", "4H", "1D")
            limit: Maximum number of candles to return (default: 100, max: 1000)
            start_time: Start time in milliseconds (optional)
            end_time: End time in milliseconds (optional)
            
        Returns:
            List of Candle objects with OHLCV data, sorted by timestamp ascending
            
        Raises:
            PionexAPIError: If the API request fails
        """
        params: dict[str, Any] = {
            "symbol": symbol,
            "interval": interval,
            "limit": min(limit, 1000),
        }
        
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        
        response = await self._request(
            method="GET",
            endpoint="/api/v1/market/klines",
            params=params,
            authenticated=False,  # Public endpoint
        )
        
        candles: list[Candle] = []
        
        # Parse candles from response
        klines = response.get("klines", [])
        for item in klines:
            try:
                # Pionex returns candles as arrays or objects
                if isinstance(item, list):
                    # Array format: [timestamp, open, high, low, close, volume]
                    candle = Candle(
                        timestamp=datetime.fromtimestamp(int(item[0]) / 1000, tz=timezone.utc),
                        open=float(item[1]),
                        high=float(item[2]),
                        low=float(item[3]),
                        close=float(item[4]),
                        volume=float(item[5]),
                    )
                else:
                    # Object format
                    candle = Candle(
                        timestamp=datetime.fromtimestamp(
                            int(item.get("time", item.get("timestamp", 0))) / 1000,
                            tz=timezone.utc,
                        ),
                        open=float(item.get("open", 0)),
                        high=float(item.get("high", 0)),
                        low=float(item.get("low", 0)),
                        close=float(item.get("close", 0)),
                        volume=float(item.get("volume", item.get("amount", 0))),
                    )
                candles.append(candle)
            except (KeyError, ValueError, IndexError) as e:
                logger.warning(f"Failed to parse candle: {item}. Error: {e}")
                continue
        
        # Sort by timestamp ascending
        candles.sort(key=lambda c: c.timestamp)
        
        return candles
    
    async def get_depth(
        self,
        symbol: str,
        limit: int = 20,
    ) -> OrderBook:
        """
        Retrieve order book depth for a symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., "BTC_USDT")
            limit: Number of price levels to return (default: 20, max: 100)
            
        Returns:
            OrderBook with bid and ask levels
            
        Raises:
            PionexAPIError: If the API request fails
            
        Requirements:
            - 1.6: Retrieve bid/ask depth from /api/v1/market/depth
        """
        params: dict[str, Any] = {
            "symbol": symbol,
            "limit": min(limit, 100),
        }
        
        response = await self._request(
            method="GET",
            endpoint="/api/v1/market/depth",
            params=params,
            authenticated=False,  # Public endpoint
        )
        
        # Parse bids (buy orders)
        bids: list[OrderBookLevel] = []
        for item in response.get("bids", []):
            try:
                if isinstance(item, list):
                    # Array format: [price, quantity]
                    bids.append(OrderBookLevel(
                        price=Decimal(str(item[0])),
                        quantity=Decimal(str(item[1])),
                    ))
                else:
                    # Object format
                    bids.append(OrderBookLevel(
                        price=Decimal(str(item.get("price", 0))),
                        quantity=Decimal(str(item.get("quantity", item.get("amount", 0)))),
                    ))
            except (ValueError, IndexError) as e:
                logger.warning(f"Failed to parse bid: {item}. Error: {e}")
                continue
        
        # Parse asks (sell orders)
        asks: list[OrderBookLevel] = []
        for item in response.get("asks", []):
            try:
                if isinstance(item, list):
                    # Array format: [price, quantity]
                    asks.append(OrderBookLevel(
                        price=Decimal(str(item[0])),
                        quantity=Decimal(str(item[1])),
                    ))
                else:
                    # Object format
                    asks.append(OrderBookLevel(
                        price=Decimal(str(item.get("price", 0))),
                        quantity=Decimal(str(item.get("quantity", item.get("amount", 0)))),
                    ))
            except (ValueError, IndexError) as e:
                logger.warning(f"Failed to parse ask: {item}. Error: {e}")
                continue
        
        # Get timestamp from response or use current time
        timestamp_ms = response.get("timestamp", response.get("time"))
        if timestamp_ms:
            timestamp = datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=timezone.utc)
        else:
            timestamp = datetime.now(tz=timezone.utc)
        
        return OrderBook(
            symbol=symbol,
            bids=bids,
            asks=asks,
            timestamp=timestamp,
        )
    
    async def get_trades(
        self,
        symbol: str,
        limit: int = 100,
    ) -> list[Trade]:
        """
        Retrieve recent trades for a symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., "BTC_USDT")
            limit: Maximum number of trades to return (default: 100, max: 500)
            
        Returns:
            List of Trade objects, sorted by timestamp descending (most recent first)
            
        Raises:
            PionexAPIError: If the API request fails
            
        Requirements:
            - 1.5: Retrieve recent trades for a symbol from /api/v1/market/trades
        """
        params: dict[str, Any] = {
            "symbol": symbol,
            "limit": min(limit, 500),
        }
        
        response = await self._request(
            method="GET",
            endpoint="/api/v1/market/trades",
            params=params,
            authenticated=False,  # Public endpoint
        )
        
        trades: list[Trade] = []
        
        # Parse trades from response
        trades_data = response.get("trades", [])
        for item in trades_data:
            try:
                # Determine trade side
                side_str = str(item.get("side", item.get("isBuyerMaker", ""))).upper()
                if side_str in ("BUY", "TRUE", "1"):
                    side = OrderSide.BUY
                elif side_str in ("SELL", "FALSE", "0"):
                    side = OrderSide.SELL
                else:
                    # Default to BUY if unknown
                    side = OrderSide.BUY
                
                # Get timestamp
                timestamp_ms = item.get("timestamp", item.get("time", 0))
                timestamp = datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=timezone.utc)
                
                trade = Trade(
                    trade_id=str(item.get("id", item.get("tradeId", ""))),
                    symbol=symbol,
                    price=Decimal(str(item.get("price", 0))),
                    quantity=Decimal(str(item.get("quantity", item.get("amount", item.get("size", 0))))),
                    side=side,
                    timestamp=timestamp,
                )
                trades.append(trade)
            except (KeyError, ValueError) as e:
                logger.warning(f"Failed to parse trade: {item}. Error: {e}")
                continue
        
        # Sort by timestamp descending (most recent first)
        trades.sort(key=lambda t: t.timestamp, reverse=True)
        
        return trades
    
    # =========================================================================
    # Account Methods
    # =========================================================================
    
    async def get_balances(self) -> list[Balance]:
        """
        Retrieve all currency balances from the account.
        
        This method fetches the current balance for all currencies in the
        user's Pionex account, including both available (free) and locked
        amounts.
        
        Returns:
            List of Balance objects with currency balance information
            
        Raises:
            PionexAPIError: If the API request fails (e.g., authentication error)
            
        Requirements:
            - 1.3: Retrieve all currency balances from /api/v1/account/balance
            
        Example:
            >>> async with PionexClient(api_key="key", api_secret="secret") as client:
            ...     balances = await client.get_balances()
            ...     for balance in balances:
            ...         print(f"{balance.currency}: {balance.free} free, {balance.locked} locked")
        """
        response = await self._request(
            method="GET",
            endpoint="/api/v1/account/balances",
            authenticated=True,  # Requires authentication
        )
        
        balances: list[Balance] = []
        
        # Parse balances from response
        # Pionex returns balances in a "balances" array
        balances_data = response.get("balances", [])
        for item in balances_data:
            try:
                # Parse currency and amounts
                currency = item.get("coin", item.get("currency", item.get("asset", "")))
                
                # Parse free (available) balance
                free_str = item.get("free", item.get("available", item.get("availableBalance", "0")))
                free = Decimal(str(free_str))
                
                # Parse locked balance
                locked_str = item.get("locked", item.get("frozen", item.get("lockedBalance", "0")))
                locked = Decimal(str(locked_str))
                
                # Skip zero balances if both free and locked are zero
                if free == 0 and locked == 0:
                    continue
                
                balance = Balance(
                    currency=currency,
                    free=free,
                    locked=locked,
                )
                balances.append(balance)
            except (KeyError, ValueError, InvalidOperation) as e:
                logger.warning(f"Failed to parse balance: {item}. Error: {e}")
                continue
        
        return balances
    
    # =========================================================================
    # Order Methods
    # =========================================================================
    
    async def create_order(self, order: OrderRequest) -> OrderResponse:
        """
        Create a new order on the Pionex exchange.
        
        This method submits a LIMIT or MARKET order to the exchange.
        For LIMIT orders, both price and quantity are required.
        For MARKET orders, only quantity is required.
        
        Args:
            order: OrderRequest containing order parameters
            
        Returns:
            OrderResponse with the created order details
            
        Raises:
            PionexAPIError: If the API request fails (e.g., insufficient balance,
                invalid symbol, authentication error)
            ValueError: If order parameters are invalid
            
        Requirements:
            - 1.4: Submit LIMIT or MARKET orders with symbol, side, type, price,
                   and quantity to /api/v1/trade/order
            
        Example:
            >>> from decimal import Decimal
            >>> from lib.pionex.models import OrderRequest, OrderSide, OrderType
            >>> 
            >>> async with PionexClient(api_key="key", api_secret="secret") as client:
            ...     # Create a LIMIT buy order
            ...     order = OrderRequest(
            ...         symbol="BTC_USDT",
            ...         side=OrderSide.BUY,
            ...         order_type=OrderType.LIMIT,
            ...         quantity=Decimal("0.001"),
            ...         price=Decimal("30000.00"),
            ...     )
            ...     response = await client.create_order(order)
            ...     print(f"Order created: {response.order_id}")
        """
        # Convert order request to API parameters
        order_params = order.to_api_params()
        
        logger.info(
            f"Creating {order.order_type.value} {order.side.value} order for "
            f"{order.quantity} {order.symbol} at price {order.price}"
        )
        
        response = await self._request(
            method="POST",
            endpoint="/api/v1/trade/order",
            data=order_params,
            authenticated=True,  # Requires authentication
        )
        
        order_response = OrderResponse.from_api_response(response)
        
        logger.info(
            f"Order created successfully: {order_response.order_id} "
            f"(status: {order_response.status.value})"
        )
        
        return order_response
    
    async def cancel_order(
        self,
        symbol: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> CancelOrderResponse:
        """
        Cancel an existing order on the Pionex exchange.
        
        Either order_id or client_order_id must be provided to identify
        the order to cancel.
        
        Args:
            symbol: Trading pair symbol (e.g., "BTC_USDT")
            order_id: Exchange-assigned order ID (optional if client_order_id provided)
            client_order_id: Client-defined order ID (optional if order_id provided)
            
        Returns:
            CancelOrderResponse with the cancellation result
            
        Raises:
            PionexAPIError: If the API request fails (e.g., order not found,
                order already filled, authentication error)
            ValueError: If neither order_id nor client_order_id is provided
            
        Example:
            >>> async with PionexClient(api_key="key", api_secret="secret") as client:
            ...     # Cancel by order ID
            ...     result = await client.cancel_order(
            ...         symbol="BTC_USDT",
            ...         order_id="123456789"
            ...     )
            ...     print(f"Order {result.order_id} canceled: {result.success}")
            ...     
            ...     # Or cancel by client order ID
            ...     result = await client.cancel_order(
            ...         symbol="BTC_USDT",
            ...         client_order_id="my-order-001"
            ...     )
        """
        if not order_id and not client_order_id:
            raise ValueError("Either order_id or client_order_id must be provided")
        
        # Build request parameters
        params: dict[str, Any] = {
            "symbol": symbol,
        }
        
        if order_id:
            params["orderId"] = order_id
        if client_order_id:
            params["clientOrderId"] = client_order_id
        
        identifier = order_id or client_order_id
        logger.info(f"Canceling order {identifier} for {symbol}")
        
        response = await self._request(
            method="DELETE",
            endpoint="/api/v1/trade/order",
            params=params,
            authenticated=True,  # Requires authentication
        )
        
        cancel_response = CancelOrderResponse.from_api_response(
            response,
            order_id=order_id or "",
            symbol=symbol,
        )
        
        logger.info(
            f"Order {cancel_response.order_id} canceled successfully "
            f"(status: {cancel_response.status.value})"
        )
        
        return cancel_response

    # =========================================================================
    # Bot Management Methods
    # =========================================================================
    
    async def list_bots(self) -> list[BotInfo]:
        """
        Retrieve all active bots from the account.
        
        This method fetches all trading bots (Grid, DCA, Infinity Grid, Futures Grid)
        associated with the user's Pionex account.
        
        Returns:
            List of BotInfo objects with bot details
            
        Raises:
            PionexAPIError: If the API request fails (e.g., authentication error)
            
        Requirements:
            - 10.1: Retrieve all active bots (Grid, DCA, Infinity Grid, Futures Grid)
            - 10.2: Retrieve bot type, trading pair, status, invested amount,
                    current P&L, and configuration parameters for each bot
            
        Example:
            >>> async with PionexClient(api_key="key", api_secret="secret") as client:
            ...     bots = await client.list_bots()
            ...     for bot in bots:
            ...         print(f"{bot.bot_type.value} bot on {bot.symbol}: {bot.pnl_percent}% P&L")
        """
        response = await self._request(
            method="GET",
            endpoint="/api/v1/trade/bots",
            authenticated=True,  # Requires authentication
        )
        
        bots: list[BotInfo] = []
        
        # Parse bots from response
        # Response can be a list directly, or have "bots" key, or be grouped by type
        bots_data = response.get("bots", [])
        
        if not bots_data and isinstance(response, dict):
            # Check if bots are grouped by type (gridBots, dcaBots, etc.)
            all_bots: list[dict[str, Any]] = []
            for bot_type_key in ["gridBots", "dcaBots", "infinityGridBots", "futuresGridBots"]:
                all_bots.extend(response.get(bot_type_key, []))
            if all_bots:
                bots_data = all_bots
        
        for item in bots_data:
            try:
                bot = BotInfo.from_api_response(item)
                bots.append(bot)
            except (KeyError, ValueError) as e:
                logger.warning(f"Failed to parse bot: {item}. Error: {e}")
                continue
        
        logger.info(f"Retrieved {len(bots)} bots from account")
        
        return bots
    
    async def create_grid_bot(self, params: GridBotParams) -> BotInfo:
        """
        Create a new Grid trading bot.
        
        Grid bots place buy and sell orders at regular price intervals within
        a defined price range, profiting from price oscillations.
        
        Args:
            params: GridBotParams containing the bot configuration
            
        Returns:
            BotInfo with the created bot details
            
        Raises:
            PionexAPIError: If the API request fails (e.g., insufficient balance,
                invalid parameters, authentication error)
            
        Requirements:
            - 10.3: Create a new Grid Bot with calculated price range and grid count
            
        Example:
            >>> from decimal import Decimal
            >>> from lib.pionex.models import GridBotParams
            >>> 
            >>> async with PionexClient(api_key="key", api_secret="secret") as client:
            ...     params = GridBotParams(
            ...         symbol="BTC_USDT",
            ...         lower_price=30000.0,
            ...         upper_price=40000.0,
            ...         grid_count=10,
            ...         investment=Decimal("1000.00"),
            ...     )
            ...     bot = await client.create_grid_bot(params)
            ...     print(f"Created grid bot: {bot.bot_id}")
        """
        logger.info(
            f"Creating Grid bot for {params.symbol} with range "
            f"[{params.lower_price}, {params.upper_price}], "
            f"{params.grid_count} grids, investment: {params.investment}"
        )
        
        response = await self._request(
            method="POST",
            endpoint="/api/v1/trade/bot/grid",
            data=params.to_api_params(),
            authenticated=True,  # Requires authentication
        )
        
        bot = BotInfo.from_api_response(response)
        
        logger.info(
            f"Grid bot created successfully: {bot.bot_id} "
            f"(status: {bot.status.value})"
        )
        
        return bot
    
    async def create_dca_bot(self, params: DCABotParams) -> BotInfo:
        """
        Create a new DCA (Dollar Cost Averaging) bot.
        
        DCA bots automatically purchase a fixed amount of cryptocurrency
        at regular intervals, averaging the purchase price over time.
        
        Args:
            params: DCABotParams containing the bot configuration
            
        Returns:
            BotInfo with the created bot details
            
        Raises:
            PionexAPIError: If the API request fails (e.g., insufficient balance,
                invalid parameters, authentication error)
            
        Requirements:
            - 10.4: Create a new DCA Bot with calculated investment intervals
            
        Example:
            >>> from decimal import Decimal
            >>> from lib.pionex.models import DCABotParams
            >>> 
            >>> async with PionexClient(api_key="key", api_secret="secret") as client:
            ...     params = DCABotParams(
            ...         symbol="BTC_USDT",
            ...         investment_per_order=Decimal("100.00"),
            ...         interval_hours=24,
            ...         total_investment=Decimal("1000.00"),
            ...     )
            ...     bot = await client.create_dca_bot(params)
            ...     print(f"Created DCA bot: {bot.bot_id}")
        """
        logger.info(
            f"Creating DCA bot for {params.symbol} with "
            f"{params.investment_per_order} per order every {params.interval_hours}h, "
            f"total investment: {params.total_investment}"
        )
        
        response = await self._request(
            method="POST",
            endpoint="/api/v1/trade/bot/dca",
            data=params.to_api_params(),
            authenticated=True,  # Requires authentication
        )
        
        bot = BotInfo.from_api_response(response)
        
        logger.info(
            f"DCA bot created successfully: {bot.bot_id} "
            f"(status: {bot.status.value})"
        )
        
        return bot
    
    async def stop_bot(self, bot_id: str) -> bool:
        """
        Stop an active trading bot.
        
        This method stops the specified bot, closes all open orders,
        and returns funds to the available balance.
        
        Args:
            bot_id: The unique identifier of the bot to stop
            
        Returns:
            True if the bot was successfully stopped
            
        Raises:
            PionexAPIError: If the API request fails (e.g., bot not found,
                bot already stopped, authentication error)
            
        Requirements:
            - 10.5: Stop the bot and realize current positions when trading pair
                    shows unfavorable signals
            - 10.6: Close all open orders and return funds to available balance
            
        Example:
            >>> async with PionexClient(api_key="key", api_secret="secret") as client:
            ...     success = await client.stop_bot("bot_123456")
            ...     if success:
            ...         print("Bot stopped successfully")
        """
        logger.info(f"Stopping bot: {bot_id}")
        
        response = await self._request(
            method="POST",
            endpoint="/api/v1/trade/bot/close",
            data={"botId": bot_id},
            authenticated=True,  # Requires authentication
        )
        
        # Check if stop was successful
        success = response.get("success", response.get("result", True))
        
        if success:
            logger.info(f"Bot {bot_id} stopped successfully")
        else:
            logger.warning(f"Bot {bot_id} stop returned unexpected response: {response}")
        
        return bool(success)
    
    async def get_bot_details(self, bot_id: str) -> BotInfo:
        """
        Get detailed information about a specific bot.
        
        Args:
            bot_id: The unique identifier of the bot
            
        Returns:
            BotInfo with the bot's current state and configuration
            
        Raises:
            PionexAPIError: If the API request fails (e.g., bot not found,
                authentication error)
            
        Requirements:
            - 10.2: Retrieve bot type, trading pair, status, invested amount,
                    current P&L, and configuration parameters
            
        Example:
            >>> async with PionexClient(api_key="key", api_secret="secret") as client:
            ...     bot = await client.get_bot_details("bot_123456")
            ...     print(f"Bot {bot.bot_id}: {bot.status.value}, P&L: {bot.pnl}")
        """
        logger.info(f"Getting details for bot: {bot_id}")
        
        response = await self._request(
            method="GET",
            endpoint="/api/v1/trade/bot",
            params={"botId": bot_id},
            authenticated=True,  # Requires authentication
        )
        
        bot = BotInfo.from_api_response(response)
        
        logger.info(
            f"Retrieved bot details: {bot.bot_id} "
            f"(type: {bot.bot_type.value}, status: {bot.status.value})"
        )
        
        return bot
