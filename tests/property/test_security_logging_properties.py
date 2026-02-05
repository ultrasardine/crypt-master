"""
Property-based tests for Security Logging.

Feature: multi-tenant-user-isolation
Property 21: Cross-User Access Security Logging

These tests use the hypothesis library to verify that security logging
behaves correctly across a wide range of inputs.

Requirements:
- 12.5: Log any attempted cross-user data access for security monitoring
"""

from __future__ import annotations

import string
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from lib.multitenancy.security import (
    SecurityEvent,
    SecurityEventLogger,
    SecurityEventType,
    get_security_logger,
    log_cross_user_access,
)


# Strategies for generating test data
user_id_strategy = st.integers(min_value=1, max_value=1000000)

resource_type_strategy = st.sampled_from(["Bot", "Trade", "PortfolioSnapshot", "UserProfile"])

resource_id_strategy = st.one_of(
    st.integers(min_value=1, max_value=1000000),
    st.text(
        alphabet=string.ascii_letters + string.digits + "_-",
        min_size=1,
        max_size=50,
    ),
)

# Strategy for generating details dictionaries
details_strategy = st.one_of(
    st.none(),
    st.fixed_dictionaries(
        {},
        optional={
            "view": st.text(min_size=1, max_size=50),
            "method": st.sampled_from(["GET", "POST", "PUT", "DELETE", "PATCH"]),
            "ip_address": st.ip_addresses().map(str),
            "path": st.text(min_size=1, max_size=100),
        },
    ),
)


def create_test_user(user_id: int | None = None) -> User:
    """Create a test user with a unique username."""
    username = f"testuser_{uuid.uuid4().hex[:8]}"
    user = User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="testpass123",
    )
    if user_id is not None:
        # Override the ID for testing purposes (only works in tests)
        user.id = user_id
    return user


def create_mock_user(user_id: int) -> MagicMock:
    """Create a mock user with a specific ID."""
    mock_user = MagicMock()
    mock_user.id = user_id
    return mock_user


def create_mock_resource(
    resource_type: str,
    resource_id: int | str,
    owner_id: int,
    user_field: str = "user",
) -> MagicMock:
    """Create a mock resource with specified attributes."""
    mock_resource = MagicMock()
    mock_resource.__class__.__name__ = resource_type
    mock_resource.id = resource_id
    mock_resource.pk = resource_id

    # Set the owner
    mock_owner = MagicMock()
    mock_owner.id = owner_id
    setattr(mock_resource, user_field, mock_owner)

    return mock_resource


