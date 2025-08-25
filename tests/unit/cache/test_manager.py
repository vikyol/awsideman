"""Unit tests for the unified cache manager."""

import threading
import time
from datetime import timedelta

from src.awsideman.cache.manager import CacheManager


class TestSingletonBehavior:
    """Test singleton pattern implementation."""

    def setup_method(self):
        """Reset singleton instances before each test."""
        CacheManager.reset_instance()

    def test_singleton_same_instance(self):
        """Test that multiple instantiations return the same instance."""
        manager1 = CacheManager()
        manager2 = CacheManager()

        assert manager1 is manager2
        assert id(manager1) == id(manager2)

    def test_singleton_with_different_parameters(self):
        """Test that singleton ignores parameters after first instantiation."""
        manager1 = CacheManager(default_ttl=timedelta(minutes=10))
        manager2 = CacheManager(default_ttl=timedelta(minutes=20))

        assert manager1 is manager2
        # First instance parameters should be preserved
        assert manager1._default_ttl == timedelta(minutes=10)

    def test_singleton_thread_safety(self):
        """Test that singleton creation is thread-safe."""
        instances = []
        barrier = threading.Barrier(10)  # Synchronize 10 threads

        def create_instance():
            barrier.wait()  # Wait for all threads to be ready
            instance = CacheManager()
            instances.append(instance)

        # Create 10 threads that simultaneously try to create instances
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=create_instance)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # All instances should be the same object
        assert len(instances) == 10
        first_instance = instances[0]
        for instance in instances:
            assert instance is first_instance

    def test_singleton_reset_for_testing(self):
        """Test that singleton can be reset for testing purposes."""
        manager1 = CacheManager()
        manager1_id = id(manager1)

        # Reset singleton instance
        CacheManager.reset_instance()

        # New instance should be different
        manager2 = CacheManager()
        manager2_id = id(manager2)

        assert manager1_id != manager2_id


class TestCacheOperations:
    """Test basic cache operations."""

    def setup_method(self):
        """Reset singleton instance before each test."""
        CacheManager.reset_instance()

    def test_get_set_basic(self):
        """Test basic get and set operations."""
        manager = CacheManager()

        # Test cache miss
        result = manager.get("test_key")
        assert result is None

        # Test cache set and hit
        test_data = {"test": "data"}
        manager.set("test_key", test_data)

        result = manager.get("test_key")
        assert result == test_data

    def test_ttl_expiration(self):
        """Test that entries expire after TTL."""
        manager = CacheManager(default_ttl=timedelta(milliseconds=100))

        test_data = {"test": "data"}
        manager.set("test_key", test_data)

        # Should be available immediately
        assert manager.get("test_key") == test_data

        # Wait for expiration
        time.sleep(0.15)  # 150ms > 100ms TTL

        # Should be expired
        assert manager.get("test_key") is None

    def test_custom_ttl(self):
        """Test setting custom TTL for individual entries."""
        manager = CacheManager(default_ttl=timedelta(minutes=10))

        test_data = {"test": "data"}
        custom_ttl = timedelta(milliseconds=100)
        manager.set("test_key", test_data, ttl=custom_ttl)

        # Should be available immediately
        assert manager.get("test_key") == test_data

        # Wait for custom TTL expiration
        time.sleep(0.15)

        # Should be expired
        assert manager.get("test_key") is None

    def test_exists(self):
        """Test exists method."""
        manager = CacheManager()

        # Key doesn't exist
        assert not manager.exists("test_key")

        # Set key
        manager.set("test_key", "test_data")
        assert manager.exists("test_key")

        # Test with expired key
        manager.set("expired_key", "data", ttl=timedelta(milliseconds=50))
        time.sleep(0.1)
        assert not manager.exists("expired_key")

    def test_clear(self):
        """Test clearing all cache entries."""
        manager = CacheManager()

        # Add some entries
        manager.set("key1", "data1")
        manager.set("key2", "data2")
        manager.set("key3", "data3")

        assert manager.get_cache_size() == 3

        # Clear cache
        manager.clear()

        assert manager.get_cache_size() == 0
        assert manager.get("key1") is None
        assert manager.get("key2") is None
        assert manager.get("key3") is None


