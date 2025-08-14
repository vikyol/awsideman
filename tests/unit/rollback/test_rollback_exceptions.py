"""Tests for rollback exception classes."""

from src.awsideman.rollback.exceptions import (
    AWSClientNotAvailableError,
    IdempotencyViolationError,
    OperationAlreadyRolledBackError,
    OperationNotFoundError,
    RollbackConfigurationError,
    RollbackError,
    RollbackExecutionError,
    RollbackPartialFailureError,
    RollbackStorageError,
    RollbackTimeoutError,
    RollbackValidationError,
    StateVerificationError,
)


class TestRollbackError:
    """Test the base RollbackError class."""

    def test_basic_rollback_error(self):
        """Test basic rollback error creation."""
        error = RollbackError("Test error message")

        assert str(error) == "Test error message"
        assert error.operation_id is None
        assert error.context == {}

    def test_rollback_error_with_operation_id(self):
        """Test rollback error with operation ID."""
        operation_id = "test-op-123"
        error = RollbackError("Test error", operation_id=operation_id)

        assert error.operation_id == operation_id

    def test_rollback_error_with_context(self):
        """Test rollback error with context."""
        context = {"key": "value", "number": 42}
        error = RollbackError("Test error", context=context)

        assert error.context == context


class TestOperationNotFoundError:
    """Test the OperationNotFoundError class."""

    def test_operation_not_found_error(self):
        """Test operation not found error creation."""
        operation_id = "missing-op-123"
        error = OperationNotFoundError(operation_id)

        assert error.operation_id == operation_id
        assert "Operation missing-op-123 not found" in str(error)


class TestOperationAlreadyRolledBackError:
    """Test the OperationAlreadyRolledBackError class."""

    def test_already_rolled_back_without_rollback_id(self):
        """Test already rolled back error without rollback operation ID."""
        operation_id = "rolled-back-op-123"
        error = OperationAlreadyRolledBackError(operation_id)

        assert error.operation_id == operation_id
        assert "already been rolled back" in str(error)
        assert error.context.get("rollback_operation_id") is None

    def test_already_rolled_back_with_rollback_id(self):
        """Test already rolled back error with rollback operation ID."""
        operation_id = "rolled-back-op-123"
        rollback_id = "rollback-op-456"
        error = OperationAlreadyRolledBackError(operation_id, rollback_id)

        assert error.operation_id == operation_id
        assert rollback_id in str(error)
        assert error.context["rollback_operation_id"] == rollback_id


class TestRollbackValidationError:
    """Test the RollbackValidationError class."""

    def test_validation_error_single_error(self):
        """Test validation error with single error."""
        operation_id = "invalid-op-123"
        errors = ["Permission denied"]
        error = RollbackValidationError(operation_id, errors)

        assert error.operation_id == operation_id
        assert error.validation_errors == errors
        assert error.validation_warnings == []
        assert "Permission denied" in str(error)

    def test_validation_error_multiple_errors(self):
        """Test validation error with multiple errors."""
        operation_id = "invalid-op-123"
        errors = ["Permission denied", "Resource not found", "Invalid state"]
        warnings = ["This might cause issues"]
        error = RollbackValidationError(operation_id, errors, warnings)

        assert error.validation_errors == errors
        assert error.validation_warnings == warnings
        assert "3 errors" in str(error)

    def test_validation_error_context(self):
        """Test validation error context."""
        operation_id = "invalid-op-123"
        errors = ["Error 1", "Error 2"]
        warnings = ["Warning 1"]
        error = RollbackValidationError(operation_id, errors, warnings)

        assert error.context["validation_errors"] == errors
        assert error.context["validation_warnings"] == warnings


