"""
Unit tests for security event logging.

Tests the security logging functionality for cross-user access attempts
and other security events.

Requirements:
- 12.5: Log any attempted cross-user data access for security monitoring
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model

from lib.multitenancy.security import (
    SecurityEvent,
    SecurityEventLogger,
    SecurityEventType,
    get_security_logger,
    log_cross_user_access,
)

User = get_user_model()


class TestSecurityEvent:
    """Tests for SecurityEvent dataclass."""

    def test_security_event_creation(self) -> None:
        """Test creating a security event with all fields."""
        event = SecurityEvent(
            event_type=SecurityEventType.CROSS_USER_ACCESS_ATTEMPT,
            requesting_user_id=1,
            target_resource_type="Bot",
            target_resource_id=42,
            target_owner_id=2,
        )

        assert event.event_type == SecurityEventType.CROSS_USER_ACCESS_ATTEMPT
        assert event.requesting_user_id == 1
        assert event.target_resource_type == "Bot"
        assert event.target_resource_id == 42
        assert event.target_owner_id == 2
        assert event.timestamp is not None

    def test_security_event_auto_timestamp(self) -> None:
        """Test that timestamp is automatically set if not provided."""
        before = datetime.now(tz=UTC)
        event = SecurityEvent(
            event_type=SecurityEventType.CROSS_USER_ACCESS_ATTEMPT,
            requesting_user_id=1,
            target_resource_type="Bot",
        )
        after = datetime.now(tz=UTC)

        assert event.timestamp is not None
        assert before <= event.timestamp <= after

    def test_security_event_custom_timestamp(self) -> None:
        """Test that custom timestamp is preserved."""
        custom_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        event = SecurityEvent(
            event_type=SecurityEventType.CROSS_USER_ACCESS_ATTEMPT,
            requesting_user_id=1,
            target_resource_type="Bot",
            timestamp=custom_time,
        )

        assert event.timestamp == custom_time

    def test_security_event_to_dict(self) -> None:
        """Test converting security event to dictionary."""
        event = SecurityEvent(
            event_type=SecurityEventType.CROSS_USER_ACCESS_ATTEMPT,
            requesting_user_id=1,
            target_resource_type="Bot",
            target_resource_id=42,
            target_owner_id=2,
            details={"view": "BotDetailView"},
        )

        result = event.to_dict()

        assert result["event_type"] == "cross_user_access_attempt"
        assert result["requesting_user_id"] == 1
        assert result["target_resource_type"] == "Bot"
        assert result["target_resource_id"] == 42
        assert result["target_owner_id"] == 2
        assert result["details"] == {"view": "BotDetailView"}
        assert "timestamp" in result


class TestSecurityEventType:
    """Tests for SecurityEventType enum."""

    def test_all_event_types_have_values(self) -> None:
        """Test that all event types have string values."""
        for event_type in SecurityEventType:
            assert isinstance(event_type.value, str)
            assert len(event_type.value) > 0

    def test_cross_user_access_attempt_value(self) -> None:
        """Test the cross user access attempt event type value."""
        assert SecurityEventType.CROSS_USER_ACCESS_ATTEMPT.value == "cross_user_access_attempt"


class TestSecurityEventLogger:
    """Tests for SecurityEventLogger class."""

    def test_log_event(self) -> None:
        """Test logging a security event."""
        logger = SecurityEventLogger()
        event = SecurityEvent(
            event_type=SecurityEventType.CROSS_USER_ACCESS_ATTEMPT,
            requesting_user_id=1,
            target_resource_type="Bot",
            target_resource_id=42,
            target_owner_id=2,
        )

        with patch.object(logger._logger, "warning") as mock_warning:
            logger.log_event(event)

            mock_warning.assert_called_once()
            call_args = mock_warning.call_args
            # The format string contains %s placeholders, check the args
            assert event.event_type.value in call_args[0]  # First positional arg
            assert "security_event" in call_args[1]["extra"]

    def test_log_cross_user_access_attempt(self) -> None:
        """Test logging a cross-user access attempt with a model object."""
        logger = SecurityEventLogger()

        # Create mock user and resource
        mock_user = MagicMock()
        mock_user.id = 1

        mock_owner = MagicMock()
        mock_owner.id = 2

        mock_resource = MagicMock()
        mock_resource.__class__.__name__ = "Bot"
        mock_resource.id = 42
        mock_resource.user = mock_owner

        with patch.object(logger._logger, "warning") as mock_warning:
            logger.log_cross_user_access_attempt(
                requesting_user=mock_user,
                target_resource=mock_resource,
            )

            mock_warning.assert_called_once()
            call_args = mock_warning.call_args
            # Check the log message contains expected info
            assert "1" in str(call_args)  # requesting user id
            assert "Bot" in str(call_args)  # resource type
            assert "42" in str(call_args)  # resource id
            assert "2" in str(call_args)  # owner id

    def test_log_cross_user_access_attempt_with_details(self) -> None:
        """Test logging with additional details."""
        logger = SecurityEventLogger()

        mock_user = MagicMock()
        mock_user.id = 1

        mock_resource = MagicMock()
        mock_resource.__class__.__name__ = "Trade"
        mock_resource.id = 100
        mock_resource.user = MagicMock(id=5)

        with patch.object(logger._logger, "warning") as mock_warning:
            logger.log_cross_user_access_attempt(
                requesting_user=mock_user,
                target_resource=mock_resource,
                details={"view": "TradeDetailView", "method": "GET"},
            )

            mock_warning.assert_called_once()
            extra = mock_warning.call_args[1]["extra"]
            assert extra["security_event"]["details"]["view"] == "TradeDetailView"
            assert extra["security_event"]["details"]["method"] == "GET"

    def test_log_cross_user_access_attempt_with_none_user(self) -> None:
        """Test logging when requesting user is None (unauthenticated)."""
        logger = SecurityEventLogger()

        mock_resource = MagicMock()
        mock_resource.__class__.__name__ = "Bot"
        mock_resource.id = 42
        mock_resource.user = MagicMock(id=2)

        with patch.object(logger._logger, "warning") as mock_warning:
            logger.log_cross_user_access_attempt(
                requesting_user=None,
                target_resource=mock_resource,
            )

            mock_warning.assert_called_once()
            extra = mock_warning.call_args[1]["extra"]
            assert extra["security_event"]["requesting_user_id"] is None

    def test_log_bulk_operation_filtered_with_difference(self) -> None:
        """Test logging bulk operation when records were filtered."""
        logger = SecurityEventLogger()

        mock_user = MagicMock()
        mock_user.id = 1

        with patch.object(logger._logger, "warning") as mock_warning:
            logger.log_bulk_operation_filtered(
                requesting_user=mock_user,
                resource_type="Bot",
                total_requested=10,
                filtered_count=3,
                operation="delete",
            )

            mock_warning.assert_called_once()

    def test_log_bulk_operation_filtered_no_difference(self) -> None:
        """Test logging bulk operation when no records were filtered."""
        logger = SecurityEventLogger()

        mock_user = MagicMock()
        mock_user.id = 1

        with patch.object(logger._logger, "debug") as mock_debug:
            logger.log_bulk_operation_filtered(
                requesting_user=mock_user,
                resource_type="Bot",
                total_requested=5,
                filtered_count=5,
                operation="update",
            )

            mock_debug.assert_called_once()

    def test_log_admin_data_access(self) -> None:
        """Test logging admin data access."""
        logger = SecurityEventLogger()

        mock_admin = MagicMock()
        mock_admin.id = 1

        with patch.object(logger._logger, "info") as mock_info:
            logger.log_admin_data_access(
                admin_user=mock_admin,
                resource_type="Bot",
                resource_id=42,
                target_owner_id=5,
                action="view",
            )

            mock_info.assert_called_once()
            call_args = mock_info.call_args
            assert "Admin data access" in call_args[0][0]


class TestGetSecurityLogger:
    """Tests for get_security_logger function."""

    def test_returns_security_event_logger(self) -> None:
        """Test that get_security_logger returns a SecurityEventLogger."""
        logger = get_security_logger()
        assert isinstance(logger, SecurityEventLogger)

    def test_returns_singleton(self) -> None:
        """Test that get_security_logger returns the same instance."""
        logger1 = get_security_logger()
        logger2 = get_security_logger()
        assert logger1 is logger2


class TestLogCrossUserAccess:
    """Tests for log_cross_user_access convenience function."""

    def test_logs_cross_user_access(self) -> None:
        """Test the convenience function logs correctly."""
        mock_user = MagicMock()
        mock_user.id = 1

        mock_resource = MagicMock()
        mock_resource.__class__.__name__ = "Bot"
        mock_resource.id = 42
        mock_resource.user = MagicMock(id=2)

        # Get the actual logger instance and patch its _logger
        security_logger_instance = get_security_logger()
        with patch.object(security_logger_instance._logger, "warning") as mock_warning:
            log_cross_user_access(
                requesting_user=mock_user,
                target_resource=mock_resource,
            )

            mock_warning.assert_called_once()


@pytest.mark.django_db
class TestSecurityLoggingIntegration:
    """Integration tests for security logging with Django models."""

    def test_log_cross_user_access_with_real_user(self) -> None:
        """Test logging with a real Django user."""
        user1 = User.objects.create_user(
            username="user1",
            email="user1@example.com",
            password="testpass123",
        )
        user2 = User.objects.create_user(
            username="user2",
            email="user2@example.com",
            password="testpass123",
        )

        # Create a mock resource owned by user2
        mock_resource = MagicMock()
        mock_resource.__class__.__name__ = "Bot"
        mock_resource.id = 42
        mock_resource.user = user2

        logger = get_security_logger()

        with patch.object(logger._logger, "warning") as mock_warning:
            logger.log_cross_user_access_attempt(
                requesting_user=user1,
                target_resource=mock_resource,
            )

            mock_warning.assert_called_once()
            extra = mock_warning.call_args[1]["extra"]
            assert extra["security_event"]["requesting_user_id"] == user1.id
            assert extra["security_event"]["target_owner_id"] == user2.id
