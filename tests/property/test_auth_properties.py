"""
Property-based tests for Token Authentication.

Feature: multi-tenant-user-isolation
Property 13: Token Authentication User Identification
Property 14: Invalid Token Rejection
Property 15: Token Regeneration Invalidation
Property 18: Protected Page Authentication Requirement

These tests use the hypothesis library to verify that token authentication
correctly identifies users across a wide range of inputs and rejects invalid tokens.
"""

from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import User
from hypothesis import HealthCheck, given
from hypothesis import settings as hypothesis_settings
from hypothesis import strategies as st
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import AuthenticationFailed


def create_test_user(username: str | None = None, email: str | None = None) -> User:
    """Create a test user with a unique username."""
    if username is None:
        username = f"testuser_{uuid.uuid4().hex[:8]}"
    if email is None:
        email = f"{username}@example.com"
    return User.objects.create_user(
        username=username,
        email=email,
        password="testpass123",
    )


def create_token_for_user(user: User) -> Token:
    """Create an authentication token for a user."""
    token, _ = Token.objects.get_or_create(user=user)
    return token


@pytest.mark.django_db(transaction=True)
class TestTokenAuthenticationUserIdentification:
    """
    Property 13: Token Authentication User Identification

    *For any* API request with a valid authentication token, the request.user
    SHALL be set to the user who owns that token.

    Feature: multi-tenant-user-isolation, Property 13: Token Authentication User Identification

    **Validates: Requirements 9.3**
    """

    @hypothesis_settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_users=st.integers(min_value=1, max_value=5),
    )
    def test_token_identifies_correct_user(
        self,
        num_users: int,
    ) -> None:
        """
        Property: Valid tokens correctly identify the token owner.

        Feature: multi-tenant-user-isolation, Property 13: Token Authentication User Identification

        **Validates: Requirements 9.3**
        """
        users_and_tokens: list[tuple[User, Token]] = []
        auth = TokenAuthentication()

        try:
            for _ in range(num_users):
                user = create_test_user()
                token = create_token_for_user(user)
                users_and_tokens.append((user, token))

            for user, token in users_and_tokens:
                authenticated_user, auth_token = auth.authenticate_credentials(token.key)
                assert authenticated_user.id == user.id
                assert authenticated_user.username == user.username
                assert auth_token.key == token.key

        finally:
            for user, token in users_and_tokens:
                token.delete()
                user.delete()

    @hypothesis_settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_users=st.integers(min_value=2, max_value=5),
    )
    def test_different_tokens_identify_different_users(
        self,
        num_users: int,
    ) -> None:
        """
        Property: Different tokens identify their respective owners correctly.

        Feature: multi-tenant-user-isolation, Property 13: Token Authentication User Identification

        **Validates: Requirements 9.3**
        """
        users_and_tokens: list[tuple[User, Token]] = []
        auth = TokenAuthentication()

        try:
            for _ in range(num_users):
                user = create_test_user()
                token = create_token_for_user(user)
                users_and_tokens.append((user, token))

            for i, (owner, token) in enumerate(users_and_tokens):
                authenticated_user, _ = auth.authenticate_credentials(token.key)
                assert authenticated_user.id == owner.id

                for j, (other_user, _) in enumerate(users_and_tokens):
                    if i != j:
                        assert authenticated_user.id != other_user.id

        finally:
            for user, token in users_and_tokens:
                token.delete()
                user.delete()

    @hypothesis_settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_requests=st.integers(min_value=1, max_value=10),
    )
    def test_token_consistently_identifies_user(
        self,
        num_requests: int,
    ) -> None:
        """
        Property: A token consistently identifies the same user across multiple authentications.

        Feature: multi-tenant-user-isolation, Property 13: Token Authentication User Identification

        **Validates: Requirements 9.3**
        """
        user = create_test_user()
        token = create_token_for_user(user)
        auth = TokenAuthentication()

        try:
            identified_user_ids = []
            for _ in range(num_requests):
                authenticated_user, _ = auth.authenticate_credentials(token.key)
                identified_user_ids.append(authenticated_user.id)

            assert all(uid == user.id for uid in identified_user_ids)

        finally:
            token.delete()
            user.delete()

    @hypothesis_settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        is_staff=st.booleans(),
        is_superuser=st.booleans(),
    )
    def test_token_identifies_user_regardless_of_permissions(
        self,
        is_staff: bool,
        is_superuser: bool,
    ) -> None:
        """
        Property: Token authentication identifies users regardless of permission level.

        Feature: multi-tenant-user-isolation, Property 13: Token Authentication User Identification

        **Validates: Requirements 9.3**
        """
        user = create_test_user()
        user.is_staff = is_staff
        user.is_superuser = is_superuser
        user.save()

        token = create_token_for_user(user)
        auth = TokenAuthentication()

        try:
            authenticated_user, _ = auth.authenticate_credentials(token.key)
            assert authenticated_user.id == user.id
            assert authenticated_user.username == user.username

        finally:
            token.delete()
            user.delete()


