"""Tests for cache backend base classes and interfaces."""

import pytest

from src.awsideman.cache.backends.base import BackendHealthStatus, CacheBackend, CacheBackendError


class TestCacheBackend:
    """Test the abstract CacheBackend interface."""

    def test_abstract_methods_raise_not_implemented(self):
        """Test that abstract methods raise NotImplementedError."""
        # Cannot instantiate abstract class directly
        with pytest.raises(TypeError):
            CacheBackend()


class TestCacheBackendError:
    """Test the CacheBackendError exception class."""

    def test_basic_error_creation(self):
        """Test basic error creation with message only."""
        error = CacheBackendError("Test error message")
        assert str(error) == "Test error message"
        assert error.backend_type == "unknown"
        assert error.original_error is None

    def test_error_with_backend_type(self):
        """Test error creation with backend type."""
        error = CacheBackendError("Test error", backend_type="file")
        assert str(error) == "Test error"
        assert error.backend_type == "file"
        assert error.original_error is None

    def test_error_with_original_error(self):
        """Test error creation with original exception."""
        original = ValueError("Original error")
        error = CacheBackendError("Test error", original_error=original)
        assert "Test error (caused by: Original error)" in str(error)
        assert error.original_error == original

    def test_error_with_all_parameters(self):
        """Test error creation with all parameters."""
        original = ValueError("Original error")
        error = CacheBackendError("Test error", backend_type="dynamodb", original_error=original)
        assert "Test error (caused by: Original error)" in str(error)
        assert error.backend_type == "dynamodb"
        assert error.original_error == original


class TestBackendHealthStatus:
    """Test the BackendHealthStatus class."""

    def test_basic_health_status_creation(self):
        """Test basic health status creation."""
        status = BackendHealthStatus(
            is_healthy=True, backend_type="file", message="Backend is healthy"
        )

        assert status.is_healthy is True
        assert status.backend_type == "file"
        assert status.message == "Backend is healthy"
        assert status.response_time_ms is None
        assert status.error is None

    def test_health_status_with_response_time(self):
        """Test health status with response time."""
        status = BackendHealthStatus(
            is_healthy=True,
            backend_type="dynamodb",
            message="Backend is healthy",
            response_time_ms=150.5,
        )

        assert status.response_time_ms == 150.5

    def test_health_status_with_error(self):
        """Test health status with error."""
        error = Exception("Connection failed")
        status = BackendHealthStatus(
            is_healthy=False, backend_type="dynamodb", message="Backend is unhealthy", error=error
        )

        assert status.is_healthy is False
        assert status.error == error

    def test_to_dict_basic(self):
        """Test converting health status to dictionary."""
        status = BackendHealthStatus(
            is_healthy=True, backend_type="file", message="Backend is healthy"
        )

        result = status.to_dict()

        expected = {"is_healthy": True, "backend_type": "file", "message": "Backend is healthy"}

        assert result == expected

    def test_to_dict_with_response_time(self):
        """Test converting health status with response time to dictionary."""
        status = BackendHealthStatus(
            is_healthy=True,
            backend_type="file",
            message="Backend is healthy",
            response_time_ms=100.0,
        )

        result = status.to_dict()

        assert result["response_time_ms"] == 100.0

    def test_to_dict_with_error(self):
        """Test converting health status with error to dictionary."""
        error = Exception("Connection failed")
        status = BackendHealthStatus(
            is_healthy=False, backend_type="dynamodb", message="Backend is unhealthy", error=error
        )

        result = status.to_dict()

        assert result["error"] == "Connection failed"

    def test_to_dict_complete(self):
        """Test converting complete health status to dictionary."""
        error = Exception("Timeout")
        status = BackendHealthStatus(
            is_healthy=False,
            backend_type="hybrid",
            message="Backend timeout",
            response_time_ms=5000.0,
            error=error,
        )

        result = status.to_dict()

        expected = {
            "is_healthy": False,
            "backend_type": "hybrid",
            "message": "Backend timeout",
            "response_time_ms": 5000.0,
            "error": "Timeout",
        }

        assert result == expected


class MockCacheBackend(CacheBackend):
    """Mock implementation of CacheBackend for testing."""

    def __init__(self):
        self.data = {}
        self.stats = {"backend_type": "mock"}
        self.healthy = True

    def get(self, key: str):
        return self.data.get(key)

    def set(self, key: str, data: bytes, ttl=None, operation="unknown"):
        self.data[key] = data

    def invalidate(self, key=None):
        if key is None:
            self.data.clear()
        else:
            self.data.pop(key, None)

    def get_stats(self):
        return self.stats.copy()

    def health_check(self):
        return self.healthy


class TestCacheBackendInterface:
    """Test the cache backend interface with a mock implementation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.backend = MockCacheBackend()

    def test_get_set_operations(self):
        """Test basic get/set operations."""
        test_data = b"test data"

        # Initially empty
        assert self.backend.get("test_key") is None

        # Set data
        self.backend.set("test_key", test_data)

        # Retrieve data
        result = self.backend.get("test_key")
        assert result == test_data

    def test_invalidate_specific_key(self):
        """Test invalidating a specific key."""
        self.backend.set("key1", b"data1")
        self.backend.set("key2", b"data2")

        # Invalidate specific key
        self.backend.invalidate("key1")

        assert self.backend.get("key1") is None
        assert self.backend.get("key2") == b"data2"

    def test_invalidate_all_keys(self):
        """Test invalidating all keys."""
        self.backend.set("key1", b"data1")
        self.backend.set("key2", b"data2")

        # Invalidate all
        self.backend.invalidate()

        assert self.backend.get("key1") is None
        assert self.backend.get("key2") is None

    def test_get_stats(self):
        """Test getting backend statistics."""
        stats = self.backend.get_stats()
        assert isinstance(stats, dict)
        assert stats["backend_type"] == "mock"

    def test_health_check(self):
        """Test health check functionality."""
        assert self.backend.health_check() is True

        # Simulate unhealthy backend
        self.backend.healthy = False
        assert self.backend.health_check() is False
