"""REST API serializers."""

from rest_framework import serializers

from apps.bots.models import Bot, BotEvent
from apps.core.models import PortfolioSnapshot, SystemConfig, TradingPair
from apps.trading.models import Signal, Trade


class TradingPairSerializer(serializers.ModelSerializer):
    """Serializer for TradingPair model."""

    class Meta:
        model = TradingPair
        fields = [
            "id",
            "symbol",
            "base_currency",
            "quote_currency",
            "is_active",
            "min_quantity",
            "max_quantity",
            "price_precision",
            "quantity_precision",
        ]


class PortfolioSerializer(serializers.ModelSerializer):
    """Serializer for PortfolioSnapshot model."""

    class Meta:
        model = PortfolioSnapshot
        fields = [
            "id",
            "total_value",
            "available_balance",
            "allocated_to_bots",
            "drawdown",
            "high_water_mark",
            "is_simulated",
            "created_at",
        ]


class SignalSerializer(serializers.ModelSerializer):
    """Serializer for Signal model."""

    trading_pair = TradingPairSerializer(read_only=True)
    trading_pair_id = serializers.PrimaryKeyRelatedField(
        queryset=TradingPair.objects.all(),
        source="trading_pair",
        write_only=True,
        required=False,
    )

    class Meta:
        model = Signal
        fields = [
            "id",
            "trading_pair",
            "trading_pair_id",
            "direction",
            "confidence",
            "indicators",
            "reasoning",
            "executed",
            "executed_at",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class BotEventSerializer(serializers.ModelSerializer):
    """Serializer for BotEvent model."""

    class Meta:
        model = BotEvent
        fields = [
            "id",
            "event_type",
            "details",
            "reasoning",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class BotSerializer(serializers.ModelSerializer):
    """Serializer for Bot model."""

    trading_pair = TradingPairSerializer(read_only=True)
    trading_pair_id = serializers.PrimaryKeyRelatedField(
        queryset=TradingPair.objects.all(),
        source="trading_pair",
        write_only=True,
        required=False,
    )
    events = BotEventSerializer(many=True, read_only=True)

    class Meta:
        model = Bot
        fields = [
            "id",
            "pionex_bot_id",
            "bot_type",
            "trading_pair",
            "trading_pair_id",
            "status",
            "invested_amount",
            "current_value",
            "current_pnl",
            "pnl_percent",
            "params",
            "is_simulated",
            "created_at",
            "stopped_at",
            "stop_reason",
            "events",
        ]
        read_only_fields = [
            "id",
            "pionex_bot_id",
            "current_value",
            "current_pnl",
            "pnl_percent",
            "created_at",
            "stopped_at",
            "events",
        ]


class BotCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new bot."""

    trading_pair_id = serializers.PrimaryKeyRelatedField(
        queryset=TradingPair.objects.all(),
        source="trading_pair",
    )

    class Meta:
        model = Bot
        fields = [
            "bot_type",
            "trading_pair_id",
            "invested_amount",
            "params",
            "is_simulated",
        ]

    def validate_invested_amount(self, value):
        """Validate invested amount is positive."""
        if value <= 0:
            raise serializers.ValidationError("Invested amount must be positive.")
        return value

    def validate_bot_type(self, value):
        """Validate bot type is supported."""
        from apps.bots.models import BotType

        valid_types = [choice[0] for choice in BotType.choices]
        if value not in valid_types:
            raise serializers.ValidationError(
                f"Invalid bot type. Must be one of: {', '.join(valid_types)}"
            )
        return value


class TradeSerializer(serializers.ModelSerializer):
    """Serializer for Trade model."""

    trading_pair = TradingPairSerializer(read_only=True)
    signal = SignalSerializer(read_only=True)

    class Meta:
        model = Trade
        fields = [
            "id",
            "signal",
            "trading_pair",
            "side",
            "entry_price",
            "exit_price",
            "quantity",
            "pnl",
            "pnl_percent",
            "is_simulated",
            "order_id",
            "created_at",
            "closed_at",
            "notes",
        ]
        read_only_fields = ["id", "created_at"]


class TradeStatisticsSerializer(serializers.Serializer):
    """Serializer for trade statistics."""

    total_trades = serializers.IntegerField()
    open_positions = serializers.IntegerField()
    closed_trades = serializers.IntegerField()
    profitable_trades = serializers.IntegerField()
    unprofitable_trades = serializers.IntegerField()
    total_pnl = serializers.DecimalField(max_digits=20, decimal_places=10)
    win_rate = serializers.FloatField()


class SystemConfigSerializer(serializers.ModelSerializer):
    """Serializer for SystemConfig model."""

    class Meta:
        model = SystemConfig
        fields = ["id", "key", "value", "description", "updated_at"]
        read_only_fields = ["id", "updated_at"]


class SystemConfigUpdateSerializer(serializers.Serializer):
    """Serializer for updating system configuration."""

    key = serializers.CharField(max_length=100)
    value = serializers.JSONField()
    description = serializers.CharField(required=False, allow_blank=True, default="")


class BacktestRequestSerializer(serializers.Serializer):
    """Serializer for backtest request."""

    symbol = serializers.CharField(max_length=20)
    start_date = serializers.DateTimeField()
    end_date = serializers.DateTimeField()
    initial_balance = serializers.DecimalField(max_digits=20, decimal_places=8)
    strategy_params = serializers.JSONField(required=False, default=dict)

    def validate(self, data):
        """Validate backtest parameters."""
        if data["start_date"] >= data["end_date"]:
            raise serializers.ValidationError("start_date must be before end_date")
        if data["initial_balance"] <= 0:
            raise serializers.ValidationError("initial_balance must be positive")
        return data


class BacktestResultSerializer(serializers.Serializer):
    """Serializer for backtest results."""

    symbol = serializers.CharField()
    start_date = serializers.DateTimeField()
    end_date = serializers.DateTimeField()
    initial_balance = serializers.DecimalField(max_digits=20, decimal_places=8)
    final_balance = serializers.DecimalField(max_digits=20, decimal_places=8)
    total_return = serializers.FloatField()
    total_trades = serializers.IntegerField()
    win_rate = serializers.FloatField()
    max_drawdown = serializers.FloatField()
    sharpe_ratio = serializers.FloatField(allow_null=True)
    sortino_ratio = serializers.FloatField(allow_null=True)
    trades = TradeSerializer(many=True)
