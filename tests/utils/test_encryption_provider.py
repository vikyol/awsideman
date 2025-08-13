"""Tests for encryption provider interface and implementations."""

import json

import pytest

from src.awsideman.encryption.provider import (
    EncryptionError,
    EncryptionProvider,
    EncryptionProviderFactory,
    NoEncryption,
)


class TestEncryptionProvider:
    """Test the abstract EncryptionProvider interface."""

    def test_abstract_methods_raise_not_implemented(self):
        """Test that abstract methods raise NotImplementedError."""
        # Cannot instantiate abstract class directly
        with pytest.raises(TypeError):
            EncryptionProvider()


class TestEncryptionError:
    """Test the EncryptionError exception class."""

    def test_basic_error_creation(self):
        """Test basic error creation with message only."""
        error = EncryptionError("Test error message")
        assert str(error) == "Test error message"
        assert error.encryption_type == "unknown"
        assert error.original_error is None

    def test_error_with_encryption_type(self):
        """Test error creation with encryption type."""
        error = EncryptionError("Test error", encryption_type="aes256")
        assert str(error) == "Test error"
        assert error.encryption_type == "aes256"
        assert error.original_error is None

    def test_error_with_original_error(self):
        """Test error creation with original exception."""
        original = ValueError("Original error")
        error = EncryptionError("Test error", original_error=original)
        assert "Test error (caused by: Original error)" in str(error)
        assert error.original_error == original

    def test_error_with_all_parameters(self):
        """Test error creation with all parameters."""
        original = ValueError("Original error")
        error = EncryptionError("Test error", encryption_type="aes256", original_error=original)
        assert "Test error (caused by: Original error)" in str(error)
        assert error.encryption_type == "aes256"
        assert error.original_error == original


