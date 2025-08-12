"""Tests for comprehensive timeout handling system."""
import asyncio
import signal
import time
from unittest.mock import patch

import pytest

from src.awsideman.utils.error_handler import ErrorCategory
from src.awsideman.utils.timeout_handler import (
    TimeoutConfig,
    TimeoutHandler,
    TimeoutResult,
    TimeoutStrategy,
    get_timeout_handler,
    with_timeout,
)


class TestTimeoutConfig:
    """Test TimeoutConfig functionality."""

    def test_default_config(self):
        """Test default timeout configuration."""
        config = TimeoutConfig()

        assert config.default_timeout_seconds == 30.0
        assert config.max_timeout_seconds == 300.0
        assert config.retry_attempts == 3
        assert config.backoff_multiplier == 2.0
        assert config.max_backoff_seconds == 60.0
        assert config.strategy == TimeoutStrategy.RETRY_WITH_BACKOFF
        assert config.enable_timeout_warnings is True
        assert config.warning_threshold_ratio == 0.8
        assert config.enable_adaptive_timeout is True
        assert config.operation_timeout_overrides == {}

    def test_custom_config(self):
        """Test custom timeout configuration."""
        overrides = {"slow_operation": 120.0}
        config = TimeoutConfig(
            default_timeout_seconds=60.0,
            max_timeout_seconds=600.0,
            retry_attempts=5,
            strategy=TimeoutStrategy.FAIL_FAST,
            operation_timeout_overrides=overrides,
        )

        assert config.default_timeout_seconds == 60.0
        assert config.max_timeout_seconds == 600.0
        assert config.retry_attempts == 5
        assert config.strategy == TimeoutStrategy.FAIL_FAST
        assert config.operation_timeout_overrides == overrides


class TestTimeoutResult:
    """Test TimeoutResult functionality."""

    def test_timeout_result_creation(self):
        """Test creating timeout result."""
        result = TimeoutResult(
            success=True,
            result="operation_result",
            duration_seconds=15.5,
            retry_count=2,
            final_timeout_used=30.0,
        )

        assert result.success is True
        assert result.result == "operation_result"
        assert result.error is None
        assert result.duration_seconds == 15.5
        assert result.timeout_occurred is False
        assert result.retry_count == 2
        assert result.final_timeout_used == 30.0
        assert result.warnings == []

    def test_timeout_result_with_error(self):
        """Test timeout result with error."""
        from src.awsideman.utils.error_handler import ErrorContext, ErrorSeverity, StatusError

        error = StatusError(
            error_id="TEST_001",
            message="Test error",
            category=ErrorCategory.TIMEOUT,
            severity=ErrorSeverity.MEDIUM,
            context=ErrorContext(component="Test", operation="test"),
        )

        result = TimeoutResult(
            success=False, error=error, timeout_occurred=True, duration_seconds=30.0
        )

        assert result.success is False
        assert result.result is None
        assert result.error is error
        assert result.timeout_occurred is True


