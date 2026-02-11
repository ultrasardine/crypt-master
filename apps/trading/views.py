"""Trading views."""

import asyncio
import logging
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from apps.core.models import TradingPair

from .models import Signal, SignalDirection, Trade, TradeSide

logger = logging.getLogger(__name__)


class SignalListView(LoginRequiredMixin, ListView):
    """List view for trading signals with filtering. Filtered by user's active pairs."""

    model = Signal
    template_name = "trading/signal_list.html"
    context_object_name = "signals"
    paginate_by = 50

    def get_queryset(self):
        """Filter signals to user's active trading pairs."""
        queryset = Signal.objects.select_related("trading_pair").prefetch_related(
            "outcome", "outcome__bot"
        ).all()

        # Filter by user's active trading pairs
        if hasattr(self.request.user, "profile"):
            active_pairs = self.request.user.profile.active_trading_pairs
            if active_pairs:
                queryset = queryset.filter(trading_pair__symbol__in=active_pairs)
            else:
                # No pairs configured - show no signals
                queryset = queryset.none()

        # Filter by direction
        direction = self.request.GET.get("direction")
        if direction and direction in dict(SignalDirection.choices):
            queryset = queryset.filter(direction=direction)

        # Filter by executed status
        executed = self.request.GET.get("executed")
        if executed == "yes":
            queryset = queryset.executed()
        elif executed == "no":
            queryset = queryset.pending()

        # Filter by confidence threshold
        min_confidence = self.request.GET.get("min_confidence")
        if min_confidence:
            try:
                queryset = queryset.high_confidence(float(min_confidence))
            except ValueError:
                pass

        # Filter by trading pair
        symbol = self.request.GET.get("symbol")
        if symbol:
            queryset = queryset.for_pair(symbol)

        return queryset

    def get_context_data(self, **kwargs):
        """Add filter options and stats to context."""
        context = super().get_context_data(**kwargs)

        # Filter options
        context["direction_choices"] = SignalDirection.choices
        context["trading_pairs"] = TradingPair.objects.active()

        # Current filter values
        context["current_direction"] = self.request.GET.get("direction", "")
        context["current_executed"] = self.request.GET.get("executed", "")
        context["current_min_confidence"] = self.request.GET.get("min_confidence", "")
        context["current_symbol"] = self.request.GET.get("symbol", "")

        # Summary stats - filtered by user's active pairs
        active_pairs = []
        if hasattr(self.request.user, "profile"):
            active_pairs = self.request.user.profile.active_trading_pairs or []

        if active_pairs:
            recent = Signal.objects.filter(
                trading_pair__symbol__in=active_pairs
            ).recent(hours=24)
        else:
            recent = Signal.objects.none()

        context["total_signals_24h"] = recent.count()
        context["buy_signals_24h"] = recent.buy_signals().count() if active_pairs else 0
        context["sell_signals_24h"] = recent.sell_signals().count() if active_pairs else 0
        context["avg_confidence"] = recent.average_confidence() if active_pairs else None

        return context


class SignalDetailView(LoginRequiredMixin, DetailView):
    """Detail view for a single signal."""

    model = Signal
    template_name = "trading/signal_detail.html"
    context_object_name = "signal"

    def get_queryset(self):
        """Filter to user's active trading pairs."""
        queryset = Signal.objects.select_related("trading_pair")

        # Filter by user's active trading pairs
        if hasattr(self.request.user, "profile"):
            active_pairs = self.request.user.profile.active_trading_pairs
            if active_pairs:
                queryset = queryset.filter(trading_pair__symbol__in=active_pairs)
            else:
                queryset = queryset.none()

        return queryset

    def get_context_data(self, **kwargs):
        """Add related trades to context."""
        context = super().get_context_data(**kwargs)
        # Only show user's trades related to this signal
        context["trades"] = self.object.trades.filter(user=self.request.user)
        return context


