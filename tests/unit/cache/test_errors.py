"""Tests for cache error handling and circuit breaker functionality."""

import threading
import time
from unittest.mock import patch

import pytest

from src.awsideman.cache.errors import (
    CacheBackendError,
    CacheConfigurationError,
    CacheError,
    CacheInvalidationError,
    CacheKeyError,
    CacheSerializationError,
    CircuitBreaker,
    CircuitBreakerState,
    GracefulDegradationMixin,
    handle_cache_error,
)


class TestCacheErrorHierarchy:
    """Test cache error hierarchy."""

    def test_cache_error_base(self):
        """Test base CacheError functionality."""
        error = CacheError("Test error")
        assert str(error) == "Test error"
        assert error.cause is None

        # Test with cause
        cause = ValueError("Original error")
        error_with_cause = CacheError("Wrapped error", cause=cause)
        assert error_with_cause.cause == cause

    def test_cache_backend_error(self):
        """Test CacheBackendError inherits from CacheError."""
        error = CacheBackendError("Backend failed")
        assert isinstance(error, CacheError)
        assert str(error) == "Backend failed"

    def test_cache_invalidation_error(self):
        """Test CacheInvalidationError inherits from CacheError."""
        error = CacheInvalidationError("Invalidation failed")
        assert isinstance(error, CacheError)
        assert str(error) == "Invalidation failed"

    def test_cache_serialization_error(self):
        """Test CacheSerializationError inherits from CacheError."""
        error = CacheSerializationError("Serialization failed")
        assert isinstance(error, CacheError)
        assert str(error) == "Serialization failed"

    def test_cache_key_error(self):
        """Test CacheKeyError inherits from CacheError."""
        error = CacheKeyError("Invalid key")
        assert isinstance(error, CacheError)
        assert str(error) == "Invalid key"

    def test_cache_configuration_error(self):
        """Test CacheConfigurationError inherits from CacheError."""
        error = CacheConfigurationError("Config invalid")
        assert isinstance(error, CacheError)
        assert str(error) == "Config invalid"


class TestCircuitBreaker:
    """Test circuit breaker functionality."""

    def test_initial_state(self):
        """Test circuit breaker initial state."""
        cb = CircuitBreaker()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0

    def test_successful_calls_in_closed_state(self):
        """Test successful calls don't change closed state."""
        cb = CircuitBreaker(failure_threshold=3)

        def success_func():
            return "success"

        # Multiple successful calls should keep circuit closed
        for _ in range(5):
            result = cb.call(success_func)
            assert result == "success"
            assert cb.state == CircuitBreakerState.CLOSED
            assert cb.failure_count == 0

    def test_failures_open_circuit(self):
        """Test that failures open the circuit."""
        cb = CircuitBreaker(failure_threshold=3)

        def failing_func():
            raise CacheBackendError("Backend failed")

        # First two failures should keep circuit closed
        for i in range(2):
            with pytest.raises(CacheBackendError):
                cb.call(failing_func)
            assert cb.state == CircuitBreakerState.CLOSED
            assert cb.failure_count == i + 1

        # Third failure should open circuit
        with pytest.raises(CacheBackendError):
            cb.call(failing_func)
        assert cb.state == CircuitBreakerState.OPEN
        assert cb.failure_count == 3

    def test_open_circuit_blocks_calls(self):
        """Test that open circuit blocks calls."""
        cb = CircuitBreaker(failure_threshold=2)

        def failing_func():
            raise CacheBackendError("Backend failed")

        # Trigger circuit opening
        for _ in range(2):
            with pytest.raises(CacheBackendError):
                cb.call(failing_func)

        assert cb.state == CircuitBreakerState.OPEN

        # Now calls should be blocked
        def success_func():
            return "success"

        with pytest.raises(CacheBackendError, match="Circuit breaker is OPEN"):
            cb.call(success_func)

    def test_half_open_transition(self):
        """Test transition to half-open state after timeout."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)

        def failing_func():
            raise CacheBackendError("Backend failed")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(CacheBackendError):
                cb.call(failing_func)

        assert cb.state == CircuitBreakerState.OPEN

        # Wait for recovery timeout
        time.sleep(0.2)

        def success_func():
            return "success"

        # First call after timeout should transition to half-open
        result = cb.call(success_func)
        assert result == "success"
        assert cb.state == CircuitBreakerState.HALF_OPEN

    def test_half_open_to_closed_transition(self):
        """Test transition from half-open to closed after successful calls."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1, success_threshold=2)

        def failing_func():
            raise CacheBackendError("Backend failed")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(CacheBackendError):
                cb.call(failing_func)

        # Wait and transition to half-open
        time.sleep(0.2)

        def success_func():
            return "success"

        # First successful call transitions to half-open
        result = cb.call(success_func)
        assert result == "success"
        assert cb.state == CircuitBreakerState.HALF_OPEN

        # Second successful call should close the circuit
        result = cb.call(success_func)
        assert result == "success"
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0

    def test_half_open_to_open_on_failure(self):
        """Test transition from half-open back to open on failure."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)

        def failing_func():
            raise CacheBackendError("Backend failed")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(CacheBackendError):
                cb.call(failing_func)

        # Wait and transition to half-open
        time.sleep(0.2)

        def success_func():
            return "success"

        # Transition to half-open
        cb.call(success_func)
        assert cb.state == CircuitBreakerState.HALF_OPEN

        # Failure in half-open should go back to open
        with pytest.raises(CacheBackendError):
            cb.call(failing_func)
        assert cb.state == CircuitBreakerState.OPEN

    def test_decorator_usage(self):
        """Test circuit breaker as decorator."""
        cb = CircuitBreaker(failure_threshold=2)

        @cb
        def test_func(should_fail=False):
            if should_fail:
                raise CacheBackendError("Failed")
            return "success"

        # Successful calls
        assert test_func() == "success"
        assert cb.state == CircuitBreakerState.CLOSED

        # Failing calls
        for _ in range(2):
            with pytest.raises(CacheBackendError):
                test_func(should_fail=True)

        assert cb.state == CircuitBreakerState.OPEN

    def test_unexpected_exceptions_dont_trigger_circuit(self):
        """Test that unexpected exceptions don't trigger circuit breaker."""
        cb = CircuitBreaker(failure_threshold=2, expected_exception=CacheBackendError)

        def func_with_unexpected_error():
            raise ValueError("Unexpected error")

        # Unexpected exceptions should not trigger circuit breaker
        for _ in range(5):
            with pytest.raises(ValueError):
                cb.call(func_with_unexpected_error)
            assert cb.state == CircuitBreakerState.CLOSED
            assert cb.failure_count == 0

    def test_manual_reset(self):
        """Test manual circuit breaker reset."""
        cb = CircuitBreaker(failure_threshold=2)

        def failing_func():
            raise CacheBackendError("Backend failed")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(CacheBackendError):
                cb.call(failing_func)

        assert cb.state == CircuitBreakerState.OPEN

        # Manual reset
        cb.reset()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0

    def test_thread_safety(self):
        """Test circuit breaker thread safety."""
        cb = CircuitBreaker(failure_threshold=10)
        results = []
        errors = []

        def worker():
            try:

                def test_func():
                    return "success"

                result = cb.call(test_func)
                results.append(result)
            except Exception as e:
                errors.append(e)

        # Run multiple threads
        threads = [threading.Thread(target=worker) for _ in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # All should succeed
        assert len(results) == 20
        assert len(errors) == 0
        assert all(r == "success" for r in results)

    def test_get_stats(self):
        """Test circuit breaker statistics."""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60, success_threshold=2)

        stats = cb.get_stats()
        assert stats["state"] == "closed"
        assert stats["failure_count"] == 0
        assert stats["success_count"] == 0
        assert stats["last_failure_time"] is None
        assert stats["failure_threshold"] == 3
        assert stats["recovery_timeout"] == 60
        assert stats["success_threshold"] == 2


