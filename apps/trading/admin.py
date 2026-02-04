"""Admin configuration for trading models."""

from django.contrib import admin

from .models import Signal, Trade


@admin.register(Signal)
class SignalAdmin(admin.ModelAdmin):
    """Admin for Signal model."""

    list_display = [
        "trading_pair",
        "direction",
        "confidence",
        "executed",
        "created_at",
    ]
    list_filter = ["direction", "executed", "trading_pair"]
    search_fields = ["trading_pair__symbol"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    """Admin for Trade model."""

    list_display = [
        "trading_pair",
        "side",
        "quantity",
        "entry_price",
        "exit_price",
        "pnl",
        "is_simulated",
        "created_at",
    ]
    list_filter = ["side", "is_simulated", "trading_pair"]
    search_fields = ["trading_pair__symbol", "order_id"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at", "updated_at"]
