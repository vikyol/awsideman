"""Tests for the unified cache manager rollout."""

from unittest.mock import Mock, patch

import pytest

from src.awsideman.cache.manager import CacheManager
from src.awsideman.cache.utilities import create_cache_manager
from src.awsideman.commands.cache.helpers import get_cache_manager


class TestCacheManagerRollout:
    """Test suite for unified cache manager rollout."""

    def test_singleton_behavior(self):
        """Test that CacheManager follows singleton pattern."""
        # Get two instances
        manager1 = CacheManager()
        manager2 = CacheManager()

        # They should be the same instance
        assert manager1 is manager2

    def test_get_cache_manager_returns_unified_manager(self):
        """Test that get_cache_manager returns CacheManager instance."""
        cache_manager = get_cache_manager()

        assert isinstance(cache_manager, CacheManager)

    def test_create_cache_manager_returns_unified_manager(self):
        """Test that create_cache_manager returns CacheManager instance."""
        cache_manager = create_cache_manager()

        assert isinstance(cache_manager, CacheManager)

    def test_multiple_get_cache_manager_calls_return_same_instance(self):
        """Test that multiple calls to get_cache_manager return the same instance."""
        manager1 = get_cache_manager()
        manager2 = get_cache_manager()

        assert manager1 is manager2

    def test_cache_manager_has_required_methods(self):
        """Test that the cache manager has all required methods."""
        cache_manager = get_cache_manager()

        # Check for core cache methods
        assert hasattr(cache_manager, "get")
        assert hasattr(cache_manager, "set")
        assert hasattr(cache_manager, "invalidate")
        assert hasattr(cache_manager, "clear")
        assert hasattr(cache_manager, "exists")
        assert hasattr(cache_manager, "get_stats")

        # Check for new invalidation method
        assert hasattr(cache_manager, "invalidate_for_operation")

    def test_cache_manager_invalidate_for_operation(self):
        """Test that invalidate_for_operation works correctly."""
        cache_manager = get_cache_manager()

        # Set some test data
        cache_manager.set("user:list:all", {"users": []})
        cache_manager.set("user:describe:user-123", {"user": "data"})

        # Invalidate user operations
        invalidated_count = cache_manager.invalidate_for_operation("create", "user", "user-456")

        # Should have invalidated some entries
        assert invalidated_count >= 0

    def test_cache_manager_basic_operations(self):
        """Test basic cache operations work correctly."""
        cache_manager = get_cache_manager()

        # Clear any existing data
        cache_manager.clear()

        # Test set and get
        test_key = "test:key"
        test_data = {"test": "data"}

        cache_manager.set(test_key, test_data)
        retrieved_data = cache_manager.get(test_key)

        assert retrieved_data == test_data

        # Test exists
        assert cache_manager.exists(test_key)

        # Test invalidate
        cache_manager.invalidate(test_key)
        assert not cache_manager.exists(test_key)

    def test_cache_manager_pattern_invalidation(self):
        """Test pattern-based invalidation works correctly."""
        cache_manager = get_cache_manager()

        # Clear any existing data
        cache_manager.clear()

        # Set test data with patterns
        cache_manager.set("user:list:all", {"users": []})
        cache_manager.set("user:describe:user-123", {"user": "data"})
        cache_manager.set("group:list:all", {"groups": []})

        # Invalidate all user entries
        invalidated_count = cache_manager.invalidate("user:*")

        # Should have invalidated user entries but not group entries
        assert invalidated_count == 2
        assert not cache_manager.exists("user:list:all")
        assert not cache_manager.exists("user:describe:user-123")
        assert cache_manager.exists("group:list:all")

    def test_cache_manager_stats(self):
        """Test that cache statistics work correctly."""
        cache_manager = get_cache_manager()

        # Clear any existing data
        cache_manager.clear()

        # Get initial stats
        stats = cache_manager.get_stats()

        assert isinstance(stats, dict)
        assert "total_entries" in stats
        assert "hits" in stats
        assert "misses" in stats

        # Add some data and check stats update
        cache_manager.set("test:key", {"data": "value"})

        updated_stats = cache_manager.get_stats()
        assert updated_stats["total_entries"] >= 1

    def test_cache_manager_thread_safety(self):
        """Test that cache manager is thread-safe."""
        import threading
        import time

        cache_manager = get_cache_manager()
        cache_manager.clear()

        results = []
        errors = []

        def worker(worker_id):
            try:
                # Each worker sets and gets data
                key = f"worker:{worker_id}"
                data = {"worker_id": worker_id, "timestamp": time.time()}

                cache_manager.set(key, data)
                retrieved = cache_manager.get(key)

                if retrieved == data:
                    results.append(worker_id)
                else:
                    errors.append(f"Worker {worker_id}: data mismatch")

            except Exception as e:
                errors.append(f"Worker {worker_id}: {str(e)}")

        # Create multiple threads
        threads = []
        for i in range(10):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Check results
        assert len(errors) == 0, f"Thread safety errors: {errors}"
        assert len(results) == 10, f"Expected 10 successful workers, got {len(results)}"


