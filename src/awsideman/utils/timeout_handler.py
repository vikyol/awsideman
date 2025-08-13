"""Timeout handling system for AWS Identity Center status monitoring operations."""

import asyncio
import functools
import signal
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Optional, TypeVar

from .error_handler import ErrorCategory, ErrorContext, ErrorSeverity, StatusError
from .logging_config import get_status_logger

T = TypeVar("T")


class TimeoutStrategy(str, Enum):
    """Strategies for handling timeouts."""

    FAIL_FAST = "fail_fast"  # Fail immediately on timeout
    RETRY_WITH_BACKOFF = "retry_with_backoff"  # Retry with exponential backoff
    GRACEFUL_DEGRADATION = "graceful_degradation"  # Return partial results
    EXTEND_TIMEOUT = "extend_timeout"  # Dynamically extend timeout


@dataclass
class TimeoutConfig:
    """Configuration for timeout handling."""

    default_timeout_seconds: float = 30.0
    max_timeout_seconds: float = 300.0
    retry_attempts: int = 3
    backoff_multiplier: float = 2.0
    max_backoff_seconds: float = 60.0
    strategy: TimeoutStrategy = TimeoutStrategy.RETRY_WITH_BACKOFF
    enable_timeout_warnings: bool = True
    warning_threshold_ratio: float = 0.8  # Warn when 80% of timeout is reached
    enable_adaptive_timeout: bool = True
    operation_timeout_overrides: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self):
        """Ensure collections are properly initialized."""
        if self.operation_timeout_overrides is None:
            self.operation_timeout_overrides = {}


@dataclass
class TimeoutResult:
    """Result of a timeout-handled operation."""

    success: bool
    result: Any = None
    error: Optional[StatusError] = None
    duration_seconds: float = 0.0
    timeout_occurred: bool = False
    retry_count: int = 0
    final_timeout_used: float = 0.0
    warnings: list = field(default_factory=list)

    def __post_init__(self):
        """Ensure collections are properly initialized."""
        if self.warnings is None:
            self.warnings = []


