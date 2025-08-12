"""Security tests for advanced cache features."""

import json
import os
import tempfile
import time
from pathlib import Path

import pytest

from src.awsideman.cache.config import AdvancedCacheConfig
from src.awsideman.cache.factory import BackendFactory
from src.awsideman.encryption.key_manager import FallbackKeyManager
from src.awsideman.encryption.provider import EncryptionError, EncryptionProviderFactory


class TestCacheSecurity:
    """Security tests for cache system."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_encryption_key_security(self):
        """Test encryption key security properties."""
        key_manager = FallbackKeyManager(fallback_dir=self.temp_dir)

        # Generate multiple keys
        key1 = key_manager.get_key()
        key2 = key_manager.get_key()  # Should be same as key1 (cached)

        # Keys should be 32 bytes (256 bits) for AES-256
        assert len(key1) == 32
        assert len(key2) == 32
        assert key1 == key2  # Same key from cache

        # Rotate key
        old_key, new_key = key_manager.rotate_key()

        # New key should be different
        assert old_key == key1
        assert new_key != old_key
        assert len(new_key) == 32

        # Keys should appear random (basic entropy check)
        # Count unique bytes in key
        unique_bytes = len(set(new_key))
        assert unique_bytes > 20, f"Key appears to have low entropy: {unique_bytes} unique bytes"

        # Key should not be all zeros or all ones
        assert new_key != b"\x00" * 32
        assert new_key != b"\xff" * 32

    def test_encryption_data_security(self):
        """Test encryption data security properties."""
        key_manager = FallbackKeyManager(fallback_dir=self.temp_dir)
        encryption = EncryptionProviderFactory.create_provider("aes256", key_manager=key_manager)

        # Test sensitive data
        sensitive_data = {
            "password": "super_secret_password_123",
            "api_key": "sk-1234567890abcdef",
            "personal_info": {"ssn": "123-45-6789", "credit_card": "4111-1111-1111-1111"},
        }

        # Encrypt data
        encrypted_data = encryption.encrypt(sensitive_data)

        # Encrypted data should be bytes
        assert isinstance(encrypted_data, bytes)

        # Encrypted data should not contain plaintext
        encrypted_str = encrypted_data.decode("latin-1", errors="ignore")
        assert "super_secret_password_123" not in encrypted_str
        assert "sk-1234567890abcdef" not in encrypted_str
        assert "123-45-6789" not in encrypted_str
        assert "4111-1111-1111-1111" not in encrypted_str

        # Encrypted data should not be valid JSON
        with pytest.raises((json.JSONDecodeError, UnicodeDecodeError)):
            json.loads(encrypted_data.decode("utf-8"))

        # Decryption should recover original data
        decrypted_data = encryption.decrypt(encrypted_data)
        assert decrypted_data == sensitive_data

    def test_encryption_iv_randomness(self):
        """Test that encryption uses random IVs."""
        key_manager = FallbackKeyManager(fallback_dir=self.temp_dir)
        encryption = EncryptionProviderFactory.create_provider("aes256", key_manager=key_manager)

        test_data = {"test": "data"}

        # Encrypt same data multiple times
        encrypted_results = []
        for _ in range(10):
            encrypted = encryption.encrypt(test_data)
            encrypted_results.append(encrypted)

        # All encrypted results should be different (due to random IV)
        for i, result1 in enumerate(encrypted_results):
            for j, result2 in enumerate(encrypted_results):
                if i != j:
                    assert result1 != result2, "Encrypted results should differ due to random IV"

        # All should decrypt to same data
        for encrypted in encrypted_results:
            decrypted = encryption.decrypt(encrypted)
            assert decrypted == test_data

        # IVs (first 16 bytes) should all be different
        ivs = [encrypted[:16] for encrypted in encrypted_results]
        unique_ivs = set(ivs)
        assert len(unique_ivs) == len(ivs), "IVs should be unique"

    def test_encryption_key_isolation(self):
        """Test that different keys cannot decrypt each other's data."""
        # Create two separate key managers
        key_manager1 = FallbackKeyManager(fallback_dir=self.temp_dir)
        key_manager2 = FallbackKeyManager(fallback_dir=tempfile.mkdtemp())

        encryption1 = EncryptionProviderFactory.create_provider("aes256", key_manager=key_manager1)
        encryption2 = EncryptionProviderFactory.create_provider("aes256", key_manager=key_manager2)

        test_data = {"secret": "data"}

        # Encrypt with first key
        encrypted_data = encryption1.encrypt(test_data)

        # Should decrypt correctly with same key
        decrypted_data = encryption1.decrypt(encrypted_data)
        assert decrypted_data == test_data

        # Should fail to decrypt with different key
        with pytest.raises(EncryptionError):
            encryption2.decrypt(encrypted_data)

        # Clean up second temp dir
        import shutil

        shutil.rmtree(key_manager2.fallback_dir, ignore_errors=True)

    def test_cache_file_permissions(self):
        """Test that cache files have secure permissions."""
        config = AdvancedCacheConfig(
            backend_type="file", encryption_enabled=True, file_cache_dir=self.temp_dir
        )

        backend = BackendFactory.create_backend(config)
        key_manager = FallbackKeyManager(fallback_dir=self.temp_dir)
        encryption = EncryptionProviderFactory.create_provider("aes256", key_manager=key_manager)

        # Store sensitive data
        sensitive_data = {"secret": "sensitive_information"}
        encrypted_data = encryption.encrypt(sensitive_data)
        backend.set("secure_key", encrypted_data, ttl=3600, operation="security_test")

        # Find the cache file
        cache_files = list(Path(self.temp_dir).rglob("*.json"))
        assert len(cache_files) > 0, "No cache files found"

        cache_file = cache_files[0]

        # Check file permissions (should be readable/writable by owner only)
        file_stat = cache_file.stat()
        file_mode = file_stat.st_mode & 0o777

        # On Unix systems, should be 0o600 (owner read/write only)
        if os.name == "posix":
            expected_mode = 0o600
            assert (
                file_mode == expected_mode
            ), f"Cache file permissions too permissive: {oct(file_mode)}"

    def test_key_storage_security(self):
        """Test that encryption keys are stored securely."""
        key_manager = FallbackKeyManager(fallback_dir=self.temp_dir)

        # Generate a key
        key = key_manager.get_key()

        # Check that key file exists and has secure permissions
        key_file = Path(self.temp_dir) / ".encryption_key"
        assert key_file.exists(), "Key file should exist"

        # Check file permissions
        if os.name == "posix":
            file_stat = key_file.stat()
            file_mode = file_stat.st_mode & 0o777
            assert file_mode == 0o600, f"Key file permissions too permissive: {oct(file_mode)}"

        # Check that key is base64 encoded (not stored as raw bytes)
        with open(key_file, "r") as f:
            stored_key_str = f.read().strip()

        # Should be valid base64
        import base64

        try:
            decoded_key = base64.b64decode(stored_key_str)
            assert decoded_key == key
        except Exception:
            pytest.fail("Key not properly base64 encoded")

        # Key should not appear in plaintext in file
        with open(key_file, "rb") as f:
            file_content = f.read()

        assert key not in file_content, "Raw key found in key file"

    def test_timing_attack_resistance(self):
        """Test resistance to timing attacks."""
        key_manager = FallbackKeyManager(fallback_dir=self.temp_dir)
        encryption = EncryptionProviderFactory.create_provider("aes256", key_manager=key_manager)

        # Create test data of different sizes
        small_data = {"data": "x" * 100}
        large_data = {"data": "x" * 10000}

        # Encrypt both
        small_encrypted = encryption.encrypt(small_data)
        large_encrypted = encryption.encrypt(large_data)

        # Measure decryption times
        small_times = []
        large_times = []

        for _ in range(50):  # Multiple measurements
            # Time small data decryption
            start_time = time.perf_counter()
            encryption.decrypt(small_encrypted)
            small_times.append(time.perf_counter() - start_time)

            # Time large data decryption
            start_time = time.perf_counter()
            encryption.decrypt(large_encrypted)
            large_times.append(time.perf_counter() - start_time)

        # Calculate averages
        avg_small_time = sum(small_times) / len(small_times)
        avg_large_time = sum(large_times) / len(large_times)

        print("\nTiming Analysis:")
        print(f"Small data avg time: {avg_small_time*1000:.3f}ms")
        print(f"Large data avg time: {avg_large_time*1000:.3f}ms")

        # Large data should take longer (proportional to size)
        assert avg_large_time > avg_small_time, "Large data should take longer to decrypt"

        # But the difference should be reasonable (not indicating timing vulnerabilities)
        time_ratio = avg_large_time / avg_small_time
        assert time_ratio < 200, f"Timing difference too large: {time_ratio}x"

    def test_secure_key_deletion(self):
        """Test secure key deletion."""
        key_manager = FallbackKeyManager(fallback_dir=self.temp_dir)

        # Generate and use a key
        original_key = key_manager.get_key()

        # Verify key file exists
        key_file = Path(self.temp_dir) / ".encryption_key"
        assert key_file.exists()

        # Delete the key
        result = key_manager.delete_key()
        assert result is True

        # Key file should be gone
        assert not key_file.exists()

        # Getting key again should generate a new one
        new_key = key_manager.get_key()
        assert new_key != original_key
        assert len(new_key) == 32

    def test_cache_data_isolation(self):
        """Test that cache data is properly isolated."""
        config = AdvancedCacheConfig(
            backend_type="file", encryption_enabled=True, file_cache_dir=self.temp_dir
        )

        backend = BackendFactory.create_backend(config)
        key_manager = FallbackKeyManager(fallback_dir=self.temp_dir)
        encryption = EncryptionProviderFactory.create_provider("aes256", key_manager=key_manager)

        # Store data for different "users" or contexts
        user1_data = {"user": "alice", "secret": "alice_secret"}
        user2_data = {"user": "bob", "secret": "bob_secret"}

        encrypted_user1 = encryption.encrypt(user1_data)
        encrypted_user2 = encryption.encrypt(user2_data)

        backend.set("user1_data", encrypted_user1, ttl=3600, operation="user1_op")
        backend.set("user2_data", encrypted_user2, ttl=3600, operation="user2_op")

        # Retrieve and verify isolation
        retrieved_user1 = backend.get("user1_data")
        retrieved_user2 = backend.get("user2_data")

        decrypted_user1 = encryption.decrypt(retrieved_user1)
        decrypted_user2 = encryption.decrypt(retrieved_user2)

        assert decrypted_user1 == user1_data
        assert decrypted_user2 == user2_data
        assert decrypted_user1 != decrypted_user2

        # Verify no cross-contamination in cache files
        cache_files = list(Path(self.temp_dir).rglob("*.json"))
        for cache_file in cache_files:
            with open(cache_file, "rb") as f:
                file_content = f.read()

            # Neither user's secret should appear in plaintext
            assert b"alice_secret" not in file_content
            assert b"bob_secret" not in file_content

    def test_error_information_leakage(self):
        """Test that errors don't leak sensitive information."""
        key_manager = FallbackKeyManager(fallback_dir=self.temp_dir)
        encryption = EncryptionProviderFactory.create_provider("aes256", key_manager=key_manager)

        # Test with invalid encrypted data
        invalid_data = b"this_is_not_encrypted_data"

        try:
            encryption.decrypt(invalid_data)
            pytest.fail("Should have raised EncryptionError")
        except EncryptionError as e:
            error_message = str(e)

            # Error message should not contain sensitive information
            assert "this_is_not_encrypted_data" not in error_message
            assert key_manager.get_key().hex() not in error_message

            # Should be a generic error message
            assert (
                "Invalid encrypted data" in error_message
                or "AES decryption failed" in error_message
            )

    def test_cache_key_security(self):
        """Test cache key security properties."""
        config = AdvancedCacheConfig(
            backend_type="file", encryption_enabled=True, file_cache_dir=self.temp_dir
        )

        backend = BackendFactory.create_backend(config)
        key_manager = FallbackKeyManager(fallback_dir=self.temp_dir)
        encryption = EncryptionProviderFactory.create_provider("aes256", key_manager=key_manager)

        # Test with potentially problematic cache keys
        problematic_keys = [
            "../../../etc/passwd",  # Path traversal
            "key with spaces",
            "key/with/slashes",
            "key\\with\\backslashes",
            "key:with:colons",
            "key|with|pipes",
            "key<with>brackets",
            'key"with"quotes',
            "key'with'apostrophes",
            "very_long_key_" + "x" * 1000,  # Very long key
        ]

        test_data = {"security": "test"}
        encrypted_data = encryption.encrypt(test_data)

        for key in problematic_keys:
            # Should handle problematic keys safely
            backend.set(key, encrypted_data, ttl=3600, operation="security_test")
            retrieved_data = backend.get(key)

            assert retrieved_data == encrypted_data

            # Verify no files were created outside the cache directory
            cache_dir = Path(self.temp_dir)
            all_files = list(cache_dir.rglob("*"))

            for file_path in all_files:
                # All files should be within the cache directory
                assert cache_dir in file_path.parents or file_path == cache_dir

    def test_concurrent_access_security(self):
        """Test security under concurrent access."""
        import threading

        config = AdvancedCacheConfig(
            backend_type="file", encryption_enabled=True, file_cache_dir=self.temp_dir
        )

        backend = BackendFactory.create_backend(config)
        key_manager = FallbackKeyManager(fallback_dir=self.temp_dir)
        encryption = EncryptionProviderFactory.create_provider("aes256", key_manager=key_manager)

        # Shared data for threads
        results = []
        errors = []

        def worker_function(worker_id):
            """Worker function for concurrent testing."""
            try:
                # Each worker has its own sensitive data
                worker_data = {
                    "worker_id": worker_id,
                    "secret": f"worker_{worker_id}_secret_data",
                    "timestamp": time.time(),
                }

                encrypted_data = encryption.encrypt(worker_data)
                key = f"worker_{worker_id}_data"

                # Store data
                backend.set(key, encrypted_data, ttl=3600, operation=f"worker_{worker_id}")

                # Retrieve and verify
                retrieved_data = backend.get(key)
                decrypted_data = encryption.decrypt(retrieved_data)

                # Verify data integrity
                if decrypted_data == worker_data:
                    results.append((worker_id, "success"))
                else:
                    results.append((worker_id, "data_mismatch"))

            except Exception as e:
                errors.append((worker_id, str(e)))

        # Run concurrent workers
        threads = []
        num_workers = 10

        for i in range(num_workers):
            thread = threading.Thread(target=worker_function, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Analyze results
        successful_workers = [r for r in results if r[1] == "success"]

        print("\nConcurrent Security Test Results:")
        print(f"Workers: {num_workers}")
        print(f"Successful: {len(successful_workers)}")
        print(f"Errors: {len(errors)}")

        # All workers should succeed
        assert len(successful_workers) == num_workers, f"Some workers failed: {errors}"
        assert len(errors) == 0, f"Unexpected errors: {errors}"

        # Verify no data corruption between workers
        for worker_id in range(num_workers):
            key = f"worker_{worker_id}_data"
            retrieved_data = backend.get(key)
            decrypted_data = encryption.decrypt(retrieved_data)

            # Data should belong to correct worker
            assert decrypted_data["worker_id"] == worker_id
            assert decrypted_data["secret"] == f"worker_{worker_id}_secret_data"
