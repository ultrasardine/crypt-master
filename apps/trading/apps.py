"""Trading app configuration."""

from django.apps import AppConfig


class TradingConfig(AppConfig):
    """Configuration for the trading app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.trading"
    verbose_name = "Trading"
