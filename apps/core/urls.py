"""
Core app URL configuration.

Includes routes for:
- Health check endpoint
- System settings management
- User registration and profile management
- API key and token management
"""

from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    # Health check
    path("health/", views.health_check, name="health_check"),
    # System settings
    path("settings/", views.SettingsView.as_view(), name="settings"),
    path("settings/update/", views.SettingsUpdateView.as_view(), name="settings_update"),
    path("settings/reset/", views.SettingsResetView.as_view(), name="settings_reset"),
    path("settings/api-keys/", views.APIKeySetupView.as_view(), name="api_key_setup"),
    path("settings/toggle-mode/", views.TradingModeToggleView.as_view(), name="toggle_mode"),
    # User registration
    path("register/", views.UserRegistrationView.as_view(), name="register"),
    # User profile management
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path("profile/edit/", views.ProfileEditView.as_view(), name="profile_edit"),
    # API key management
    path("profile/api-keys/", views.APIKeyManagementView.as_view(), name="api_key_management"),
    path("profile/api-keys/clear/", views.APIKeyClearView.as_view(), name="api_key_clear"),
    # API token management
    path("profile/api-token/", views.APITokenView.as_view(), name="api_token"),
    path(
        "profile/api-token/generate/",
        views.APITokenGenerateView.as_view(),
        name="api_token_generate",
    ),
    path(
        "profile/api-token/regenerate/",
        views.APITokenRegenerateView.as_view(),
        name="api_token_regenerate",
    ),
    # Trading pairs
    path(
        "profile/fetch-pionex-symbols/",
        views.FetchPionexSymbolsView.as_view(),
        name="fetch_pionex_symbols",
    ),
]