class TestNoEncryption:
    """Test the NoEncryption provider implementation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.provider = NoEncryption()

    def test_encrypt_simple_data(self):
        """Test encrypting simple data types."""
        test_cases = [{"key": "value"}, ["item1", "item2"], "simple string", 42, 3.14, True, None]

        for data in test_cases:
            encrypted = self.provider.encrypt(data)
            assert isinstance(encrypted, bytes)

            # Should be valid JSON
            json_str = encrypted.decode("utf-8")
            parsed = json.loads(json_str)
            assert parsed == data

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

        # Create a non-serializable object
        class NonSerializable:
            pass

        non_serializable = NonSerializable()

        with pytest.raises(EncryptionError) as exc_info:
            self.provider.encrypt(non_serializable)

        assert exc_info.value.encryption_type == "none"
        assert "Failed to serialize data to JSON" in str(exc_info.value)
        assert isinstance(exc_info.value.original_error, TypeError)

    def test_decrypt_invalid_bytes_raises_error(self):
        """Test that invalid bytes raise EncryptionError."""
        # Invalid UTF-8 bytes
        invalid_bytes = b"\xff\xfe\xfd"

        with pytest.raises(EncryptionError) as exc_info:
            self.provider.decrypt(invalid_bytes)

        assert exc_info.value.encryption_type == "none"
        assert "Failed to decode bytes to UTF-8" in str(exc_info.value)
        assert isinstance(exc_info.value.original_error, UnicodeDecodeError)

    def test_decrypt_invalid_json_raises_error(self):
        """Test that invalid JSON raises EncryptionError."""
        # Valid UTF-8 but invalid JSON
        invalid_json = b'{"invalid": json}'

        with pytest.raises(EncryptionError) as exc_info:
            self.provider.decrypt(invalid_json)

        assert exc_info.value.encryption_type == "none"
        assert "Failed to deserialize JSON data" in str(exc_info.value)
        assert isinstance(exc_info.value.original_error, json.JSONDecodeError)

    def test_get_encryption_type(self):
        """Test getting encryption type identifier."""
        assert self.provider.get_encryption_type() == "none"

    def test_is_available(self):
        """Test availability check."""
        assert self.provider.is_available() is True

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


class TestEncryptionProviderFactory:
    """Test the EncryptionProviderFactory class."""

    def test_create_none_provider(self):
        """Test creating no-encryption provider."""
        provider = EncryptionProviderFactory.create_provider("none")
        assert isinstance(provider, NoEncryption)
        assert provider.get_encryption_type() == "none"

    def test_create_unknown_provider_raises_error(self):
        """Test that unknown provider type raises EncryptionError."""
        with pytest.raises(EncryptionError) as exc_info:
            EncryptionProviderFactory.create_provider("unknown")

        assert "Unknown encryption type: unknown" in str(exc_info.value)
        assert exc_info.value.encryption_type == "unknown"

    def test_create_aes_provider_missing_key_manager(self):
        """Test creating AES provider without key_manager works automatically."""
        # Now creates a KeyManager automatically instead of raising an error
        provider = EncryptionProviderFactory.create_provider("aes256")

        assert provider.get_encryption_type() == "aes256"
        # Should have created a key manager automatically
        assert hasattr(provider, "key_manager")

    def test_create_aes_provider_with_key_manager(self):
        """Test creating AES provider with key manager."""
        from unittest.mock import Mock

        # Mock key manager
        key_manager = Mock()
        key_manager.get_key.return_value = b"0" * 32  # 32-byte key

        provider = EncryptionProviderFactory.create_provider("aes256", key_manager=key_manager)

        assert provider.get_encryption_type() == "aes256"

    def test_get_available_providers_basic(self):
        """Test getting available providers (basic case)."""
        providers = EncryptionProviderFactory.get_available_providers()
        assert "none" in providers
        assert isinstance(providers, list)

    def test_get_available_providers_with_aes(self):
        """Test getting available providers when AES is available."""
        providers = EncryptionProviderFactory.get_available_providers()

        assert "none" in providers
        # AES should be available now that we've implemented it
        assert "aes256" in providers

    def test_get_available_providers_includes_aes(self):
        """Test getting available providers includes AES when implemented."""
        providers = EncryptionProviderFactory.get_available_providers()

        assert "none" in providers
        # AES should be available now that we've implemented it
        assert "aes256" in providers

    def test_validate_provider_config_none(self):
        """Test validating configuration for no-encryption provider."""
        assert EncryptionProviderFactory.validate_provider_config("none", {}) is True
        assert EncryptionProviderFactory.validate_provider_config("none", {"any": "config"}) is True

    def test_validate_provider_config_unknown(self):
        """Test validating configuration for unknown provider."""
        assert EncryptionProviderFactory.validate_provider_config("unknown", {}) is False

    def test_validate_provider_config_aes_available(self):
        """Test validating configuration for AES provider when available."""
        result = EncryptionProviderFactory.validate_provider_config("aes256", {"key": "value"})

        # Should return True since AES is now implemented
        assert result is True

    def test_validate_provider_config_aes_works(self):
        """Test validating configuration for AES provider works."""
        result = EncryptionProviderFactory.validate_provider_config("aes256", {})

        # Should return True since AES is available
        assert result is True


class TestEncryptionProviderIntegration:
    """Integration tests for encryption providers."""

    def test_factory_creates_functional_providers(self):
        """Test that factory creates functional providers."""
        provider = EncryptionProviderFactory.create_provider("none")

        # Test basic functionality
        test_data = {"test": "data", "number": 42}
        encrypted = provider.encrypt(test_data)
        decrypted = provider.decrypt(encrypted)

        assert decrypted == test_data
        assert provider.is_available() is True
        assert provider.get_encryption_type() == "none"

    def test_provider_error_handling_consistency(self):
        """Test that all providers handle errors consistently."""
        provider = EncryptionProviderFactory.create_provider("none")

        # Test encryption error
        class NonSerializable:
            pass

        with pytest.raises(EncryptionError) as exc_info:
            provider.encrypt(NonSerializable())

        assert exc_info.value.encryption_type == "none"
        assert exc_info.value.original_error is not None

        # Test decryption error
        with pytest.raises(EncryptionError) as exc_info:
            provider.decrypt(b"invalid json")

        assert exc_info.value.encryption_type == "none"
        assert exc_info.value.original_error is not None
