"""Tests for rollback error recovery system."""

import asyncio
from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError

from src.awsideman.rollback.error_recovery import (
    ErrorRecoveryResult,
    ErrorType,
    RecoveryAction,
    RecoveryStrategy,
    RetryConfig,
    RollbackErrorRecovery,
    get_error_recovery,
    with_rollback_retry,
)
from src.awsideman.rollback.exceptions import (
    AWSClientNotAvailableError,
    RollbackExecutionError,
    RollbackPartialFailureError,
    RollbackTimeoutError,
)


class TestRetryConfig:
    """Test the RetryConfig class."""

    def test_default_retry_config(self):
        """Test default retry configuration."""
        config = RetryConfig()

        assert config.max_attempts == 3
        assert config.initial_delay == 1.0
        assert config.max_delay == 60.0
        assert config.backoff_multiplier == 2.0
        assert config.jitter is True
        assert "ThrottlingException" in config.retryable_error_codes

    def test_custom_retry_config(self):
        """Test custom retry configuration."""
        config = RetryConfig(
            max_attempts=5,
            initial_delay=2.0,
            max_delay=120.0,
            backoff_multiplier=1.5,
            jitter=False,
            retryable_error_codes=["CustomError"],
        )

        assert config.max_attempts == 5
        assert config.initial_delay == 2.0
        assert config.max_delay == 120.0
        assert config.backoff_multiplier == 1.5
        assert config.jitter is False
        assert config.retryable_error_codes == ["CustomError"]


class TestRecoveryAction:
    """Test the RecoveryAction class."""

    def test_basic_recovery_action(self):
        """Test basic recovery action creation."""
        action = RecoveryAction(
            strategy=RecoveryStrategy.RETRY,
            description="Retry the operation",
        )

        assert action.strategy == RecoveryStrategy.RETRY
        assert action.description == "Retry the operation"
        assert action.retry_config is None
        assert action.skip_reason is None
        assert action.manual_steps is None

    def test_recovery_action_with_all_fields(self):
        """Test recovery action with all fields."""
        retry_config = RetryConfig(max_attempts=2)
        manual_steps = ["Step 1", "Step 2"]

        action = RecoveryAction(
            strategy=RecoveryStrategy.MANUAL_INTERVENTION,
            description="Manual intervention required",
            retry_config=retry_config,
            skip_reason="Resource not found",
            manual_steps=manual_steps,
        )

        assert action.strategy == RecoveryStrategy.MANUAL_INTERVENTION
        assert action.retry_config == retry_config
        assert action.skip_reason == "Resource not found"
        assert action.manual_steps == manual_steps


