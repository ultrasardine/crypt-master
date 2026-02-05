"""
URL configuration for crypt-master project.
"""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    # Health check endpoint (for Docker/Kubernetes probes)
    path("", include("apps.core.urls")),
    # Admin
    path("admin/", admin.site.urls),
    # Authentication URLs
    # Requirements:
    # - 8.1: Support Django's built-in session authentication for portal access
    # - 8.2: Create a session and redirect to the dashboard on login
    # - 8.3: Invalidate the session and clear cookies on logout
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path(
        "accounts/logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),
    # Application routes
    path("", include("apps.dashboard.urls")),
    path("trading/", include("apps.trading.urls")),
    path("bots/", include("apps.bots.urls")),
    path("analysis/", include("apps.analysis.urls")),
    path("api/v1/", include("apps.api.urls")),
]
