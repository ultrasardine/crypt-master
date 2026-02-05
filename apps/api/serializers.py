"""REST API serializers."""

from rest_framework import serializers

from apps.bots.models import Bot, BotEvent
from apps.core.models import PortfolioSnapshot, SystemConfig, TradingPair, UserProfile
from apps.trading.models import Signal, Trade
from lib.crypto.api_key_manager import APIKeyValidationError


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


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for UserProfile model.

    This serializer excludes all encrypted fields and provides write-only
    fields for API key submission. Decrypted API keys are never exposed
    through this serializer.

    Requirements:
    - 1.4: Display all non-sensitive settings without exposing encrypted data
    - 2.4: Never expose decrypted API keys through any API endpoint or serializer
    """

    # Read-only field to indicate if API keys are configured
    has_api_keys = serializers.BooleanField(read_only=True)

    # Write-only fields for API key submission
    api_key = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        help_text="Pionex API key (write-only, 16-64 alphanumeric characters)",
    )
    api_secret = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        help_text="Pionex API secret (write-only, 16-64 alphanumeric characters)",
    )

    # Username from related User model (read-only)
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = UserProfile
        fields = [
            "id",
            "username",
            "email",
            "has_api_keys",
            "api_key",
            "api_secret",
            "default_trading_mode",
            "risk_tolerance",
            "notification_email_enabled",
            "active_trading_pairs",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "username",
            "email",
            "has_api_keys",
            "created_at",
            "updated_at",
        ]
        # Explicitly exclude encrypted fields - they should never be serialized
        # Note: These fields are not in 'fields' list, so they won't be included

    def validate(self, attrs):
        """
        Validate that both api_key and api_secret are provided together.

        If one is provided, the other must also be provided.
        """
        api_key = attrs.get("api_key", "")
        api_secret = attrs.get("api_secret", "")

        # If either is provided, both must be provided
        if api_key and not api_secret:
            raise serializers.ValidationError(
                {"api_secret": "API secret is required when providing API key."}
            )
        if api_secret and not api_key:
            raise serializers.ValidationError(
                {"api_key": "API key is required when providing API secret."}
            )

        return attrs

    def update(self, instance, validated_data):
        """
        Update UserProfile instance.

        Handles API key encryption separately from other fields.
        """
        # Extract API credentials from validated data
        api_key = validated_data.pop("api_key", None)
        api_secret = validated_data.pop("api_secret", None)

        # Update regular fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Handle API credentials separately
        if api_key and api_secret:
            try:
                instance.set_api_credentials(api_key, api_secret)
            except APIKeyValidationError as e:
                raise serializers.ValidationError({"api_key": str(e)})

        return instance


class UserProfileAPIKeySerializer(serializers.Serializer):
    """
    Serializer for API key management operations.

    Used for setting or clearing API credentials.

    Requirements:
    - 2.4: Never expose decrypted API keys through any API endpoint
    - 2.5: Securely overwrite previous encrypted values on update
    - 2.6: Securely remove encrypted data on deletion
    """

    api_key = serializers.CharField(
        required=True,
        min_length=16,
        max_length=64,
        help_text="Pionex API key (16-64 alphanumeric characters)",
    )
    api_secret = serializers.CharField(
        required=True,
        min_length=16,
        max_length=64,
        help_text="Pionex API secret (16-64 alphanumeric characters)",
    )

    def validate_api_key(self, value):
        """Validate API key format."""
        from lib.crypto.api_key_manager import APIKeyManager

        manager = APIKeyManager(master_key="validation-only")
        if not manager.validate_api_key_format(value):
            raise serializers.ValidationError(
                "Invalid API key format. Must be 16-128 alphanumeric characters."
            )
        return value

    def validate_api_secret(self, value):
        """Validate API secret format."""
        from lib.crypto.api_key_manager import APIKeyManager

        manager = APIKeyManager(master_key="validation-only")
        if not manager.validate_api_key_format(value):
            raise serializers.ValidationError(
                "Invalid API secret format. Must be 16-128 alphanumeric characters."
            )
        return value
