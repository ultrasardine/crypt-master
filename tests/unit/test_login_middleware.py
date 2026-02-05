"""
Unit tests for LoginRequiredMiddleware.

Tests the middleware that enforces authentication for portal pages.

Requirements:
- 8.4: THE portal SHALL require authentication for all pages except login and registration
- 8.5: WHEN an unauthenticated user accesses a protected page,
       THE system SHALL redirect to the login page
"""

import pytest
from django.contrib.auth.models import AnonymousUser, User
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory

from lib.multitenancy.middleware import LoginRequiredMiddleware


@pytest.fixture
def request_factory() -> RequestFactory:
    """Create a Django request factory."""
    return RequestFactory()


@pytest.fixture
def mock_get_response():
    """Create a mock get_response callable."""

    def get_response(request: HttpRequest) -> HttpResponse:
        return HttpResponse("OK", status=200)

    return get_response


@pytest.fixture
def middleware(mock_get_response) -> LoginRequiredMiddleware:
    """Create a LoginRequiredMiddleware instance."""
    return LoginRequiredMiddleware(mock_get_response)


@pytest.fixture
def authenticated_user(db) -> User:
    """Create an authenticated user."""
    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )


class TestLoginRequiredMiddleware:
    """Tests for LoginRequiredMiddleware."""

    def test_authenticated_user_can_access_protected_page(
        self,
        middleware: LoginRequiredMiddleware,
        request_factory: RequestFactory,
        authenticated_user: User,
    ) -> None:
        """
        Test that authenticated users can access protected pages.

        Requirements: 8.4
        """
        request = request_factory.get("/")
        request.user = authenticated_user

        response = middleware(request)

        assert response.status_code == 200
        assert response.content == b"OK"

    def test_unauthenticated_user_redirected_from_protected_page(
        self,
        middleware: LoginRequiredMiddleware,
        request_factory: RequestFactory,
    ) -> None:
        """
        Test that unauthenticated users are redirected to login.

        Requirements: 8.5
        """
        request = request_factory.get("/bots/")
        request.user = AnonymousUser()

        response = middleware(request)

        assert response.status_code == 302
        assert "/accounts/login/" in response.url
        assert "next=/bots/" in response.url

    def test_login_page_accessible_without_auth(
        self,
        middleware: LoginRequiredMiddleware,
        request_factory: RequestFactory,
    ) -> None:
        """
        Test that the login page is accessible without authentication.

        Requirements: 8.4
        """
        request = request_factory.get("/accounts/login/")
        request.user = AnonymousUser()

        response = middleware(request)

        assert response.status_code == 200

    def test_logout_page_accessible_without_auth(
        self,
        middleware: LoginRequiredMiddleware,
        request_factory: RequestFactory,
    ) -> None:
        """
        Test that the logout page is accessible without authentication.

        Requirements: 8.4
        """
        request = request_factory.get("/accounts/logout/")
        request.user = AnonymousUser()

        response = middleware(request)

        assert response.status_code == 200

    def test_registration_page_accessible_without_auth(
        self,
        middleware: LoginRequiredMiddleware,
        request_factory: RequestFactory,
    ) -> None:
        """
        Test that the registration page is accessible without authentication.

        Requirements: 8.4
        """
        request = request_factory.get("/accounts/register/")
        request.user = AnonymousUser()

        response = middleware(request)

        assert response.status_code == 200

    def test_health_check_accessible_without_auth(
        self,
        middleware: LoginRequiredMiddleware,
        request_factory: RequestFactory,
    ) -> None:
        """
        Test that the health check endpoint is accessible without authentication.

        Requirements: 8.4
        """
        request = request_factory.get("/health/")
        request.user = AnonymousUser()

        response = middleware(request)

        assert response.status_code == 200

    def test_api_endpoints_accessible_without_session_auth(
        self,
        middleware: LoginRequiredMiddleware,
        request_factory: RequestFactory,
    ) -> None:
        """
        Test that API endpoints are not blocked by the middleware.

        API endpoints use token authentication, not session authentication.

        Requirements: 8.4
        """
        request = request_factory.get("/api/v1/bots/")
        request.user = AnonymousUser()

        response = middleware(request)

        # API should pass through middleware (token auth handles it)
        assert response.status_code == 200

    def test_admin_pages_accessible_without_session_auth(
        self,
        middleware: LoginRequiredMiddleware,
        request_factory: RequestFactory,
    ) -> None:
        """
        Test that admin pages are not blocked by the middleware.

        Admin has its own authentication mechanism.

        Requirements: 8.4
        """
        request = request_factory.get("/admin/")
        request.user = AnonymousUser()

        response = middleware(request)

        # Admin should pass through middleware (admin auth handles it)
        assert response.status_code == 200

    def test_static_files_accessible_without_auth(
        self,
        middleware: LoginRequiredMiddleware,
        request_factory: RequestFactory,
    ) -> None:
        """
        Test that static files are accessible without authentication.

        Requirements: 8.4
        """
        request = request_factory.get("/static/css/style.css")
        request.user = AnonymousUser()

        response = middleware(request)

        assert response.status_code == 200

    def test_redirect_includes_next_parameter(
        self,
        middleware: LoginRequiredMiddleware,
        request_factory: RequestFactory,
    ) -> None:
        """
        Test that redirect includes the original URL as 'next' parameter.

        Requirements: 8.5
        """
        request = request_factory.get("/trading/signals/?filter=buy")
        request.user = AnonymousUser()

        response = middleware(request)

        assert response.status_code == 302
        assert "next=/trading/signals/" in response.url

    def test_root_path_redirect_no_next_parameter(
        self,
        middleware: LoginRequiredMiddleware,
        request_factory: RequestFactory,
    ) -> None:
        """
        Test that root path redirect doesn't include 'next' parameter.

        This prevents redirect loops.

        Requirements: 8.5
        """
        request = request_factory.get("/")
        request.user = AnonymousUser()

        response = middleware(request)

        assert response.status_code == 302
        assert response.url == "/accounts/login/"
        assert "next=" not in response.url

    def test_dashboard_requires_auth(
        self,
        middleware: LoginRequiredMiddleware,
        request_factory: RequestFactory,
    ) -> None:
        """
        Test that the dashboard page requires authentication.

        Requirements: 8.4, 8.5
        """
        request = request_factory.get("/")
        request.user = AnonymousUser()

        response = middleware(request)

        assert response.status_code == 302
        assert "/accounts/login/" in response.url

    def test_bots_page_requires_auth(
        self,
        middleware: LoginRequiredMiddleware,
        request_factory: RequestFactory,
    ) -> None:
        """
        Test that the bots page requires authentication.

        Requirements: 8.4, 8.5
        """
        request = request_factory.get("/bots/")
        request.user = AnonymousUser()

        response = middleware(request)

        assert response.status_code == 302
        assert "/accounts/login/" in response.url

    def test_trading_page_requires_auth(
        self,
        middleware: LoginRequiredMiddleware,
        request_factory: RequestFactory,
    ) -> None:
        """
        Test that the trading page requires authentication.

        Requirements: 8.4, 8.5
        """
        request = request_factory.get("/trading/signals/")
        request.user = AnonymousUser()

        response = middleware(request)

        assert response.status_code == 302
        assert "/accounts/login/" in response.url

    def test_analysis_page_requires_auth(
        self,
        middleware: LoginRequiredMiddleware,
        request_factory: RequestFactory,
    ) -> None:
        """
        Test that the analysis page requires authentication.

        Requirements: 8.4, 8.5
        """
        request = request_factory.get("/analysis/")
        request.user = AnonymousUser()

        response = middleware(request)

        assert response.status_code == 302
        assert "/accounts/login/" in response.url

    def test_settings_page_requires_auth(
        self,
        middleware: LoginRequiredMiddleware,
        request_factory: RequestFactory,
    ) -> None:
        """
        Test that the settings page requires authentication.

        Requirements: 8.4, 8.5
        """
        request = request_factory.get("/settings/")
        request.user = AnonymousUser()

        response = middleware(request)

        assert response.status_code == 302
        assert "/accounts/login/" in response.url


