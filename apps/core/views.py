"""
Core views including health check endpoint, settings management,
user registration, and profile management.

Requirements:
- 1.1: Create UserProfile with default settings on user registration
- 1.2: Persist user preference changes
- 1.3: Store user preferences (trading mode, notifications, risk tolerance)
- 1.4: Display all non-sensitive settings without exposing encrypted data
- 2.5: Securely overwrite previous encrypted values on update
- 2.6: Securely remove encrypted data on deletion
- 9.2: Generate a unique token associated with the user's account
- 9.6: Invalidate the previous token when regenerating
"""

import json
import os

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, FormView, TemplateView, UpdateView, View
from rest_framework.authtoken.models import Token

from .forms import APIKeyForm, UserProfileForm, UserRegistrationForm
from .models import SystemConfig, UserProfile


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



class UserRegistrationView(CreateView):
    """
    View for user registration.

    Creates a new user account and automatically creates a UserProfile
    with default settings via the post_save signal.

    Requirements:
    - 1.1: Create UserProfile with default settings on user registration
    """

    form_class = UserRegistrationForm
    template_name = "registration/register.html"
    success_url = reverse_lazy("dashboard:home")

    def dispatch(self, request, *args, **kwargs):
        """Redirect authenticated users to dashboard."""
        if request.user.is_authenticated:
            return redirect("dashboard:home")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        """
        Save the user and log them in.

        The UserProfile is automatically created via the post_save signal.
        """
        user = form.save()
        login(self.request, user)
        messages.success(
            self.request,
            f"Welcome to Crypt Master, {user.username}! Your account has been created.",
        )
        return redirect(self.success_url)


class ProfileView(LoginRequiredMixin, TemplateView):
    """
    View for displaying user profile.

    Shows user settings and API key status without exposing encrypted data.

    Requirements:
    - 1.4: Display all non-sensitive settings without exposing encrypted data
    """

    template_name = "core/profile.html"

    def get_context_data(self, **kwargs):
        """Add profile data to context."""
        context = super().get_context_data(**kwargs)
        profile = self.request.user.profile

        context["profile"] = profile
        context["has_api_keys"] = profile.has_api_keys()

        # Get API token if it exists
        try:
            token = Token.objects.get(user=self.request.user)
            # Mask the token for display (show first 8 and last 4 chars)
            if len(token.key) > 12:
                context["api_token_masked"] = f"{token.key[:8]}...{token.key[-4:]}"
            else:
                context["api_token_masked"] = "****"
            context["has_api_token"] = True
        except Token.DoesNotExist:
            context["has_api_token"] = False
            context["api_token_masked"] = None

        return context


class ProfileEditView(LoginRequiredMixin, UpdateView):
    """
    View for editing user profile settings.

    Allows users to update their preferences (trading mode, risk tolerance, etc.)

    Requirements:
    - 1.2: Persist user preference changes
    - 1.3: Store user preferences (trading mode, notifications, risk tolerance)
    """

    model = UserProfile
    form_class = UserProfileForm
    template_name = "core/profile_edit.html"
    success_url = reverse_lazy("core:profile")

    def get_object(self, queryset=None):
        """Return the current user's profile."""
        return self.request.user.profile

    def form_valid(self, form):
        """Save the profile and show success message."""
        form.save()
        messages.success(self.request, "Profile settings updated successfully.")
        return redirect(self.success_url)


class APIKeyManagementView(LoginRequiredMixin, FormView):
    """
    View for managing Pionex API credentials.

    Allows users to set or update their API keys.

    Requirements:
    - 2.5: Securely overwrite previous encrypted values on update
    """

    form_class = APIKeyForm
    template_name = "core/api_key_management.html"
    success_url = reverse_lazy("core:profile")

    def get_context_data(self, **kwargs):
        """Add API key status to context."""
        context = super().get_context_data(**kwargs)
        context["has_api_keys"] = self.request.user.profile.has_api_keys()
        return context

    def form_valid(self, form):
        """Save API credentials to the user's profile."""
        try:
            form.save(self.request.user.profile)
            messages.success(self.request, "API credentials saved successfully.")
        except Exception as e:
            messages.error(self.request, f"Failed to save API credentials: {e}")
            return self.form_invalid(form)
        return redirect(self.success_url)


class APIKeyClearView(LoginRequiredMixin, View):
    """
    View for clearing API credentials.

    Requirements:
    - 2.6: Securely remove encrypted data on deletion
    """

    def post(self, request):
        """Clear the user's API credentials."""
        profile = request.user.profile

        if not profile.has_api_keys():
            messages.info(request, "No API credentials to clear.")
        else:
            profile.clear_api_credentials()
            messages.success(request, "API credentials cleared successfully.")

        return redirect("core:profile")


class APITokenView(LoginRequiredMixin, TemplateView):
    """
    View for managing API tokens.

    Displays the user's API token and allows regeneration.

    Requirements:
    - 9.2: Generate a unique token associated with the user's account
    - 9.6: Invalidate the previous token when regenerating
    """

    template_name = "core/api_token.html"

    def get_context_data(self, **kwargs):
        """Add token data to context."""
        context = super().get_context_data(**kwargs)

        try:
            token = Token.objects.get(user=self.request.user)
            context["token"] = token.key
            context["has_token"] = True
        except Token.DoesNotExist:
            context["token"] = None
            context["has_token"] = False

        return context


class APITokenGenerateView(LoginRequiredMixin, View):
    """
    View for generating a new API token.

    Requirements:
    - 9.2: Generate a unique token associated with the user's account
    """

    def post(self, request):
        """Generate a new API token for the user."""
        token, created = Token.objects.get_or_create(user=request.user)

        if created:
            messages.success(request, "API token generated successfully.")
        else:
            messages.info(request, "You already have an API token.")

        return redirect("core:api_token")


class APITokenRegenerateView(LoginRequiredMixin, View):
    """
    View for regenerating the API token.

    Invalidates the existing token and creates a new one.

    Requirements:
    - 9.6: Invalidate the previous token when regenerating
    """

    def post(self, request):
        """Regenerate the user's API token."""
        # Delete existing token
        Token.objects.filter(user=request.user).delete()

        # Create new token
        Token.objects.create(user=request.user)

        messages.success(
            request,
            "API token regenerated successfully. Previous token has been invalidated.",
        )
        return redirect("core:api_token")