class TestRollbackExecutionError:
    """Test the RollbackExecutionError class."""

    def test_execution_error(self):
        """Test rollback execution error."""
        operation_id = "failed-op-123"
        rollback_id = "rollback-op-456"
        failed_actions = 3
        total_actions = 10
        errors = ["Error 1", "Error 2", "Error 3"]

        error = RollbackExecutionError(
            operation_id, rollback_id, failed_actions, total_actions, errors
        )

        assert error.operation_id == operation_id
        assert error.rollback_operation_id == rollback_id
        assert error.failed_actions == failed_actions
        assert error.total_actions == total_actions
        assert error.errors == errors
        assert "3/10 actions failed" in str(error)


class TestRollbackPartialFailureError:
    """Test the RollbackPartialFailureError class."""

    def test_partial_failure_error(self):
        """Test rollback partial failure error."""
        operation_id = "partial-fail-op-123"
        rollback_id = "rollback-op-456"
        completed_actions = 7
        failed_actions = 3
        total_actions = 10
        errors = ["Error 1", "Error 2", "Error 3"]

        error = RollbackPartialFailureError(
            operation_id, rollback_id, completed_actions, failed_actions, total_actions, errors
        )

        assert error.operation_id == operation_id
        assert error.rollback_operation_id == rollback_id
        assert error.completed_actions == completed_actions
        assert error.failed_actions == failed_actions
        assert error.total_actions == total_actions
        assert error.errors == errors
        assert "7 succeeded, 3 failed out of 10 total" in str(error)


class TestStateVerificationError:
    """Test the StateVerificationError class."""

    def test_state_verification_error(self):
        """Test state verification error."""
        operation_id = "verify-op-123"
        account_id = "123456789012"
        expected_state = "assigned"
        actual_state = "not_assigned"

        error = StateVerificationError(operation_id, account_id, expected_state, actual_state)

        assert error.operation_id == operation_id
        assert error.account_id == account_id
        assert error.expected_state == expected_state
        assert error.actual_state == actual_state
        assert "expected assigned, found not_assigned" in str(error)

    def test_state_verification_error_with_context(self):
        """Test state verification error with additional context."""
        operation_id = "verify-op-123"
        account_id = "123456789012"
        expected_state = "assigned"
        actual_state = "not_assigned"
        context = {"permission_set": "ReadOnlyAccess", "principal": "user-123"}

        error = StateVerificationError(
            operation_id, account_id, expected_state, actual_state, context
        )

        assert error.context["permission_set"] == "ReadOnlyAccess"
        assert error.context["principal"] == "user-123"


class TestRollbackStorageError:
    """Test the RollbackStorageError class."""

    def test_storage_error_basic(self):
        """Test basic storage error."""
        message = "Failed to write operation record"
        error = RollbackStorageError(message)

        assert str(error) == message
        assert error.storage_path is None
        assert error.original_exception is None

    def test_storage_error_with_details(self):
        """Test storage error with details."""
        message = "Failed to write operation record"
        operation_id = "storage-op-123"
        storage_path = "/path/to/operations.json"
        original_exception = IOError("Disk full")

        error = RollbackStorageError(message, operation_id, storage_path, original_exception)

        assert error.operation_id == operation_id
        assert error.storage_path == storage_path
        assert error.original_exception == original_exception
        assert error.context["storage_path"] == storage_path
        assert "Disk full" in error.context["original_exception"]


class TestRollbackConfigurationError:
    """Test the RollbackConfigurationError class."""

    def test_configuration_error(self):
        """Test configuration error."""
        message = "Invalid rollback configuration"
        config_key = "rollback.retention_days"

        error = RollbackConfigurationError(message, config_key)

        assert str(error) == message
        assert error.config_key == config_key
        assert error.context["config_key"] == config_key


class TestAWSClientNotAvailableError:
    """Test the AWSClientNotAvailableError class."""

    def test_aws_client_not_available_error(self):
        """Test AWS client not available error."""
        operation = "rollback execution"
        error = AWSClientNotAvailableError(operation)

        assert error.operation == operation
        assert "AWS client not available for rollback execution" in str(error)
        assert "AWS credentials are configured" in str(error)