@pytest.mark.django_db(transaction=True)
class TestCrossUserAccessSecurityLogging:
    """
    Property 21: Cross-User Access Security Logging

    *For any* attempted access to another user's data that is blocked,
    a security log entry SHALL be created with the requesting user ID,
    target resource, and timestamp.

    Feature: multi-tenant-user-isolation, Property 21: Cross-User Access Security Logging

    **Validates: Requirements 12.5**
    """

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        requesting_user_id=user_id_strategy,
        owner_id=user_id_strategy,
        resource_type=resource_type_strategy,
        resource_id=resource_id_strategy,
    )
    def test_cross_user_access_creates_log_entry(
        self,
        requesting_user_id: int,
        owner_id: int,
        resource_type: str,
        resource_id: int | str,
    ) -> None:
        """
        Property: For any cross-user access attempt, a security log entry is created.

        Feature: multi-tenant-user-isolation, Property 21: Cross-User Access Security Logging

        **Validates: Requirements 12.5**
        """
        # Ensure different users (cross-user access)
        if requesting_user_id == owner_id:
            owner_id = requesting_user_id + 1

        mock_user = create_mock_user(requesting_user_id)
        mock_resource = create_mock_resource(resource_type, resource_id, owner_id)

        logger = SecurityEventLogger()

        with patch.object(logger._logger, "warning") as mock_warning:
            logger.log_cross_user_access_attempt(
                requesting_user=mock_user,
                target_resource=mock_resource,
            )

            # Verify a log entry was created
            mock_warning.assert_called_once()

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        requesting_user_id=user_id_strategy,
        owner_id=user_id_strategy,
        resource_type=resource_type_strategy,
        resource_id=resource_id_strategy,
    )
    def test_log_entry_contains_requesting_user_id(
        self,
        requesting_user_id: int,
        owner_id: int,
        resource_type: str,
        resource_id: int | str,
    ) -> None:
        """
        Property: The log entry contains the requesting user ID.

        Feature: multi-tenant-user-isolation, Property 21: Cross-User Access Security Logging

        **Validates: Requirements 12.5**
        """
        if requesting_user_id == owner_id:
            owner_id = requesting_user_id + 1

        mock_user = create_mock_user(requesting_user_id)
        mock_resource = create_mock_resource(resource_type, resource_id, owner_id)

        logger = SecurityEventLogger()

        with patch.object(logger._logger, "warning") as mock_warning:
            logger.log_cross_user_access_attempt(
                requesting_user=mock_user,
                target_resource=mock_resource,
            )

            mock_warning.assert_called_once()
            extra = mock_warning.call_args[1]["extra"]
            security_event = extra["security_event"]

            # Verify requesting user ID is in the log entry
            assert security_event["requesting_user_id"] == requesting_user_id, (
                f"Log entry should contain requesting user ID {requesting_user_id}, "
                f"but got {security_event['requesting_user_id']}"
            )

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        requesting_user_id=user_id_strategy,
        owner_id=user_id_strategy,
        resource_type=resource_type_strategy,
        resource_id=resource_id_strategy,
    )
    def test_log_entry_contains_target_resource_type(
        self,
        requesting_user_id: int,
        owner_id: int,
        resource_type: str,
        resource_id: int | str,
    ) -> None:
        """
        Property: The log entry contains the target resource type.

        Feature: multi-tenant-user-isolation, Property 21: Cross-User Access Security Logging

        **Validates: Requirements 12.5**
        """
        if requesting_user_id == owner_id:
            owner_id = requesting_user_id + 1

        mock_user = create_mock_user(requesting_user_id)
        mock_resource = create_mock_resource(resource_type, resource_id, owner_id)

        logger = SecurityEventLogger()

        with patch.object(logger._logger, "warning") as mock_warning:
            logger.log_cross_user_access_attempt(
                requesting_user=mock_user,
                target_resource=mock_resource,
            )

            mock_warning.assert_called_once()
            extra = mock_warning.call_args[1]["extra"]
            security_event = extra["security_event"]

            # Verify resource type is in the log entry
            assert security_event["target_resource_type"] == resource_type, (
                f"Log entry should contain resource type '{resource_type}', "
                f"but got '{security_event['target_resource_type']}'"
            )

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        requesting_user_id=user_id_strategy,
        owner_id=user_id_strategy,
        resource_type=resource_type_strategy,
        resource_id=resource_id_strategy,
    )
    def test_log_entry_contains_target_resource_id(
        self,
        requesting_user_id: int,
        owner_id: int,
        resource_type: str,
        resource_id: int | str,
    ) -> None:
        """
        Property: The log entry contains the target resource ID.

        Feature: multi-tenant-user-isolation, Property 21: Cross-User Access Security Logging

        **Validates: Requirements 12.5**
        """
        if requesting_user_id == owner_id:
            owner_id = requesting_user_id + 1

        mock_user = create_mock_user(requesting_user_id)
        mock_resource = create_mock_resource(resource_type, resource_id, owner_id)

        logger = SecurityEventLogger()

        with patch.object(logger._logger, "warning") as mock_warning:
            logger.log_cross_user_access_attempt(
                requesting_user=mock_user,
                target_resource=mock_resource,
            )

            mock_warning.assert_called_once()
            extra = mock_warning.call_args[1]["extra"]
            security_event = extra["security_event"]

            # Verify resource ID is in the log entry
            assert security_event["target_resource_id"] == resource_id, (
                f"Log entry should contain resource ID '{resource_id}', "
                f"but got '{security_event['target_resource_id']}'"
            )

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        requesting_user_id=user_id_strategy,
        owner_id=user_id_strategy,
        resource_type=resource_type_strategy,
        resource_id=resource_id_strategy,
    )
    def test_log_entry_contains_timestamp(
        self,
        requesting_user_id: int,
        owner_id: int,
        resource_type: str,
        resource_id: int | str,
    ) -> None:
        """
        Property: The log entry contains a timestamp.

        Feature: multi-tenant-user-isolation, Property 21: Cross-User Access Security Logging

        **Validates: Requirements 12.5**
        """
        if requesting_user_id == owner_id:
            owner_id = requesting_user_id + 1

        mock_user = create_mock_user(requesting_user_id)
        mock_resource = create_mock_resource(resource_type, resource_id, owner_id)

        logger = SecurityEventLogger()
        before_time = datetime.now(tz=UTC)

        with patch.object(logger._logger, "warning") as mock_warning:
            logger.log_cross_user_access_attempt(
                requesting_user=mock_user,
                target_resource=mock_resource,
            )

            after_time = datetime.now(tz=UTC)

            mock_warning.assert_called_once()
            extra = mock_warning.call_args[1]["extra"]
            security_event = extra["security_event"]

            # Verify timestamp is present and valid
            assert "timestamp" in security_event, "Log entry should contain a timestamp"
            assert security_event["timestamp"] is not None, "Timestamp should not be None"

            # Parse the timestamp and verify it's within the expected range
            timestamp_str = security_event["timestamp"]
            timestamp = datetime.fromisoformat(timestamp_str)
            assert before_time <= timestamp <= after_time, (
                f"Timestamp {timestamp} should be between {before_time} and {after_time}"
            )

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        requesting_user_id=user_id_strategy,
        owner_id=user_id_strategy,
        resource_type=resource_type_strategy,
        resource_id=resource_id_strategy,
        details=details_strategy,
    )
    def test_log_entry_preserves_additional_details(
        self,
        requesting_user_id: int,
        owner_id: int,
        resource_type: str,
        resource_id: int | str,
        details: dict[str, Any] | None,
    ) -> None:
        """
        Property: Additional details provided are preserved in the log entry.

        Feature: multi-tenant-user-isolation, Property 21: Cross-User Access Security Logging

        **Validates: Requirements 12.5**
        """
        if requesting_user_id == owner_id:
            owner_id = requesting_user_id + 1

        mock_user = create_mock_user(requesting_user_id)
        mock_resource = create_mock_resource(resource_type, resource_id, owner_id)

        logger = SecurityEventLogger()

        with patch.object(logger._logger, "warning") as mock_warning:
            logger.log_cross_user_access_attempt(
                requesting_user=mock_user,
                target_resource=mock_resource,
                details=details,
            )

            mock_warning.assert_called_once()
            extra = mock_warning.call_args[1]["extra"]
            security_event = extra["security_event"]

            # Verify details are preserved
            if details is None:
                assert security_event["details"] == {}, (
                    "Details should be empty dict when None is provided"
                )
            else:
                for key, value in details.items():
                    assert key in security_event["details"], (
                        f"Detail key '{key}' should be in log entry"
                    )
                    assert security_event["details"][key] == value, (
                        f"Detail value for '{key}' should be '{value}'"
                    )

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        requesting_user_id=user_id_strategy,
        owner_id=user_id_strategy,
        resource_type=resource_type_strategy,
        resource_id=resource_id_strategy,
    )
    def test_log_entry_contains_target_owner_id(
        self,
        requesting_user_id: int,
        owner_id: int,
        resource_type: str,
        resource_id: int | str,
    ) -> None:
        """
        Property: The log entry contains the target resource owner ID.

        Feature: multi-tenant-user-isolation, Property 21: Cross-User Access Security Logging

        **Validates: Requirements 12.5**
        """
        if requesting_user_id == owner_id:
            owner_id = requesting_user_id + 1

        mock_user = create_mock_user(requesting_user_id)
        mock_resource = create_mock_resource(resource_type, resource_id, owner_id)

        logger = SecurityEventLogger()

        with patch.object(logger._logger, "warning") as mock_warning:
            logger.log_cross_user_access_attempt(
                requesting_user=mock_user,
                target_resource=mock_resource,
            )

            mock_warning.assert_called_once()
            extra = mock_warning.call_args[1]["extra"]
            security_event = extra["security_event"]

            # Verify owner ID is in the log entry
            assert security_event["target_owner_id"] == owner_id, (
                f"Log entry should contain owner ID {owner_id}, "
                f"but got {security_event['target_owner_id']}"
            )

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        requesting_user_id=user_id_strategy,
        owner_id=user_id_strategy,
        resource_type=resource_type_strategy,
        resource_id=resource_id_strategy,
    )
    def test_log_entry_has_correct_event_type(
        self,
        requesting_user_id: int,
        owner_id: int,
        resource_type: str,
        resource_id: int | str,
    ) -> None:
        """
        Property: The log entry has the correct event type for cross-user access.

        Feature: multi-tenant-user-isolation, Property 21: Cross-User Access Security Logging

        **Validates: Requirements 12.5**
        """
        if requesting_user_id == owner_id:
            owner_id = requesting_user_id + 1

        mock_user = create_mock_user(requesting_user_id)
        mock_resource = create_mock_resource(resource_type, resource_id, owner_id)

        logger = SecurityEventLogger()

        with patch.object(logger._logger, "warning") as mock_warning:
            logger.log_cross_user_access_attempt(
                requesting_user=mock_user,
                target_resource=mock_resource,
            )

            mock_warning.assert_called_once()
            extra = mock_warning.call_args[1]["extra"]
            security_event = extra["security_event"]

            # Verify event type is correct
            expected_event_type = SecurityEventType.CROSS_USER_ACCESS_ATTEMPT.value
            assert security_event["event_type"] == expected_event_type, (
                f"Event type should be '{expected_event_type}', "
                f"but got '{security_event['event_type']}'"
            )


