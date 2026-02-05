"""
Pionex Client Factory for multi-user support.

This module provides a factory for creating user-specific Pionex API clients,
retrieving and decrypting API credentials from user profiles.

Requirements:
- 7.2: Bot operations use user-specific API keys
- 7.3: Bot creation uses correct user's API keys
- 7.5: Graceful handling of missing API keys
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from lib.crypto.api_key_manager import APIKeyManager
from lib.pionex.client import PionexClient

if TYPE_CHECKING:
    from django.contrib.auth.models import User

    from apps.bots.models import Bot

logger = logging.getLogger(__name__)


class MissingAPIKeysError(Exception):
    """Raised when a user has no API keys configured."""

    def __init__(self, user_id: int, username: str):
        self.user_id = user_id
        self.username = username
        super().__init__(f"User {username} (id={user_id}) has no API keys configured")


class APIKeyDecryptionError(Exception):
    """Raised when API key decryption fails."""

    def __init__(self, user_id: int, username: str, reason: str):
        self.user_id = user_id
        self.username = username
        self.reason = reason
        super().__init__(
            f"Failed to decrypt API keys for user {username} (id={user_id}): {reason}"
        )


class PionexClientFactory:
    """
    Factory for creating user-specific Pionex API clients.

    This factory retrieves and decrypts API credentials from user profiles
    to create Pionex clients that operate with the correct user's credentials.

    Usage:
        >>> factory = PionexClientFactory(api_key_manager)
        >>> async with await factory.get_client_for_user(user) as client:
        ...     balances = await client.get_balances()

    Requirements:
    - 7.2: Bot operations use user-specific API keys
    - 7.3: Bot creation uses correct user's API keys
    - 7.5: Graceful handling of missing API keys
    """

    def __init__(self, api_key_manager: APIKeyManager) -> None:
        """
        Initialize the factory with an API key manager.

        Args:
            api_key_manager: Manager for decrypting user API keys.
        """
        self._api_key_manager = api_key_manager

    async def get_client_for_user(self, user: User) -> PionexClient:
        """
        Create a Pionex client using the user's decrypted API keys.

        This method retrieves the user's encrypted API credentials from their
        profile, decrypts them, and creates a PionexClient instance.

        Args:
            user: The user whose API keys should be used.

        Returns:
            A PionexClient configured with the user's credentials.

        Raises:
            MissingAPIKeysError: If the user has no API keys configured.
            APIKeyDecryptionError: If decryption fails.

        Requirements:
        - 7.2: Bot operations use user-specific API keys
        - 7.5: Graceful handling of missing API keys
        """
        # Get user profile
        try:
            profile = user.profile
        except AttributeError:
            logger.error(
                "User %s (id=%s) has no profile",
                user.username,
                user.id,
            )
            raise MissingAPIKeysError(user.id, user.username)

        # Check if user has API keys
        if not profile.has_api_keys():
            logger.warning(
                "User %s (id=%s) has no API keys configured",
                user.username,
                user.id,
            )
            raise MissingAPIKeysError(user.id, user.username)

        # Decrypt API keys
        try:
            api_key = profile.get_decrypted_api_key()
            api_secret = profile.get_decrypted_api_secret()
        except Exception as e:
            logger.error(
                "Failed to decrypt API keys for user %s (id=%s): %s",
                user.username,
                user.id,
                str(e),
            )
            raise APIKeyDecryptionError(user.id, user.username, str(e)) from e

        logger.debug(
            "Created Pionex client for user %s (id=%s)",
            user.username,
            user.id,
        )

        return PionexClient(api_key=api_key, api_secret=api_secret)

    async def get_client_for_bot(self, bot: Bot) -> PionexClient:
        """
        Create a Pionex client for the bot's owner.

        This is a convenience method that retrieves the bot's owner and
        creates a client with their credentials.

        Args:
            bot: The bot whose owner's API keys should be used.

        Returns:
            A PionexClient configured with the bot owner's credentials.

        Raises:
            MissingAPIKeysError: If the bot's owner has no API keys configured.
            APIKeyDecryptionError: If decryption fails.
            ValueError: If the bot has no owner.

        Requirements:
        - 7.3: Bot creation uses correct user's API keys
        - 7.4: Bot evaluation uses correct user's API keys
        """
        if bot.user is None:
            logger.error(
                "Bot %s (id=%s) has no owner",
                bot.pionex_bot_id,
                bot.id,
            )
            raise ValueError(f"Bot {bot.pionex_bot_id} has no owner")

        return await self.get_client_for_user(bot.user)

    def has_api_keys(self, user: User) -> bool:
        """
        Check if a user has API keys configured.

        This is a synchronous method for quick checks without decryption.

        Args:
            user: The user to check.

        Returns:
            True if the user has API keys configured, False otherwise.

        Requirements:
        - 7.5: Graceful handling of missing API keys
        """
        try:
            profile = user.profile
            return profile.has_api_keys()
        except AttributeError:
            return False