class TradeListView(LoginRequiredMixin, ListView):
    """List view for trades with filtering and P&L display. User-isolated."""

    model = Trade
    template_name = "trading/trade_list.html"
    context_object_name = "trades"
    paginate_by = 50

    def get_queryset(self):
        """Filter trades to current user only."""
        queryset = Trade.objects.select_related("trading_pair", "signal").filter(
            user=self.request.user
        )

        # Filter by side
        side = self.request.GET.get("side")
        if side and side in dict(TradeSide.choices):
            queryset = queryset.filter(side=side)

        # Filter by mode (simulated/live)
        mode = self.request.GET.get("mode")
        if mode == "simulated":
            queryset = queryset.simulated()
        elif mode == "live":
            queryset = queryset.live()

        # Filter by status (open/closed)
        status = self.request.GET.get("status")
        if status == "open":
            queryset = queryset.open_positions()
        elif status == "closed":
            queryset = queryset.closed()

        # Filter by profitability
        profit = self.request.GET.get("profit")
        if profit == "profitable":
            queryset = queryset.profitable()
        elif profit == "unprofitable":
            queryset = queryset.unprofitable()

        # Filter by trading pair
        symbol = self.request.GET.get("symbol")
        if symbol:
            queryset = queryset.for_pair(symbol)

        return queryset

    def get_context_data(self, **kwargs):
        """Add filter options and trade statistics to context."""
        context = super().get_context_data(**kwargs)

        # Filter options
        context["side_choices"] = TradeSide.choices
        context["trading_pairs"] = TradingPair.objects.active()

        # Current filter values
        context["current_side"] = self.request.GET.get("side", "")
        context["current_mode"] = self.request.GET.get("mode", "")
        context["current_status"] = self.request.GET.get("status", "")
        context["current_profit"] = self.request.GET.get("profit", "")
        context["current_symbol"] = self.request.GET.get("symbol", "")

        # Trade statistics - user's trades only
        user_trades = Trade.objects.filter(user=self.request.user)

        # Live stats
        live_stats = user_trades.live().statistics()
        context["live_stats"] = live_stats

        # Simulated stats
        sim_stats = user_trades.simulated().statistics()
        context["sim_stats"] = sim_stats

        # Recent P&L - user's trades only
        context["recent_pnl"] = user_trades.live().recent(hours=24).total_pnl()
        context["recent_volume"] = user_trades.live().recent(hours=24).total_volume()

        return context


class TradeDetailView(LoginRequiredMixin, DetailView):
    """Detail view for a single trade. User-isolated."""

    model = Trade
    template_name = "trading/trade_detail.html"
    context_object_name = "trade"

    def get_queryset(self):
        """Only allow access to user's own trades."""
        return Trade.objects.select_related("trading_pair", "signal").filter(
            user=self.request.user
        )


# =========================================================================
# Pionex Order Management Views
# =========================================================================


def get_pionex_client():
    """
    Get a configured Pionex client instance.

    Returns:
        PionexClient instance configured with user's API credentials

    Note:
        This retrieves credentials from environment variables.
        In a multi-tenant setup, this would retrieve from user's APIKey model.
    """
    import os

    from lib.pionex.client import PionexClient

    api_key = os.environ.get("PIONEX_API_KEY", "")
    api_secret = os.environ.get("PIONEX_API_SECRET", "")

    return PionexClient(api_key=api_key, api_secret=api_secret)


