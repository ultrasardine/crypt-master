"""
Property-based tests for API Key Encryption.

Feature: multi-tenant-user-isolation
Properties 1-3: Encryption Round-Trip, Unique Salts, API Key Validation

These tests use the hypothesis library to verify that the encryption
module behaves correctly across a wide range of inputs.
"""

import string

from hypothesis import given, settings
from hypothesis import strategies as st

from lib.crypto.api_key_manager import APIKeyManager

# Use low iterations for testing (production uses 480,000)
TEST_ITERATIONS = 1000

# Custom strategies for generating realistic inputs
master_key_strategy = st.text(
    alphabet=string.ascii_letters + string.digits + string.punctuation,
    min_size=8,
    max_size=64,
)

# Strategy for API keys - alphanumeric strings of valid length
valid_api_key_strategy = st.text(
    alphabet=string.ascii_letters + string.digits,
    min_size=16,
    max_size=128,
)

# Strategy for arbitrary plaintext (any non-empty string)
plaintext_strategy = st.text(
    min_size=1,
    max_size=128,
)


class TestEncryptionRoundTrip:
    """
    Property 1: API Key Encryption Round-Trip

    *For any* valid API key and secret pair, encrypting them with a user's salt
    and then decrypting with the same salt SHALL produce the original values.

    **Validates: Requirements 2.1, 2.5**
    """

    @settings(max_examples=10)
    @given(
        master_key=master_key_strategy,
        plaintext=plaintext_strategy,
    )
    def test_encrypt_decrypt_round_trip(
        self,
        master_key: str,
        plaintext: str,
    ) -> None:
        """
        Property: encrypt() followed by decrypt() with the same salt
        produces the original plaintext.

        **Validates: Requirements 2.1, 2.5**
        """
        manager = APIKeyManager(master_key=master_key, iterations=TEST_ITERATIONS)
        salt = manager.generate_salt()

        # Encrypt the plaintext
        ciphertext = manager.encrypt(plaintext, salt)

        # Decrypt should return original plaintext
        decrypted = manager.decrypt(ciphertext, salt)

        assert decrypted == plaintext, (
            f"Round-trip failed: original={plaintext!r}, decrypted={decrypted!r}"
        )

    @settings(max_examples=10)
    @given(
        master_key=master_key_strategy,
        api_key=valid_api_key_strategy,
        api_secret=valid_api_key_strategy,
    )
    def test_api_credentials_round_trip(
        self,
        master_key: str,
        api_key: str,
        api_secret: str,
    ) -> None:
        """
        Property: API key and secret can be encrypted and decrypted independently.

        This simulates the real use case where both API key and secret are
        stored encrypted with the same user salt.

        **Validates: Requirements 2.1, 2.5**
        """
        manager = APIKeyManager(master_key=master_key, iterations=TEST_ITERATIONS)
        salt = manager.generate_salt()

        # Encrypt both credentials
        encrypted_key = manager.encrypt(api_key, salt)
        encrypted_secret = manager.encrypt(api_secret, salt)

        # Decrypt both credentials
        decrypted_key = manager.decrypt(encrypted_key, salt)
        decrypted_secret = manager.decrypt(encrypted_secret, salt)

        assert decrypted_key == api_key, "API key round-trip failed"
        assert decrypted_secret == api_secret, "API secret round-trip failed"

    @settings(max_examples=10)
    @given(
        master_key=master_key_strategy,
        plaintext=plaintext_strategy,
    )
    def test_ciphertext_differs_from_plaintext(
        self,
        master_key: str,
        plaintext: str,
    ) -> None:
        """
        Property: Encrypted value is different from the original plaintext.

        This ensures the encryption is actually transforming the data.

        **Validates: Requirements 2.1**
        """
        manager = APIKeyManager(master_key=master_key, iterations=TEST_ITERATIONS)
        salt = manager.generate_salt()

        ciphertext = manager.encrypt(plaintext, salt)

        # Ciphertext should be different from plaintext
        # (Fernet adds authentication tag and IV, so this should always be true)
        assert ciphertext != plaintext, "Ciphertext should differ from plaintext"

    @settings(max_examples=10)
    @given(
        master_key=master_key_strategy,
        plaintext=plaintext_strategy,
    )
    def test_multiple_encryptions_produce_different_ciphertexts(
        self,
        master_key: str,
        plaintext: str,
    ) -> None:
        """
        Property: Encrypting the same plaintext twice produces different ciphertexts.

        Fernet uses a random IV for each encryption, so the same plaintext
        encrypted twice should produce different ciphertexts (semantic security).

        **Validates: Requirements 2.1**
        """
        manager = APIKeyManager(master_key=master_key, iterations=TEST_ITERATIONS)
        salt = manager.generate_salt()

        ciphertext1 = manager.encrypt(plaintext, salt)
        ciphertext2 = manager.encrypt(plaintext, salt)

        # Due to random IV, ciphertexts should differ
        assert ciphertext1 != ciphertext2, (
            "Same plaintext should produce different ciphertexts due to random IV"
        )

        # But both should decrypt to the same plaintext
        assert manager.decrypt(ciphertext1, salt) == plaintext
        assert manager.decrypt(ciphertext2, salt) == plaintext