class TestRollbackErrorRecovery:
    """Test the RollbackErrorRecovery class."""

    def test_initialization(self):
        """Test error recovery initialization."""
        recovery = RollbackErrorRecovery()

        assert recovery.retry_config is not None
        assert len(recovery._error_strategies) > 0

    def test_initialization_with_custom_config(self):
        """Test error recovery initialization with custom config."""
        custom_config = RetryConfig(max_attempts=5)
        recovery = RollbackErrorRecovery(custom_config)

        assert recovery.retry_config == custom_config

    def test_classify_client_error_permission(self):
        """Test classification of permission errors."""
        recovery = RollbackErrorRecovery()

        error = ClientError(
            error_response={"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
            operation_name="TestOperation",
        )

        error_type = recovery.classify_error(error)
        assert error_type == ErrorType.PERMISSION_ERROR

    def test_classify_client_error_resource_not_found(self):
        """Test classification of resource not found errors."""
        recovery = RollbackErrorRecovery()

        error = ClientError(
            error_response={"Error": {"Code": "ResourceNotFoundException", "Message": "Not found"}},
            operation_name="TestOperation",
        )

        error_type = recovery.classify_error(error)
        assert error_type == ErrorType.RESOURCE_NOT_FOUND

    def test_classify_client_error_conflict(self):
        """Test classification of conflict errors."""
        recovery = RollbackErrorRecovery()

        error = ClientError(
            error_response={"Error": {"Code": "ConflictException", "Message": "Conflict"}},
            operation_name="TestOperation",
        )

        error_type = recovery.classify_error(error)
        assert error_type == ErrorType.CONFLICT_ERROR

    def test_classify_client_error_transient(self):
        """Test classification of transient errors."""
        recovery = RollbackErrorRecovery()

        error = ClientError(
            error_response={"Error": {"Code": "ThrottlingException", "Message": "Throttled"}},
            operation_name="TestOperation",
        )

        error_type = recovery.classify_error(error)
        assert error_type == ErrorType.TRANSIENT_AWS_ERROR

    def test_classify_network_error(self):
        """Test classification of network errors."""
        recovery = RollbackErrorRecovery()

        error = ConnectionError("Connection failed")
        error_type = recovery.classify_error(error)
        assert error_type == ErrorType.NETWORK_ERROR

    def test_classify_timeout_error(self):
        """Test classification of timeout errors."""
        recovery = RollbackErrorRecovery()

        error = asyncio.TimeoutError()
        error_type = recovery.classify_error(error)
        assert error_type == ErrorType.NETWORK_ERROR

    def test_classify_rollback_timeout_error(self):
        """Test classification of rollback timeout errors."""
        recovery = RollbackErrorRecovery()

        error = RollbackTimeoutError("op-123", 300, 5, 10)
        error_type = recovery.classify_error(error)
        assert error_type == ErrorType.TIMEOUT_ERROR

    def test_classify_aws_client_not_available_error(self):
        """Test classification of AWS client not available errors."""
        recovery = RollbackErrorRecovery()

        error = AWSClientNotAvailableError("test operation")
        error_type = recovery.classify_error(error)
        assert error_type == ErrorType.CONFIGURATION_ERROR

    def test_classify_unknown_error(self):
        """Test classification of unknown errors."""
        recovery = RollbackErrorRecovery()

        error = RuntimeError("Unknown error")
        error_type = recovery.classify_error(error)
        assert error_type == ErrorType.UNKNOWN_ERROR

    def test_get_recovery_action(self):
        """Test getting recovery action for an error."""
        recovery = RollbackErrorRecovery()

        error = ClientError(
            error_response={"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
            operation_name="TestOperation",
        )

        action = recovery.get_recovery_action(error)
        assert action.strategy == RecoveryStrategy.FAIL_FAST

    def test_execute_with_recovery_success_first_attempt(self):
        """Test successful operation on first attempt."""
        recovery = RollbackErrorRecovery()

        operation = Mock(return_value="success")

        result = recovery.execute_with_recovery(operation, "test_operation")

        assert result.success is True
        assert result.attempts_made == 1
        assert result.strategy_used == RecoveryStrategy.CONTINUE
        assert result.final_error is None
        operation.assert_called_once()

    def test_execute_with_recovery_success_after_retry(self):
        """Test successful operation after retry."""
        recovery = RollbackErrorRecovery()

        # Mock operation that fails once then succeeds
        operation = Mock(
            side_effect=[
                ClientError(
                    error_response={
                        "Error": {"Code": "ThrottlingException", "Message": "Throttled"}
                    },
                    operation_name="TestOperation",
                ),
                "success",
            ]
        )

        with patch("time.sleep"):  # Mock sleep to speed up test
            result = recovery.execute_with_recovery(operation, "test_operation")

        assert result.success is True
        assert result.attempts_made == 2
        assert result.strategy_used == RecoveryStrategy.RETRY
        assert result.final_error is None
        assert operation.call_count == 2

    def test_execute_with_recovery_fail_fast(self):
        """Test fail fast strategy."""
        recovery = RollbackErrorRecovery()

        operation = Mock(
            side_effect=ClientError(
                error_response={"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
                operation_name="TestOperation",
            )
        )

        result = recovery.execute_with_recovery(operation, "test_operation")

        assert result.success is False
        assert result.attempts_made == 1
        assert result.strategy_used == RecoveryStrategy.FAIL_FAST
        assert result.final_error is not None
        operation.assert_called_once()

    def test_execute_with_recovery_skip_strategy(self):
        """Test skip strategy."""
        recovery = RollbackErrorRecovery()

        operation = Mock(
            side_effect=ClientError(
                error_response={
                    "Error": {"Code": "ResourceNotFoundException", "Message": "Not found"}
                },
                operation_name="TestOperation",
            )
        )

        result = recovery.execute_with_recovery(operation, "test_operation")

        assert result.success is True  # Skip is considered success
        assert result.attempts_made == 1
        assert result.strategy_used == RecoveryStrategy.SKIP
        operation.assert_called_once()

    def test_execute_with_recovery_continue_strategy(self):
        """Test continue strategy."""
        recovery = RollbackErrorRecovery()

        operation = Mock(
            side_effect=ClientError(
                error_response={"Error": {"Code": "ConflictException", "Message": "Conflict"}},
                operation_name="TestOperation",
            )
        )

        result = recovery.execute_with_recovery(operation, "test_operation")

        assert result.success is True  # Continue is considered success
        assert result.attempts_made == 1
        assert result.strategy_used == RecoveryStrategy.CONTINUE
        assert result.final_error is not None  # But error is preserved
        operation.assert_called_once()

    def test_execute_with_recovery_max_retries_exceeded(self):
        """Test max retries exceeded."""
        recovery = RollbackErrorRecovery(RetryConfig(max_attempts=2))

        operation = Mock(
            side_effect=ClientError(
                error_response={"Error": {"Code": "ThrottlingException", "Message": "Throttled"}},
                operation_name="TestOperation",
            )
        )

        with patch("time.sleep"):  # Mock sleep to speed up test
            result = recovery.execute_with_recovery(operation, "test_operation")

        assert result.success is False
        assert result.attempts_made == 2
        assert result.strategy_used == RecoveryStrategy.RETRY
        assert result.final_error is not None
        assert operation.call_count == 2

    def test_calculate_retry_delay(self):
        """Test retry delay calculation."""
        recovery = RollbackErrorRecovery()

        # Test exponential backoff
        delay1 = recovery._calculate_retry_delay(1)
        delay2 = recovery._calculate_retry_delay(2)
        delay3 = recovery._calculate_retry_delay(3)

        # Should increase with backoff multiplier (accounting for jitter)
        assert delay1 >= 0.8  # 1.0 * 0.8 (min jitter)
        assert delay1 <= 1.2  # 1.0 * 1.2 (max jitter)

        assert delay2 >= 1.6  # 2.0 * 0.8 (min jitter)
        assert delay2 <= 2.4  # 2.0 * 1.2 (max jitter)

        assert delay3 >= 3.2  # 4.0 * 0.8 (min jitter)
        assert delay3 <= 4.8  # 4.0 * 1.2 (max jitter)

        # Test without jitter
        config = RetryConfig(jitter=False)
        delay_no_jitter = recovery._calculate_retry_delay(2, config)
        assert delay_no_jitter == 2.0  # 1.0 * 2.0^(2-1)

        delay_no_jitter_3 = recovery._calculate_retry_delay(3, config)
        assert delay_no_jitter_3 == 4.0  # 1.0 * 2.0^(3-1)

    def test_calculate_retry_delay_max_limit(self):
        """Test retry delay maximum limit."""
        config = RetryConfig(
            initial_delay=10.0, max_delay=15.0, backoff_multiplier=3.0, jitter=False
        )
        recovery = RollbackErrorRecovery(config)

        # Should be capped at max_delay
        delay = recovery._calculate_retry_delay(5, config)
        assert delay == 15.0

    def test_handle_partial_failure_high_success_rate(self):
        """Test handling partial failure with high success rate."""
        recovery = RollbackErrorRecovery()

        result = recovery.handle_partial_failure(
            operation_id="op-123",
            rollback_operation_id="rollback-456",
            completed_actions=8,
            failed_actions=2,
            total_actions=10,
            errors=["Error 1", "Error 2"],
        )

        assert result.success is True
        assert result.strategy_used == RecoveryStrategy.CONTINUE
        assert "High success rate" in " ".join(result.recovery_notes)

    def test_handle_partial_failure_moderate_success_rate(self):
        """Test handling partial failure with moderate success rate."""
        recovery = RollbackErrorRecovery()

        result = recovery.handle_partial_failure(
            operation_id="op-123",
            rollback_operation_id="rollback-456",
            completed_actions=6,
            failed_actions=4,
            total_actions=10,
            errors=["Error 1", "Error 2", "Error 3", "Error 4"],
        )

        assert result.success is False
        assert result.strategy_used == RecoveryStrategy.MANUAL_INTERVENTION
        assert isinstance(result.final_error, RollbackPartialFailureError)
        assert "Manual intervention recommended" in " ".join(result.recovery_notes)

    def test_handle_partial_failure_low_success_rate(self):
        """Test handling partial failure with low success rate."""
        recovery = RollbackErrorRecovery()

        result = recovery.handle_partial_failure(
            operation_id="op-123",
            rollback_operation_id="rollback-456",
            completed_actions=2,
            failed_actions=8,
            total_actions=10,
            errors=["Error " + str(i) for i in range(8)],
        )

        assert result.success is False
        assert result.strategy_used == RecoveryStrategy.FAIL_FAST
        assert isinstance(result.final_error, RollbackExecutionError)
        assert "mostly failed" in " ".join(result.recovery_notes)

    def test_handle_partial_failure_zero_total_actions(self):
        """Test handling partial failure with zero total actions."""
        recovery = RollbackErrorRecovery()

        result = recovery.handle_partial_failure(
            operation_id="op-123",
            rollback_operation_id="rollback-456",
            completed_actions=0,
            failed_actions=0,
            total_actions=0,
            errors=[],
        )

        # Should handle division by zero gracefully
        assert result.success is False

    def test_register_custom_strategy(self):
        """Test registering custom recovery strategy."""
        recovery = RollbackErrorRecovery()

        custom_action = RecoveryAction(
            strategy=RecoveryStrategy.MANUAL_INTERVENTION,
            description="Custom strategy",
        )

        recovery.register_custom_strategy(ErrorType.UNKNOWN_ERROR, custom_action)

        # Test that custom strategy is used
        error = RuntimeError("Unknown error")
        action = recovery.get_recovery_action(error)
        assert action.strategy == RecoveryStrategy.MANUAL_INTERVENTION
        assert action.description == "Custom strategy"

    def test_get_recovery_summary_empty(self):
        """Test recovery summary with empty results."""
        recovery = RollbackErrorRecovery()

        summary = recovery.get_recovery_summary([])

        assert summary["total_operations"] == 0

    def test_get_recovery_summary_with_results(self):
        """Test recovery summary with results."""
        recovery = RollbackErrorRecovery()

        results = [
            ErrorRecoveryResult(
                success=True,
                strategy_used=RecoveryStrategy.RETRY,
                attempts_made=2,
                recovery_notes=["Note 1", "Note 2"],
            ),
            ErrorRecoveryResult(
                success=False,
                strategy_used=RecoveryStrategy.FAIL_FAST,
                attempts_made=1,
                recovery_notes=["Note 3"],
            ),
            ErrorRecoveryResult(
                success=True,
                strategy_used=RecoveryStrategy.SKIP,
                attempts_made=1,
                recovery_notes=[],
            ),
        ]

        summary = recovery.get_recovery_summary(results)

        assert summary["total_operations"] == 3
        assert summary["successful_operations"] == 2
        assert summary["failed_operations"] == 1
        assert summary["success_rate"] == 2 / 3
        assert summary["average_attempts"] == 4 / 3  # (2+1+1)/3
        assert summary["strategies_used"]["retry"] == 1
        assert summary["strategies_used"]["fail_fast"] == 1
        assert summary["strategies_used"]["skip"] == 1
        assert summary["total_recovery_notes"] == 3


class TestGlobalErrorRecovery:
    """Test global error recovery functions."""

    def test_get_error_recovery_singleton(self):
        """Test that get_error_recovery returns singleton."""
        recovery1 = get_error_recovery()
        recovery2 = get_error_recovery()

        assert recovery1 is recovery2
        assert isinstance(recovery1, RollbackErrorRecovery)


class TestWithRollbackRetryDecorator:
    """Test the with_rollback_retry decorator."""

    def test_decorator_success_first_attempt(self):
        """Test decorator with successful first attempt."""

        @with_rollback_retry(max_attempts=3)
        def test_function():
            return "success"

        result = test_function()
        assert result.success is True
        assert result.attempts_made == 1

    def test_decorator_success_after_retry(self):
        """Test decorator with success after retry."""
        call_count = 0

        @with_rollback_retry(max_attempts=3, initial_delay=0.01)
        def test_function():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ClientError(
                    error_response={
                        "Error": {"Code": "ThrottlingException", "Message": "Throttled"}
                    },
                    operation_name="TestOperation",
                )
            return "success"

        result = test_function()
        assert result.success is True
        assert result.attempts_made == 2
        assert call_count == 2

    def test_decorator_failure_raises_exception(self):
        """Test decorator raises exception on failure."""

        @with_rollback_retry(max_attempts=2, initial_delay=0.01)
        def test_function():
            raise ClientError(
                error_response={"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
                operation_name="TestOperation",
            )

        with pytest.raises(ClientError):
            test_function()

    def test_decorator_custom_config(self):
        """Test decorator with custom configuration."""
        call_count = 0

        @with_rollback_retry(
            max_attempts=5,
            initial_delay=0.01,
            max_delay=0.1,
            backoff_multiplier=1.5,
        )
        def test_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ClientError(
                    error_response={
                        "Error": {"Code": "ThrottlingException", "Message": "Throttled"}
                    },
                    operation_name="TestOperation",
                )
            return "success"

        result = test_function()
        assert result.success is True
        assert result.attempts_made == 3
        assert call_count == 3


class TestErrorRecoveryIntegration:
    """Test error recovery integration scenarios."""

    def test_complex_error_scenario(self):
        """Test complex error scenario with multiple error types."""
        recovery = RollbackErrorRecovery(RetryConfig(max_attempts=4))

        call_count = 0
        errors = [
            ClientError(
                error_response={"Error": {"Code": "ThrottlingException", "Message": "Throttled"}},
                operation_name="TestOperation",
            ),
            ConnectionError("Network error"),
            ClientError(
                error_response={
                    "Error": {
                        "Code": "ServiceUnavailableException",
                        "Message": "Service unavailable",
                    }
                },
                operation_name="TestOperation",
            ),
            "success",
        ]

        def operation():
            nonlocal call_count
            result = errors[call_count]
            call_count += 1
            if isinstance(result, Exception):
                raise result
            return result

        with patch("time.sleep"):  # Mock sleep to speed up test
            result = recovery.execute_with_recovery(operation, "complex_operation")

        assert result.success is True
        assert result.attempts_made == 4
        assert call_count == 4

    def test_mixed_strategies_in_batch(self):
        """Test mixed recovery strategies in a batch operation."""
        recovery = RollbackErrorRecovery()

        # Simulate different errors that would use different strategies
        errors = [
            ClientError(
                error_response={
                    "Error": {"Code": "ResourceNotFoundException", "Message": "Not found"}
                },
                operation_name="TestOperation",
            ),  # Should skip
            ClientError(
                error_response={"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
                operation_name="TestOperation",
            ),  # Should fail fast
            ClientError(
                error_response={"Error": {"Code": "ConflictException", "Message": "Conflict"}},
                operation_name="TestOperation",
            ),  # Should continue
        ]

        results = []
        for i, error in enumerate(errors):

            def operation():
                raise error

            result = recovery.execute_with_recovery(operation, f"operation_{i}")
            results.append(result)

        # Check that different strategies were used
        strategies = [r.strategy_used for r in results]
        assert RecoveryStrategy.SKIP in strategies
        assert RecoveryStrategy.FAIL_FAST in strategies
        assert RecoveryStrategy.CONTINUE in strategies

        # Check success/failure patterns
        assert results[0].success is True  # Skip
        assert results[1].success is False  # Fail fast
        assert results[2].success is True  # Continue
