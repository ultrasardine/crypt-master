"""Admin configuration for trading models."""

from django.contrib import admin

from lib.multitenancy.admin import AdminAuditMixin

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
class TradeAdmin(AdminAuditMixin, admin.ModelAdmin):
    """Admin for Trade model with audit logging."""

    list_display = [
        "trading_pair",
        "user",
        "side",
        "quantity",
        "entry_price",
        "exit_price",
        "pnl",
        "is_simulated",
        "created_at",
    ]
    list_filter = ["user", "side", "is_simulated", "trading_pair"]
    search_fields = ["trading_pair__symbol", "order_id", "user__username"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at", "updated_at"]
