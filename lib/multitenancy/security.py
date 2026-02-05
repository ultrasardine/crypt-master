"""
Security event logging for multi-tenant user isolation.

This module provides centralized security logging for cross-user access attempts
and other security-related events in the multi-tenant system.

Requirements:
- 12.5: Log any attempted cross-user data access for security monitoring
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from django.contrib.auth.models import User
    from django.db.models import Model

# Dedicated security logger
security_logger = logging.getLogger("security")


class SecurityEventType(Enum):
    """Types of security events that can be logged."""

    CROSS_USER_ACCESS_ATTEMPT = "cross_user_access_attempt"
    UNAUTHORIZED_RESOURCE_ACCESS = "unauthorized_resource_access"
    BULK_OPERATION_FILTERED = "bulk_operation_filtered"
    ADMIN_DATA_ACCESS = "admin_data_access"
    API_KEY_ACCESS_ATTEMPT = "api_key_access_attempt"


@dataclass
class SecurityEvent:
    """
    Represents a security event for logging.

    Attributes:
        event_type: The type of security event
        requesting_user_id: ID of the user making the request
        target_resource_type: Type/name of the resource being accessed
        target_resource_id: ID of the specific resource
        target_owner_id: ID of the user who owns the resource (if applicable)
        timestamp: When the event occurred
        details: Additional context about the event
    """

    event_type: SecurityEventType
    requesting_user_id: int | None
    target_resource_type: str
    target_resource_id: str | int | None = None
    target_owner_id: int | None = None
    timestamp: datetime | None = None
    details: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """Set timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.now(tz=UTC)

    def to_dict(self) -> dict[str, Any]:
        """Convert the event to a dictionary for logging."""
        return {
            "event_type": self.event_type.value,
            "requesting_user_id": self.requesting_user_id,
            "target_resource_type": self.target_resource_type,
            "target_resource_id": self.target_resource_id,
            "target_owner_id": self.target_owner_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "details": self.details or {},
        }


