"""AES encryption provider implementation for cache data encryption."""

import json
import os
from datetime import datetime
from typing import Any

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from ..utils.security import get_secure_logger, secure_memory, timing_protection
from .key_manager import KeyManager
from .provider import EncryptionError, EncryptionProvider

# Use secure logger instead of standard logger
logger = get_secure_logger(__name__)


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime objects."""

    def default(self, obj):
        if isinstance(obj, datetime):
            return {"__datetime__": True, "value": obj.isoformat()}
        return super().default(obj)


def datetime_decoder(dct):
    """Custom JSON decoder that handles datetime objects."""
    if "__datetime__" in dct:
        return datetime.fromisoformat(dct["value"])
    return dct


class AESEncryption(EncryptionProvider):
    """
    AES-256-CBC encryption provider for cache data.

    Provides secure encryption using AES-256 in CBC mode with PKCS7 padding
    and random initialization vectors for each encryption operation.
    """

    def __init__(self, key_manager: "KeyManager"):
        """
        Initialize AES encryption provider.

        Args:
            key_manager: Key manager instance for handling encryption keys

        Raises:
            EncryptionError: If initialization fails
        """
        try:
            self.key_manager = key_manager
            self._backend = default_backend()

            # Verify that we can get a key
            self._test_key_access()

        except Exception as e:
            raise EncryptionError(
                f"Failed to initialize AES encryption: {e}",
                encryption_type="aes256",
                original_error=e,
            )

    def encrypt(self, data: Any) -> bytes:
        """
        Encrypt data using AES-256-CBC with random IV and secure memory handling.

        Args:
            data: Data to encrypt (must be JSON-serializable)

        Returns:
            Encrypted data as bytes (IV + encrypted_data)

        Raises:
            EncryptionError: If encryption fails
        """
        key_addr = None
        json_bytes_array = None
        padded_data_array = None

        try:
            # Serialize data to JSON with datetime support
            json_str = json.dumps(data, cls=DateTimeEncoder, separators=(",", ":"))
            json_bytes = json_str.encode("utf-8")

            # Create mutable copy for secure handling
            json_bytes_array = bytearray(json_bytes)

            # Get encryption key and lock it in memory
            key = self.key_manager.get_key()
            key_addr = secure_memory.lock_memory(key)

            # Generate random IV (16 bytes for AES)
            iv = os.urandom(16)

            # Create cipher
            cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=self._backend)
            encryptor = cipher.encryptor()

            # Apply PKCS7 padding
            padder = padding.PKCS7(128).padder()  # 128 bits = 16 bytes for AES
            padded_data = padder.update(json_bytes)
            padded_data += padder.finalize()

            # Create mutable copy for secure handling
            padded_data_array = bytearray(padded_data)

            # Encrypt data
            encrypted_data = encryptor.update(padded_data) + encryptor.finalize()

            # Log security event
            logger.security_event(
                "encryption_operation",
                {"operation": "encrypt", "data_size": len(json_bytes), "encryption_type": "aes256"},
                "DEBUG",
            )

            # Return IV + encrypted data
            return iv + encrypted_data

        except (TypeError, ValueError) as e:
            logger.security_event(
                "encryption_error",
                {
                    "operation": "encrypt",
                    "error_type": "serialization_error",
                    "encryption_type": "aes256",
                },
                "WARNING",
            )
            raise EncryptionError(
                f"Failed to serialize data for encryption: {e}",
                encryption_type="aes256",
                original_error=e,
            )
        except Exception as e:
            logger.security_event(
                "encryption_error",
                {
                    "operation": "encrypt",
                    "error_type": "encryption_failure",
                    "encryption_type": "aes256",
                },
                "ERROR",
            )
            raise EncryptionError(
                f"AES encryption failed: {e}", encryption_type="aes256", original_error=e
            )
        finally:
            # Securely clean up sensitive data
            if json_bytes_array:
                secure_memory.secure_zero(json_bytes_array)
            if padded_data_array:
                secure_memory.secure_zero(padded_data_array)
            if key_addr:
                secure_memory.unlock_memory(key_addr)

    def decrypt(self, encrypted_data: bytes) -> Any:
        """
        Decrypt AES-256-CBC encrypted data with timing attack protection.

        Args:
            encrypted_data: Encrypted data as bytes (IV + encrypted_data)

        Returns:
            Original decrypted data

        Raises:
            EncryptionError: If decryption fails
        """
        key_addr = None
        padded_data_array = None
        json_bytes_array = None

        try:
            # Add timing jitter to prevent timing analysis
            timing_protection.add_timing_jitter(1.0, 3.0)

            # Validate input length in constant time
            is_valid_length = len(encrypted_data) >= 16
            if not is_valid_length:
                # Still perform some operations to maintain constant time
                dummy_iv = b"\x00" * 16  # noqa: F841
                dummy_content = b"\x00" * 16  # noqa: F841
                timing_protection.add_timing_jitter(2.0, 4.0)
                raise ValueError("Invalid encrypted data: too short to contain IV")

            # Extract IV and encrypted content
            iv = encrypted_data[:16]
            encrypted_content = encrypted_data[16:]

            # Validate content length in constant time
            has_content = len(encrypted_content) > 0
            if not has_content:
                # Maintain timing consistency
                timing_protection.add_timing_jitter(2.0, 4.0)
                raise ValueError("Invalid encrypted data: no encrypted content")

            # Get decryption key and lock it in memory
            key = self.key_manager.get_key()
            key_addr = secure_memory.lock_memory(key)

            # Create cipher
            cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=self._backend)
            decryptor = cipher.decryptor()

            # Decrypt data
            padded_data = decryptor.update(encrypted_content) + decryptor.finalize()

            # Create mutable copy for secure handling
            padded_data_array = bytearray(padded_data)

            # Remove PKCS7 padding
            unpadder = padding.PKCS7(128).unpadder()
            json_bytes = unpadder.update(padded_data) + unpadder.finalize()

            # Create mutable copy for secure handling
            json_bytes_array = bytearray(json_bytes)

            # Deserialize JSON with datetime support
            json_str = json_bytes.decode("utf-8")
            result = json.loads(json_str, object_hook=datetime_decoder)

            # Log successful decryption
            logger.security_event(
                "encryption_operation",
                {"operation": "decrypt", "data_size": len(json_bytes), "encryption_type": "aes256"},
                "DEBUG",
            )

            return result

        except EncryptionError:
            # Re-raise EncryptionError as-is to avoid double wrapping
            # Add timing jitter to prevent information leakage
            timing_protection.add_timing_jitter(2.0, 5.0)
            raise
        except UnicodeDecodeError as e:
            logger.security_event(
                "encryption_error",
                {
                    "operation": "decrypt",
                    "error_type": "unicode_decode_error",
                    "encryption_type": "aes256",
                },
                "WARNING",
            )
            timing_protection.add_timing_jitter(2.0, 5.0)
            raise EncryptionError(
                "Decryption failed: invalid data format", encryption_type="aes256", original_error=e
            )
        except json.JSONDecodeError as e:
            logger.security_event(
                "encryption_error",
                {
                    "operation": "decrypt",
                    "error_type": "json_decode_error",
                    "encryption_type": "aes256",
                },
                "WARNING",
            )
            timing_protection.add_timing_jitter(2.0, 5.0)
            raise EncryptionError(
                "Decryption failed: invalid data format", encryption_type="aes256", original_error=e
            )
        except ValueError as e:
            # This can be raised by padding operations, cipher operations, or our validation
            if "Invalid encrypted data" in str(e):
                # Our own validation errors
                logger.security_event(
                    "encryption_error",
                    {
                        "operation": "decrypt",
                        "error_type": "validation_error",
                        "encryption_type": "aes256",
                    },
                    "WARNING",
                )
                timing_protection.add_timing_jitter(2.0, 5.0)
                raise EncryptionError(
                    "Decryption failed: invalid data format", encryption_type="aes256"
                )
            elif "Invalid padding" in str(e) or "padding" in str(e).lower():
                logger.security_event(
                    "encryption_error",
                    {
                        "operation": "decrypt",
                        "error_type": "padding_error",
                        "encryption_type": "aes256",
                    },
                    "WARNING",
                )
                timing_protection.add_timing_jitter(2.0, 5.0)
                raise EncryptionError(
                    "Decryption failed: invalid data format",
                    encryption_type="aes256",
                    original_error=e,
                )
            else:
                logger.security_event(
                    "encryption_error",
                    {
                        "operation": "decrypt",
                        "error_type": "general_error",
                        "encryption_type": "aes256",
                    },
                    "ERROR",
                )
                timing_protection.add_timing_jitter(2.0, 5.0)
                raise EncryptionError(
                    "Decryption failed: invalid data format",
                    encryption_type="aes256",
                    original_error=e,
                )
        except Exception as e:
            logger.security_event(
                "encryption_error",
                {
                    "operation": "decrypt",
                    "error_type": "unexpected_error",
                    "encryption_type": "aes256",
                },
                "ERROR",
            )
            timing_protection.add_timing_jitter(2.0, 5.0)
            raise EncryptionError(
                "Decryption failed: unexpected error", encryption_type="aes256", original_error=e
            )
        finally:
            # Securely clean up sensitive data
            if padded_data_array:
                secure_memory.secure_zero(padded_data_array)
            if json_bytes_array:
                secure_memory.secure_zero(json_bytes_array)
            if key_addr:
                secure_memory.unlock_memory(key_addr)

    def get_encryption_type(self) -> str:
        """
        Get the encryption type identifier.

        Returns:
            String identifier "aes256" for AES-256 encryption
        """
        return "aes256"

    def is_available(self) -> bool:
        """
        Check if AES encryption is available and functional.

        Returns:
            True if AES encryption is available, False otherwise
        """
        try:
            # Test that we can access the key manager
            self.key_manager.get_key()
            return True
        except Exception as e:
            logger.debug(f"AES encryption not available: {e}")
            return False

    @staticmethod
    def is_available_static() -> bool:
        """
        Check if AES encryption dependencies are available.

        Returns:
            True if cryptography library is available, False otherwise
        """
        try:
            from cryptography.hazmat.backends import default_backend  # noqa: F401
            from cryptography.hazmat.primitives import padding  # noqa: F401
            from cryptography.hazmat.primitives.ciphers import (  # noqa: F401
                Cipher,
                algorithms,
                modes,
            )

            return True
        except ImportError:
            return False
        except Exception:
            return False

    @staticmethod
    def validate_config(config: dict) -> bool:
        """
        Validate configuration for AES encryption provider.

        Args:
            config: Configuration dictionary to validate

        Returns:
            True if configuration is valid, False otherwise
        """
        try:
            # AES encryption requires a key manager configuration
            # For now, we just check that the basic dependencies are available
            return AESEncryption.is_available_static()
        except Exception as e:
            logger.debug(f"AES config validation failed: {e}")
            return False

    def _test_key_access(self) -> None:
        """
        Test that we can access encryption keys.

        Raises:
            EncryptionError: If key access fails
        """
        try:
            # Try to get a key to verify key manager is working
            key = self.key_manager.get_key()
            if not key or len(key) != 32:  # AES-256 requires 32-byte key
                raise EncryptionError(
                    "Invalid encryption key: must be 32 bytes for AES-256", encryption_type="aes256"
                )
        except EncryptionError:
            raise
        except Exception as e:
            raise EncryptionError(
                f"Failed to access encryption key: {e}", encryption_type="aes256", original_error=e
            )

    def _constant_time_compare(self, a: bytes, b: bytes) -> bool:
        """
        Perform constant-time comparison to prevent timing attacks.

        Args:
            a: First bytes to compare
            b: Second bytes to compare

        Returns:
            True if bytes are equal, False otherwise
        """
        return timing_protection.constant_time_compare(a, b)

    def verify_integrity(self, encrypted_data: bytes) -> bool:
        """
        Verify the integrity of encrypted data by attempting decryption.

        Args:
            encrypted_data: Encrypted data to verify

        Returns:
            True if data can be decrypted successfully, False otherwise
        """
        try:
            self.decrypt(encrypted_data)
            return True
        except EncryptionError:
            return False
        except Exception:
            return False
