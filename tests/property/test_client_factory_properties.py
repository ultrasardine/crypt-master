"""
Property-based tests for Pionex Client Factory.

Feature: multi-tenant-user-isolation
Properties 11-12: Bot Operations Use Correct API Keys, Missing API Key Handling

These tests use the hypothesis library to verify that the PionexClientFactory
correctly retrieves and uses user-specific API credentials.
"""

from __future__ import annotations

import asyncio
import string
import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from apps.bots.models import Bot, BotStatus, BotType
from apps.core.models import TradingPair
from lib.crypto.api_key_manager import APIKeyManager
from lib.pionex.client_factory import (
    MissingAPIKeysError,
    PionexClientFactory,
)


# Strategies for generating test data
api_key_strategy = st.text(
    alphabet=string.ascii_letters + string.digits,
    min_size=16,
    max_size=64,
)

api_secret_strategy = st.text(
    alphabet=string.ascii_letters + string.digits,
    min_size=16,
    max_size=64,
)


def create_test_user(username: str = None) -> User:
    """Create a test user with a unique username."""
    if username is None:
        username = f"testuser_{uuid.uuid4().hex[:8]}"
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
def api_key_manager():
    """Create an API key manager for tests."""
    return APIKeyManager(master_key="test-master-key-for-testing-only")