@pytest.mark.django_db(transaction=True)
class TestSecurityLoggingWithNullUser:
    """
    Additional property tests for edge cases with null/anonymous users.

    Feature: multi-tenant-user-isolation, Property 21: Cross-User Access Security Logging

    **Validates: Requirements 12.5**
    """

    @settings(
        max_examples=15,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        owner_id=user_id_strategy,
        resource_type=resource_type_strategy,
        resource_id=resource_id_strategy,
    )
    def test_log_entry_handles_null_requesting_user(
        self,
        owner_id: int,
        resource_type: str,
        resource_id: int | str,
    ) -> None:
        """
        Property: Log entry is created even when requesting user is None (unauthenticated).

        Feature: multi-tenant-user-isolation, Property 21: Cross-User Access Security Logging

        **Validates: Requirements 12.5**
        """
        mock_resource = create_mock_resource(resource_type, resource_id, owner_id)

        logger = SecurityEventLogger()

        with patch.object(logger._logger, "warning") as mock_warning:
            logger.log_cross_user_access_attempt(
                requesting_user=None,
                target_resource=mock_resource,
            )

            # Verify a log entry was still created
            mock_warning.assert_called_once()
            extra = mock_warning.call_args[1]["extra"]
            security_event = extra["security_event"]

            # Verify requesting user ID is None
            assert security_event["requesting_user_id"] is None, (
                "Requesting user ID should be None for unauthenticated access"
            )

            # Verify other fields are still populated
            assert security_event["target_resource_type"] == resource_type
            assert security_event["target_resource_id"] == resource_id
            assert security_event["target_owner_id"] == owner_id


