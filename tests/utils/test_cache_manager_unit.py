"""Comprehensive unit tests for CacheManager core functionality."""

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, mock_open, patch

from src.awsideman.cache.manager import CacheManager
from src.awsideman.cache.utils import CachePathManager
from src.awsideman.utils.models import CacheConfig, CacheEntry


class TestCacheManagerCore(unittest.TestCase):
    """Test core CacheManager functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.cache_config = CacheConfig(enabled=True, default_ttl=3600)
        self.cache_manager = CacheManager(config=self.cache_config, base_cache_dir=self.temp_dir)

    def test_init_with_config(self):
        """Test CacheManager initialization with provided config."""
        config = CacheConfig(enabled=False, default_ttl=1800)
        manager = CacheManager(config=config, base_cache_dir=self.temp_dir)

        self.assertEqual(manager.config, config)
        self.assertIsInstance(manager.path_manager, CachePathManager)

    def test_init_without_config(self):
        """Test CacheManager initialization without config loads from Config class."""
        with patch.object(CacheManager, "_load_cache_config") as mock_load:
            mock_config = CacheConfig(enabled=True, default_ttl=7200)
            mock_load.return_value = mock_config

            manager = CacheManager(base_cache_dir=self.temp_dir)

            mock_load.assert_called_once()
            self.assertEqual(manager.config, mock_config)

    def test_get_cache_miss(self):
        """Test get method with cache miss (file doesn't exist)."""
        result = self.cache_manager.get("nonexistent_key")
        self.assertIsNone(result)

    def test_get_cache_hit_valid(self):
        """Test get method with cache hit and valid (non-expired) entry."""
        # Create a valid cache entry
        test_data = {"test": "data", "number": 42}
        cache_key = "test_key"

        # Set the data first
        self.cache_manager.set(cache_key, test_data, operation="test_op")

        # Get the data back
        result = self.cache_manager.get(cache_key)

        self.assertEqual(result, test_data)

    def test_get_cache_hit_expired(self):
        """Test get method with cache hit but expired entry."""
        test_data = {"test": "expired_data"}
        cache_key = "expired_key"

        # Create an expired cache entry manually
        cache_file = self.cache_manager.path_manager.get_cache_file_path(cache_key)
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        expired_entry = {
            "data": test_data,
            "created_at": time.time() - 7200,  # 2 hours ago
            "ttl": 3600,  # 1 hour TTL (expired)
            "key": cache_key,
            "operation": "test_op",
        }

        with open(cache_file, "w") as f:
            json.dump(expired_entry, f)

        # Should return None for expired entry
        result = self.cache_manager.get(cache_key)
        self.assertIsNone(result)

        # Expired file should be removed
        self.assertFalse(cache_file.exists())

    def test_set_basic(self):
        """Test set method with basic data."""
        test_data = {"key": "value", "list": [1, 2, 3]}
        cache_key = "test_set_key"

        self.cache_manager.set(cache_key, test_data, operation="test_op")

        # Verify file was created
        cache_file = self.cache_manager.path_manager.get_cache_file_path(cache_key)
        self.assertTrue(cache_file.exists())

        # Verify content
        with open(cache_file, "r") as f:
            stored_data = json.load(f)

        self.assertEqual(stored_data["data"], test_data)
        self.assertEqual(stored_data["key"], cache_key)
        self.assertEqual(stored_data["operation"], "test_op")
        self.assertIsInstance(stored_data["created_at"], float)
        self.assertEqual(stored_data["ttl"], self.cache_config.default_ttl)

    def test_set_with_custom_ttl(self):
        """Test set method with custom TTL."""
        test_data = {"custom": "ttl_data"}
        cache_key = "custom_ttl_key"
        custom_ttl = 1800

        self.cache_manager.set(cache_key, test_data, ttl=custom_ttl, operation="test_op")

        # Verify TTL was set correctly
        cache_file = self.cache_manager.path_manager.get_cache_file_path(cache_key)
        with open(cache_file, "r") as f:
            stored_data = json.load(f)

        self.assertEqual(stored_data["ttl"], custom_ttl)

    def test_set_different_data_types(self):
        """Test set method with different JSON-serializable data types."""
        test_cases = [
            ("dict_key", {"test": "dict"}),
            ("list_key", [1, 2, 3, "string"]),
            ("string_key", "test string"),
            ("int_key", 42),
            ("float_key", 3.14),
            ("bool_key", True),
            ("null_key", None),
        ]

        for key, data in test_cases:
            with self.subTest(key=key, data=data):
                self.cache_manager.set(key, data, operation="test_op")
                result = self.cache_manager.get(key)
                self.assertEqual(result, data)

    def test_set_cache_disabled(self):
        """Test set method when cache is disabled."""
        self.cache_manager.config.enabled = False

        test_data = {"should": "not_be_cached"}
        cache_key = "disabled_key"

        self.cache_manager.set(cache_key, test_data, operation="test_op")

        # Verify no file was created
        cache_file = self.cache_manager.path_manager.get_cache_file_path(cache_key)
        self.assertFalse(cache_file.exists())

    def test_invalidate_specific_key(self):
        """Test invalidate method with specific key."""
        # Set some data first
        test_data = {"to": "invalidate"}
        cache_key = "invalidate_key"

        self.cache_manager.set(cache_key, test_data, operation="test_op")

        # Verify it exists
        self.assertIsNotNone(self.cache_manager.get(cache_key))

        # Invalidate it
        self.cache_manager.invalidate(cache_key)

        # Verify it's gone
        self.assertIsNone(self.cache_manager.get(cache_key))

    def test_invalidate_all_entries(self):
        """Test invalidate method with no key (clear all)."""
        # Set multiple entries
        test_data = [("key1", {"data": 1}), ("key2", {"data": 2}), ("key3", {"data": 3})]

        for key, data in test_data:
            self.cache_manager.set(key, data, operation="test_op")

        # Verify all exist
        for key, data in test_data:
            self.assertEqual(self.cache_manager.get(key), data)

        # Invalidate all
        self.cache_manager.invalidate()

        # Verify all are gone
        for key, _ in test_data:
            self.assertIsNone(self.cache_manager.get(key))

    def test_invalidate_cache_disabled(self):
        """Test invalidate method when cache is disabled."""
        self.cache_manager.config.enabled = False

        # Should not raise exception
        self.cache_manager.invalidate("some_key")
        self.cache_manager.invalidate()

    def test_is_expired_method(self):
        """Test _is_expired method."""
        current_time = time.time()

        # Non-expired entry
        valid_entry = CacheEntry(
            data={"test": "data"},
            created_at=current_time - 1800,  # 30 minutes ago
            ttl=3600,  # 1 hour TTL
            key="test_key",
            operation="test_op",
        )

        self.assertFalse(self.cache_manager._is_expired(valid_entry))

        # Expired entry
        expired_entry = CacheEntry(
            data={"test": "data"},
            created_at=current_time - 7200,  # 2 hours ago
            ttl=3600,  # 1 hour TTL
            key="test_key",
            operation="test_op",
        )

        self.assertTrue(self.cache_manager._is_expired(expired_entry))

    def test_load_cache_config_success(self):
        """Test _load_cache_config method with successful config loading."""
        mock_config_dict = {
            "enabled": True,
            "default_ttl": 7200,
            "operation_ttls": {"list_users": 1800},
            "max_size_mb": 200,
        }

        with patch("src.awsideman.cache.manager.Config") as mock_config_class:
            mock_config_instance = Mock()
            mock_config_instance.get_cache_config.return_value = mock_config_dict
            mock_config_class.return_value = mock_config_instance

            result = self.cache_manager._load_cache_config()

            self.assertIsInstance(result, CacheConfig)
            self.assertEqual(result.enabled, True)
            self.assertEqual(result.default_ttl, 7200)
            self.assertEqual(result.operation_ttls, {"list_users": 1800})
            self.assertEqual(result.max_size_mb, 200)

    def test_load_cache_config_failure(self):
        """Test _load_cache_config method with config loading failure."""
        with patch("src.awsideman.cache.manager.Config", side_effect=Exception("Config error")):
            result = self.cache_manager._load_cache_config()

            # Should return default config
            self.assertIsInstance(result, CacheConfig)
            self.assertEqual(result.enabled, True)
            self.assertEqual(result.default_ttl, 3600)
            self.assertEqual(result.operation_ttls, {})
            self.assertEqual(result.max_size_mb, 100)


class TestCacheManagerTTLLogic(unittest.TestCase):
    """Test TTL-related functionality in CacheManager."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.cache_config = CacheConfig(
            enabled=True,
            default_ttl=3600,
            operation_ttls={"list_users": 1800, "describe_account": 7200},
        )
        self.cache_manager = CacheManager(config=self.cache_config, base_cache_dir=self.temp_dir)

    def test_set_uses_operation_specific_ttl(self):
        """Test that set method uses operation-specific TTL when available."""
        test_data = {"user": "data"}
        cache_key = "user_key"

        self.cache_manager.set(cache_key, test_data, operation="list_users")

        # Verify operation-specific TTL was used
        cache_file = self.cache_manager.path_manager.get_cache_file_path(cache_key)
        with open(cache_file, "r") as f:
            stored_data = json.load(f)

        self.assertEqual(stored_data["ttl"], 1800)  # Operation-specific TTL

    def test_set_uses_default_ttl_for_unknown_operation(self):
        """Test that set method uses default TTL for unknown operations."""
        test_data = {"unknown": "data"}
        cache_key = "unknown_key"

        self.cache_manager.set(cache_key, test_data, operation="unknown_operation")

        # Verify default TTL was used
        cache_file = self.cache_manager.path_manager.get_cache_file_path(cache_key)
        with open(cache_file, "r") as f:
            stored_data = json.load(f)

        self.assertEqual(stored_data["ttl"], 3600)  # Default TTL

    def test_set_custom_ttl_overrides_operation_ttl(self):
        """Test that custom TTL parameter overrides operation-specific TTL."""
        test_data = {"override": "data"}
        cache_key = "override_key"
        custom_ttl = 900

        self.cache_manager.set(cache_key, test_data, ttl=custom_ttl, operation="list_users")

        # Verify custom TTL was used instead of operation-specific
        cache_file = self.cache_manager.path_manager.get_cache_file_path(cache_key)
        with open(cache_file, "r") as f:
            stored_data = json.load(f)

        self.assertEqual(stored_data["ttl"], custom_ttl)

    def test_get_respects_ttl_expiration(self):
        """Test that get method properly respects TTL expiration."""
        test_data = {"ttl": "test"}
        cache_key = "ttl_key"
        short_ttl = 1  # 1 second

        self.cache_manager.set(cache_key, test_data, ttl=short_ttl, operation="test_op")

        # Should be available immediately
        result = self.cache_manager.get(cache_key)
        self.assertEqual(result, test_data)

        # Wait for expiration
        time.sleep(1.1)

        # Should be expired now
        result = self.cache_manager.get(cache_key)
        self.assertIsNone(result)


class TestCacheManagerFileOperations(unittest.TestCase):
    """Test file operation aspects of CacheManager."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.cache_config = CacheConfig(enabled=True, default_ttl=3600)
        self.cache_manager = CacheManager(config=self.cache_config, base_cache_dir=self.temp_dir)

    def test_atomic_write_operation(self):
        """Test that cache writes are atomic (using temporary file)."""
        test_data = {"atomic": "write"}
        cache_key = "atomic_key"

        # Mock the file operations to verify atomic write
        cache_file = self.cache_manager.path_manager.get_cache_file_path(cache_key)
        temp_file = cache_file.with_suffix(".tmp")

        with patch("builtins.open", mock_open()) as mock_file:
            with patch.object(Path, "rename") as mock_rename:
                self.cache_manager.set(cache_key, test_data, operation="test_op")

                # Verify file was opened for writing
                mock_file.assert_called_with(temp_file, "w")

                # Verify temporary file was used
                mock_rename.assert_called_once_with(temp_file, cache_file)

    def test_cleanup_temp_file_on_error(self):
        """Test that temporary files are cleaned up on write errors."""
        test_data = {"cleanup": "test"}
        cache_key = "cleanup_key"

        with patch("builtins.open", side_effect=OSError("Write error")):
            with patch.object(self.cache_manager, "_cleanup_temp_file") as mock_cleanup:
                self.cache_manager.set(cache_key, test_data, operation="test_op")

                # Verify cleanup was called
                mock_cleanup.assert_called_once()

    def test_remove_cache_file_success(self):
        """Test _remove_cache_file method with successful removal."""
        # Create a test file
        test_file = Path(self.temp_dir) / "test_remove.json"
        test_file.write_text('{"test": "data"}')

        self.assertTrue(test_file.exists())

        self.cache_manager._remove_cache_file(test_file)

        self.assertFalse(test_file.exists())

    def test_remove_cache_file_nonexistent(self):
        """Test _remove_cache_file method with non-existent file."""
        nonexistent_file = Path(self.temp_dir) / "nonexistent.json"

        # Should not raise exception
        self.cache_manager._remove_cache_file(nonexistent_file)

    def test_handle_corrupted_cache_file(self):
        """Test _handle_corrupted_cache_file method."""
        # Create a corrupted file
        corrupted_file = Path(self.temp_dir) / "corrupted.json"
        corrupted_file.write_text("corrupted content")

        self.assertTrue(corrupted_file.exists())

        self.cache_manager._handle_corrupted_cache_file(corrupted_file, "test corruption")

        self.assertFalse(corrupted_file.exists())

    def test_cleanup_temp_file(self):
        """Test _cleanup_temp_file method."""
        cache_file = Path(self.temp_dir) / "test.json"
        temp_file = cache_file.with_suffix(".tmp")
        temp_file.write_text("temp content")

        self.assertTrue(temp_file.exists())

        self.cache_manager._cleanup_temp_file(cache_file)

        self.assertFalse(temp_file.exists())

    def test_cleanup_temp_file_nonexistent(self):
        """Test _cleanup_temp_file method with non-existent temp file."""
        cache_file = Path(self.temp_dir) / "test.json"

        # Should not raise exception
        self.cache_manager._cleanup_temp_file(cache_file)

    def test_cleanup_temp_file_none_input(self):
        """Test _cleanup_temp_file method with None input."""
        # Should not raise exception
        self.cache_manager._cleanup_temp_file(None)


if __name__ == "__main__":
    unittest.main()


class TestCacheManagerSizeManagement(unittest.TestCase):
    """Test cache size management functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.cache_config = CacheConfig(enabled=True, default_ttl=3600, max_size_mb=1)
        self.cache_manager = CacheManager(config=self.cache_config, base_cache_dir=self.temp_dir)

    def test_check_and_manage_cache_size_under_limit(self):
        """Test cache size management when under limit."""
        # Add small data that won't exceed limit
        small_data = {"small": "data"}
        self.cache_manager.set("small_key", small_data, operation="test_op")

        # Should not trigger cleanup
        with patch.object(self.cache_manager, "_cleanup_by_size") as mock_cleanup:
            self.cache_manager._check_and_manage_cache_size()
            mock_cleanup.assert_not_called()

    def test_check_and_manage_cache_size_over_limit(self):
        """Test cache size management when over limit."""
        # Mock size methods to simulate over-limit condition
        with patch.object(
            self.cache_manager.path_manager, "get_cache_size", return_value=2 * 1024 * 1024
        ):  # 2MB
            with patch.object(
                self.cache_manager, "_cleanup_by_size", return_value=5
            ) as mock_cleanup:
                self.cache_manager._check_and_manage_cache_size()
                mock_cleanup.assert_called_once()

    def test_cleanup_by_size(self):
        """Test _cleanup_by_size method."""
        # Create some test cache files
        cache_dir = Path(self.temp_dir)
        cache_dir.mkdir(exist_ok=True)

        # Create files with different ages and content
        current_time = time.time()
        test_files = []

        for i in range(3):
            cache_file = cache_dir / f"cache_{i}.json"
            cache_data = {
                "data": {"test": f"data_{i}"},
                "created_at": current_time - (i * 1000),  # Different ages
                "ttl": 3600,
                "key": f"key_{i}",
                "operation": "test_op",
            }

            with open(cache_file, "w") as f:
                json.dump(cache_data, f)

            test_files.append(cache_file)

        # Mock the path manager to return our test files
        with patch.object(
            self.cache_manager.path_manager, "list_cache_files", return_value=test_files
        ):
            removed_count = self.cache_manager._cleanup_by_size(1024)  # Request to free 1KB

            self.assertGreaterEqual(removed_count, 0)

    def test_cleanup_old_entries(self):
        """Test _cleanup_old_entries method."""
        # Create some test cache files
        cache_dir = Path(self.temp_dir)
        cache_dir.mkdir(exist_ok=True)

        test_files = []
        for i in range(5):
            cache_file = cache_dir / f"old_cache_{i}.json"
            cache_file.write_text('{"test": "data"}')
            test_files.append(cache_file)

        # Mock the path manager
        with patch.object(
            self.cache_manager.path_manager, "list_cache_files", return_value=test_files
        ):
            removed_count = self.cache_manager._cleanup_old_entries(max_entries_to_remove=3)

            self.assertEqual(removed_count, 3)

    def test_get_cache_size_info(self):
        """Test get_cache_size_info method."""
        # Add some test data
        test_data = {"size": "info_test"}
        self.cache_manager.set("size_key", test_data, operation="test_op")

        size_info = self.cache_manager.get_cache_size_info()

        self.assertIsInstance(size_info, dict)
        required_keys = [
            "current_size_bytes",
            "current_size_mb",
            "max_size_bytes",
            "max_size_mb",
            "usage_percentage",
            "is_over_limit",
            "bytes_over_limit",
            "available_space_bytes",
            "available_space_mb",
        ]

        for key in required_keys:
            self.assertIn(key, size_info)

        self.assertGreaterEqual(size_info["current_size_bytes"], 0)
        self.assertGreaterEqual(size_info["current_size_mb"], 0)

    def test_get_cache_size_info_error(self):
        """Test get_cache_size_info method with error."""
        with patch.object(
            self.cache_manager.path_manager, "get_cache_size", side_effect=Exception("Size error")
        ):
            size_info = self.cache_manager.get_cache_size_info()

            self.assertIn("error", size_info)
            self.assertEqual(size_info["current_size_bytes"], 0)


class TestCacheManagerStats(unittest.TestCase):
    """Test cache statistics functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.cache_config = CacheConfig(enabled=True, default_ttl=3600)
        self.cache_manager = CacheManager(config=self.cache_config, base_cache_dir=self.temp_dir)

    def test_get_cache_stats_empty_cache(self):
        """Test get_cache_stats with empty cache."""
        stats = self.cache_manager.get_cache_stats()

        self.assertIsInstance(stats, dict)
        self.assertEqual(stats["enabled"], True)
        self.assertEqual(stats["total_entries"], 0)
        self.assertEqual(stats["valid_entries"], 0)
        self.assertEqual(stats["expired_entries"], 0)
        self.assertEqual(stats["corrupted_entries"], 0)
        self.assertEqual(stats["total_size_bytes"], 0)
        self.assertEqual(stats["default_ttl"], 3600)

    def test_get_cache_stats_with_valid_entries(self):
        """Test get_cache_stats with valid cache entries."""
        # Add some valid entries
        test_data = [("key1", {"data": 1}), ("key2", {"data": 2}), ("key3", {"data": 3})]

        for key, data in test_data:
            self.cache_manager.set(key, data, operation="test_op")

        stats = self.cache_manager.get_cache_stats()

        self.assertEqual(stats["total_entries"], 3)
        self.assertEqual(stats["valid_entries"], 3)
        self.assertEqual(stats["expired_entries"], 0)
        self.assertEqual(stats["corrupted_entries"], 0)
        self.assertGreater(stats["total_size_bytes"], 0)

    def test_get_cache_stats_with_expired_entries(self):
        """Test get_cache_stats with expired cache entries."""
        # Create expired entries manually
        cache_dir = Path(self.temp_dir)
        cache_dir.mkdir(exist_ok=True)

        current_time = time.time()

        # Valid entry
        valid_file = cache_dir / "valid.json"
        valid_data = {
            "data": {"test": "valid"},
            "created_at": current_time - 1800,  # 30 minutes ago
            "ttl": 3600,  # 1 hour TTL (still valid)
            "key": "valid_key",
            "operation": "test_op",
        }
        with open(valid_file, "w") as f:
            json.dump(valid_data, f)

        # Expired entry
        expired_file = cache_dir / "expired.json"
        expired_data = {
            "data": {"test": "expired"},
            "created_at": current_time - 7200,  # 2 hours ago
            "ttl": 3600,  # 1 hour TTL (expired)
            "key": "expired_key",
            "operation": "test_op",
        }
        with open(expired_file, "w") as f:
            json.dump(expired_data, f)

        stats = self.cache_manager.get_cache_stats()

        self.assertEqual(stats["total_entries"], 2)
        self.assertEqual(stats["valid_entries"], 1)
        self.assertEqual(stats["expired_entries"], 1)
        self.assertEqual(stats["corrupted_entries"], 0)

    def test_get_cache_stats_with_corrupted_entries(self):
        """Test get_cache_stats with corrupted cache entries."""
        # Create a corrupted cache file
        cache_dir = Path(self.temp_dir)
        cache_dir.mkdir(exist_ok=True)

        corrupted_file = cache_dir / "corrupted.json"
        with open(corrupted_file, "w") as f:
            f.write("invalid json content {")

        stats = self.cache_manager.get_cache_stats()

        self.assertEqual(stats["total_entries"], 1)
        self.assertEqual(stats["valid_entries"], 0)
        self.assertEqual(stats["expired_entries"], 0)
        self.assertEqual(stats["corrupted_entries"], 1)
        self.assertIn("warning", stats)

    def test_get_cache_stats_error(self):
        """Test get_cache_stats with error."""
        with patch.object(
            self.cache_manager.path_manager,
            "list_cache_files",
            side_effect=Exception("Stats error"),
        ):
            stats = self.cache_manager.get_cache_stats()

            self.assertIn("error", stats)
            self.assertEqual(stats["enabled"], True)


class TestCacheManagerIntegration(unittest.TestCase):
    """Integration tests for CacheManager functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.cache_config = CacheConfig(
            enabled=True,
            default_ttl=3600,
            operation_ttls={"list_users": 1800, "describe_account": 7200},
            max_size_mb=10,
        )
        self.cache_manager = CacheManager(config=self.cache_config, base_cache_dir=self.temp_dir)

    def test_full_cache_lifecycle(self):
        """Test complete cache lifecycle: set, get, expire, invalidate."""
        test_data = {"lifecycle": "test", "complex": {"nested": ["data", 123]}}
        cache_key = "lifecycle_key"

        # 1. Set data
        self.cache_manager.set(cache_key, test_data, operation="list_users")

        # 2. Get data (should hit cache)
        result = self.cache_manager.get(cache_key)
        self.assertEqual(result, test_data)

        # 3. Check stats
        stats = self.cache_manager.get_cache_stats()
        self.assertEqual(stats["valid_entries"], 1)

        # 4. Invalidate
        self.cache_manager.invalidate(cache_key)

        # 5. Verify invalidation
        result = self.cache_manager.get(cache_key)
        self.assertIsNone(result)

        # 6. Check stats after invalidation
        stats = self.cache_manager.get_cache_stats()
        self.assertEqual(stats["total_entries"], 0)

    def test_multiple_operations_with_different_ttls(self):
        """Test multiple operations with different TTL configurations."""
        operations_data = [
            ("list_users", {"users": ["user1", "user2"]}, 1800),
            ("describe_account", {"account": "123456789012"}, 7200),
            ("unknown_op", {"data": "unknown"}, 3600),  # Should use default TTL
        ]

        for operation, data, expected_ttl in operations_data:
            cache_key = f"{operation}_key"

            # Set data
            self.cache_manager.set(cache_key, data, operation=operation)

            # Verify data can be retrieved
            result = self.cache_manager.get(cache_key)
            self.assertEqual(result, data)

            # Verify correct TTL was used
            cache_file = self.cache_manager.path_manager.get_cache_file_path(cache_key)
            with open(cache_file, "r") as f:
                stored_data = json.load(f)

            self.assertEqual(stored_data["ttl"], expected_ttl)

    def test_cache_behavior_when_disabled(self):
        """Test that cache operations work correctly when cache is disabled."""
        # Disable cache
        self.cache_manager.config.enabled = False

        test_data = {"disabled": "cache_test"}
        cache_key = "disabled_key"

        # Set should not create file
        self.cache_manager.set(cache_key, test_data, operation="test_op")
        cache_file = self.cache_manager.path_manager.get_cache_file_path(cache_key)
        self.assertFalse(cache_file.exists())

        # Get should return None
        result = self.cache_manager.get(cache_key)
        self.assertIsNone(result)

        # Invalidate should not raise exception
        self.cache_manager.invalidate(cache_key)
        self.cache_manager.invalidate()  # Clear all

        # Stats should indicate disabled state
        stats = self.cache_manager.get_cache_stats()
        self.assertEqual(stats["enabled"], False)

    def test_concurrent_cache_operations(self):
        """Test cache operations that might happen concurrently."""
        import queue
        import threading

        results = queue.Queue()
        errors = queue.Queue()

        def cache_worker(worker_id):
            try:
                # Each worker sets and gets its own data
                test_data = {"worker": worker_id, "data": list(range(10))}
                cache_key = f"worker_{worker_id}_key"

                # Set data
                self.cache_manager.set(cache_key, test_data, operation="test_op")

                # Get data back
                result = self.cache_manager.get(cache_key)

                results.put((worker_id, result == test_data))

            except Exception as e:
                errors.put((worker_id, str(e)))

        # Start multiple worker threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=cache_worker, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Check results
        self.assertTrue(errors.empty(), f"Errors occurred: {list(errors.queue)}")

        success_count = 0
        while not results.empty():
            worker_id, success = results.get()
            if success:
                success_count += 1

        self.assertEqual(success_count, 5, "All workers should have succeeded")