def run_async(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


@pytest.mark.django_db(transaction=True)
class TestBotOperationsUseCorrectAPIKeys:
    """
    Property 11: Bot Operations Use Correct API Keys

    *For any* bot operation (create, stop, evaluate) performed by the Bot_Agent,
    the Pionex API client used SHALL be initialized with the API keys belonging
    to the bot's owner.

    **Validates: Requirements 7.2, 7.3, 7.4**
    """

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        api_key=api_key_strategy,
        api_secret=api_secret_strategy,
    )
    def test_client_uses_user_api_keys(
        self,
        api_key_manager,
        api_key: str,
        api_secret: str,
    ) -> None:
        """
        Property: get_client_for_user() creates client with user's API keys.

        Feature: multi-tenant-user-isolation, Property 11: Bot Operations Use Correct API Keys

        **Validates: Requirements 7.2**
        """
        user = create_test_user()

        try:
            # Set up API keys for the user
            profile = user.profile
            profile.set_api_credentials(api_key, api_secret)

            # Create factory
            factory = PionexClientFactory(api_key_manager)

            # Mock PionexClient to capture initialization args
            with patch("lib.pionex.client_factory.PionexClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client

                # Get client for user (run async in sync context)
                run_async(factory.get_client_for_user(user))

                # Verify client was created with correct keys
                mock_client_class.assert_called_once()
                call_kwargs = mock_client_class.call_args[1]

                # The decrypted keys should match the original
                assert call_kwargs["api_key"] == api_key
                assert call_kwargs["api_secret"] == api_secret

        finally:
            user.delete()

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        api_key=api_key_strategy,
        api_secret=api_secret_strategy,
    )
    def test_client_for_bot_uses_owner_keys(
        self,
        trading_pair,
        api_key_manager,
        api_key: str,
        api_secret: str,
    ) -> None:
        """
        Property: get_client_for_bot() creates client with bot owner's API keys.

        Feature: multi-tenant-user-isolation, Property 11: Bot Operations Use Correct API Keys

        **Validates: Requirements 7.3, 7.4**
        """
        user = create_test_user()

        try:
            # Set up API keys for the user
            profile = user.profile
            profile.set_api_credentials(api_key, api_secret)

            # Create a bot owned by the user
            bot = Bot.objects.create(
                user=user,
                pionex_bot_id=f"bot_{uuid.uuid4().hex[:8]}",
                bot_type=BotType.GRID,
                trading_pair=trading_pair,
                status=BotStatus.ACTIVE,
                invested_amount="100.00",
            )

            # Create factory
            factory = PionexClientFactory(api_key_manager)

            # Mock PionexClient to capture initialization args
            with patch("lib.pionex.client_factory.PionexClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client

                # Get client for bot
                run_async(factory.get_client_for_bot(bot))

                # Verify client was created with owner's keys
                mock_client_class.assert_called_once()
                call_kwargs = mock_client_class.call_args[1]

                assert call_kwargs["api_key"] == api_key
                assert call_kwargs["api_secret"] == api_secret

        finally:
            Bot.objects.filter(user=user).delete()
            user.delete()

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_users=st.integers(min_value=2, max_value=4),
    )
    def test_different_users_get_different_clients(
        self,
        trading_pair,
        api_key_manager,
        num_users: int,
    ) -> None:
        """
        Property: Different users get clients with their own API keys.

        Feature: multi-tenant-user-isolation, Property 11: Bot Operations Use Correct API Keys

        **Validates: Requirements 7.2, 7.3**
        """
        users = []
        user_keys = {}

        try:
            # Create users with different API keys
            for i in range(num_users):
                user = create_test_user()
                users.append(user)

                # Generate valid alphanumeric API keys (16-64 chars)
                api_key = f"apikey{uuid.uuid4().hex}"[:32]
                api_secret = f"secret{uuid.uuid4().hex}"[:32]
                user_keys[user.id] = (api_key, api_secret)

                profile = user.profile
                profile.set_api_credentials(api_key, api_secret)

            # Create factory
            factory = PionexClientFactory(api_key_manager)

            # Verify each user gets their own keys
            for user in users:
                expected_key, expected_secret = user_keys[user.id]

                with patch("lib.pionex.client_factory.PionexClient") as mock_client_class:
                    mock_client = MagicMock()
                    mock_client_class.return_value = mock_client

                    run_async(factory.get_client_for_user(user))

                    call_kwargs = mock_client_class.call_args[1]
                    assert call_kwargs["api_key"] == expected_key, (
                        f"User {user.username} should get their own API key"
                    )
                    assert call_kwargs["api_secret"] == expected_secret, (
                        f"User {user.username} should get their own API secret"
                    )

        finally:
            for user in users:
                user.delete()

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        api_key=api_key_strategy,
        api_secret=api_secret_strategy,
    )
    def test_bot_uses_owner_keys_not_other_user_keys(
        self,
        trading_pair,
        api_key_manager,
        api_key: str,
        api_secret: str,
    ) -> None:
        """
        Property: Bot operations use owner's keys, not another user's keys.

        Feature: multi-tenant-user-isolation, Property 11: Bot Operations Use Correct API Keys

        **Validates: Requirements 7.2, 7.3, 7.4**
        """
        owner = create_test_user()
        other_user = create_test_user()

        try:
            # Set up different API keys for each user
            owner_key = api_key
            owner_secret = api_secret
            # Generate different valid keys for other user
            other_key = f"other{uuid.uuid4().hex}"[:32]
            other_secret = f"othersec{uuid.uuid4().hex}"[:32]

            owner.profile.set_api_credentials(owner_key, owner_secret)
            other_user.profile.set_api_credentials(other_key, other_secret)

            # Create a bot owned by owner
            bot = Bot.objects.create(
                user=owner,
                pionex_bot_id=f"bot_{uuid.uuid4().hex[:8]}",
                bot_type=BotType.GRID,
                trading_pair=trading_pair,
                status=BotStatus.ACTIVE,
                invested_amount="100.00",
            )

            factory = PionexClientFactory(api_key_manager)

            with patch("lib.pionex.client_factory.PionexClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client

                run_async(factory.get_client_for_bot(bot))

                call_kwargs = mock_client_class.call_args[1]

                # Should use owner's keys, not other user's
                assert call_kwargs["api_key"] == owner_key
                assert call_kwargs["api_secret"] == owner_secret
                assert call_kwargs["api_key"] != other_key
                assert call_kwargs["api_secret"] != other_secret

        finally:
            Bot.objects.filter(user=owner).delete()
            owner.delete()
            other_user.delete()


@pytest.mark.django_db(transaction=True)
class TestGracefulHandlingOfMissingAPIKeys:
    """
    Property 12: Graceful Handling of Missing API Keys

    *For any* user without configured API keys, bot operations for that user
    SHALL be skipped without affecting other users, and an error SHALL be logged.

    **Validates: Requirements 7.5**
    """

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        has_api_keys=st.booleans(),
    )
    def test_missing_api_keys_raises_error(
        self,
        api_key_manager,
        has_api_keys: bool,
    ) -> None:
        """
        Property: Users without API keys raise MissingAPIKeysError.

        Feature: multi-tenant-user-isolation, Property 12: Graceful Handling of Missing API Keys

        **Validates: Requirements 7.5**
        """
        user = create_test_user()

        try:
            if has_api_keys:
                # Set up valid API keys (alphanumeric only)
                user.profile.set_api_credentials(
                    f"apikey{uuid.uuid4().hex}"[:32],
                    f"secret{uuid.uuid4().hex}"[:32],
                )

            factory = PionexClientFactory(api_key_manager)

            if has_api_keys:
                # Should succeed
                with patch("lib.pionex.client_factory.PionexClient") as mock_client_class:
                    mock_client = MagicMock()
                    mock_client_class.return_value = mock_client
                    client = run_async(factory.get_client_for_user(user))
                    assert client is not None
            else:
                # Should raise MissingAPIKeysError
                with pytest.raises(MissingAPIKeysError) as exc_info:
                    run_async(factory.get_client_for_user(user))

                assert exc_info.value.user_id == user.id
                assert exc_info.value.username == user.username

        finally:
            user.delete()

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        num_users_with_keys=st.integers(min_value=1, max_value=3),
        num_users_without_keys=st.integers(min_value=1, max_value=3),
    )
    def test_missing_keys_dont_affect_other_users(
        self,
        api_key_manager,
        num_users_with_keys: int,
        num_users_without_keys: int,
    ) -> None:
        """
        Property: Missing API keys for one user don't affect other users.

        Feature: multi-tenant-user-isolation, Property 12: Graceful Handling of Missing API Keys

        **Validates: Requirements 7.5**
        """
        users_with_keys = []
        users_without_keys = []

        try:
            # Create users with API keys (valid alphanumeric format)
            for i in range(num_users_with_keys):
                user = create_test_user()
                user.profile.set_api_credentials(
                    f"apikey{uuid.uuid4().hex}"[:32],
                    f"secret{uuid.uuid4().hex}"[:32],
                )
                users_with_keys.append(user)

            # Create users without API keys
            for i in range(num_users_without_keys):
                user = create_test_user()
                # Don't set API keys
                users_without_keys.append(user)

            factory = PionexClientFactory(api_key_manager)

            # Users with keys should work
            for user in users_with_keys:
                with patch("lib.pionex.client_factory.PionexClient") as mock_client_class:
                    mock_client = MagicMock()
                    mock_client_class.return_value = mock_client
                    client = run_async(factory.get_client_for_user(user))
                    assert client is not None

            # Users without keys should fail gracefully
            for user in users_without_keys:
                with pytest.raises(MissingAPIKeysError):
                    run_async(factory.get_client_for_user(user))

            # Verify users with keys still work after failures
            for user in users_with_keys:
                with patch("lib.pionex.client_factory.PionexClient") as mock_client_class:
                    mock_client = MagicMock()
                    mock_client_class.return_value = mock_client
                    client = run_async(factory.get_client_for_user(user))
                    assert client is not None

        finally:
            for user in users_with_keys + users_without_keys:
                user.delete()

    def test_bot_with_owner_gets_client(
        self,
        trading_pair,
        api_key_manager,
    ) -> None:
        """
        Property: Bots with owners can get a client when owner has API keys.

        Feature: multi-tenant-user-isolation, Property 12: Graceful Handling of Missing API Keys

        **Validates: Requirements 7.5**

        Note: User FK is now non-nullable (Requirements 11.3), so all bots
        must have an owner. This test verifies that bots with owners who have
        API keys can successfully get a client.
        """
        owner = create_test_user()

        try:
            owner.profile.set_api_credentials(
                f"apikey{uuid.uuid4().hex}"[:32],
                f"secret{uuid.uuid4().hex}"[:32],
            )

            bot = Bot.objects.create(
                user=owner,
                pionex_bot_id=f"bot_{uuid.uuid4().hex[:8]}",
                bot_type=BotType.GRID,
                trading_pair=trading_pair,
                status=BotStatus.ACTIVE,
                invested_amount="100.00",
            )

            factory = PionexClientFactory(api_key_manager)

            with patch("lib.pionex.client_factory.PionexClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client
                client = run_async(factory.get_client_for_bot(bot))
                assert client is not None

        finally:
            Bot.objects.filter(pionex_bot_id=bot.pionex_bot_id).delete()
            owner.delete()

    def test_bot_owner_without_api_keys_raises_error(
        self,
        trading_pair,
        api_key_manager,
    ) -> None:
        """
        Property: Bots with owners who have no API keys raise MissingAPIKeysError.

        Feature: multi-tenant-user-isolation, Property 12: Graceful Handling of Missing API Keys

        **Validates: Requirements 7.5**

        Note: User FK is now non-nullable (Requirements 11.3), so all bots
        must have an owner. This test verifies that bots with owners who
        don't have API keys configured raise an appropriate error.
        """
        owner = create_test_user()

        try:
            # Don't set API credentials for owner

            bot = Bot.objects.create(
                user=owner,
                pionex_bot_id=f"bot_{uuid.uuid4().hex[:8]}",
                bot_type=BotType.GRID,
                trading_pair=trading_pair,
                status=BotStatus.ACTIVE,
                invested_amount="100.00",
            )

            factory = PionexClientFactory(api_key_manager)

            with pytest.raises(MissingAPIKeysError) as exc_info:
                run_async(factory.get_client_for_bot(bot))
            assert "no api keys" in str(exc_info.value).lower()

        finally:
            Bot.objects.filter(pionex_bot_id=bot.pionex_bot_id).delete()
            owner.delete()

    def test_has_api_keys_check(self, api_key_manager) -> None:
        """
        Test that has_api_keys() correctly checks for API key presence.

        **Validates: Requirements 7.5**
        """
        user = create_test_user()

        try:
            factory = PionexClientFactory(api_key_manager)

            # Initially no keys
            assert factory.has_api_keys(user) is False

            # After setting keys (valid alphanumeric format)
            user.profile.set_api_credentials(
                f"apikey{uuid.uuid4().hex}"[:32],
                f"secret{uuid.uuid4().hex}"[:32],
            )
            assert factory.has_api_keys(user) is True

            # After clearing keys
            user.profile.clear_api_credentials()
            assert factory.has_api_keys(user) is False

        finally:
            user.delete()

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        api_key=api_key_strategy,
        api_secret=api_secret_strategy,
    )
    def test_missing_keys_logs_warning(
        self,
        api_key_manager,
        api_key: str,
        api_secret: str,
    ) -> None:
        """
        Property: Missing API keys are logged as warnings.

        Feature: multi-tenant-user-isolation, Property 12: Graceful Handling of Missing API Keys

        **Validates: Requirements 7.5**
        """
        user = create_test_user()

        try:
            factory = PionexClientFactory(api_key_manager)

            with patch("lib.pionex.client_factory.logger") as mock_logger:
                with pytest.raises(MissingAPIKeysError):
                    run_async(factory.get_client_for_user(user))

                # Verify warning was logged
                mock_logger.warning.assert_called_once()
                call_args = mock_logger.warning.call_args[0]
                assert user.username in call_args[0] or str(user.id) in str(call_args)

        finally:
            user.delete()
