"""
Property-based tests for Admin Action Audit Logging.

Feature: multi-tenant-user-isolation
Property 17: Admin Action Audit Logging

These tests use the hypothesis library to verify that admin actions on
user-owned data are properly logged for audit purposes.
"""

from __future__ import annotations

import logging
import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from apps.bots.models import Bot, BotStatus, BotType
from apps.core.models import PortfolioSnapshot, TradingPair
from apps.trading.models import Trade, TradeSide
from lib.multitenancy.admin import AdminAuditMixin, get_admin_audit_log


def create_test_user(username: str = None, is_superuser: bool = False) -> User:
    """Create a test user with a unique username."""
    if username is None:
        username = f"testuser_{uuid.uuid4().hex[:8]}"
    if is_superuser:
        return User.objects.create_superuser(
            username=username,
            email=f"{username}@example.com",
            password="testpass123",
        )
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="testpass123",
    )


@pytest.fixture
def trading_pair(db):
    """Create a trading pair for tests."""
    pair, _ = TradingPair.objects.get_or_create(
        symbol="BTC_USDT",
        defaults={
            "base_currency": "BTC",
            "quote_currency": "USDT",
            "is_active": True,
        },
    )
    return pair


@pytest.fixture
def request_factory():
    """Create a request factory for tests."""
    return RequestFactory()


