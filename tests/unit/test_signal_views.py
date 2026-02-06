"""Unit tests for signal views."""

import pytest
from decimal import Decimal
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.bots.models import Bot
from apps.core.models import TradingPair, UserProfile
from apps.trading.models import Signal, SignalDirection, SignalOutcome


@pytest.mark.django_db
class TestSignalListView:
    """Test SignalListView with outcome column."""

    @pytest.fixture
    def user(self):
        """Create a test user with profile."""
        user = User.objects.create_user(username="testuser", password="testpass")
        # Update the auto-created profile with active trading pairs
        user.profile.active_trading_pairs = ["BTC_USDT"]
        user.profile.save()
        return user

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
    def client(self, user):
        """Create authenticated client."""
        client = Client()
        client.force_login(user)
        return client

    def test_signal_list_displays_outcome_column(self, client, user, trading_pair):
        """Test that signal list displays outcome column."""
        # Create a signal with outcome
        signal = Signal.objects.create(
            trading_pair=trading_pair,
            direction=SignalDirection.BUY,
            confidence=90.0,
            executed=True,
            executed_at=timezone.now(),
        )

        bot = Bot.objects.create(
            user=user,
            trading_pair=trading_pair,
            pionex_bot_id="test_bot",
            bot_type="GRID",
            status="STOPPED",
            invested_amount=Decimal("1000.00"),
            current_value=Decimal("1100.00"),
            current_pnl=Decimal("100.00"),
            pnl_percent=10.0,
            stopped_at=timezone.now(),
        )

        SignalOutcome.objects.create(
            signal=signal,
            bot=bot,
            final_pnl=Decimal("100.00"),
            final_pnl_percent=10.0,
            is_profitable=True,
            bot_duration_hours=24.0,
        )

        # Get the signal list page
        response = client.get(reverse("trading:signal_list"))

        assert response.status_code == 200
        assert "Outcome" in response.content.decode()
        assert "+10.00%" in response.content.decode()

    def test_signal_list_shows_pending_for_unexecuted_signals(self, client, trading_pair):
        """Test that unexecuted signals show pending in outcome column."""
        # Create a pending signal
        Signal.objects.create(
            trading_pair=trading_pair,
            direction=SignalDirection.BUY,
            confidence=85.0,
            executed=False,
        )

        response = client.get(reverse("trading:signal_list"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "Outcome" in content
        # Should show "-" for pending signals
        assert 'text-slate-400">-</span>' in content

    def test_signal_list_shows_in_progress_for_executed_without_outcome(
        self, client, trading_pair
    ):
        """Test that executed signals without outcome show 'In Progress'."""
        # Create an executed signal without outcome
        Signal.objects.create(
            trading_pair=trading_pair,
            direction=SignalDirection.BUY,
            confidence=88.0,
            executed=True,
            executed_at=timezone.now(),
        )

        response = client.get(reverse("trading:signal_list"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "In Progress" in content

    def test_signal_list_displays_negative_outcome(self, client, user, trading_pair):
        """Test that signal list displays negative outcomes correctly."""
        # Create a signal with negative outcome
        signal = Signal.objects.create(
            trading_pair=trading_pair,
            direction=SignalDirection.SELL,
            confidence=92.0,
            executed=True,
            executed_at=timezone.now(),
        )

        bot = Bot.objects.create(
            user=user,
            trading_pair=trading_pair,
            pionex_bot_id="test_bot_2",
            bot_type="DCA",
            status="STOPPED",
            invested_amount=Decimal("2000.00"),
            current_value=Decimal("1800.00"),
            current_pnl=Decimal("-200.00"),
            pnl_percent=-10.0,
            stopped_at=timezone.now(),
        )

        SignalOutcome.objects.create(
            signal=signal,
            bot=bot,
            final_pnl=Decimal("-200.00"),
            final_pnl_percent=-10.0,
            is_profitable=False,
            bot_duration_hours=48.0,
        )

        response = client.get(reverse("trading:signal_list"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "-10.00%" in content
        # Should use red color for negative outcome
        assert "text-red-400" in content

    def test_signal_list_tooltip_shows_bot_details(self, client, user, trading_pair):
        """Test that hovering over outcome shows bot details in tooltip."""
        # Create a signal with outcome
        signal = Signal.objects.create(
            trading_pair=trading_pair,
            direction=SignalDirection.BUY,
            confidence=90.0,
            executed=True,
            executed_at=timezone.now(),
        )

        bot = Bot.objects.create(
            user=user,
            trading_pair=trading_pair,
            pionex_bot_id="test_bot",
            bot_type="GRID",
            status="STOPPED",
            invested_amount=Decimal("1000.00"),
            current_value=Decimal("1100.00"),
            current_pnl=Decimal("100.00"),
            pnl_percent=10.0,
            stopped_at=timezone.now(),
        )

        SignalOutcome.objects.create(
            signal=signal,
            bot=bot,
            final_pnl=Decimal("100.00"),
            final_pnl_percent=10.0,
            is_profitable=True,
            bot_duration_hours=24.0,
        )

        response = client.get(reverse("trading:signal_list"))

        assert response.status_code == 200
        content = response.content.decode()
        # Check tooltip content
        assert "Bot Outcome" in content
        assert "Final P&L:" in content
        assert "Duration:" in content
        assert "24.0h" in content
        assert "Bot Type:" in content
        assert "GRID" in content

