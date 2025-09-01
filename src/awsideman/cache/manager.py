"""Unified cache manager implementation with singleton pattern."""

import fnmatch
import json
import logging
import os
import threading
import time
from datetime import timedelta
from typing import Any, Dict, List, Optional

from .errors import CacheBackendError, CacheKeyError, CircuitBreaker, GracefulDegradationMixin
from .interfaces import ICacheManager

logger = logging.getLogger(__name__)


class CacheManager(ICacheManager, GracefulDegradationMixin):
    """
    Unified cache manager with singleton pattern and thread-safe operations.

    This implementation provides a single, consistent cache manager instance
    across the entire system, eliminating the confusion of multiple cache managers.

    Features:
    - Thread-safe singleton pattern
    - In-memory storage with TTL support
    - Pattern-based invalidation
    - Statistics tracking
    - Automatic cleanup of expired entries
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """Singleton pattern implementation."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    # Store the kwargs for the first initialization
                    cls._init_kwargs = kwargs
            return cls._instance
        else:
            return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset the singleton instance for testing purposes."""
        with cls._lock:
            cls._instance = None
            # Clear _init_kwargs to ensure clean test state
            if hasattr(cls, "_init_kwargs"):
                delattr(cls, "_init_kwargs")

    def __init__(self, default_ttl: Optional[timedelta] = None, profile: Optional[str] = None):
        """
        Initialize the unified cache manager.

        Args:
            default_ttl: Default TTL for cache entries. Defaults to 15 minutes.
            profile: AWS profile name for isolation
        """
        # Only initialize once (singleton pattern)
        if hasattr(self, "_initialized"):
            return

        # Initialize graceful degradation mixin
        super().__init__()

        self._initialized = True
        self._lock = threading.RLock()  # Reentrant lock for nested operations
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._profile = profile

        # Always use the stored kwargs from first creation for consistency
        if hasattr(self.__class__, "_init_kwargs") and self.__class__._init_kwargs:
            stored_ttl = self.__class__._init_kwargs.get("default_ttl")
            self._default_ttl = stored_ttl or timedelta(minutes=15)
        else:
            self._default_ttl = default_ttl or timedelta(minutes=15)

        # Initialize persistent backend (file backend by default)
        self._backend = None
        self._initialize_backend()

        # Circuit breaker for cache operations
        # Use shorter recovery timeout for testing
        recovery_timeout = 0.1 if os.getenv("PYTEST_CURRENT_TEST") else 60
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=recovery_timeout,
            expected_exception=CacheBackendError,
            success_threshold=3,
        )

        # Statistics tracking
        self._stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "invalidations": 0,
            "clears": 0,
            "errors": 0,
        }

        # Configuration attributes for compatibility
        self._config = self._create_compatibility_config()

        logger.debug("CacheManager initialized as singleton")

    def _initialize_backend(self) -> None:
        """Initialize the persistent cache backend."""
        try:
            from .backends.file import FileBackend

            # Create file backend with profile-specific cache directory
            self._backend = FileBackend(profile=self._profile)
            logger.info(
                f"Initialized file backend for persistent caching (profile: {self._profile or 'default'})"
            )

        except Exception as e:
            logger.warning(f"Failed to initialize file backend: {e}")
            logger.info("Falling back to in-memory only caching")
            self._backend = None

    def _create_compatibility_config(self) -> Any:
        """Create a compatibility config object for backward compatibility."""

        class CompatibilityConfig:
            def __init__(self, manager):
                self._manager = manager
                self.enabled = True  # Always enabled for CacheManager
                self.backend_type = "file" if manager._backend else "memory"
                self.default_ttl = int(self._manager._default_ttl.total_seconds())
                self.max_size_mb = 100  # Default 100MB limit
                self.max_size = 1000  # Default 1000 entries limit

            @property
            def backend_type(self):
                return self._backend_type

            @backend_type.setter
            def backend_type(self, value):
                self._backend_type = value

            @property
            def enabled(self):
                return self._enabled

            @enabled.setter
            def enabled(self, value):
                self._enabled = value

            @property
            def encryption_enabled(self):
                """Dynamically check if backend has encryption enabled."""
                if self._manager._backend and hasattr(self._manager._backend, "get_stats"):
                    try:
                        backend_stats = self._manager._backend.get_stats()
                        if backend_stats.get("total_entries", 0) > 0:
                            # Sample a few files to check encryption status
                            if hasattr(self._manager._backend, "path_manager"):
                                cache_files = self._manager._backend.path_manager.list_cache_files()
                                for cache_file in cache_files[:3]:  # Check first 3 files
                                    try:
                                        with open(cache_file, "rb") as f:
                                            file_content = f.read()
                                        if len(file_content) >= 4:
                                            metadata_length = int.from_bytes(
                                                file_content[:4], byteorder="big"
                                            )
                                            if metadata_length > 0 and metadata_length < len(
                                                file_content
                                            ):
                                                metadata_json = file_content[
                                                    4 : 4 + metadata_length
                                                ]
                                                metadata = json.loads(metadata_json.decode("utf-8"))
                                                if metadata.get("encrypted", False):
                                                    return True
                                    except Exception:
                                        continue
                    except Exception:
                        pass
                return False

            @encryption_enabled.setter
            def encryption_enabled(self, value):
                # Read-only property, ignore setter
                pass

            @property
            def encryption_type(self):
                """Dynamically check encryption type."""
                if self.encryption_enabled:
                    return "aes"
                return "none"

            @encryption_type.setter
            def encryption_type(self, value):
                # Read-only property, ignore setter
                pass

            @property
            def default_ttl(self):
                return self._default_ttl

            @default_ttl.setter
            def default_ttl(self, value):
                self._default_ttl = value

            @property
            def max_size_mb(self):
                return self._max_size_mb

            @max_size_mb.setter
            def max_size_mb(self, value):
                self._max_size_mb = value

            @property
            def max_size(self):
                return self._max_size

            @max_size.setter
            def max_size(self, value):
                self._max_size = value

        return CompatibilityConfig(self)

    @property
    def config(self):
        """Get the compatibility configuration object."""
        return self._config

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics for monitoring (compatibility method).

        Returns:
            Dictionary containing cache statistics compatible with existing commands
        """
        try:
            with self._lock:
                current_time = time.time()

                # Count expired entries
                expired_count = 0
                total_entries = len(self._cache)

                # Also count entries from backend if available
                backend_entries = 0
                backend_size_bytes = 0
                backend_size_mb = 0
                if self._backend and hasattr(self._backend, "get_stats"):
                    try:
                        backend_stats = self._backend.get_stats()
                        backend_entries = backend_stats.get("total_entries", 0)
                        backend_size_bytes = backend_stats.get("total_size_bytes", 0)
                        backend_size_mb = backend_stats.get("total_size_mb", 0)
                        total_entries += backend_entries
                        logger.debug(
                            f"Backend stats: {backend_stats}, backend_entries: {backend_entries}, total_entries: {total_entries}"
                        )
                    except Exception as e:
                        logger.debug(f"Failed to get backend stats: {e}")
                else:
                    logger.debug(
                        f"No backend or get_stats method: backend={self._backend}, has_get_stats={hasattr(self._backend, 'get_stats') if self._backend else False}"
                    )

                for entry in self._cache.values():
                    if current_time > entry["expires_at"]:
                        expired_count += 1

                # Calculate hit rate
                total_requests = self._stats["hits"] + self._stats["misses"]
                hit_rate = (
                    (self._stats["hits"] / total_requests * 100) if total_requests > 0 else 0.0
                )

                # Get circuit breaker stats
                circuit_stats = self._circuit_breaker.get_stats()

                # Get degradation stats
                degradation_stats = self.get_degradation_stats()

                # Return compatibility format
                return {
                    "enabled": True,  # CacheManager is always enabled
                    "backend_type": "file" if self._backend else "memory",
                    "total_entries": total_entries,
                    "valid_entries": total_entries - expired_count,
                    "expired_entries": expired_count,
                    "corrupted_entries": 0,  # Not applicable for memory backend
                    "hits": self._stats["hits"],
                    "misses": self._stats["misses"],
                    "sets": self._stats["sets"],
                    "invalidations": self._stats["invalidations"],
                    "clears": self._stats["clears"],
                    "errors": self._stats["errors"],
                    "hit_rate": hit_rate,
                    "hit_rate_percentage": round(hit_rate, 2),
                    "default_ttl": int(self._default_ttl.total_seconds()),
                    "max_size_mb": 100,  # Default value
                    "total_size_mb": backend_size_mb,  # From backend
                    "total_size_bytes": backend_size_bytes,  # From backend
                    "circuit_breaker": circuit_stats,
                    "degradation": degradation_stats,
                }
        except Exception as e:
            logger.error(f"Failed to get cache statistics: {e}")
            return {
                "enabled": True,
                "backend_type": "memory",
                "error": str(e),
                "total_entries": 0,
                "valid_entries": 0,
                "expired_entries": 0,
                "corrupted_entries": 0,
                "hits": 0,
                "misses": 0,
                "sets": 0,
                "invalidations": 0,
                "clears": 0,
                "errors": 1,
                "hit_rate": 0.0,
                "hit_rate_percentage": 0.0,
                "default_ttl": int(self._default_ttl.total_seconds()),
                "max_size_mb": 100,
                "total_size_mb": 0,
                "total_size_bytes": 0,
                "circuit_breaker": self._circuit_breaker.get_stats(),
                "degradation": self.get_degradation_stats(),
            }

    def get_backend(self) -> Optional[Any]:
        """
        Get the cache backend for compatibility with cache commands.

        Returns:
            Cache backend instance if available, None otherwise
        """
        return self._backend

    def get_cache_size_info(self) -> Dict[str, Any]:
        """
        Get cache size information for monitoring (compatibility method).

        Returns:
            Dictionary containing cache size information
        """
        try:
            with self._lock:
                total_entries = len(self._cache)
                max_entries = self._config.max_size
                usage_percentage = (total_entries / max_entries * 100) if max_entries > 0 else 0

                return {
                    "total_entries": total_entries,
                    "max_entries": max_entries,
                    "usage_percentage": round(usage_percentage, 2),
                    "is_over_limit": total_entries > max_entries,
                    "bytes_over_limit": 0,  # Not applicable for memory backend
                    "available_space_mb": 100,  # Default value
                    "used_space_mb": 0,  # Not applicable for memory backend
                    "free_space_mb": 100,  # Default value
                }
        except Exception as e:
            logger.error(f"Failed to get cache size info: {e}")
            return {
                "total_entries": 0,
                "max_entries": 1000,
                "usage_percentage": 0.0,
                "is_over_limit": False,
                "bytes_over_limit": 0,
                "available_space_mb": 100,
                "used_space_mb": 0,
                "free_space_mb": 100,
            }

    def get_recent_entries(self, limit: int = 10) -> list:
        """
        Get recent cache entries for display (compatibility method).

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of recent cache entries with metadata
        """
        try:
            with self._lock:
                current_time = time.time()
                recent_entries = []

                # First, get entries from in-memory cache
                for key, entry in self._cache.items():
                    if current_time <= entry["expires_at"]:  # Only show non-expired entries
                        recent_entries.append(
                            {
                                "key": key,
                                "created_at": entry["created_at"],
                                "expires_at": entry["expires_at"],
                                "ttl": str(
                                    int(entry["ttl"])
                                ),  # Convert to string to avoid rendering issues
                                "size": str(
                                    len(str(entry["data"])) if entry["data"] else "0"
                                ),  # Convert to string
                                "age": str(
                                    int(time.time() - entry["created_at"])
                                ),  # Convert to string
                            }
                        )

                # If we have a backend, also get entries from there
                if self._backend and hasattr(self._backend, "path_manager"):
                    try:
                        # Get actual cache files from the backend
                        cache_files = self._backend.path_manager.list_cache_files()
                        # Sort files by modification time (newest first) and process more than limit to account for parsing failures
                        cache_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
                        for cache_file in cache_files[
                            : limit * 2
                        ]:  # Process more files to account for parsing failures
                            try:
                                # Read the cache file directly to get metadata
                                with open(cache_file, "rb") as f:
                                    file_content = f.read()

                                # Parse the metadata from the JSON header
                                import json

                                if len(file_content) >= 4:
                                    try:
                                        # Try to read metadata length
                                        metadata_length = int.from_bytes(
                                            file_content[:4], byteorder="big"
                                        )
                                        if metadata_length > 0 and metadata_length < len(
                                            file_content
                                        ):
                                            # Parse metadata JSON
                                            metadata_json = file_content[4 : 4 + metadata_length]
                                            metadata = json.loads(metadata_json.decode("utf-8"))

                                            # Extract key from metadata
                                            key = metadata.get("key", cache_file.stem)
                                            created_at = metadata.get("created_at", time.time())
                                            ttl = metadata.get("ttl", 900)

                                            # Calculate expiration and age
                                            expires_at = created_at + ttl
                                            age = int(time.time() - created_at)

                                            # Add the actual cache entry
                                            recent_entries.append(
                                                {
                                                    "key": key,
                                                    "created_at": created_at,
                                                    "expires_at": expires_at,
                                                    "ttl": str(ttl),
                                                    "size": str(
                                                        metadata.get("data_size", "unknown")
                                                    ),
                                                    "age": str(age),
                                                }
                                            )
                                    except (ValueError, json.JSONDecodeError, KeyError) as e:
                                        logger.debug(
                                            f"Failed to parse metadata for {cache_file}: {e}"
                                        )
                                        # Fall back to basic entry
                                        recent_entries.append(
                                            {
                                                "key": cache_file.stem,
                                                "created_at": time.time(),
                                                "expires_at": time.time() + 3600,
                                                "ttl": "3600",
                                                "size": "unknown",
                                                "age": "0",
                                            }
                                        )
                                else:
                                    # Fall back to basic entry if file is too short
                                    recent_entries.append(
                                        {
                                            "key": cache_file.stem,
                                            "created_at": time.time(),
                                            "expires_at": time.time() + 3600,
                                            "ttl": "3600",
                                            "size": "unknown",
                                            "age": "0",
                                        }
                                    )
                            except Exception as e:
                                logger.debug(f"Failed to read cache file {cache_file}: {e}")
                                # Add a basic entry if we can't read the full data
                                recent_entries.append(
                                    {
                                        "key": cache_file.stem,
                                        "created_at": time.time(),
                                        "expires_at": time.time() + 3600,
                                        "ttl": "3600",
                                        "size": "unknown",
                                        "age": "0",
                                    }
                                )
                    except Exception as e:
                        logger.debug(f"Failed to get backend cache files: {e}")

                # Sort by creation time (newest first)
                recent_entries.sort(key=lambda x: x["created_at"], reverse=True)

                # Limit results
                return recent_entries[:limit]

        except Exception as e:
            logger.error(f"Failed to get recent entries: {e}")
            return []

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve cached data by key.

        Args:
            key: Cache key to retrieve

        Returns:
            Cached data if found and not expired, None otherwise

        Raises:
            CacheKeyError: If key format is invalid
            CacheBackendError: If cache operation fails
        """
        if not key or not isinstance(key, str):
            raise CacheKeyError(f"Invalid cache key: {key}")

        def cache_operation():
            return self._circuit_breaker.call(self._get_internal, key)

        def fallback_operation():
            logger.warning(f"Cache get failed for key {key}, returning None")
            return None

        return self.with_graceful_degradation(cache_operation, fallback_operation)

    def _get_internal(self, key: str) -> Optional[Any]:
        """Internal get operation without circuit breaker."""
        with self._lock:
            # First check in-memory cache
            if key in self._cache:
                entry = self._cache[key]
                current_time = time.time()

                if current_time > entry["expires_at"]:
                    # Entry has expired, remove it
                    del self._cache[key]
                    self._stats["misses"] += 1
                    return None

                self._stats["hits"] += 1
                return entry["data"]

            # If not in memory, try backend
            if self._backend:
                try:
                    import pickle

                    backend_data = self._backend.get(key)
                    if backend_data:
                        # Parse the backend data
                        entry_data = pickle.loads(backend_data)
                        # Store in memory for faster access
                        self._cache[key] = entry_data
                        self._stats["hits"] += 1
                        return entry_data["data"]
                except Exception as e:
                    logger.debug(f"Backend get failed for key {key}: {e}")

            self._stats["misses"] += 1
            return None

    def set(self, key: str, data: Any, ttl: Optional[timedelta] = None) -> None:
        """
        Store data in cache with optional TTL.

        Args:
            key: Cache key to store data under
            data: Data to cache
            ttl: Optional TTL override. If None, uses default TTL.

        Raises:
            CacheKeyError: If key format is invalid
            CacheBackendError: If cache operation fails
        """
        if not key or not isinstance(key, str):
            raise CacheKeyError(f"Invalid cache key: {key}")

        def cache_operation():
            return self._circuit_breaker.call(self._set_internal, key, data, ttl)

        def fallback_operation():
            logger.warning(f"Cache set failed for key {key}, operation skipped")

        self.with_graceful_degradation(cache_operation, fallback_operation)

    def _set_internal(self, key: str, data: Any, ttl: Optional[timedelta] = None) -> None:
        """Internal set operation without circuit breaker."""
        with self._lock:
            # Use provided TTL or default
            entry_ttl = ttl or self._default_ttl
            expires_at = time.time() + entry_ttl.total_seconds()

            entry_data = {
                "data": data,
                "expires_at": expires_at,
                "created_at": time.time(),
                "ttl": entry_ttl.total_seconds(),
            }

            # Store in memory for fast access
            self._cache[key] = entry_data

            # Also store in backend for persistence
            if self._backend:
                try:
                    import pickle

                    backend_data = pickle.dumps(entry_data)
                    self._backend.set(key, backend_data, ttl=int(entry_ttl.total_seconds()))
                except Exception as e:
                    logger.debug(f"Backend set failed for key {key}: {e}")

            self._stats["sets"] += 1

            # Clean up expired entries periodically
            if len(self._cache) % 10 == 0:  # Every 10th operation
                self.cleanup_expired()

    def invalidate(self, pattern: str) -> int:
        """
        Invalidate cache entries matching pattern.

        Args:
            pattern: Pattern to match cache keys (supports wildcards)

        Returns:
            Number of invalidated entries

        Raises:
            CacheKeyError: If pattern format is invalid
            CacheBackendError: If cache operation fails
        """
        if not pattern or not isinstance(pattern, str):
            raise CacheKeyError(f"Invalid pattern: {pattern}")

        def cache_operation():
            return self._circuit_breaker.call(self._invalidate_internal, pattern)

        def fallback_operation():
            logger.warning(f"Cache invalidation failed for pattern {pattern}, returning 0")
            return 0

        return self.with_graceful_degradation(cache_operation, fallback_operation)

    def _invalidate_internal(self, pattern: str) -> int:
        """Internal invalidate operation without circuit breaker."""
        with self._lock:
            keys_to_remove = []

            # If pattern is "*", clear everything including backend
            if pattern == "*":
                # Clear in-memory cache
                keys_to_remove = list(self._cache.keys())
                self._cache.clear()

                # Also clear the persistent backend if available
                if self._backend and hasattr(self._backend, "invalidate"):
                    try:
                        # Invalidate all entries in the backend
                        self._backend.invalidate()
                        logger.info("Cleared backend cache")
                    except Exception as e:
                        logger.warning(f"Failed to clear backend cache: {e}")

                removed_count = len(keys_to_remove)
                if removed_count > 0:
                    self._stats["invalidations"] += removed_count
                    logger.debug(f"Invalidated {removed_count} cache entries and cleared backend")

                return removed_count

            # For pattern-based invalidation, we need to check both in-memory and backend
            # First, collect all keys that match the pattern from in-memory cache
            for key in self._cache.keys():
                if fnmatch.fnmatch(key, pattern):
                    keys_to_remove.append(key)

            # Also check backend for matching keys if it supports listing
            if self._backend:
                try:
                    # Get all keys from backend and check for matches
                    backend_keys = self._get_backend_keys()
                    for key in backend_keys:
                        if fnmatch.fnmatch(key, pattern) and key not in keys_to_remove:
                            keys_to_remove.append(key)
                except Exception as e:
                    logger.debug(f"Could not get backend keys for pattern matching: {e}")

            # Remove matching entries from both in-memory cache and backend
            for key in keys_to_remove:
                # Remove from in-memory cache if present
                if key in self._cache:
                    del self._cache[key]

                # Remove from backend if available
                if self._backend and hasattr(self._backend, "invalidate"):
                    try:
                        self._backend.invalidate(key)
                        logger.debug(f"Invalidated backend entry for key: {key}")
                    except Exception as e:
                        logger.debug(f"Failed to invalidate backend entry for key {key}: {e}")

            removed_count = len(keys_to_remove)
            if removed_count > 0:
                self._stats["invalidations"] += removed_count
                logger.debug(
                    f"Invalidated {removed_count} cache entries matching pattern: {pattern}"
                )

            return removed_count

    def _get_backend_keys(self) -> List[str]:
        """
        Get all cache keys from the backend.

        Returns:
            List of cache keys from the backend
        """
        if not self._backend:
            return []

        try:
            # For file backend, we need to read the metadata from each file to get the original key
            if hasattr(self._backend, "path_manager"):
                cache_files = self._backend.path_manager.list_cache_files()
                keys = []
                for cache_file in cache_files:
                    try:
                        # Read the cache file to extract the original key from metadata
                        with open(cache_file, "rb") as f:
                            file_content = f.read()

                        # Check if it's the new format with metadata
                        if len(file_content) >= 4:
                            metadata_length = int.from_bytes(file_content[:4], byteorder="big")
                            if metadata_length > 0 and metadata_length < len(file_content):
                                metadata_json = file_content[4 : 4 + metadata_length]
                                metadata = json.loads(metadata_json.decode("utf-8"))
                                if "key" in metadata:
                                    keys.append(metadata["key"])
                                    continue

                        # For legacy format, we can't easily get the key, so skip
                        logger.debug(f"Could not extract key from legacy cache file {cache_file}")

                    except Exception as e:
                        logger.debug(f"Could not read cache file {cache_file}: {e}")
                return keys

            # If we can't list keys, return empty list
            logger.debug("Backend does not support key listing")
            return []

        except Exception as e:
            logger.debug(f"Failed to get backend keys: {e}")
            return []

    def clear(self) -> None:
        """
        Clear all cache entries (emergency use only).

        Raises:
            CacheBackendError: If cache operation fails
        """

        def cache_operation():
            return self._circuit_breaker.call(self._clear_internal)

        def fallback_operation():
            logger.warning("Cache clear failed, operation skipped")

        self.with_graceful_degradation(cache_operation, fallback_operation)

    def _clear_internal(self) -> None:
        """Internal clear operation without circuit breaker."""
        with self._lock:
            cleared_count = len(self._cache)

            # Clear in-memory cache
            self._cache.clear()

            # Also clear the persistent backend if available
            if self._backend and hasattr(self._backend, "invalidate"):
                try:
                    # Invalidate all entries in the backend
                    self._backend.invalidate()
                    logger.info("Cleared backend cache")
                except Exception as e:
                    logger.warning(f"Failed to clear backend cache: {e}")

            self._stats["clears"] += 1
            logger.info(f"Cleared {cleared_count} in-memory cache entries and backend cache")

    def exists(self, key: str) -> bool:
        """
        Check if key exists in cache.

        Args:
            key: Cache key to check

        Returns:
            True if key exists and is not expired, False otherwise

        Raises:
            CacheKeyError: If key format is invalid
            CacheBackendError: If cache operation fails
        """
        if not key or not isinstance(key, str):
            raise CacheKeyError(f"Invalid cache key: {key}")

        def cache_operation():
            return self._circuit_breaker.call(self._exists_internal, key)

        def fallback_operation():
            logger.warning(f"Cache exists check failed for key {key}, returning False")
            return False

        return self.with_graceful_degradation(cache_operation, fallback_operation)

    def _exists_internal(self, key: str) -> bool:
        """Internal exists check without circuit breaker."""
        with self._lock:
            if key not in self._cache:
                return False

            entry = self._cache[key]
            current_time = time.time()

            if current_time > entry["expires_at"]:
                # Entry has expired, remove it
                del self._cache[key]
                return False

            return True

    def get_stats(self) -> dict:
        """
        Get cache statistics for monitoring.

        Returns:
            Dictionary containing cache statistics
        """
        try:
            with self._lock:
                current_time = time.time()

                # Count expired entries
                expired_count = 0
                total_entries = len(self._cache)

                for entry in self._cache.values():
                    if current_time > entry["expires_at"]:
                        expired_count += 1

                # Calculate hit rate
                total_requests = self._stats["hits"] + self._stats["misses"]
                hit_rate = (
                    (self._stats["hits"] / total_requests * 100) if total_requests > 0 else 0.0
                )

                # Get circuit breaker stats
                circuit_stats = self._circuit_breaker.get_stats()

                # Get degradation stats
                degradation_stats = self.get_degradation_stats()

                return {
                    "total_entries": total_entries,
                    "expired_entries": expired_count,
                    "active_entries": total_entries - expired_count,
                    "hits": self._stats["hits"],
                    "misses": self._stats["misses"],
                    "sets": self._stats["sets"],
                    "invalidations": self._stats["invalidations"],
                    "clears": self._stats["clears"],
                    "errors": self._stats["errors"],
                    "hit_rate_percentage": round(hit_rate, 2),
                    "default_ttl_seconds": self._default_ttl.total_seconds(),
                    "circuit_breaker": circuit_stats,
                    "degradation": degradation_stats,
                }
        except Exception as e:
            logger.error(f"Failed to get cache statistics: {e}")
            return {
                "error": str(e),
                "circuit_breaker": self._circuit_breaker.get_stats(),
                "degradation": self.get_degradation_stats(),
            }

    def cleanup_expired(self) -> int:
        """
        Remove expired entries from cache.

        Returns:
            Number of expired entries removed
        """
        with self._lock:
            current_time = time.time()
            keys_to_remove = []

            for key, entry in self._cache.items():
                if current_time > entry["expires_at"]:
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                del self._cache[key]

            removed_count = len(keys_to_remove)
            if removed_count > 0:
                logger.debug(f"Cleaned up {removed_count} expired cache entries")

            return removed_count

    def get_cache_size(self) -> int:
        """
        Get current number of cache entries.

        Returns:
            Number of entries in cache
        """
        with self._lock:
            return len(self._cache)

    def get_keys_matching(self, pattern: str) -> list:
        """
        Get list of cache keys matching pattern.

        Args:
            pattern: Pattern to match cache keys

        Returns:
            List of matching cache keys
        """
        with self._lock:
            matching_keys = []
            for key in self._cache.keys():
                if fnmatch.fnmatch(key, pattern):
                    matching_keys.append(key)
            return matching_keys

    def invalidate_for_operation(
        self,
        operation_type: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        additional_context: Optional[Dict[str, str]] = None,
    ) -> int:
        """
        Invalidate cache based on operation type and resource using the invalidation engine.

        This method provides a convenient way to invalidate cache entries based on
        AWS operations without needing to directly instantiate the invalidation engine.

        Args:
            operation_type: Type of operation (create, update, delete, etc.)
            resource_type: Type of resource (user, group, permission_set, assignment)
            resource_id: Specific resource identifier (optional)
            additional_context: Additional context for complex invalidations

        Returns:
            Total number of invalidated cache entries
        """
        # Import here to avoid circular imports
        from .invalidation import CacheInvalidationEngine

        engine = CacheInvalidationEngine(self)
        return engine.invalidate_for_operation(
            operation_type, resource_type, resource_id, additional_context
        )

    def get_circuit_breaker_stats(self) -> dict:
        """
        Get circuit breaker statistics.

        Returns:
            Dictionary containing circuit breaker statistics
        """
        return self._circuit_breaker.get_stats()

    def reset_circuit_breaker(self) -> None:
        """
        Manually reset the circuit breaker (for admin/testing purposes).
        """
        self._circuit_breaker.reset()
        logger.info("Circuit breaker manually reset")

    def is_circuit_breaker_open(self) -> bool:
        """
        Check if circuit breaker is currently open.

        Returns:
            True if circuit breaker is open, False otherwise
        """
        from .errors import CircuitBreakerState

        return self._circuit_breaker.state == CircuitBreakerState.OPEN
