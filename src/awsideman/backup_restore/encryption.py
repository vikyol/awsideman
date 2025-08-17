"""
Encryption providers for backup data security.

This module provides encryption implementations for securing backup data
at rest and in transit, supporting various encryption algorithms and
key management strategies with integration to the existing key management system.
"""

import base64
import hashlib
import logging
import os
import secrets
from typing import Any, Dict, Optional, Tuple

from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from ..encryption.key_manager import FallbackKeyManager, KeyManager
from ..encryption.provider import EncryptionError
from .interfaces import EncryptionProviderInterface

logger = logging.getLogger(__name__)


class FernetEncryptionProvider(EncryptionProviderInterface):
    """
    Fernet-based encryption provider using symmetric encryption.

    Provides simple and secure encryption using the Fernet symmetric
    encryption algorithm from the cryptography library.
    """

    def __init__(self, master_key: Optional[str] = None):
        """
        Initialize Fernet encryption provider.

        Args:
            master_key: Optional master key for encryption. If not provided,
                       a new key will be generated.
        """
        if master_key:
            self.master_key = master_key.encode() if isinstance(master_key, str) else master_key
        else:
            self.master_key = Fernet.generate_key()

        self.fernet = Fernet(self.master_key)
        logger.info("Initialized Fernet encryption provider")

    async def encrypt(
        self, data: bytes, key_id: Optional[str] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Encrypt data using Fernet encryption.

        Args:
            data: Raw data to encrypt
            key_id: Optional key identifier (not used in this implementation)

        Returns:
            Tuple of (encrypted_data, encryption_metadata)
        """
        try:
            encrypted_data = self.fernet.encrypt(data)

            metadata = {
                "algorithm": "Fernet",
                "key_id": key_id or "default",
                "encrypted": True,
                "version": "1.0",
            }

            logger.debug(f"Successfully encrypted {len(data)} bytes")
            return encrypted_data, metadata

        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise

    async def decrypt(self, encrypted_data: bytes, encryption_metadata: Dict[str, Any]) -> bytes:
        """
        Decrypt data using Fernet encryption.

        Args:
            encrypted_data: Encrypted data to decrypt
            encryption_metadata: Metadata needed for decryption

        Returns:
            Decrypted raw data
        """
        try:
            if not encryption_metadata.get("encrypted", False):
                logger.warning("Data is not marked as encrypted")
                return encrypted_data

            algorithm = encryption_metadata.get("algorithm")
            if algorithm != "Fernet":
                raise ValueError(f"Unsupported encryption algorithm: {algorithm}")

            decrypted_data = self.fernet.decrypt(encrypted_data)

            logger.debug(f"Successfully decrypted {len(encrypted_data)} bytes")
            return decrypted_data

        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise

    async def generate_key(self) -> str:
        """
        Generate a new encryption key.

        Returns:
            Key identifier for the generated key
        """
        new_key = Fernet.generate_key()
        key_id = hashlib.sha256(new_key).hexdigest()[:16]

        logger.info(f"Generated new encryption key: {key_id}")
        return key_id

    async def rotate_key(self, old_key_id: str) -> str:
        """
        Rotate an encryption key.

        Args:
            old_key_id: Identifier of the key to rotate

        Returns:
            Identifier of the new key
        """
        # For Fernet, we generate a new key and update the provider
        new_key = Fernet.generate_key()
        self.master_key = new_key
        self.fernet = Fernet(new_key)

        new_key_id = hashlib.sha256(new_key).hexdigest()[:16]

        logger.info(f"Rotated encryption key from {old_key_id} to {new_key_id}")
        return new_key_id

    def get_master_key(self) -> bytes:
        """
        Get the master key (for backup/recovery purposes).

        Returns:
            Master key bytes
        """
        return self.master_key


class AESEncryptionProvider(EncryptionProviderInterface):
    """
    AES-256 encryption provider with PBKDF2 key derivation.

    Provides AES-256-GCM encryption with password-based key derivation
    for enhanced security and compatibility.
    """

    def __init__(self, password: Optional[str] = None, salt: Optional[bytes] = None):
        """
        Initialize AES encryption provider.

        Args:
            password: Password for key derivation. If not provided, a random one is generated.
            salt: Salt for key derivation. If not provided, a random one is generated.
        """
        self.password = password or secrets.token_urlsafe(32)
        self.salt = salt or os.urandom(16)

        # Derive key from password
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,  # 256 bits
            salt=self.salt,
            iterations=100000,
            backend=default_backend(),
        )
        self.key = kdf.derive(
            self.password.encode() if isinstance(self.password, str) else self.password
        )

        logger.info("Initialized AES-256 encryption provider")

    async def encrypt(
        self, data: bytes, key_id: Optional[str] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Encrypt data using AES-256-GCM.

        Args:
            data: Raw data to encrypt
            key_id: Optional key identifier

        Returns:
            Tuple of (encrypted_data, encryption_metadata)
        """
        try:
            # Generate a random IV
            iv = os.urandom(12)  # 96 bits for GCM

            # Create cipher
            cipher = Cipher(algorithms.AES(self.key), modes.GCM(iv), backend=default_backend())
            encryptor = cipher.encryptor()

            # Encrypt data
            ciphertext = encryptor.update(data) + encryptor.finalize()

            # Combine IV, tag, and ciphertext
            encrypted_data = iv + encryptor.tag + ciphertext

            metadata = {
                "algorithm": "AES-256-GCM",
                "key_id": key_id or "default",
                "iv": base64.b64encode(iv).decode(),
                "salt": base64.b64encode(self.salt).decode(),
                "encrypted": True,
                "version": "1.0",
            }

            logger.debug(f"Successfully encrypted {len(data)} bytes with AES-256-GCM")
            return encrypted_data, metadata

        except Exception as e:
            logger.error(f"AES encryption failed: {e}")
            raise

    async def decrypt(self, encrypted_data: bytes, encryption_metadata: Dict[str, Any]) -> bytes:
        """
        Decrypt data using AES-256-GCM.

        Args:
            encrypted_data: Encrypted data to decrypt
            encryption_metadata: Metadata needed for decryption

        Returns:
            Decrypted raw data
        """
        try:
            if not encryption_metadata.get("encrypted", False):
                logger.warning("Data is not marked as encrypted")
                return encrypted_data

            algorithm = encryption_metadata.get("algorithm")
            if algorithm != "AES-256-GCM":
                raise ValueError(f"Unsupported encryption algorithm: {algorithm}")

            # Extract IV, tag, and ciphertext
            iv = encrypted_data[:12]
            tag = encrypted_data[12:28]
            ciphertext = encrypted_data[28:]

            # Create cipher
            cipher = Cipher(algorithms.AES(self.key), modes.GCM(iv, tag), backend=default_backend())
            decryptor = cipher.decryptor()

            # Decrypt data
            decrypted_data = decryptor.update(ciphertext) + decryptor.finalize()

            logger.debug(f"Successfully decrypted {len(encrypted_data)} bytes with AES-256-GCM")
            return decrypted_data

        except Exception as e:
            logger.error(f"AES decryption failed: {e}")
            raise

    async def generate_key(self) -> str:
        """
        Generate a new encryption key.

        Returns:
            Key identifier for the generated key
        """
        new_password = secrets.token_urlsafe(32)
        new_salt = os.urandom(16)

        # Derive new key
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=new_salt,
            iterations=100000,
            backend=default_backend(),
        )
        new_key = kdf.derive(new_password.encode())

        key_id = hashlib.sha256(new_key).hexdigest()[:16]

        logger.info(f"Generated new AES encryption key: {key_id}")
        return key_id

    async def rotate_key(self, old_key_id: str) -> str:
        """
        Rotate an encryption key.

        Args:
            old_key_id: Identifier of the key to rotate

        Returns:
            Identifier of the new key
        """
        # Generate new password and salt
        self.password = secrets.token_urlsafe(32)
        self.salt = os.urandom(16)

        # Derive new key
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.salt,
            iterations=100000,
            backend=default_backend(),
        )
        self.key = kdf.derive(self.password.encode())

        new_key_id = hashlib.sha256(self.key).hexdigest()[:16]

        logger.info(f"Rotated AES encryption key from {old_key_id} to {new_key_id}")
        return new_key_id

    def get_key_info(self) -> Dict[str, str]:
        """
        Get key information for backup/recovery purposes.

        Returns:
            Dictionary containing key information
        """
        return {
            "salt": base64.b64encode(self.salt).decode(),
            "password": (
                self.password
                if isinstance(self.password, str)
                else base64.b64encode(self.password).decode()
            ),
        }


