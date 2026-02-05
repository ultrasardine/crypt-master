"""
User-filtered model managers for multi-tenant data isolation.

This module provides base manager and queryset classes that automatically
filter data by user, ensuring users can only access their own data.

Requirements:
- 12.1: Row-level filtering on all user-owned models
- 12.3: Query-level filtering using Django's model managers
- 10.2: Admin bypass for superusers
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import models
from django.db.models import QuerySet

if TYPE_CHECKING:
    from django.contrib.auth.models import User
    from django.http import HttpRequest

logger = logging.getLogger(__name__)


class UserFilteredQuerySet(QuerySet):
    """
    Base QuerySet with user filtering capabilities.

    This queryset provides methods to filter results by user ownership,
    ensuring data isolation in a multi-tenant environment.

    Requirements:
    - 12.1: Row-level filtering on all user-owned models
    - 12.3: Query-level filtering using Django's model managers
    """

    def for_user(self, user: User) -> UserFilteredQuerySet:
        """
        Filter queryset to only include records owned by the specified user.

        Args:
            user: The user to filter records for.

        Returns:
            QuerySet filtered to the user's records.

        Requirements:
        - 12.1: Row-level filtering on all user-owned models
        - 12.3: Query-level filtering using Django's model managers
        """
        return self.filter(user=user)

    def for_request(self, request: HttpRequest) -> UserFilteredQuerySet:
        """
        Filter queryset based on the authenticated user from the request.

        Superusers (admins) bypass the filter and see all records.
        Regular users only see their own records.

        Args:
            request: The HTTP request containing the authenticated user.

        Returns:
            QuerySet filtered appropriately based on user role.

        Requirements:
        - 12.1: Row-level filtering on all user-owned models
        - 10.2: Admin bypass for superusers
        """
        if not request.user.is_authenticated:
            # Return empty queryset for unauthenticated users
            return self.none()

        if request.user.is_superuser:
            # Admin bypass - return all records
            logger.debug(
                "Admin user %s accessing all records for %s",
                request.user.id,
                self.model.__name__,
            )
            return self.all()

        return self.for_user(request.user)


class UserFilteredManager(models.Manager):
    """
    Base manager class with user filtering capabilities.

    This manager provides methods to filter querysets by user ownership,
    ensuring consistent data isolation across the application.

    Usage:
        class MyModel(models.Model):
            user = models.ForeignKey(User, on_delete=models.CASCADE)
            # ... other fields

            objects = UserFilteredManager()

        # In views:
        queryset = MyModel.objects.for_user(request.user)
        # or
        queryset = MyModel.objects.for_request(request)

    Requirements:
    - 12.1: Row-level filtering on all user-owned models
    - 12.3: Query-level filtering using Django's model managers
    - 10.2: Admin bypass for superusers
    """

    def get_queryset(self) -> UserFilteredQuerySet:
        """
        Return the custom UserFilteredQuerySet.

        Returns:
            UserFilteredQuerySet instance for this manager.
        """
        return UserFilteredQuerySet(self.model, using=self._db)

    def for_user(self, user: User) -> UserFilteredQuerySet:
        """
        Get all records for a specific user.

        Args:
            user: The user to filter records for.

        Returns:
            QuerySet filtered to the user's records.

        Requirements:
        - 12.1: Row-level filtering on all user-owned models
        - 12.3: Query-level filtering using Django's model managers
        """
        return self.get_queryset().for_user(user)

    def for_request(self, request: HttpRequest) -> UserFilteredQuerySet:
        """
        Get records filtered based on the authenticated user from the request.

        Superusers (admins) bypass the filter and see all records.
        Regular users only see their own records.

        Args:
            request: The HTTP request containing the authenticated user.

        Returns:
            QuerySet filtered appropriately based on user role.

        Requirements:
        - 12.1: Row-level filtering on all user-owned models
        - 10.2: Admin bypass for superusers
        """
        return self.get_queryset().for_request(request)
