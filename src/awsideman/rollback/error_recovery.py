"""Error recovery strategies for rollback operations."""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from botocore.exceptions import ClientError
from rich.console import Console

from .exceptions import (
    AWSClientNotAvailableError,
    RollbackExecutionError,
    RollbackPartialFailureError,
    RollbackTimeoutError,
)

console = Console()
logger = logging.getLogger(__name__)


class RecoveryStrategy(str, Enum):
    """Recovery strategies for different types of errors."""

    RETRY = "retry"
    SKIP = "skip"
    FAIL_FAST = "fail_fast"
    CONTINUE = "continue"
    MANUAL_INTERVENTION = "manual_intervention"


class ErrorType(str, Enum):
    """Types of errors that can occur during rollback operations."""

    TRANSIENT_AWS_ERROR = "transient_aws_error"
    PERMISSION_ERROR = "permission_error"
    RESOURCE_NOT_FOUND = "resource_not_found"
    CONFLICT_ERROR = "conflict_error"
    TIMEOUT_ERROR = "timeout_error"
    NETWORK_ERROR = "network_error"
    CONFIGURATION_ERROR = "configuration_error"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    initial_delay: float = 1.0
    max_delay: float = 60.0
    backoff_multiplier: float = 2.0
    jitter: bool = True
    retryable_error_codes: List[str] = field(
        default_factory=lambda: [
            "ThrottlingException",
            "TooManyRequestsException",
            "ServiceUnavailableException",
            "InternalServerError",
            "RequestTimeout",
            "ServiceTemporarilyUnavailable",
        ]
    )


@dataclass
class RecoveryAction:
    """A recovery action to be taken for a specific error."""

    strategy: RecoveryStrategy
    description: str
    retry_config: Optional[RetryConfig] = None
    skip_reason: Optional[str] = None
    manual_steps: Optional[List[str]] = None


@dataclass
class ErrorRecoveryResult:
    """Result of error recovery attempt."""

    success: bool
    strategy_used: RecoveryStrategy
    attempts_made: int
    final_error: Optional[Exception] = None
    recovery_notes: List[str] = field(default_factory=list)


