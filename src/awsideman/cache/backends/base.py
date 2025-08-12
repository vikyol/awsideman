"""Cache backend interface and implementations for advanced cache features."""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class CacheBackend(ABC):
    """
    Abstract base class for cache backends.

    Defines the standard interface that all cache backends must implement
    to provide pluggable storage options for the cache system.
    """

    @abstractmethod
    def get(self, key: str) -> Optional[bytes]:
        """
        Retrieve raw data from backend.

        Args:
            key: Cache key to retrieve

        Returns:
            Raw bytes data if found, None otherwise

        Raises:
            CacheBackendError: If backend operation fails
        """
        pass

    @abstractmethod
    def set(
        self, key: str, data: bytes, ttl: Optional[int] = None, operation: str = "unknown"
    ) -> None:
        """
        Store raw data to backend.

        Args:
            key: Cache key to store data under
            data: Raw bytes data to store
            ttl: Optional TTL in seconds. Backend may ignore if not supported.
            operation: AWS operation that generated this data

        Raises:
            CacheBackendError: If backend operation fails
        """
        pass

    @abstractmethod
    def invalidate(self, key: Optional[str] = None) -> None:
        """
        Remove cache entries from backend.

        Args:
            key: Cache key to invalidate. If None, invalidates all cache entries.

        Raises:
            CacheBackendError: If backend operation fails
        """
        pass

    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """
        Get backend-specific statistics.

        Returns:
            Dictionary containing backend statistics and metadata

        Raises:
            CacheBackendError: If backend operation fails
        """
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """
        Check if backend is healthy and accessible.

        Returns:
            True if backend is healthy, False otherwise
        """
        pass


class CacheBackendError(Exception):
    """
    Exception raised when cache backend operations fail.

    This exception provides a consistent error interface across
    different backend implementations.
    """

    def __init__(
        self,
        message: str,
        backend_type: str = "unknown",
        original_error: Optional[Exception] = None,
    ):
        """
        Initialize cache backend error.

        Args:
            message: Error message
            backend_type: Type of backend that failed
            original_error: Original exception that caused this error
        """
        super().__init__(message)
        self.backend_type = backend_type
        self.original_error = original_error

        # Log the error for debugging
        if original_error:
            logger.error(
                f"Cache backend error in {backend_type}: {message} (caused by: {original_error})"
            )
        else:
            logger.error(f"Cache backend error in {backend_type}: {message}")

    def __str__(self) -> str:
        """Return string representation of the error."""
        base_msg = super().__str__()
        if self.original_error:
            return f"{base_msg} (caused by: {self.original_error})"
        return base_msg


class BackendHealthStatus:
    """
    Represents the health status of a cache backend.

    Provides detailed information about backend connectivity,
    performance, and any issues detected.
    """

    def __init__(
        self,
        is_healthy: bool,
        backend_type: str,
        message: str = "",
        response_time_ms: Optional[float] = None,
        error: Optional[Exception] = None,
    ):
        """
        Initialize backend health status.

        Args:
            is_healthy: Whether the backend is healthy
            backend_type: Type of backend
            message: Status message
            response_time_ms: Response time in milliseconds
            error: Any error encountered during health check
        """
        self.is_healthy = is_healthy
        self.backend_type = backend_type
        self.message = message
        self.response_time_ms = response_time_ms
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        """Convert health status to dictionary."""
        result = {
            "is_healthy": self.is_healthy,
            "backend_type": self.backend_type,
            "message": self.message,
        }

        if self.response_time_ms is not None:
            result["response_time_ms"] = self.response_time_ms

        if self.error:
            result["error"] = str(self.error)

        return result
