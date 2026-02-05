"""
Multi-tenancy support for user data isolation.

This module provides base classes and mixins for implementing
row-level data isolation in a multi-tenant Django application.

Components:
- UserFilteredManager: Base manager class with user filtering methods
- UserIsolationMixin: View mixin for enforcing user data isolation
- LoginRequiredMiddleware: Middleware for portal authentication
- AdminAuditMixin: Admin mixin for audit logging
- SecurityEventLogger: Centralized security event logging

Requirements:
- 8.4: Require authentication for all pages except login and registration
- 8.5: Redirect unauthenticated users to the login page
- 10.4: Log admin actions on user data
- 12.1: Row-level filtering on all user-owned models
- 12.2: Verify user ownership before serialization
- 12.3: Query-level filtering using Django's model managers
- 12.4: Verify user ownership for direct object lookups
- 12.5: Log any attempted cross-user data access for security monitoring
- 10.2: Admin bypass for superusers
"""

from lib.multitenancy.admin import AdminAuditMixin, get_admin_audit_log
from lib.multitenancy.managers import UserFilteredManager, UserFilteredQuerySet
from lib.multitenancy.middleware import LoginRequiredMiddleware
from lib.multitenancy.mixins import UserIsolationMixin, UserOwnershipMixin
from lib.multitenancy.security import (
    SecurityEvent,
    SecurityEventLogger,
    SecurityEventType,
    get_security_logger,
    log_cross_user_access,
)

__all__ = [
    "AdminAuditMixin",
    "LoginRequiredMiddleware",
    "SecurityEvent",
    "SecurityEventLogger",
    "SecurityEventType",
    "UserFilteredManager",
    "UserFilteredQuerySet",
    "UserIsolationMixin",
    "UserOwnershipMixin",
    "get_admin_audit_log",
    "get_security_logger",
    "log_cross_user_access",
]