class OrderListView(LoginRequiredMixin, TemplateView):
    """
    List view for open orders with real-time updates.

    Displays all open orders for the user's active trading pairs
    in a table with cancel functionality.

    Requirements:
        - 7.1: Display open orders in table with symbol, side, type, price, size, filled, status
        - 7.6: Use Tailwind design system with BUY (emerald) and SELL (red) colors
    """

    template_name = "trading/order_list.html"

    def get_context_data(self, **kwargs):
        """Add orders and trading pairs to context."""
        context = super().get_context_data(**kwargs)

        # Get active trading pairs for the user
        active_pairs = []
        if hasattr(self.request.user, "profile"):
            active_pairs = self.request.user.profile.active_trading_pairs or []

        # If no pairs configured, use default pairs
        if not active_pairs:
            active_pairs = ["BTC_USDT", "ETH_USDT"]

        context["trading_pairs"] = TradingPair.objects.active()
        context["active_pairs"] = active_pairs

        # Get current filter
        current_symbol = self.request.GET.get("symbol", "")
        context["current_symbol"] = current_symbol

        # Fetch open orders from Pionex API
        orders = []
        error_message = None

        try:
            # Run async code in sync context
            orders = asyncio.run(self._fetch_open_orders(active_pairs, current_symbol))
        except Exception as e:
            logger.error(f"Failed to fetch open orders: {e}")
            error_message = f"Failed to fetch orders: {e}"

        context["orders"] = orders
        context["error_message"] = error_message
        context["order_count"] = len(orders)

        return context

    async def _fetch_open_orders(self, active_pairs: list[str], symbol_filter: str) -> list:
        """Fetch open orders from Pionex API."""
        from lib.pionex.models import PionexAPIError

        orders = []

        async with get_pionex_client() as client:
            # If a specific symbol is selected, only fetch for that symbol
            if symbol_filter:
                pairs_to_fetch = [symbol_filter]
            else:
                pairs_to_fetch = active_pairs

            for symbol in pairs_to_fetch:
                try:
                    symbol_orders = await client.get_open_orders(symbol)
                    orders.extend(symbol_orders)
                except PionexAPIError as e:
                    logger.warning(f"Failed to fetch orders for {symbol}: {e}")
                    continue

        # Sort by create_time descending (most recent first)
        orders.sort(key=lambda o: o.create_time, reverse=True)

        return orders


class OrderHistoryView(LoginRequiredMixin, TemplateView):
    """
    List view for all orders (open and closed) with filtering.

    Displays order history with filtering by symbol, status, and date range.

    Requirements:
        - 7.2: Display all orders with filtering by symbol, status, date range
    """

    template_name = "trading/order_history.html"

    def get_context_data(self, **kwargs):
        """Add orders and filter options to context."""
        context = super().get_context_data(**kwargs)

        # Get active trading pairs for the user
        active_pairs = []
        if hasattr(self.request.user, "profile"):
            active_pairs = self.request.user.profile.active_trading_pairs or []

        if not active_pairs:
            active_pairs = ["BTC_USDT", "ETH_USDT"]

        context["trading_pairs"] = TradingPair.objects.active()
        context["active_pairs"] = active_pairs

        # Get filter values
        current_symbol = self.request.GET.get("symbol", "")
        current_status = self.request.GET.get("status", "")
        start_date = self.request.GET.get("start_date", "")
        end_date = self.request.GET.get("end_date", "")

        context["current_symbol"] = current_symbol
        context["current_status"] = current_status
        context["start_date"] = start_date
        context["end_date"] = end_date

        # Parse dates
        start_time = None
        end_time = None

        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                start_time = int(start_dt.timestamp() * 1000)
            except ValueError:
                pass

        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                # End of day
                end_dt = end_dt + timedelta(days=1) - timedelta(seconds=1)
                end_time = int(end_dt.timestamp() * 1000)
            except ValueError:
                pass

        # Fetch orders from Pionex API
        orders = []
        error_message = None

        try:
            orders = asyncio.run(
                self._fetch_all_orders(active_pairs, current_symbol, start_time, end_time)
            )

            # Filter by status if specified
            if current_status:
                orders = [o for o in orders if o.status.value == current_status]

        except Exception as e:
            logger.error(f"Failed to fetch order history: {e}")
            error_message = f"Failed to fetch orders: {e}"

        context["orders"] = orders
        context["error_message"] = error_message
        context["order_count"] = len(orders)

        return context

    async def _fetch_all_orders(
        self,
        active_pairs: list[str],
        symbol_filter: str,
        start_time: int | None,
        end_time: int | None,
    ) -> list:
        """Fetch all orders from Pionex API."""
        from lib.pionex.models import PionexAPIError

        orders = []

        async with get_pionex_client() as client:
            if symbol_filter:
                pairs_to_fetch = [symbol_filter]
            else:
                pairs_to_fetch = active_pairs

            for symbol in pairs_to_fetch:
                try:
                    symbol_orders = await client.get_all_orders(
                        symbol=symbol,
                        start_time=start_time,
                        end_time=end_time,
                        limit=100,
                    )
                    orders.extend(symbol_orders)
                except PionexAPIError as e:
                    logger.warning(f"Failed to fetch orders for {symbol}: {e}")
                    continue

        # Sort by create_time descending
        orders.sort(key=lambda o: o.create_time, reverse=True)

        return orders


