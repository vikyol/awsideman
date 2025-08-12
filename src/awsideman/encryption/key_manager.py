"""Key management system for encryption keys using OS keyring integration."""

import base64
import os
import secrets
from typing import Optional, Tuple

import keyring
from keyring.errors import KeyringError

from ..utils.security import get_secure_logger, secure_memory
from .provider import EncryptionError

# Use secure logger instead of standard logger
logger = get_secure_logger(__name__)


class KeyManager:
    """
    Key manager for handling encryption keys using OS keyring integration.

    Provides secure key generation, storage, and rotation using the operating
    system's keyring/keychain for secure key storage.
    """

    def __init__(self, service_name: str = "awsideman-cache", username: str = "encryption-key"):
        """
        Initialize key manager.

        Args:
            service_name: Service name for keyring storage
            username: Username for keyring storage
        """
        self.service_name = service_name
        self.username = username
        self._cached_key: Optional[bytes] = None
        self._key_cache_time: Optional[float] = None
        self._cache_ttl = 300  # Cache key for 5 minutes

    def get_key(self) -> bytes:
        """
        Get or generate encryption key with secure memory handling.

        Returns:
            32-byte AES-256 encryption key

        Raises:
            EncryptionError: If key retrieval or generation fails
        """
        try:
            # Check if we have a cached key that's still valid
            if self._is_key_cache_valid():
                # Lock cached key in memory for security
                secure_memory.lock_memory(self._cached_key)
                return self._cached_key

            # Try to retrieve key from keyring
            key_str = self._get_key_from_keyring()

            if key_str:
                # Decode existing key
                key = self._decode_key(key_str)
                self._cache_key(key)

                # Log security event
                logger.security_event(
                    "key_access",
                    {"operation": "retrieve_existing_key", "source": "keyring"},
                    "DEBUG",
                )

                return key
            else:
                # Generate new key if none exists
                key = self._generate_key()
                self._store_key(key)
                self._cache_key(key)

                # Log security event
                logger.security_event(
                    "key_generation",
                    {"operation": "generate_new_key", "key_length": len(key)},
                    "INFO",
                )

                logger.info("Generated new encryption key and stored in keyring")
                return key

        except EncryptionError:
            raise
        except Exception as e:
            logger.security_event(
                "key_error", {"operation": "get_key", "error_type": type(e).__name__}, "ERROR"
            )
            raise EncryptionError(
                f"Failed to get encryption key: {e}",
                encryption_type="key_management",
                original_error=e,
            )

    def rotate_key(self) -> Tuple[Optional[bytes], bytes]:
        """
        Generate new key and return both old and new keys for re-encryption.

        Returns:
            Tuple of (old_key, new_key) where old_key may be None if no previous key existed

        Raises:
            EncryptionError: If key rotation fails
        """
        try:
            # Get current key (if any)
            old_key = None
            try:
                old_key_str = self._get_key_from_keyring()
                if old_key_str:
                    old_key = self._decode_key(old_key_str)
            except Exception as e:
                logger.warning(f"Could not retrieve old key during rotation: {e}")

            # Generate new key
            new_key = self._generate_key()

            # Store new key
            self._store_key(new_key)

            # Update cache
            self._cache_key(new_key)

            logger.info("Successfully rotated encryption key")
            return old_key, new_key

        except EncryptionError:
            raise
        except Exception as e:
            raise EncryptionError(
                f"Failed to rotate encryption key: {e}",
                encryption_type="key_management",
                original_error=e,
            )

    def delete_key(self) -> bool:
        """
        Delete encryption key from keyring.

        Returns:
            True if key was deleted or didn't exist, False if deletion failed
        """
        try:
            keyring.delete_password(self.service_name, self.username)
            self._clear_key_cache()
            logger.info("Deleted encryption key from keyring")
            return True
        except KeyringError as e:
            if "not found" in str(e).lower():
                # Key didn't exist, which is fine
                self._clear_key_cache()
                return True
            else:
                logger.error(f"Failed to delete encryption key: {e}")
                return False
        except Exception as e:
            logger.error(f"Unexpected error deleting encryption key: {e}")
            return False

    def key_exists(self) -> bool:
        """
        Check if an encryption key exists in the keyring.

        Returns:
            True if key exists, False otherwise
        """
        try:
            key_str = self._get_key_from_keyring()
            return key_str is not None
        except Exception as e:
            logger.debug(f"Error checking if key exists: {e}")
            return False

    def is_keyring_available(self) -> bool:
        """
        Check if keyring is available and functional.

        Returns:
            True if keyring is available, False otherwise
        """
        try:
            # Try to perform a basic keyring operation
            test_service = f"{self.service_name}-test"
            test_username = "test"
            test_value = "test"

            # Try to set and get a test value
            keyring.set_password(test_service, test_username, test_value)
            retrieved = keyring.get_password(test_service, test_username)

            # Clean up test entry
            try:
                keyring.delete_password(test_service, test_username)
            except Exception:
                pass  # Ignore cleanup errors

            return retrieved == test_value

        except Exception as e:
            logger.debug(f"Keyring not available: {e}")
            return False

    def get_key_info(self) -> dict:
        """
        Get information about the current key.

        Returns:
            Dictionary with key information
        """
        try:
            key_exists = self.key_exists()
            keyring_available = self.is_keyring_available()

            info = {
                "key_exists": key_exists,
                "keyring_available": keyring_available,
                "service_name": self.service_name,
                "username": self.username,
                "cached": self._is_key_cache_valid(),
            }

            if key_exists:
                try:
                    key = self.get_key()
                    info["key_length"] = len(key)
                    info["key_valid"] = len(key) == 32  # AES-256 requires 32 bytes
                except Exception as e:
                    info["key_error"] = str(e)
                    info["key_valid"] = False

            return info

        except Exception as e:
            return {"error": str(e), "keyring_available": False, "key_exists": False}

    def _generate_key(self) -> bytes:
        """
        Generate a new AES-256 encryption key.

        Returns:
            32-byte cryptographically secure random key
        """
        return secrets.token_bytes(32)  # 256 bits = 32 bytes

    def _encode_key(self, key: bytes) -> str:
        """
        Encode key to base64 string for storage.

        Args:
            key: Key bytes to encode

        Returns:
            Base64 encoded key string
        """
        return base64.b64encode(key).decode("ascii")

    def _decode_key(self, key_str: str) -> bytes:
        """
        Decode base64 key string to bytes.

        Args:
            key_str: Base64 encoded key string

        Returns:
            Key bytes

        Raises:
            EncryptionError: If decoding fails
        """
        try:
            key = base64.b64decode(key_str.encode("ascii"))
            if len(key) != 32:
                raise EncryptionError(
                    f"Invalid key length: expected 32 bytes, got {len(key)}",
                    encryption_type="key_management",
                )
            return key
        except Exception as e:
            raise EncryptionError(
                f"Failed to decode encryption key: {e}",
                encryption_type="key_management",
                original_error=e,
            )

    def _get_key_from_keyring(self) -> Optional[str]:
        """
        Retrieve key from keyring.

        Returns:
            Base64 encoded key string or None if not found

        Raises:
            EncryptionError: If keyring access fails
        """
        try:
            return keyring.get_password(self.service_name, self.username)
        except KeyringError as e:
            if "not found" in str(e).lower():
                return None
            else:
                raise EncryptionError(
                    f"Failed to access keyring: {e}",
                    encryption_type="key_management",
                    original_error=e,
                )
        except Exception as e:
            raise EncryptionError(
                f"Unexpected error accessing keyring: {e}",
                encryption_type="key_management",
                original_error=e,
            )

    def _store_key(self, key: bytes) -> None:
        """
        Store key in keyring.

        Args:
            key: Key bytes to store

        Raises:
            EncryptionError: If keyring storage fails
        """
        try:
            key_str = self._encode_key(key)
            keyring.set_password(self.service_name, self.username, key_str)
        except KeyringError as e:
            raise EncryptionError(
                f"Failed to store key in keyring: {e}",
                encryption_type="key_management",
                original_error=e,
            )
        except Exception as e:
            raise EncryptionError(
                f"Unexpected error storing key in keyring: {e}",
                encryption_type="key_management",
                original_error=e,
            )

    def _cache_key(self, key: bytes) -> None:
        """
        Cache key in memory for performance with secure memory handling.

        Args:
            key: Key bytes to cache
        """
        import time

        # Clear any existing cached key securely
        if self._cached_key:
            self._clear_key_cache()

        # Cache new key and lock it in memory
        self._cached_key = key
        self._key_cache_time = time.time()
        secure_memory.lock_memory(key)

    def _clear_key_cache(self) -> None:
        """Clear cached key from memory securely."""
        if self._cached_key:
            # Create mutable copy for secure zeroing
            key_array = bytearray(self._cached_key)
            secure_memory.secure_zero(key_array)

        self._cached_key = None
        self._key_cache_time = None

    def _is_key_cache_valid(self) -> bool:
        """
        Check if cached key is still valid.

        Returns:
            True if cached key is valid, False otherwise
        """
        if not self._cached_key or not self._key_cache_time:
            return False

        import time

        return (time.time() - self._key_cache_time) < self._cache_ttl