@pytest.mark.django_db(transaction=True)
class TestInvalidTokenRejection:
    """
    Property 14: Invalid Token Rejection

    *For any* API request with an invalid, expired, or malformed authentication token,
    the system SHALL return a 401 Unauthorized response.

    Feature: multi-tenant-user-isolation, Property 14: Invalid Token Rejection

    **Validates: Requirements 9.4**
    """

    @hypothesis_settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        random_token=st.text(
            alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
            min_size=1,
            max_size=50,
        ),
    )
    def test_random_tokens_rejected(
        self,
        random_token: str,
    ) -> None:
        """
        Property: Random strings used as tokens are rejected.

        Feature: multi-tenant-user-isolation, Property 14: Invalid Token Rejection

        **Validates: Requirements 9.4**
        """
        auth = TokenAuthentication()

        with pytest.raises(AuthenticationFailed):
            auth.authenticate_credentials(random_token)

    @hypothesis_settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        hex_token=st.text(
            alphabet="0123456789abcdef",
            min_size=40,
            max_size=40,
        ),
    )
    def test_fake_hex_tokens_rejected(
        self,
        hex_token: str,
    ) -> None:
        """
        Property: Fake hex tokens (similar format to real tokens) are rejected.

        Feature: multi-tenant-user-isolation, Property 14: Invalid Token Rejection

        **Validates: Requirements 9.4**
        """
        auth = TokenAuthentication()

        with pytest.raises(AuthenticationFailed):
            auth.authenticate_credentials(hex_token)

    @hypothesis_settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_users=st.integers(min_value=1, max_value=3),
    )
    def test_deleted_user_token_rejected(
        self,
        num_users: int,
    ) -> None:
        """
        Property: Tokens for deleted users are rejected.

        Feature: multi-tenant-user-isolation, Property 14: Invalid Token Rejection

        **Validates: Requirements 9.4**
        """
        auth = TokenAuthentication()
        deleted_tokens: list[str] = []

        for _ in range(num_users):
            user = create_test_user()
            token = create_token_for_user(user)
            token_key = token.key
            deleted_tokens.append(token_key)
            user.delete()  # Cascades to token

        for token_key in deleted_tokens:
            with pytest.raises(AuthenticationFailed):
                auth.authenticate_credentials(token_key)

    @hypothesis_settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        modification=st.sampled_from([
            "prepend_char",
            "append_char",
            "truncate",
            "extend",
            "replace_char",
        ]),
    )
    def test_modified_valid_token_rejected(
        self,
        modification: str,
    ) -> None:
        """
        Property: Modified versions of valid tokens are rejected.

        Feature: multi-tenant-user-isolation, Property 14: Invalid Token Rejection

        **Validates: Requirements 9.4**
        """
        user = create_test_user()
        token = create_token_for_user(user)
        original_key = token.key
        auth = TokenAuthentication()

        try:
            if modification == "prepend_char":
                modified_key = "x" + original_key
            elif modification == "append_char":
                modified_key = original_key + "x"
            elif modification == "truncate":
                modified_key = original_key[:-1]
            elif modification == "extend":
                modified_key = original_key + original_key[:5]
            elif modification == "replace_char":
                modified_key = ("f" if original_key[0] == "0" else "0") + original_key[1:]
            else:
                modified_key = original_key + "modified"

            with pytest.raises(AuthenticationFailed):
                auth.authenticate_credentials(modified_key)

        finally:
            token.delete()
            user.delete()


