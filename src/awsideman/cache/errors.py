"""Cache error handling and circuit breaker implementation."""

import logging
import threading
import time
from enum import Enum
from typing import Any, Callable, Optional, Type

logger = logging.getLogger(__name__)


class CacheError(Exception):
    """Base exception for cache-related errors."""

    def __init__(self, message: str, cause: Optional[Exception] = None):
        super().__init__(message)
        self.cause = cause


class CacheBackendError(CacheError):
    """Error in cache backend operations."""

    pass


class CacheInvalidationError(CacheError):
    """Error during cache invalidation."""

    pass


class CacheSerializationError(CacheError):
    """Error serializing/deserializing cache data."""

    pass


class CacheKeyError(CacheError):
    """Error with cache key format or validation."""

    pass


class CacheConfigurationError(CacheError):
    """Error in cache configuration."""

    pass


class CircuitBreakerState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, blocking requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker implementation for cache backend failures.

    Implements the circuit breaker pattern to provide graceful degradation
    when cache backend operations fail repeatedly.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: Type[Exception] = CacheBackendError,
        success_threshold: int = 3,
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before trying half-open
            expected_exception: Exception type that triggers circuit breaker
            success_threshold: Successful calls needed to close circuit from half-open
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.success_threshold = success_threshold

        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitBreakerState:
        """Get current circuit breaker state."""
        return self._state

    @property
    def failure_count(self) -> int:
        """Get current failure count."""
        return self._failure_count

    def __call__(self, func: Callable) -> Callable:
        """Decorator to wrap functions with circuit breaker."""

        def wrapper(*args, **kwargs):
            return self.call(func, *args, **kwargs)

        return wrapper

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Call function with circuit breaker protection.

        Args:
            func: Function to call
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            CacheBackendError: When circuit is open
            Original exception: When function fails
        """
        with self._lock:
            if self._state == CircuitBreakerState.OPEN:
                if self._should_attempt_reset():
                    self._state = CircuitBreakerState.HALF_OPEN
                    logger.info("Circuit breaker transitioning to HALF_OPEN")
                else:
                    raise CacheBackendError(
                        f"Circuit breaker is OPEN. Last failure: {self._last_failure_time}"
                    )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception:
            self._on_failure()
            raise
        except Exception as e:
            # Don't count unexpected exceptions as circuit breaker failures
            logger.warning(f"Unexpected exception in circuit breaker: {e}")
            raise

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self._last_failure_time is None:
            return True
        return time.time() - self._last_failure_time >= self.recovery_timeout

    def _on_success(self) -> None:
        """Handle successful function call."""
        with self._lock:
            if self._state == CircuitBreakerState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._reset()
                    logger.info("Circuit breaker reset to CLOSED after successful calls")
            elif self._state == CircuitBreakerState.CLOSED:
                # Reset failure count on success in closed state
                self._failure_count = 0

    def _on_failure(self) -> None:
        """Handle failed function call."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitBreakerState.HALF_OPEN:
                # Failure in half-open state goes back to open
                self._state = CircuitBreakerState.OPEN
                self._success_count = 0
                logger.warning("Circuit breaker opened due to failure in HALF_OPEN state")
            elif self._state == CircuitBreakerState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    self._state = CircuitBreakerState.OPEN
                    logger.warning(f"Circuit breaker opened after {self._failure_count} failures")

    def _reset(self) -> None:
        """Reset circuit breaker to closed state."""
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None

    def reset(self) -> None:
        """Manually reset circuit breaker (for testing/admin purposes)."""
        with self._lock:
            self._reset()
            logger.info("Circuit breaker manually reset")

    def get_stats(self) -> dict:
        """Get circuit breaker statistics."""
        with self._lock:
            return {
                "state": self._state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "last_failure_time": self._last_failure_time,
                "failure_threshold": self.failure_threshold,
                "recovery_timeout": self.recovery_timeout,
                "success_threshold": self.success_threshold,
            }


class GracefulDegradationMixin:
    """
    Mixin to provide graceful degradation functionality.

    When cache operations fail, this mixin provides methods to fall back
    to direct operations while logging the degradation.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._degradation_count = 0
        self._degradation_lock = threading.Lock()

    def with_graceful_degradation(
        self,
        cache_operation: Callable,
        fallback_operation: Callable,
        operation_name: str = "cache operation",
    ) -> Any:
        """
        Execute cache operation with graceful degradation to fallback.

        Args:
            cache_operation: Primary cache operation to try
            fallback_operation: Fallback operation if cache fails
            operation_name: Name of operation for logging

        Returns:
            Result from cache operation or fallback operation
        """
        try:
            return cache_operation()
        except (CacheError, Exception) as e:
            with self._degradation_lock:
                self._degradation_count += 1

            logger.warning(f"Cache {operation_name} failed, falling back to direct operation: {e}")

            try:
                return fallback_operation()
            except Exception as fallback_error:
                logger.error(
                    f"Both cache and fallback {operation_name} failed. "
                    f"Cache error: {e}, Fallback error: {fallback_error}"
                )
                raise fallback_error

    def get_degradation_stats(self) -> dict:
        """Get graceful degradation statistics."""
        with self._degradation_lock:
            return {"degradation_count": self._degradation_count}

    def reset_degradation_stats(self) -> None:
        """Reset degradation statistics (for testing)."""
        with self._degradation_lock:
            self._degradation_count = 0


def handle_cache_error(
    operation: str,
    error: Exception,
    fallback_result: Any = None,
    raise_on_fallback_failure: bool = True,
) -> Any:
    """
    Centralized cache error handling utility.

    Args:
        operation: Name of the operation that failed
        error: The exception that occurred
        fallback_result: Result to return if fallback is successful
        raise_on_fallback_failure: Whether to raise exception if fallback fails

    Returns:
        fallback_result if provided, None otherwise

    Raises:
        CacheError: If raise_on_fallback_failure is True and no fallback provided
    """
    if isinstance(error, CacheError):
        logger.warning(f"Cache {operation} failed: {error}")
    else:
        logger.warning(f"Unexpected error in cache {operation}: {error}")
        # Wrap unexpected errors in CacheError
        error = CacheError(f"Unexpected error in {operation}", cause=error)

    if fallback_result is not None:
        logger.info(f"Using fallback result for {operation}")
        return fallback_result

    if raise_on_fallback_failure:
        raise error

    return None