class OrderDetailView(LoginRequiredMixin, TemplateView):
    """
    Detail view for a single order with fills.

    Displays order details and all fills (trade executions) for the order.

    Requirements:
        - 7.3: Display order details including all fills for that order
    """

    template_name = "trading/order_detail.html"

    def get_context_data(self, **kwargs):
        """Add order and fills to context."""
        context = super().get_context_data(**kwargs)

        symbol = self.kwargs.get("symbol", "")
        order_id = self.kwargs.get("order_id", 0)

        context["symbol"] = symbol
        context["order_id"] = order_id

        order = None
        fills = []
        error_message = None

        try:
            order, fills = asyncio.run(self._fetch_order_with_fills(symbol, order_id))
        except Exception as e:
            logger.error(f"Failed to fetch order {order_id}: {e}")
            error_message = f"Failed to fetch order: {e}"

        context["order"] = order
        context["fills"] = fills
        context["error_message"] = error_message

        # Calculate total fees
        if fills:
            total_fees = {}
            for fill in fills:
                coin = fill.fee_coin
                if coin not in total_fees:
                    total_fees[coin] = fill.fee
                else:
                    total_fees[coin] += fill.fee
            context["total_fees"] = total_fees

        return context

    async def _fetch_order_with_fills(self, symbol: str, order_id: int):
        """Fetch order details and fills from Pionex API."""
        from lib.pionex.models import PionexAPIError

        order = None
        fills = []

        async with get_pionex_client() as client:
            try:
                order = await client.get_order(symbol, order_id)
            except PionexAPIError as e:
                logger.warning(f"Failed to fetch order {order_id}: {e}")
                raise

            try:
                fills = await client.get_fills_by_order_id(symbol, order_id)
            except PionexAPIError as e:
                logger.warning(f"Failed to fetch fills for order {order_id}: {e}")
                # Don't raise - order may have no fills yet

        return order, fills