@pytest.mark.django_db(transaction=True)
class TestSecurityLoggingConvenienceFunction:
    """
    Property tests for the log_cross_user_access convenience function.

    Feature: multi-tenant-user-isolation, Property 21: Cross-User Access Security Logging

    **Validates: Requirements 12.5**
    """

    @settings(
        max_examples=15,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        requesting_user_id=user_id_strategy,
        owner_id=user_id_strategy,
        resource_type=resource_type_strategy,
        resource_id=resource_id_strategy,
    )
    def test_convenience_function_creates_log_entry(
        self,
        requesting_user_id: int,
        owner_id: int,
        resource_type: str,
        resource_id: int | str,
    ) -> None:
        """
        Property: The convenience function creates a log entry with all required fields.

        Feature: multi-tenant-user-isolation, Property 21: Cross-User Access Security Logging

        **Validates: Requirements 12.5**
        """
        if requesting_user_id == owner_id:
            owner_id = requesting_user_id + 1

        mock_user = create_mock_user(requesting_user_id)
        mock_resource = create_mock_resource(resource_type, resource_id, owner_id)

        # Get the singleton logger and patch its internal logger
        security_logger_instance = get_security_logger()

        with patch.object(security_logger_instance._logger, "warning") as mock_warning:
            log_cross_user_access(
                requesting_user=mock_user,
                target_resource=mock_resource,
            )

            mock_warning.assert_called_once()
            extra = mock_warning.call_args[1]["extra"]
            security_event = extra["security_event"]

            # Verify all required fields are present
            assert security_event["requesting_user_id"] == requesting_user_id
            assert security_event["target_resource_type"] == resource_type
            assert security_event["target_resource_id"] == resource_id
            assert security_event["target_owner_id"] == owner_id
            assert "timestamp" in security_event
            assert security_event["timestamp"] is not None


