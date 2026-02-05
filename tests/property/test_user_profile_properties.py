"""
Property-based tests for UserProfile model.

Feature: multi-tenant-user-isolation
Properties 4-5: API Key Deletion Completeness, API Key Non-Exposure

These tests use the hypothesis library to verify that the UserProfile
model behaves correctly across a wide range of inputs.
"""

import string

import pytest
from django.contrib.auth.models import User
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.core.models import UserProfile
from lib.crypto.api_key_manager import APIKeyValidationError

# Strategy for valid API keys - alphanumeric strings of valid length (16-128 chars)
valid_api_key_strategy = st.text(
    alphabet=string.ascii_letters + string.digits,
    min_size=16,
    max_size=128,
)


@pytest.mark.django_db(transaction=True)
class TestAPIKeyDeletionCompleteness:
    """
    Property 4: API Key Deletion Completeness

    *For any* user with stored API keys, after calling clear_api_credentials(),
    the has_api_keys() method SHALL return False and get_decrypted_api_key()
    SHALL raise an error.

    **Validates: Requirements 2.6**
    """

    @settings(max_examples=25, deadline=None)
    @given(
        api_key=valid_api_key_strategy,
        api_secret=valid_api_key_strategy,
    )
    def test_clear_credentials_removes_all_data(
        self,
        api_key: str,
        api_secret: str,
    ) -> None:
        """
        Property: After clear_api_credentials(), has_api_keys() returns False.

        **Validates: Requirements 2.6**
        """
        # Create a unique user for this test iteration
        import uuid

        username = f"testuser_{uuid.uuid4().hex[:8]}"
        user = User.objects.create_user(username, f"{username}@example.com", "testpass")

        try:
            profile = user.profile

            # Set API credentials
            profile.set_api_credentials(api_key, api_secret)
            assert profile.has_api_keys() is True, "API keys should be set"

            # Clear credentials
            profile.clear_api_credentials()

            # Verify all credential fields are cleared
            assert profile.has_api_keys() is False, (
                "has_api_keys() should return False after clear"
            )
            assert profile.encrypted_api_key == "", "encrypted_api_key should be empty"
            assert profile.encrypted_api_secret == "", "encrypted_api_secret should be empty"
            assert profile.api_key_salt == "", "api_key_salt should be empty"
        finally:
            user.delete()

    @settings(max_examples=25, deadline=None)
    @given(
        api_key=valid_api_key_strategy,
        api_secret=valid_api_key_strategy,
    )
    def test_get_decrypted_key_raises_after_clear(
        self,
        api_key: str,
        api_secret: str,
    ) -> None:
        """
        Property: After clear_api_credentials(), get_decrypted_api_key() raises ValueError.

        **Validates: Requirements 2.6**
        """
        import uuid

        username = f"testuser_{uuid.uuid4().hex[:8]}"
        user = User.objects.create_user(username, f"{username}@example.com", "testpass")

        try:
            profile = user.profile

            # Set and then clear credentials
            profile.set_api_credentials(api_key, api_secret)
            profile.clear_api_credentials()

            # Attempting to get decrypted key should raise ValueError
            with pytest.raises(ValueError, match="No API keys configured"):
                profile.get_decrypted_api_key()
        finally:
            user.delete()

    @settings(max_examples=25, deadline=None)
    @given(
        api_key=valid_api_key_strategy,
        api_secret=valid_api_key_strategy,
    )
    def test_get_decrypted_secret_raises_after_clear(
        self,
        api_key: str,
        api_secret: str,
    ) -> None:
        """
        Property: After clear_api_credentials(), get_decrypted_api_secret() raises ValueError.

        **Validates: Requirements 2.6**
        """
        import uuid

        username = f"testuser_{uuid.uuid4().hex[:8]}"
        user = User.objects.create_user(username, f"{username}@example.com", "testpass")

        try:
            profile = user.profile

            # Set and then clear credentials
            profile.set_api_credentials(api_key, api_secret)
            profile.clear_api_credentials()

            # Attempting to get decrypted secret should raise ValueError
            with pytest.raises(ValueError, match="No API keys configured"):
                profile.get_decrypted_api_secret()
        finally:
            user.delete()

    @settings(max_examples=25, deadline=None)
    @given(
        api_key=valid_api_key_strategy,
        api_secret=valid_api_key_strategy,
    )
    def test_clear_is_idempotent(
        self,
        api_key: str,
        api_secret: str,
    ) -> None:
        """
        Property: Calling clear_api_credentials() multiple times is safe.

        **Validates: Requirements 2.6**
        """
        import uuid

        username = f"testuser_{uuid.uuid4().hex[:8]}"
        user = User.objects.create_user(username, f"{username}@example.com", "testpass")

        try:
            profile = user.profile

            # Set credentials
            profile.set_api_credentials(api_key, api_secret)

            # Clear multiple times - should not raise
            profile.clear_api_credentials()
            profile.clear_api_credentials()
            profile.clear_api_credentials()

            # Should still be cleared
            assert profile.has_api_keys() is False
        finally:
            user.delete()

    @settings(max_examples=25, deadline=None)
    @given(
        api_key=valid_api_key_strategy,
        api_secret=valid_api_key_strategy,
    )
    def test_clear_persists_to_database(
        self,
        api_key: str,
        api_secret: str,
    ) -> None:
        """
        Property: clear_api_credentials() persists the cleared state to the database.

        **Validates: Requirements 2.6**
        """
        import uuid

        username = f"testuser_{uuid.uuid4().hex[:8]}"
        user = User.objects.create_user(username, f"{username}@example.com", "testpass")

        try:
            profile = user.profile

            # Set and clear credentials
            profile.set_api_credentials(api_key, api_secret)
            profile.clear_api_credentials()

            # Refresh from database
            profile.refresh_from_db()

            # Should still be cleared after refresh
            assert profile.has_api_keys() is False, (
                "Cleared state should persist to database"
            )
            assert profile.encrypted_api_key == ""
            assert profile.encrypted_api_secret == ""
            assert profile.api_key_salt == ""
        finally:
            user.delete()



