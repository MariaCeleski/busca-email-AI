"""AES-256-GCM encryption service for OAuth token storage.

Provides symmetric encryption/decryption of sensitive tokens at rest
using AES-256 in GCM mode (authenticated encryption with associated data).

The encryption key is loaded from the ENCRYPTION_KEY environment variable
(base64-encoded 32 bytes) via the application settings.
"""

import base64
import os
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.config import get_settings


class TokenEncryptionService:
    """AES-256-GCM encryption for OAuth tokens at rest.

    Uses a 256-bit key from the application config (base64-encoded).
    Each encryption operation generates a unique 12-byte nonce prepended
    to the ciphertext for later use during decryption.
    """

    # GCM standard nonce size (96 bits)
    _NONCE_SIZE = 12

    def __init__(self, key: Optional[str] = None) -> None:
        """Initialize with an AES-256 key.

        Args:
            key: Base64-encoded 32-byte key. If not provided,
                 reads from application settings (ENCRYPTION_KEY).

        Raises:
            ValueError: If the key is missing or not exactly 32 bytes.
        """
        raw_key = key if key is not None else get_settings().encryption_key
        if not raw_key:
            raise ValueError(
                "Encryption key is required. Set the ENCRYPTION_KEY environment variable."
            )
        try:
            self._key = base64.b64decode(raw_key)
        except Exception as exc:
            raise ValueError(f"Invalid base64 encryption key: {exc}") from exc

        if len(self._key) != 32:
            raise ValueError(
                f"Encryption key must be exactly 32 bytes (got {len(self._key)}). "
                "Generate with: python -c \"import base64, os; print(base64.b64encode(os.urandom(32)).decode())\""
            )
        self._aesgcm = AESGCM(self._key)

    def encrypt(self, plaintext: str) -> bytes:
        """Encrypt a plaintext string using AES-256-GCM.

        A random 12-byte nonce is generated per call and prepended to the
        ciphertext. The output format is: nonce (12 bytes) || ciphertext+tag.

        Args:
            plaintext: The string value to encrypt (e.g., an OAuth token).

        Returns:
            Encrypted bytes (nonce + ciphertext + GCM auth tag).

        Raises:
            ValueError: If plaintext is empty.
        """
        if not plaintext:
            raise ValueError("Cannot encrypt empty plaintext.")

        nonce = os.urandom(self._NONCE_SIZE)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return nonce + ciphertext

    def decrypt(self, ciphertext: bytes) -> str:
        """Decrypt AES-256-GCM encrypted bytes back to plaintext.

        Expects the input format: nonce (12 bytes) || ciphertext+tag.

        Args:
            ciphertext: The encrypted bytes produced by encrypt().

        Returns:
            The original plaintext string.

        Raises:
            ValueError: If ciphertext is too short or corrupted.
            cryptography.exceptions.InvalidTag: If authentication fails
                (tampered data or wrong key).
        """
        if len(ciphertext) <= self._NONCE_SIZE:
            raise ValueError(
                "Ciphertext is too short to contain a valid nonce and payload."
            )

        nonce = ciphertext[: self._NONCE_SIZE]
        encrypted_data = ciphertext[self._NONCE_SIZE :]
        plaintext_bytes = self._aesgcm.decrypt(nonce, encrypted_data, None)
        return plaintext_bytes.decode("utf-8")