class TestPublicPathPatterns:
    """Tests for public path pattern matching."""

    def test_is_public_path_login(
        self,
        middleware: LoginRequiredMiddleware,
    ) -> None:
        """Test login path is recognized as public."""
        assert middleware._is_public_path("/accounts/login/") is True
        assert middleware._is_public_path("/accounts/login") is True

    def test_is_public_path_logout(
        self,
        middleware: LoginRequiredMiddleware,
    ) -> None:
        """Test logout path is recognized as public."""
        assert middleware._is_public_path("/accounts/logout/") is True
        assert middleware._is_public_path("/accounts/logout") is True

    def test_is_public_path_register(
        self,
        middleware: LoginRequiredMiddleware,
    ) -> None:
        """Test registration path is recognized as public."""
        assert middleware._is_public_path("/accounts/register/") is True
        assert middleware._is_public_path("/accounts/register") is True

    def test_is_public_path_health(
        self,
        middleware: LoginRequiredMiddleware,
    ) -> None:
        """Test health check path is recognized as public."""
        assert middleware._is_public_path("/health/") is True
        assert middleware._is_public_path("/health") is True

    def test_is_public_path_api(
        self,
        middleware: LoginRequiredMiddleware,
    ) -> None:
        """Test API paths are recognized as public."""
        assert middleware._is_public_path("/api/v1/bots/") is True
        assert middleware._is_public_path("/api/v1/signals/") is True
        assert middleware._is_public_path("/api/v1/trades/") is True

    def test_is_public_path_admin(
        self,
        middleware: LoginRequiredMiddleware,
    ) -> None:
        """Test admin paths are recognized as public."""
        assert middleware._is_public_path("/admin/") is True
        assert middleware._is_public_path("/admin/auth/user/") is True

    def test_is_public_path_static(
        self,
        middleware: LoginRequiredMiddleware,
    ) -> None:
        """Test static file paths are recognized as public."""
        assert middleware._is_public_path("/static/css/style.css") is True
        assert middleware._is_public_path("/static/js/app.js") is True

    def test_is_not_public_path_protected(
        self,
        middleware: LoginRequiredMiddleware,
    ) -> None:
        """Test protected paths are not recognized as public."""
        assert middleware._is_public_path("/") is False
        assert middleware._is_public_path("/bots/") is False
        assert middleware._is_public_path("/trading/signals/") is False
        assert middleware._is_public_path("/analysis/") is False
        assert middleware._is_public_path("/settings/") is False
