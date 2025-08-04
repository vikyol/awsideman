"""AES encryption provider implementation for cache data encryption."""

import json
import logging
import os
import time
from typing import Any, Optional

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend

from .provider import EncryptionProvider, EncryptionError

logger = logging.getLogger(__name__)


class AESEncryption(EncryptionProvider):
    """
    AES-256-CBC encryption provider for cache data.
    
    Provides secure encryption using AES-256 in CBC mode with PKCS7 padding
    and random initialization vectors for each encryption operation.
    """
    
    def __init__(self, key_manager: 'KeyManager'):
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
                original_error=e
            )
    
    def encrypt(self, data: Any) -> bytes:
        """
        Encrypt data using AES-256-CBC with random IV.
        
        Args:
            data: Data to encrypt (must be JSON-serializable)
            
        Returns:
            Encrypted data as bytes (IV + encrypted_data)
            
        Raises:
            EncryptionError: If encryption fails
        """
        try:
            # Serialize data to JSON
            json_str = json.dumps(data, separators=(',', ':'))
            json_bytes = json_str.encode('utf-8')
            
            # Get encryption key
            key = self.key_manager.get_key()
            
            # Generate random IV (16 bytes for AES)
            iv = os.urandom(16)
            
            # Create cipher
            cipher = Cipher(
                algorithms.AES(key),
                modes.CBC(iv),
                backend=self._backend
            )
            encryptor = cipher.encryptor()
            
            # Apply PKCS7 padding
            padder = padding.PKCS7(128).padder()  # 128 bits = 16 bytes for AES
            padded_data = padder.update(json_bytes)
            padded_data += padder.finalize()
            
            # Encrypt data
            encrypted_data = encryptor.update(padded_data) + encryptor.finalize()
            
            # Return IV + encrypted data
            return iv + encrypted_data
            
        except (TypeError, ValueError) as e:
            raise EncryptionError(
                f"Failed to serialize data for encryption: {e}",
                encryption_type="aes256",
                original_error=e
            )
        except Exception as e:
            raise EncryptionError(
                f"AES encryption failed: {e}",
                encryption_type="aes256",
                original_error=e
            )
    
    def decrypt(self, encrypted_data: bytes) -> Any:
        """
        Decrypt AES-256-CBC encrypted data.
        
        Args:
            encrypted_data: Encrypted data as bytes (IV + encrypted_data)
            
        Returns:
            Original decrypted data
            
        Raises:
            EncryptionError: If decryption fails
        """
        try:
            if len(encrypted_data) < 16:
                raise ValueError("Invalid encrypted data: too short to contain IV")
            
            # Extract IV and encrypted content
            iv = encrypted_data[:16]
            encrypted_content = encrypted_data[16:]
            
            if len(encrypted_content) == 0:
                raise ValueError("Invalid encrypted data: no encrypted content")
            
            # Get decryption key
            key = self.key_manager.get_key()
            
            # Create cipher
            cipher = Cipher(
                algorithms.AES(key),
                modes.CBC(iv),
                backend=self._backend
            )
            decryptor = cipher.decryptor()
            
            # Decrypt data
            padded_data = decryptor.update(encrypted_content) + decryptor.finalize()
            
            # Remove PKCS7 padding
            unpadder = padding.PKCS7(128).unpadder()
            json_bytes = unpadder.update(padded_data) + unpadder.finalize()
            
            # Deserialize JSON
            json_str = json_bytes.decode('utf-8')
            return json.loads(json_str)
            
        except EncryptionError:
            # Re-raise EncryptionError as-is to avoid double wrapping
            raise
        except UnicodeDecodeError as e:
            raise EncryptionError(
                f"Failed to decode decrypted data as UTF-8: {e}",
                encryption_type="aes256",
                original_error=e
            )
        except json.JSONDecodeError as e:
            raise EncryptionError(
                f"Failed to deserialize decrypted JSON data: {e}",
                encryption_type="aes256",
                original_error=e
            )
        except ValueError as e:
            # This can be raised by padding operations, cipher operations, or our validation
            if "Invalid encrypted data" in str(e):
                # Our own validation errors
                raise EncryptionError(
                    str(e),
                    encryption_type="aes256"
                )
            elif "Invalid padding" in str(e) or "padding" in str(e).lower():
                raise EncryptionError(
                    "Decryption failed: invalid padding (wrong key or corrupted data)",
                    encryption_type="aes256",
                    original_error=e
                )
            else:
                raise EncryptionError(
                    f"AES decryption failed: {e}",
                    encryption_type="aes256",
                    original_error=e
                )
        except Exception as e:
            raise EncryptionError(
                f"AES decryption failed: {e}",
                encryption_type="aes256",
                original_error=e
            )
    
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
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            from cryptography.hazmat.primitives import padding
            from cryptography.hazmat.backends import default_backend
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
                    "Invalid encryption key: must be 32 bytes for AES-256",
                    encryption_type="aes256"
                )
        except EncryptionError:
            raise
        except Exception as e:
            raise EncryptionError(
                f"Failed to access encryption key: {e}",
                encryption_type="aes256",
                original_error=e
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
        if len(a) != len(b):
            return False
        
        result = 0
        for x, y in zip(a, b):
            result |= x ^ y
        
        return result == 0
    
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