"""REST API views."""

import uuid
from decimal import Decimal

from django.utils import timezone
from rest_framework import generics, status
from rest_framework.authtoken.models import Token
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.bots.models import Bot, BotEvent, BotStatus
from apps.core.models import PortfolioSnapshot, SystemConfig, TradingPair
from apps.trading.models import Signal, Trade
from lib.multitenancy.mixins import UserIsolationMixin, UserOwnershipMixin

from .serializers import (
    BacktestRequestSerializer,
    BotCreateSerializer,
    BotSerializer,
    PortfolioSerializer,
    SignalSerializer,
    SystemConfigSerializer,
    SystemConfigUpdateSerializer,
    TradeSerializer,
    TradeStatisticsSerializer,
    TradingPairSerializer,
)


class StandardPagination(PageNumberPagination):
    """Standard pagination for list views."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class PortfolioView(APIView):
    """API view for current portfolio state.

    Applies user isolation to ensure users only see their own portfolio data.

    Requirements:
    - 5.2: Filter results to only include snapshots owned by the authenticated user
    - 5.4: Return 404 for cross-user access attempts
    """

    def get(self, request):
        """Get the latest portfolio snapshot for the authenticated user.

        Query params:
            simulated: bool - If true, return simulated portfolio

        Requirements:
        - 5.2: Filter results to only include snapshots owned by the authenticated user
        """
        is_simulated = request.query_params.get("simulated", "false").lower() == "true"

        # Start with base queryset
        queryset = PortfolioSnapshot.objects.all()

        # Apply user filtering (admin bypass)
        if request.user.is_authenticated:
            if not request.user.is_superuser:
                queryset = queryset.filter(user=request.user)
        else:
            # Unauthenticated users get no results
            queryset = queryset.none()

        # Filter by simulated status and get latest
        if is_simulated:
            snapshot = queryset.simulated().first()
        else:
            snapshot = queryset.live().first()

        if snapshot:
            serializer = PortfolioSerializer(snapshot)
            return Response(serializer.data)
        return Response(
            {"detail": "No portfolio snapshot available"},
            status=status.HTTP_404_NOT_FOUND,
        )


class PortfolioHistoryView(UserIsolationMixin, generics.ListAPIView):
    """API view for portfolio history.

    Applies user isolation to ensure users only see their own portfolio history.

    Requirements:
    - 5.2: Filter results to only include snapshots owned by the authenticated user
    - 5.4: Return 404 for cross-user access attempts
    """

    serializer_class = PortfolioSerializer
    pagination_class = StandardPagination
    queryset = PortfolioSnapshot.objects.all()

    def get_queryset(self):
        """Get portfolio snapshots with optional filtering.

        First applies user isolation via the mixin, then applies additional filters.

        Requirements:
        - 5.2: Filter results to only include snapshots owned by the authenticated user
        """
        # Get user-filtered queryset from mixin
        queryset = super().get_queryset()

        # Filter by simulated status
        is_simulated = self.request.query_params.get("simulated", "false").lower() == "true"
        if is_simulated:
            queryset = queryset.simulated()
        else:
            queryset = queryset.live()

        # Filter by hours
        hours = self.request.query_params.get("hours")
        if hours:
            try:
                queryset = queryset.recent(int(hours))
            except ValueError:
                pass

        return queryset


class TradingPairListView(generics.ListAPIView):
    """API view for listing trading pairs."""

    serializer_class = TradingPairSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        """Get trading pairs with optional filtering."""
        queryset = TradingPair.objects.all()

        # Filter by active status
        active_only = self.request.query_params.get("active", "true").lower() == "true"
        if active_only:
            queryset = queryset.active()

        # Filter by quote currency
        quote = self.request.query_params.get("quote")
        if quote:
            queryset = queryset.by_quote(quote.upper())

        # Filter by base currency
        base = self.request.query_params.get("base")
        if base:
            queryset = queryset.by_base(base.upper())

        return queryset


class SignalListView(generics.ListAPIView):
    """API view for listing signals.

    Signals are shared across users (no user FK), but are filtered based on
    the authenticated user's active_trading_pairs preferences.

    Requirements:
    - 6.3: Display signals for trading pairs the user has configured
    """

    serializer_class = SignalSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        """Get signals with optional filtering.

        Applies user preference filtering based on active_trading_pairs,
        then applies additional query parameter filters.

        Requirements:
        - 6.3: Display signals for trading pairs the user has configured
        """
        queryset = Signal.objects.select_related("trading_pair").all()

        # Filter by user's active trading pairs if authenticated
        # Signals are shared but filtered by user preferences
        if self.request.user.is_authenticated:
            # Admin users see all signals (bypass filtering)
            if not self.request.user.is_superuser:
                # Get user's active trading pairs from their profile
                if hasattr(self.request.user, "profile"):
                    active_pairs = self.request.user.profile.active_trading_pairs
                    if active_pairs:
                        # Filter signals to only those for user's active pairs
                        queryset = queryset.filter(trading_pair__symbol__in=active_pairs)
                    # If user has no active pairs configured, show no signals
                    else:
                        queryset = queryset.none()
                else:
                    # User has no profile, show no signals
                    queryset = queryset.none()
        # Unauthenticated users see all signals (public market data)
        # This maintains backward compatibility for public signal viewing

        # Filter by symbol
        symbol = self.request.query_params.get("symbol")
        if symbol:
            queryset = queryset.for_pair(symbol.upper())

        # Filter by direction
        direction = self.request.query_params.get("direction")
        if direction:
            queryset = queryset.by_direction(direction.upper())

        # Filter by minimum confidence
        min_confidence = self.request.query_params.get("min_confidence")
        if min_confidence:
            try:
                queryset = queryset.high_confidence(float(min_confidence))
            except ValueError:
                pass

        # Filter by hours
        hours = self.request.query_params.get("hours")
        if hours:
            try:
                queryset = queryset.recent(int(hours))
            except ValueError:
                pass

        # Filter by executed status
        executed = self.request.query_params.get("executed")
        if executed is not None:
            if executed.lower() == "true":
                queryset = queryset.executed()
            elif executed.lower() == "false":
                queryset = queryset.pending()

        return queryset


class SignalDetailView(generics.RetrieveAPIView):
    """API view for signal details."""

    queryset = Signal.objects.select_related("trading_pair").all()
    serializer_class = SignalSerializer


class BotListView(UserIsolationMixin, generics.ListCreateAPIView):
    """API view for listing and creating bots.

    Applies user isolation to ensure users only see their own bots.

    Requirements:
    - 3.2: Filter results to only include bots owned by the authenticated user
    - 3.3: Associate new bots with the authenticated user
    """

    pagination_class = StandardPagination
    queryset = Bot.objects.select_related("trading_pair").prefetch_related("events").all()

    def get_serializer_class(self):
        """Return appropriate serializer based on request method."""
        if self.request.method == "POST":
            return BotCreateSerializer
        return BotSerializer

    def get_queryset(self):
        """Get bots with optional filtering.

        First applies user isolation via the mixin, then applies additional filters.

        Requirements:
        - 3.2: Filter results to only include bots owned by the authenticated user
        """
        # Get user-filtered queryset from mixin
        queryset = super().get_queryset()

        # Filter by status
        bot_status = self.request.query_params.get("status")
        if bot_status:
            queryset = queryset.filter(status=bot_status.upper())

        # Filter by type
        bot_type = self.request.query_params.get("type")
        if bot_type:
            queryset = queryset.by_type(bot_type.upper())

        # Filter by symbol
        symbol = self.request.query_params.get("symbol")
        if symbol:
            queryset = queryset.for_pair(symbol.upper())

        # Filter by simulated status
        is_simulated = self.request.query_params.get("simulated")
        if is_simulated is not None:
            if is_simulated.lower() == "true":
                queryset = queryset.simulated()
            elif is_simulated.lower() == "false":
                queryset = queryset.live()

        # Filter by profitability
        profitable = self.request.query_params.get("profitable")
        if profitable is not None:
            if profitable.lower() == "true":
                queryset = queryset.profitable()
            elif profitable.lower() == "false":
                queryset = queryset.unprofitable()

        return queryset

    def perform_create(self, serializer):
        """Create a new bot with generated pionex_bot_id and associate with user.

        Requirements:
        - 3.3: Associate new bots with the authenticated user
        """
        # Generate a unique bot ID (in real implementation, this would come from Pionex API)
        pionex_bot_id = (
            f"sim_{uuid.uuid4().hex[:16]}"
            if serializer.validated_data.get("is_simulated", False)
            else f"bot_{uuid.uuid4().hex[:16]}"
        )

        bot = serializer.save(
            user=self.request.user,  # Associate bot with authenticated user
            pionex_bot_id=pionex_bot_id,
            status=BotStatus.ACTIVE,
            current_value=serializer.validated_data["invested_amount"],
            current_pnl=Decimal("0"),
            pnl_percent=0.0,
        )

        # Create bot creation event
        BotEvent.objects.create(
            bot=bot,
            event_type=BotEvent.EventType.CREATED,
            details={
                "invested_amount": str(bot.invested_amount),
                "params": bot.params,
            },
            reasoning="Bot created via API",
        )


class BotDetailView(UserOwnershipMixin, UserIsolationMixin, generics.RetrieveDestroyAPIView):
    """API view for bot details and deletion (stop).

    Applies user isolation to ensure users can only access their own bots.
    Uses UserOwnershipMixin to verify ownership before stop/delete operations.

    Requirements:
    - 3.4: Return 404 for cross-user access attempts
    - 3.5: Verify ownership before stopping/deleting bots
    """

    queryset = Bot.objects.select_related("trading_pair").prefetch_related("events").all()
    serializer_class = BotSerializer

    def destroy(self, request, *args, **kwargs):
        """Stop a bot instead of deleting it.

        Ownership is verified by the UserIsolationMixin.get_object() method
        which is called by self.get_object().

        Requirements:
        - 3.5: Verify ownership before stopping bots
        """
        bot = self.get_object()  # This verifies ownership via mixin

        if bot.status == BotStatus.STOPPED:
            return Response(
                {"detail": "Bot is already stopped"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get stop reason from request
        stop_reason = request.data.get("reason", "Stopped via API")

        # Update bot status
        bot.status = BotStatus.STOPPED
        bot.stopped_at = timezone.now()
        bot.stop_reason = stop_reason
        bot.save()

        # Create stop event
        BotEvent.objects.create(
            bot=bot,
            event_type=BotEvent.EventType.STOPPED,
            details={
                "final_pnl": str(bot.current_pnl) if bot.current_pnl else "0",
                "final_value": str(bot.current_value) if bot.current_value else "0",
            },
            reasoning=stop_reason,
        )

        serializer = self.get_serializer(bot)
        return Response(serializer.data)


class TradeListView(UserIsolationMixin, generics.ListAPIView):
    """API view for listing trades.

    Applies user isolation to ensure users only see their own trades.

    Requirements:
    - 4.2: Filter results to only include trades owned by the authenticated user
    """

    serializer_class = TradeSerializer
    pagination_class = StandardPagination
    queryset = Trade.objects.select_related("trading_pair", "signal").all()

    def get_queryset(self):
        """Get trades with optional filtering.

        First applies user isolation via the mixin, then applies additional filters.

        Requirements:
        - 4.2: Filter results to only include trades owned by the authenticated user
        """
        # Get user-filtered queryset from mixin
        queryset = super().get_queryset()

        # Filter by symbol
        symbol = self.request.query_params.get("symbol")
        if symbol:
            queryset = queryset.for_pair(symbol.upper())

        # Filter by side
        side = self.request.query_params.get("side")
        if side:
            if side.upper() == "BUY":
                queryset = queryset.buys()
            elif side.upper() == "SELL":
                queryset = queryset.sells()

        # Filter by simulated status
        is_simulated = self.request.query_params.get("simulated")
        if is_simulated is not None:
            if is_simulated.lower() == "true":
                queryset = queryset.simulated()
            elif is_simulated.lower() == "false":
                queryset = queryset.live()

        # Filter by open/closed status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            if status_filter.lower() == "open":
                queryset = queryset.open_positions()
            elif status_filter.lower() == "closed":
                queryset = queryset.closed()

        # Filter by profitability
        profitable = self.request.query_params.get("profitable")
        if profitable is not None:
            if profitable.lower() == "true":
                queryset = queryset.profitable()
            elif profitable.lower() == "false":
                queryset = queryset.unprofitable()

        # Filter by hours
        hours = self.request.query_params.get("hours")
        if hours:
            try:
                queryset = queryset.recent(int(hours))
            except ValueError:
                pass

        return queryset


class TradeDetailView(UserIsolationMixin, generics.RetrieveAPIView):
    """API view for trade details.

    Applies user isolation to ensure users can only access their own trades.

    Requirements:
    - 4.4: Return 404 for cross-user access attempts
    """

    queryset = Trade.objects.select_related("trading_pair", "signal").all()
    serializer_class = TradeSerializer


class TradeStatisticsView(APIView):
    """API view for trade statistics.

    Filters statistics to only include trades belonging to the authenticated user.

    Requirements:
    - 4.5: Only include trades belonging to the requesting user in statistics
    """

    def get(self, request):
        """Get trade statistics.

        Query params:
            simulated: bool - If true, return simulated trade stats
            symbol: str - Filter by trading pair symbol

        Requirements:
        - 4.5: Only include trades belonging to the requesting user in statistics
        """
        is_simulated = request.query_params.get("simulated", "false").lower() == "true"
        symbol = request.query_params.get("symbol")

        # Start with all trades
        queryset = Trade.objects.all()

        # Apply user filtering (admin bypass)
        if request.user.is_authenticated:
            if not request.user.is_superuser:
                queryset = queryset.filter(user=request.user)
        else:
            # Unauthenticated users get empty results
            queryset = queryset.none()

        if is_simulated:
            queryset = queryset.simulated()
        else:
            queryset = queryset.live()

        if symbol:
            queryset = queryset.for_pair(symbol.upper())

        stats = queryset.statistics()
        serializer = TradeStatisticsSerializer(stats)
        return Response(serializer.data)


class AnalysisView(APIView):
    """API view for latest analysis of a symbol."""

    def get(self, request, symbol):
        """Get the latest analysis for a trading pair."""
        signal = Signal.objects.filter(trading_pair__symbol=symbol.upper()).first()
        if signal:
            serializer = SignalSerializer(signal)
            return Response(serializer.data)
        return Response(
            {"detail": f"No analysis available for {symbol}"},
            status=status.HTTP_404_NOT_FOUND,
        )


class ConfigView(APIView):
    """API view for system configuration."""

    def get(self, request):
        """Get all system configuration.

        Query params:
            key: str - Get specific config by key
        """
        key = request.query_params.get("key")

        if key:
            try:
                config = SystemConfig.objects.get(key=key)
                serializer = SystemConfigSerializer(config)
                return Response(serializer.data)
            except SystemConfig.DoesNotExist:
                return Response(
                    {"detail": f"Configuration key '{key}' not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

        configs = SystemConfig.objects.all()
        serializer = SystemConfigSerializer(configs, many=True)
        return Response(serializer.data)

    def put(self, request):
        """Update system configuration."""
        serializer = SystemConfigUpdateSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        key = serializer.validated_data["key"]
        value = serializer.validated_data["value"]
        description = serializer.validated_data.get("description", "")

        config = SystemConfig.set_value(key, value, description)
        response_serializer = SystemConfigSerializer(config)
        return Response(response_serializer.data)

    def delete(self, request):
        """Delete a configuration key.

        Query params:
            key: str - Config key to delete (required)
        """
        key = request.query_params.get("key")

        if not key:
            return Response(
                {"detail": "Key parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            config = SystemConfig.objects.get(key=key)
            config.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except SystemConfig.DoesNotExist:
            return Response(
                {"detail": f"Configuration key '{key}' not found"},
                status=status.HTTP_404_NOT_FOUND,
            )


class BacktestView(APIView):
    """API view for running backtests."""

    def post(self, request):
        """Run a backtest.

        Note: This is a placeholder implementation. Full backtesting
        functionality will be implemented in task 20.
        """
        serializer = BacktestRequestSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Validate trading pair exists
        symbol = serializer.validated_data["symbol"].upper()
        if not TradingPair.objects.filter(symbol=symbol).exists():
            return Response(
                {"detail": f"Trading pair '{symbol}' not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Placeholder response - actual implementation in task 20
        result = {
            "symbol": symbol,
            "start_date": serializer.validated_data["start_date"],
            "end_date": serializer.validated_data["end_date"],
            "initial_balance": serializer.validated_data["initial_balance"],
            "final_balance": serializer.validated_data["initial_balance"],
            "total_return": 0.0,
            "total_trades": 0,
            "win_rate": 0.0,
            "max_drawdown": 0.0,
            "sharpe_ratio": None,
            "sortino_ratio": None,
            "trades": [],
            "message": "Backtesting functionality will be fully implemented in task 20",
        }

        return Response(result, status=status.HTTP_200_OK)


class TokenGenerateView(APIView):
    """API view for generating authentication tokens.

    Generates a new token for the authenticated user. If the user already has
    a token, returns the existing token.

    Requirements:
    - 9.1: Support token-based authentication for API access using TokenAuthentication
    - 9.2: Generate a unique token associated with the user's account
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Generate or retrieve an API token for the authenticated user.

        Returns the existing token if one exists, otherwise creates a new one.

        Requirements:
        - 9.2: Generate a unique token associated with the user's account
        """
        token, created = Token.objects.get_or_create(user=request.user)

        return Response(
            {
                "token": token.key,
                "created": created,
                "user_id": request.user.id,
                "username": request.user.username,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class TokenRegenerateView(APIView):
    """API view for regenerating authentication tokens.

    Invalidates the user's existing token and generates a new one.

    Requirements:
    - 9.6: Invalidate the previous token when regenerating
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Regenerate the API token for the authenticated user.

        Deletes the existing token (if any) and creates a new one.
        This invalidates any clients using the old token.

        Requirements:
        - 9.6: Invalidate the previous token when regenerating
        """
        # Delete existing token if it exists
        Token.objects.filter(user=request.user).delete()

        # Create a new token
        token = Token.objects.create(user=request.user)

        return Response(
            {
                "token": token.key,
                "regenerated": True,
                "user_id": request.user.id,
                "username": request.user.username,
                "message": "Token regenerated successfully. Previous token has been invalidated.",
            },
            status=status.HTTP_201_CREATED,
        )