class SecurityEventLogger:
    """
    Centralized security event logger for multi-tenant isolation.

    This class provides methods for logging various security events,
    particularly cross-user access attempts.

    Requirements:
    - 12.5: Log any attempted cross-user data access for security monitoring

    Usage:
        from lib.multitenancy.security import get_security_logger

        logger = get_security_logger()
        logger.log_cross_user_access_attempt(
            requesting_user=request.user,
            target_resource=bot,
        )
    """

    def __init__(self) -> None:
        """Initialize the security event logger."""
        self._logger = security_logger

    def log_event(self, event: SecurityEvent) -> None:
        """
        Log a security event.

        Args:
            event: The security event to log.
        """
        log_data = event.to_dict()

        self._logger.warning(
            "Security event: %s - user=%s attempted to access %s (id=%s) owned by user=%s",
            event.event_type.value,
            event.requesting_user_id,
            event.target_resource_type,
            event.target_resource_id,
            event.target_owner_id,
            extra={"security_event": log_data},
        )

    def log_cross_user_access_attempt(
        self,
        requesting_user: User | None,
        target_resource: Model,
        user_field: str = "user",
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        Log a cross-user access attempt.

        This method should be called when a user attempts to access
        a resource owned by another user.

        Args:
            requesting_user: The user making the request
            target_resource: The resource being accessed
            user_field: The name of the user field on the resource
            details: Additional context about the attempt

        Requirements:
        - 12.5: Log any attempted cross-user data access for security monitoring
        """
        # Get the owner of the resource
        owner = getattr(target_resource, user_field, None)
        owner_id = owner.id if owner else None

        # Get resource information
        resource_type = target_resource.__class__.__name__
        resource_id = getattr(target_resource, "id", None) or getattr(
            target_resource, "pk", None
        )

        event = SecurityEvent(
            event_type=SecurityEventType.CROSS_USER_ACCESS_ATTEMPT,
            requesting_user_id=requesting_user.id if requesting_user else None,
            target_resource_type=resource_type,
            target_resource_id=resource_id,
            target_owner_id=owner_id,
            details=details,
        )

        self.log_event(event)

    def log_unauthorized_resource_access(
        self,
        requesting_user: User | None,
        resource_type: str,
        resource_id: str | int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        Log an unauthorized resource access attempt.

        This method should be called when a user attempts to access
        a resource they don't have permission to access.

        Args:
            requesting_user: The user making the request
            resource_type: The type of resource being accessed
            resource_id: The ID of the resource
            details: Additional context about the attempt
        """
        event = SecurityEvent(
            event_type=SecurityEventType.UNAUTHORIZED_RESOURCE_ACCESS,
            requesting_user_id=requesting_user.id if requesting_user else None,
            target_resource_type=resource_type,
            target_resource_id=resource_id,
            details=details,
        )

        self.log_event(event)

    def log_bulk_operation_filtered(
        self,
        requesting_user: User | None,
        resource_type: str,
        total_requested: int,
        filtered_count: int,
        operation: str = "unknown",
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        Log when a bulk operation is filtered to user's own records.

        This method should be called when a bulk operation is performed
        and records are filtered to only include the user's own data.

        Args:
            requesting_user: The user making the request
            resource_type: The type of resources being operated on
            total_requested: Total number of records requested
            filtered_count: Number of records after filtering
            operation: The type of bulk operation
            details: Additional context

        Requirements:
        - 12.6: Filter all records by user before bulk operations
        """
        event_details = {
            "operation": operation,
            "total_requested": total_requested,
            "filtered_count": filtered_count,
            **(details or {}),
        }

        event = SecurityEvent(
            event_type=SecurityEventType.BULK_OPERATION_FILTERED,
            requesting_user_id=requesting_user.id if requesting_user else None,
            target_resource_type=resource_type,
            details=event_details,
        )

        # Only log as warning if records were filtered out
        if total_requested != filtered_count:
            self.log_event(event)
        else:
            # Log as debug if no filtering occurred
            self._logger.debug(
                "Bulk operation on %s: user=%s, operation=%s, count=%s",
                resource_type,
                requesting_user.id if requesting_user else None,
                operation,
                filtered_count,
                extra={"security_event": event.to_dict()},
            )

    def log_admin_data_access(
        self,
        admin_user: User,
        resource_type: str,
        resource_id: str | int | None = None,
        target_owner_id: int | None = None,
        action: str = "view",
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        Log when an admin accesses another user's data.

        This method should be called when an admin user accesses
        data belonging to another user.

        Args:
            admin_user: The admin user making the request
            resource_type: The type of resource being accessed
            resource_id: The ID of the resource
            target_owner_id: The ID of the user who owns the resource
            action: The action being performed (view, edit, delete)
            details: Additional context
        """
        event_details = {
            "action": action,
            "is_admin": True,
            **(details or {}),
        }

        event = SecurityEvent(
            event_type=SecurityEventType.ADMIN_DATA_ACCESS,
            requesting_user_id=admin_user.id,
            target_resource_type=resource_type,
            target_resource_id=resource_id,
            target_owner_id=target_owner_id,
            details=event_details,
        )

        # Log admin access at info level (not warning)
        self._logger.info(
            "Admin data access: admin=%s accessed %s (id=%s) owned by user=%s, action=%s",
            admin_user.id,
            resource_type,
            resource_id,
            target_owner_id,
            action,
            extra={"security_event": event.to_dict()},
        )


# Singleton instance
_security_logger: SecurityEventLogger | None = None


def get_security_logger() -> SecurityEventLogger:
    """
    Get the singleton security event logger instance.

    Returns:
        SecurityEventLogger instance for logging security events.

    Usage:
        from lib.multitenancy.security import get_security_logger

        logger = get_security_logger()
        logger.log_cross_user_access_attempt(
            requesting_user=request.user,
            target_resource=bot,
        )
    """
    global _security_logger
    if _security_logger is None:
        _security_logger = SecurityEventLogger()
    return _security_logger


def log_cross_user_access(
    requesting_user: User | None,
    target_resource: Model,
    user_field: str = "user",
    details: dict[str, Any] | None = None,
) -> None:
    """
    Convenience function to log a cross-user access attempt.

    This is a shortcut for getting the security logger and calling
    log_cross_user_access_attempt.

    Args:
        requesting_user: The user making the request
        target_resource: The resource being accessed
        user_field: The name of the user field on the resource
        details: Additional context about the attempt

    Requirements:
    - 12.5: Log any attempted cross-user data access for security monitoring

    Usage:
        from lib.multitenancy.security import log_cross_user_access

        log_cross_user_access(
            requesting_user=request.user,
            target_resource=bot,
        )
    """
    get_security_logger().log_cross_user_access_attempt(
        requesting_user=requesting_user,
        target_resource=target_resource,
        user_field=user_field,
        details=details,
    )
