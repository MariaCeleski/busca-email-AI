"""Unit tests for the TokenEncryptionService."""

import base64
import os

import pytest
from cryptography.exceptions import InvalidTag

from src.security.encryption import TokenEncryptionService


def _generate_valid_key() -> str:
    """Generate a valid base64-encoded 32-byte key for testing."""
    return base64.b64encode(os.urandom(32)).decode()


class TestTokenEncryptionService:
    """Tests for TokenEncryptionService encrypt/decrypt round-trip."""

    def test_encrypt_decrypt_round_trip(self) -> None:
        """Encrypting then decrypting should return the original value."""
        key = _generate_valid_key()
        service = TokenEncryptionService(key=key)

        original = "ya29.a0AfH6SMB_some_oauth_token_value"
        encrypted = service.encrypt(original)
        decrypted = service.decrypt(encrypted)

        assert decrypted == original

    def test_encrypt_produces_different_ciphertext_each_time(self) -> None:
        """Each encryption should use a unique nonce, producing unique output."""
        key = _generate_valid_key()
        service = TokenEncryptionService(key=key)

        plaintext = "refresh_token_abc123"
        ct1 = service.encrypt(plaintext)
        ct2 = service.encrypt(plaintext)

        assert ct1 != ct2  # Different nonces -> different ciphertext

    def test_decrypt_with_wrong_key_raises(self) -> None:
        """Decrypting with a different key should raise InvalidTag."""
        key1 = _generate_valid_key()
        key2 = _generate_valid_key()
        service1 = TokenEncryptionService(key=key1)
        service2 = TokenEncryptionService(key=key2)

        encrypted = service1.encrypt("secret_token")

        with pytest.raises(InvalidTag):
            service2.decrypt(encrypted)

    def test_decrypt_tampered_ciphertext_raises(self) -> None:
        """Modifying ciphertext should cause authentication failure."""
        key = _generate_valid_key()
        service = TokenEncryptionService(key=key)

        encrypted = service.encrypt("my_token")
        # Flip a byte in the ciphertext portion (after nonce)
        tampered = bytearray(encrypted)
        tampered[15] ^= 0xFF
        tampered = bytes(tampered)

        with pytest.raises(InvalidTag):
            service.decrypt(tampered)

    def test_encrypt_empty_string_raises(self) -> None:
        """Encrypting an empty string should raise ValueError."""
        key = _generate_valid_key()
        service = TokenEncryptionService(key=key)

        with pytest.raises(ValueError, match="Cannot encrypt empty plaintext"):
            service.encrypt("")

    def test_decrypt_too_short_ciphertext_raises(self) -> None:
        """Decrypting data shorter than nonce size should raise ValueError."""
        key = _generate_valid_key()
        service = TokenEncryptionService(key=key)

        with pytest.raises(ValueError, match="too short"):
            service.decrypt(b"short")

    def test_invalid_key_length_raises(self) -> None:
        """A key that isn't 32 bytes should raise ValueError."""
        short_key = base64.b64encode(b"too-short").decode()

        with pytest.raises(ValueError, match="must be exactly 32 bytes"):
            TokenEncryptionService(key=short_key)

    def test_missing_key_raises(self) -> None:
        """An empty key string should raise ValueError."""
        with pytest.raises(ValueError, match="Encryption key is required"):
            TokenEncryptionService(key="")

    def test_invalid_base64_key_raises(self) -> None:
        """A non-base64 string should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid base64"):
            TokenEncryptionService(key="not!valid!base64!@#$%")

    def test_encrypt_unicode_content(self) -> None:
        """Should handle unicode content correctly."""
        key = _generate_valid_key()
        service = TokenEncryptionService(key=key)

        original = "token_with_émojis_🔐_and_ñ"
        encrypted = service.encrypt(original)
        decrypted = service.decrypt(encrypted)

        assert decrypted == original

    def test_encrypt_long_token(self) -> None:
        """Should handle long token values."""
        key = _generate_valid_key()
        service = TokenEncryptionService(key=key)

        original = "A" * 4096  # Long token
        encrypted = service.encrypt(original)
        decrypted = service.decrypt(encrypted)

        assert decrypted == original

    def test_ciphertext_starts_with_nonce(self) -> None:
        """Ciphertext should be at least nonce_size + 1 bytes."""
        key = _generate_valid_key()
        service = TokenEncryptionService(key=key)

        encrypted = service.encrypt("test")
        # AES-GCM: nonce (12) + ciphertext (>=1) + tag (16) = minimum 29 bytes
        assert len(encrypted) >= 12 + 1 + 16
