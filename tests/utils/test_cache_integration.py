"""Integration tests for advanced cache features."""

import json
import tempfile
import time
from unittest.mock import patch

import pytest

from src.awsideman.cache.backends.file import FileBackend
from src.awsideman.cache.config import AdvancedCacheConfig
from src.awsideman.cache.factory import BackendFactory
from src.awsideman.encryption.key_manager import FallbackKeyManager
from src.awsideman.encryption.provider import EncryptionProviderFactory


class TestCacheIntegration:
    """Integration tests for cache system components."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_file_backend_with_no_encryption_integration(self):
        """Test file backend with no encryption end-to-end."""
        # Create configuration
        config = AdvancedCacheConfig(
            backend_type="file", encryption_enabled=False, file_cache_dir=self.temp_dir
        )

        # Create backend
        backend = BackendFactory.create_backend(config)

        # Create encryption provider
        encryption = EncryptionProviderFactory.create_provider("none")

        # Test data
        test_data = {
            "users": [
                {"id": 1, "name": "Alice", "active": True},
                {"id": 2, "name": "Bob", "active": False},
            ],
            "metadata": {"total": 2, "page": 1},
        }

        # Encrypt data
        encrypted_data = encryption.encrypt(test_data)

        # Store in backend
        backend.set("test_key", encrypted_data, ttl=3600, operation="test_operation")

        # Retrieve from backend
        retrieved_data = backend.get("test_key")
        assert retrieved_data is not None

        # Decrypt data
        decrypted_data = encryption.decrypt(retrieved_data)

        # Verify data integrity
        assert decrypted_data == test_data

        # Test backend stats
        stats = backend.get_stats()
        assert stats["backend_type"] == "file"
        assert stats["valid_entries"] == 1

        # Test health check
        assert backend.health_check() is True

    def test_file_backend_with_aes_encryption_integration(self):
        """Test file backend with AES encryption end-to-end."""
        # Create configuration
        config = AdvancedCacheConfig(
            backend_type="file",
            encryption_enabled=True,
            encryption_type="aes256",
            file_cache_dir=self.temp_dir,
        )

        # Create backend
        backend = BackendFactory.create_backend(config)

        # Create key manager (using fallback for testing)
        key_manager = FallbackKeyManager(fallback_dir=self.temp_dir)

        # Create encryption provider
        encryption = EncryptionProviderFactory.create_provider("aes256", key_manager=key_manager)

        # Test data
        test_data = {
            "sensitive": "data",
            "credentials": {"username": "test", "token": "secret123"},
            "numbers": [1, 2, 3, 4, 5],
        }

        # Encrypt data
        encrypted_data = encryption.encrypt(test_data)

        # Verify data is actually encrypted (not readable as JSON)
        with pytest.raises((json.JSONDecodeError, UnicodeDecodeError)):
            json.loads(encrypted_data.decode("utf-8"))

        # Store in backend
        backend.set("encrypted_key", encrypted_data, ttl=1800, operation="secure_operation")

        # Retrieve from backend
        retrieved_data = backend.get("encrypted_key")
        assert retrieved_data is not None

        # Decrypt data
        decrypted_data = encryption.decrypt(retrieved_data)

        # Verify data integrity
        assert decrypted_data == test_data

        # Test that different encryption instances with same key can decrypt
        key_manager2 = FallbackKeyManager(fallback_dir=self.temp_dir)
        encryption2 = EncryptionProviderFactory.create_provider("aes256", key_manager=key_manager2)

        decrypted_data2 = encryption2.decrypt(retrieved_data)
        assert decrypted_data2 == test_data

    def test_cache_manager_integration_with_file_backend(self):
        """Test CacheManager integration with file backend."""
        # Create configuration
        config = AdvancedCacheConfig(
            enabled=True,
            backend_type="file",
            encryption_enabled=False,
            default_ttl=3600,
            operation_ttls={"list_users": 1800, "get_account": 7200},
            file_cache_dir=self.temp_dir,
        )

        # Create cache manager (would normally be done by the application)
        # For this test, we'll create the components manually
        backend = BackendFactory.create_backend(config)
        encryption = EncryptionProviderFactory.create_provider("none")

        # Test data for different operations
        test_cases = [
            ("list_users", {"users": ["alice", "bob", "charlie"]}, 1800),
            ("get_account", {"account_id": "123", "name": "Test Account"}, 7200),
            ("unknown_op", {"data": "unknown"}, 3600),
        ]

        for operation, data, expected_ttl in test_cases:
            cache_key = f"{operation}_test"

            # Encrypt and store
            encrypted_data = encryption.encrypt(data)
            backend.set(cache_key, encrypted_data, ttl=expected_ttl, operation=operation)

            # Retrieve and decrypt
            retrieved_data = backend.get(cache_key)
            assert retrieved_data is not None

            decrypted_data = encryption.decrypt(retrieved_data)
            assert decrypted_data == data

        # Test cache statistics
        stats = backend.get_stats()
        assert stats["valid_entries"] == 3
        assert stats["expired_entries"] == 0
        assert stats["corrupted_entries"] == 0

    def test_cache_expiration_integration(self):
        """Test cache expiration behavior integration."""
        config = AdvancedCacheConfig(
            backend_type="file", encryption_enabled=False, file_cache_dir=self.temp_dir
        )

        backend = BackendFactory.create_backend(config)
        encryption = EncryptionProviderFactory.create_provider("none")

        # Test data with short TTL
        test_data = {"expires": "soon"}
        encrypted_data = encryption.encrypt(test_data)

        # Store with 1 second TTL
        backend.set("expiring_key", encrypted_data, ttl=1, operation="test_expiration")

        # Should be available immediately
        retrieved_data = backend.get("expiring_key")
        assert retrieved_data is not None

        decrypted_data = encryption.decrypt(retrieved_data)
        assert decrypted_data == test_data

        # Wait for expiration
        time.sleep(1.1)

        # Should be expired and removed
        expired_data = backend.get("expiring_key")
        assert expired_data is None

        # Stats should reflect the removal
        stats = backend.get_stats()
        assert stats["valid_entries"] == 0

    def test_cache_invalidation_integration(self):
        """Test cache invalidation integration."""
        config = AdvancedCacheConfig(
            backend_type="file", encryption_enabled=False, file_cache_dir=self.temp_dir
        )

        backend = BackendFactory.create_backend(config)
        encryption = EncryptionProviderFactory.create_provider("none")

        # Store multiple entries
        test_entries = [("key1", {"data": 1}), ("key2", {"data": 2}), ("key3", {"data": 3})]

        for key, data in test_entries:
            encrypted_data = encryption.encrypt(data)
            backend.set(key, encrypted_data, ttl=3600, operation="test_invalidation")

        # Verify all entries exist
        for key, data in test_entries:
            retrieved_data = backend.get(key)
            assert retrieved_data is not None
            decrypted_data = encryption.decrypt(retrieved_data)
            assert decrypted_data == data

        # Invalidate specific key
        backend.invalidate("key2")

        # Verify key2 is gone, others remain
        assert backend.get("key1") is not None
        assert backend.get("key2") is None
        assert backend.get("key3") is not None

        # Invalidate all remaining
        backend.invalidate()

        # Verify all are gone
        for key, _ in test_entries:
            assert backend.get(key) is None

    def test_encryption_key_rotation_integration(self):
        """Test encryption key rotation integration."""
        config = AdvancedCacheConfig(
            backend_type="file", encryption_enabled=True, file_cache_dir=self.temp_dir
        )

        backend = BackendFactory.create_backend(config)

        # Create key manager
        key_manager = FallbackKeyManager(fallback_dir=self.temp_dir)
        encryption = EncryptionProviderFactory.create_provider("aes256", key_manager=key_manager)

        # Store data with original key
        original_data = {"original": "data", "sensitive": True}
        encrypted_data = encryption.encrypt(original_data)
        backend.set("rotation_test", encrypted_data, ttl=3600, operation="key_rotation")

        # Verify data can be retrieved
        retrieved_data = backend.get("rotation_test")
        decrypted_data = encryption.decrypt(retrieved_data)
        assert decrypted_data == original_data

        # Rotate key
        old_key, new_key = key_manager.rotate_key()
        assert old_key is not None
        assert new_key is not None
        assert old_key != new_key

        # Create new encryption instance with rotated key
        new_encryption = EncryptionProviderFactory.create_provider(
            "aes256", key_manager=key_manager
        )

        # Old encrypted data should not be decryptable with new key
        with pytest.raises(Exception):  # Should fail to decrypt
            new_encryption.decrypt(encrypted_data)

        # But new data encrypted with new key should work
        new_data = {"rotated": "key_data"}
        new_encrypted_data = new_encryption.encrypt(new_data)
        backend.set("new_key_test", new_encrypted_data, ttl=3600, operation="new_key")

        retrieved_new_data = backend.get("new_key_test")
        decrypted_new_data = new_encryption.decrypt(retrieved_new_data)
        assert decrypted_new_data == new_data

    def test_backend_health_check_integration(self):
        """Test backend health check integration."""
        config = AdvancedCacheConfig(backend_type="file", file_cache_dir=self.temp_dir)

        backend = BackendFactory.create_backend(config)

        # Health check should pass for accessible directory
        assert backend.health_check() is True

        # Get detailed health status
        if hasattr(backend, "get_detailed_health_status"):
            status = backend.get_detailed_health_status()
            assert status.is_healthy is True
            assert status.backend_type == "file"
            assert status.response_time_ms is not None
            assert status.response_time_ms >= 0

    def test_configuration_loading_integration(self):
        """Test configuration loading integration."""
        # Test loading from environment variables
        import os

        env_vars = {
            "AWSIDEMAN_CACHE_ENABLED": "true",
            "AWSIDEMAN_CACHE_BACKEND": "file",
            "AWSIDEMAN_CACHE_ENCRYPTION": "false",
            "AWSIDEMAN_CACHE_TTL_DEFAULT": "7200",
            "AWSIDEMAN_CACHE_TTL_LIST_USERS": "1800",
            "AWSIDEMAN_CACHE_FILE_DIR": self.temp_dir,
        }

        with patch.dict(os.environ, env_vars, clear=True):
            config = AdvancedCacheConfig.from_environment()

            assert config.enabled is True
            assert config.backend_type == "file"
            assert config.encryption_enabled is False
            assert config.default_ttl == 7200
            assert config.operation_ttls == {"list_users": 1800}
            assert config.file_cache_dir == self.temp_dir

            # Test that configuration can be used to create working backend
            backend = BackendFactory.create_backend(config)
            assert isinstance(backend, FileBackend)
            assert backend.health_check() is True

    def test_error_handling_integration(self):
        """Test error handling integration across components."""
        # Test with invalid cache directory
        config = AdvancedCacheConfig(backend_type="file", file_cache_dir="/invalid/readonly/path")

        # Backend creation should fail gracefully
        with pytest.raises(Exception):  # Should raise CacheBackendError
            BackendFactory.create_backend(config)

        # Test fallback behavior
        fallback_backend = BackendFactory.create_backend_with_fallback(config)
        # Should fall back to default directory and work
        assert fallback_backend.health_check() is True

    def test_large_data_integration(self):
        """Test handling of large data integration."""
        config = AdvancedCacheConfig(
            backend_type="file", encryption_enabled=True, file_cache_dir=self.temp_dir
        )

        backend = BackendFactory.create_backend(config)
        key_manager = FallbackKeyManager(fallback_dir=self.temp_dir)
        encryption = EncryptionProviderFactory.create_provider("aes256", key_manager=key_manager)

        # Create large data structure
        large_data = {
            "items": [
                {
                    "id": i,
                    "name": f"Item {i}",
                    "description": "x" * 1000,  # 1KB per item
                    "metadata": {"created": f"2023-01-{i:02d}", "active": True},
                }
                for i in range(100)  # ~100KB total
            ],
            "summary": {
                "total_items": 100,
                "total_size": "~100KB",
                "created_at": "2023-01-01T00:00:00Z",
            },
        }

        # Encrypt and store
        encrypted_data = encryption.encrypt(large_data)
        backend.set("large_data_key", encrypted_data, ttl=3600, operation="large_data_test")

        # Retrieve and decrypt
        retrieved_data = backend.get("large_data_key")
        assert retrieved_data is not None

        decrypted_data = encryption.decrypt(retrieved_data)
        assert decrypted_data == large_data

        # Verify stats reflect the large entry
        stats = backend.get_stats()
        assert stats["valid_entries"] == 1
        assert stats["total_size_bytes"] > 100000  # Should be > 100KB

    def test_concurrent_access_simulation(self):
        """Test concurrent access patterns simulation."""
        config = AdvancedCacheConfig(
            backend_type="file", encryption_enabled=False, file_cache_dir=self.temp_dir
        )

        backend = BackendFactory.create_backend(config)
        encryption = EncryptionProviderFactory.create_provider("none")

        # Simulate concurrent writes and reads
        test_data = [
            (f"concurrent_key_{i}", {"worker_id": i, "data": f"data_{i}"}) for i in range(10)
        ]

        # Write all data
        for key, data in test_data:
            encrypted_data = encryption.encrypt(data)
            backend.set(key, encrypted_data, ttl=3600, operation="concurrent_test")

        # Read all data back
        for key, expected_data in test_data:
            retrieved_data = backend.get(key)
            assert retrieved_data is not None

            decrypted_data = encryption.decrypt(retrieved_data)
            assert decrypted_data == expected_data

        # Verify all entries are present
        stats = backend.get_stats()
        assert stats["valid_entries"] == 10
        assert stats["corrupted_entries"] == 0

    def test_mixed_encryption_types_integration(self):
        """Test integration with mixed encryption types."""
        config = AdvancedCacheConfig(backend_type="file", file_cache_dir=self.temp_dir)

        backend = BackendFactory.create_backend(config)

        # Test with no encryption
        no_encryption = EncryptionProviderFactory.create_provider("none")
        plain_data = {"type": "plain", "encrypted": False}
        plain_encrypted = no_encryption.encrypt(plain_data)
        backend.set("plain_key", plain_encrypted, ttl=3600, operation="plain_test")

        # Test with AES encryption
        key_manager = FallbackKeyManager(fallback_dir=self.temp_dir)
        aes_encryption = EncryptionProviderFactory.create_provider(
            "aes256", key_manager=key_manager
        )
        encrypted_data = {"type": "encrypted", "encrypted": True}
        aes_encrypted = aes_encryption.encrypt(encrypted_data)
        backend.set("encrypted_key", aes_encrypted, ttl=3600, operation="encrypted_test")

        # Retrieve and verify both types
        plain_retrieved = backend.get("plain_key")
        plain_decrypted = no_encryption.decrypt(plain_retrieved)
        assert plain_decrypted == plain_data

        encrypted_retrieved = backend.get("encrypted_key")
        encrypted_decrypted = aes_encryption.decrypt(encrypted_retrieved)
        assert encrypted_decrypted == encrypted_data

        # Verify cross-decryption fails appropriately
        with pytest.raises(Exception):
            # Should fail to decrypt AES data with no encryption
            no_encryption.decrypt(encrypted_retrieved)

        with pytest.raises(Exception):
            # Should fail to decrypt plain data with AES
            aes_encryption.decrypt(plain_retrieved)
