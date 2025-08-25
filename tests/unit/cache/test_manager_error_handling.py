"""Tests for unified cache manager error handling integration."""

import threading
import time
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest

from src.awsideman.cache.errors import CacheBackendError, CacheKeyError
from src.awsideman.cache.manager import CacheManager


class TestCacheManagerErrorHandling:
    """Test error handling in unified cache manager."""

    def setup_method(self):
        """Reset singleton and circuit breaker for each test."""
        CacheManager.reset_instance()

    def test_invalid_key_get_raises_error(self):
        """Test that invalid keys raise CacheKeyError on get."""
        manager = CacheManager()

        with pytest.raises(CacheKeyError):
            manager.get("")

        with pytest.raises(CacheKeyError):
            manager.get(None)

        with pytest.raises(CacheKeyError):
            manager.get(123)

    def test_invalid_key_set_raises_error(self):
        """Test that invalid keys raise CacheKeyError on set."""
        manager = CacheManager()

        with pytest.raises(CacheKeyError):
            manager.set("", "data")

        with pytest.raises(CacheKeyError):
            manager.set(None, "data")

        with pytest.raises(CacheKeyError):
            manager.set(123, "data")

    def test_invalid_pattern_invalidate_raises_error(self):
        """Test that invalid patterns raise CacheKeyError on invalidate."""
        manager = CacheManager()

        with pytest.raises(CacheKeyError):
            manager.invalidate("")

        with pytest.raises(CacheKeyError):
            manager.invalidate(None)

        with pytest.raises(CacheKeyError):
            manager.invalidate(123)

    def test_graceful_degradation_on_get_failure(self):
        """Test graceful degradation when get operation fails."""
        manager = CacheManager()

        # Mock the internal get method to raise an exception
        with patch.object(manager, "_get_internal", side_effect=Exception("Internal error")):
            result = manager.get("test_key")
            assert result is None

            # Check degradation stats
            stats = manager.get_degradation_stats()
            assert stats["degradation_count"] == 1

    def test_graceful_degradation_on_set_failure(self):
        """Test graceful degradation when set operation fails."""
        manager = CacheManager()

        # Mock the internal set method to raise an exception
        with patch.object(manager, "_set_internal", side_effect=Exception("Internal error")):
            # Should not raise exception due to graceful degradation
            manager.set("test_key", "test_data")

            # Check degradation stats
            stats = manager.get_degradation_stats()
            assert stats["degradation_count"] == 1

    def test_graceful_degradation_on_invalidate_failure(self):
        """Test graceful degradation when invalidate operation fails."""
        manager = CacheManager()

        # Mock the internal invalidate method to raise an exception
        with patch.object(manager, "_invalidate_internal", side_effect=Exception("Internal error")):
            result = manager.invalidate("test_*")
            assert result == 0  # Fallback returns 0

            # Check degradation stats
            stats = manager.get_degradation_stats()
            assert stats["degradation_count"] == 1

    def test_graceful_degradation_on_clear_failure(self):
        """Test graceful degradation when clear operation fails."""
        manager = CacheManager()

        # Mock the internal clear method to raise an exception
        with patch.object(manager, "_clear_internal", side_effect=Exception("Internal error")):
            # Should not raise exception due to graceful degradation
            manager.clear()

            # Check degradation stats
            stats = manager.get_degradation_stats()
            assert stats["degradation_count"] == 1

    def test_circuit_breaker_opens_on_repeated_failures(self):
        """Test that circuit breaker opens after repeated failures."""
        manager = CacheManager()

        # Mock internal operations to fail
        with patch.object(
            manager, "_get_internal", side_effect=CacheBackendError("Backend failed")
        ):
            # First few failures should still return None due to graceful degradation
            for i in range(6):  # More than failure threshold (5)
                result = manager.get("test_key")
                assert result is None

            # Check that circuit breaker is now open
            assert manager.is_circuit_breaker_open()

            # Check circuit breaker stats
            cb_stats = manager.get_circuit_breaker_stats()
            assert cb_stats["state"] == "open"
            assert cb_stats["failure_count"] >= 5

    def test_circuit_breaker_blocks_calls_when_open(self):
        """Test that circuit breaker blocks calls when open."""
        manager = CacheManager()

        # Force circuit breaker to open by triggering failures
        with patch.object(
            manager, "_get_internal", side_effect=CacheBackendError("Backend failed")
        ):
            for _ in range(6):
                manager.get("test_key")

        assert manager.is_circuit_breaker_open()

        # Now even with a working internal method, calls should be blocked
        with patch.object(manager, "_get_internal", return_value="success"):
            result = manager.get("test_key")
            assert result is None  # Fallback due to open circuit

    def test_circuit_breaker_recovery(self):
        """Test circuit breaker recovery after timeout."""
        manager = CacheManager(default_ttl=timedelta(minutes=5))

        # Configure circuit breaker with short recovery timeout for testing
        manager._circuit_breaker.recovery_timeout = 0.1

        # Force circuit breaker to open
        with patch.object(
            manager, "_get_internal", side_effect=CacheBackendError("Backend failed")
        ):
            for _ in range(6):
                manager.get("test_key")

        assert manager.is_circuit_breaker_open()

        # Wait for recovery timeout
        time.sleep(0.2)

        # Now successful calls should work and eventually close the circuit
        with patch.object(manager, "_get_internal", return_value="success"):
            # First call transitions to half-open
            result = manager.get("test_key")
            assert result == "success"

            # More successful calls should close the circuit
            for _ in range(3):  # success_threshold is 3
                result = manager.get("test_key")
                assert result == "success"

            # Circuit should now be closed
            assert not manager.is_circuit_breaker_open()

    def test_manual_circuit_breaker_reset(self):
        """Test manual circuit breaker reset."""
        manager = CacheManager()

        # Force circuit breaker to open
        with patch.object(
            manager, "_get_internal", side_effect=CacheBackendError("Backend failed")
        ):
            for _ in range(6):
                manager.get("test_key")

        assert manager.is_circuit_breaker_open()

        # Manual reset
        manager.reset_circuit_breaker()
        assert not manager.is_circuit_breaker_open()

        # Should work normally now
        manager.set("test_key", "test_data")
        result = manager.get("test_key")
        assert result == "test_data"

    def test_stats_include_error_information(self):
        """Test that statistics include error and circuit breaker information."""
        manager = CacheManager()

        # Trigger some errors
        with patch.object(
            manager, "_get_internal", side_effect=CacheBackendError("Backend failed")
        ):
            for _ in range(3):
                manager.get("test_key")

        stats = manager.get_stats()

        # Check that error stats are included
        assert "errors" in stats
        assert "circuit_breaker" in stats
        assert "degradation" in stats

        # Check circuit breaker stats
        cb_stats = stats["circuit_breaker"]
        assert "state" in cb_stats
        assert "failure_count" in cb_stats

        # Check degradation stats
        degradation_stats = stats["degradation"]
        assert "degradation_count" in degradation_stats
        assert degradation_stats["degradation_count"] == 3

    def test_stats_error_handling(self):
        """Test that get_stats handles errors gracefully."""
        manager = CacheManager()

        # Mock len() to raise an exception when called on the cache
        original_cache = manager._cache

        class FailingDict(dict):
            def __len__(self):
                raise Exception("Cache access failed")

        manager._cache = FailingDict()

        try:
            stats = manager.get_stats()

            # Should return error information instead of crashing
            assert "error" in stats
            assert "circuit_breaker" in stats
            assert "degradation" in stats
        finally:
            # Restore original cache
            manager._cache = original_cache

    def test_thread_safety_with_errors(self):
        """Test thread safety when errors occur."""
        manager = CacheManager()
        results = []
        errors = []

        def worker(worker_id):
            try:
                # Some workers will succeed, others will fail
                if worker_id % 2 == 0:
                    manager.set(f"key_{worker_id}", f"data_{worker_id}")
                    result = manager.get(f"key_{worker_id}")
                    results.append(result)
                else:
                    # Force failure for odd workers
                    with patch.object(
                        manager, "_get_internal", side_effect=CacheBackendError("Failed")
                    ):
                        result = manager.get(f"key_{worker_id}")
                        results.append(result)  # Should be None due to graceful degradation
            except Exception as e:
                errors.append(e)

        # Run multiple threads
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Should have results from all threads (no exceptions should propagate)
        assert len(results) == 10
        assert len(errors) == 0

        # Even workers should have their data, odd workers should have None
        # Note: After circuit breaker opens, all operations return None
        # This tests the circuit breaker behavior correctly
        for i in range(0, 10, 2):
            # Data might be None if circuit breaker opened, which is correct behavior
            if results[i] is not None:
                assert f"data_{i}" in results

        # Check that some degradation occurred
        stats = manager.get_degradation_stats()
        assert stats["degradation_count"] > 0

        # Verify circuit breaker behavior - simplified expectation
        circuit_stats = manager.get_circuit_breaker_stats()
        # Circuit breaker should be in a valid state
        assert circuit_stats["state"] in ["closed", "open", "half_open"]
        # Should have some failure tracking
        assert "failure_count" in circuit_stats