class TestRollbackTimeoutError:
    """Test the RollbackTimeoutError class."""

    def test_timeout_error(self):
        """Test rollback timeout error."""
        operation_id = "timeout-op-123"
        timeout_seconds = 300
        completed_actions = 5
        total_actions = 10

        error = RollbackTimeoutError(
            operation_id, timeout_seconds, completed_actions, total_actions
        )

        assert error.operation_id == operation_id
        assert error.timeout_seconds == timeout_seconds
        assert error.completed_actions == completed_actions
        assert error.total_actions == total_actions
        assert "timed out after 300 seconds" in str(error)
        assert "Completed 5/10 actions" in str(error)


class TestIdempotencyViolationError:
    """Test the IdempotencyViolationError class."""

    def test_idempotency_violation_error(self):
        """Test idempotency violation error."""
        operation_id = "duplicate-op-123"
        duplicate_rollback_id = "existing-rollback-456"

        error = IdempotencyViolationError(operation_id, duplicate_rollback_id)

        assert error.operation_id == operation_id
        assert error.duplicate_rollback_id == duplicate_rollback_id
        assert "already been rolled back" in str(error)
        assert duplicate_rollback_id in str(error)

    def test_idempotency_violation_error_custom_message(self):
        """Test idempotency violation error with custom message."""
        operation_id = "duplicate-op-123"
        duplicate_rollback_id = "existing-rollback-456"
        custom_message = "Custom idempotency violation message"

        error = IdempotencyViolationError(operation_id, duplicate_rollback_id, custom_message)

        assert str(error) == custom_message


class TestExceptionInheritance:
    """Test exception inheritance hierarchy."""

    def test_all_exceptions_inherit_from_rollback_error(self):
        """Test that all rollback exceptions inherit from RollbackError."""
        exception_classes = [
            OperationNotFoundError,
            OperationAlreadyRolledBackError,
            RollbackValidationError,
            RollbackExecutionError,
            RollbackPartialFailureError,
            StateVerificationError,
            RollbackStorageError,
            RollbackConfigurationError,
            AWSClientNotAvailableError,
            RollbackTimeoutError,
            IdempotencyViolationError,
        ]

        for exception_class in exception_classes:
            assert issubclass(exception_class, RollbackError)
            assert issubclass(exception_class, Exception)

    def test_rollback_error_inherits_from_exception(self):
        """Test that RollbackError inherits from Exception."""
        assert issubclass(RollbackError, Exception)


class TestExceptionUsagePatterns:
    """Test common exception usage patterns."""

    def test_exception_chaining(self):
        """Test exception chaining with rollback errors."""
        original_error = ValueError("Original error")

        try:
            raise original_error
        except ValueError as e:
            rollback_error = RollbackStorageError("Storage failed", original_exception=e)

            assert rollback_error.original_exception == original_error
            assert "Original error" in rollback_error.context["original_exception"]

    def test_exception_context_preservation(self):
        """Test that exception context is preserved."""
        context = {
            "account_id": "123456789012",
            "permission_set": "ReadOnlyAccess",
            "principal_id": "user-123",
        }

        error = RollbackError("Test error", context=context)

        # Context should be preserved
        assert error.context == context

        # Context should be mutable
        error.context["additional_info"] = "Added later"
        assert error.context["additional_info"] == "Added later"

    def test_exception_serialization_compatibility(self):
        """Test that exceptions can be serialized for logging."""
        error = RollbackExecutionError(
            operation_id="test-op-123",
            rollback_operation_id="rollback-456",
            failed_actions=2,
            total_actions=5,
            errors=["Error 1", "Error 2"],
        )

        # Should be able to convert to string
        error_str = str(error)
        assert "test-op-123" in error_str

        # Should be able to access all attributes
        assert error.operation_id == "test-op-123"
        assert error.rollback_operation_id == "rollback-456"
        assert error.failed_actions == 2
        assert error.total_actions == 5
        assert len(error.errors) == 2
