"""Analysis app configuration."""

from django.apps import AppConfig


class AnalysisConfig(AppConfig):
    """Configuration for the analysis app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.analysis"
    verbose_name = "Analysis"
