"""Hybrid backend implementation combining file and DynamoDB backends."""

import logging
import time
from typing import Any, Dict, Optional

from .base import BackendHealthStatus, CacheBackend, CacheBackendError
from .dynamodb import DynamoDBBackend
from .file import FileBackend

logger = logging.getLogger(__name__)


class HybridBackend(CacheBackend):
    """
    Hybrid backend that combines local file and remote DynamoDB storage.

    Implements intelligent caching strategies:
    - Frequently accessed data is cached locally with configurable TTL
    - All data is stored in DynamoDB for sharing across machines
    - Local cache acts as a fast access layer
    - Automatic promotion/demotion based on access patterns
    """

    def __init__(
        self, local_backend: FileBackend, remote_backend: DynamoDBBackend, local_ttl: int = 300
    ):
        """
        Initialize hybrid backend.

        Args:
            local_backend: File backend for local caching
            remote_backend: DynamoDB backend for remote storage
            local_ttl: TTL for local cache entries in seconds (default: 5 minutes)
        """
        self.local_backend = local_backend
        self.remote_backend = remote_backend
        self.local_ttl = local_ttl
        self.backend_type = "hybrid"

        # Access tracking for promotion/demotion decisions
        self._access_counts = {}
        self._last_access_times = {}

        logger.debug(f"Initialized hybrid backend with local_ttl: {local_ttl}s")

    def get(self, key: str) -> Optional[bytes]:
        """
        Retrieve data from hybrid backend.

        Strategy:
        1. Check local cache first for fast access
        2. If not found locally, check remote DynamoDB
        3. If found remotely, promote to local cache based on access patterns
        4. Track access patterns for future promotion decisions

        Args:
            key: Cache key to retrieve

        Returns:
            Raw bytes data if found and not expired, None otherwise

        Raises:
            CacheBackendError: If both backends fail
        """
        try:
            # Track access for promotion/demotion decisions
            self._track_access(key)

            # First, try local cache for fast access
            try:
                local_data = self.local_backend.get(key)
                if local_data is not None:
                    logger.debug(f"Hybrid backend local cache hit for key: {key}")
                    return local_data
            except CacheBackendError as e:
                logger.warning(f"Local backend error during get for key {key}: {e}")
                # Continue to remote backend

            # If not in local cache, try remote DynamoDB
            try:
                remote_data = self.remote_backend.get(key)
                if remote_data is not None:
                    logger.debug(f"Hybrid backend remote cache hit for key: {key}")

                    # Consider promoting to local cache
                    if self._should_promote_to_local(key):
                        try:
                            self.local_backend.set(key, remote_data, self.local_ttl, "promotion")
                            logger.debug(f"Promoted key {key} to local cache")
                        except CacheBackendError as e:
                            logger.warning(f"Failed to promote key {key} to local cache: {e}")
                            # Don't fail the get operation if promotion fails

                    return remote_data
            except CacheBackendError as e:
                logger.warning(f"Remote backend error during get for key {key}: {e}")
                # Both backends failed, but we'll raise the remote error as it's more critical
                raise

            # Not found in either backend
            logger.debug(f"Hybrid backend cache miss for key: {key}")
            return None

        except CacheBackendError:
            # Re-raise cache backend errors
            raise
        except Exception as e:
            logger.error(f"Unexpected error in hybrid backend get for key {key}: {e}")
            raise CacheBackendError(
                f"Unexpected error in hybrid backend get: {e}",
                backend_type=self.backend_type,
                original_error=e,
            )

    def set(
        self, key: str, data: bytes, ttl: Optional[int] = None, operation: str = "unknown"
    ) -> None:
        """
        Store data to hybrid backend.

        Strategy:
        1. Always store to remote DynamoDB for persistence and sharing
        2. Store to local cache if data is likely to be accessed again soon
        3. Handle partial failures gracefully

        Args:
            key: Cache key to store data under
            data: Raw bytes data to store
            ttl: Optional TTL in seconds
            operation: AWS operation that generated this data

        Raises:
            CacheBackendError: If remote storage fails (local failures are logged but not raised)
        """
        try:
            # Always store to remote backend first (most important)
            remote_error = None
            try:
                self.remote_backend.set(key, data, ttl, operation)
                logger.debug(f"Stored key {key} to remote backend")
            except CacheBackendError as e:
                remote_error = e
                logger.error(f"Failed to store key {key} to remote backend: {e}")

            # Store to local cache if appropriate
            if self._should_cache_locally(key, operation):
                try:
                    # Use local TTL for local cache, but respect provided TTL if shorter
                    effective_local_ttl = self.local_ttl
                    if ttl is not None and ttl < self.local_ttl:
                        effective_local_ttl = ttl

                    self.local_backend.set(key, data, effective_local_ttl, operation)
                    logger.debug(
                        f"Stored key {key} to local backend with TTL: {effective_local_ttl}s"
                    )
                except CacheBackendError as e:
                    logger.warning(f"Failed to store key {key} to local backend: {e}")

            # If remote storage failed, raise error (local failure is not critical)
            if remote_error:
                raise remote_error

            # Track successful set operation
            self._track_access(key)

        except CacheBackendError:
            # Re-raise cache backend errors
            raise
        except Exception as e:
            logger.error(f"Unexpected error in hybrid backend set for key {key}: {e}")
            raise CacheBackendError(
                f"Unexpected error in hybrid backend set: {e}",
                backend_type=self.backend_type,
                original_error=e,
            )

    def invalidate(self, key: Optional[str] = None) -> None:
        """
        Remove cache entries from hybrid backend.

        Strategy:
        1. Invalidate from both local and remote backends
        2. Handle partial failures gracefully
        3. Clear access tracking data

        Args:
            key: Cache key to invalidate. If None, invalidates all cache entries.

        Raises:
            CacheBackendError: If both backends fail (partial failures are logged)
        """
        try:
            local_error = None
            remote_error = None

            # Invalidate from local backend
            try:
                self.local_backend.invalidate(key)
                logger.debug(f"Invalidated key {key} from local backend")
            except CacheBackendError as e:
                local_error = e
                logger.warning(f"Failed to invalidate key {key} from local backend: {e}")

            # Invalidate from remote backend
            try:
                self.remote_backend.invalidate(key)
                logger.debug(f"Invalidated key {key} from remote backend")
            except CacheBackendError as e:
                remote_error = e
                logger.warning(f"Failed to invalidate key {key} from remote backend: {e}")

            # Clear access tracking data
            if key is None:
                # Clear all tracking data
                self._access_counts.clear()
                self._last_access_times.clear()
                logger.debug("Cleared all access tracking data")
            else:
                # Clear tracking data for specific key
                self._access_counts.pop(key, None)
                self._last_access_times.pop(key, None)
                logger.debug(f"Cleared access tracking data for key: {key}")

            # If both backends failed, raise the more critical remote error
            if local_error and remote_error:
                logger.error(
                    f"Both backends failed during invalidation: local={local_error}, remote={remote_error}"
                )
                raise remote_error
            elif remote_error:
                raise remote_error
            # If only local failed, don't raise error as remote success is more important

        except CacheBackendError:
            # Re-raise cache backend errors
            raise
        except Exception as e:
            logger.error(f"Unexpected error in hybrid backend invalidate: {e}")
            raise CacheBackendError(
                f"Unexpected error in hybrid backend invalidate: {e}",
                backend_type=self.backend_type,
                original_error=e,
            )

    def get_stats(self) -> Dict[str, Any]:
        """
        Get hybrid backend statistics.

        Returns:
            Dictionary containing statistics from both backends plus hybrid-specific metrics

        Raises:
            CacheBackendError: If stats collection fails
        """
        try:
            stats = {
                "backend_type": self.backend_type,
                "local_ttl": self.local_ttl,
                "access_tracking": {
                    "tracked_keys": len(self._access_counts),
                    "total_accesses": sum(self._access_counts.values()),
                    "most_accessed_keys": self._get_most_accessed_keys(5),
                },
            }

            # Get local backend stats
            try:
                local_stats = self.local_backend.get_stats()
                stats["local_backend"] = local_stats
            except CacheBackendError as e:
                logger.warning(f"Failed to get local backend stats: {e}")
                stats["local_backend"] = {"error": str(e)}

            # Get remote backend stats
            try:
                remote_stats = self.remote_backend.get_stats()
                stats["remote_backend"] = remote_stats
            except CacheBackendError as e:
                logger.warning(f"Failed to get remote backend stats: {e}")
                stats["remote_backend"] = {"error": str(e)}

            # Calculate hybrid-specific metrics
            local_entries = stats.get("local_backend", {}).get("valid_entries", 0)
            remote_entries = stats.get("remote_backend", {}).get("item_count", 0)

            stats["cache_efficiency"] = {
                "local_entries": local_entries,
                "remote_entries": remote_entries,
                "local_hit_potential": (
                    f"{(local_entries / max(remote_entries, 1)) * 100:.1f}%"
                    if remote_entries > 0
                    else "0%"
                ),
            }

            return stats

        except Exception as e:
            logger.error(f"Failed to get hybrid backend stats: {e}")
            raise CacheBackendError(
                f"Failed to get hybrid backend stats: {e}",
                backend_type=self.backend_type,
                original_error=e,
            )

    def health_check(self) -> bool:
        """
        Check if hybrid backend is healthy.

        Returns:
            True if at least one backend is healthy, False if both are unhealthy
        """
        try:
            local_healthy = False
            remote_healthy = False

            # Check local backend health
            try:
                local_healthy = self.local_backend.health_check()
            except Exception as e:
                logger.warning(f"Local backend health check failed: {e}")

            # Check remote backend health
            try:
                remote_healthy = self.remote_backend.health_check()
            except Exception as e:
                logger.warning(f"Remote backend health check failed: {e}")

            # Hybrid backend is healthy if at least one backend is healthy
            is_healthy = local_healthy or remote_healthy

            if is_healthy:
                logger.debug(
                    f"Hybrid backend health check passed (local: {local_healthy}, remote: {remote_healthy})"
                )
            else:
                logger.error("Hybrid backend health check failed - both backends are unhealthy")

            return is_healthy

        except Exception as e:
            logger.error(f"Hybrid backend health check failed with unexpected error: {e}")
            return False

    def get_detailed_health_status(self) -> BackendHealthStatus:
        """
        Get detailed health status of the hybrid backend.

        Returns:
            BackendHealthStatus object with detailed information
        """
        start_time = time.time()

        try:
            # Check both backends
            local_status = None
            remote_status = None

            try:
                if hasattr(self.local_backend, "get_detailed_health_status"):
                    local_status = self.local_backend.get_detailed_health_status()
                else:
                    local_healthy = self.local_backend.health_check()
                    local_status = BackendHealthStatus(
                        is_healthy=local_healthy,
                        backend_type="file",
                        message="Local backend health check completed",
                    )
            except Exception as e:
                local_status = BackendHealthStatus(
                    is_healthy=False,
                    backend_type="file",
                    message=f"Local backend health check failed: {e}",
                    error=e,
                )

            try:
                if hasattr(self.remote_backend, "get_detailed_health_status"):
                    remote_status = self.remote_backend.get_detailed_health_status()
                else:
                    remote_healthy = self.remote_backend.health_check()
                    remote_status = BackendHealthStatus(
                        is_healthy=remote_healthy,
                        backend_type="dynamodb",
                        message="Remote backend health check completed",
                    )
            except Exception as e:
                remote_status = BackendHealthStatus(
                    is_healthy=False,
                    backend_type="dynamodb",
                    message=f"Remote backend health check failed: {e}",
                    error=e,
                )

            # Determine overall health
            is_healthy = local_status.is_healthy or remote_status.is_healthy

            # Create status message
            if local_status.is_healthy and remote_status.is_healthy:
                message = "Both local and remote backends are healthy"
            elif local_status.is_healthy:
                message = (
                    f"Local backend healthy, remote backend unhealthy: {remote_status.message}"
                )
            elif remote_status.is_healthy:
                message = f"Remote backend healthy, local backend unhealthy: {local_status.message}"
            else:
                message = f"Both backends unhealthy - Local: {local_status.message}, Remote: {remote_status.message}"

            response_time = (time.time() - start_time) * 1000

            return BackendHealthStatus(
                is_healthy=is_healthy,
                backend_type=self.backend_type,
                message=message,
                response_time_ms=response_time,
            )

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return BackendHealthStatus(
                is_healthy=False,
                backend_type=self.backend_type,
                message=f"Unexpected error during health check: {e}",
                response_time_ms=response_time,
                error=e,
            )

    def _track_access(self, key: str) -> None:
        """
        Track access to a cache key for promotion/demotion decisions.

        Args:
            key: Cache key that was accessed
        """
        current_time = time.time()

        # Increment access count
        self._access_counts[key] = self._access_counts.get(key, 0) + 1
        self._last_access_times[key] = current_time

        # Periodically clean up old tracking data to prevent memory leaks
        if len(self._access_counts) > 1000:  # Arbitrary limit
            self._cleanup_old_tracking_data()

    def _cleanup_old_tracking_data(self) -> None:
        """
        Clean up old access tracking data to prevent memory leaks.

        Removes tracking data for keys that haven't been accessed recently.
        """
        current_time = time.time()
        cleanup_threshold = current_time - (
            self.local_ttl * 2
        )  # Clean up data older than 2x local TTL

        keys_to_remove = []
        for key, last_access in self._last_access_times.items():
            if last_access < cleanup_threshold:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            self._access_counts.pop(key, None)
            self._last_access_times.pop(key, None)

        if keys_to_remove:
            logger.debug(f"Cleaned up tracking data for {len(keys_to_remove)} old keys")

    def _should_promote_to_local(self, key: str) -> bool:
        """
        Determine if a key should be promoted to local cache.

        Promotion criteria:
        - Key has been accessed multiple times recently
        - Key was accessed recently (within local TTL period)

        Args:
            key: Cache key to evaluate for promotion

        Returns:
            True if key should be promoted to local cache
        """
        access_count = self._access_counts.get(key, 0)
        last_access = self._last_access_times.get(key, 0)
        current_time = time.time()

        # Promote if accessed multiple times
        if access_count >= 2:
            logger.debug(f"Promoting key {key} to local cache (access count: {access_count})")
            return True

        # Promote if accessed very recently (within 25% of local TTL)
        recent_threshold = current_time - (self.local_ttl * 0.25)
        if last_access > recent_threshold:
            logger.debug(f"Promoting key {key} to local cache (recent access)")
            return True

        return False

    def _should_cache_locally(self, key: str, operation: str) -> bool:
        """
        Determine if a key should be cached locally when set.

        Local caching criteria:
        - Key has been accessed before (likely to be accessed again)
        - Operation type suggests frequent access
        - Always cache for certain high-frequency operations

        Args:
            key: Cache key to evaluate
            operation: AWS operation that generated the data

        Returns:
            True if key should be cached locally
        """
        # Always cache if key has been accessed before
        if key in self._access_counts:
            logger.debug(f"Caching key {key} locally (previously accessed)")
            return True

        # Cache certain high-frequency operations locally by default
        high_frequency_operations = {
            "list_roots",
            "list_accounts",
            "describe_account",
            "list_organizational_units",
            "list_children",
            "get_user",
            "list_users",
            "get_group",
            "list_groups",
        }

        if operation.lower() in high_frequency_operations:
            logger.debug(f"Caching key {key} locally (high-frequency operation: {operation})")
            return True

        # For new keys with unknown operations, don't cache locally initially
        # They will be promoted if accessed frequently
        return False

    def _get_most_accessed_keys(self, limit: int = 5) -> list:
        """
        Get the most frequently accessed keys.

        Args:
            limit: Maximum number of keys to return

        Returns:
            List of (key, access_count) tuples sorted by access count
        """
        if not self._access_counts:
            return []

        # Sort by access count (descending) and return top N
        sorted_keys = sorted(self._access_counts.items(), key=lambda x: x[1], reverse=True)

        return sorted_keys[:limit]

    def sync_backends(self) -> Dict[str, Any]:
        """
        Synchronize data between local and remote backends.

        This method can be used to:
        - Push local-only data to remote backend
        - Pull remote data that's not in local cache
        - Resolve conflicts between backends

        Returns:
            Dictionary with synchronization results
        """
        sync_result = {"success": False, "local_to_remote": 0, "remote_to_local": 0, "errors": []}

        try:
            logger.info("Starting backend synchronization")

            # Get stats from both backends to understand current state
            try:
                self.local_backend.get_stats()
                self.remote_backend.get_stats()
            except Exception as e:
                sync_result["errors"].append(f"Failed to get backend stats: {e}")
                return sync_result

            # For now, we implement a simple sync strategy:
            # - Don't automatically sync all data (could be expensive)
            # - Just ensure both backends are healthy and accessible
            # - Future enhancement could implement more sophisticated sync

            local_healthy = self.local_backend.health_check()
            remote_healthy = self.remote_backend.health_check()

            if local_healthy and remote_healthy:
                sync_result["success"] = True
                logger.info("Backend synchronization completed - both backends healthy")
            else:
                sync_result["errors"].append(
                    f"Backend health issues - local: {local_healthy}, remote: {remote_healthy}"
                )

            return sync_result

        except Exception as e:
            logger.error(f"Backend synchronization failed: {e}")
            sync_result["errors"].append(f"Synchronization failed: {e}")
            return sync_result
