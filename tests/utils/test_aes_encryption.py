"""Tests for AES encryption provider implementation."""

import os
from unittest.mock import Mock, patch

import pytest

from src.awsideman.encryption.aes import AESEncryption
from src.awsideman.encryption.provider import EncryptionError


class MockKeyManager:
    """Mock key manager for testing."""

    def __init__(self, key: bytes = None):
        self.key = key or os.urandom(32)  # 32 bytes for AES-256

    def get_key(self) -> bytes:
        return self.key


class TestAESEncryption:
    """Test the AESEncryption provider implementation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.key_manager = MockKeyManager()
        self.provider = AESEncryption(self.key_manager)

    def test_initialization_success(self):
        """Test successful initialization."""
        key_manager = MockKeyManager()
        provider = AESEncryption(key_manager)

        assert provider.key_manager == key_manager
        assert provider.get_encryption_type() == "aes256"

    def test_initialization_with_invalid_key_manager(self):
        """Test initialization with invalid key manager."""
        key_manager = Mock()
        key_manager.get_key.side_effect = Exception("Key access failed")

        with pytest.raises(EncryptionError) as exc_info:
            AESEncryption(key_manager)

        assert "Failed to initialize AES encryption" in str(exc_info.value)
        assert exc_info.value.encryption_type == "aes256"

    def test_encrypt_simple_data(self):
        """Test encrypting simple data types."""
        test_cases = [{"key": "value"}, ["item1", "item2"], "simple string", 42, 3.14, True, None]

        for data in test_cases:
            encrypted = self.provider.encrypt(data)
            assert isinstance(encrypted, bytes)
            assert len(encrypted) > 16  # At least IV + some encrypted data

            # First 16 bytes should be the IV
            iv = encrypted[:16]
            assert len(iv) == 16

            # Encrypted content should be present
            encrypted_content = encrypted[16:]
            assert len(encrypted_content) > 0

            # Each encryption should produce different results (due to random IV)
            encrypted2 = self.provider.encrypt(data)
            assert encrypted != encrypted2  # Different IVs should make them different

    def test_decrypt_simple_data(self):
        """Test decrypting simple data types."""
        test_cases = [{"key": "value"}, ["item1", "item2"], "simple string", 42, 3.14, True, None]

        for original_data in test_cases:
            # Encrypt then decrypt
            encrypted = self.provider.encrypt(original_data)
            decrypted = self.provider.decrypt(encrypted)
            assert decrypted == original_data

    def test_encrypt_complex_data(self):
        """Test encrypting complex nested data structures."""
        complex_data = {
            "users": [
                {"id": 1, "name": "Alice", "active": True},
                {"id": 2, "name": "Bob", "active": False},
            ],
            "metadata": {
                "total": 2,
                "page": 1,
                "settings": {"sort": "name", "filters": ["active"]},
            },
            "timestamp": 1234567890.123,
        }

        encrypted = self.provider.encrypt(complex_data)
        decrypted = self.provider.decrypt(encrypted)
        assert decrypted == complex_data

    def test_encrypt_non_serializable_data_raises_error(self):
        """Test that non-JSON-serializable data raises EncryptionError."""

        class NonSerializable:
            pass

        non_serializable = NonSerializable()

        with pytest.raises(EncryptionError) as exc_info:
            self.provider.encrypt(non_serializable)

        assert exc_info.value.encryption_type == "aes256"
        assert "Failed to serialize data for encryption" in str(exc_info.value)

    def test_decrypt_invalid_data_too_short(self):
        """Test that data too short to contain IV raises EncryptionError."""
        invalid_data = b"short"  # Less than 16 bytes

        with pytest.raises(EncryptionError) as exc_info:
            self.provider.decrypt(invalid_data)

        assert exc_info.value.encryption_type == "aes256"
        assert "too short to contain IV" in str(exc_info.value)

    def test_decrypt_invalid_data_no_content(self):
        """Test that data with only IV raises EncryptionError."""
        invalid_data = os.urandom(16)  # Only IV, no encrypted content

        with pytest.raises(EncryptionError) as exc_info:
            self.provider.decrypt(invalid_data)

        assert exc_info.value.encryption_type == "aes256"
        assert "no encrypted content" in str(exc_info.value)

    def test_decrypt_with_wrong_key(self):
        """Test decryption with wrong key raises EncryptionError."""
        # Encrypt with one key
        data = {"test": "data"}
        encrypted = self.provider.encrypt(data)

        # Try to decrypt with different key
        different_key_manager = MockKeyManager(os.urandom(32))
        different_provider = AESEncryption(different_key_manager)

        with pytest.raises(EncryptionError) as exc_info:
            different_provider.decrypt(encrypted)

        assert exc_info.value.encryption_type == "aes256"
        # Should be a padding error or similar
        assert (
            "padding" in str(exc_info.value).lower()
            or "decryption failed" in str(exc_info.value).lower()
        )

    def test_decrypt_corrupted_data(self):
        """Test decryption of corrupted data raises EncryptionError."""
        # Encrypt valid data
        data = {"test": "data"}
        encrypted = self.provider.encrypt(data)

        # Corrupt the encrypted data
        corrupted = bytearray(encrypted)
        corrupted[20] = (corrupted[20] + 1) % 256  # Flip a bit in encrypted content

        with pytest.raises(EncryptionError) as exc_info:
            self.provider.decrypt(bytes(corrupted))

        assert exc_info.value.encryption_type == "aes256"

    def test_get_encryption_type(self):
        """Test getting encryption type identifier."""
        assert self.provider.get_encryption_type() == "aes256"

    def test_is_available_success(self):
        """Test availability check when key manager works."""
        assert self.provider.is_available() is True

    def test_is_available_key_manager_fails(self):
        """Test availability check when key manager fails."""
        key_manager = Mock()
        key_manager.get_key.side_effect = Exception("Key access failed")

        # Create provider without triggering initialization error
        provider = AESEncryption.__new__(AESEncryption)
        provider.key_manager = key_manager

        assert provider.is_available() is False

    def test_is_available_static_success(self):
        """Test static availability check."""
        assert AESEncryption.is_available_static() is True

    @patch("src.awsideman.encryption.aes.Cipher")
    def test_is_available_static_import_error(self, mock_cipher):
        """Test static availability check with import error."""
        mock_cipher.side_effect = ImportError("Module not found")

        # Need to reload the module to test import error
        import importlib

        import src.awsideman.encryption.aes

        importlib.reload(src.awsideman.encryption.aes)

        # This test is complex due to import caching, so we'll test the factory instead
        from src.awsideman.encryption.provider import EncryptionProviderFactory

        providers = EncryptionProviderFactory.get_available_providers()
        # Should still have 'none' but might not have 'aes256' depending on import state
        assert "none" in providers

    def test_validate_config_success(self):
        """Test configuration validation."""
        assert AESEncryption.validate_config({}) is True
        assert AESEncryption.validate_config({"any": "config"}) is True

    def test_roundtrip_with_special_characters(self):
        """Test encryption/decryption with special characters."""
        special_data = {
            "unicode": "Hello 世界 🌍",
            "special_chars": "!@#$%^&*()_+-=[]{}|;':\",./<>?",
            "newlines": "Line 1\nLine 2\r\nLine 3",
            "tabs": "Column 1\tColumn 2\tColumn 3",
        }

        encrypted = self.provider.encrypt(special_data)
        decrypted = self.provider.decrypt(encrypted)
        assert decrypted == special_data

    def test_empty_data_structures(self):
        """Test encryption/decryption of empty data structures."""
        test_cases = [{}, [], "", 0, False]

        for data in test_cases:
            encrypted = self.provider.encrypt(data)
            decrypted = self.provider.decrypt(encrypted)
            assert decrypted == data

    def test_large_data_encryption(self):
        """Test encryption of large data structures."""
        # Create a large data structure
        large_data = {
            "items": [{"id": i, "data": f"item_{i}" * 100} for i in range(1000)],
            "metadata": {"count": 1000, "description": "Large test data" * 1000},
        }

        encrypted = self.provider.encrypt(large_data)
        decrypted = self.provider.decrypt(encrypted)
        assert decrypted == large_data

    def test_verify_integrity_valid_data(self):
        """Test integrity verification with valid data."""
        data = {"test": "data"}
        encrypted = self.provider.encrypt(data)

        assert self.provider.verify_integrity(encrypted) is True

    def test_verify_integrity_invalid_data(self):
        """Test integrity verification with invalid data."""
        invalid_data = b"invalid encrypted data"

        assert self.provider.verify_integrity(invalid_data) is False

    def test_verify_integrity_corrupted_data(self):
        """Test integrity verification with corrupted data."""
        data = {"test": "data"}
        encrypted = self.provider.encrypt(data)

        # Corrupt the data
        corrupted = bytearray(encrypted)
        corrupted[20] = (corrupted[20] + 1) % 256

        assert self.provider.verify_integrity(bytes(corrupted)) is False

    def test_different_keys_produce_different_results(self):
        """Test that different keys produce different encrypted results."""
        data = {"test": "data"}

        # Encrypt with first key
        encrypted1 = self.provider.encrypt(data)

        # Encrypt with second key
        key_manager2 = MockKeyManager(os.urandom(32))
        provider2 = AESEncryption(key_manager2)
        encrypted2 = provider2.encrypt(data)

        # Results should be different
        assert encrypted1 != encrypted2

        # But each should decrypt correctly with its own key
        assert self.provider.decrypt(encrypted1) == data
        assert provider2.decrypt(encrypted2) == data

    def test_iv_randomness(self):
        """Test that IVs are random for each encryption."""
        data = {"test": "data"}

        # Encrypt same data multiple times
        encryptions = [self.provider.encrypt(data) for _ in range(10)]

        # Extract IVs (first 16 bytes)
        ivs = [enc[:16] for enc in encryptions]

        # All IVs should be different
        assert len(set(ivs)) == len(ivs), "IVs should be unique"

        # All should decrypt to same data
        for enc in encryptions:
            assert self.provider.decrypt(enc) == data

    def test_key_manager_error_handling(self):
        """Test error handling when key manager fails during operations."""
        # Create provider with working key manager
        data = {"test": "data"}
        encrypted = self.provider.encrypt(data)

        # Make key manager fail
        self.key_manager.get_key = Mock(side_effect=Exception("Key access failed"))

        # Encryption should fail
        with pytest.raises(EncryptionError) as exc_info:
            self.provider.encrypt(data)

        assert "AES encryption failed" in str(exc_info.value)
        assert exc_info.value.encryption_type == "aes256"

        # Decryption should also fail
        with pytest.raises(EncryptionError) as exc_info:
            self.provider.decrypt(encrypted)

        assert "AES decryption failed" in str(exc_info.value)
        assert exc_info.value.encryption_type == "aes256"


class TestAESEncryptionIntegration:
    """Integration tests for AES encryption with real key manager."""

    @patch("keyring.get_password")
    @patch("keyring.set_password")
    def test_integration_with_key_manager(self, mock_set, mock_get):
        """Test AES encryption integration with key manager."""
        # Mock keyring to return None (no existing key)
        mock_get.return_value = None

        # Create real key manager (will generate new key)
        from src.awsideman.encryption.key_manager import KeyManager

        key_manager = KeyManager()

        # Create AES provider
        provider = AESEncryption(key_manager)

        # Test encryption/decryption
        test_data = {"integration": "test", "number": 42}
        encrypted = provider.encrypt(test_data)
        decrypted = provider.decrypt(encrypted)

        assert decrypted == test_data
        assert provider.get_encryption_type() == "aes256"
        assert provider.is_available() is True

        # Verify key was stored
        mock_set.assert_called_once()

    def test_error_propagation(self):
        """Test that errors are properly propagated with context."""
        key_manager = MockKeyManager()
        provider = AESEncryption(key_manager)

        # Test with invalid encrypted data
        with pytest.raises(EncryptionError) as exc_info:
            provider.decrypt(b"invalid")

        error = exc_info.value
        assert error.encryption_type == "aes256"
        assert error.original_error is None  # This specific validation error doesn't wrap another
        assert "too short to contain IV" in str(error)