@pytest.mark.django_db(transaction=True)
class TestAdminActionAuditLogging:
    """
    Property 17: Admin Action Audit Logging

    *For any* admin action that modifies user data, an audit log entry SHALL
    be created containing the admin user ID, action type, and affected record.

    **Validates: Requirements 10.4**
    """

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        action_type=st.sampled_from(["add", "change", "delete"]),
    )
    def test_admin_action_logs_user_data_modification(
        self,
        trading_pair,
        request_factory,
        action_type: str,
    ) -> None:
        """
        Property: Admin actions on user-owned data create audit log entries.

        Feature: multi-tenant-user-isolation, Property 17: Admin Action Audit Logging

        **Validates: Requirements 10.4**
        """
        admin_user = create_test_user(is_superuser=True)
        owner_user = create_test_user()

        try:
            # Create a bot owned by owner_user
            bot = Bot.objects.create(
                user=owner_user,
                pionex_bot_id=f"bot_{uuid.uuid4().hex[:8]}",
                bot_type=BotType.GRID,
                trading_pair=trading_pair,
                status=BotStatus.ACTIVE,
                invested_amount="100.00",
            )

            # Create a mock admin class with the mixin
            class MockBotAdmin(AdminAuditMixin):
                user_field = "user"

                def __init__(self):
                    pass

            mock_admin = MockBotAdmin()

            # Create request as admin
            request = request_factory.post("/admin/bots/bot/")
            request.user = admin_user

            # Capture log output
            with patch("lib.multitenancy.admin.logger") as mock_logger:
                # Call the internal logging method directly
                mock_admin._log_user_data_action(request, bot, action_type)

                # Verify log was called with correct info
                mock_logger.info.assert_called_once()
                call_args = mock_logger.info.call_args

                # Check that log contains required information
                log_message = call_args[0][0]
                assert "admin_user_id" in log_message
                assert "action" in log_message
                assert "model" in log_message
                assert "object_id" in log_message
                assert "owner_user_id" in log_message

                # Check the actual values
                log_kwargs = call_args[0][1:]
                assert admin_user.id in log_kwargs
                assert action_type in log_kwargs
                assert "Bot" in log_kwargs
                assert owner_user.id in log_kwargs

        finally:
            Bot.objects.filter(user__in=[owner_user]).delete()
            admin_user.delete()
            owner_user.delete()

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_actions=st.integers(min_value=1, max_value=5),
    )
    def test_each_admin_action_creates_separate_log(
        self,
        trading_pair,
        request_factory,
        num_actions: int,
    ) -> None:
        """
        Property: Each admin action creates a separate audit log entry.

        Feature: multi-tenant-user-isolation, Property 17: Admin Action Audit Logging

        **Validates: Requirements 10.4**
        """
        admin_user = create_test_user(is_superuser=True)
        owner_user = create_test_user()

        try:
            # Create multiple bots
            bots = []
            for i in range(num_actions):
                bot = Bot.objects.create(
                    user=owner_user,
                    pionex_bot_id=f"bot_{uuid.uuid4().hex[:8]}",
                    bot_type=BotType.GRID,
                    trading_pair=trading_pair,
                    status=BotStatus.ACTIVE,
                    invested_amount="100.00",
                )
                bots.append(bot)

            class MockBotAdmin(AdminAuditMixin):
                user_field = "user"

                def __init__(self):
                    pass

            mock_admin = MockBotAdmin()

            request = request_factory.post("/admin/bots/bot/")
            request.user = admin_user

            # Log actions for each bot
            with patch("lib.multitenancy.admin.logger") as mock_logger:
                for bot in bots:
                    mock_admin._log_user_data_action(request, bot, "change")

                # Verify log was called for each action
                assert mock_logger.info.call_count == num_actions

        finally:
            Bot.objects.filter(user=owner_user).delete()
            admin_user.delete()
            owner_user.delete()

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        model_type=st.sampled_from(["bot", "trade", "portfolio"]),
    )
    def test_audit_log_includes_correct_model_type(
        self,
        trading_pair,
        request_factory,
        model_type: str,
    ) -> None:
        """
        Property: Audit log correctly identifies the model type being modified.

        Feature: multi-tenant-user-isolation, Property 17: Admin Action Audit Logging

        **Validates: Requirements 10.4**
        """
        admin_user = create_test_user(is_superuser=True)
        owner_user = create_test_user()

        try:
            # Create the appropriate model
            if model_type == "bot":
                obj = Bot.objects.create(
                    user=owner_user,
                    pionex_bot_id=f"bot_{uuid.uuid4().hex[:8]}",
                    bot_type=BotType.GRID,
                    trading_pair=trading_pair,
                    status=BotStatus.ACTIVE,
                    invested_amount="100.00",
                )
                expected_model_name = "Bot"
            elif model_type == "trade":
                obj = Trade.objects.create(
                    user=owner_user,
                    trading_pair=trading_pair,
                    side=TradeSide.BUY,
                    entry_price="50000.00",
                    quantity="0.001",
                )
                expected_model_name = "Trade"
            else:  # portfolio
                obj = PortfolioSnapshot.objects.create(
                    user=owner_user,
                    total_value="10000.00",
                    available_balance="5000.00",
                    allocated_to_bots="5000.00",
                    high_water_mark="10000.00",
                )
                expected_model_name = "PortfolioSnapshot"

            class MockAdmin(AdminAuditMixin):
                user_field = "user"

                def __init__(self):
                    pass

            mock_admin = MockAdmin()

            request = request_factory.post("/admin/")
            request.user = admin_user

            with patch("lib.multitenancy.admin.logger") as mock_logger:
                mock_admin._log_user_data_action(request, obj, "change")

                # Verify model name is in the log
                call_args = mock_logger.info.call_args[0]
                assert expected_model_name in call_args

        finally:
            if model_type == "bot":
                Bot.objects.filter(user=owner_user).delete()
            elif model_type == "trade":
                Trade.objects.filter(user=owner_user).delete()
            else:
                PortfolioSnapshot.objects.filter(user=owner_user).delete()
            admin_user.delete()
            owner_user.delete()

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_admins=st.integers(min_value=2, max_value=4),
    )
    def test_audit_log_identifies_correct_admin_user(
        self,
        trading_pair,
        request_factory,
        num_admins: int,
    ) -> None:
        """
        Property: Audit log correctly identifies which admin performed the action.

        Feature: multi-tenant-user-isolation, Property 17: Admin Action Audit Logging

        **Validates: Requirements 10.4**
        """
        admin_users = [create_test_user(is_superuser=True) for _ in range(num_admins)]
        owner_user = create_test_user()

        try:
            bot = Bot.objects.create(
                user=owner_user,
                pionex_bot_id=f"bot_{uuid.uuid4().hex[:8]}",
                bot_type=BotType.GRID,
                trading_pair=trading_pair,
                status=BotStatus.ACTIVE,
                invested_amount="100.00",
            )

            class MockBotAdmin(AdminAuditMixin):
                user_field = "user"

                def __init__(self):
                    pass

            mock_admin = MockBotAdmin()

            # Each admin performs an action
            for admin_user in admin_users:
                request = request_factory.post("/admin/bots/bot/")
                request.user = admin_user

                with patch("lib.multitenancy.admin.logger") as mock_logger:
                    mock_admin._log_user_data_action(request, bot, "change")

                    # Verify the correct admin ID is logged
                    call_args = mock_logger.info.call_args[0]
                    assert admin_user.id in call_args
                    assert admin_user.username in call_args

        finally:
            Bot.objects.filter(user=owner_user).delete()
            for admin_user in admin_users:
                admin_user.delete()
            owner_user.delete()

    def test_audit_log_handles_user_owner(
        self,
        trading_pair,
        request_factory,
    ) -> None:
        """
        Property: Audit log correctly logs the owner user for user-owned objects.

        Feature: multi-tenant-user-isolation, Property 17: Admin Action Audit Logging

        **Validates: Requirements 10.4**

        Note: User FK is now non-nullable (Requirements 11.3), so all objects
        must have an owner. This test verifies the audit log correctly captures
        the owner information.
        """
        admin_user = create_test_user(is_superuser=True)
        owner_user = create_test_user()

        try:
            bot = Bot.objects.create(
                user=owner_user,
                pionex_bot_id=f"bot_{uuid.uuid4().hex[:8]}",
                bot_type=BotType.GRID,
                trading_pair=trading_pair,
                status=BotStatus.ACTIVE,
                invested_amount="100.00",
            )

            class MockBotAdmin(AdminAuditMixin):
                user_field = "user"

                def __init__(self):
                    pass

            mock_admin = MockBotAdmin()

            request = request_factory.post("/admin/bots/bot/")
            request.user = admin_user

            with patch("lib.multitenancy.admin.logger") as mock_logger:
                # Should not raise an exception
                mock_admin._log_user_data_action(request, bot, "change")

                # Verify log was called
                mock_logger.info.assert_called_once()

                call_args = mock_logger.info.call_args[0]
                # Owner user ID should be in the log
                assert owner_user.id in call_args

        finally:
            Bot.objects.filter(pionex_bot_id=bot.pionex_bot_id).delete()
            admin_user.delete()
            owner_user.delete()


