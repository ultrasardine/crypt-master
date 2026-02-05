"""Admin configuration for core models."""

from django.contrib import admin

from lib.multitenancy.admin import AdminAuditMixin

from .models import PortfolioSnapshot, SystemConfig, TradingPair


@admin.register(TradingPair)
class TradingPairAdmin(admin.ModelAdmin):
    """Admin for TradingPair model."""

    list_display = ["symbol", "base_currency", "quote_currency", "is_active", "created_at"]
    list_filter = ["is_active", "quote_currency"]
    search_fields = ["symbol", "base_currency"]
    ordering = ["symbol"]


@admin.register(PortfolioSnapshot)
class PortfolioSnapshotAdmin(AdminAuditMixin, admin.ModelAdmin):
    """Admin for PortfolioSnapshot model with audit logging."""

    list_display = [
        "created_at",
        "user",
        "total_value",
        "available_balance",
        "allocated_to_bots",
        "drawdown",
        "is_simulated",
    ]
    list_filter = ["user", "is_simulated"]
    search_fields = ["user__username"]
    ordering = ["-created_at"]


@admin.register(SystemConfig)
class SystemConfigAdmin(admin.ModelAdmin):
    """Admin for SystemConfig model."""

    list_display = ["key", "value", "updated_at"]
    search_fields = ["key", "description"]
    ordering = ["key"]
