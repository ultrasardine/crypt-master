"""Bots app configuration."""

from django.apps import AppConfig


class BotsConfig(AppConfig):
    """Configuration for the bots app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.bots"
    verbose_name = "Bots"