class FallbackKeyManager(KeyManager):
    """
    Fallback key manager that uses file-based storage when keyring is unavailable.

    This is less secure than keyring storage but provides functionality when
    the OS keyring is not available or accessible.
    """

    def __init__(
        self,
        service_name: str = "awsideman-cache",
        username: str = "encryption-key",
        fallback_dir: Optional[str] = None,
    ):
        """
        Initialize fallback key manager.

        Args:
            service_name: Service name for keyring storage
            username: Username for keyring storage
            fallback_dir: Directory for fallback file storage (defaults to ~/.awsideman)
        """
        super().__init__(service_name, username)

        if fallback_dir:
            self.fallback_dir = fallback_dir
        else:
            from pathlib import Path

            self.fallback_dir = str(Path.home() / ".awsideman")

        self.fallback_file = os.path.join(self.fallback_dir, ".encryption_key")

    def get_key(self) -> bytes:
        """
        Get or generate encryption key, using file fallback if keyring unavailable.

        Returns:
            32-byte AES-256 encryption key

        Raises:
            EncryptionError: If key retrieval or generation fails
        """
        try:
            # Try keyring first
            if self.is_keyring_available():
                return super().get_key()
            else:
                logger.warning("Keyring not available, using file-based key storage (less secure)")
                return self._get_key_from_file()
        except Exception as e:
            raise EncryptionError(
                f"Failed to get encryption key with fallback: {e}",
                encryption_type="key_management",
                original_error=e,
            )

    def _get_key_from_file(self) -> bytes:
        """
        Get key from fallback file storage.

        Returns:
            32-byte encryption key

        Raises:
            EncryptionError: If file access fails
        """
        try:
            # Check if we have a cached key that's still valid
            if self._is_key_cache_valid():
                return self._cached_key

            # Try to read existing key file
            if os.path.exists(self.fallback_file):
                with open(self.fallback_file, "r") as f:
                    key_str = f.read().strip()
                key = self._decode_key(key_str)
                self._cache_key(key)
                return key
            else:
                # Generate new key
                key = self._generate_key()
                self._store_key_to_file(key)
                self._cache_key(key)
                logger.info("Generated new encryption key and stored in fallback file")
                return key

        except Exception as e:
            raise EncryptionError(
                f"Failed to get key from fallback file: {e}",
                encryption_type="key_management",
                original_error=e,
            )

    def rotate_key(self) -> Tuple[Optional[bytes], bytes]:
        """
        Generate new key and return both old and new keys for re-encryption.

        Returns:
            Tuple of (old_key, new_key) where old_key may be None if no previous key existed

        Raises:
            EncryptionError: If key rotation fails
        """
        try:
            # Try keyring first
            if self.is_keyring_available():
                return super().rotate_key()
            else:
                logger.warning("Keyring not available, using file-based key rotation (less secure)")
                return self._rotate_key_in_file()
        except Exception as e:
            raise EncryptionError(
                f"Failed to rotate encryption key with fallback: {e}",
                encryption_type="key_management",
                original_error=e,
            )

    def _rotate_key_in_file(self) -> Tuple[Optional[bytes], bytes]:
        """
        Rotate key using file storage.

        Returns:
            Tuple of (old_key, new_key)

        Raises:
            EncryptionError: If file rotation fails
        """
        try:
            # Get current key (if any)
            old_key = None
            try:
                if os.path.exists(self.fallback_file):
                    with open(self.fallback_file, "r") as f:
                        key_str = f.read().strip()
                    old_key = self._decode_key(key_str)
            except Exception as e:
                logger.warning(f"Could not retrieve old key during rotation: {e}")

            # Generate new key
            new_key = self._generate_key()

            # Store new key
            self._store_key_to_file(new_key)

            # Update cache
            self._cache_key(new_key)

            logger.info("Successfully rotated encryption key using file storage")
            return old_key, new_key

        except Exception as e:
            raise EncryptionError(
                f"Failed to rotate key in fallback file: {e}",
                encryption_type="key_management",
                original_error=e,
            )

    def _store_key_to_file(self, key: bytes) -> None:
        """
        Store key to fallback file.

        Args:
            key: Key bytes to store

        Raises:
            EncryptionError: If file storage fails
        """
        try:
            # Ensure directory exists
            os.makedirs(self.fallback_dir, mode=0o700, exist_ok=True)

            # Write key to file with restricted permissions
            key_str = self._encode_key(key)
            with open(self.fallback_file, "w") as f:
                f.write(key_str)

            # Set restrictive file permissions (owner read/write only)
            os.chmod(self.fallback_file, 0o600)

        except Exception as e:
            raise EncryptionError(
                f"Failed to store key to fallback file: {e}",
                encryption_type="key_management",
                original_error=e,
            )
