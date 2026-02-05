"""
View mixins for multi-tenant user data isolation.

This module provides mixins for Django REST Framework views that enforce
user-based data isolation, ensuring users can only access their own data.

Requirements:
- 12.2: Verify user ownership before serialization
- 12.4: Verify user ownership for direct object lookups
- 12.5: Log any attempted cross-user data access for security monitoring
- 10.2: Admin bypass for superusers
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.http import Http404

from lib.multitenancy.security import get_security_logger

if TYPE_CHECKING:
    from django.db.models import QuerySet

logger = logging.getLogger(__name__)


class UserIsolationMixin:
    """
    Mixin for views that enforces user data isolation.

    This mixin overrides get_queryset() to filter results by the authenticated
    user, and perform_create() to associate new objects with the current user.
    It also provides ownership verification for detail views.

    Usage:
        class MyModelListView(UserIsolationMixin, generics.ListCreateAPIView):
            queryset = MyModel.objects.all()
            serializer_class = MyModelSerializer

    Requirements:
    - 12.2: Verify user ownership before serialization
    - 12.4: Verify user ownership for direct object lookups
    - 10.2: Admin bypass for superusers
    """

    # Set to True to log cross-user access attempts
    log_access_attempts: bool = True

    # Field name for user foreign key (default: 'user')
    user_field: str = "user"

    def get_queryset(self) -> QuerySet:
        """
        Filter queryset to current user's data only.

        Superusers (admins) bypass the filter and see all records.
        Regular users only see their own records.

        Returns:
            QuerySet filtered appropriately based on user role.

        Requirements:
        - 12.2: Verify user ownership before serialization
        - 10.2: Admin bypass for superusers
        """
        queryset = super().get_queryset()

        # Check if user is authenticated
        if not hasattr(self, "request") or not self.request.user.is_authenticated:
            return queryset.none()

        # Admin bypass - return all records
        if self.request.user.is_superuser:
            logger.debug(
                "Admin user %s accessing all records for %s",
                self.request.user.id,
                queryset.model.__name__,
            )
            return queryset

        # Filter by user
        filter_kwargs = {self.user_field: self.request.user}
        return queryset.filter(**filter_kwargs)

    def perform_create(self, serializer) -> None:
        """
        Associate new objects with the current user.

        This method is called when creating new objects through the API.
        It automatically sets the user field to the authenticated user.

        Args:
            serializer: The serializer instance with validated data.

        Requirements:
        - 3.3: Associate new bots with authenticated user
        - 4.3: Associate new trades with user
        - 5.3: Associate new portfolio snapshots with user
        """
        save_kwargs = {self.user_field: self.request.user}
        serializer.save(**save_kwargs)

    def get_object(self) -> Any:
        """
        Get object with ownership verification.

        This method retrieves the object and verifies that the current user
        owns it. If the user doesn't own the object, a 404 is returned
        (not 403) to prevent information leakage about other users' data.

        Returns:
            The requested object if owned by the current user.

        Raises:
            Http404: If the object doesn't exist or isn't owned by the user.

        Requirements:
        - 12.4: Verify user ownership for direct object lookups
        - 3.4, 4.4, 5.4: Return 404 for cross-user access attempts
        """
        obj = super().get_object()

        # Admin bypass
        if self.request.user.is_superuser:
            return obj

        # Verify ownership
        obj_user = getattr(obj, self.user_field, None)
        if obj_user is None or obj_user != self.request.user:
            # Log the cross-user access attempt
            if self.log_access_attempts:
                self._log_cross_user_access_attempt(obj)

            # Return 404 to prevent information leakage
            raise Http404("Not found.")

        return obj

    def _log_cross_user_access_attempt(self, obj: Any) -> None:
        """
        Log a cross-user access attempt for security monitoring.

        Args:
            obj: The object that was attempted to be accessed.

        Requirements:
        - 12.5: Log cross-user data access attempts
        """
        security_logger = get_security_logger()
        security_logger.log_cross_user_access_attempt(
            requesting_user=self.request.user,
            target_resource=obj,
            user_field=self.user_field,
            details={
                "view": self.__class__.__name__,
                "method": getattr(self.request, "method", "unknown"),
                "path": getattr(self.request, "path", "unknown"),
            },
        )

    def check_object_permissions(self, request, obj) -> None:
        """
        Check object-level permissions including ownership.

        This method is called by DRF's retrieve/update/delete views.
        It verifies ownership in addition to standard permission checks.

        Args:
            request: The HTTP request.
            obj: The object being accessed.

        Raises:
            Http404: If the user doesn't own the object.

        Requirements:
        - 12.4: Verify user ownership for direct object lookups
        """
        super().check_object_permissions(request, obj)

        # Admin bypass
        if request.user.is_superuser:
            return

        # Verify ownership
        obj_user = getattr(obj, self.user_field, None)
        if obj_user is None or obj_user != request.user:
            if self.log_access_attempts:
                self._log_cross_user_access_attempt(obj)
            raise Http404("Not found.")


class UserOwnershipMixin:
    """
    Mixin for verifying user ownership on update/delete operations.

    This mixin provides additional verification for operations that modify
    or delete objects, ensuring the user owns the object before proceeding.

    Usage:
        class MyModelDetailView(UserOwnershipMixin, UserIsolationMixin, generics.RetrieveUpdateDestroyAPIView):
            queryset = MyModel.objects.all()
            serializer_class = MyModelSerializer

    Requirements:
    - 3.5: Verify ownership before stopping/deleting bots
    - 12.4: Verify user ownership for direct object lookups
    """

    def perform_update(self, serializer) -> None:
        """
        Verify ownership before updating an object.

        Args:
            serializer: The serializer instance with validated data.

        Raises:
            Http404: If the user doesn't own the object.

        Requirements:
        - 12.4: Verify user ownership for direct object lookups
        """
        obj = serializer.instance
        self._verify_ownership(obj)
        serializer.save()

    def perform_destroy(self, instance) -> None:
        """
        Verify ownership before deleting an object.

        Args:
            instance: The object to delete.

        Raises:
            Http404: If the user doesn't own the object.

        Requirements:
        - 3.5: Verify ownership before stopping/deleting bots
        - 12.4: Verify user ownership for direct object lookups
        """
        self._verify_ownership(instance)
        instance.delete()

    def _verify_ownership(self, obj: Any) -> None:
        """
        Verify that the current user owns the object.

        Args:
            obj: The object to verify ownership of.

        Raises:
            Http404: If the user doesn't own the object.
        """
        # Admin bypass
        if self.request.user.is_superuser:
            return

        user_field = getattr(self, "user_field", "user")
        obj_user = getattr(obj, user_field, None)

        if obj_user is None or obj_user != self.request.user:
            # Use centralized security logging
            security_logger = get_security_logger()
            security_logger.log_cross_user_access_attempt(
                requesting_user=self.request.user,
                target_resource=obj,
                user_field=user_field,
                details={
                    "view": self.__class__.__name__,
                    "method": getattr(self.request, "method", "unknown"),
                    "path": getattr(self.request, "path", "unknown"),
                    "action": "modify",
                },
            )
            raise Http404("Not found.")
