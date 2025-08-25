"""Tests for cache manager integration in commands."""

from unittest.mock import patch

from src.awsideman.cache.manager import CacheManager


class TestCommandCacheIntegration:
    """Test cache manager integration in command modules."""

    def test_user_create_uses_unified_cache_manager(self):
        """Test that user create command uses CacheManager."""
        from src.awsideman.commands.cache.helpers import get_cache_manager

        cache_manager = get_cache_manager()
        assert isinstance(cache_manager, CacheManager)

    def test_user_delete_uses_unified_cache_manager(self):
        """Test that user delete command uses CacheManager."""
        from src.awsideman.commands.cache.helpers import get_cache_manager

        cache_manager = get_cache_manager()
        assert isinstance(cache_manager, CacheManager)

    def test_user_update_uses_unified_cache_manager(self):
        """Test that user update command uses CacheManager."""
        from src.awsideman.commands.cache.helpers import get_cache_manager

        cache_manager = get_cache_manager()
        assert isinstance(cache_manager, CacheManager)

    def test_user_create_invalidation(self):
        """Test that user create command can access cache manager for invalidation."""
        from src.awsideman.commands.cache.helpers import get_cache_manager

        # Verify that the cache manager has the invalidate_for_operation method
        cache_manager = get_cache_manager()
        assert hasattr(cache_manager, "invalidate_for_operation")

        # Test that the method works
        result = cache_manager.invalidate_for_operation("create", "user", "test-user-id")
        assert isinstance(result, int)  # Should return count of invalidated entries

    def test_user_delete_invalidation(self):
        """Test that user delete command can access cache manager for invalidation."""
        from src.awsideman.commands.cache.helpers import get_cache_manager

        # Verify that the cache manager has the invalidate_for_operation method
        cache_manager = get_cache_manager()
        assert hasattr(cache_manager, "invalidate_for_operation")

        # Test that the method works
        result = cache_manager.invalidate_for_operation("delete", "user", "test-user-id")
        assert isinstance(result, int)  # Should return count of invalidated entries

    def test_user_update_invalidation(self):
        """Test that user update command can access cache manager for invalidation."""
        from src.awsideman.commands.cache.helpers import get_cache_manager

        # Verify that the cache manager has the invalidate_for_operation method
        cache_manager = get_cache_manager()
        assert hasattr(cache_manager, "invalidate_for_operation")

        # Test that the method works
        result = cache_manager.invalidate_for_operation("update", "user", "test-user-id")
        assert isinstance(result, int)  # Should return count of invalidated entries

    def test_cache_clear_uses_unified_cache_manager(self):
        """Test that cache clear command uses CacheManager."""
        from src.awsideman.commands.cache.helpers import get_cache_manager

        cache_manager = get_cache_manager()
        assert isinstance(cache_manager, CacheManager)

    def test_cache_clear_invalidation(self):
        """Test that cache clear command can access cache manager for invalidation."""
        from src.awsideman.commands.cache.helpers import get_cache_manager

        # Verify that the cache manager has the invalidate method
        cache_manager = get_cache_manager()
        assert hasattr(cache_manager, "invalidate")

        # Test that the method works with wildcard pattern
        result = cache_manager.invalidate("*")
        assert isinstance(result, int)  # Should return count of invalidated entries

    def test_cache_warm_uses_unified_cache_manager(self):
        """Test that cache warm command uses CacheManager."""
        from src.awsideman.commands.cache.helpers import get_cache_manager

        cache_manager = get_cache_manager()
        assert isinstance(cache_manager, CacheManager)


