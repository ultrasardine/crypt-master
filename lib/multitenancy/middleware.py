"""
Login required middleware for portal authentication.

This middleware enforces authentication for all portal pages except
explicitly excluded paths (login, registration, public pages).

Requirements:
- 8.1: Support Django's built-in session authentication for portal access
- 8.4: Require authentication for all pages except login and registration
- 8.5: Redirect unauthenticated users to the login page
"""

import re
from collections.abc import Callable
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect


class LoginRequiredMiddleware:
    """
    Middleware that requires authentication for all portal pages.

    This middleware checks if the user is authenticated for each request.
    If not authenticated and the path is not in the excluded list,
    the user is redirected to the login page.

    Excluded paths:
    - Login and logout pages
    - Registration page
    - Health check endpoint
    - API endpoints (use token authentication)
    - Admin pages (have their own authentication)
    - Static files

    Requirements:
    - 8.4: THE portal SHALL require authentication for all pages except login and registration
    - 8.5: WHEN an unauthenticated user accesses a protected page,
           THE system SHALL redirect to the login page
    """

    # Default paths that don't require authentication
    DEFAULT_PUBLIC_PATHS: list[str] = [
        r"^/accounts/login/?$",
        r"^/accounts/logout/?$",
        r"^/accounts/register/?$",
        r"^/health/?$",
        r"^/api/",  # API uses token authentication
        r"^/admin/",  # Admin has its own authentication
        r"^/static/",  # Static files
        r"^/__debug__/",  # Django debug toolbar
    ]

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        """
        Initialize the middleware.

        Args:
            get_response: The next middleware or view in the chain.
        """
        self.get_response = get_response

        # Compile regex patterns for public paths
        # Allow customization via settings
        public_paths = getattr(settings, "LOGIN_EXEMPT_URLS", self.DEFAULT_PUBLIC_PATHS)
        self.public_path_patterns = [re.compile(pattern) for pattern in public_paths]

        # Get login URL from settings, default to Django's standard
        self.login_url = getattr(settings, "LOGIN_URL", "/accounts/login/")

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """
        Process the request and enforce authentication.

        Args:
            request: The incoming HTTP request.

        Returns:
            The response from the next middleware/view, or a redirect to login.
        """
        # Check if the path is public (doesn't require authentication)
        if self._is_public_path(request.path):
            return self.get_response(request)

        # Check if user is authenticated
        if request.user.is_authenticated:
            return self.get_response(request)

        # User is not authenticated and path requires authentication
        # Redirect to login page with next parameter
        return self._redirect_to_login(request)

    def _is_public_path(self, path: str) -> bool:
        """
        Check if the given path is public (doesn't require authentication).

        Args:
            path: The request path to check.

        Returns:
            True if the path is public, False otherwise.
        """
        for pattern in self.public_path_patterns:
            if pattern.match(path):
                return True
        return False

    def _redirect_to_login(self, request: HttpRequest) -> HttpResponse:
        """
        Redirect the user to the login page.

        Includes the original path as the 'next' parameter so the user
        can be redirected back after successful login.

        Args:
            request: The incoming HTTP request.

        Returns:
            A redirect response to the login page.
        """
        # Build the redirect URL with the 'next' parameter
        next_url = request.get_full_path()

        # Don't include 'next' for the root path to avoid redirect loops
        if next_url == "/" or next_url == self.login_url:
            return redirect(self.login_url)

        return redirect(f"{self.login_url}?next={next_url}")


def get_login_required_middleware_class() -> type[LoginRequiredMiddleware]:
    """
    Factory function to get the LoginRequiredMiddleware class.

    This allows for easy testing and customization.

    Returns:
        The LoginRequiredMiddleware class.
    """
    return LoginRequiredMiddleware