@pytest.mark.django_db(transaction=True)
class TestSecurityEventDataclass:
    """
    Property tests for the SecurityEvent dataclass.

    Feature: multi-tenant-user-isolation, Property 21: Cross-User Access Security Logging

    **Validates: Requirements 12.5**
    """

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        requesting_user_id=st.one_of(st.none(), user_id_strategy),
        resource_type=resource_type_strategy,
        resource_id=st.one_of(st.none(), resource_id_strategy),
        owner_id=st.one_of(st.none(), user_id_strategy),
        details=details_strategy,
    )
    def test_security_event_to_dict_preserves_all_fields(
        self,
        requesting_user_id: int | None,
        resource_type: str,
        resource_id: int | str | None,
        owner_id: int | None,
        details: dict[str, Any] | None,
    ) -> None:
        """
        Property: SecurityEvent.to_dict() preserves all fields correctly.

        Feature: multi-tenant-user-isolation, Property 21: Cross-User Access Security Logging

        **Validates: Requirements 12.5**
        """
        event = SecurityEvent(
            event_type=SecurityEventType.CROSS_USER_ACCESS_ATTEMPT,
            requesting_user_id=requesting_user_id,
            target_resource_type=resource_type,
            target_resource_id=resource_id,
            target_owner_id=owner_id,
            details=details,
        )

        result = event.to_dict()

        # Verify all fields are preserved
        assert result["event_type"] == SecurityEventType.CROSS_USER_ACCESS_ATTEMPT.value
        assert result["requesting_user_id"] == requesting_user_id
        assert result["target_resource_type"] == resource_type
        assert result["target_resource_id"] == resource_id
        assert result["target_owner_id"] == owner_id
        assert "timestamp" in result

        if details is None:
            assert result["details"] == {}
        else:
            assert result["details"] == details

    @settings(
        max_examples=15,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        requesting_user_id=user_id_strategy,
        resource_type=resource_type_strategy,
    )
    def test_security_event_auto_generates_timestamp(
        self,
        requesting_user_id: int,
        resource_type: str,
    ) -> None:
        """
        Property: SecurityEvent auto-generates a timestamp when not provided.

        Feature: multi-tenant-user-isolation, Property 21: Cross-User Access Security Logging

        **Validates: Requirements 12.5**
        """
        before_time = datetime.now(tz=UTC)

        event = SecurityEvent(
            event_type=SecurityEventType.CROSS_USER_ACCESS_ATTEMPT,
            requesting_user_id=requesting_user_id,
            target_resource_type=resource_type,
        )

        after_time = datetime.now(tz=UTC)

        assert event.timestamp is not None, "Timestamp should be auto-generated"
        assert before_time <= event.timestamp <= after_time, (
            f"Auto-generated timestamp {event.timestamp} should be between "
            f"{before_time} and {after_time}"
        )
