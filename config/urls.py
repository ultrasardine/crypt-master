"""
URL configuration for crypt-master project.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Health check endpoint (for Docker/Kubernetes probes)
    path("", include("apps.core.urls")),
    # Admin
    path("admin/", admin.site.urls),
    # Application routes
    path("", include("apps.dashboard.urls")),
    path("trading/", include("apps.trading.urls")),
    path("bots/", include("apps.bots.urls")),
    path("analysis/", include("apps.analysis.urls")),
    path("api/v1/", include("apps.api.urls")),
]