@pytest.mark.django_db(transaction=True)
class TestTokenRegenerationInvalidation:
    """
    Property 15: Token Regeneration Invalidation

    *For any* user who regenerates their API token, requests using the previous
    token SHALL return 401 Unauthorized.

    Feature: multi-tenant-user-isolation, Property 15: Token Regeneration Invalidation

    **Validates: Requirements 9.6**
    """

    @hypothesis_settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_regenerations=st.integers(min_value=1, max_value=5),
    )
    def test_old_token_invalidated_after_regeneration(
        self,
        num_regenerations: int,
    ) -> None:
        """
        Property: Old tokens are invalidated after regeneration.

        Feature: multi-tenant-user-isolation, Property 15: Token Regeneration Invalidation

        **Validates: Requirements 9.6**
        """
        user = create_test_user()
        auth = TokenAuthentication()
        old_tokens: list[str] = []

        try:
            for _ in range(num_regenerations):
                token = create_token_for_user(user)
                old_key = token.key
                old_tokens.append(old_key)

                # Regenerate by deleting and creating new
                token.delete()
                Token.objects.filter(user=user).delete()

            # Create final token
            final_token = Token.objects.create(user=user)

            # All old tokens should be rejected
            for old_key in old_tokens:
                with pytest.raises(AuthenticationFailed):
                    auth.authenticate_credentials(old_key)

            # New token should work
            authenticated_user, _ = auth.authenticate_credentials(final_token.key)
            assert authenticated_user.id == user.id

        finally:
            Token.objects.filter(user=user).delete()
            user.delete()

    @hypothesis_settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_users=st.integers(min_value=2, max_value=4),
    )
    def test_regeneration_only_invalidates_own_token(
        self,
        num_users: int,
    ) -> None:
        """
        Property: Regenerating one user's token doesn't affect other users' tokens.

        Feature: multi-tenant-user-isolation, Property 15: Token Regeneration Invalidation

        **Validates: Requirements 9.6**
        """
        users_and_tokens: list[tuple[User, Token]] = []
        auth = TokenAuthentication()

        try:
            for _ in range(num_users):
                user = create_test_user()
                token = create_token_for_user(user)
                users_and_tokens.append((user, token))

            # Regenerate first user's token
            first_user, first_token = users_and_tokens[0]
            old_key = first_token.key
            first_token.delete()
            new_token = Token.objects.create(user=first_user)
            users_and_tokens[0] = (first_user, new_token)

            # Old token should be rejected
            with pytest.raises(AuthenticationFailed):
                auth.authenticate_credentials(old_key)

            # Other users' tokens should still work
            for user, token in users_and_tokens[1:]:
                authenticated_user, _ = auth.authenticate_credentials(token.key)
                assert authenticated_user.id == user.id

        finally:
            for user, token in users_and_tokens:
                Token.objects.filter(user=user).delete()
                user.delete()


@pytest.mark.django_db(transaction=True)
class TestProtectedPageAuthenticationRequirement:
    """
    Property 18: Protected Page Authentication Requirement

    *For any* unauthenticated request to a protected portal page, the system SHALL
    redirect to the login page.

    Feature: multi-tenant-user-isolation, Property 18: Protected Page Authentication Requirement

    **Validates: Requirements 8.4, 8.5**
    """

    PROTECTED_PORTAL_PATHS: list[str] = [
        "/",
        "/bots/",
        "/trading/signals/",
        "/analysis/",
        "/settings/",
    ]

    @hypothesis_settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        path_index=st.integers(min_value=0, max_value=4),
    )
    def test_unauthenticated_request_redirects_to_login(
        self,
        path_index: int,
        client,
    ) -> None:
        """
        Property: Unauthenticated requests to protected pages redirect to login.

        Feature: multi-tenant-user-isolation, Property 18: Protected Page Authentication Requirement

        **Validates: Requirements 8.4, 8.5**
        """
        path = self.PROTECTED_PORTAL_PATHS[path_index % len(self.PROTECTED_PORTAL_PATHS)]
        response = client.get(path)

        assert response.status_code == 302
        assert "/accounts/login/" in response.url

    @hypothesis_settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        path_index=st.integers(min_value=0, max_value=4),
    )
    def test_authenticated_user_can_access_protected_pages(
        self,
        path_index: int,
        client,
    ) -> None:
        """
        Property: Authenticated users can access protected pages.

        Feature: multi-tenant-user-isolation, Property 18: Protected Page Authentication Requirement

        **Validates: Requirements 8.4, 8.5**
        """
        user = create_test_user()

        try:
            client.force_login(user)
            path = self.PROTECTED_PORTAL_PATHS[path_index % len(self.PROTECTED_PORTAL_PATHS)]
            response = client.get(path)

            # Should not redirect to login (200 or 404 for missing resources is OK)
            assert response.status_code != 302 or "/accounts/login/" not in response.url

        finally:
            user.delete()

    @hypothesis_settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        public_path_index=st.integers(min_value=0, max_value=2),
    )
    def test_public_paths_accessible_without_auth(
        self,
        public_path_index: int,
        client,
    ) -> None:
        """
        Property: Public paths are accessible without authentication.

        Feature: multi-tenant-user-isolation, Property 18: Protected Page Authentication Requirement

        **Validates: Requirements 8.4, 8.5**
        """
        public_paths = [
            "/accounts/login/",
            "/accounts/logout/",
            "/api/v1/signals/",  # API uses token auth, not session
        ]

        path = public_paths[public_path_index % len(public_paths)]
        response = client.get(path)

        # Should not redirect to login
        assert response.status_code != 302 or "/accounts/login/" not in response.url
