"""
API Key Manager for secure encryption and decryption of user API credentials.

This module provides Fernet symmetric encryption with PBKDF2 key derivation
for securely storing and retrieving user API keys. Each user has a unique
salt that is combined with the application master key to derive a user-specific
encryption key.

Requirements:
- 2.1: Encrypt API keys using Fernet symmetric encryption before storage
- 2.2: Use unique per-user salt combined with application secret key for key derivation
- 2.7: Validate API key format before encryption to prevent storing invalid credentials
"""

from __future__ import annotations

import base64
import os
import re

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class APIKeyValidationError(ValueError):
    """Raised when an API key fails format validation."""

    pass


class APIKeyDecryptionError(ValueError):
    """Raised when decryption fails due to invalid data or wrong key."""

    pass


class APIKeyManager:
    """
    Manages encryption/decryption of user API credentials.

    This class uses Fernet symmetric encryption with PBKDF2 key derivation
    to securely encrypt and decrypt API keys. Each user has a unique salt
    that ensures their encryption key is different from all other users.

    The encryption process:
    1. A unique salt is generated for each user
    2. The master key and user salt are combined using PBKDF2 to derive a user-specific key
    3. The derived key is used with Fernet to encrypt/decrypt the API credentials

    Example:
        >>> manager = APIKeyManager(master_key="your-secret-master-key")
        >>> salt = manager.generate_salt()
        >>> encrypted = manager.encrypt("my-api-key", salt)
        >>> decrypted = manager.decrypt(encrypted, salt)
        >>> assert decrypted == "my-api-key"

    Attributes:
        SALT_SIZE: Size of the salt in bytes (16 bytes = 128 bits)
        DEFAULT_PBKDF2_ITERATIONS: Default number of PBKDF2 iterations for key derivation
        PIONEX_API_KEY_PATTERN: Regex pattern for validating Pionex API keys
    """

    SALT_SIZE: int = 16  # 128 bits
    DEFAULT_PBKDF2_ITERATIONS: int = 480_000  # OWASP recommended minimum for PBKDF2-SHA256

    # Pionex API keys are alphanumeric strings, typically 32-128 characters
    # Based on observed patterns from Pionex documentation
    PIONEX_API_KEY_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z0-9]{16,128}$")

    def __init__(self, master_key: str, iterations: int | None = None) -> None:
        """
        Initialize the API Key Manager with a master key.

        Args:
            master_key: The application's master secret key used for key derivation.
                       This should be a strong, randomly generated secret stored
                       securely (e.g., in environment variables).
            iterations: Number of PBKDF2 iterations. Defaults to DEFAULT_PBKDF2_ITERATIONS.
                       Lower values can be used for testing but should never be used
                       in production.

        Raises:
            ValueError: If master_key is empty or None
        """
        if not master_key:
            raise ValueError("Master key cannot be empty")

        self._master_key = master_key.encode("utf-8")
        self._iterations = iterations if iterations is not None else self.DEFAULT_PBKDF2_ITERATIONS

    def generate_salt(self) -> bytes:
        """
        Generate a cryptographically secure random salt.

        The salt is used to derive a unique encryption key for each user.
        This ensures that even if two users have the same API key, their
        encrypted values will be different.

        Returns:
            A random salt of SALT_SIZE bytes (16 bytes / 128 bits)
        """
        return os.urandom(self.SALT_SIZE)

    def derive_user_key(self, user_salt: bytes) -> bytes:
        """
        Derive a user-specific encryption key from the master key and user salt.

        Uses PBKDF2 with SHA-256 to derive a 32-byte key suitable for Fernet.
        The high iteration count provides protection against brute-force attacks.

        Args:
            user_salt: The unique salt for this user (must be SALT_SIZE bytes)

        Returns:
            A 32-byte key encoded as URL-safe base64 for use with Fernet

        Raises:
            ValueError: If user_salt is not the correct size
        """
        if len(user_salt) != self.SALT_SIZE:
            raise ValueError(f"Salt must be exactly {self.SALT_SIZE} bytes")

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,  # Fernet requires 32-byte keys
            salt=user_salt,
            iterations=self._iterations,
        )

        derived_key = kdf.derive(self._master_key)
        # Fernet requires URL-safe base64 encoded key
        return base64.urlsafe_b64encode(derived_key)

    def encrypt(self, plaintext: str, user_salt: bytes) -> str:
        """
        Encrypt a string value using user-specific key.

        The plaintext is encrypted using Fernet symmetric encryption with
        a key derived from the master key and user salt.

        Args:
            plaintext: The string to encrypt (e.g., an API key)
            user_salt: The unique salt for this user

        Returns:
            The encrypted value as a base64-encoded string

        Raises:
            ValueError: If plaintext is empty or user_salt is invalid
        """
        if not plaintext:
            raise ValueError("Plaintext cannot be empty")

        derived_key = self.derive_user_key(user_salt)
        fernet = Fernet(derived_key)

        encrypted_bytes = fernet.encrypt(plaintext.encode("utf-8"))
        return encrypted_bytes.decode("utf-8")

    def decrypt(self, ciphertext: str, user_salt: bytes) -> str:
        """
        Decrypt a string value using user-specific key.

        The ciphertext is decrypted using Fernet symmetric encryption with
        a key derived from the master key and user salt.

        Args:
            ciphertext: The encrypted value as a base64-encoded string
            user_salt: The unique salt for this user (must match encryption salt)

        Returns:
            The decrypted plaintext string

        Raises:
            APIKeyDecryptionError: If decryption fails (wrong key, corrupted data, etc.)
            ValueError: If ciphertext is empty or user_salt is invalid
        """
        if not ciphertext:
            raise ValueError("Ciphertext cannot be empty")

        try:
            derived_key = self.derive_user_key(user_salt)
            fernet = Fernet(derived_key)

            decrypted_bytes = fernet.decrypt(ciphertext.encode("utf-8"))
            return decrypted_bytes.decode("utf-8")
        except InvalidToken as e:
            raise APIKeyDecryptionError(
                "Failed to decrypt: invalid token or wrong key"
            ) from e

    def validate_api_key_format(self, api_key: str) -> bool:
        """
        Validate Pionex API key format before encryption.

        Pionex API keys are alphanumeric strings typically between 16-64 characters.
        This validation prevents storing obviously invalid credentials.

        Args:
            api_key: The API key string to validate

        Returns:
            True if the API key matches the expected format, False otherwise
        """
        if not api_key:
            return False

        return bool(self.PIONEX_API_KEY_PATTERN.match(api_key))