@pytest.mark.django_db(transaction=True)
class TestAPIKeyNonExposure:
    """
    Property 5: API Key Non-Exposure

    *For any* API endpoint that returns user data (profile, bots, trades, etc.),
    the response SHALL never contain decrypted API keys or secrets, regardless
    of user role (including admin).

    **Validates: Requirements 1.4, 2.4, 10.5**
    """

    @settings(max_examples=25, deadline=None)
    @given(
        api_key=valid_api_key_strategy,
        api_secret=valid_api_key_strategy,
    )
    def test_serializer_never_exposes_encrypted_fields(
        self,
        api_key: str,
        api_secret: str,
    ) -> None:
        """
        Property: UserProfileSerializer never includes encrypted fields in output.

        **Validates: Requirements 1.4, 2.4**
        """
        from apps.api.serializers import UserProfileSerializer
        import uuid

        username = f"testuser_{uuid.uuid4().hex[:8]}"
        user = User.objects.create_user(username, f"{username}@example.com", "testpass")

        try:
            profile = user.profile
            profile.set_api_credentials(api_key, api_secret)

            # Serialize the profile
            serializer = UserProfileSerializer(profile)
            data = serializer.data

            # Verify encrypted fields are not in output
            assert "encrypted_api_key" not in data, (
                "encrypted_api_key should not be in serialized output"
            )
            assert "encrypted_api_secret" not in data, (
                "encrypted_api_secret should not be in serialized output"
            )
            assert "api_key_salt" not in data, (
                "api_key_salt should not be in serialized output"
            )

            # Verify decrypted values are not in output
            assert api_key not in str(data), (
                "Decrypted API key should not appear in serialized output"
            )
            assert api_secret not in str(data), (
                "Decrypted API secret should not appear in serialized output"
            )
        finally:
            user.delete()

    @settings(max_examples=25, deadline=None)
    @given(
        api_key=valid_api_key_strategy,
        api_secret=valid_api_key_strategy,
    )
    def test_serializer_shows_has_api_keys_status(
        self,
        api_key: str,
        api_secret: str,
    ) -> None:
        """
        Property: Serializer shows has_api_keys status without exposing actual keys.

        **Validates: Requirements 1.4, 2.4**
        """
        from apps.api.serializers import UserProfileSerializer
        import uuid

        username = f"testuser_{uuid.uuid4().hex[:8]}"
        user = User.objects.create_user(username, f"{username}@example.com", "testpass")

        try:
            profile = user.profile

            # Before setting keys
            serializer = UserProfileSerializer(profile)
            assert serializer.data["has_api_keys"] is False

            # After setting keys
            profile.set_api_credentials(api_key, api_secret)
            serializer = UserProfileSerializer(profile)
            assert serializer.data["has_api_keys"] is True

            # After clearing keys
            profile.clear_api_credentials()
            serializer = UserProfileSerializer(profile)
            assert serializer.data["has_api_keys"] is False
        finally:
            user.delete()

    @settings(max_examples=25, deadline=None)
    @given(
        api_key=valid_api_key_strategy,
        api_secret=valid_api_key_strategy,
    )
    def test_api_key_write_only_fields(
        self,
        api_key: str,
        api_secret: str,
    ) -> None:
        """
        Property: api_key and api_secret fields are write-only in serializer.

        **Validates: Requirements 2.4**
        """
        from apps.api.serializers import UserProfileSerializer
        import uuid

        username = f"testuser_{uuid.uuid4().hex[:8]}"
        user = User.objects.create_user(username, f"{username}@example.com", "testpass")

        try:
            profile = user.profile
            profile.set_api_credentials(api_key, api_secret)

            # Serialize the profile
            serializer = UserProfileSerializer(profile)
            data = serializer.data

            # api_key and api_secret should not be in output (write-only)
            assert "api_key" not in data, (
                "api_key field should be write-only and not in output"
            )
            assert "api_secret" not in data, (
                "api_secret field should be write-only and not in output"
            )
        finally:
            user.delete()

    @settings(max_examples=25, deadline=None)
    @given(
        api_key=valid_api_key_strategy,
        api_secret=valid_api_key_strategy,
    )
    def test_serialized_data_safe_for_json_response(
        self,
        api_key: str,
        api_secret: str,
    ) -> None:
        """
        Property: Serialized profile data is safe to return in JSON response.

        This test verifies that converting serialized data to JSON doesn't
        accidentally expose sensitive information.

        **Validates: Requirements 1.4, 2.4, 10.5**
        """
        from apps.api.serializers import UserProfileSerializer
        import json
        import uuid

        username = f"testuser_{uuid.uuid4().hex[:8]}"
        user = User.objects.create_user(username, f"{username}@example.com", "testpass")

        try:
            profile = user.profile
            profile.set_api_credentials(api_key, api_secret)

            # Serialize and convert to JSON (simulating API response)
            serializer = UserProfileSerializer(profile)
            json_str = json.dumps(serializer.data)

            # Verify sensitive data not in JSON
            assert api_key not in json_str, (
                "API key should not appear in JSON response"
            )
            assert api_secret not in json_str, (
                "API secret should not appear in JSON response"
            )
            assert profile.encrypted_api_key not in json_str, (
                "Encrypted API key should not appear in JSON response"
            )
            assert profile.encrypted_api_secret not in json_str, (
                "Encrypted API secret should not appear in JSON response"
            )
            assert profile.api_key_salt not in json_str, (
                "API key salt should not appear in JSON response"
            )
        finally:
            user.delete()

    @settings(max_examples=25, deadline=None)
    @given(
        api_key=valid_api_key_strategy,
        api_secret=valid_api_key_strategy,
    )
    def test_model_str_does_not_expose_keys(
        self,
        api_key: str,
        api_secret: str,
    ) -> None:
        """
        Property: UserProfile __str__ method does not expose API keys.

        **Validates: Requirements 2.4**
        """
        import uuid

        username = f"testuser_{uuid.uuid4().hex[:8]}"
        user = User.objects.create_user(username, f"{username}@example.com", "testpass")

        try:
            profile = user.profile
            profile.set_api_credentials(api_key, api_secret)

            # Get string representation
            str_repr = str(profile)

            # Verify no sensitive data in string representation
            assert api_key not in str_repr, (
                "API key should not appear in __str__ output"
            )
            assert api_secret not in str_repr, (
                "API secret should not appear in __str__ output"
            )
        finally:
            user.delete()
