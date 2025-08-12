"""Encryption provider interface and implementations for cache data encryption."""

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

logger = logging.getLogger(__name__)


class EncryptionProvider(ABC):
    """
    Abstract base class for encryption providers.

    Defines the standard interface that all encryption providers must implement
    to provide pluggable encryption options for the cache system.
    """

    @abstractmethod
    def encrypt(self, data: Any) -> bytes:
        """
        Encrypt data and return bytes.

        Args:
            data: Data to encrypt (must be JSON-serializable)

        Returns:
            Encrypted data as bytes

        Raises:
            EncryptionError: If encryption fails
        """
        pass

    @abstractmethod
    def decrypt(self, encrypted_data: bytes) -> Any:
        """
        Decrypt bytes and return original data.

        Args:
            encrypted_data: Encrypted data as bytes

        Returns:
            Original decrypted data

        Raises:
            EncryptionError: If decryption fails
        """
        pass

    @abstractmethod
    def get_encryption_type(self) -> str:
        """
        Get the encryption type identifier.

        Returns:
            String identifier for the encryption type
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if the encryption provider is available and functional.

        Returns:
            True if the provider is available, False otherwise
        """
        pass


class EncryptionError(Exception):
    """
    Exception raised when encryption/decryption operations fail.

    This exception provides a consistent error interface across
    different encryption provider implementations.
    """

    def __init__(
        self,
        message: str,
        encryption_type: str = "unknown",
        original_error: Optional[Exception] = None,
    ):
        """
        Initialize encryption error.

        Args:
            message: Error message
            encryption_type: Type of encryption that failed
            original_error: Original exception that caused this error
        """
        super().__init__(message)
        self.encryption_type = encryption_type
        self.original_error = original_error

        # Log the error for debugging
        if original_error:
            logger.error(
                f"Encryption error in {encryption_type}: {message} (caused by: {original_error})"
            )
        else:
            logger.error(f"Encryption error in {encryption_type}: {message}")

    def __str__(self) -> str:
        """Return string representation of the error."""
        base_msg = super().__str__()
        if self.original_error:
            return f"{base_msg} (caused by: {self.original_error})"
        return base_msg


class NoEncryption(EncryptionProvider):
    """
    No-encryption provider for backward compatibility.

    This provider performs no actual encryption, just serializes/deserializes
    data to/from JSON bytes. Used as the default provider when encryption
    is disabled.
    """

    def encrypt(self, data: Any) -> bytes:
        """
        Serialize data to JSON bytes without encryption.

        Args:
            data: Data to serialize (must be JSON-serializable)

        Returns:
            JSON-serialized data as bytes

        Raises:
            EncryptionError: If serialization fails
        """
        try:
            # Serialize data to JSON string, then encode to bytes
            json_str = json.dumps(data, separators=(",", ":"))
            return json_str.encode("utf-8")

        except (TypeError, ValueError) as e:
            raise EncryptionError(
                f"Failed to serialize data to JSON: {e}", encryption_type="none", original_error=e
            )
        except Exception as e:
            raise EncryptionError(
                f"Unexpected error during data serialization: {e}",
                encryption_type="none",
                original_error=e,
            )

    def decrypt(self, encrypted_data: bytes) -> Any:
        """
        Deserialize JSON bytes to original data without decryption.

        Args:
            encrypted_data: JSON-serialized data as bytes

        Returns:
            Original deserialized data

        Raises:
            EncryptionError: If deserialization fails
        """
        try:
            # Decode bytes to JSON string, then deserialize
            json_str = encrypted_data.decode("utf-8")
            return json.loads(json_str)

        except UnicodeDecodeError as e:
            raise EncryptionError(
                f"Failed to decode bytes to UTF-8: {e}", encryption_type="none", original_error=e
            )
        except json.JSONDecodeError as e:
            raise EncryptionError(
                f"Failed to deserialize JSON data: {e}", encryption_type="none", original_error=e
            )
        except Exception as e:
            raise EncryptionError(
                f"Unexpected error during data deserialization: {e}",
                encryption_type="none",
                original_error=e,
            )

    def get_encryption_type(self) -> str:
        """
        Get the encryption type identifier.

        Returns:
            String identifier "none" for no encryption
        """
        return "none"

    def is_available(self) -> bool:
        """
        Check if the no-encryption provider is available.

        Returns:
            Always True since no-encryption is always available
        """
        return True


class EncryptionProviderFactory:
    """
    Factory class for creating encryption provider instances.

    Provides a centralized way to create and configure encryption providers
    based on configuration settings.
    """

    @staticmethod
    def create_provider(encryption_type: str = "none", **kwargs) -> EncryptionProvider:
        """
        Create an encryption provider instance.

        Args:
            encryption_type: Type of encryption provider to create
            **kwargs: Additional configuration parameters for the provider

        Returns:
            Configured encryption provider instance

        Raises:
            EncryptionError: If the provider type is unknown or creation fails
        """
        try:
            if encryption_type == "none":
                return NoEncryption()
            elif encryption_type == "aes256":
                # Import here to avoid circular imports and optional dependencies
                try:
                    from .aes import AESEncryption
                    from .key_manager import KeyManager

                    # Create key manager if not provided
                    if "key_manager" not in kwargs:
                        kwargs["key_manager"] = KeyManager()

                    return AESEncryption(**kwargs)
                except ImportError as e:
                    raise EncryptionError(
                        f"AES encryption not available: {e}",
                        encryption_type=encryption_type,
                        original_error=e,
                    )
            else:
                raise EncryptionError(
                    f"Unknown encryption type: {encryption_type}", encryption_type=encryption_type
                )

        except EncryptionError:
            # Re-raise EncryptionError as-is to avoid double wrapping
            raise
        except ImportError as e:
            raise EncryptionError(
                f"Failed to import encryption provider for type {encryption_type}: {e}",
                encryption_type=encryption_type,
                original_error=e,
            )
        except Exception as e:
            raise EncryptionError(
                f"Failed to create encryption provider for type {encryption_type}: {e}",
                encryption_type=encryption_type,
                original_error=e,
            )

    @staticmethod
    def get_available_providers() -> list[str]:
        """
        Get list of available encryption provider types.

        Returns:
            List of available encryption provider type identifiers
        """
        available = ["none"]

        # Check if AES encryption is available
        try:
            from .aes import AESEncryption

            if AESEncryption.is_available_static():
                available.append("aes256")
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"AES encryption not available: {e}")

        return available

    @staticmethod
    def validate_provider_config(encryption_type: str, config: dict) -> bool:
        """
        Validate configuration for a specific encryption provider type.

        Args:
            encryption_type: Type of encryption provider
            config: Configuration dictionary to validate

        Returns:
            True if configuration is valid, False otherwise
        """
        try:
            if encryption_type == "none":
                # No configuration needed for no-encryption
                return True
            elif encryption_type == "aes256":
                # Import here to avoid circular imports
                try:
                    from .aes import AESEncryption

                    return AESEncryption.validate_config(config)
                except ImportError:
                    logger.warning(
                        f"Cannot validate config for {encryption_type}: provider not available"
                    )
                    return False
            else:
                logger.warning(f"Unknown encryption type for validation: {encryption_type}")
                return False

        except ImportError:
            logger.warning(f"Cannot validate config for {encryption_type}: provider not available")
            return False
        except Exception as e:
            logger.error(f"Error validating config for {encryption_type}: {e}")
            return False
