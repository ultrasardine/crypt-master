"""Unit tests for Regime Detector view."""

import json
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.test import Client, RequestFactory
from django.urls import reverse
from django.utils import timezone

from apps.analysis.views import RegimeDetectorView
from apps.core.models import MarketContextSnapshot
from lib.analysis.context import Regime


@pytest.mark.django_db
class TestRegimeDetectorView:
    """Test RegimeDetectorView functionality."""

    @pytest.fixture
    def user(self):
        """Create a test user."""
        return User.objects.create_user(username="testuser", password="testpass")

    @pytest.fixture
    def client(self, user):
        """Create an authenticated test client."""
        client = Client()
        client.login(username="testuser", password="testpass")
        return client

    @pytest.fixture
    def view(self, user):
        """Create a view instance with authenticated request."""
        factory = RequestFactory()
        request = factory.get("/analysis/regimes/")
        request.user = user
        view = RegimeDetectorView()
        view.request = request
        view.setup(request)
        return view

    @pytest.fixture
    def sample_snapshot(self):
        """Create a sample MarketContextSnapshot."""
        return MarketContextSnapshot.objects.create(
            timestamp=timezone.now(),
            symbol="BTC_USDT",
            regime=Regime.RISK_ON.value,
            trend_strength_score=0.75,
            risk_regime_score=0.65,
            sentiment_regime_score=0.80,
            fear_greed_index=72,
            btc_dominance=45.5,
            is_stale=False,
            is_degraded=False,
        )

    # =========================================================================
    # Test view response structure
    # =========================================================================

    def test_view_returns_200_for_authenticated_user(self, client):
        """Test that authenticated users can access the view."""
        response = client.get(reverse("analysis:regimes"))
        assert response.status_code == 200

    def test_view_redirects_unauthenticated_user(self):
        """Test that unauthenticated users are redirected to login."""
        client = Client()
        response = client.get(reverse("analysis:regimes"))
        assert response.status_code == 302
        assert "/login/" in response.url or "/accounts/login/" in response.url

    def test_view_uses_correct_template(self, client):
        """Test that the view uses the correct template."""
        response = client.get(reverse("analysis:regimes"))
        assert "analysis/regimes.html" in [t.name for t in response.templates]

    def test_context_contains_required_keys(self, client, sample_snapshot):
        """Test that context contains all required keys."""
        response = client.get(reverse("analysis:regimes"))
        context = response.context

        assert "selected_days" in context
        assert "time_range_options" in context
        assert "latest_snapshot" in context
        assert "regime_history" in context
        assert "regime_transitions" in context
        assert "all_regime_colors" in context

    def test_context_contains_regime_colors_when_snapshot_exists(self, client, sample_snapshot):
        """Test that regime colors are in context when snapshot exists."""
        response = client.get(reverse("analysis:regimes"))
        context = response.context

        assert "regime_colors" in context
        assert "regime_display" in context
        assert "context_scores" in context

    def test_context_scores_structure(self, client, sample_snapshot):
        """Test that context scores have correct structure."""
        response = client.get(reverse("analysis:regimes"))
        context = response.context

        scores = context["context_scores"]
        assert "trend_strength" in scores
        assert "risk_regime" in scores
        assert "sentiment_regime" in scores

        # Each score should have value, percentage, and label
        for key in ["trend_strength", "risk_regime", "sentiment_regime"]:
            assert "value" in scores[key]
            assert "percentage" in scores[key]
            assert "label" in scores[key]

    # =========================================================================
    # Test time-range filtering
    # =========================================================================

    def test_default_time_range_is_7_days(self, client):
        """Test that default time range is 7 days."""
        response = client.get(reverse("analysis:regimes"))
        assert response.context["selected_days"] == 7

    def test_time_range_7_days(self, client):
        """Test filtering with 7 days time range."""
        response = client.get(reverse("analysis:regimes") + "?days=7")
        assert response.context["selected_days"] == 7

    def test_time_range_30_days(self, client):
        """Test filtering with 30 days time range."""
        response = client.get(reverse("analysis:regimes") + "?days=30")
        assert response.context["selected_days"] == 30

    def test_invalid_time_range_defaults_to_7(self, client):
        """Test that invalid time range defaults to 7 days."""
        response = client.get(reverse("analysis:regimes") + "?days=invalid")
        assert response.context["selected_days"] == 7

    def test_unsupported_time_range_defaults_to_7(self, client):
        """Test that unsupported time range values default to 7 days."""
        response = client.get(reverse("analysis:regimes") + "?days=14")
        assert response.context["selected_days"] == 7

    def test_regime_history_filtered_by_time_range(self, client, user):
        """Test that regime history is filtered by selected time range."""
        # Clean up any existing snapshots from other tests
        MarketContextSnapshot.objects.all().delete()
        
        now = timezone.now()

        # Create snapshot within 7 days
        MarketContextSnapshot.objects.create(
            timestamp=now - timedelta(days=3),
            symbol="BTC_USDT",
            regime=Regime.RISK_ON.value,
        )

        # Create snapshot outside 7 days but within 30 days
        MarketContextSnapshot.objects.create(
            timestamp=now - timedelta(days=15),
            symbol="BTC_USDT",
            regime=Regime.RISK_OFF.value,
        )

        # Test 7 days filter
        response = client.get(reverse("analysis:regimes") + "?days=7")
        history = json.loads(response.context["regime_history"])
        assert len(history) == 1
        assert history[0]["regime"] == Regime.RISK_ON.value

        # Test 30 days filter
        response = client.get(reverse("analysis:regimes") + "?days=30")
        history = json.loads(response.context["regime_history"])
        assert len(history) == 2

    # =========================================================================
    # Test authentication requirement
    # =========================================================================

    def test_login_required_mixin_applied(self, user):
        """Test that LoginRequiredMixin is applied to the view."""
        from django.contrib.auth.mixins import LoginRequiredMixin

        assert issubclass(RegimeDetectorView, LoginRequiredMixin)

    def test_unauthenticated_request_redirects(self):
        """Test that unauthenticated requests are redirected."""
        client = Client()
        response = client.get(reverse("analysis:regimes"))
        assert response.status_code == 302

    # =========================================================================
    # Test regime display formatting
    # =========================================================================

    def test_regime_display_formatting(self, view):
        """Test that regime values are formatted correctly for display."""
        assert view._format_regime_display("RISK_ON") == "Risk On"
        assert view._format_regime_display("RISK_OFF") == "Risk Off"
        assert view._format_regime_display("RANGE_BOUND") == "Range Bound"
        assert view._format_regime_display("TRENDING_UP") == "Trending Up"
        assert view._format_regime_display("TRENDING_DOWN") == "Trending Down"
        assert view._format_regime_display("UNKNOWN") == "Unknown"

    def test_to_percentage_conversion(self, view):
        """Test score to percentage conversion."""
        assert view._to_percentage(0.0) == 0
        assert view._to_percentage(0.5) == 50
        assert view._to_percentage(1.0) == 100
        assert view._to_percentage(0.75) == 75
        assert view._to_percentage(None) == 0

    # =========================================================================
    # Test regime colors
    # =========================================================================

    def test_regime_colors_mapping(self, view):
        """Test that all regimes have color mappings."""
        for regime in Regime:
            assert regime.value in view.REGIME_COLORS
            colors = view.REGIME_COLORS[regime.value]
            assert "bg" in colors
            assert "text" in colors
            assert "border" in colors
            assert "dot" in colors

    def test_risk_on_colors(self, view):
        """Test RISK_ON regime colors are emerald."""
        colors = view.REGIME_COLORS[Regime.RISK_ON.value]
        assert "emerald" in colors["bg"]
        assert "emerald" in colors["text"]

    def test_risk_off_colors(self, view):
        """Test RISK_OFF regime colors are red."""
        colors = view.REGIME_COLORS[Regime.RISK_OFF.value]
        assert "red" in colors["bg"]
        assert "red" in colors["text"]

    def test_range_bound_colors(self, view):
        """Test RANGE_BOUND regime colors are slate."""
        colors = view.REGIME_COLORS[Regime.RANGE_BOUND.value]
        assert "slate" in colors["bg"]
        assert "slate" in colors["text"]

    def test_trending_up_colors(self, view):
        """Test TRENDING_UP regime colors are sky."""
        colors = view.REGIME_COLORS[Regime.TRENDING_UP.value]
        assert "sky" in colors["bg"]
        assert "sky" in colors["text"]

    def test_trending_down_colors(self, view):
        """Test TRENDING_DOWN regime colors are amber."""
        colors = view.REGIME_COLORS[Regime.TRENDING_DOWN.value]
        assert "amber" in colors["bg"]
        assert "amber" in colors["text"]

    # =========================================================================
    # Test regime transitions
    # =========================================================================

    def test_regime_transitions_detected(self, client, user):
        """Test that regime transitions are correctly detected."""
        # Clean up any existing snapshots from other tests
        MarketContextSnapshot.objects.all().delete()
        
        now = timezone.now()

        # Create snapshots with regime changes
        MarketContextSnapshot.objects.create(
            timestamp=now - timedelta(hours=3),
            symbol="BTC_USDT",
            regime=Regime.RISK_ON.value,
        )
        MarketContextSnapshot.objects.create(
            timestamp=now - timedelta(hours=2),
            symbol="BTC_USDT",
            regime=Regime.RISK_OFF.value,
        )
        MarketContextSnapshot.objects.create(
            timestamp=now - timedelta(hours=1),
            symbol="BTC_USDT",
            regime=Regime.TRENDING_UP.value,
        )

        response = client.get(reverse("analysis:regimes"))
        transitions = response.context["regime_transitions"]

        # Should have 2 transitions
        assert len(transitions) == 2

        # Most recent transition first
        assert transitions[0]["from_regime"] == Regime.RISK_OFF.value
        assert transitions[0]["to_regime"] == Regime.TRENDING_UP.value

    def test_no_transitions_when_regime_unchanged(self, client, user):
        """Test that no transitions are detected when regime stays the same."""
        # Clean up any existing snapshots from other tests
        MarketContextSnapshot.objects.all().delete()
        
        now = timezone.now()

        # Create snapshots with same regime
        for i in range(3):
            MarketContextSnapshot.objects.create(
                timestamp=now - timedelta(hours=i),
                symbol="BTC_USDT",
                regime=Regime.RISK_ON.value,
            )

        response = client.get(reverse("analysis:regimes"))
        transitions = response.context["regime_transitions"]

        assert len(transitions) == 0

    # =========================================================================
    # Test empty state
    # =========================================================================

    def test_empty_state_when_no_snapshots(self, client):
        """Test view handles empty state gracefully."""
        # Clean up any existing snapshots from other tests
        MarketContextSnapshot.objects.all().delete()
        
        response = client.get(reverse("analysis:regimes"))
        context = response.context

        assert context["latest_snapshot"] is None
        assert json.loads(context["regime_history"]) == []
        assert context["regime_transitions"] == []

    # =========================================================================
    # Test stale data indicator
    # =========================================================================

    def test_stale_snapshot_indicated(self, client, user):
        """Test that stale snapshots are indicated in context."""
        MarketContextSnapshot.objects.create(
            timestamp=timezone.now(),
            symbol="BTC_USDT",
            regime=Regime.UNKNOWN.value,
            is_stale=True,
            is_degraded=True,
        )

        response = client.get(reverse("analysis:regimes"))
        snapshot = response.context["latest_snapshot"]

        assert snapshot.is_stale is True
        assert snapshot.is_degraded is True
