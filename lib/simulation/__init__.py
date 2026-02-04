"""
Dry-Run Simulation Library.

This module provides a dry-run simulator for testing trading strategies
without risking real funds. It maintains a simulated balance ledger,
simulates order and bot operations, and tracks P&L.

Requirements:
- 2.1: Simulate all order operations without calling real Pionex order endpoint
- 2.2: Maintain a simulated balance ledger tracking virtual positions
- 2.3: Update simulated balance ledger as if orders filled at current market price
- 2.4: Log all simulated trades with timestamps, prices, quantities, and simulated P&L
- 10.12: Simulate bot operations without creating real bots on Pionex
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class SimulatedOrderStatus(Enum):
    """Status of a simulated order."""

    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"


class SimulatedBotStatus(Enum):
    """Status of a simulated bot."""

    ACTIVE = "ACTIVE"
    STOPPED = "STOPPED"


class SimulatedBotType(Enum):
    """Type of simulated bot."""

    GRID = "GRID"
    DCA = "DCA"


@dataclass
class SimulatedBalance:
    """
    Simulated balance for a currency.

    Attributes:
        currency: The currency code (e.g., "BTC", "USDT")
        free: Available balance
        locked: Balance locked in orders/bots
    """

    currency: str
    free: Decimal
    locked: Decimal = field(default_factory=lambda: Decimal("0"))

    @property
    def total(self) -> Decimal:
        """Total balance (free + locked)."""
        return self.free + self.locked


@dataclass
class SimulatedOrder:
    """
    A simulated order execution.

    Attributes:
        order_id: Unique identifier for the simulated order
        symbol: Trading pair symbol
        side: Order side (BUY or SELL)
        quantity: Order quantity
        price: Execution price
        status: Order status
        timestamp: When the order was executed
        base_currency: Base currency of the pair
        quote_currency: Quote currency of the pair
        quote_amount: Total quote currency amount (price * quantity)
    """

    order_id: str
    symbol: str
    side: str
    quantity: Decimal
    price: Decimal
    status: SimulatedOrderStatus
    timestamp: datetime
    base_currency: str
    quote_currency: str

    @property
    def quote_amount(self) -> Decimal:
        """Total quote currency amount."""
        return self.price * self.quantity


@dataclass
class SimulatedBot:
    """
    A simulated trading bot.

    Attributes:
        bot_id: Unique identifier for the simulated bot
        bot_type: Type of bot (GRID or DCA)
        symbol: Trading pair symbol
        status: Bot status
        invested: Amount invested
        current_value: Current value of positions
        pnl: Profit and loss
        params: Bot parameters
        created_at: When the bot was created
        base_currency: Base currency of the pair
        quote_currency: Quote currency of the pair
    """

    bot_id: str
    bot_type: SimulatedBotType
    symbol: str
    status: SimulatedBotStatus
    invested: Decimal
    current_value: Decimal
    pnl: Decimal
    params: dict[str, Any]
    created_at: datetime
    base_currency: str
    quote_currency: str

    @property
    def pnl_percent(self) -> float:
        """P&L as percentage."""
        if self.invested == 0:
            return 0.0
        return float(self.pnl / self.invested) * 100


@dataclass
class SimulatedTrade:
    """
    A simulated trade record for P&L tracking.

    Attributes:
        trade_id: Unique identifier
        order_id: Associated order ID
        symbol: Trading pair
        side: Trade side (BUY or SELL)
        quantity: Trade quantity
        price: Trade price
        timestamp: When the trade occurred
        pnl: Realized P&L (for closing trades)
        is_closing: Whether this trade closes a position
    """

    trade_id: str
    order_id: str
    symbol: str
    side: str
    quantity: Decimal
    price: Decimal
    timestamp: datetime
    pnl: Decimal = field(default_factory=lambda: Decimal("0"))
    is_closing: bool = False


@dataclass(frozen=True)
class BalanceLedgerEntry:
    """
    An entry in the balance ledger for audit trail.

    Attributes:
        timestamp: When the change occurred
        currency: Currency affected
        change: Amount changed (positive or negative)
        balance_after: Balance after the change
        reason: Reason for the change
        reference_id: Order or bot ID that caused the change
    """

    timestamp: datetime
    currency: str
    change: Decimal
    balance_after: Decimal
    reason: str
    reference_id: str


class DryRunSimulator:
    """
    Dry-run simulator for testing trading strategies.

    This simulator maintains a virtual balance ledger and simulates
    order and bot operations without making real API calls. All
    operations are logged for review.

    Requirements:
        - 2.1: Simulate all order operations without calling real Pionex order endpoint
        - 2.2: Maintain a simulated balance ledger tracking virtual positions
        - 2.3: Update simulated balance ledger as if orders filled at current market price
        - 2.4: Log all simulated trades with timestamps, prices, quantities, and simulated P&L
        - 10.12: Simulate bot operations without creating real bots on Pionex

    Example:
        >>> simulator = DryRunSimulator()
        >>> simulator.set_balance("USDT", Decimal("10000.00"))
        >>> simulator.set_balance("BTC", Decimal("0.5"))
        >>>
        >>> # Simulate a buy order
        >>> order = simulator.simulate_order(
        ...     symbol="BTC_USDT",
        ...     side="BUY",
        ...     quantity=Decimal("0.1"),
        ...     price=Decimal("50000.00"),
        ... )
        >>> print(f"Order {order.order_id}: {order.status.value}")
    """

    def __init__(self) -> None:
        """Initialize the dry-run simulator."""
        self._balances: dict[str, SimulatedBalance] = {}
        self._orders: list[SimulatedOrder] = []
        self._bots: dict[str, SimulatedBot] = {}
        self._trades: list[SimulatedTrade] = []
        self._ledger: list[BalanceLedgerEntry] = []
        self._positions: dict[str, Decimal] = {}  # symbol -> quantity (positive=long)
        self._position_avg_prices: dict[str, Decimal] = {}  # symbol -> avg entry price

    # =========================================================================
    # Balance Management
    # =========================================================================

    def set_balance(self, currency: str, amount: Decimal) -> None:
        """
        Set the balance for a currency.

        Args:
            currency: Currency code (e.g., "BTC", "USDT")
            amount: Balance amount

        Raises:
            ValueError: If amount is negative

        Requirements:
            - 2.2: Maintain a simulated balance ledger tracking virtual positions
        """
        if amount < 0:
            raise ValueError(f"Balance amount must be non-negative, got {amount}")

        old_balance = self._balances.get(currency)
        old_amount = old_balance.free if old_balance else Decimal("0")

        self._balances[currency] = SimulatedBalance(
            currency=currency,
            free=amount,
            locked=old_balance.locked if old_balance else Decimal("0"),
        )

        # Log the change
        change = amount - old_amount
        self._add_ledger_entry(
            currency=currency,
            change=change,
            balance_after=amount,
            reason="Balance set",
            reference_id="INIT",
        )

        logger.info(f"Set {currency} balance to {amount}")

    def get_balance(self, currency: str) -> SimulatedBalance:
        """
        Get the balance for a currency.

        Args:
            currency: Currency code

        Returns:
            SimulatedBalance for the currency (zero if not set)

        Requirements:
            - 2.2: Maintain a simulated balance ledger tracking virtual positions
        """
        if currency not in self._balances:
            return SimulatedBalance(currency=currency, free=Decimal("0"))
        return self._balances[currency]

    def get_all_balances(self) -> list[SimulatedBalance]:
        """
        Get all non-zero balances.

        Returns:
            List of SimulatedBalance objects

        Requirements:
            - 2.2: Maintain a simulated balance ledger tracking virtual positions
        """
        return [b for b in self._balances.values() if b.total > 0]

    def _update_balance(
        self,
        currency: str,
        change: Decimal,
        reason: str,
        reference_id: str,
    ) -> Decimal:
        """
        Update balance for a currency.

        Args:
            currency: Currency code
            change: Amount to add (positive) or subtract (negative)
            reason: Reason for the change
            reference_id: Order or bot ID

        Returns:
            New balance after the change

        Raises:
            ValueError: If resulting balance would be negative

        Requirements:
            - 2.2: Maintain a simulated balance ledger tracking virtual positions
            - 2.3: Update simulated balance ledger as if orders filled
        """
        current = self.get_balance(currency)
        new_free = current.free + change

        if new_free < 0:
            raise ValueError(
                f"Insufficient {currency} balance: have {current.free}, need {-change}"
            )

        self._balances[currency] = SimulatedBalance(
            currency=currency,
            free=new_free,
            locked=current.locked,
        )

        self._add_ledger_entry(
            currency=currency,
            change=change,
            balance_after=new_free,
            reason=reason,
            reference_id=reference_id,
        )

        return new_free

    def _add_ledger_entry(
        self,
        currency: str,
        change: Decimal,
        balance_after: Decimal,
        reason: str,
        reference_id: str,
    ) -> None:
        """Add an entry to the balance ledger."""
        entry = BalanceLedgerEntry(
            timestamp=datetime.now(tz=UTC),
            currency=currency,
            change=change,
            balance_after=balance_after,
            reason=reason,
            reference_id=reference_id,
        )
        self._ledger.append(entry)

    def get_ledger(self) -> list[BalanceLedgerEntry]:
        """
        Get the complete balance ledger.

        Returns:
            List of all ledger entries in chronological order
        """
        return list(self._ledger)

    # =========================================================================
    # Order Simulation
    # =========================================================================

    def _parse_symbol(self, symbol: str) -> tuple[str, str]:
        """
        Parse a trading symbol into base and quote currencies.

        Args:
            symbol: Trading pair symbol (e.g., "BTC_USDT")

        Returns:
            Tuple of (base_currency, quote_currency)
        """
        if "_" in symbol:
            parts = symbol.split("_")
            return parts[0], parts[1]
        # Fallback: assume last 4 chars are quote (USDT, BUSD, etc.)
        return symbol[:-4], symbol[-4:]

    def simulate_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
    ) -> SimulatedOrder:
        """
        Simulate an order execution.

        This method simulates filling an order at the specified price,
        updating the balance ledger accordingly.

        For BUY orders:
        - Decreases quote currency by (price * quantity)
        - Increases base currency by quantity

        For SELL orders:
        - Decreases base currency by quantity
        - Increases quote currency by (price * quantity)

        Args:
            symbol: Trading pair symbol (e.g., "BTC_USDT")
            side: Order side ("BUY" or "SELL")
            quantity: Order quantity in base currency
            price: Execution price

        Returns:
            SimulatedOrder with execution details

        Raises:
            ValueError: If side is invalid or insufficient balance

        Requirements:
            - 2.1: Simulate all order operations without calling real Pionex order endpoint
            - 2.3: Update simulated balance ledger as if orders filled at current market price
            - 2.4: Log all simulated trades with timestamps, prices, quantities, and simulated P&L
        """
        side_upper = side.upper()
        if side_upper not in ("BUY", "SELL"):
            raise ValueError(f"Side must be 'BUY' or 'SELL', got {side}")

        if quantity <= 0:
            raise ValueError(f"Quantity must be positive, got {quantity}")

        if price <= 0:
            raise ValueError(f"Price must be positive, got {price}")

        base_currency, quote_currency = self._parse_symbol(symbol)
        quote_amount = price * quantity
        order_id = f"SIM-{uuid.uuid4().hex[:12].upper()}"
        timestamp = datetime.now(tz=UTC)

        # Calculate P&L for closing trades
        pnl = Decimal("0")
        is_closing = False

        try:
            if side_upper == "BUY":
                # BUY: spend quote currency, receive base currency
                self._update_balance(
                    currency=quote_currency,
                    change=-quote_amount,
                    reason=f"BUY {symbol}",
                    reference_id=order_id,
                )
                self._update_balance(
                    currency=base_currency,
                    change=quantity,
                    reason=f"BUY {symbol}",
                    reference_id=order_id,
                )

                # Update position tracking
                current_pos = self._positions.get(symbol, Decimal("0"))
                if current_pos < 0:
                    # Closing a short position
                    is_closing = True
                    close_qty = min(quantity, abs(current_pos))
                    avg_price = self._position_avg_prices.get(symbol, price)
                    pnl = (avg_price - price) * close_qty  # Short profit when price drops

                # Update position
                new_pos = current_pos + quantity
                self._positions[symbol] = new_pos
                if new_pos > 0:
                    # Update average price for long position
                    if current_pos <= 0:
                        self._position_avg_prices[symbol] = price
                    else:
                        # Weighted average
                        old_value = current_pos * self._position_avg_prices.get(symbol, price)
                        new_value = quantity * price
                        self._position_avg_prices[symbol] = (old_value + new_value) / new_pos

            else:  # SELL
                # SELL: spend base currency, receive quote currency
                self._update_balance(
                    currency=base_currency,
                    change=-quantity,
                    reason=f"SELL {symbol}",
                    reference_id=order_id,
                )
                self._update_balance(
                    currency=quote_currency,
                    change=quote_amount,
                    reason=f"SELL {symbol}",
                    reference_id=order_id,
                )

                # Update position tracking
                current_pos = self._positions.get(symbol, Decimal("0"))
                if current_pos > 0:
                    # Closing a long position
                    is_closing = True
                    close_qty = min(quantity, current_pos)
                    avg_price = self._position_avg_prices.get(symbol, price)
                    pnl = (price - avg_price) * close_qty  # Long profit when price rises

                # Update position
                new_pos = current_pos - quantity
                self._positions[symbol] = new_pos
                if new_pos < 0:
                    # Update average price for short position
                    if current_pos >= 0:
                        self._position_avg_prices[symbol] = price
                    else:
                        # Weighted average for shorts
                        old_value = abs(current_pos) * self._position_avg_prices.get(symbol, price)
                        new_value = quantity * price
                        self._position_avg_prices[symbol] = (old_value + new_value) / abs(new_pos)

            status = SimulatedOrderStatus.FILLED

        except ValueError as e:
            # Insufficient balance - order rejected
            logger.warning(f"Order rejected: {e}")
            status = SimulatedOrderStatus.REJECTED
            pnl = Decimal("0")
            is_closing = False

        order = SimulatedOrder(
            order_id=order_id,
            symbol=symbol,
            side=side_upper,
            quantity=quantity,
            price=price,
            status=status,
            timestamp=timestamp,
            base_currency=base_currency,
            quote_currency=quote_currency,
        )

        self._orders.append(order)

        # Record trade
        if status == SimulatedOrderStatus.FILLED:
            trade = SimulatedTrade(
                trade_id=f"TRD-{uuid.uuid4().hex[:12].upper()}",
                order_id=order_id,
                symbol=symbol,
                side=side_upper,
                quantity=quantity,
                price=price,
                timestamp=timestamp,
                pnl=pnl,
                is_closing=is_closing,
            )
            self._trades.append(trade)

        # Log the trade
        logger.info(
            f"Simulated {side_upper} order: {order_id} - "
            f"{quantity} {base_currency} @ {price} {quote_currency} = "
            f"{quote_amount} {quote_currency} (status: {status.value})"
            + (f", P&L: {pnl}" if is_closing else "")
        )

        return order

    def get_orders(self) -> list[SimulatedOrder]:
        """
        Get all simulated orders.

        Returns:
            List of SimulatedOrder objects
        """
        return list(self._orders)

    def get_trades(self) -> list[SimulatedTrade]:
        """
        Get all simulated trades.

        Returns:
            List of SimulatedTrade objects

        Requirements:
            - 2.4: Log all simulated trades with timestamps, prices, quantities, and simulated P&L
        """
        return list(self._trades)

    # =========================================================================
    # Bot Simulation
    # =========================================================================

    def simulate_bot_creation(
        self,
        symbol: str,
        bot_type: str,
        investment: Decimal,
        params: dict[str, Any] | None = None,
    ) -> SimulatedBot:
        """
        Simulate creating a trading bot.

        This method simulates allocating funds to a bot without
        making real API calls.

        Args:
            symbol: Trading pair symbol
            bot_type: Type of bot ("GRID" or "DCA")
            investment: Amount to invest
            params: Bot-specific parameters

        Returns:
            SimulatedBot with bot details

        Raises:
            ValueError: If bot_type is invalid or insufficient balance

        Requirements:
            - 10.12: Simulate bot operations without creating real bots on Pionex
        """
        bot_type_upper = bot_type.upper()
        if bot_type_upper not in ("GRID", "DCA"):
            raise ValueError(f"Bot type must be 'GRID' or 'DCA', got {bot_type}")

        if investment <= 0:
            raise ValueError(f"Investment must be positive, got {investment}")

        base_currency, quote_currency = self._parse_symbol(symbol)
        bot_id = f"BOT-{uuid.uuid4().hex[:12].upper()}"
        timestamp = datetime.now(tz=UTC)

        # Lock the investment amount from quote currency
        current = self.get_balance(quote_currency)
        if current.free < investment:
            raise ValueError(
                f"Insufficient {quote_currency} balance: have {current.free}, need {investment}"
            )

        # Move from free to locked
        self._balances[quote_currency] = SimulatedBalance(
            currency=quote_currency,
            free=current.free - investment,
            locked=current.locked + investment,
        )

        self._add_ledger_entry(
            currency=quote_currency,
            change=-investment,
            balance_after=current.free - investment,
            reason=f"Bot {bot_type_upper} creation - locked",
            reference_id=bot_id,
        )

        bot = SimulatedBot(
            bot_id=bot_id,
            bot_type=SimulatedBotType[bot_type_upper],
            symbol=symbol,
            status=SimulatedBotStatus.ACTIVE,
            invested=investment,
            current_value=investment,  # Initially equal to invested
            pnl=Decimal("0"),
            params=params or {},
            created_at=timestamp,
            base_currency=base_currency,
            quote_currency=quote_currency,
        )

        self._bots[bot_id] = bot

        logger.info(
            f"Simulated {bot_type_upper} bot creation: {bot_id} - "
            f"{symbol}, investment: {investment} {quote_currency}"
        )

        return bot

    def simulate_bot_stop(self, bot_id: str) -> SimulatedBot:
        """
        Simulate stopping a trading bot.

        This method simulates returning funds from a bot to
        available balance.

        Args:
            bot_id: The bot ID to stop

        Returns:
            SimulatedBot with updated status

        Raises:
            ValueError: If bot not found or already stopped

        Requirements:
            - 10.12: Simulate bot operations without creating real bots on Pionex
        """
        if bot_id not in self._bots:
            raise ValueError(f"Bot not found: {bot_id}")

        bot = self._bots[bot_id]

        if bot.status == SimulatedBotStatus.STOPPED:
            raise ValueError(f"Bot already stopped: {bot_id}")

        # Return funds from locked to free
        quote_currency = bot.quote_currency
        current = self.get_balance(quote_currency)
        return_amount = bot.current_value

        self._balances[quote_currency] = SimulatedBalance(
            currency=quote_currency,
            free=current.free + return_amount,
            locked=current.locked - bot.invested,
        )

        self._add_ledger_entry(
            currency=quote_currency,
            change=return_amount,
            balance_after=current.free + return_amount,
            reason=f"Bot {bot.bot_type.value} stopped - unlocked",
            reference_id=bot_id,
        )

        # Update bot status
        stopped_bot = SimulatedBot(
            bot_id=bot.bot_id,
            bot_type=bot.bot_type,
            symbol=bot.symbol,
            status=SimulatedBotStatus.STOPPED,
            invested=bot.invested,
            current_value=bot.current_value,
            pnl=bot.pnl,
            params=bot.params,
            created_at=bot.created_at,
            base_currency=bot.base_currency,
            quote_currency=bot.quote_currency,
        )

        self._bots[bot_id] = stopped_bot

        logger.info(
            f"Simulated bot stop: {bot_id} - "
            f"returned {return_amount} {quote_currency}, P&L: {bot.pnl}"
        )

        return stopped_bot

    def update_bot_value(
        self,
        bot_id: str,
        current_value: Decimal,
    ) -> SimulatedBot:
        """
        Update the current value of a simulated bot.

        This is used to simulate market movements affecting bot value.

        Args:
            bot_id: The bot ID to update
            current_value: New current value

        Returns:
            SimulatedBot with updated value

        Raises:
            ValueError: If bot not found
        """
        if bot_id not in self._bots:
            raise ValueError(f"Bot not found: {bot_id}")

        bot = self._bots[bot_id]
        pnl = current_value - bot.invested

        updated_bot = SimulatedBot(
            bot_id=bot.bot_id,
            bot_type=bot.bot_type,
            symbol=bot.symbol,
            status=bot.status,
            invested=bot.invested,
            current_value=current_value,
            pnl=pnl,
            params=bot.params,
            created_at=bot.created_at,
            base_currency=bot.base_currency,
            quote_currency=bot.quote_currency,
        )

        self._bots[bot_id] = updated_bot

        return updated_bot

    def get_bot(self, bot_id: str) -> SimulatedBot | None:
        """
        Get a simulated bot by ID.

        Args:
            bot_id: The bot ID

        Returns:
            SimulatedBot or None if not found
        """
        return self._bots.get(bot_id)

    def get_all_bots(self) -> list[SimulatedBot]:
        """
        Get all simulated bots.

        Returns:
            List of SimulatedBot objects
        """
        return list(self._bots.values())

    def get_active_bots(self) -> list[SimulatedBot]:
        """
        Get all active simulated bots.

        Returns:
            List of active SimulatedBot objects
        """
        return [b for b in self._bots.values() if b.status == SimulatedBotStatus.ACTIVE]

    # =========================================================================
    # Portfolio and P&L
    # =========================================================================

    def get_total_pnl(self) -> Decimal:
        """
        Get total realized P&L from all trades.

        Returns:
            Total P&L

        Requirements:
            - 2.4: Log all simulated trades with timestamps, prices, quantities, and simulated P&L
        """
        return sum((t.pnl for t in self._trades), Decimal("0"))

    def get_bot_allocation(self) -> Decimal:
        """
        Get total amount allocated to active bots.

        Returns:
            Total allocation to bots
        """
        return sum(
            (b.invested for b in self._bots.values() if b.status == SimulatedBotStatus.ACTIVE),
            Decimal("0"),
        )

    def get_portfolio_value(self, prices: dict[str, Decimal]) -> Decimal:
        """
        Calculate total portfolio value given current prices.

        Args:
            prices: Dictionary of symbol -> price for valuation

        Returns:
            Total portfolio value in quote currency (assumes USDT)
        """
        total = Decimal("0")

        for balance in self._balances.values():
            if balance.currency == "USDT":
                total += balance.total
            else:
                # Look for price in format "CURRENCY_USDT"
                symbol = f"{balance.currency}_USDT"
                if symbol in prices:
                    total += balance.total * prices[symbol]

        return total

    def reset(self) -> None:
        """
        Reset the simulator to initial state.

        Clears all balances, orders, bots, trades, and ledger entries.
        """
        self._balances.clear()
        self._orders.clear()
        self._bots.clear()
        self._trades.clear()
        self._ledger.clear()
        self._positions.clear()
        self._position_avg_prices.clear()

        logger.info("Simulator reset to initial state")


# Export public API
__all__ = [
    "DryRunSimulator",
    "SimulatedBalance",
    "SimulatedOrder",
    "SimulatedOrderStatus",
    "SimulatedBot",
    "SimulatedBotStatus",
    "SimulatedBotType",
    "SimulatedTrade",
    "BalanceLedgerEntry",
]