class NoOpEncryptionProvider(EncryptionProviderInterface):
    """
    No-operation encryption provider for testing or when encryption is disabled.

    This provider passes data through without any encryption, useful for
    testing scenarios or when encryption is not required.
    """

    def __init__(self):
        """Initialize no-op encryption provider."""
        logger.info("Initialized no-op encryption provider (no encryption)")

    async def encrypt(
        self, data: bytes, key_id: Optional[str] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Pass-through encryption (no actual encryption).

        Args:
            data: Raw data to "encrypt"
            key_id: Optional key identifier (ignored)

        Returns:
            Tuple of (original_data, empty_metadata)
        """
        metadata = {
            "algorithm": "none",
            "key_id": key_id or "none",
            "encrypted": False,
            "version": "1.0",
        }

        logger.debug(f"Pass-through encryption for {len(data)} bytes")
        return data, metadata

    async def decrypt(self, encrypted_data: bytes, encryption_metadata: Dict[str, Any]) -> bytes:
        """
        Pass-through decryption (no actual decryption).

        Args:
            encrypted_data: Data to "decrypt"
            encryption_metadata: Metadata (ignored)

        Returns:
            Original data unchanged
        """
        logger.debug(f"Pass-through decryption for {len(encrypted_data)} bytes")
        return encrypted_data

    async def generate_key(self) -> str:
        """
        Generate a dummy key identifier.

        Returns:
            Dummy key identifier
        """
        key_id = f"noop-{secrets.token_hex(8)}"
        logger.debug(f"Generated dummy key: {key_id}")
        return key_id

    async def rotate_key(self, old_key_id: str) -> str:
        """
        Rotate to a new dummy key identifier.

        Args:
            old_key_id: Old key identifier (ignored)

        Returns:
            New dummy key identifier
        """
        new_key_id = f"noop-{secrets.token_hex(8)}"
        logger.debug(f"Rotated dummy key from {old_key_id} to {new_key_id}")
        return new_key_id


class ManagedAESEncryptionProvider(EncryptionProviderInterface):
    """
    AES-256 encryption provider integrated with the existing key management system.

    This provider uses the centralized key management system for secure key storage
    and rotation, providing AES-256-GCM encryption for backup data at rest and in transit.
    """

    def __init__(self, service_name: str = "awsideman-backup", use_fallback: bool = True):
        """
        Initialize managed AES encryption provider.

        Args:
            service_name: Service name for key management
            use_fallback: Whether to use fallback key manager if keyring unavailable
        """
        self.service_name = service_name

        if use_fallback:
            self.key_manager = FallbackKeyManager(
                service_name=service_name, username="backup-encryption-key"
            )
        else:
            self.key_manager = KeyManager(
                service_name=service_name, username="backup-encryption-key"
            )

        logger.info(f"Initialized managed AES-256 encryption provider for service: {service_name}")

    async def encrypt(
        self, data: bytes, key_id: Optional[str] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Encrypt data using AES-256-GCM with managed keys.

        Args:
            data: Raw data to encrypt
            key_id: Optional key identifier (used for metadata only)

        Returns:
            Tuple of (encrypted_data, encryption_metadata)
        """
        try:
            # Get encryption key from key manager
            encryption_key = self.key_manager.get_key()

            # Generate a random IV
            iv = os.urandom(12)  # 96 bits for GCM

            # Create cipher
            cipher = Cipher(
                algorithms.AES(encryption_key), modes.GCM(iv), backend=default_backend()
            )
            encryptor = cipher.encryptor()

            # Encrypt data
            ciphertext = encryptor.update(data) + encryptor.finalize()

            # Combine IV, tag, and ciphertext
            encrypted_data = iv + encryptor.tag + ciphertext

            # Generate key fingerprint for verification
            key_fingerprint = hashlib.sha256(encryption_key).hexdigest()[:16]

            metadata = {
                "algorithm": "AES-256-GCM-Managed",
                "key_id": key_id or "managed",
                "key_fingerprint": key_fingerprint,
                "iv": base64.b64encode(iv).decode(),
                "service_name": self.service_name,
                "encrypted": True,
                "version": "2.0",
                "encryption_at_rest": True,
                "encryption_in_transit": True,
            }

            logger.debug(f"Successfully encrypted {len(data)} bytes with managed AES-256-GCM")
            return encrypted_data, metadata

        except Exception as e:
            logger.error(f"Managed AES encryption failed: {e}")
            raise EncryptionError(
                f"Managed AES encryption failed: {e}",
                encryption_type="managed_aes",
                original_error=e,
            )

    async def decrypt(self, encrypted_data: bytes, encryption_metadata: Dict[str, Any]) -> bytes:
        """
        Decrypt data using AES-256-GCM with managed keys.

        Args:
            encrypted_data: Encrypted data to decrypt
            encryption_metadata: Metadata needed for decryption

        Returns:
            Decrypted raw data
        """
        try:
            if not encryption_metadata.get("encrypted", False):
                logger.warning("Data is not marked as encrypted")
                return encrypted_data

            algorithm = encryption_metadata.get("algorithm")
            if algorithm != "AES-256-GCM-Managed":
                raise ValueError(f"Unsupported encryption algorithm: {algorithm}")

            # Get decryption key from key manager
            decryption_key = self.key_manager.get_key()

            # Verify key fingerprint if available
            if "key_fingerprint" in encryption_metadata:
                current_fingerprint = hashlib.sha256(decryption_key).hexdigest()[:16]
                expected_fingerprint = encryption_metadata["key_fingerprint"]
                if current_fingerprint != expected_fingerprint:
                    logger.warning("Key fingerprint mismatch - key may have been rotated")

            # Extract IV, tag, and ciphertext
            iv = encrypted_data[:12]
            tag = encrypted_data[12:28]
            ciphertext = encrypted_data[28:]

            # Create cipher
            cipher = Cipher(
                algorithms.AES(decryption_key), modes.GCM(iv, tag), backend=default_backend()
            )
            decryptor = cipher.decryptor()

            # Decrypt data
            decrypted_data = decryptor.update(ciphertext) + decryptor.finalize()

            logger.debug(
                f"Successfully decrypted {len(encrypted_data)} bytes with managed AES-256-GCM"
            )
            return decrypted_data

        except Exception as e:
            logger.error(f"Managed AES decryption failed: {e}")
            raise EncryptionError(
                f"Managed AES decryption failed: {e}",
                encryption_type="managed_aes",
                original_error=e,
            )

    async def generate_key(self) -> str:
        """
        Generate a new encryption key using the key manager.

        Returns:
            Key identifier for the generated key
        """
        try:
            # Rotate key in key manager (generates new key)
            old_key, new_key = self.key_manager.rotate_key()

            # Generate key identifier
            key_id = hashlib.sha256(new_key).hexdigest()[:16]

            logger.info(f"Generated new managed encryption key: {key_id}")
            return key_id

        except Exception as e:
            logger.error(f"Failed to generate managed key: {e}")
            raise EncryptionError(
                f"Failed to generate managed key: {e}",
                encryption_type="managed_aes",
                original_error=e,
            )

    async def rotate_key(self, old_key_id: str) -> str:
        """
        Rotate an encryption key using the key manager.

        Args:
            old_key_id: Identifier of the key to rotate

        Returns:
            Identifier of the new key
        """
        try:
            # Rotate key in key manager
            old_key, new_key = self.key_manager.rotate_key()

            # Generate new key identifier
            new_key_id = hashlib.sha256(new_key).hexdigest()[:16]

            logger.info(f"Rotated managed encryption key from {old_key_id} to {new_key_id}")
            return new_key_id

        except Exception as e:
            logger.error(f"Failed to rotate managed key: {e}")
            raise EncryptionError(
                f"Failed to rotate managed key: {e}",
                encryption_type="managed_aes",
                original_error=e,
            )

    def get_key_info(self) -> Dict[str, Any]:
        """
        Get information about the managed key.

        Returns:
            Dictionary containing key information
        """
        try:
            key_info = self.key_manager.get_key_info()
            key_info["provider_type"] = "managed_aes"
            key_info["service_name"] = self.service_name
            return key_info
        except Exception as e:
            logger.error(f"Failed to get managed key info: {e}")
            return {
                "error": str(e),
                "provider_type": "managed_aes",
                "service_name": self.service_name,
            }

    async def verify_key_access(self) -> bool:
        """
        Verify that the key manager can access encryption keys.

        Returns:
            True if key access is working, False otherwise
        """
        try:
            # Try to get a key to verify access
            key = self.key_manager.get_key()
            return len(key) == 32  # AES-256 requires 32 bytes
        except Exception as e:
            logger.error(f"Key access verification failed: {e}")
            return False


class TransitEncryptionProvider(EncryptionProviderInterface):
    """
    Encryption provider specifically designed for data in transit.

    This provider adds additional security measures for data being transmitted
    over networks, including integrity verification and anti-replay protection.
    """

    def __init__(self, base_provider: EncryptionProviderInterface):
        """
        Initialize transit encryption provider.

        Args:
            base_provider: Base encryption provider to wrap
        """
        self.base_provider = base_provider
        logger.info("Initialized transit encryption provider")

    async def encrypt(
        self, data: bytes, key_id: Optional[str] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Encrypt data for transit with additional security measures.

        Args:
            data: Raw data to encrypt
            key_id: Optional key identifier

        Returns:
            Tuple of (encrypted_data, encryption_metadata)
        """
        try:
            # Add timestamp and nonce for anti-replay protection
            import time

            timestamp = int(time.time()).to_bytes(8, "big")
            nonce = os.urandom(16)

            # Prepend timestamp and nonce to data
            transit_data = timestamp + nonce + data

            # Encrypt using base provider
            encrypted_data, metadata = await self.base_provider.encrypt(transit_data, key_id)

            # Add transit-specific metadata
            metadata.update(
                {
                    "transit_encryption": True,
                    "timestamp": int.from_bytes(timestamp, "big"),
                    "nonce": base64.b64encode(nonce).decode(),
                    "integrity_hash": hashlib.sha256(data).hexdigest(),
                }
            )

            logger.debug(f"Successfully encrypted {len(data)} bytes for transit")
            return encrypted_data, metadata

        except Exception as e:
            logger.error(f"Transit encryption failed: {e}")
            raise EncryptionError(
                f"Transit encryption failed: {e}", encryption_type="transit", original_error=e
            )

    async def decrypt(self, encrypted_data: bytes, encryption_metadata: Dict[str, Any]) -> bytes:
        """
        Decrypt data from transit with security verification.

        Args:
            encrypted_data: Encrypted data to decrypt
            encryption_metadata: Metadata needed for decryption

        Returns:
            Decrypted raw data
        """
        try:
            # Decrypt using base provider
            transit_data = await self.base_provider.decrypt(encrypted_data, encryption_metadata)

            # Extract timestamp and original data
            timestamp = transit_data[:8]
            original_data = transit_data[24:]

            # Verify timestamp (optional anti-replay check)
            if "timestamp" in encryption_metadata:
                expected_timestamp = encryption_metadata["timestamp"]
                actual_timestamp = int.from_bytes(timestamp, "big")
                if actual_timestamp != expected_timestamp:
                    logger.warning("Timestamp mismatch in transit decryption")

            # Verify integrity hash if available
            if "integrity_hash" in encryption_metadata:
                expected_hash = encryption_metadata["integrity_hash"]
                actual_hash = hashlib.sha256(original_data).hexdigest()
                if actual_hash != expected_hash:
                    raise EncryptionError(
                        "Integrity verification failed during transit decryption",
                        encryption_type="transit",
                    )

            logger.debug(f"Successfully decrypted {len(encrypted_data)} bytes from transit")
            return original_data

        except Exception as e:
            logger.error(f"Transit decryption failed: {e}")
            raise EncryptionError(
                f"Transit decryption failed: {e}", encryption_type="transit", original_error=e
            )

    async def generate_key(self) -> str:
        """Generate a new encryption key using the base provider."""
        return await self.base_provider.generate_key()

    async def rotate_key(self, old_key_id: str) -> str:
        """Rotate an encryption key using the base provider."""
        return await self.base_provider.rotate_key(old_key_id)


class EncryptionProviderFactory:
    """Factory for creating encryption provider instances."""

    @staticmethod
    def create_fernet_provider(master_key: Optional[str] = None) -> FernetEncryptionProvider:
        """
        Create a Fernet encryption provider.

        Args:
            master_key: Optional master key

        Returns:
            FernetEncryptionProvider instance
        """
        return FernetEncryptionProvider(master_key)

    @staticmethod
    def create_aes_provider(
        password: Optional[str] = None, salt: Optional[bytes] = None
    ) -> AESEncryptionProvider:
        """
        Create an AES encryption provider.

        Args:
            password: Optional password for key derivation
            salt: Optional salt for key derivation

        Returns:
            AESEncryptionProvider instance
        """
        return AESEncryptionProvider(password, salt)

    @staticmethod
    def create_managed_aes_provider(
        service_name: str = "awsideman-backup", use_fallback: bool = True
    ) -> ManagedAESEncryptionProvider:
        """
        Create a managed AES encryption provider.

        Args:
            service_name: Service name for key management
            use_fallback: Whether to use fallback key manager if keyring unavailable

        Returns:
            ManagedAESEncryptionProvider instance
        """
        return ManagedAESEncryptionProvider(service_name, use_fallback)

    @staticmethod
    def create_transit_provider(
        base_provider: EncryptionProviderInterface,
    ) -> TransitEncryptionProvider:
        """
        Create a transit encryption provider.

        Args:
            base_provider: Base encryption provider to wrap

        Returns:
            TransitEncryptionProvider instance
        """
        return TransitEncryptionProvider(base_provider)

    @staticmethod
    def create_noop_provider() -> NoOpEncryptionProvider:
        """
        Create a no-op encryption provider.

        Returns:
            NoOpEncryptionProvider instance
        """
        return NoOpEncryptionProvider()

    @staticmethod
    def create_provider(provider_type: str, **config) -> EncryptionProviderInterface:
        """
        Create an encryption provider based on type and configuration.

        Args:
            provider_type: Type of provider ('fernet', 'aes', 'managed_aes', 'transit', 'noop')
            **config: Configuration parameters for the provider

        Returns:
            EncryptionProviderInterface implementation

        Raises:
            ValueError: If provider_type is not supported
        """
        provider_type = provider_type.lower()

        if provider_type == "fernet":
            return EncryptionProviderFactory.create_fernet_provider(**config)
        elif provider_type == "aes":
            return EncryptionProviderFactory.create_aes_provider(**config)
        elif provider_type == "managed_aes":
            return EncryptionProviderFactory.create_managed_aes_provider(**config)
        elif provider_type == "transit":
            base_provider = config.get("base_provider")
            if not base_provider:
                # Default to managed AES as base provider
                base_provider = EncryptionProviderFactory.create_managed_aes_provider()
            return EncryptionProviderFactory.create_transit_provider(base_provider)
        elif provider_type == "noop" or provider_type == "none":
            return EncryptionProviderFactory.create_noop_provider()
        else:
            raise ValueError(f"Unsupported encryption provider type: {provider_type}")

    @staticmethod
    def create_default_provider() -> EncryptionProviderInterface:
        """
        Create the default encryption provider for backup operations.

        Returns:
            Default encryption provider (ManagedAESEncryptionProvider)
        """
        return EncryptionProviderFactory.create_managed_aes_provider()
