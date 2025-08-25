"""Simple tests for the unified cache manager functionality."""

import time
from datetime import timedelta

from src.awsideman.cache.manager import CacheManager


class TestUnifiedCacheManager:
    """Test the unified cache manager functionality."""

    def setup_method(self):
        """Reset singleton for each test."""
        CacheManager.reset_instance()

    def test_basic_operations(self):
        """Test basic cache operations."""
        manager = CacheManager()

        # Test set and get
        manager.set("test_key", "test_value")
        result = manager.get("test_key")
        assert result == "test_value"

        # Test cache miss
        result = manager.get("nonexistent_key")
        assert result is None

    def test_ttl_expiration(self):
        """Test TTL expiration."""
        manager = CacheManager(default_ttl=timedelta(seconds=0.1))

        # Set data with very short TTL
        manager.set("expire_key", "expire_value")

        # Should be available immediately
        result = manager.get("expire_key")
        assert result == "expire_value"

        # Wait for expiration
        time.sleep(0.2)

        # Should be expired now
        result = manager.get("expire_key")
        assert result is None

    def test_pattern_invalidation(self):
        """Test pattern-based invalidation."""
        manager = CacheManager()

        # Set multiple keys
        manager.set("user:list:all", ["user1", "user2"])
        manager.set("user:describe:user1", {"id": "user1"})
        manager.set("group:list:all", ["group1", "group2"])

        # Invalidate all user keys
        invalidated = manager.invalidate("user:*")
        assert invalidated >= 2

        # User keys should be gone
        assert manager.get("user:list:all") is None
        assert manager.get("user:describe:user1") is None

        # Group keys should remain
        assert manager.get("group:list:all") == ["group1", "group2"]

    def test_singleton_behavior(self):
        """Test that cache manager is a singleton."""
        manager1 = CacheManager()
        manager2 = CacheManager()

        assert manager1 is manager2

        # Set data in one instance
        manager1.set("singleton_key", "singleton_value")

        # Should be available in other instance
        result = manager2.get("singleton_key")
        assert result == "singleton_value"

    def test_circuit_breaker(self):
        """Test circuit breaker functionality."""
        manager = CacheManager()

        # Get initial stats
        initial_stats = manager.get_circuit_breaker_stats()
        assert initial_stats["state"] == "closed"

        # Reset circuit breaker for testing
        manager.reset_circuit_breaker()

        # Verify reset
        reset_stats = manager.get_circuit_breaker_stats()
        assert reset_stats["state"] == "closed"
        assert reset_stats["failure_count"] == 0

    def test_cache_stats(self):
        """Test cache statistics."""
        manager = CacheManager()

        # Get initial stats
        stats = manager.get_stats()
        assert "hits" in stats
        assert "misses" in stats
        assert "sets" in stats

        # Perform operations
        manager.set("stats_key", "stats_value")
        manager.get("stats_key")  # Hit
        manager.get("nonexistent")  # Miss

        # Check updated stats
        updated_stats = manager.get_stats()
        assert updated_stats["sets"] >= 1
        assert updated_stats["hits"] >= 1
        assert updated_stats["misses"] >= 1

    def test_clear_cache(self):
        """Test clearing the cache."""
        manager = CacheManager()

        # Set some data
        manager.set("clear_key1", "value1")
        manager.set("clear_key2", "value2")

        # Verify data exists
        assert manager.get("clear_key1") == "value1"
        assert manager.get("clear_key2") == "value2"

        # Clear cache
        manager.clear()

        # Verify data is gone
        assert manager.get("clear_key1") is None
        assert manager.get("clear_key2") is None

    def test_exists_method(self):
        """Test the exists method."""
        manager = CacheManager()

        # Key doesn't exist initially
        assert not manager.exists("exists_key")

        # Set the key
        manager.set("exists_key", "exists_value")

        # Key should exist now
        assert manager.exists("exists_key")

        # Get keys matching pattern
        matching_keys = manager.get_keys_matching("exists_*")
        assert "exists_key" in matching_keys
