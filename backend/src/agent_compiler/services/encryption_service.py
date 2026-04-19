"""Encryption service for secrets management.

Uses Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256).
Master key is loaded from FORGE_MASTER_KEY environment variable.

Security Notes:
- Master key should be 32 bytes, base64-encoded (Fernet key format)
- In production, use a secrets manager (AWS Secrets Manager, Vault, etc.)
- Never log or expose the master key or decrypted secrets

Rotation-Ready Design (v2):
- Support multiple key versions for gradual rotation
- Re-encryption job to migrate secrets to new key
- Key version tracking in Credential model
"""

import base64
import hashlib
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from agent_compiler.observability.logging import get_logger

logger = get_logger(__name__)

# Environment variable for master key
MASTER_KEY_ENV = "FORGE_MASTER_KEY"


class EncryptionError(Exception):
    """Raised when encryption/decryption fails."""

    pass


class MasterKeyNotConfiguredError(Exception):
    """Raised when master key is not configured."""

    pass


def _derive_fernet_key(master_key: str) -> bytes:
    """Derive a valid Fernet key from the master key.

    Fernet requires a 32-byte base64-encoded key.
    We use SHA256 to derive a consistent key from any input.
    """
    # Hash the master key to get consistent 32 bytes
    key_bytes = hashlib.sha256(master_key.encode()).digest()
    # Base64 encode for Fernet
    return base64.urlsafe_b64encode(key_bytes)


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    """Get or create the Fernet instance (cached).

    Returns:
        Fernet instance for encryption/decryption

    Raises:
        MasterKeyNotConfiguredError: If FORGE_MASTER_KEY is not set
    """
    master_key = os.environ.get(MASTER_KEY_ENV)

    if not master_key:
        raise MasterKeyNotConfiguredError(
            f"{MASTER_KEY_ENV} environment variable is not set. "
            "This is required for credential encryption. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )

    try:
        # Try to use the key directly if it's already a valid Fernet key
        try:
            return Fernet(master_key.encode())
        except (ValueError, Exception):
            # Otherwise, derive a key from it
            derived_key = _derive_fernet_key(master_key)
            return Fernet(derived_key)
    except Exception as e:
        logger.error(f"Failed to initialize encryption: {type(e).__name__}")
        raise EncryptionError("Failed to initialize encryption service") from e


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret using Fernet.

    Args:
        plaintext: The secret to encrypt (e.g., API key)

    Returns:
        Base64-encoded ciphertext

    Raises:
        EncryptionError: If encryption fails
        MasterKeyNotConfiguredError: If master key not set
    """
    if not plaintext:
        raise EncryptionError("Cannot encrypt empty secret")

    try:
        fernet = _get_fernet()
        ciphertext = fernet.encrypt(plaintext.encode())
        return ciphertext.decode()
    except MasterKeyNotConfiguredError:
        raise
    except Exception as e:
        logger.error(f"Encryption failed: {type(e).__name__}")
        raise EncryptionError("Failed to encrypt secret") from e


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt a secret using Fernet.

    Args:
        ciphertext: Base64-encoded ciphertext

    Returns:
        Decrypted plaintext

    Raises:
        EncryptionError: If decryption fails (invalid key or corrupted data)
        MasterKeyNotConfiguredError: If master key not set
    """
    if not ciphertext:
        raise EncryptionError("Cannot decrypt empty ciphertext")

    try:
        fernet = _get_fernet()
        plaintext = fernet.decrypt(ciphertext.encode())
        return plaintext.decode()
    except MasterKeyNotConfiguredError:
        raise
    except InvalidToken:
        logger.error("Decryption failed: invalid token (wrong key or corrupted data)")
        raise EncryptionError(
            "Failed to decrypt secret. This may indicate a master key mismatch or corrupted data."
        )
    except Exception as e:
        logger.error(f"Decryption failed: {type(e).__name__}")
        raise EncryptionError("Failed to decrypt secret") from e


def is_encryption_configured() -> bool:
    """Check if encryption is properly configured.

    Returns:
        True if FORGE_MASTER_KEY is set and valid
    """
    try:
        _get_fernet()
        return True
    except (MasterKeyNotConfiguredError, EncryptionError):
        return False


def mask_secret(secret: str, visible_chars: int = 4) -> str:
    """Mask a secret for safe logging/display.

    Args:
        secret: The secret to mask
        visible_chars: Number of characters to show at the end

    Returns:
        Masked string like "****abc1"
    """
    if not secret:
        return "****"
    if len(secret) <= visible_chars:
        return "*" * len(secret)
    return "*" * (len(secret) - visible_chars) + secret[-visible_chars:]


def clear_encryption_cache() -> None:
    """Clear the cached Fernet instance.

    Call this if the master key changes (e.g., during testing).
    """
    _get_fernet.cache_clear()
