"""
Core app URL configuration.
"""

from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("health/", views.health_check, name="health_check"),
    path("settings/", views.SettingsView.as_view(), name="settings"),
    path("settings/update/", views.SettingsUpdateView.as_view(), name="settings_update"),
    path("settings/reset/", views.SettingsResetView.as_view(), name="settings_reset"),
    path("settings/api-keys/", views.APIKeySetupView.as_view(), name="api_key_setup"),
    path("settings/toggle-mode/", views.TradingModeToggleView.as_view(), name="toggle_mode"),
]
