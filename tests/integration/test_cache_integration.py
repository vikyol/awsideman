"""Simple integration tests for the unified cache system."""

import time
from datetime import timedelta

from src.awsideman.cache.manager import CacheManager


class TestCacheIntegration:
    """Test the unified cache system integration."""

    def setup_method(self):
        """Reset singleton for each test."""
        CacheManager.reset_instance()

    def test_cache_lifecycle_integration(self):
        """Test complete cache lifecycle with real operations."""
        manager = CacheManager()

        # Test basic operations
        manager.set("test_key", "test_value")
        result = manager.get("test_key")
        assert result == "test_value"

        # Test TTL expiration
        manager.set("expire_key", "expire_value", ttl=timedelta(seconds=0.1))
        assert manager.get("expire_key") == "expire_value"

        time.sleep(0.2)  # Wait for expiration
        assert manager.get("expire_key") is None

        # Test pattern invalidation
        manager.set("user:list:all", ["user1", "user2"])
        manager.set("user:describe:user1", {"id": "user1"})
        manager.set("group:list:all", ["group1"])

        # Invalidate user keys
        invalidated = manager.invalidate("user:*")
        assert invalidated >= 2

        # Verify invalidation
        assert manager.get("user:list:all") is None
        assert manager.get("user:describe:user1") is None
        assert manager.get("group:list:all") == ["group1"]

    def test_cache_stats_integration(self):
        """Test cache statistics integration."""
        manager = CacheManager()

        # Get initial stats
        initial_stats = manager.get_stats()
        assert initial_stats["hits"] == 0
        assert initial_stats["misses"] == 0
        assert initial_stats["sets"] == 0

        # Perform operations
        manager.set("stats_key", "stats_value")
        manager.get("stats_key")  # Hit
        manager.get("nonexistent")  # Miss

        # Check updated stats
        updated_stats = manager.get_stats()
        assert updated_stats["sets"] >= 1
        assert updated_stats["hits"] >= 1
        assert updated_stats["misses"] >= 1

    def test_circuit_breaker_integration(self):
        """Test circuit breaker integration."""
        manager = CacheManager()

        # Get initial circuit breaker state
        initial_state = manager.get_circuit_breaker_stats()
        assert initial_state["state"] == "closed"

        # Reset circuit breaker for testing
        manager.reset_circuit_breaker()

        # Verify reset
        reset_state = manager.get_circuit_breaker_stats()
        assert reset_state["state"] == "closed"
        assert reset_state["failure_count"] == 0

    def test_cache_clear_integration(self):
        """Test cache clear integration."""
        manager = CacheManager()

        # Set multiple entries
        manager.set("clear_key1", "value1")
        manager.set("clear_key2", "value2")
        manager.set("clear_key3", "value3")

        # Verify entries exist
        assert manager.get("clear_key1") == "value1"
        assert manager.get("clear_key2") == "value2"
        assert manager.get("clear_key3") == "value3"

        # Clear cache
        manager.clear()

        # Verify all entries are gone
        assert manager.get("clear_key1") is None
        assert manager.get("clear_key2") is None
        assert manager.get("clear_key3") is None

    def test_pattern_matching_integration(self):
        """Test pattern matching for cache operations."""
        manager = CacheManager()

        # Set entries with different patterns
        manager.set("user:list:all", ["user1", "user2"])
        manager.set("user:describe:user1", {"id": "user1"})
        manager.set("user:describe:user2", {"id": "user2"})
        manager.set("group:list:all", ["group1"])
        manager.set("permission:list:all", ["perm1"])

        # Test different pattern matches
        user_keys = manager.get_keys_matching("user:*")
        assert len(user_keys) >= 3

        describe_keys = manager.get_keys_matching("*:describe:*")
        assert len(describe_keys) >= 2

        # Test invalidation with patterns
        manager.invalidate("user:describe:*")
        assert manager.get("user:describe:user1") is None
        assert manager.get("user:describe:user2") is None
        assert manager.get("user:list:all") == ["user1", "user2"]  # Should remain

    def test_singleton_behavior_integration(self):
        """Test singleton behavior across different contexts."""
        manager1 = CacheManager()
        manager2 = CacheManager()

        # Verify singleton behavior
        assert manager1 is manager2

        # Set data in one instance
        manager1.set("singleton_key", "singleton_value")

        # Should be available in other instance
        result = manager2.get("singleton_key")
        assert result == "singleton_value"

        # Verify both instances share the same cache
        assert manager1.get_cache_size() == manager2.get_cache_size()
