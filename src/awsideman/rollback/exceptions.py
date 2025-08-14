"""Custom exception classes for rollback operations."""

from typing import Any, Dict, List, Optional


class RollbackError(Exception):
    """Base exception for rollback operations."""

    def __init__(
        self,
        message: str,
        operation_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        """Initialize rollback error.

        Args:
            message: Error message
            operation_id: Operation ID related to the error
            context: Additional context information
        """
        super().__init__(message)
        self.operation_id = operation_id
        self.context = context or {}


class OperationNotFoundError(RollbackError):
    """Exception raised when an operation is not found."""

    def __init__(self, operation_id: str):
        """Initialize operation not found error.

        Args:
            operation_id: The operation ID that was not found
        """
        super().__init__(
            f"Operation {operation_id} not found in rollback history",
            operation_id=operation_id,
        )


class OperationAlreadyRolledBackError(RollbackError):
    """Exception raised when attempting to rollback an already rolled back operation."""

    def __init__(self, operation_id: str, rollback_operation_id: Optional[str] = None):
        """Initialize already rolled back error.

        Args:
            operation_id: The operation ID that was already rolled back
            rollback_operation_id: The rollback operation ID if available
        """
        message = f"Operation {operation_id} has already been rolled back"
        if rollback_operation_id:
            message += f" (rollback operation: {rollback_operation_id})"

        super().__init__(
            message,
            operation_id=operation_id,
            context={"rollback_operation_id": rollback_operation_id},
        )


class RollbackValidationError(RollbackError):
    """Exception raised when rollback validation fails."""

    def __init__(
        self,
        operation_id: str,
        validation_errors: List[str],
        validation_warnings: Optional[List[str]] = None,
    ):
        """Initialize rollback validation error.

        Args:
            operation_id: The operation ID that failed validation
            validation_errors: List of validation error messages
            validation_warnings: List of validation warning messages
        """
        error_summary = f"Rollback validation failed for operation {operation_id}"
        if len(validation_errors) == 1:
            error_summary += f": {validation_errors[0]}"
        else:
            error_summary += f" with {len(validation_errors)} errors"

        super().__init__(
            error_summary,
            operation_id=operation_id,
            context={
                "validation_errors": validation_errors,
                "validation_warnings": validation_warnings or [],
            },
        )
        self.validation_errors = validation_errors
        self.validation_warnings = validation_warnings or []


class RollbackExecutionError(RollbackError):
    """Exception raised when rollback execution fails."""

    def __init__(
        self,
        operation_id: str,
        rollback_operation_id: str,
        failed_actions: int,
        total_actions: int,
        errors: List[str],
    ):
        """Initialize rollback execution error.

        Args:
            operation_id: The original operation ID
            rollback_operation_id: The rollback operation ID
            failed_actions: Number of failed actions
            total_actions: Total number of actions
            errors: List of error messages from failed actions
        """
        message = (
            f"Rollback execution failed for operation {operation_id}: "
            f"{failed_actions}/{total_actions} actions failed"
        )

        super().__init__(
            message,
            operation_id=operation_id,
            context={
                "rollback_operation_id": rollback_operation_id,
                "failed_actions": failed_actions,
                "total_actions": total_actions,
                "errors": errors,
            },
        )
        self.rollback_operation_id = rollback_operation_id
        self.failed_actions = failed_actions
        self.total_actions = total_actions
        self.errors = errors


class RollbackPartialFailureError(RollbackError):
    """Exception raised when rollback partially fails but some actions succeed."""

    def __init__(
        self,
        operation_id: str,
        rollback_operation_id: str,
        completed_actions: int,
        failed_actions: int,
        total_actions: int,
        errors: List[str],
    ):
        """Initialize rollback partial failure error.

        Args:
            operation_id: The original operation ID
            rollback_operation_id: The rollback operation ID
            completed_actions: Number of completed actions
            failed_actions: Number of failed actions
            total_actions: Total number of actions
            errors: List of error messages from failed actions
        """
        message = (
            f"Rollback partially failed for operation {operation_id}: "
            f"{completed_actions} succeeded, {failed_actions} failed out of {total_actions} total"
        )

        super().__init__(
            message,
            operation_id=operation_id,
            context={
                "rollback_operation_id": rollback_operation_id,
                "completed_actions": completed_actions,
                "failed_actions": failed_actions,
                "total_actions": total_actions,
                "errors": errors,
            },
        )
        self.rollback_operation_id = rollback_operation_id
        self.completed_actions = completed_actions
        self.failed_actions = failed_actions
        self.total_actions = total_actions
        self.errors = errors


class StateVerificationError(RollbackError):
    """Exception raised when state verification fails."""

    def __init__(
        self,
        operation_id: str,
        account_id: str,
        expected_state: str,
        actual_state: str,
        context: Optional[Dict[str, Any]] = None,
    ):
        """Initialize state verification error.

        Args:
            operation_id: The operation ID being verified
            account_id: The account ID where verification failed
            expected_state: The expected assignment state
            actual_state: The actual assignment state found
            context: Additional context information
        """
        message = (
            f"State verification failed for operation {operation_id} on account {account_id}: "
            f"expected {expected_state}, found {actual_state}"
        )

        super().__init__(
            message,
            operation_id=operation_id,
            context={
                "account_id": account_id,
                "expected_state": expected_state,
                "actual_state": actual_state,
                **(context or {}),
            },
        )
        self.account_id = account_id
        self.expected_state = expected_state
        self.actual_state = actual_state


class RollbackStorageError(RollbackError):
    """Exception raised when rollback storage operations fail."""

    def __init__(
        self,
        message: str,
        operation_id: Optional[str] = None,
        storage_path: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ):
        """Initialize rollback storage error.

        Args:
            message: Error message
            operation_id: Operation ID if applicable
            storage_path: Storage path where error occurred
            original_exception: Original exception that caused the storage error
        """
        super().__init__(
            message,
            operation_id=operation_id,
            context={
                "storage_path": storage_path,
                "original_exception": str(original_exception) if original_exception else None,
            },
        )
        self.storage_path = storage_path
        self.original_exception = original_exception


class RollbackConfigurationError(RollbackError):
    """Exception raised when rollback configuration is invalid."""

    def __init__(self, message: str, config_key: Optional[str] = None):
        """Initialize rollback configuration error.

        Args:
            message: Error message
            config_key: Configuration key that caused the error
        """
        super().__init__(
            message,
            context={"config_key": config_key},
        )
        self.config_key = config_key


class AWSClientNotAvailableError(RollbackError):
    """Exception raised when AWS client is not available for rollback operations."""

    def __init__(self, operation: str):
        """Initialize AWS client not available error.

        Args:
            operation: The operation that requires AWS client
        """
        super().__init__(
            f"AWS client not available for {operation}. "
            "Ensure AWS credentials are configured and client manager is initialized.",
            context={"operation": operation},
        )
        self.operation = operation


class RollbackTimeoutError(RollbackError):
    """Exception raised when rollback operations timeout."""

    def __init__(
        self,
        operation_id: str,
        timeout_seconds: int,
        completed_actions: int,
        total_actions: int,
    ):
        """Initialize rollback timeout error.

        Args:
            operation_id: The operation ID that timed out
            timeout_seconds: The timeout value in seconds
            completed_actions: Number of actions completed before timeout
            total_actions: Total number of actions
        """
        message = (
            f"Rollback operation {operation_id} timed out after {timeout_seconds} seconds. "
            f"Completed {completed_actions}/{total_actions} actions."
        )

        super().__init__(
            message,
            operation_id=operation_id,
            context={
                "timeout_seconds": timeout_seconds,
                "completed_actions": completed_actions,
                "total_actions": total_actions,
            },
        )
        self.timeout_seconds = timeout_seconds
        self.completed_actions = completed_actions
        self.total_actions = total_actions


class IdempotencyViolationError(RollbackError):
    """Exception raised when idempotency checks fail."""

    def __init__(
        self,
        operation_id: str,
        duplicate_rollback_id: str,
        message: Optional[str] = None,
    ):
        """Initialize idempotency violation error.

        Args:
            operation_id: The operation ID with idempotency violation
            duplicate_rollback_id: The existing rollback operation ID
            message: Custom error message
        """
        if not message:
            message = (
                f"Idempotency violation: Operation {operation_id} has already been rolled back "
                f"by rollback operation {duplicate_rollback_id}"
            )

        super().__init__(
            message,
            operation_id=operation_id,
            context={"duplicate_rollback_id": duplicate_rollback_id},
        )
        self.duplicate_rollback_id = duplicate_rollback_id