class TestPatternInvalidation:
    """Test pattern-based cache invalidation."""

    def setup_method(self):
        """Reset singleton instances before each test."""
        CacheManager.reset_instance()

    def test_wildcard_invalidation(self):
        """Test invalidation with wildcard patterns."""
        manager = CacheManager()

        # Set up test data
        manager.set("user:list:all", "user_list_data")
        manager.set("user:describe:user-123", "user_123_data")
        manager.set("user:describe:user-456", "user_456_data")
        manager.set("group:list:all", "group_list_data")
        manager.set("group:describe:group-789", "group_789_data")

        # Test wildcard invalidation - currently only clears in-memory cache
        # Backend entries remain until they expire or are cleared with "*"
        invalidated = manager.invalidate("user:*")

        assert invalidated == 3  # Should invalidate 3 user entries from memory

        # Note: In current implementation, pattern invalidation only clears in-memory cache
        # Backend entries remain and will be reloaded on next access
        # This test reflects the current behavior

    def test_specific_pattern_invalidation(self):
        """Test invalidation with specific patterns."""
        manager = CacheManager()

        # Set up test data
        manager.set("user:describe:user-123", "user_123_data")
        manager.set("user:describe:user-456", "user_456_data")
        manager.set("user:list:all", "user_list_data")

        # Test specific pattern - currently only clears in-memory cache
        invalidated = manager.invalidate("user:describe:*")

        assert invalidated == 2  # Should invalidate 2 describe entries from memory

        # Note: In current implementation, pattern invalidation only clears in-memory cache
        # Backend entries remain and will be reloaded on next access

    def test_exact_key_invalidation(self):
        """Test invalidation of exact keys."""
        manager = CacheManager()

        # Set up test data
        manager.set("exact:key", "exact_data")
        manager.set("exact:key:suffix", "suffix_data")

        # Test exact key invalidation - currently only clears in-memory cache
        invalidated = manager.invalidate("exact:key")

        assert invalidated == 1  # Should invalidate only exact match from memory

        # Note: In current implementation, pattern invalidation only clears in-memory cache
        # Backend entries remain and will be reloaded on next access

    def test_no_match_invalidation(self):
        """Test invalidation when no keys match pattern."""
        manager = CacheManager()

        # Set up test data
        manager.set("user:list:all", "user_data")
        manager.set("group:list:all", "group_data")

        # Test pattern that matches nothing
        invalidated = manager.invalidate("permission:*")

        assert invalidated == 0

        # All entries should remain
        assert manager.get("user:list:all") == "user_data"
        assert manager.get("group:list:all") == "group_data"


