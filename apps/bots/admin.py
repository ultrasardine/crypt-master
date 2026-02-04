"""Admin configuration for bot models."""

from django.contrib import admin

from .models import Bot, BotEvent


@admin.register(Bot)
class BotAdmin(admin.ModelAdmin):
    """Admin for Bot model."""

    list_display = [
        "pionex_bot_id",
        "bot_type",
        "trading_pair",
        "status",
        "invested_amount",
        "current_pnl",
        "pnl_percent",
        "is_simulated",
        "created_at",
    ]
    list_filter = ["bot_type", "status", "is_simulated", "trading_pair"]
    search_fields = ["pionex_bot_id", "trading_pair__symbol"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(BotEvent)
class BotEventAdmin(admin.ModelAdmin):
    """Admin for BotEvent model."""

    list_display = ["bot", "event_type", "created_at"]
    list_filter = ["event_type"]
    search_fields = ["bot__pionex_bot_id"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at"]
