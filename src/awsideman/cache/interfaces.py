"""Cache manager interfaces for the unified cache system."""

import threading
from abc import ABC, abstractmethod
from datetime import timedelta
from typing import Any, Optional


class ICacheManager(ABC):
    """
    Interface for cache manager implementations.

    Defines the core operations that all cache managers must support
    for consistent behavior across the system.
    """

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve cached data by key.

        Args:
            key: Cache key to retrieve

        Returns:
            Cached data if found and not expired, None otherwise
        """
        pass

    @abstractmethod
    def set(self, key: str, data: Any, ttl: Optional[timedelta] = None) -> None:
        """
        Store data in cache with optional TTL.

        Args:
            key: Cache key to store data under
            data: Data to cache
            ttl: Optional TTL override. If None, uses default TTL.
        """
        pass

    @abstractmethod
    def invalidate(self, pattern: str) -> int:
        """
        Invalidate cache entries matching pattern.

        Args:
            pattern: Pattern to match cache keys (supports wildcards)

        Returns:
            Number of invalidated entries
        """
        pass

    @abstractmethod
    def clear(self) -> None:
        """
        Clear all cache entries (emergency use only).
        """
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """
        Check if key exists in cache.

        Args:
            key: Cache key to check

        Returns:
            True if key exists and is not expired, False otherwise
        """
        pass

    @abstractmethod
    def get_stats(self) -> dict:
        """
        Get cache statistics for monitoring.

        Returns:
            Dictionary containing cache statistics
        """
        pass


class SingletonABCMeta(type(ABC)):
    """
    Combined metaclass that supports both ABC and Singleton patterns.

    Ensures only one instance of the cache manager exists across the entire system
    while maintaining thread safety during initialization and supporting ABC.
    """

    _instances = {}
    _lock: threading.Lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        """
        Create or return existing singleton instance.

        Uses double-checked locking pattern for thread safety.
        """
        if cls not in cls._instances:
            with cls._lock:
                # Double-check pattern to avoid race conditions
                if cls not in cls._instances:
                    print(f"DEBUG: Creating new singleton instance for {cls.__name__}")
                    instance = super().__call__(*args, **kwargs)
                    cls._instances[cls] = instance
                    print(f"DEBUG: Stored singleton instance: {instance}")
                else:
                    print(f"DEBUG: Found existing singleton instance: {cls._instances[cls]}")
        else:
            print(f"DEBUG: Returning existing singleton instance: {cls._instances[cls]}")
        return cls._instances[cls]

    @classmethod
    def reset_instances(cls):
        """
        Reset all singleton instances (for testing only).

        This method should only be used in test environments
        to ensure clean state between tests.
        """
        with cls._lock:
            cls._instances.clear()


# Keep the old name for backward compatibility
SingletonMeta = SingletonABCMeta
