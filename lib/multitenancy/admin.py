"""
Admin mixins for multi-tenant user data management.

This module provides admin mixins that add audit logging for admin actions
on user-owned data, ensuring accountability and traceability.

Requirements:
- 10.4: Log admin actions on user data
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.contenttypes.models import ContentType

if TYPE_CHECKING:
    from django.contrib.auth.models import User
    from django.db.models import Model
    from django.http import HttpRequest

logger = logging.getLogger(__name__)


class AdminAuditMixin:
    """
    Mixin for admin classes that adds audit logging for user data modifications.

    This mixin logs all admin actions (add, change, delete) on user-owned models,
    including the admin user ID, action type, affected record, and the owner user.

    Usage:
        @admin.register(Bot)
        class BotAdmin(AdminAuditMixin, admin.ModelAdmin):
            ...

    Requirements:
    - 10.4: Log admin actions on user data
    """

    # Field name for user foreign key (default: 'user')
    user_field: str = "user"

    def log_addition(self, request: HttpRequest, obj: Model, message: Any) -> LogEntry:
        """
        Log an addition action with user ownership info.

        Args:
            request: The HTTP request.
            obj: The object being added.
            message: The log message.

        Returns:
            The created LogEntry.

        Requirements:
        - 10.4: Log admin actions on user data
        """
        log_entry = super().log_addition(request, obj, message)
        self._log_user_data_action(request, obj, "add")
        return log_entry

    def log_change(self, request: HttpRequest, obj: Model, message: Any) -> LogEntry:
        """
        Log a change action with user ownership info.

        Args:
            request: The HTTP request.
            obj: The object being changed.
            message: The log message.

        Returns:
            The created LogEntry.

        Requirements:
        - 10.4: Log admin actions on user data
        """
        log_entry = super().log_change(request, obj, message)
        self._log_user_data_action(request, obj, "change")
        return log_entry

    def log_deletion(self, request: HttpRequest, obj: Model, object_repr: str) -> LogEntry:
        """
        Log a deletion action with user ownership info.

        Args:
            request: The HTTP request.
            obj: The object being deleted.
            object_repr: String representation of the object.

        Returns:
            The created LogEntry.

        Requirements:
        - 10.4: Log admin actions on user data
        """
        log_entry = super().log_deletion(request, obj, object_repr)
        self._log_user_data_action(request, obj, "delete")
        return log_entry

    def _log_user_data_action(
        self, request: HttpRequest, obj: Model, action_type: str
    ) -> None:
        """
        Log an admin action on user-owned data.

        This creates a structured log entry for security monitoring and audit trails.

        Args:
            request: The HTTP request containing the admin user.
            obj: The object being acted upon.
            action_type: The type of action ('add', 'change', 'delete').

        Requirements:
        - 10.4: Log admin actions on user data
        """
        owner_user = getattr(obj, self.user_field, None)
        owner_user_id = owner_user.id if owner_user else None
        owner_username = owner_user.username if owner_user else "N/A"

        logger.info(
            "Admin action on user data: admin_user_id=%s, admin_username=%s, "
            "action=%s, model=%s, object_id=%s, owner_user_id=%s, owner_username=%s",
            request.user.id,
            request.user.username,
            action_type,
            obj.__class__.__name__,
            getattr(obj, "id", "unknown"),
            owner_user_id,
            owner_username,
        )


def get_admin_audit_log(
    admin_user: User | None = None,
    action_flag: int | None = None,
    content_type: ContentType | None = None,
    limit: int = 100,
) -> list[LogEntry]:
    """
    Retrieve admin audit log entries with optional filtering.

    Args:
        admin_user: Filter by admin user who performed the action.
        action_flag: Filter by action type (ADDITION, CHANGE, DELETION).
        content_type: Filter by content type of affected objects.
        limit: Maximum number of entries to return.

    Returns:
        List of LogEntry objects matching the filters.

    Requirements:
    - 10.4: Log admin actions on user data
    """
    queryset = LogEntry.objects.all()

    if admin_user is not None:
        queryset = queryset.filter(user=admin_user)

    if action_flag is not None:
        queryset = queryset.filter(action_flag=action_flag)

    if content_type is not None:
        queryset = queryset.filter(content_type=content_type)

    return list(queryset.order_by("-action_time")[:limit])