# TestGracefulDegradationMixin class removed - was testing stale functionality


class TestHandleCacheError:
    """Test centralized cache error handling utility."""

    def test_handle_cache_error_with_fallback(self):
        """Test handling cache error with fallback result."""
        error = CacheBackendError("Cache failed")
        result = handle_cache_error("test_op", error, fallback_result="fallback")
        assert result == "fallback"

    def test_handle_cache_error_without_fallback_raises(self):
        """Test handling cache error without fallback raises exception."""
        error = CacheBackendError("Cache failed")
        with pytest.raises(CacheBackendError):
            handle_cache_error("test_op", error)

    def test_handle_cache_error_without_fallback_no_raise(self):
        """Test handling cache error without fallback and no raise."""
        error = CacheBackendError("Cache failed")
        result = handle_cache_error("test_op", error, raise_on_fallback_failure=False)
        assert result is None

    def test_handle_unexpected_error(self):
        """Test handling unexpected error wraps in CacheError."""
        error = ValueError("Unexpected error")
        with pytest.raises(CacheError) as exc_info:
            handle_cache_error("test_op", error)

        assert exc_info.value.cause == error
        assert "Unexpected error in test_op" in str(exc_info.value)

    @patch("src.awsideman.cache.errors.logger")
    def test_logging_behavior(self, mock_logger):
        """Test that errors are properly logged."""
        # Test cache error logging
        cache_error = CacheBackendError("Cache failed")
        handle_cache_error("test_op", cache_error, fallback_result="fallback")
        mock_logger.warning.assert_called_with("Cache test_op failed: Cache failed")
        mock_logger.info.assert_called_with("Using fallback result for test_op")

        # Test unexpected error logging
        unexpected_error = ValueError("Unexpected")
        try:
            handle_cache_error("test_op", unexpected_error, raise_on_fallback_failure=False)
        except Exception:
            pass
        mock_logger.warning.assert_called_with("Unexpected error in cache test_op: Unexpected")


class TestCircuitBreakerIntegration:
    """Test circuit breaker integration scenarios."""

    def test_circuit_breaker_with_graceful_degradation(self):
        """Test circuit breaker working with graceful degradation."""
        cb = CircuitBreaker(failure_threshold=2)

        class TestService(GracefulDegradationMixin):
            def __init__(self):
                super().__init__()
                self.circuit_breaker = cb

            def get_data(self, key: str):
                def cache_operation():
                    return self.circuit_breaker.call(self._cache_get, key)

                def fallback_operation():
                    return f"direct_result_{key}"

                return self.with_graceful_degradation(
                    cache_operation, fallback_operation, "get_data"
                )

            def _cache_get(self, key: str):
                if key == "fail":
                    raise CacheBackendError("Cache backend failed")
                return f"cached_result_{key}"

        service = TestService()

        # Successful cache operations
        assert service.get_data("success") == "cached_result_success"
        assert cb.state == CircuitBreakerState.CLOSED

        # Trigger circuit breaker opening
        for _ in range(2):
            result = service.get_data("fail")
            assert result == "direct_result_fail"

        assert cb.state == CircuitBreakerState.OPEN

        # Circuit is open, should use fallback
        result = service.get_data("success")
        assert result == "direct_result_success"

        # Check degradation stats
        stats = service.get_degradation_stats()
        assert stats["degradation_count"] == 3  # 2 failures + 1 blocked call
