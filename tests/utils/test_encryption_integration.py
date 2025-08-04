"""Integration tests for the complete encryption infrastructure."""

import tempfile
import pytest
from unittest.mock import patch

from src.awsideman.encryption.provider import EncryptionProviderFactory
from src.awsideman.encryption.key_manager import FallbackKeyManager
from src.awsideman.encryption.aes import AESEncryption


class TestEncryptionInfrastructureIntegration:
    """Integration tests for the complete encryption infrastructure."""
    
    def test_complete_encryption_workflow(self):
        """Test the complete encryption workflow from factory to decryption."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create key manager with file fallback
            key_manager = FallbackKeyManager(fallback_dir=temp_dir)
            
            # Mock keyring as unavailable to use file storage
            with patch.object(key_manager, 'is_keyring_available', return_value=False):
                # Create AES encryption provider through factory
                provider = EncryptionProviderFactory.create_provider("aes256", key_manager=key_manager)
                
                # Verify provider type
                assert provider.get_encryption_type() == "aes256"
                assert isinstance(provider, AESEncryption)
                assert provider.is_available() is True
                
                # Test encryption/decryption with various data types
                test_data = [
                    {"users": ["alice", "bob"], "count": 2},
                    ["item1", "item2", "item3"],
                    "simple string with unicode: 世界",
                    42,
                    3.14159,
                    True,
                    None,
                    {"nested": {"deep": {"data": "value"}}}
                ]
                
                for data in test_data:
                    # Encrypt data
                    encrypted = provider.encrypt(data)
                    assert isinstance(encrypted, bytes)
                    assert len(encrypted) > 16  # At least IV + some content
                    
                    # Decrypt data
                    decrypted = provider.decrypt(encrypted)
                    assert decrypted == data
                    
                    # Verify integrity
                    assert provider.verify_integrity(encrypted) is True
    
    def test_key_rotation_with_encryption(self):
        """Test key rotation with re-encryption of data."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create key manager with file fallback
            key_manager = FallbackKeyManager(fallback_dir=temp_dir)
            
            # Mock keyring as unavailable to use file storage
            with patch.object(key_manager, 'is_keyring_available', return_value=False):
                # Create provider and encrypt some data
                provider = EncryptionProviderFactory.create_provider("aes256", key_manager=key_manager)
                
                original_data = {"sensitive": "data", "timestamp": 1234567890}
                encrypted_with_old_key = provider.encrypt(original_data)
                
                # Verify we can decrypt with current key
                assert provider.decrypt(encrypted_with_old_key) == original_data
                
                # Rotate the key
                old_key, new_key = key_manager.rotate_key()
                assert old_key is not None
                assert new_key is not None
                assert old_key != new_key
                
                # Create new provider instance (simulating restart)
                new_provider = EncryptionProviderFactory.create_provider("aes256", key_manager=key_manager)
                
                # Should be able to encrypt new data with new key
                new_data = {"new": "data"}
                encrypted_with_new_key = new_provider.encrypt(new_data)
                assert new_provider.decrypt(encrypted_with_new_key) == new_data
                
                # Old encrypted data should not decrypt with new key
                # (This would require a migration process in real usage)
                with pytest.raises(Exception):  # Should fail with padding or decryption error
                    new_provider.decrypt(encrypted_with_old_key)
    
    def test_factory_provider_availability(self):
        """Test that factory correctly reports available providers."""
        available_providers = EncryptionProviderFactory.get_available_providers()
        
        # Should have both none and aes256
        assert "none" in available_providers
        assert "aes256" in available_providers
        
        # Test creating each available provider
        none_provider = EncryptionProviderFactory.create_provider("none")
        assert none_provider.get_encryption_type() == "none"
        assert none_provider.is_available() is True
        
        # AES provider requires key manager
        with tempfile.TemporaryDirectory() as temp_dir:
            key_manager = FallbackKeyManager(fallback_dir=temp_dir)
            with patch.object(key_manager, 'is_keyring_available', return_value=False):
                aes_provider = EncryptionProviderFactory.create_provider("aes256", key_manager=key_manager)
                assert aes_provider.get_encryption_type() == "aes256"
                assert aes_provider.is_available() is True
    
    def test_configuration_validation(self):
        """Test configuration validation for different provider types."""
        # None provider should always validate
        assert EncryptionProviderFactory.validate_provider_config("none", {}) is True
        assert EncryptionProviderFactory.validate_provider_config("none", {"any": "config"}) is True
        
        # AES provider should validate when dependencies are available
        assert EncryptionProviderFactory.validate_provider_config("aes256", {}) is True
        assert EncryptionProviderFactory.validate_provider_config("aes256", {"key_manager": "config"}) is True
        
        # Unknown provider should not validate
        assert EncryptionProviderFactory.validate_provider_config("unknown", {}) is False
    
    def test_error_handling_consistency(self):
        """Test that error handling is consistent across the infrastructure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            key_manager = FallbackKeyManager(fallback_dir=temp_dir)
            
            with patch.object(key_manager, 'is_keyring_available', return_value=False):
                provider = EncryptionProviderFactory.create_provider("aes256", key_manager=key_manager)
                
                # Test encryption error with non-serializable data
                class NonSerializable:
                    pass
                
                from src.awsideman.encryption.provider import EncryptionError
                
                with pytest.raises(EncryptionError) as exc_info:
                    provider.encrypt(NonSerializable())
                
                error = exc_info.value
                assert error.encryption_type == "aes256"
                assert "Failed to serialize data for encryption" in str(error)
                
                # Test decryption error with invalid data
                with pytest.raises(EncryptionError) as exc_info:
                    provider.decrypt(b"invalid")
                
                error = exc_info.value
                assert error.encryption_type == "aes256"
                assert "too short to contain IV" in str(error)
    
    def test_performance_characteristics(self):
        """Test basic performance characteristics of encryption."""
        import time
        
        with tempfile.TemporaryDirectory() as temp_dir:
            key_manager = FallbackKeyManager(fallback_dir=temp_dir)
            
            with patch.object(key_manager, 'is_keyring_available', return_value=False):
                provider = EncryptionProviderFactory.create_provider("aes256", key_manager=key_manager)
                
                # Test with various data sizes
                test_data = {
                    "small": {"key": "value"},
                    "medium": {"data": "x" * 1000},
                    "large": {"items": [{"id": i, "data": "x" * 100} for i in range(100)]}
                }
                
                for size_name, data in test_data.items():
                    # Measure encryption time
                    start_time = time.time()
                    encrypted = provider.encrypt(data)
                    encrypt_time = time.time() - start_time
                    
                    # Measure decryption time
                    start_time = time.time()
                    decrypted = provider.decrypt(encrypted)
                    decrypt_time = time.time() - start_time
                    
                    # Verify correctness
                    assert decrypted == data
                    
                    # Basic performance check (should be fast for test data)
                    assert encrypt_time < 1.0, f"Encryption too slow for {size_name} data: {encrypt_time}s"
                    assert decrypt_time < 1.0, f"Decryption too slow for {size_name} data: {decrypt_time}s"
    
    def test_security_properties(self):
        """Test basic security properties of the encryption."""
        with tempfile.TemporaryDirectory() as temp_dir:
            key_manager = FallbackKeyManager(fallback_dir=temp_dir)
            
            with patch.object(key_manager, 'is_keyring_available', return_value=False):
                provider = EncryptionProviderFactory.create_provider("aes256", key_manager=key_manager)
                
                data = {"secret": "sensitive_information"}
                
                # Test that same data produces different ciphertext (due to random IV)
                encrypted1 = provider.encrypt(data)
                encrypted2 = provider.encrypt(data)
                
                assert encrypted1 != encrypted2, "Same plaintext should produce different ciphertext"
                
                # But both should decrypt to same data
                assert provider.decrypt(encrypted1) == data
                assert provider.decrypt(encrypted2) == data
                
                # Test that ciphertext doesn't contain plaintext
                plaintext_str = str(data)
                assert plaintext_str.encode() not in encrypted1
                assert plaintext_str.encode() not in encrypted2
                
                # Test that small changes in ciphertext cause decryption failure
                corrupted = bytearray(encrypted1)
                corrupted[20] = (corrupted[20] + 1) % 256  # Flip one bit
                
                from src.awsideman.encryption.provider import EncryptionError
                with pytest.raises(EncryptionError):
                    provider.decrypt(bytes(corrupted))