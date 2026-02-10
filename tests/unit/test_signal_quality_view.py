"""Unit tests for Signal Quality view."""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.test import Client, RequestFactory
from django.urls import reverse
from django.utils import timezone

from apps.analysis.views import SignalQualityView
from apps.core.models import TradingPair
from apps.trading.models import Signal, SignalOutcome, StrategyPattern
from lib.analysis.context import Regime


@pytest.mark.django_db
class TestSignalQualityView:
    """Test SignalQualityView functionality."""

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
        request = factory.get("/analysis/signal-quality/")
        request.user = user
        view = SignalQualityView()
        view.request = request
        view.setup(request)
        return view

    @pytest.fixture
    def trading_pair(self):
        """Create a test trading pair."""
        return TradingPair.objects.create(
            symbol="BTC_USDT",
            base_currency="BTC",
            quote_currency="USDT",
            is_active=True,
        )

    @pytest.fixture
    def sample_signal_outcome(self, trading_pair):
        """Create a sample signal with outcome."""
        signal = Signal.objects.create(
            trading_pair=trading_pair,
            direction="BUY",
            confidence=85.0,
            regime=Regime.RISK_ON.value,
            indicators=[{"name": "RSI", "value": 35, "signal": "BUY"}],
        )
        return SignalOutcome.objects.create(
            signal=signal,
            final_pnl_percent=5.5,
            is_profitable=True,
            recorded_at=timezone.now(),
        )

    @pytest.fixture
    def sample_strategy_pattern(self):
        """Create a sample strategy pattern."""
        return StrategyPattern.objects.create(
            feature_combination={
                "regime": Regime.TRENDING_UP.value,
                "rsi_range": [30, 50],
                "adx_min": 25,
            },
            sample_size=50,
            average_pnl=3.5,
            hit_rate=0.65,
            is_active=True,
        )

    # =========================================================================
    # Test view response structure
    # =========================================================================

    def test_view_returns_200_for_authenticated_user(self, client):
        """Test that authenticated users can access the view."""
        response = client.get(reverse("analysis:signal_quality"))
        assert response.status_code == 200

    def test_view_redirects_unauthenticated_user(self):
        """Test that unauthenticated users are redirected to login."""
        client = Client()
        response = client.get(reverse("analysis:signal_quality"))
        assert response.status_code == 302
        assert "/login/" in response.url or "/accounts/login/" in response.url

    def test_view_uses_correct_template(self, client):
        """Test that the view uses the correct template."""
        response = client.get(reverse("analysis:signal_quality"))
        assert "analysis/signal_quality.html" in [t.name for t in response.templates]

    def test_context_contains_required_keys(self, client, sample_signal_outcome):
        """Test that context contains all required keys."""
        response = client.get(reverse("analysis:signal_quality"))
        context = response.context

        assert "selected_days" in context
        assert "selected_symbol" in context
        assert "selected_regime" in context
        assert "time_range_options" in context
        assert "trading_pairs" in context
        assert "regime_options" in context
        assert "all_regime_colors" in context
        assert "regime_performance" in context
        assert "indicator_performance" in context
        assert "strategy_patterns" in context
        assert "summary_stats" in context

    def test_summary_stats_structure(self, client, sample_signal_outcome):
        """Test that summary stats have correct structure."""
        response = client.get(reverse("analysis:signal_quality"))
        context = response.context

        stats = context["summary_stats"]
        assert "total_signals" in stats
        assert "overall_win_rate" in stats
        assert "overall_avg_pnl" in stats
        assert "profitable_signals" in stats
        assert "unprofitable_signals" in stats

    # =========================================================================
    # Test filtering functionality
    # =========================================================================

    def test_default_time_range_is_30_days(self, client):
        """Test that default time range is 30 days."""
        response = client.get(reverse("analysis:signal_quality"))
        assert response.context["selected_days"] == 30

    def test_time_range_7_days(self, client):
        """Test filtering with 7 days time range."""
        response = client.get(reverse("analysis:signal_quality") + "?days=7")
        assert response.context["selected_days"] == 7

    def test_time_range_30_days(self, client):
        """Test filtering with 30 days time range."""
        response = client.get(reverse("analysis:signal_quality") + "?days=30")
        assert response.context["selected_days"] == 30

    def test_time_range_90_days(self, client):
        """Test filtering with 90 days time range."""
        response = client.get(reverse("analysis:signal_quality") + "?days=90")
        assert response.context["selected_days"] == 90

    def test_invalid_time_range_defaults_to_30(self, client):
        """Test that invalid time range defaults to 30 days."""
        response = client.get(reverse("analysis:signal_quality") + "?days=invalid")
        assert response.context["selected_days"] == 30

    def test_unsupported_time_range_defaults_to_30(self, client):
        """Test that unsupported time range values default to 30 days."""
        response = client.get(reverse("analysis:signal_quality") + "?days=14")
        assert response.context["selected_days"] == 30

    def test_symbol_filter(self, client, trading_pair, sample_signal_outcome):
        """Test filtering by symbol."""
        response = client.get(
            reverse("analysis:signal_quality") + f"?symbol={trading_pair.symbol}"
        )
        assert response.context["selected_symbol"] == trading_pair.symbol

    def test_regime_filter(self, client, sample_signal_outcome):
        """Test filtering by regime."""
        response = client.get(
            reverse("analysis:signal_quality") + f"?regime={Regime.RISK_ON.value}"
        )
        assert response.context["selected_regime"] == Regime.RISK_ON.value

    def test_combined_filters(self, client, trading_pair, sample_signal_outcome):
        """Test combining multiple filters."""
        url = (
            reverse("analysis:signal_quality")
            + f"?days=7&symbol={trading_pair.symbol}&regime={Regime.RISK_ON.value}"
        )
        response = client.get(url)
        context = response.context

        assert context["selected_days"] == 7
        assert context["selected_symbol"] == trading_pair.symbol
        assert context["selected_regime"] == Regime.RISK_ON.value

    # =========================================================================
    # Test authentication requirement
    # =========================================================================

    def test_login_required_mixin_applied(self, user):
        """Test that LoginRequiredMixin is applied to the view."""
        from django.contrib.auth.mixins import LoginRequiredMixin

        assert issubclass(SignalQualityView, LoginRequiredMixin)

    def test_unauthenticated_request_redirects(self):
        """Test that unauthenticated requests are redirected."""
        client = Client()
        response = client.get(reverse("analysis:signal_quality"))
        assert response.status_code == 302

    # =========================================================================
    # Test regime performance calculation
    # =========================================================================

    def test_regime_performance_calculation(self, client, trading_pair, user):
        """Test that regime performance is calculated correctly."""
        # Create signals with outcomes for different regimes
        for regime in [Regime.RISK_ON.value, Regime.RISK_OFF.value]:
            for i in range(3):
                signal = Signal.objects.create(
                    trading_pair=trading_pair,
                    direction="BUY",
                    confidence=80.0 + i,
                    regime=regime,
                    indicators=[],
                )
                SignalOutcome.objects.create(
                    signal=signal,
                    final_pnl_percent=5.0 if i < 2 else -3.0,
                    is_profitable=i < 2,
                    recorded_at=timezone.now(),
                )

        response = client.get(reverse("analysis:signal_quality"))
        regime_perf = response.context["regime_performance"]

        # Should have 2 regimes
        assert len(regime_perf) == 2

        # Each regime should have correct structure
        for perf in regime_perf:
            assert "regime" in perf
            assert "regime_display" in perf
            assert "win_rate" in perf
            assert "avg_pnl" in perf
            assert "total_signals" in perf
            assert "avg_confidence" in perf
            assert "colors" in perf

    def test_regime_performance_win_rate(self, client, trading_pair, user):
        """Test that win rate is calculated correctly."""
        # Create 2 profitable and 1 unprofitable signal
        for i in range(3):
            signal = Signal.objects.create(
                trading_pair=trading_pair,
                direction="BUY",
                confidence=80.0,
                regime=Regime.TRENDING_UP.value,
                indicators=[],
            )
            SignalOutcome.objects.create(
                signal=signal,
                final_pnl_percent=5.0 if i < 2 else -3.0,
                is_profitable=i < 2,
                recorded_at=timezone.now(),
            )

        response = client.get(reverse("analysis:signal_quality"))
        regime_perf = response.context["regime_performance"]

        # Find TRENDING_UP regime
        trending_up = next(
            (p for p in regime_perf if p["regime"] == Regime.TRENDING_UP.value), None
        )
        assert trending_up is not None
        assert trending_up["win_rate"] == pytest.approx(66.7, rel=0.1)
        assert trending_up["total_signals"] == 3

    # =========================================================================
    # Test strategy patterns display
    # =========================================================================

    def test_strategy_patterns_displayed(self, client, sample_strategy_pattern):
        """Test that active strategy patterns are displayed."""
        response = client.get(reverse("analysis:signal_quality"))
        patterns = response.context["strategy_patterns"]

        assert len(patterns) >= 1
        pattern = patterns[0]
        assert pattern.hit_rate == 0.65
        assert pattern.average_pnl == 3.5
        assert pattern.sample_size == 50

    def test_inactive_patterns_not_displayed(self, client):
        """Test that inactive strategy patterns are not displayed."""
        # Create inactive pattern
        StrategyPattern.objects.create(
            feature_combination={"regime": Regime.RISK_OFF.value},
            sample_size=30,
            average_pnl=2.0,
            hit_rate=0.55,
            is_active=False,
        )

        response = client.get(reverse("analysis:signal_quality"))
        patterns = response.context["strategy_patterns"]

        # Should not include inactive patterns
        for pattern in patterns:
            assert pattern.is_active is True

    def test_patterns_filtered_by_regime(self, client):
        """Test that patterns are filtered by regime when filter is applied."""
        # Create patterns for different regimes
        StrategyPattern.objects.create(
            feature_combination={"regime": Regime.RISK_ON.value},
            sample_size=30,
            average_pnl=2.0,
            hit_rate=0.55,
            is_active=True,
        )
        StrategyPattern.objects.create(
            feature_combination={"regime": Regime.RISK_OFF.value},
            sample_size=25,
            average_pnl=1.5,
            hit_rate=0.52,
            is_active=True,
        )

        # Filter by RISK_ON
        response = client.get(
            reverse("analysis:signal_quality") + f"?regime={Regime.RISK_ON.value}"
        )
        patterns = response.context["strategy_patterns"]

        # Should only include RISK_ON patterns
        for pattern in patterns:
            assert pattern.feature_combination.get("regime") == Regime.RISK_ON.value

    # =========================================================================
    # Test empty state
    # =========================================================================

    def test_empty_state_when_no_outcomes(self, client):
        """Test view handles empty state gracefully."""
        response = client.get(reverse("analysis:signal_quality"))
        context = response.context

        assert context["regime_performance"] == []
        assert context["indicator_performance"] == []
        assert context["summary_stats"]["total_signals"] == 0

    # =========================================================================
    # Test indicator combination extraction
    # =========================================================================

    def test_indicator_combo_extraction(self, view, trading_pair):
        """Test that indicator combinations are extracted correctly."""
        signal = Signal.objects.create(
            trading_pair=trading_pair,
            direction="BUY",
            confidence=80.0,
            regime=Regime.RISK_ON.value,
            indicators=[
                {"name": "RSI", "value": 25, "signal": "BUY"},
                {"name": "FGI", "value": 20, "signal": "BUY"},
            ],
        )

        combo = view._extract_indicator_combo(signal)
        assert "RSI oversold" in combo
        assert "FGI extreme fear" in combo

    def test_indicator_combo_with_regime(self, view, trading_pair):
        """Test that regime is included in indicator combination."""
        signal = Signal.objects.create(
            trading_pair=trading_pair,
            direction="BUY",
            confidence=80.0,
            regime=Regime.TRENDING_UP.value,
            indicators=[],
        )

        combo = view._extract_indicator_combo(signal)
        assert "Trending Up" in combo

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
