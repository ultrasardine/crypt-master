"""
Core views including health check endpoint and settings management.
"""

import json
import os

from django.contrib import messages
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views.generic import FormView, TemplateView, View

from .models import SystemConfig


def health_check(request):
    """
    Health check endpoint for Docker/Kubernetes health probes.

    Returns:
        - 200 OK if the application is healthy
        - 503 Service Unavailable if database is unreachable
    """
    health_status = {
        "status": "healthy",
        "database": "ok",
    }

    # Check database connectivity
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["database"] = f"error: {str(e)}"
        return JsonResponse(health_status, status=503)

    return JsonResponse(health_status, status=200)


class SettingsView(TemplateView):
    """Main settings view for configuration management."""

    template_name = "core/settings.html"

    def get_context_data(self, **kwargs):
        """Add configuration data to context."""
        context = super().get_context_data(**kwargs)

        # Get all system configurations
        context["configs"] = SystemConfig.objects.all()

        # Default configuration values with descriptions
        default_configs = {
            "dry_run_mode": {
                "value": True,
                "description": "Enable dry-run mode (simulated trading)",
                "type": "boolean",
            },
            "min_confidence_threshold": {
                "value": 85.0,
                "description": "Minimum confidence score to execute trades (0-100)",
                "type": "number",
            },
            "max_position_pct": {
                "value": 10.0,
                "description": "Maximum position size as percentage of portfolio",
                "type": "number",
            },
            "max_drawdown_pct": {
                "value": 20.0,
                "description": "Maximum drawdown before halting trading",
                "type": "number",
            },
            "max_risk_per_trade": {
                "value": 2.0,
                "description": "Maximum risk per trade as percentage of portfolio",
                "type": "number",
            },
            "bot_loss_threshold": {
                "value": 10.0,
                "description": "Bot P&L threshold for auto-stop (negative percentage)",
                "type": "number",
            },
            "analysis_interval_seconds": {
                "value": 300,
                "description": "Interval between market analysis cycles (seconds)",
                "type": "integer",
            },
            "technical_weight": {
                "value": 0.6,
                "description": "Weight for technical indicators in confidence scoring",
                "type": "number",
            },
            "sentiment_weight": {
                "value": 0.3,
                "description": "Weight for sentiment analysis in confidence scoring",
                "type": "number",
            },
            "news_weight": {
                "value": 0.1,
                "description": "Weight for news sentiment in confidence scoring",
                "type": "number",
            },
        }

        # Merge defaults with stored values
        config_display = []
        for key, default in default_configs.items():
            stored = SystemConfig.get_value(key)
            config_display.append(
                {
                    "key": key,
                    "value": stored if stored is not None else default["value"],
                    "default": default["value"],
                    "description": default["description"],
                    "type": default["type"],
                    "is_default": stored is None,
                }
            )

        context["config_display"] = config_display

        # API key status (check if environment variables are set)
        context["api_key_configured"] = bool(os.environ.get("PIONEX_API_KEY"))
        context["api_secret_configured"] = bool(os.environ.get("PIONEX_API_SECRET"))

        # System status
        context["dry_run_mode"] = SystemConfig.get_value("dry_run_mode", default=True)

        return context


class SettingsUpdateView(View):
    """View for updating a single configuration value."""

    def post(self, request):
        """Update configuration value."""
        key = request.POST.get("key")
        value = request.POST.get("value")
        config_type = request.POST.get("type", "string")

        if not key:
            messages.error(request, "Configuration key is required.")
            return redirect("core:settings")

        # Convert value based on type
        try:
            if config_type == "boolean":
                value = value.lower() in ("true", "1", "yes", "on")
            elif config_type == "number":
                value = float(value)
            elif config_type == "integer":
                value = int(value)
            elif config_type == "json":
                value = json.loads(value)
        except (ValueError, json.JSONDecodeError) as e:
            messages.error(request, f"Invalid value format: {e}")
            return redirect("core:settings")

        # Get description from existing config or use empty
        existing = SystemConfig.objects.filter(key=key).first()
        description = existing.description if existing else ""

        # Update or create the configuration
        SystemConfig.set_value(key, value, description)
        messages.success(request, f"Configuration '{key}' updated successfully.")

        return redirect("core:settings")


class SettingsResetView(View):
    """View for resetting a configuration to default."""

    def post(self, request):
        """Reset configuration to default by deleting it."""
        key = request.POST.get("key")

        if not key:
            messages.error(request, "Configuration key is required.")
            return redirect("core:settings")

        try:
            config = SystemConfig.objects.get(key=key)
            config.delete()
            messages.success(request, f"Configuration '{key}' reset to default.")
        except SystemConfig.DoesNotExist:
            messages.info(request, f"Configuration '{key}' is already at default.")

        return redirect("core:settings")


class APIKeySetupView(TemplateView):
    """View for API key setup instructions."""

    template_name = "core/api_key_setup.html"

    def get_context_data(self, **kwargs):
        """Add API key status to context."""
        context = super().get_context_data(**kwargs)

        # Check current API key status
        context["api_key_configured"] = bool(os.environ.get("PIONEX_API_KEY"))
        context["api_secret_configured"] = bool(os.environ.get("PIONEX_API_SECRET"))

        # Mask the API key if set (show only first/last 4 chars)
        api_key = os.environ.get("PIONEX_API_KEY", "")
        if api_key and len(api_key) > 8:
            context["api_key_masked"] = f"{api_key[:4]}...{api_key[-4:]}"
        elif api_key:
            context["api_key_masked"] = "****"
        else:
            context["api_key_masked"] = None

        return context


class TradingModeToggleView(View):
    """View for toggling between dry-run and live trading modes."""

    def post(self, request):
        """Toggle trading mode."""
        current_mode = SystemConfig.get_value("dry_run_mode", default=True)
        new_mode = not current_mode

        # Require confirmation for switching to live mode
        if not new_mode:  # Switching to live mode
            confirm = request.POST.get("confirm")
            if confirm != "LIVE":
                messages.warning(
                    request,
                    "To enable live trading, type 'LIVE' in the confirmation field.",
                )
                return redirect("core:settings")

        SystemConfig.set_value(
            "dry_run_mode",
            new_mode,
            "Enable dry-run mode (simulated trading)",
        )

        mode_name = "Dry-Run" if new_mode else "Live"
        messages.success(request, f"Trading mode changed to {mode_name}.")

        return redirect("core:settings")