class TimeoutHandler:
    """
    Comprehensive timeout handler for status monitoring operations.

    Provides timeout management with multiple strategies including retries,
    graceful degradation, and adaptive timeout adjustment based on
    operation history and performance characteristics.
    """

    def __init__(self, config: Optional[TimeoutConfig] = None):
        """
        Initialize the timeout handler.

        Args:
            config: Timeout configuration
        """
        self.config = config or TimeoutConfig()
        self.logger = get_status_logger("timeout_handler")

        # Track operation performance for adaptive timeouts
        self._operation_history: Dict[str, list] = {}
        self._performance_stats: Dict[str, Dict[str, float]] = {}

        # Track active operations for monitoring
        self._active_operations: Dict[str, Dict[str, Any]] = {}

    async def execute_with_timeout(
        self,
        operation: Callable[..., Awaitable[T]],
        operation_name: str,
        timeout_seconds: Optional[float] = None,
        context: Optional[Dict[str, Any]] = None,
        *args,
        **kwargs,
    ) -> TimeoutResult:
        """
        Execute an async operation with comprehensive timeout handling.

        Args:
            operation: Async operation to execute
            operation_name: Name of the operation for logging and tracking
            timeout_seconds: Timeout in seconds (uses default if None)
            context: Additional context for error handling
            *args: Arguments to pass to the operation
            **kwargs: Keyword arguments to pass to the operation

        Returns:
            TimeoutResult: Result of the timeout-handled operation
        """
        start_time = time.time()
        operation_id = f"{operation_name}_{int(start_time * 1000)}"

        # Determine timeout to use
        effective_timeout = self._get_effective_timeout(operation_name, timeout_seconds)

        # Track active operation
        self._active_operations[operation_id] = {
            "name": operation_name,
            "start_time": start_time,
            "timeout": effective_timeout,
            "context": context or {},
        }

        try:
            self.logger.debug(
                f"Starting operation '{operation_name}' with {effective_timeout}s timeout"
            )

            # Execute with the configured strategy
            if self.config.strategy == TimeoutStrategy.FAIL_FAST:
                result = await self._execute_fail_fast(
                    operation, operation_id, effective_timeout, *args, **kwargs
                )
            elif self.config.strategy == TimeoutStrategy.RETRY_WITH_BACKOFF:
                result = await self._execute_with_retry(
                    operation, operation_id, effective_timeout, *args, **kwargs
                )
            elif self.config.strategy == TimeoutStrategy.GRACEFUL_DEGRADATION:
                result = await self._execute_with_degradation(
                    operation, operation_id, effective_timeout, *args, **kwargs
                )
            elif self.config.strategy == TimeoutStrategy.EXTEND_TIMEOUT:
                result = await self._execute_with_extension(
                    operation, operation_id, effective_timeout, *args, **kwargs
                )
            else:
                # Default to retry with backoff
                result = await self._execute_with_retry(
                    operation, operation_id, effective_timeout, *args, **kwargs
                )

            # Record performance data
            duration = time.time() - start_time
            self._record_operation_performance(operation_name, duration, result.success)

            result.duration_seconds = duration
            result.final_timeout_used = effective_timeout

            if result.success:
                self.logger.debug(
                    f"Operation '{operation_name}' completed successfully in {duration:.2f}s"
                )
            else:
                self.logger.warning(f"Operation '{operation_name}' failed after {duration:.2f}s")

            return result

        except Exception as e:
            # Handle unexpected errors
            duration = time.time() - start_time
            ErrorContext(
                component="TimeoutHandler",
                operation=operation_name,
                additional_context=context or {},
            )

            from .error_handler import handle_status_error

            status_error = handle_status_error(e, "TimeoutHandler", operation_name, **context or {})

            self.logger.error(
                f"Unexpected error in timeout handler for '{operation_name}': {str(e)}"
            )

            return TimeoutResult(
                success=False,
                error=status_error,
                duration_seconds=duration,
                final_timeout_used=effective_timeout,
            )

        finally:
            # Clean up active operation tracking
            self._active_operations.pop(operation_id, None)

    def execute_sync_with_timeout(
        self,
        operation: Callable[..., T],
        operation_name: str,
        timeout_seconds: Optional[float] = None,
        context: Optional[Dict[str, Any]] = None,
        *args,
        **kwargs,
    ) -> TimeoutResult:
        """
        Execute a synchronous operation with timeout handling.

        Args:
            operation: Synchronous operation to execute
            operation_name: Name of the operation
            timeout_seconds: Timeout in seconds
            context: Additional context
            *args: Arguments to pass to the operation
            **kwargs: Keyword arguments to pass to the operation

        Returns:
            TimeoutResult: Result of the timeout-handled operation
        """
        start_time = time.time()
        effective_timeout = self._get_effective_timeout(operation_name, timeout_seconds)

        try:
            self.logger.debug(
                f"Starting sync operation '{operation_name}' with {effective_timeout}s timeout"
            )

            # Use signal-based timeout for synchronous operations
            result = self._execute_sync_with_signal_timeout(
                operation, operation_name, effective_timeout, *args, **kwargs
            )

            duration = time.time() - start_time
            self._record_operation_performance(operation_name, duration, True)

            self.logger.debug(f"Sync operation '{operation_name}' completed in {duration:.2f}s")

            return TimeoutResult(
                success=True,
                result=result,
                duration_seconds=duration,
                final_timeout_used=effective_timeout,
            )

        except TimeoutError as e:
            duration = time.time() - start_time

            error_context = ErrorContext(
                component="TimeoutHandler",
                operation=operation_name,
                additional_context=context or {},
            )

            status_error = StatusError(
                error_id="SYNC_TIMEOUT_001",
                message=f"Synchronous operation '{operation_name}' timed out after {effective_timeout}s",
                category=ErrorCategory.TIMEOUT,
                severity=ErrorSeverity.MEDIUM,
                context=error_context,
                original_exception=e,
                is_retryable=True,
                retry_after_seconds=int(effective_timeout * 1.5),
            )

            self.logger.warning(
                f"Sync operation '{operation_name}' timed out after {effective_timeout}s"
            )

            return TimeoutResult(
                success=False,
                error=status_error,
                duration_seconds=duration,
                timeout_occurred=True,
                final_timeout_used=effective_timeout,
            )

        except Exception as e:
            duration = time.time() - start_time

            from .error_handler import handle_status_error

            status_error = handle_status_error(e, "TimeoutHandler", operation_name, **context or {})

            self.logger.error(f"Error in sync operation '{operation_name}': {str(e)}")

            return TimeoutResult(
                success=False,
                error=status_error,
                duration_seconds=duration,
                final_timeout_used=effective_timeout,
            )

    async def _execute_fail_fast(
        self,
        operation: Callable[..., Awaitable[Any]],
        operation_id: str,
        timeout_seconds: float,
        *args,
        **kwargs,
    ) -> TimeoutResult:
        """Execute operation with fail-fast timeout strategy."""
        try:
            # Set up timeout warning if enabled
            warning_task = None
            if self.config.enable_timeout_warnings:
                warning_time = timeout_seconds * self.config.warning_threshold_ratio
                warning_task = asyncio.create_task(
                    self._timeout_warning(operation_id, warning_time)
                )

            # Execute operation with timeout
            result = await asyncio.wait_for(operation(*args, **kwargs), timeout=timeout_seconds)

            # Cancel warning task if it's still running
            if warning_task and not warning_task.done():
                warning_task.cancel()

            return TimeoutResult(success=True, result=result)

        except asyncio.TimeoutError as e:
            # Cancel warning task
            if warning_task and not warning_task.done():
                warning_task.cancel()

            error_context = ErrorContext(
                component="TimeoutHandler",
                operation=self._active_operations.get(operation_id, {}).get("name", "unknown"),
                additional_context=self._active_operations.get(operation_id, {}).get("context", {}),
            )

            status_error = StatusError(
                error_id="TIMEOUT_001",
                message=f"Operation timed out after {timeout_seconds}s",
                category=ErrorCategory.TIMEOUT,
                severity=ErrorSeverity.MEDIUM,
                context=error_context,
                original_exception=e,
                is_retryable=True,
                retry_after_seconds=int(timeout_seconds * 1.5),
            )

            return TimeoutResult(success=False, error=status_error, timeout_occurred=True)

    async def _execute_with_retry(
        self,
        operation: Callable[..., Awaitable[Any]],
        operation_id: str,
        timeout_seconds: float,
        *args,
        **kwargs,
    ) -> TimeoutResult:
        """Execute operation with retry and backoff strategy."""
        last_error = None
        total_attempts = 0
        current_timeout = timeout_seconds

        for attempt in range(self.config.retry_attempts + 1):
            total_attempts += 1

            try:
                self.logger.debug(
                    f"Attempt {attempt + 1} for operation {operation_id} with {current_timeout}s timeout"
                )

                # Set up timeout warning
                warning_task = None
                if self.config.enable_timeout_warnings:
                    warning_time = current_timeout * self.config.warning_threshold_ratio
                    warning_task = asyncio.create_task(
                        self._timeout_warning(operation_id, warning_time)
                    )

                # Execute operation
                result = await asyncio.wait_for(operation(*args, **kwargs), timeout=current_timeout)

                # Cancel warning task
                if warning_task and not warning_task.done():
                    warning_task.cancel()

                return TimeoutResult(success=True, result=result, retry_count=attempt)

            except asyncio.TimeoutError as e:
                # Cancel warning task
                if warning_task and not warning_task.done():
                    warning_task.cancel()

                last_error = e

                if attempt < self.config.retry_attempts:
                    # Calculate backoff delay
                    backoff_delay = min(
                        self.config.backoff_multiplier**attempt, self.config.max_backoff_seconds
                    )

                    self.logger.warning(
                        f"Attempt {attempt + 1} timed out after {current_timeout}s, "
                        f"retrying in {backoff_delay}s"
                    )

                    await asyncio.sleep(backoff_delay)

                    # Increase timeout for next attempt
                    current_timeout = min(
                        current_timeout * self.config.backoff_multiplier,
                        self.config.max_timeout_seconds,
                    )
                else:
                    self.logger.error(
                        f"All {total_attempts} attempts failed for operation {operation_id}"
                    )

            except Exception as e:
                # Non-timeout error, don't retry
                if warning_task and not warning_task.done():
                    warning_task.cancel()

                from .error_handler import handle_status_error

                operation_name = self._active_operations.get(operation_id, {}).get(
                    "name", "unknown"
                )
                context = self._active_operations.get(operation_id, {}).get("context", {})

                status_error = handle_status_error(e, "TimeoutHandler", operation_name, **context)

                return TimeoutResult(success=False, error=status_error, retry_count=attempt)

        # All retries exhausted
        error_context = ErrorContext(
            component="TimeoutHandler",
            operation=self._active_operations.get(operation_id, {}).get("name", "unknown"),
            additional_context=self._active_operations.get(operation_id, {}).get("context", {}),
        )

        status_error = StatusError(
            error_id="TIMEOUT_RETRY_001",
            message=f"Operation failed after {total_attempts} attempts, final timeout: {current_timeout}s",
            category=ErrorCategory.TIMEOUT,
            severity=ErrorSeverity.HIGH,
            context=error_context,
            original_exception=last_error,
            is_retryable=False,
        )

        return TimeoutResult(
            success=False, error=status_error, timeout_occurred=True, retry_count=total_attempts - 1
        )

    async def _execute_with_degradation(
        self, operation: Callable, operation_id: str, timeout_seconds: float, *args, **kwargs
    ) -> TimeoutResult:
        """Execute operation with graceful degradation strategy."""
        # This strategy would need to be implemented based on the specific operation
        # For now, fall back to retry strategy
        return await self._execute_with_retry(
            operation, operation_id, timeout_seconds, *args, **kwargs
        )

    async def _execute_with_extension(
        self, operation: Callable, operation_id: str, timeout_seconds: float, *args, **kwargs
    ) -> TimeoutResult:
        """Execute operation with dynamic timeout extension strategy."""
        current_timeout = timeout_seconds
        extensions_used = 0
        max_extensions = 3

        while extensions_used <= max_extensions:
            try:
                self.logger.debug(
                    f"Executing with timeout {current_timeout}s (extension {extensions_used})"
                )

                # Set up timeout warning
                warning_task = None
                if self.config.enable_timeout_warnings:
                    warning_time = current_timeout * self.config.warning_threshold_ratio
                    warning_task = asyncio.create_task(
                        self._timeout_warning(operation_id, warning_time)
                    )

                result = await asyncio.wait_for(operation(*args, **kwargs), timeout=current_timeout)

                # Cancel warning task
                if warning_task and not warning_task.done():
                    warning_task.cancel()

                return TimeoutResult(
                    success=True,
                    result=result,
                    warnings=(
                        [f"Used {extensions_used} timeout extensions"]
                        if extensions_used > 0
                        else []
                    ),
                )

            except asyncio.TimeoutError:
                # Cancel warning task
                if warning_task and not warning_task.done():
                    warning_task.cancel()

                if extensions_used < max_extensions:
                    extensions_used += 1
                    # Extend timeout by 50%
                    current_timeout = min(current_timeout * 1.5, self.config.max_timeout_seconds)
                    self.logger.warning(
                        f"Extending timeout to {current_timeout}s (extension {extensions_used})"
                    )
                else:
                    # No more extensions allowed
                    break

        # Timeout with all extensions exhausted
        error_context = ErrorContext(
            component="TimeoutHandler",
            operation=self._active_operations.get(operation_id, {}).get("name", "unknown"),
            additional_context=self._active_operations.get(operation_id, {}).get("context", {}),
        )

        status_error = StatusError(
            error_id="TIMEOUT_EXT_001",
            message=f"Operation timed out after {extensions_used} extensions, final timeout: {current_timeout}s",
            category=ErrorCategory.TIMEOUT,
            severity=ErrorSeverity.HIGH,
            context=error_context,
            is_retryable=True,
            retry_after_seconds=int(current_timeout),
        )

        return TimeoutResult(
            success=False,
            error=status_error,
            timeout_occurred=True,
            warnings=[f"Used all {extensions_used} timeout extensions"],
        )

    def _execute_sync_with_signal_timeout(
        self, operation: Callable, operation_name: str, timeout_seconds: float, *args, **kwargs
    ) -> Any:
        """Execute synchronous operation with signal-based timeout."""

        def timeout_handler(signum, frame):
            raise TimeoutError(f"Operation '{operation_name}' timed out after {timeout_seconds}s")

        # Set up signal handler (Unix only)
        if hasattr(signal, "SIGALRM"):
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(int(timeout_seconds))

            try:
                result = operation(*args, **kwargs)
                signal.alarm(0)  # Cancel the alarm
                return result
            finally:
                signal.signal(signal.SIGALRM, old_handler)
        else:
            # Fallback for systems without SIGALRM (like Windows)
            # This is less precise but works cross-platform
            import threading

            result_container = {"result": None, "exception": None, "completed": False}

            def run_operation():
                try:
                    result_container["result"] = operation(*args, **kwargs)
                    result_container["completed"] = True
                except Exception as e:
                    result_container["exception"] = e
                    result_container["completed"] = True

            thread = threading.Thread(target=run_operation)
            thread.daemon = True
            thread.start()
            thread.join(timeout_seconds)

            if not result_container["completed"]:
                raise TimeoutError(
                    f"Operation '{operation_name}' timed out after {timeout_seconds}s"
                )

            if result_container["exception"]:
                raise result_container["exception"]

            return result_container["result"]

    async def _timeout_warning(self, operation_id: str, warning_delay: float) -> None:
        """Issue a warning when operation is taking longer than expected."""
        await asyncio.sleep(warning_delay)

        operation_info = self._active_operations.get(operation_id, {})
        operation_name = operation_info.get("name", "unknown")
        total_timeout = operation_info.get("timeout", 0)

        self.logger.warning(
            f"Operation '{operation_name}' is taking longer than expected "
            f"({warning_delay:.1f}s elapsed, {total_timeout:.1f}s timeout)"
        )

    def _get_effective_timeout(
        self, operation_name: str, requested_timeout: Optional[float]
    ) -> float:
        """Determine the effective timeout to use for an operation."""
        # Use requested timeout if provided
        if requested_timeout is not None:
            return min(requested_timeout, self.config.max_timeout_seconds)

        # Check for operation-specific override
        if operation_name in self.config.operation_timeout_overrides:
            return min(
                self.config.operation_timeout_overrides[operation_name],
                self.config.max_timeout_seconds,
            )

        # Use adaptive timeout if enabled and we have performance data
        if self.config.enable_adaptive_timeout and operation_name in self._performance_stats:
            stats = self._performance_stats[operation_name]
            # Use 95th percentile + 50% buffer
            adaptive_timeout = stats.get("p95_duration", self.config.default_timeout_seconds) * 1.5
            return min(adaptive_timeout, self.config.max_timeout_seconds)

        # Fall back to default
        return self.config.default_timeout_seconds

    def _record_operation_performance(
        self, operation_name: str, duration: float, success: bool
    ) -> None:
        """Record performance data for adaptive timeout calculation."""
        if operation_name not in self._operation_history:
            self._operation_history[operation_name] = []

        # Keep only recent history (last 100 operations)
        history = self._operation_history[operation_name]
        history.append({"duration": duration, "success": success, "timestamp": time.time()})

        if len(history) > 100:
            history.pop(0)

        # Update performance statistics
        successful_durations = [h["duration"] for h in history if h["success"]]

        if successful_durations:
            successful_durations.sort()
            count = len(successful_durations)

            self._performance_stats[operation_name] = {
                "avg_duration": sum(successful_durations) / count,
                "min_duration": min(successful_durations),
                "max_duration": max(successful_durations),
                "p50_duration": successful_durations[count // 2],
                "p95_duration": (
                    successful_durations[int(count * 0.95)]
                    if count > 20
                    else max(successful_durations)
                ),
                "success_rate": len(successful_durations) / len(history),
                "sample_count": count,
            }

    def get_operation_stats(self, operation_name: str) -> Optional[Dict[str, float]]:
        """Get performance statistics for an operation."""
        return self._performance_stats.get(operation_name)

    def get_active_operations(self) -> Dict[str, Dict[str, Any]]:
        """Get information about currently active operations."""
        current_time = time.time()
        active_ops = {}

        for op_id, op_info in self._active_operations.items():
            elapsed = current_time - op_info["start_time"]
            active_ops[op_id] = {
                **op_info,
                "elapsed_seconds": elapsed,
                "timeout_remaining": max(0, op_info["timeout"] - elapsed),
            }

        return active_ops

    def cancel_operation(self, operation_id: str) -> bool:
        """
        Cancel an active operation (if possible).

        Args:
            operation_id: ID of the operation to cancel

        Returns:
            bool: True if operation was found and cancelled
        """
        if operation_id in self._active_operations:
            self.logger.info(f"Cancelling operation {operation_id}")
            # In a real implementation, this would need to coordinate with the actual operation
            # For now, just remove from tracking
            del self._active_operations[operation_id]
            return True
        return False


# Global timeout handler instance
_global_timeout_handler: Optional[TimeoutHandler] = None


def get_timeout_handler() -> TimeoutHandler:
    """Get the global timeout handler instance."""
    global _global_timeout_handler
    if _global_timeout_handler is None:
        _global_timeout_handler = TimeoutHandler()
    return _global_timeout_handler


def with_timeout(
    timeout_seconds: Optional[float] = None,
    operation_name: Optional[str] = None,
    strategy: Optional[TimeoutStrategy] = None,
):
    """
    Decorator for adding timeout handling to async functions.

    Args:
        timeout_seconds: Timeout in seconds
        operation_name: Name of the operation (uses function name if None)
        strategy: Timeout strategy to use

    Returns:
        Decorated function with timeout handling
    """

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[TimeoutResult]]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> TimeoutResult:
            handler = get_timeout_handler()
            op_name = operation_name or func.__name__

            # Temporarily override strategy if specified
            original_strategy = handler.config.strategy
            if strategy:
                handler.config.strategy = strategy

            try:
                return await handler.execute_with_timeout(
                    func, op_name, timeout_seconds, None, *args, **kwargs
                )
            finally:
                # Restore original strategy
                handler.config.strategy = original_strategy

        return wrapper

    return decorator
