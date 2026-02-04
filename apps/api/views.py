"""REST API views."""

import uuid
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.bots.models import Bot, BotEvent, BotStatus
from apps.core.models import PortfolioSnapshot, SystemConfig, TradingPair
from apps.trading.models import Signal, Trade

from .serializers import (
    BacktestRequestSerializer,
    BacktestResultSerializer,
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
    """API view for current portfolio state."""

    def get(self, request):
        """Get the latest portfolio snapshot.
        
        Query params:
            simulated: bool - If true, return simulated portfolio
        """
        is_simulated = request.query_params.get("simulated", "false").lower() == "true"
        
        if is_simulated:
            snapshot = PortfolioSnapshot.objects.latest_simulated()
        else:
            snapshot = PortfolioSnapshot.objects.latest_live()
        
        if snapshot:
            serializer = PortfolioSerializer(snapshot)
            return Response(serializer.data)
        return Response(
            {"detail": "No portfolio snapshot available"},
            status=status.HTTP_404_NOT_FOUND,
        )


class PortfolioHistoryView(generics.ListAPIView):
    """API view for portfolio history."""

    serializer_class = PortfolioSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        """Get portfolio snapshots with optional filtering."""
        queryset = PortfolioSnapshot.objects.all()
        
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
    """API view for listing signals."""

    serializer_class = SignalSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        """Get signals with optional filtering."""
        queryset = Signal.objects.select_related("trading_pair").all()
        
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


class BotListView(generics.ListCreateAPIView):
    """API view for listing and creating bots."""

    pagination_class = StandardPagination

    def get_serializer_class(self):
        """Return appropriate serializer based on request method."""
        if self.request.method == "POST":
            return BotCreateSerializer
        return BotSerializer

    def get_queryset(self):
        """Get bots with optional filtering."""
        queryset = Bot.objects.select_related("trading_pair").prefetch_related("events").all()
        
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
        """Create a new bot with generated pionex_bot_id."""
        # Generate a unique bot ID (in real implementation, this would come from Pionex API)
        pionex_bot_id = f"sim_{uuid.uuid4().hex[:16]}" if serializer.validated_data.get("is_simulated", False) else f"bot_{uuid.uuid4().hex[:16]}"
        
        bot = serializer.save(
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


class BotDetailView(generics.RetrieveDestroyAPIView):
    """API view for bot details and deletion (stop)."""

    queryset = Bot.objects.select_related("trading_pair").prefetch_related("events").all()
    serializer_class = BotSerializer

    def destroy(self, request, *args, **kwargs):
        """Stop a bot instead of deleting it."""
        bot = self.get_object()
        
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


class TradeListView(generics.ListAPIView):
    """API view for listing trades."""

    serializer_class = TradeSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        """Get trades with optional filtering."""
        queryset = Trade.objects.select_related("trading_pair", "signal").all()
        
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


class TradeDetailView(generics.RetrieveAPIView):
    """API view for trade details."""

    queryset = Trade.objects.select_related("trading_pair", "signal").all()
    serializer_class = TradeSerializer


class TradeStatisticsView(APIView):
    """API view for trade statistics."""

    def get(self, request):
        """Get trade statistics.
        
        Query params:
            simulated: bool - If true, return simulated trade stats
            symbol: str - Filter by trading pair symbol
        """
        is_simulated = request.query_params.get("simulated", "false").lower() == "true"
        symbol = request.query_params.get("symbol")
        
        queryset = Trade.objects.all()
        
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