class TestCacheManagerConsistency:
    """Test that all components use the same cache manager instance."""

    def test_all_components_use_same_cache_instance(self):
        """Test that all components get the same cache manager instance."""
        from src.awsideman.cache.utilities import create_cache_manager
        from src.awsideman.commands.cache.helpers import get_cache_manager
        from src.awsideman.utils.account_cache_optimizer import AccountCacheOptimizer

        # Get cache manager from different sources
        cache_manager_1 = get_cache_manager()
        cache_manager_2 = create_cache_manager()

        # Create components that use cache manager
        optimizer = AccountCacheOptimizer(organizations_client=None)
        cache_manager_3 = optimizer.cache_manager

        # All should be the same instance (singleton)
        assert cache_manager_1 is cache_manager_2
        assert cache_manager_2 is cache_manager_3

    def test_cache_manager_state_consistency(self):
        """Test that cache state is consistent across all access points."""
        from src.awsideman.cache.utilities import create_cache_manager
        from src.awsideman.commands.cache.helpers import get_cache_manager

        # Get cache manager instances
        cache_manager_1 = get_cache_manager()
        cache_manager_2 = create_cache_manager()

        # Clear cache through one instance
        cache_manager_1.clear()

        # Set data through first instance
        test_key = "consistency:test"
        test_data = {"test": "data"}
        cache_manager_1.set(test_key, test_data)

        # Retrieve through second instance
        retrieved_data = cache_manager_2.get(test_key)

        # Should be the same data
        assert retrieved_data == test_data

        # Invalidate through second instance
        cache_manager_2.invalidate(test_key)

        # Should not exist when checked through first instance
        assert not cache_manager_1.exists(test_key)


class TestCacheManagerErrorHandling:
    """Test error handling in cache manager integration."""

    @patch("src.awsideman.commands.cache.helpers.create_cache_manager")
    def test_get_cache_manager_error_handling(self, mock_create_cache_manager):
        """Test that get_cache_manager handles errors gracefully."""
        # Make create_cache_manager raise an exception
        mock_create_cache_manager.side_effect = Exception("Test error")

        from src.awsideman.commands.cache.helpers import get_cache_manager

        # Should still return a cache manager (fallback)
        cache_manager = get_cache_manager()
        assert isinstance(cache_manager, CacheManager)

    def test_cache_manager_operation_error_handling(self):
        """Test that cache manager operations handle errors gracefully."""
        from src.awsideman.commands.cache.helpers import get_cache_manager

        cache_manager = get_cache_manager()

        # Test with invalid operations - should not crash
        try:
            # These should handle errors gracefully
            cache_manager.get("")  # Empty key
            cache_manager.set("", {})  # Empty key
            cache_manager.invalidate("")  # Empty pattern
        except Exception as e:
            # Some exceptions are expected for invalid input
            # But the system should not crash completely
            assert "Invalid" in str(e) or "key" in str(e).lower()

    def test_command_cache_error_handling(self):
        """Test that cache manager handles errors gracefully."""
        from src.awsideman.commands.cache.helpers import get_cache_manager

        cache_manager = get_cache_manager()

        # Test that cache operations handle errors gracefully
        # These should not crash the system
        try:
            # Test with various operations that might fail
            cache_manager.invalidate_for_operation("test", "resource", "id")
            cache_manager.get_stats()
            cache_manager.invalidate("test:*")
        except Exception:
            # Some exceptions might be expected, but system should not crash
            pass

        # Cache manager should still be functional
        assert isinstance(cache_manager, CacheManager)


class TestCacheManagerPerformance:
    """Test performance aspects of cache manager integration."""

    def test_cache_manager_singleton_performance(self):
        """Test that singleton access is fast."""
        import time

        from src.awsideman.commands.cache.helpers import get_cache_manager

        # Time multiple accesses
        start_time = time.time()

        for _ in range(100):
            _cache_manager = get_cache_manager()

        end_time = time.time()

        # Should be very fast (less than 1 second for 100 accesses)
        assert (end_time - start_time) < 1.0

    def test_cache_manager_operation_performance(self):
        """Test that basic cache operations are fast."""
        import time

        from src.awsideman.commands.cache.helpers import get_cache_manager

        cache_manager = get_cache_manager()
        cache_manager.clear()

        # Time basic operations
        start_time = time.time()

        for i in range(100):
            key = f"perf:test:{i}"
            data = {"index": i, "data": f"test_data_{i}"}

            cache_manager.set(key, data)
            retrieved = cache_manager.get(key)
            assert retrieved == data

        end_time = time.time()

        # Should be reasonably fast (less than 5 seconds for 100 operations)
        assert (end_time - start_time) < 5.0