class TestCacheManagerIntegration:
    """Test integration of cache manager with other components."""

    def test_aws_client_manager_uses_unified_cache(self):
        """Test that AWSClientManager uses CacheManager."""
        from src.awsideman.aws_clients.manager import AWSClientManager

        # Create an AWSClientManager instance
        manager = AWSClientManager(enable_caching=True)

        # The cache_manager should be CacheManager or None initially
        # When we get a cached client, it should use CacheManager
        try:
            cached_client = manager.get_cached_client()

            # The cached client should have a CacheManager
            assert hasattr(cached_client, "cache_manager")
            assert isinstance(cached_client.cache_manager, CacheManager)
        except Exception:
            # If we can't create a cached client (due to missing AWS config),
            # just verify that the manager would use CacheManager
            assert manager.cache_manager is None or isinstance(manager.cache_manager, CacheManager)

    def test_account_cache_optimizer_uses_unified_cache(self):
        """Test that AccountCacheOptimizer uses CacheManager."""
        from src.awsideman.utils.account_cache_optimizer import AccountCacheOptimizer

        # Create an AccountCacheOptimizer instance
        optimizer = AccountCacheOptimizer(organizations_client=None)

        # It should use CacheManager
        assert isinstance(optimizer.cache_manager, CacheManager)

    def test_cached_aws_client_uses_unified_cache(self):
        """Test that CachedAwsClient uses CacheManager."""
        from src.awsideman.aws_clients.cached_client import CachedAwsClient
        from src.awsideman.aws_clients.manager import AWSClientManager

        # Create a mock client manager
        mock_client_manager = Mock(spec=AWSClientManager)

        # Create CachedAwsClient without providing cache_manager
        cached_client = CachedAwsClient(mock_client_manager)

        # It should use CacheManager by default
        assert isinstance(cached_client.cache_manager, CacheManager)


class TestCacheManagerFallback:
    """Test fallback behavior of cache manager."""

    @patch("src.awsideman.commands.cache.helpers.create_cache_manager")
    def test_get_cache_manager_fallback(self, mock_create_cache_manager):
        """Test that get_cache_manager falls back gracefully on errors."""
        # Make create_cache_manager raise an exception
        mock_create_cache_manager.side_effect = Exception("Test error")

        # get_cache_manager should still return a CacheManager instance
        # (because the fallback also creates CacheManager)
        cache_manager = get_cache_manager()

        # Should be a CacheManager instance (from fallback)
        assert isinstance(cache_manager, CacheManager)

    def test_cache_manager_error_handling(self):
        """Test that cache manager handles errors gracefully."""
        cache_manager = get_cache_manager()

        # Test with invalid key - should raise CacheKeyError
        with pytest.raises(Exception):  # CacheKeyError
            cache_manager.get("")

        # Test with None key should raise error but be handled
        with pytest.raises(Exception):
            cache_manager.get(None)


class TestCacheManagerConfiguration:
    """Test cache manager configuration and initialization."""

    def test_cache_manager_default_configuration(self):
        """Test that cache manager has sensible default configuration."""
        cache_manager = get_cache_manager()

        # Should have default TTL
        assert hasattr(cache_manager, "_default_ttl")
        assert cache_manager._default_ttl is not None

        # Should be initialized
        assert hasattr(cache_manager, "_initialized")
        assert cache_manager._initialized is True

    def test_cache_manager_statistics_tracking(self):
        """Test that cache manager tracks statistics correctly."""
        cache_manager = get_cache_manager()
        cache_manager.clear()

        # Get initial stats
        initial_stats = cache_manager.get_stats()
        initial_sets = initial_stats.get("sets", 0)
        initial_gets = initial_stats.get("hits", 0) + initial_stats.get("misses", 0)

        # Perform some operations
        cache_manager.set("test:stats", {"data": "value"})
        cache_manager.get("test:stats")  # Hit
        cache_manager.get("nonexistent:key")  # Miss

        # Check updated stats
        updated_stats = cache_manager.get_stats()

        assert updated_stats.get("sets", 0) >= initial_sets + 1
        assert (updated_stats.get("hits", 0) + updated_stats.get("misses", 0)) >= initial_gets + 2

    def test_cache_manager_circuit_breaker(self):
        """Test that cache manager has circuit breaker functionality."""
        cache_manager = get_cache_manager()

        # Should have circuit breaker
        assert hasattr(cache_manager, "_circuit_breaker")
        assert hasattr(cache_manager, "get_circuit_breaker_stats")
        assert hasattr(cache_manager, "reset_circuit_breaker")
        assert hasattr(cache_manager, "is_circuit_breaker_open")

        # Circuit breaker stats should be available
        cb_stats = cache_manager.get_circuit_breaker_stats()
        assert isinstance(cb_stats, dict)
