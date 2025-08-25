"""Integration tests for the unified cache manager."""

from src.awsideman.cache import CacheManager, ICacheManager


class TestCacheManagerIntegration:
    """Test integration of unified cache manager with the cache module."""

    def setup_method(self):
        """Reset singleton and circuit breaker for each test."""
        CacheManager.reset_instance()

    def test_import_from_cache_module(self):
        """Test that CacheManager can be imported from cache module."""
        # This test verifies the __init__.py exports work correctly
        manager = CacheManager()
        assert manager is not None
        assert isinstance(manager, ICacheManager)

    def test_singleton_behavior_across_imports(self):
        """Test that singleton behavior works across different import paths."""
        from src.awsideman.cache import CacheManager as Manager1
        from src.awsideman.cache.manager import CacheManager as Manager2

        instance1 = Manager1()
        instance2 = Manager2()

        assert instance1 is instance2

    def test_interface_compliance(self):
        """Test that CacheManager implements ICacheManager interface."""
        manager = CacheManager()

        # Test all interface methods exist and work
        assert hasattr(manager, "get")
        assert hasattr(manager, "set")
        assert hasattr(manager, "invalidate")
        assert hasattr(manager, "clear")
        assert hasattr(manager, "exists")
        assert hasattr(manager, "get_stats")

        # Test basic functionality
        manager.set("test_key", "test_value")
        assert manager.get("test_key") == "test_value"
        assert manager.exists("test_key")

        invalidated = manager.invalidate("test_*")
        assert invalidated == 1
        assert not manager.exists("test_key")

    def test_hierarchical_cache_keys(self):
        """Test the hierarchical cache key structure as specified in design."""
        manager = CacheManager()

        # Test hierarchical key patterns as specified in the design
        test_keys = [
            "user:list:all",
            "user:describe:user-123",
            "group:list:all",
            "group:describe:group-456",
            "group:members:group-456",
            "permission_set:list:all",
            "assignment:list:account-789:permission-set-123",
        ]

        # Set data for all keys
        for key in test_keys:
            manager.set(key, f"data_for_{key}")

        # Test pattern-based invalidation
        user_invalidated = manager.invalidate("user:*")
        # Should invalidate user:list:all and user:describe:user-123
        # But there might be additional user keys from previous tests, so check >= 2
        assert user_invalidated >= 2, f"Expected at least 2 user keys, got {user_invalidated}"

        # Verify user keys are gone but others remain
        assert manager.get("user:list:all") is None
        assert manager.get("user:describe:user-123") is None
        assert manager.get("group:list:all") == "data_for_group:list:all"
        assert manager.get("group:describe:group-456") == "data_for_group:describe:group-456"

        # Test more specific pattern
        group_describe_invalidated = manager.invalidate("group:describe:*")
        assert group_describe_invalidated == 1

        # Verify only group describe is gone
        assert manager.get("group:describe:group-456") is None
        assert manager.get("group:list:all") == "data_for_group:list:all"
        assert manager.get("group:members:group-456") == "data_for_group:members:group-456"

    def test_performance_requirements(self):
        """Test that cache operations meet performance requirements."""
        import time

        manager = CacheManager()

        # Test cache hit performance (should be very fast)
        manager.set("perf_test", "test_data")

        start_time = time.time()
        for _ in range(1000):
            result = manager.get("perf_test")
            assert result == "test_data"
        hit_time = time.time() - start_time

        # Cache hits should be very fast (less than 100ms for 1000 operations)
        assert hit_time < 0.1, f"Cache hits took {hit_time:.3f}s, should be < 0.1s"

        # Test invalidation performance
        # Set up multiple entries
        for i in range(100):
            manager.set(f"perf_test_{i}", f"data_{i}")

        start_time = time.time()
        invalidated = manager.invalidate("perf_test_*")
        invalidation_time = time.time() - start_time

        # Invalidation should complete quickly (less than 100ms as per requirements)
        assert (
            invalidation_time < 0.1
        ), f"Invalidation took {invalidation_time:.3f}s, should be < 0.1s"
        assert (
            invalidated == 100
        )  # The 100 perf_test_* entries (original perf_test doesn't match pattern)

    def test_thread_safety_integration(self):
        """Test thread safety in a more realistic scenario."""
        import threading

        manager = CacheManager()
        results = {}
        errors = []

        def worker_thread(thread_id):
            try:
                # Simulate realistic cache operations
                for i in range(10):
                    key = f"thread_{thread_id}_item_{i}"
                    data = {"thread": thread_id, "item": i, "data": f"value_{i}"}

                    # Set data
                    manager.set(key, data)

                    # Get data back
                    retrieved = manager.get(key)
                    if retrieved != data:
                        errors.append(f"Data mismatch in thread {thread_id}, item {i}")

                    # Test pattern invalidation
                    if i == 5:  # Halfway through, invalidate some entries
                        manager.invalidate(f"thread_{thread_id}_item_[0-4]")

                results[thread_id] = "completed"
            except Exception as e:
                errors.append(f"Thread {thread_id} error: {e}")

        # Run multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=worker_thread, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Verify results
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 5
        for i in range(5):
            assert results[i] == "completed"