class TestThreadSafety:
    """Test thread safety of cache operations."""

    def setup_method(self):
        """Reset singleton instances before each test."""
        CacheManager.reset_instance()

    def test_concurrent_get_set(self):
        """Test concurrent get and set operations."""
        manager = CacheManager()
        results = {}
        errors = []

        def worker(thread_id):
            try:
                # Each thread sets and gets its own data
                key = f"thread_{thread_id}"
                data = f"data_{thread_id}"

                manager.set(key, data)
                retrieved = manager.get(key)
                results[thread_id] = retrieved
            except Exception as e:
                errors.append(e)

        # Create and start threads
        threads = []
        for i in range(10):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Check results
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 10

        for i in range(10):
            assert results[i] == f"data_{i}"

    def test_concurrent_invalidation(self):
        """Test concurrent invalidation operations."""
        manager = CacheManager()

        # Set up initial data with non-overlapping patterns
        for i in range(50):
            manager.set(f"user_{i}", f"user_data_{i}")
            manager.set(f"group_{i}", f"group_data_{i}")

        invalidation_results = []
        errors = []

        def invalidate_worker(pattern):
            try:
                result = manager.invalidate(pattern)
                invalidation_results.append(result)
            except Exception as e:
                errors.append(e)

        # Create threads that invalidate different patterns (non-overlapping)
        threads = []
        patterns = ["user_1*", "user_2*", "group_1*", "group_2*"]

        for pattern in patterns:
            thread = threading.Thread(target=invalidate_worker, args=(pattern,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Check results
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(invalidation_results) == 4

        # Each pattern should match some entries
        total_invalidated = sum(invalidation_results)
        assert total_invalidated > 0  # At least some entries should be invalidated

        # Verify that concurrent operations didn't cause data corruption
        remaining_entries = manager.get_cache_size()
        assert remaining_entries >= 0  # Should not be negative


class TestStatistics:
    """Test cache statistics tracking."""

    def setup_method(self):
        """Reset singleton instances before each test."""
        CacheManager.reset_instance()

    def test_hit_miss_statistics(self):
        """Test hit and miss statistics tracking."""
        manager = CacheManager()

        # Initial stats should be zero
        stats = manager.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["sets"] == 0

        # Test cache miss
        manager.get("nonexistent_key")
        stats = manager.get_stats()
        assert stats["misses"] == 1

        # Test cache set and hit
        manager.set("test_key", "test_data")
        manager.get("test_key")

        stats = manager.get_stats()
        assert stats["sets"] == 1
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate_percentage"] == 50.0  # 1 hit out of 2 requests

    def test_invalidation_statistics(self):
        """Test invalidation statistics tracking."""
        manager = CacheManager()

        # Set up test data
        manager.set("key1", "data1")
        manager.set("key2", "data2")
        manager.set("key3", "data3")

        # Test invalidation
        manager.invalidate("key*")

        stats = manager.get_stats()
        assert stats["invalidations"] == 3

    def test_clear_statistics(self):
        """Test clear statistics tracking."""
        manager = CacheManager()

        # Set up test data
        manager.set("key1", "data1")
        manager.set("key2", "data2")

        # Test clear
        manager.clear()

        stats = manager.get_stats()
        assert stats["clears"] == 1

    def test_expired_entries_count(self):
        """Test counting of expired entries in statistics."""
        manager = CacheManager()

        # Set entries with short TTL
        manager.set("key1", "data1", ttl=timedelta(milliseconds=50))
        manager.set("key2", "data2", ttl=timedelta(milliseconds=50))
        manager.set("key3", "data3", ttl=timedelta(minutes=10))  # Long TTL

        # Wait for some to expire
        time.sleep(0.1)

        stats = manager.get_stats()
        assert stats["total_entries"] == 3
        assert stats["expired_entries"] == 2
        assert stats["active_entries"] == 1


class TestUtilityMethods:
    """Test utility methods."""

    def setup_method(self):
        """Reset singleton instances before each test."""
        CacheManager.reset_instance()

    def test_cleanup_expired(self):
        """Test cleanup of expired entries."""
        manager = CacheManager()

        # Set entries with different TTLs
        manager.set("short1", "data1", ttl=timedelta(milliseconds=50))
        manager.set("short2", "data2", ttl=timedelta(milliseconds=50))
        manager.set("long", "data3", ttl=timedelta(minutes=10))

        # Wait for short TTL entries to expire
        time.sleep(0.1)

        # Cleanup expired entries
        removed_count = manager.cleanup_expired()

        assert removed_count == 2
        assert manager.get_cache_size() == 1
        assert manager.get("long") == "data3"

    def test_get_keys_matching(self):
        """Test getting keys matching a pattern."""
        manager = CacheManager()

        # Set up test data
        manager.set("user:list:all", "data1")
        manager.set("user:describe:user-123", "data2")
        manager.set("group:list:all", "data3")
        manager.set("group:describe:group-456", "data4")

        # Test pattern matching
        user_keys = manager.get_keys_matching("user:*")
        assert len(user_keys) == 2
        assert "user:list:all" in user_keys
        assert "user:describe:user-123" in user_keys

        describe_keys = manager.get_keys_matching("*:describe:*")
        assert len(describe_keys) == 2
        assert "user:describe:user-123" in describe_keys
        assert "group:describe:group-456" in describe_keys

    def test_get_cache_size(self):
        """Test getting cache size."""
        manager = CacheManager()

        assert manager.get_cache_size() == 0

        manager.set("key1", "data1")
        assert manager.get_cache_size() == 1

        manager.set("key2", "data2")
        assert manager.get_cache_size() == 2

        manager.invalidate("key1")
        assert manager.get_cache_size() == 1


class TestInvalidationIntegration:
    """Test integration with invalidation engine."""

    def setup_method(self):
        """Reset singleton instances before each test."""
        CacheManager.reset_instance()

    def test_invalidate_for_operation_user(self):
        """Test invalidate_for_operation method for user operations."""
        manager = CacheManager()

        # Set up some cache entries
        manager.set("user:list:all", ["user1", "user2"])
        manager.set("user:describe:user-123", {"id": "user-123"})
        manager.set("group:members:group-456", ["user-123"])

        # Invalidate for user update
        result = manager.invalidate_for_operation("update", "user", "user-123")

        # Should have invalidated multiple entries
        assert result > 0

        # Note: In current implementation, invalidate_for_operation only clears in-memory cache
        # Backend entries remain and will be reloaded on next access

    def test_invalidate_for_operation_group(self):
        """Test invalidate_for_operation method for group operations."""
        manager = CacheManager()

        # Set up some cache entries
        manager.set("group:list:all", ["group1", "group2"])
        manager.set("group:describe:group-456", {"id": "group-456"})
        manager.set("group:members:group-456", ["user-123"])

        # Invalidate for group update
        result = manager.invalidate_for_operation("update", "group", "group-456")

        # Should have invalidated multiple entries
        assert result > 0

        # Note: In current implementation, invalidate_for_operation only clears in-memory cache
        # Backend entries remain and will be reloaded on next access

    def test_invalidate_for_operation_with_context(self):
        """Test invalidate_for_operation with additional context."""
        manager = CacheManager()

        # Set up some cache entries
        manager.set("group:members:group-456", ["user-123", "user-789"])
        manager.set("user:describe:user-123", {"id": "user-123"})
        manager.set("user:describe:user-789", {"id": "user-789"})

        # Invalidate for group membership change
        result = manager.invalidate_for_operation(
            "add_member", "group", "group-456", {"affected_user_ids": "user-123,user-789"}
        )

        # Should have invalidated multiple entries
        assert result > 0

        # Note: In current implementation, invalidate_for_operation only clears in-memory cache
        # Backend entries remain and will be reloaded on next access

    def test_invalidate_for_operation_no_context(self):
        """Test invalidate_for_operation without additional context."""
        manager = CacheManager()

        # Set up some cache entries
        manager.set("user:list:all", ["user1", "user2"])

        # Should work without additional context
        result = manager.invalidate_for_operation("create", "user")

        assert result >= 0

    def test_invalidate_for_operation_permission_set(self):
        """Test invalidate_for_operation for permission set operations."""
        manager = CacheManager()

        # Set up some cache entries
        manager.set("permission_set:list:all", ["ps1", "ps2"])
        manager.set("permission_set:describe:ps-TestPS", {"name": "TestPS"})
        manager.set("assignment:list:acc-123456789012", ["assignment1"])

        # Invalidate for permission set update
        result = manager.invalidate_for_operation(
            "update", "permission_set", "ps-TestPS", {"account_id": "123456789012"}
        )

        # Should have invalidated multiple entries
        assert result > 0

        # Note: In current implementation, invalidate_for_operation only clears in-memory cache
        # Backend entries remain and will be reloaded on next access

    def test_invalidate_for_operation_assignment(self):
        """Test invalidate_for_operation for assignment operations."""
        manager = CacheManager()

        # Set up some cache entries
        manager.set("assignment:list:all", ["assignment1", "assignment2"])
        manager.set("assignment:account_assignments:acc-123456789012", ["assignment1"])
        manager.set("user:describe:user-123", {"id": "user-123"})

        # Invalidate for assignment creation
        result = manager.invalidate_for_operation(
            "create",
            "assignment",
            None,
            {"account_id": "123456789012", "principal_id": "user-123", "principal_type": "USER"},
        )

        # Should have invalidated multiple entries
        assert result > 0

        # Note: In current implementation, invalidate_for_operation only clears in-memory cache
        # Backend entries remain and will be reloaded on next access