@pytest.mark.asyncio
class TestTimeoutHandler:
    """Test TimeoutHandler functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = TimeoutConfig(
            default_timeout_seconds=1.0,  # Short timeout for testing
            retry_attempts=2,
            enable_timeout_warnings=False,  # Disable warnings for cleaner tests
        )
        self.handler = TimeoutHandler(self.config)

    async def test_execute_with_timeout_success(self):
        """Test successful operation execution with timeout."""

        async def fast_operation():
            await asyncio.sleep(0.1)
            return "success"

        result = await self.handler.execute_with_timeout(
            fast_operation, "fast_test", timeout_seconds=0.5
        )

        assert result.success is True
        assert result.result == "success"
        assert result.timeout_occurred is False
        assert result.duration_seconds < 0.5
        assert result.retry_count == 0

    async def test_execute_with_timeout_failure(self):
        """Test operation that times out."""

        async def slow_operation():
            await asyncio.sleep(2.0)  # Longer than timeout
            return "should_not_reach"

        result = await self.handler.execute_with_timeout(
            slow_operation, "slow_test", timeout_seconds=0.5
        )

        assert result.success is False
        assert result.result is None
        assert result.timeout_occurred is True
        assert result.error is not None
        assert result.error.category == ErrorCategory.TIMEOUT

    async def test_execute_with_timeout_exception(self):
        """Test operation that raises an exception."""

        async def failing_operation():
            raise ValueError("Test error")

        result = await self.handler.execute_with_timeout(failing_operation, "failing_test")

        assert result.success is False
        assert result.result is None
        assert result.error is not None
        assert "Test error" in result.error.message

    async def test_fail_fast_strategy(self):
        """Test fail-fast timeout strategy."""
        self.handler.config.strategy = TimeoutStrategy.FAIL_FAST

        async def slow_operation():
            await asyncio.sleep(2.0)
            return "should_not_reach"

        result = await self.handler.execute_with_timeout(
            slow_operation, "fail_fast_test", timeout_seconds=0.5
        )

        assert result.success is False
        assert result.timeout_occurred is True
        assert result.retry_count == 0  # No retries with fail-fast

    async def test_retry_with_backoff_strategy(self):
        """Test retry with backoff strategy."""
        self.handler.config.strategy = TimeoutStrategy.RETRY_WITH_BACKOFF
        self.handler.config.retry_attempts = 2

        call_count = 0

        async def intermittent_slow_operation():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                await asyncio.sleep(2.0)  # Timeout on first two attempts
            return f"success_on_attempt_{call_count}"

        result = await self.handler.execute_with_timeout(
            intermittent_slow_operation, "retry_test", timeout_seconds=0.5
        )

        assert result.success is True
        assert result.result == "success_on_attempt_3"
        assert result.retry_count == 2
        assert call_count == 3

    async def test_retry_exhausted(self):
        """Test when all retry attempts are exhausted."""
        self.handler.config.strategy = TimeoutStrategy.RETRY_WITH_BACKOFF
        self.handler.config.retry_attempts = 2

        async def always_slow_operation():
            await asyncio.sleep(2.0)
            return "should_not_reach"

        result = await self.handler.execute_with_timeout(
            always_slow_operation, "retry_exhausted_test", timeout_seconds=0.5
        )

        assert result.success is False
        assert result.timeout_occurred is True
        assert result.retry_count == 2
        assert "failed after 3 attempts" in result.error.message

    async def test_extend_timeout_strategy(self):
        """Test extend timeout strategy."""
        self.handler.config.strategy = TimeoutStrategy.EXTEND_TIMEOUT

        call_count = 0

        async def operation_that_needs_extension():
            nonlocal call_count
            call_count += 1
            # First call times out, second succeeds with extended timeout
            sleep_time = 1.5 if call_count == 1 else 0.8
            await asyncio.sleep(sleep_time)
            return "success_after_extension"

        result = await self.handler.execute_with_timeout(
            operation_that_needs_extension, "extend_test", timeout_seconds=1.0
        )

        assert result.success is True
        assert result.result == "success_after_extension"
        assert len(result.warnings) > 0
        assert "timeout extensions" in result.warnings[0]

    def test_execute_sync_with_timeout_success(self):
        """Test synchronous operation execution with timeout."""

        def fast_sync_operation():
            time.sleep(0.1)
            return "sync_success"

        result = self.handler.execute_sync_with_timeout(
            fast_sync_operation, "sync_fast_test", timeout_seconds=0.5
        )

        assert result.success is True
        assert result.result == "sync_success"
        assert result.timeout_occurred is False

    @pytest.mark.skipif(
        not hasattr(signal, "SIGALRM"), reason="SIGALRM not available on this platform"
    )
    def test_execute_sync_with_timeout_failure(self):
        """Test synchronous operation that times out."""

        def slow_sync_operation():
            time.sleep(2.0)
            return "should_not_reach"

        result = self.handler.execute_sync_with_timeout(
            slow_sync_operation, "sync_slow_test", timeout_seconds=0.5
        )

        assert result.success is False
        assert result.timeout_occurred is True
        assert result.error is not None

    def test_get_effective_timeout_default(self):
        """Test getting effective timeout with default value."""
        timeout = self.handler._get_effective_timeout("test_operation", None)
        assert timeout == self.config.default_timeout_seconds

    def test_get_effective_timeout_requested(self):
        """Test getting effective timeout with requested value."""
        timeout = self.handler._get_effective_timeout("test_operation", 45.0)
        assert timeout == 45.0

    def test_get_effective_timeout_override(self):
        """Test getting effective timeout with operation override."""
        self.handler.config.operation_timeout_overrides["special_op"] = 120.0
        timeout = self.handler._get_effective_timeout("special_op", None)
        assert timeout == 120.0

    def test_get_effective_timeout_max_limit(self):
        """Test that effective timeout respects maximum limit."""
        timeout = self.handler._get_effective_timeout("test_operation", 500.0)
        assert timeout == self.config.max_timeout_seconds

    def test_record_operation_performance(self):
        """Test recording operation performance data."""
        # Record some performance data
        self.handler._record_operation_performance("test_op", 1.5, True)
        self.handler._record_operation_performance("test_op", 2.0, True)
        self.handler._record_operation_performance("test_op", 1.8, False)

        stats = self.handler.get_operation_stats("test_op")

        assert stats is not None
        assert stats["sample_count"] == 2  # Only successful operations
        assert stats["avg_duration"] == 1.75  # (1.5 + 2.0) / 2
        assert stats["min_duration"] == 1.5
        assert stats["max_duration"] == 2.0
        assert stats["success_rate"] == 2 / 3  # 2 successful out of 3 total

    def test_get_active_operations(self):
        """Test getting active operations information."""
        # Simulate active operation
        operation_id = "test_op_123"
        start_time = time.time()
        self.handler._active_operations[operation_id] = {
            "name": "test_operation",
            "start_time": start_time,
            "timeout": 30.0,
            "context": {"user_id": "test-user"},
        }

        active_ops = self.handler.get_active_operations()

        assert operation_id in active_ops
        op_info = active_ops[operation_id]
        assert op_info["name"] == "test_operation"
        assert op_info["timeout"] == 30.0
        assert "elapsed_seconds" in op_info
        assert "timeout_remaining" in op_info

    def test_cancel_operation(self):
        """Test cancelling an active operation."""
        operation_id = "test_op_123"
        self.handler._active_operations[operation_id] = {
            "name": "test_operation",
            "start_time": time.time(),
            "timeout": 30.0,
        }

        result = self.handler.cancel_operation(operation_id)
        assert result is True
        assert operation_id not in self.handler._active_operations

        # Try to cancel non-existent operation
        result = self.handler.cancel_operation("non_existent")
        assert result is False

    async def test_adaptive_timeout(self):
        """Test adaptive timeout based on performance history."""
        self.handler.config.enable_adaptive_timeout = True

        # Record some performance history
        for duration in [1.0, 1.2, 1.5, 1.8, 2.0]:
            self.handler._record_operation_performance("adaptive_op", duration, True)

        # Get effective timeout - should be based on performance history
        timeout = self.handler._get_effective_timeout("adaptive_op", None)

        # Should be higher than default due to performance history
        # (95th percentile * 1.5 buffer)
        expected_timeout = 2.0 * 1.5  # Max duration * buffer
        assert timeout == min(expected_timeout, self.config.max_timeout_seconds)


class TestTimeoutDecorator:
    """Test timeout decorator functionality."""

    @pytest.mark.asyncio
    async def test_with_timeout_decorator_success(self):
        """Test timeout decorator with successful operation."""

        @with_timeout(timeout_seconds=1.0, operation_name="decorated_test")
        async def decorated_operation():
            await asyncio.sleep(0.1)
            return "decorated_success"

        result = await decorated_operation()

        assert isinstance(result, TimeoutResult)
        assert result.success is True
        assert result.result == "decorated_success"

    @pytest.mark.asyncio
    async def test_with_timeout_decorator_failure(self):
        """Test timeout decorator with timeout."""

        @with_timeout(timeout_seconds=0.5, operation_name="decorated_timeout_test")
        async def decorated_slow_operation():
            await asyncio.sleep(2.0)
            return "should_not_reach"

        result = await decorated_slow_operation()

        assert isinstance(result, TimeoutResult)
        assert result.success is False
        assert result.timeout_occurred is True

    @pytest.mark.asyncio
    async def test_with_timeout_decorator_custom_strategy(self):
        """Test timeout decorator with custom strategy."""

        @with_timeout(
            timeout_seconds=0.5,
            operation_name="decorated_fail_fast_test",
            strategy=TimeoutStrategy.FAIL_FAST,
        )
        async def decorated_operation():
            await asyncio.sleep(2.0)
            return "should_not_reach"

        result = await decorated_operation()

        assert isinstance(result, TimeoutResult)
        assert result.success is False
        assert result.retry_count == 0  # No retries with fail-fast


class TestGlobalTimeoutHandler:
    """Test global timeout handler functions."""

    def test_get_timeout_handler_singleton(self):
        """Test that get_timeout_handler returns the same instance."""
        handler1 = get_timeout_handler()
        handler2 = get_timeout_handler()

        assert handler1 is handler2
        assert isinstance(handler1, TimeoutHandler)


@pytest.mark.asyncio
class TestTimeoutHandlerIntegration:
    """Integration tests for timeout handler."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = TimeoutHandler()

    async def test_complex_retry_scenario(self):
        """Test complex retry scenario with varying success."""
        attempt_count = 0

        async def flaky_operation():
            nonlocal attempt_count
            attempt_count += 1

            if attempt_count == 1:
                # First attempt: timeout
                await asyncio.sleep(2.0)
            elif attempt_count == 2:
                # Second attempt: exception
                raise ValueError("Temporary error")
            else:
                # Third attempt: success
                return f"success_on_attempt_{attempt_count}"

        result = await self.handler.execute_with_timeout(
            flaky_operation, "flaky_test", timeout_seconds=0.5
        )

        assert result.success is True
        assert result.result == "success_on_attempt_3"
        assert result.retry_count == 2
        assert attempt_count == 3

    async def test_timeout_with_context(self):
        """Test timeout handling with operation context."""

        async def operation_with_context():
            await asyncio.sleep(2.0)
            return "should_not_reach"

        context = {"user_id": "user-123", "resource_id": "resource-456", "operation_type": "test"}

        result = await self.handler.execute_with_timeout(
            operation_with_context, "context_test", timeout_seconds=0.5, context=context
        )

        assert result.success is False
        assert result.error is not None

        # Verify context is preserved in error
        error_details = result.error.get_technical_details()
        assert "additional_context" in error_details

    async def test_performance_tracking_integration(self):
        """Test integration of performance tracking with timeout handling."""
        # Execute several operations to build performance history
        for i in range(5):

            async def test_operation():
                await asyncio.sleep(0.1 * (i + 1))  # Varying durations
                return f"result_{i}"

            result = await self.handler.execute_with_timeout(
                test_operation, "perf_test", timeout_seconds=1.0
            )

            assert result.success is True

        # Check that performance stats were recorded
        stats = self.handler.get_operation_stats("perf_test")
        assert stats is not None
        assert stats["sample_count"] == 5
        assert stats["success_rate"] == 1.0
        assert stats["avg_duration"] > 0

    async def test_concurrent_operations(self):
        """Test handling multiple concurrent operations."""

        async def concurrent_operation(operation_id: str, delay: float):
            await asyncio.sleep(delay)
            return f"result_{operation_id}"

        # Start multiple operations concurrently
        tasks = []
        for i in range(3):
            task = self.handler.execute_with_timeout(
                concurrent_operation,
                f"concurrent_test_{i}",
                timeout_seconds=1.0,
                context={"operation_id": i},
                operation_id=f"op_{i}",
                delay=0.2 * (i + 1),
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # All operations should succeed
        for i, result in enumerate(results):
            assert result.success is True
            assert result.result == f"result_op_{i}"

    async def test_timeout_warning_system(self):
        """Test timeout warning system."""
        config = TimeoutConfig(
            enable_timeout_warnings=True, warning_threshold_ratio=0.5  # Warn at 50% of timeout
        )
        handler = TimeoutHandler(config)

        warning_issued = False

        async def operation_that_triggers_warning():
            nonlocal warning_issued
            await asyncio.sleep(0.6)  # Will trigger warning at 0.5s
            warning_issued = True
            return "completed_with_warning"

        with patch.object(handler.logger, "warning") as mock_warning:
            result = await handler.execute_with_timeout(
                operation_that_triggers_warning, "warning_test", timeout_seconds=1.0
            )

            assert result.success is True
            # Warning should have been logged
            mock_warning.assert_called()
            warning_call = mock_warning.call_args[0][0]
            assert "taking longer than expected" in warning_call
