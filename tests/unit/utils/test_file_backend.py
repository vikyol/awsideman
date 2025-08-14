"""Tests for file backend implementation."""

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from src.awsideman.cache.backends.base import CacheBackendError
from src.awsideman.cache.backends.file import FileBackend


class TestFileBackend:
    """Test cases for file backend."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.backend = FileBackend(cache_dir=self.temp_dir)

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_init_with_custom_cache_dir(self):
        """Test backend initialization with custom cache directory."""
        backend = FileBackend(cache_dir=self.temp_dir)
        assert backend.backend_type == "file"
        assert str(self.temp_dir) in str(backend.path_manager.get_cache_directory())

    def test_init_with_default_cache_dir(self):
        """Test backend initialization with default cache directory."""
        backend = FileBackend()
        assert backend.backend_type == "file"
        # Should use default cache directory
        cache_dir = backend.path_manager.get_cache_directory()
        assert cache_dir.name == "cache"

    def test_init_directory_creation_error(self):
        """Test initialization error when cache directory cannot be created."""
        with patch.object(Path, "mkdir", side_effect=PermissionError("Access denied")):
            with pytest.raises(CacheBackendError) as exc_info:
                FileBackend(cache_dir="/invalid/path")

            assert "Failed to initialize file backend" in str(exc_info.value)
            assert exc_info.value.backend_type == "file"

    def test_get_cache_miss(self):
        """Test get operation when cache file doesn't exist."""
        result = self.backend.get("nonexistent_key")
        assert result is None

    def test_set_and_get_plain_json_data(self):
        """Test set and get operations with plain JSON data."""
        test_data = {"key": "value", "number": 42}
        json_bytes = json.dumps(test_data).encode("utf-8")

        self.backend.set("test_key", json_bytes, ttl=3600, operation="test_op")

        result = self.backend.get("test_key")
        assert result is not None

        # Should return the same JSON data as bytes
        retrieved_data = json.loads(result.decode("utf-8"))
        assert retrieved_data == test_data

    def test_set_and_get_encrypted_data(self):
        """Test set and get operations with encrypted (binary) data."""
        # Simulate encrypted data (non-UTF8 bytes)
        encrypted_data = b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a"  # PNG header as example binary

        self.backend.set("encrypted_key", encrypted_data, ttl=1800, operation="encrypt_op")

        result = self.backend.get("encrypted_key")
        assert result == encrypted_data

    def test_get_expired_entry_removed(self):
        """Test that expired entries are automatically removed."""
        # Create an expired cache file manually
        cache_file = self.backend.path_manager.get_cache_file_path("expired_key")
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        expired_entry = {
            "data": {"test": "expired"},
            "created_at": time.time() - 7200,  # 2 hours ago
            "ttl": 3600,  # 1 hour TTL (expired)
            "key": "expired_key",
            "operation": "test_op",
        }

        with open(cache_file, "w") as f:
            json.dump(expired_entry, f)

        # Should return None and remove the file
        result = self.backend.get("expired_key")
        assert result is None
        assert not cache_file.exists()

    def test_get_corrupted_file_handled(self):
        """Test handling of corrupted cache files."""
        # Create a corrupted cache file
        cache_file = self.backend.path_manager.get_cache_file_path("corrupted_key")
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        with open(cache_file, "w") as f:
            f.write("invalid json content {")

        # Should return None and remove the corrupted file
        result = self.backend.get("corrupted_key")
        assert result is None
        assert not cache_file.exists()

    def test_get_missing_required_fields(self):
        """Test handling of cache files with missing required fields."""
        cache_file = self.backend.path_manager.get_cache_file_path("invalid_key")
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        invalid_entry = {
            "data": {"test": "data"},
            # Missing required fields: created_at, ttl, key, operation
        }

        with open(cache_file, "w") as f:
            json.dump(invalid_entry, f)

        result = self.backend.get("invalid_key")
        assert result is None
        assert not cache_file.exists()

    def test_set_with_custom_ttl(self):
        """Test set operation with custom TTL."""
        test_data = json.dumps({"custom": "ttl"}).encode("utf-8")
        custom_ttl = 1800

        self.backend.set("ttl_key", test_data, ttl=custom_ttl, operation="test_op")

        # Verify TTL was set correctly by reading the file
        cache_file = self.backend.path_manager.get_cache_file_path("ttl_key")
        with open(cache_file, "r") as f:
            stored_data = json.load(f)

        assert stored_data["ttl"] == custom_ttl

    def test_set_with_default_ttl(self):
        """Test set operation with default TTL."""
        test_data = json.dumps({"default": "ttl"}).encode("utf-8")

        self.backend.set("default_ttl_key", test_data, operation="test_op")

        # Verify default TTL was used
        cache_file = self.backend.path_manager.get_cache_file_path("default_ttl_key")
        with open(cache_file, "r") as f:
            stored_data = json.load(f)

        assert stored_data["ttl"] == 3600  # Default TTL

    def test_set_atomic_write(self):
        """Test that set operation uses atomic writes."""
        test_data = json.dumps({"atomic": "write"}).encode("utf-8")

        with patch.object(Path, "rename") as mock_rename:
            self.backend.set("atomic_key", test_data, operation="test_op")

            # Verify atomic rename was called
            mock_rename.assert_called_once()

    def test_set_permission_error(self):
        """Test set operation with permission error."""
        test_data = json.dumps({"permission": "error"}).encode("utf-8")

        with patch("builtins.open", side_effect=PermissionError("Access denied")):
            with pytest.raises(CacheBackendError) as exc_info:
                self.backend.set("permission_key", test_data, operation="test_op")

            assert "Permission denied writing cache file" in str(exc_info.value)
            assert exc_info.value.backend_type == "file"

    def test_set_disk_full_error(self):
        """Test set operation with disk full error."""
        test_data = json.dumps({"disk": "full"}).encode("utf-8")

        with patch("builtins.open", side_effect=OSError("No space left on device")):
            with pytest.raises(CacheBackendError) as exc_info:
                self.backend.set("disk_full_key", test_data, operation="test_op")

            assert "Disk full" in str(exc_info.value)
            assert exc_info.value.backend_type == "file"

    def test_set_invalid_data_error(self):
        """Test set operation with invalid data that cannot be processed."""
        # Create data that looks like JSON but will cause processing errors
        invalid_data = b"not valid json or encrypted data"

        # This should still work as it will be treated as encrypted data
        self.backend.set("invalid_data_key", invalid_data, operation="test_op")

        result = self.backend.get("invalid_data_key")
        assert result == invalid_data

    def test_invalidate_specific_key(self):
        """Test invalidating a specific cache key."""
        # Set some data first
        test_data = json.dumps({"to": "invalidate"}).encode("utf-8")
        self.backend.set("invalidate_key", test_data, operation="test_op")

        # Verify it exists
        assert self.backend.get("invalidate_key") is not None

        # Invalidate it
        self.backend.invalidate("invalidate_key")

        # Verify it's gone
        assert self.backend.get("invalidate_key") is None

    def test_invalidate_all_keys(self):
        """Test invalidating all cache keys."""
        # Set multiple entries
        for i in range(3):
            test_data = json.dumps({"data": i}).encode("utf-8")
            self.backend.set(f"key_{i}", test_data, operation="test_op")

        # Verify all exist
        for i in range(3):
            assert self.backend.get(f"key_{i}") is not None

        # Invalidate all
        self.backend.invalidate()

        # Verify all are gone
        for i in range(3):
            assert self.backend.get(f"key_{i}") is None

    def test_invalidate_permission_error(self):
        """Test invalidate operation with permission error."""
        with patch.object(
            self.backend.path_manager,
            "delete_cache_file",
            side_effect=PermissionError("Access denied"),
        ):
            with pytest.raises(CacheBackendError) as exc_info:
                self.backend.invalidate("permission_key")

            assert "Permission denied invalidating cache" in str(exc_info.value)
            assert exc_info.value.backend_type == "file"

    def test_get_stats_empty_cache(self):
        """Test get_stats with empty cache."""
        stats = self.backend.get_stats()

        assert stats["backend_type"] == "file"
        assert stats["total_entries"] == 0
        assert stats["valid_entries"] == 0
        assert stats["expired_entries"] == 0
        assert stats["corrupted_entries"] == 0
        assert stats["total_size_bytes"] >= 0
        assert "cache_directory" in stats

    def test_get_stats_with_valid_entries(self):
        """Test get_stats with valid cache entries."""
        # Add some valid entries
        for i in range(3):
            test_data = json.dumps({"data": i}).encode("utf-8")
            self.backend.set(f"valid_key_{i}", test_data, operation="test_op")

        stats = self.backend.get_stats()

        assert stats["total_entries"] == 3
        assert stats["valid_entries"] == 3
        assert stats["expired_entries"] == 0
        assert stats["corrupted_entries"] == 0
        assert stats["total_size_bytes"] > 0

    def test_get_stats_with_expired_entries(self):
        """Test get_stats with expired cache entries."""
        # Create expired entry manually
        cache_file = self.backend.path_manager.get_cache_file_path("expired_stats_key")
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        expired_entry = {
            "data": {"test": "expired"},
            "created_at": time.time() - 7200,  # 2 hours ago
            "ttl": 3600,  # 1 hour TTL (expired)
            "key": "expired_stats_key",
            "operation": "test_op",
        }

        with open(cache_file, "w") as f:
            json.dump(expired_entry, f)

        stats = self.backend.get_stats()

        assert stats["total_entries"] == 1
        assert stats["valid_entries"] == 0
        assert stats["expired_entries"] == 1
        assert stats["corrupted_entries"] == 0

    def test_get_stats_with_corrupted_entries(self):
        """Test get_stats with corrupted cache entries."""
        # Create corrupted entry
        cache_file = self.backend.path_manager.get_cache_file_path("corrupted_stats_key")
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        with open(cache_file, "w") as f:
            f.write("invalid json {")

        stats = self.backend.get_stats()

        assert stats["total_entries"] == 1
        assert stats["valid_entries"] == 0
        assert stats["expired_entries"] == 0
        assert stats["corrupted_entries"] == 1
        assert "warning" in stats

    def test_get_stats_error_handling(self):
        """Test get_stats error handling."""
        with patch.object(
            self.backend.path_manager, "list_cache_files", side_effect=Exception("Stats error")
        ):
            with pytest.raises(CacheBackendError) as exc_info:
                self.backend.get_stats()

            assert "Error getting backend stats" in str(exc_info.value)
            assert exc_info.value.backend_type == "file"

    def test_health_check_success(self):
        """Test successful health check."""
        result = self.backend.health_check()
        assert result is True

    def test_health_check_directory_creation(self):
        """Test health check creates directory if it doesn't exist."""
        # Remove the cache directory
        import shutil

        shutil.rmtree(self.temp_dir)

        result = self.backend.health_check()
        assert result is True
        assert Path(self.temp_dir).exists()

    def test_health_check_permission_error(self):
        """Test health check with permission error."""
        with patch.object(Path, "write_text", side_effect=PermissionError("Access denied")):
            result = self.backend.health_check()
            assert result is False

    def test_health_check_unexpected_error(self):
        """Test health check with unexpected error."""
        with patch.object(
            self.backend.path_manager,
            "get_cache_directory",
            side_effect=Exception("Unexpected error"),
        ):
            result = self.backend.health_check()
            assert result is False

    def test_get_detailed_health_status_success(self):
        """Test detailed health status when healthy."""
        status = self.backend.get_detailed_health_status()

        assert status.is_healthy is True
        assert status.backend_type == "file"
        assert "healthy and accessible" in status.message
        assert status.response_time_ms is not None
        assert status.response_time_ms >= 0
        assert status.error is None

    def test_get_detailed_health_status_failure(self):
        """Test detailed health status when unhealthy."""
        with patch.object(Path, "write_text", side_effect=PermissionError("Access denied")):
            status = self.backend.get_detailed_health_status()

            assert status.is_healthy is False
            assert status.backend_type == "file"
            assert "Cannot write to cache directory" in status.message
            assert status.response_time_ms is not None
            assert status.error is not None

    def test_encrypted_format_detection(self):
        """Test detection and handling of encrypted format files."""
        # Create a file in encrypted format
        cache_file = self.backend.path_manager.get_cache_file_path("encrypted_format_key")
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        # Create encrypted format: [4 bytes length][metadata JSON][encrypted data]
        metadata = {
            "encrypted": True,
            "created_at": time.time(),
            "ttl": 3600,
            "key": "encrypted_format_key",
            "operation": "test_op",
            "data_size": 10,
        }

        metadata_json = json.dumps(metadata).encode("utf-8")
        metadata_length = len(metadata_json)
        encrypted_data = b"fake_encrypted_data"

        with open(cache_file, "wb") as f:
            f.write(metadata_length.to_bytes(4, byteorder="big"))
            f.write(metadata_json)
            f.write(encrypted_data)

        # Should return the encrypted data portion
        result = self.backend.get("encrypted_format_key")
        assert result == encrypted_data

    def test_encrypted_format_expired(self):
        """Test handling of expired encrypted format files."""
        cache_file = self.backend.path_manager.get_cache_file_path("expired_encrypted_key")
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        # Create expired encrypted format
        metadata = {
            "encrypted": True,
            "created_at": time.time() - 7200,  # 2 hours ago
            "ttl": 3600,  # 1 hour TTL (expired)
            "key": "expired_encrypted_key",
            "operation": "test_op",
            "data_size": 10,
        }

        metadata_json = json.dumps(metadata).encode("utf-8")
        metadata_length = len(metadata_json)
        encrypted_data = b"expired_data"

        with open(cache_file, "wb") as f:
            f.write(metadata_length.to_bytes(4, byteorder="big"))
            f.write(metadata_json)
            f.write(encrypted_data)

        # Should return None and remove the file
        result = self.backend.get("expired_encrypted_key")
        assert result is None
        assert not cache_file.exists()