class CancelOrderView(LoginRequiredMixin, View):
    """
    View to cancel a single order.

    Handles POST requests to cancel an order and returns JSON response.

    Requirements:
        - 7.4: Cancel order with confirmation and success/error feedback
    """

    def post(self, request: HttpRequest, symbol: str, order_id: str) -> HttpResponse:
        """Cancel the specified order."""
        try:
            result = asyncio.run(self._cancel_order(symbol, order_id))

            if result:
                messages.success(request, f"Order {order_id} canceled successfully.")
                return JsonResponse({"success": True, "message": "Order canceled successfully"})
            else:
                messages.error(request, f"Failed to cancel order {order_id}.")
                return JsonResponse(
                    {"success": False, "message": "Failed to cancel order"}, status=400
                )

        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            messages.error(request, f"Error canceling order: {e}")
            return JsonResponse({"success": False, "message": str(e)}, status=500)

    async def _cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel order via Pionex API."""
        async with get_pionex_client() as client:
            result = await client.cancel_order(symbol=symbol, order_id=order_id)
            return result.success


class CancelAllOrdersView(LoginRequiredMixin, View):
    """
    View to cancel all orders for a symbol.

    Handles POST requests to cancel all open orders for a trading pair.

    Requirements:
        - 7.5: Cancel all orders with confirmation showing order count
    """

    def post(self, request: HttpRequest, symbol: str) -> HttpResponse:
        """Cancel all orders for the specified symbol."""
        try:
            result = asyncio.run(self._cancel_all_orders(symbol))

            if result:
                messages.success(request, f"All orders for {symbol} canceled successfully.")
                return JsonResponse(
                    {"success": True, "message": f"All orders for {symbol} canceled"}
                )
            else:
                messages.error(request, f"Failed to cancel orders for {symbol}.")
                return JsonResponse(
                    {"success": False, "message": "Failed to cancel orders"}, status=400
                )

        except Exception as e:
            logger.error(f"Failed to cancel all orders for {symbol}: {e}")
            messages.error(request, f"Error canceling orders: {e}")
            return JsonResponse({"success": False, "message": str(e)}, status=500)

    async def _cancel_all_orders(self, symbol: str) -> bool:
        """Cancel all orders via Pionex API."""
        async with get_pionex_client() as client:
            return await client.cancel_all_orders(symbol)


# =========================================================================
# Pionex Fill History Views
# =========================================================================


class TickerListView(LoginRequiredMixin, TemplateView):
    """
    List view for market tickers with real-time updates.

    Displays 24hr tickers in a grid with stats cards showing price,
    change %, volume, and trade count. Also shows book tickers with
    best bid/ask and spread.

    Requirements:
        - 9.1: Display 24hr tickers in grid with price, change, volume
        - 9.2: Show book ticker with best bid/ask spread
        - 9.4: Use emerald for positive and red for negative changes
    """

    template_name = "trading/ticker_list.html"

    def get_context_data(self, **kwargs):
        """Add tickers and book tickers to context."""
        context = super().get_context_data(**kwargs)

        # Get active trading pairs for the user
        active_pairs = []
        if hasattr(self.request.user, "profile"):
            active_pairs = self.request.user.profile.active_trading_pairs or []

        if not active_pairs:
            active_pairs = ["BTC_USDT", "ETH_USDT"]

        context["trading_pairs"] = TradingPair.objects.active()
        context["active_pairs"] = active_pairs

        # Get filter values
        current_symbol = self.request.GET.get("symbol", "")
        market_type = self.request.GET.get("market_type", "SPOT")

        context["current_symbol"] = current_symbol
        context["market_type"] = market_type

        # Fetch tickers from Pionex API
        tickers = []
        book_tickers = []
        error_message = None

        try:
            tickers, book_tickers = asyncio.run(
                self._fetch_tickers(active_pairs, current_symbol, market_type)
            )
        except Exception as e:
            logger.error(f"Failed to fetch tickers: {e}")
            error_message = f"Failed to fetch tickers: {e}"

        context["tickers"] = tickers
        context["book_tickers"] = book_tickers
        context["error_message"] = error_message
        context["ticker_count"] = len(tickers)

        # Create a mapping of book tickers by symbol for easy lookup in template
        book_ticker_map = {bt.symbol: bt for bt in book_tickers}
        context["book_ticker_map"] = book_ticker_map

        return context

    async def _fetch_tickers(
        self,
        active_pairs: list[str],
        symbol_filter: str,
        market_type: str,
    ) -> tuple[list, list]:
        """Fetch 24hr tickers and book tickers from Pionex API."""
        from lib.pionex.models import PionexAPIError

        tickers = []
        book_tickers = []

        async with get_pionex_client() as client:
            try:
                # Fetch 24hr tickers
                if symbol_filter:
                    all_tickers = await client.get_24hr_tickers(
                        symbol=symbol_filter, market_type=market_type
                    )
                else:
                    all_tickers = await client.get_24hr_tickers(market_type=market_type)

                # Filter to active pairs if no specific symbol selected
                if symbol_filter:
                    tickers = all_tickers
                else:
                    tickers = [t for t in all_tickers if t.symbol in active_pairs]

            except PionexAPIError as e:
                logger.warning(f"Failed to fetch 24hr tickers: {e}")

            try:
                # Fetch book tickers
                if symbol_filter:
                    all_book_tickers = await client.get_book_tickers(
                        symbol=symbol_filter, market_type=market_type
                    )
                else:
                    all_book_tickers = await client.get_book_tickers(market_type=market_type)

                # Filter to active pairs if no specific symbol selected
                if symbol_filter:
                    book_tickers = all_book_tickers
                else:
                    book_tickers = [bt for bt in all_book_tickers if bt.symbol in active_pairs]

            except PionexAPIError as e:
                logger.warning(f"Failed to fetch book tickers: {e}")

        # Sort tickers by symbol
        tickers.sort(key=lambda t: t.symbol)
        book_tickers.sort(key=lambda bt: bt.symbol)

        return tickers, book_tickers


class FillListView(LoginRequiredMixin, TemplateView):
    """
    List view for fill history with filtering.

    Displays trade execution records (fills) with filtering by symbol
    and date range. Shows total fees paid in the filtered results.

    Requirements:
        - 8.1: Display fills in table with symbol, side, role, price, size, fee, timestamp
        - 8.2: Support filtering by symbol and date range
        - 8.3: Calculate and display total fees paid
        - 8.4: Show role (TAKER/MAKER) with appropriate styling
    """

    template_name = "trading/fill_list.html"

    def get_context_data(self, **kwargs):
        """Add fills and filter options to context."""
        context = super().get_context_data(**kwargs)

        # Get active trading pairs for the user
        active_pairs = []
        if hasattr(self.request.user, "profile"):
            active_pairs = self.request.user.profile.active_trading_pairs or []

        if not active_pairs:
            active_pairs = ["BTC_USDT", "ETH_USDT"]

        context["trading_pairs"] = TradingPair.objects.active()
        context["active_pairs"] = active_pairs

        # Get filter values
        current_symbol = self.request.GET.get("symbol", "")
        start_date = self.request.GET.get("start_date", "")
        end_date = self.request.GET.get("end_date", "")

        context["current_symbol"] = current_symbol
        context["start_date"] = start_date
        context["end_date"] = end_date

        # Parse dates
        start_time = None
        end_time = None

        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                start_time = int(start_dt.timestamp() * 1000)
            except ValueError:
                pass

        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                # End of day
                end_dt = end_dt + timedelta(days=1) - timedelta(seconds=1)
                end_time = int(end_dt.timestamp() * 1000)
            except ValueError:
                pass

        # Fetch fills from Pionex API
        fills = []
        error_message = None

        try:
            fills = asyncio.run(
                self._fetch_fills(active_pairs, current_symbol, start_time, end_time)
            )
        except Exception as e:
            logger.error(f"Failed to fetch fills: {e}")
            error_message = f"Failed to fetch fills: {e}"

        context["fills"] = fills
        context["error_message"] = error_message
        context["fill_count"] = len(fills)

        # Calculate total fees by currency
        total_fees = {}
        for fill in fills:
            coin = fill.fee_coin
            if coin not in total_fees:
                total_fees[coin] = fill.fee
            else:
                total_fees[coin] += fill.fee
        context["total_fees"] = total_fees

        return context

    async def _fetch_fills(
        self,
        active_pairs: list[str],
        symbol_filter: str,
        start_time: int | None,
        end_time: int | None,
    ) -> list:
        """Fetch fills from Pionex API."""
        from lib.pionex.models import PionexAPIError

        fills = []

        async with get_pionex_client() as client:
            if symbol_filter:
                pairs_to_fetch = [symbol_filter]
            else:
                pairs_to_fetch = active_pairs

            for symbol in pairs_to_fetch:
                try:
                    symbol_fills = await client.get_fills(
                        symbol=symbol,
                        start_time=start_time,
                        end_time=end_time,
                    )
                    fills.extend(symbol_fills)
                except PionexAPIError as e:
                    logger.warning(f"Failed to fetch fills for {symbol}: {e}")
                    continue

        # Sort by timestamp descending (most recent first)
        fills.sort(key=lambda f: f.timestamp, reverse=True)

        return fills
