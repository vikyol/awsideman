"""Tests for CacheManager error handling and resilience."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, mock_open

from awsideman.utils.cache_manager import CacheManager
from awsideman.utils.models import CacheConfig


class TestCacheManagerErrorHandling(unittest.TestCase):
    """Test error handling and resilience in CacheManager."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.cache_config = CacheConfig(enabled=True, default_ttl=3600)
        self.cache_manager = CacheManager(
            config=self.cache_config,
            base_cache_dir=self.temp_dir
        )
    
    def test_get_with_corrupted_json_file(self):
        """Test that corrupted JSON files are handled gracefully."""
        # Create a corrupted cache file
        cache_key = "test_key"
        cache_file = self.cache_manager.path_manager.get_cache_file_path(cache_key)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Write invalid JSON
        with open(cache_file, 'w') as f:
            f.write("invalid json content {")
        
        # Should return None and not raise exception
        result = self.cache_manager.get(cache_key)
        self.assertIsNone(result)
        
        # Corrupted file should be removed
        self.assertFalse(cache_file.exists())
    
    def test_get_with_missing_required_fields(self):
        """Test that cache files missing required fields are handled gracefully."""
        cache_key = "test_key"
        cache_file = self.cache_manager.path_manager.get_cache_file_path(cache_key)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Write JSON with missing required fields
        incomplete_data = {
            "data": {"test": "data"},
            "created_at": 1234567890
            # Missing ttl, key, operation
        }
        
        with open(cache_file, 'w') as f:
            json.dump(incomplete_data, f)
        
        # Should return None and not raise exception
        result = self.cache_manager.get(cache_key)
        self.assertIsNone(result)
        
        # Corrupted file should be removed
        self.assertFalse(cache_file.exists())
    
    def test_get_with_permission_error(self):
        """Test that permission errors are handled gracefully."""
        cache_key = "test_key"
        
        with patch('builtins.open', side_effect=PermissionError("Permission denied")):
            result = self.cache_manager.get(cache_key)
            self.assertIsNone(result)
    
    def test_set_with_permission_error(self):
        """Test that permission errors during set don't break the operation."""
        cache_key = "test_key"
        test_data = {"test": "data"}
        
        with patch('builtins.open', side_effect=PermissionError("Permission denied")):
            # Should not raise exception
            self.cache_manager.set(cache_key, test_data)
    
    def test_set_with_disk_full_error(self):
        """Test that disk full errors trigger cleanup."""
        cache_key = "test_key"
        test_data = {"test": "data"}
        
        # Mock OSError with "No space left on device" message
        disk_full_error = OSError("No space left on device")
        
        with patch('builtins.open', side_effect=disk_full_error):
            with patch.object(self.cache_manager, '_cleanup_old_entries') as mock_cleanup:
                # Should not raise exception and should trigger cleanup
                self.cache_manager.set(cache_key, test_data)
                mock_cleanup.assert_called_once()
    
    def test_set_with_invalid_data_type(self):
        """Test that non-JSON-serializable data is rejected gracefully."""
        cache_key = "test_key"
        invalid_data = object()  # Non-JSON-serializable object
        
        # Should not raise exception
        self.cache_manager.set(cache_key, invalid_data)
    
    def test_get_cache_stats_with_corrupted_files(self):
        """Test that cache stats handle corrupted files gracefully."""
        # Create some valid and corrupted cache files
        cache_dir = Path(self.temp_dir)
        cache_dir.mkdir(exist_ok=True)
        
        # Valid cache file
        valid_file = cache_dir / "valid.json"
        import time
        valid_data = {
            "data": {"test": "data"},
            "created_at": time.time(),  # Use current time so it's not expired
            "ttl": 3600,
            "key": "valid_key",
            "operation": "test_op"
        }
        with open(valid_file, 'w') as f:
            json.dump(valid_data, f)
        
        # Corrupted cache file
        corrupted_file = cache_dir / "corrupted.json"
        with open(corrupted_file, 'w') as f:
            f.write("invalid json {")
        
        # Get stats - should not raise exception
        stats = self.cache_manager.get_cache_stats()
        
        self.assertIsInstance(stats, dict)
        self.assertIn('corrupted_entries', stats)
        self.assertEqual(stats['corrupted_entries'], 1)
        self.assertEqual(stats['valid_entries'], 1)
    
    def test_invalidate_with_permission_error(self):
        """Test that permission errors during invalidate are handled gracefully."""
        cache_key = "test_key"
        
        with patch.object(self.cache_manager.path_manager, 'delete_cache_file', 
                         side_effect=PermissionError("Permission denied")):
            # Should not raise exception
            self.cache_manager.invalidate(cache_key)
    
    def test_cleanup_old_entries(self):
        """Test that cleanup of old entries works correctly."""
        # Create some cache files with different modification times
        cache_dir = Path(self.temp_dir)
        cache_dir.mkdir(exist_ok=True)
        
        files = []
        for i in range(5):
            cache_file = cache_dir / f"cache_{i}.json"
            cache_file.write_text('{"test": "data"}')
            files.append(cache_file)
        
        # Cleanup should remove some files
        removed_count = self.cache_manager._cleanup_old_entries(max_entries_to_remove=3)
        
        self.assertEqual(removed_count, 3)
        
        # Check that 2 files remain
        remaining_files = list(cache_dir.glob("*.json"))
        self.assertEqual(len(remaining_files), 2)
    
    def test_handle_corrupted_cache_file(self):
        """Test that corrupted cache files are handled properly."""
        cache_file = Path(self.temp_dir) / "corrupted.json"
        cache_file.write_text("corrupted content")
        
        # Should remove the file without raising exception
        self.cache_manager._handle_corrupted_cache_file(cache_file, "test reason")
        
        self.assertFalse(cache_file.exists())
    
    def test_cache_disabled_on_directory_creation_failure(self):
        """Test that cache is disabled when directory cannot be created."""
        # Mock directory creation failure
        with patch.object(self.cache_manager.path_manager, 'ensure_cache_directory',
                         side_effect=OSError("Cannot create directory")):
            # Create a new cache manager that will fail to create directory
            cache_manager = CacheManager(
                config=CacheConfig(enabled=True),
                base_cache_dir="/invalid/path"
            )
            
            # Cache should be disabled
            self.assertFalse(cache_manager.config.enabled)
    
    def test_cache_size_management(self):
        """Test that cache size management works correctly."""
        # Create a cache manager with a small size limit
        small_config = CacheConfig(enabled=True, max_size_mb=1)  # 1 MB limit
        cache_manager = CacheManager(
            config=small_config,
            base_cache_dir=self.temp_dir
        )
        
        # Create some large cache entries that exceed the limit
        large_data = {"data": "x" * 200000}  # ~200KB each
        
        # Add entries one by one and check that cleanup happens
        for i in range(8):  # This should exceed 1MB and trigger cleanup
            cache_manager.set(f"large_key_{i}", large_data, operation="test_op")
        
        # Check that cache size management was triggered
        size_info = cache_manager.get_cache_size_info()
        
        # The cache should be managed (not necessarily under limit, but managed)
        # Check that we have some entries but not all 8 (some should have been cleaned up)
        cache_files = cache_manager.path_manager.list_cache_files()
        self.assertGreater(len(cache_files), 0)  # Should have some files
        self.assertLess(len(cache_files), 8)     # But not all 8 files
    
    def test_get_cache_size_info(self):
        """Test that cache size info is calculated correctly."""
        # Add some test data
        test_data = {"test": "data"}
        self.cache_manager.set("test_key", test_data)
        
        size_info = self.cache_manager.get_cache_size_info()
        
        self.assertIsInstance(size_info, dict)
        self.assertIn('current_size_bytes', size_info)
        self.assertIn('current_size_mb', size_info)
        self.assertIn('max_size_bytes', size_info)
        self.assertIn('max_size_mb', size_info)
        self.assertIn('usage_percentage', size_info)
        self.assertIn('is_over_limit', size_info)
        
        # Should have some data now
        self.assertGreater(size_info['current_size_bytes'], 0)
    
    def test_cache_different_data_types(self):
        """Test that cache can handle different JSON-serializable data types."""
        # Test dict
        self.cache_manager.set("dict_key", {"test": "data"})
        self.assertEqual(self.cache_manager.get("dict_key"), {"test": "data"})
        
        # Test list
        self.cache_manager.set("list_key", [1, 2, 3])
        self.assertEqual(self.cache_manager.get("list_key"), [1, 2, 3])
        
        # Test string
        self.cache_manager.set("string_key", "test string")
        self.assertEqual(self.cache_manager.get("string_key"), "test string")
        
        # Test number
        self.cache_manager.set("number_key", 42)
        self.assertEqual(self.cache_manager.get("number_key"), 42)
        
        # Test boolean
        self.cache_manager.set("bool_key", True)
        self.assertEqual(self.cache_manager.get("bool_key"), True)


if __name__ == '__main__':
    unittest.main()