class RollbackErrorRecovery:
    """Error recovery system for rollback operations."""

    def __init__(self, retry_config: Optional[RetryConfig] = None):
        """Initialize error recovery system.

        Args:
            retry_config: Configuration for retry behavior
        """
        self.retry_config = retry_config or RetryConfig()
        self._error_strategies: Dict[ErrorType, RecoveryAction] = {}
        self._setup_default_strategies()

    def _setup_default_strategies(self) -> None:
        """Set up default recovery strategies for different error types."""
        self._error_strategies = {
            ErrorType.TRANSIENT_AWS_ERROR: RecoveryAction(
                strategy=RecoveryStrategy.RETRY,
                description="Retry transient AWS API errors with exponential backoff",
                retry_config=self.retry_config,
            ),
            ErrorType.PERMISSION_ERROR: RecoveryAction(
                strategy=RecoveryStrategy.FAIL_FAST,
                description="Fail immediately for permission errors",
                manual_steps=[
                    "Verify AWS credentials are valid and not expired",
                    "Check IAM permissions for Identity Center operations",
                    "Ensure the user has necessary permissions for rollback operations",
                ],
            ),
            ErrorType.RESOURCE_NOT_FOUND: RecoveryAction(
                strategy=RecoveryStrategy.SKIP,
                description="Skip actions for resources that no longer exist",
                skip_reason="Resource no longer exists, rollback not needed",
            ),
            ErrorType.CONFLICT_ERROR: RecoveryAction(
                strategy=RecoveryStrategy.CONTINUE,
                description="Continue with remaining actions when conflicts occur",
            ),
            ErrorType.TIMEOUT_ERROR: RecoveryAction(
                strategy=RecoveryStrategy.RETRY,
                description="Retry operations that timeout",
                retry_config=RetryConfig(
                    max_attempts=2,
                    initial_delay=5.0,
                    max_delay=30.0,
                    backoff_multiplier=1.5,
                ),
            ),
            ErrorType.NETWORK_ERROR: RecoveryAction(
                strategy=RecoveryStrategy.RETRY,
                description="Retry network-related errors",
                retry_config=RetryConfig(
                    max_attempts=3,
                    initial_delay=2.0,
                    max_delay=20.0,
                    backoff_multiplier=2.0,
                ),
            ),
            ErrorType.CONFIGURATION_ERROR: RecoveryAction(
                strategy=RecoveryStrategy.FAIL_FAST,
                description="Fail immediately for configuration errors",
                manual_steps=[
                    "Check rollback configuration settings",
                    "Verify AWS profile and region settings",
                    "Ensure all required configuration values are provided",
                ],
            ),
            ErrorType.UNKNOWN_ERROR: RecoveryAction(
                strategy=RecoveryStrategy.RETRY,
                description="Retry unknown errors with limited attempts",
                retry_config=RetryConfig(
                    max_attempts=2,
                    initial_delay=1.0,
                    max_delay=10.0,
                    backoff_multiplier=2.0,
                ),
            ),
        }

    def classify_error(self, error: Exception) -> ErrorType:
        """Classify an error to determine the appropriate recovery strategy.

        Args:
            error: The exception to classify

        Returns:
            ErrorType: The classified error type
        """
        if isinstance(error, ClientError):
            error_code = error.response.get("Error", {}).get("Code", "")

            # Permission errors
            if error_code in ["AccessDenied", "UnauthorizedOperation", "Forbidden"]:
                return ErrorType.PERMISSION_ERROR

            # Resource not found errors
            if error_code in ["ResourceNotFoundException", "NoSuchEntity", "NotFound"]:
                return ErrorType.RESOURCE_NOT_FOUND

            # Conflict errors (assignment already exists/doesn't exist)
            if error_code in ["ConflictException", "ResourceConflictException"]:
                return ErrorType.CONFLICT_ERROR

            # Transient errors
            if error_code in self.retry_config.retryable_error_codes:
                return ErrorType.TRANSIENT_AWS_ERROR

            # Timeout errors
            if error_code in ["RequestTimeout", "TimeoutException"]:
                return ErrorType.TIMEOUT_ERROR

        # Network-related errors
        if isinstance(error, (ConnectionError, TimeoutError, asyncio.TimeoutError)):
            return ErrorType.NETWORK_ERROR

        # Rollback-specific errors
        if isinstance(error, (RollbackTimeoutError,)):
            return ErrorType.TIMEOUT_ERROR

        if isinstance(error, (AWSClientNotAvailableError,)):
            return ErrorType.CONFIGURATION_ERROR

        # Default to unknown error
        return ErrorType.UNKNOWN_ERROR

    def get_recovery_action(self, error: Exception) -> RecoveryAction:
        """Get the recovery action for a specific error.

        Args:
            error: The exception to get recovery action for

        Returns:
            RecoveryAction: The recovery action to take
        """
        error_type = self.classify_error(error)
        return self._error_strategies.get(
            error_type, self._error_strategies[ErrorType.UNKNOWN_ERROR]
        )

    def execute_with_recovery(
        self,
        operation: Callable[[], Any],
        operation_name: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ErrorRecoveryResult:
        """Execute an operation with error recovery.

        Args:
            operation: The operation to execute
            operation_name: Name of the operation for logging
            context: Additional context information

        Returns:
            ErrorRecoveryResult: Result of the operation with recovery
        """
        context = context or {}
        attempts = 0
        last_error = None
        recovery_notes = []

        while attempts < self.retry_config.max_attempts:
            attempts += 1

            try:
                logger.debug(f"Executing {operation_name}, attempt {attempts}")
                operation()

                if attempts > 1:
                    recovery_notes.append(f"Operation succeeded after {attempts} attempts")

                return ErrorRecoveryResult(
                    success=True,
                    strategy_used=(
                        RecoveryStrategy.RETRY if attempts > 1 else RecoveryStrategy.CONTINUE
                    ),
                    attempts_made=attempts,
                    recovery_notes=recovery_notes,
                )

            except Exception as error:
                last_error = error
                recovery_action = self.get_recovery_action(error)

                logger.debug(
                    f"Error in {operation_name} (attempt {attempts}): {error}, "
                    f"strategy: {recovery_action.strategy}"
                )

                # Handle different recovery strategies
                if recovery_action.strategy == RecoveryStrategy.FAIL_FAST:
                    recovery_notes.append(f"Failed fast due to {recovery_action.description}")
                    break

                elif recovery_action.strategy == RecoveryStrategy.SKIP:
                    recovery_notes.append(
                        f"Skipped: {recovery_action.skip_reason or recovery_action.description}"
                    )
                    return ErrorRecoveryResult(
                        success=True,  # Consider skip as success
                        strategy_used=RecoveryStrategy.SKIP,
                        attempts_made=attempts,
                        recovery_notes=recovery_notes,
                    )

                elif recovery_action.strategy == RecoveryStrategy.CONTINUE:
                    recovery_notes.append(
                        f"Continuing despite error: {recovery_action.description}"
                    )
                    return ErrorRecoveryResult(
                        success=True,  # Consider continue as success
                        strategy_used=RecoveryStrategy.CONTINUE,
                        attempts_made=attempts,
                        final_error=error,
                        recovery_notes=recovery_notes,
                    )

                elif recovery_action.strategy == RecoveryStrategy.RETRY:
                    if attempts < self.retry_config.max_attempts:
                        delay = self._calculate_retry_delay(attempts, recovery_action.retry_config)
                        recovery_notes.append(f"Retrying after {delay:.1f}s due to {error}")
                        logger.debug(f"Retrying {operation_name} in {delay:.1f} seconds")
                        time.sleep(delay)
                        continue
                    else:
                        recovery_notes.append(
                            f"Max retry attempts ({self.retry_config.max_attempts}) exceeded"
                        )
                        break

                elif recovery_action.strategy == RecoveryStrategy.MANUAL_INTERVENTION:
                    recovery_notes.append("Manual intervention required")
                    recovery_notes.extend(recovery_action.manual_steps or [])
                    break

        # If we get here, all retry attempts failed
        # Use the strategy from the last recovery action, not hardcoded RETRY
        last_recovery_action = self.get_recovery_action(last_error) if last_error else None
        strategy_used = (
            last_recovery_action.strategy if last_recovery_action else RecoveryStrategy.RETRY
        )

        return ErrorRecoveryResult(
            success=False,
            strategy_used=strategy_used,
            attempts_made=attempts,
            final_error=last_error,
            recovery_notes=recovery_notes,
        )

    def _calculate_retry_delay(
        self, attempt: int, retry_config: Optional[RetryConfig] = None
    ) -> float:
        """Calculate the delay before the next retry attempt.

        Args:
            attempt: Current attempt number (1-based)
            retry_config: Retry configuration to use

        Returns:
            float: Delay in seconds
        """
        config = retry_config or self.retry_config

        # Calculate exponential backoff delay
        delay = config.initial_delay * (config.backoff_multiplier ** (attempt - 1))

        # Apply maximum delay limit
        delay = min(delay, config.max_delay)

        # Add jitter to prevent thundering herd
        if config.jitter:
            import random

            jitter_factor = random.uniform(0.8, 1.2)
            delay *= jitter_factor

        return delay

    def handle_partial_failure(
        self,
        operation_id: str,
        rollback_operation_id: str,
        completed_actions: int,
        failed_actions: int,
        total_actions: int,
        errors: List[str],
    ) -> ErrorRecoveryResult:
        """Handle partial failure scenarios in rollback operations.

        Args:
            operation_id: Original operation ID
            rollback_operation_id: Rollback operation ID
            completed_actions: Number of completed actions
            failed_actions: Number of failed actions
            total_actions: Total number of actions
            errors: List of error messages

        Returns:
            ErrorRecoveryResult: Recovery result for partial failure
        """
        recovery_notes = []

        # Calculate success rate
        success_rate = completed_actions / total_actions if total_actions > 0 else 0

        if success_rate >= 0.8:  # 80% success rate
            recovery_notes.append(
                f"Partial rollback successful: {completed_actions}/{total_actions} actions completed"
            )
            recovery_notes.append("High success rate, considering operation successful")

            # Log failed actions for manual review
            if errors:
                recovery_notes.append("Failed actions require manual review:")
                recovery_notes.extend(errors[:5])  # Limit to first 5 errors
                if len(errors) > 5:
                    recovery_notes.append(f"... and {len(errors) - 5} more errors")

            return ErrorRecoveryResult(
                success=True,
                strategy_used=RecoveryStrategy.CONTINUE,
                attempts_made=1,
                recovery_notes=recovery_notes,
            )

        elif success_rate >= 0.5:  # 50% success rate
            recovery_notes.append(
                f"Partial rollback with moderate success: {completed_actions}/{total_actions} actions completed"
            )
            recovery_notes.append("Manual intervention recommended to complete remaining actions")
            recovery_notes.extend(
                [
                    "Consider:",
                    "1. Review failed actions and retry manually",
                    "2. Verify AWS permissions and resource states",
                    "3. Check for conflicting assignments",
                ]
            )

            return ErrorRecoveryResult(
                success=False,
                strategy_used=RecoveryStrategy.MANUAL_INTERVENTION,
                attempts_made=1,
                final_error=RollbackPartialFailureError(
                    operation_id=operation_id,
                    rollback_operation_id=rollback_operation_id,
                    completed_actions=completed_actions,
                    failed_actions=failed_actions,
                    total_actions=total_actions,
                    errors=errors,
                ),
                recovery_notes=recovery_notes,
            )

        else:  # Low success rate
            recovery_notes.append(
                f"Rollback mostly failed: only {completed_actions}/{total_actions} actions completed"
            )
            recovery_notes.append("Operation considered failed, manual intervention required")

            return ErrorRecoveryResult(
                success=False,
                strategy_used=RecoveryStrategy.FAIL_FAST,
                attempts_made=1,
                final_error=RollbackExecutionError(
                    operation_id=operation_id,
                    rollback_operation_id=rollback_operation_id,
                    failed_actions=failed_actions,
                    total_actions=total_actions,
                    errors=errors,
                ),
                recovery_notes=recovery_notes,
            )

    def register_custom_strategy(
        self, error_type: ErrorType, recovery_action: RecoveryAction
    ) -> None:
        """Register a custom recovery strategy for an error type.

        Args:
            error_type: The error type to register strategy for
            recovery_action: The recovery action to take
        """
        self._error_strategies[error_type] = recovery_action
        logger.debug(f"Registered custom recovery strategy for {error_type}")

    def get_recovery_summary(self, results: List[ErrorRecoveryResult]) -> Dict[str, Any]:
        """Get a summary of recovery results.

        Args:
            results: List of recovery results

        Returns:
            Dict containing recovery summary statistics
        """
        if not results:
            return {"total_operations": 0}

        total_operations = len(results)
        successful_operations = sum(1 for r in results if r.success)
        failed_operations = total_operations - successful_operations

        total_attempts = sum(r.attempts_made for r in results)
        avg_attempts = total_attempts / total_operations if total_operations > 0 else 0

        strategies_used = {}
        for result in results:
            strategy = result.strategy_used.value
            strategies_used[strategy] = strategies_used.get(strategy, 0) + 1

        return {
            "total_operations": total_operations,
            "successful_operations": successful_operations,
            "failed_operations": failed_operations,
            "success_rate": successful_operations / total_operations if total_operations > 0 else 0,
            "average_attempts": avg_attempts,
            "strategies_used": strategies_used,
            "total_recovery_notes": sum(len(r.recovery_notes) for r in results),
        }


# Global error recovery instance
_global_error_recovery: Optional[RollbackErrorRecovery] = None


def get_error_recovery() -> RollbackErrorRecovery:
    """Get the global error recovery instance."""
    global _global_error_recovery
    if _global_error_recovery is None:
        _global_error_recovery = RollbackErrorRecovery()
    return _global_error_recovery


def with_rollback_retry(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_multiplier: float = 2.0,
):
    """Decorator for adding retry logic to rollback operations.

    Args:
        max_attempts: Maximum number of retry attempts
        initial_delay: Initial delay between retries
        max_delay: Maximum delay between retries
        backoff_multiplier: Backoff multiplier for exponential backoff

    Returns:
        Decorator function
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            retry_config = RetryConfig(
                max_attempts=max_attempts,
                initial_delay=initial_delay,
                max_delay=max_delay,
                backoff_multiplier=backoff_multiplier,
            )

            recovery = RollbackErrorRecovery(retry_config)

            def operation():
                return func(*args, **kwargs)

            result = recovery.execute_with_recovery(
                operation=operation,
                operation_name=func.__name__,
            )

            if not result.success and result.final_error:
                raise result.final_error

            return result

        return wrapper

    return decorator