@pytest.mark.django_db(transaction=True)
class TestGetAdminAuditLog:
    """
    Tests for the get_admin_audit_log utility function.

    **Validates: Requirements 10.4**
    """

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        limit=st.integers(min_value=1, max_value=50),
    )
    def test_get_audit_log_respects_limit(
        self,
        limit: int,
    ) -> None:
        """
        Property: get_admin_audit_log respects the limit parameter.

        **Validates: Requirements 10.4**
        """
        # Query with limit
        entries = get_admin_audit_log(limit=limit)

        # Should not exceed limit
        assert len(entries) <= limit

    def test_get_audit_log_filters_by_admin_user(self) -> None:
        """
        Test that get_admin_audit_log can filter by admin user.

        **Validates: Requirements 10.4**
        """
        admin_user = create_test_user(is_superuser=True)

        try:
            # Query for specific admin
            entries = get_admin_audit_log(admin_user=admin_user)

            # All entries should be from this admin
            for entry in entries:
                assert entry.user == admin_user

        finally:
            admin_user.delete()

    def test_get_audit_log_filters_by_action_flag(self) -> None:
        """
        Test that get_admin_audit_log can filter by action type.

        **Validates: Requirements 10.4**
        """
        # Query for additions only
        entries = get_admin_audit_log(action_flag=ADDITION)

        # All entries should be additions
        for entry in entries:
            assert entry.action_flag == ADDITION