class TestUniqueSalts:
    """
    Property 2: Unique Per-User Encryption Salts

    *For any* two distinct users, their API key salts SHALL be different,
    ensuring encryption keys are unique per user.

    **Validates: Requirements 2.2**
    """

    @settings(max_examples=10)
    @given(master_key=master_key_strategy)
    def test_generated_salts_are_unique(self, master_key: str) -> None:
        """
        Property: Multiple calls to generate_salt() produce unique values.

        **Validates: Requirements 2.2**
        """
        manager = APIKeyManager(master_key=master_key, iterations=TEST_ITERATIONS)

        # Generate multiple salts
        salts = [manager.generate_salt() for _ in range(10)]

        # All salts should be unique
        assert len(set(salts)) == len(salts), "Generated salts should be unique"

    @settings(max_examples=10)
    @given(master_key=master_key_strategy)
    def test_salt_has_correct_size(self, master_key: str) -> None:
        """
        Property: Generated salts have the correct size (16 bytes).

        **Validates: Requirements 2.2**
        """
        manager = APIKeyManager(master_key=master_key, iterations=TEST_ITERATIONS)
        salt = manager.generate_salt()

        assert len(salt) == APIKeyManager.SALT_SIZE, (
            f"Salt should be {APIKeyManager.SALT_SIZE} bytes, got {len(salt)}"
        )

    @settings(max_examples=10)
    @given(
        master_key=master_key_strategy,
        plaintext=plaintext_strategy,
    )
    def test_different_salts_produce_different_ciphertexts(
        self,
        master_key: str,
        plaintext: str,
    ) -> None:
        """
        Property: Same plaintext encrypted with different salts produces different ciphertexts.

        This ensures that per-user salts provide isolation.

        **Validates: Requirements 2.2**
        """
        manager = APIKeyManager(master_key=master_key, iterations=TEST_ITERATIONS)

        salt1 = manager.generate_salt()
        salt2 = manager.generate_salt()

        ciphertext1 = manager.encrypt(plaintext, salt1)
        ciphertext2 = manager.encrypt(plaintext, salt2)

        # Different salts should produce different ciphertexts
        assert ciphertext1 != ciphertext2, (
            "Same plaintext with different salts should produce different ciphertexts"
        )

    @settings(max_examples=10)
    @given(
        master_key=master_key_strategy,
        plaintext=plaintext_strategy,
    )
    def test_wrong_salt_cannot_decrypt(
        self,
        master_key: str,
        plaintext: str,
    ) -> None:
        """
        Property: Ciphertext encrypted with one salt cannot be decrypted with another.

        This ensures user data isolation through unique salts.

        **Validates: Requirements 2.2**
        """
        from lib.crypto.api_key_manager import APIKeyDecryptionError

        manager = APIKeyManager(master_key=master_key, iterations=TEST_ITERATIONS)

        salt1 = manager.generate_salt()
        salt2 = manager.generate_salt()

        ciphertext = manager.encrypt(plaintext, salt1)

        # Attempting to decrypt with wrong salt should fail
        try:
            manager.decrypt(ciphertext, salt2)
            raise AssertionError("Decryption with wrong salt should have failed")
        except APIKeyDecryptionError:
            pass  # Expected behavior



class TestAPIKeyValidation:
    """
    Property 3: API Key Format Validation

    *For any* string that does not match the Pionex API key format
    (alphanumeric, correct length), the API_Key_Manager SHALL reject it
    before encryption.

    **Validates: Requirements 2.7**
    """

    @settings(max_examples=10)
    @given(api_key=valid_api_key_strategy)
    def test_valid_api_keys_pass_validation(self, api_key: str) -> None:
        """
        Property: Valid API keys (alphanumeric, 16-128 chars) pass validation.

        **Validates: Requirements 2.7**
        """
        manager = APIKeyManager(master_key="test-key", iterations=TEST_ITERATIONS)
        assert manager.validate_api_key_format(api_key) is True

    @settings(max_examples=10)
    @given(
        short_key=st.text(
            alphabet=string.ascii_letters + string.digits,
            min_size=1,
            max_size=15,
        )
    )
    def test_short_keys_fail_validation(self, short_key: str) -> None:
        """
        Property: Keys shorter than 16 characters fail validation.

        **Validates: Requirements 2.7**
        """
        manager = APIKeyManager(master_key="test-key", iterations=TEST_ITERATIONS)
        assert manager.validate_api_key_format(short_key) is False

    @settings(max_examples=10)
    @given(
        long_key=st.text(
            alphabet=string.ascii_letters + string.digits,
            min_size=129,
            max_size=200,
        )
    )
    def test_long_keys_fail_validation(self, long_key: str) -> None:
        """
        Property: Keys longer than 128 characters fail validation.

        **Validates: Requirements 2.7**
        """
        manager = APIKeyManager(master_key="test-key", iterations=TEST_ITERATIONS)
        assert manager.validate_api_key_format(long_key) is False

    @settings(max_examples=10)
    @given(
        key_with_special=st.text(
            alphabet=string.ascii_letters + string.digits + "-_!@#$%",
            min_size=16,
            max_size=128,
        ).filter(lambda x: any(c in x for c in "-_!@#$%"))
    )
    def test_keys_with_special_chars_fail_validation(self, key_with_special: str) -> None:
        """
        Property: Keys containing special characters fail validation.

        **Validates: Requirements 2.7**
        """
        manager = APIKeyManager(master_key="test-key", iterations=TEST_ITERATIONS)
        assert manager.validate_api_key_format(key_with_special) is False

    def test_empty_key_fails_validation(self) -> None:
        """
        Property: Empty string fails validation.

        **Validates: Requirements 2.7**
        """
        manager = APIKeyManager(master_key="test-key", iterations=TEST_ITERATIONS)
        assert manager.validate_api_key_format("") is False

    def test_none_key_fails_validation(self) -> None:
        """
        Property: None value fails validation.

        **Validates: Requirements 2.7**
        """
        manager = APIKeyManager(master_key="test-key", iterations=TEST_ITERATIONS)
        # Type ignore since we're testing edge case
        assert manager.validate_api_key_format(None) is False  # type: ignore[arg-type]