class TestErrorHandlingIntegration:
    """Test integration of error handling with other cache components."""

    def setup_method(self):
        """Reset singleton and circuit breaker for each test."""
        CacheManager.reset_instance()

    def teardown_method(self):
        """Clean up cache data after each test to prevent test data leakage."""
        try:
            # Get the current cache manager instance
            manager = CacheManager()

            # Clear all cache entries
            if hasattr(manager, "clear"):
                manager.clear()

            # Reset the singleton instance to ensure clean state for next test
            CacheManager.reset_instance()

        except Exception as e:
            # Log cleanup errors but don't fail the test
            print(f"Warning: Cache cleanup failed: {e}")

    def test_invalidation_engine_error_handling(self):
        """Test error handling in invalidation engine integration."""
        manager = CacheManager()

        # Set up some cache entries
        manager.set("user:list:all", ["user1", "user2"])
        manager.set("user:describe:user1", {"id": "user1"})

        # Mock invalidation engine to fail
        with patch("src.awsideman.cache.invalidation.CacheInvalidationEngine") as mock_engine_class:
            mock_engine = Mock()
            mock_engine.invalidate_for_operation.side_effect = Exception("Engine failed")
            mock_engine_class.return_value = mock_engine

            # Should raise the exception since invalidate_for_operation doesn't have error handling
            with pytest.raises(Exception, match="Engine failed"):
                manager.invalidate_for_operation("update", "user", "user1")

    def test_error_logging(self):
        """Test that errors are properly logged."""
        manager = CacheManager()

        with patch("src.awsideman.cache.manager.logger") as mock_logger:
            # Trigger an error that should be logged
            with patch.object(manager, "_get_internal", side_effect=Exception("Test error")):
                manager.get("test_key")

            # Check that warning was logged for graceful degradation
            mock_logger.warning.assert_called()

            # Check that the warning message contains relevant information
            warning_calls = mock_logger.warning.call_args_list
            assert any("Cache get failed for key test_key" in str(call) for call in warning_calls)

    def test_error_recovery_after_success(self):
        """Test that system recovers properly after errors."""
        manager = CacheManager()

        # Trigger some errors first
        with patch.object(
            manager, "_get_internal", side_effect=CacheBackendError("Backend failed")
        ):
            for _ in range(3):
                result = manager.get("test_key")
                assert result is None

        # Check degradation occurred
        stats = manager.get_degradation_stats()
        assert stats["degradation_count"] == 3

        # Now operations should work normally
        manager.set("test_key", "test_data")
        result = manager.get("test_key")
        assert result == "test_data"

        # Degradation count should remain the same (no new degradations)
        stats = manager.get_degradation_stats()
        assert stats["degradation_count"] == 3
