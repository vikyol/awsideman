"""
Unit tests for comprehensive error handling and recovery system.

Tests retry logic, partial recovery, rollback capabilities, and error reporting.
"""

from datetime import datetime

import pytest
from botocore.exceptions import BotoCoreError, ClientError

from src.awsideman.backup_restore.error_handling import (
    ErrorAnalyzer,
    ErrorCategory,
    ErrorInfo,
    ErrorReporter,
    ErrorSeverity,
    OperationState,
    PartialRecoveryManager,
    RetryConfig,
    RetryHandler,
    RollbackManager,
    create_error_handling_system,
)


class TestErrorAnalyzer:
    """Test error analysis and categorization."""

    def setup_method(self):
        """Set up test fixtures."""
        self.analyzer = ErrorAnalyzer()

    def test_analyze_client_error_throttling(self):
        """Test analysis of AWS throttling errors."""
        # Create a throttling error
        error_response = {"Error": {"Code": "Throttling", "Message": "Rate exceeded"}}
        exception = ClientError(error_response, "ListUsers")

        error_info = self.analyzer.analyze_error(exception)

        assert error_info.category == ErrorCategory.RATE_LIMITING
        assert error_info.severity == ErrorSeverity.MEDIUM
        assert error_info.recoverable is True
        assert error_info.max_retries == 5
        assert "Retry with exponential backoff" in error_info.suggested_actions

    def test_analyze_client_error_access_denied(self):
        """Test analysis of AWS access denied errors."""
        error_response = {"Error": {"Code": "AccessDenied", "Message": "User is not authorized"}}
        exception = ClientError(error_response, "CreateUser")

        error_info = self.analyzer.analyze_error(exception)

        assert error_info.category == ErrorCategory.AUTHORIZATION
        assert error_info.severity == ErrorSeverity.HIGH
        assert error_info.recoverable is False
        assert "Check IAM permissions" in error_info.suggested_actions

    def test_analyze_client_error_resource_not_found(self):
        """Test analysis of resource not found errors."""
        error_response = {"Error": {"Code": "UserNotFound", "Message": "User does not exist"}}
        exception = ClientError(error_response, "GetUser")

        error_info = self.analyzer.analyze_error(exception)

        assert error_info.category == ErrorCategory.RESOURCE_NOT_FOUND
        assert error_info.severity == ErrorSeverity.MEDIUM
        assert error_info.recoverable is False
        assert "Verify resource exists" in error_info.suggested_actions

    def test_analyze_client_error_conflict(self):
        """Test analysis of resource conflict errors."""
        error_response = {
            "Error": {"Code": "ConflictException", "Message": "Resource already exists"}
        }
        exception = ClientError(error_response, "CreateGroup")

        error_info = self.analyzer.analyze_error(exception)

        assert error_info.category == ErrorCategory.RESOURCE_CONFLICT
        assert error_info.severity == ErrorSeverity.LOW
        assert error_info.recoverable is True
        assert "Use conflict resolution strategy" in error_info.suggested_actions

    def test_analyze_botocore_error_timeout(self):
        """Test analysis of BotoCore timeout errors."""
        exception = BotoCoreError()
        exception.args = ("Connection timeout",)

        error_info = self.analyzer.analyze_error(exception)

        assert error_info.category == ErrorCategory.NETWORK
        assert error_info.severity == ErrorSeverity.MEDIUM
        assert error_info.recoverable is True

    def test_analyze_generic_error_connection(self):
        """Test analysis of generic connection errors."""
        exception = ConnectionError("Connection failed")

        error_info = self.analyzer.analyze_error(exception)

        assert error_info.category == ErrorCategory.NETWORK
        assert error_info.severity == ErrorSeverity.MEDIUM
        assert error_info.recoverable is True
        assert "Check network connectivity" in error_info.suggested_actions

    def test_analyze_generic_error_validation(self):
        """Test analysis of validation errors."""
        exception = ValueError("Invalid parameter value")

        error_info = self.analyzer.analyze_error(exception)

        assert error_info.category == ErrorCategory.VALIDATION
        assert error_info.severity == ErrorSeverity.HIGH
        assert error_info.recoverable is False

    def test_error_info_serialization(self):
        """Test ErrorInfo serialization to dictionary."""
        exception = ValueError("Test error")
        error_info = self.analyzer.analyze_error(exception)

        error_dict = error_info.to_dict()

        assert "error_id" in error_dict
        assert "timestamp" in error_dict
        assert error_dict["category"] == error_info.category.value
        assert error_dict["severity"] == error_info.severity.value
        assert error_dict["message"] == str(exception)
        assert error_dict["exception_type"] == "ValueError"


class TestRetryHandler:
    """Test retry logic with exponential backoff."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = RetryConfig(max_retries=3, base_delay=0.1, max_delay=1.0)
        self.handler = RetryHandler(self.config)

    @pytest.mark.asyncio
    async def test_successful_operation_no_retry(self):
        """Test successful operation that doesn't need retry."""

        async def successful_operation():
            return "success"

        result = await self.handler.execute_with_retry(successful_operation)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_operation_succeeds_after_retries(self):
        """Test operation that succeeds after some retries."""
        call_count = 0

        async def flaky_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Temporary failure")
            return "success"

        result = await self.handler.execute_with_retry(flaky_operation)
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_operation_fails_after_max_retries(self):
        """Test operation that fails after exhausting all retries."""

        async def failing_operation():
            raise ConnectionError("Persistent failure")

        with pytest.raises(ConnectionError, match="Persistent failure"):
            await self.handler.execute_with_retry(failing_operation)

    @pytest.mark.asyncio
    async def test_non_retryable_error_no_retry(self):
        """Test that non-retryable errors are not retried."""
        call_count = 0

        async def operation_with_auth_error():
            nonlocal call_count
            call_count += 1
            error_response = {"Error": {"Code": "AccessDenied", "Message": "Not authorized"}}
            raise ClientError(error_response, "TestOperation")

        with pytest.raises(ClientError):
            await self.handler.execute_with_retry(operation_with_auth_error)

        assert call_count == 1  # Should not retry

    @pytest.mark.asyncio
    async def test_retryable_aws_error_with_retry(self):
        """Test that retryable AWS errors are retried."""
        call_count = 0

        async def operation_with_throttling():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                error_response = {"Error": {"Code": "Throttling", "Message": "Rate exceeded"}}
                raise ClientError(error_response, "TestOperation")
            return "success"

        result = await self.handler.execute_with_retry(operation_with_throttling)
        assert result == "success"
        assert call_count == 3

    def test_calculate_delay_exponential_backoff(self):
        """Test exponential backoff delay calculation."""
        # Test delay calculation for different attempts
        delay1 = self.handler._calculate_delay(1)
        delay2 = self.handler._calculate_delay(2)
        delay3 = self.handler._calculate_delay(3)

        # Should increase exponentially (with jitter, so approximate)
        assert 0.05 <= delay1 <= 0.15  # ~0.1 with jitter
        assert 0.1 <= delay2 <= 0.3  # ~0.2 with jitter
        assert 0.2 <= delay3 <= 0.6  # ~0.4 with jitter

    def test_calculate_delay_max_delay_cap(self):
        """Test that delay is capped at max_delay."""
        # Test with a high attempt number
        delay = self.handler._calculate_delay(10)
        assert delay <= self.config.max_delay


class TestPartialRecoveryManager:
    """Test partial recovery for failed operations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.recovery_manager = PartialRecoveryManager()

    @pytest.mark.asyncio
    async def test_recover_backup_operation_with_data(self):
        """Test recovery of backup operation with some collected data."""
        # Create operation state with checkpoints
        operation_state = OperationState(
            operation_id="test-backup-123", operation_type="backup", start_time=datetime.now()
        )

        # Add checkpoints with collected data
        operation_state.add_checkpoint(
            "collected_users",
            [
                {"user_id": "user1", "user_name": "test1"},
                {"user_id": "user2", "user_name": "test2"},
            ],
        )
        operation_state.add_checkpoint(
            "collected_groups", [{"group_id": "group1", "display_name": "Test Group"}]
        )

        error_info = ErrorInfo(message="Network timeout during permission set collection")

        result = await self.recovery_manager.attempt_partial_recovery(
            "backup", operation_state, error_info
        )

        assert result["success"] is True
        assert "Recovered 2 users" in result["message"]
        assert "Recovered 1 groups" in result["message"]
        assert result["recovery_type"] == "partial_backup"
        assert "permission_sets" in result["missing_resources"]
        assert "assignments" in result["missing_resources"]

    @pytest.mark.asyncio
    async def test_recover_backup_operation_no_data(self):
        """Test recovery of backup operation with no recoverable data."""
        operation_state = OperationState(
            operation_id="test-backup-456", operation_type="backup", start_time=datetime.now()
        )

        error_info = ErrorInfo(message="Connection failed at start")

        result = await self.recovery_manager.attempt_partial_recovery(
            "backup", operation_state, error_info
        )

        assert result["success"] is False
        assert "No recoverable data found" in result["message"]

    @pytest.mark.asyncio
    async def test_recover_restore_operation(self):
        """Test recovery of restore operation with applied changes."""
        operation_state = OperationState(
            operation_id="test-restore-789", operation_type="restore", start_time=datetime.now()
        )

        # Add applied changes
        operation_state.add_change("user", "user1", "create")
        operation_state.add_change("user", "user2", "update")
        operation_state.add_change("group", "group1", "create")

        error_info = ErrorInfo(message="Permission set creation failed")

        result = await self.recovery_manager.attempt_partial_recovery(
            "restore", operation_state, error_info
        )

        assert result["success"] is True
        assert "Successfully applied 2 user" in result["message"]
        assert "Successfully applied 1 group" in result["message"]
        assert result["recovery_type"] == "partial_restore"
        assert result["recovered_data"]["resource_counts"]["user"] == 2
        assert result["recovered_data"]["resource_counts"]["group"] == 1

    @pytest.mark.asyncio
    async def test_recover_unknown_operation_type(self):
        """Test recovery attempt for unknown operation type."""
        operation_state = OperationState(
            operation_id="test-unknown-999", operation_type="unknown", start_time=datetime.now()
        )

        error_info = ErrorInfo(message="Some error")

        result = await self.recovery_manager.attempt_partial_recovery(
            "unknown", operation_state, error_info
        )

        assert result["success"] is False
        assert "No recovery strategy available" in result["message"]


class TestRollbackManager:
    """Test rollback capabilities for failed operations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.rollback_manager = RollbackManager()

    @pytest.mark.asyncio
    async def test_create_rollback_action_create(self):
        """Test creating rollback action for create operation."""
        rollback_action = await self.rollback_manager.create_rollback_action(
            "user", "test-user", "create", {}
        )

        # Execute the rollback action
        result = await rollback_action()

        assert result["action"] == "delete"
        assert result["resource_type"] == "user"
        assert result["resource_id"] == "test-user"
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_create_rollback_action_update(self):
        """Test creating rollback action for update operation."""
        rollback_data = {
            "previous_values": {"display_name": "Old Name", "email": "old@example.com"}
        }

        rollback_action = await self.rollback_manager.create_rollback_action(
            "user", "test-user", "update", rollback_data
        )

        # Execute the rollback action
        result = await rollback_action()

        assert result["action"] == "restore"
        assert result["resource_type"] == "user"
        assert result["resource_id"] == "test-user"
        assert result["restored_values"] == rollback_data["previous_values"]
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_create_rollback_action_delete(self):
        """Test creating rollback action for delete operation."""
        rollback_data = {"resource_data": {"user_name": "test-user", "email": "test@example.com"}}

        rollback_action = await self.rollback_manager.create_rollback_action(
            "user", "test-user", "delete", rollback_data
        )

        # Execute the rollback action
        result = await rollback_action()

        assert result["action"] == "recreate"
        assert result["resource_type"] == "user"
        assert result["resource_id"] == "test-user"
        assert result["recreated_data"] == rollback_data["resource_data"]
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_execute_rollback_success(self):
        """Test successful rollback execution."""
        operation_state = OperationState(
            operation_id="test-rollback-123", operation_type="restore", start_time=datetime.now()
        )

        # Add some rollback actions
        async def rollback_action_1():
            return {"action": "delete", "resource": "user1"}

        async def rollback_action_2():
            return {"action": "restore", "resource": "user2"}

        operation_state.add_rollback_action(rollback_action_1)
        operation_state.add_rollback_action(rollback_action_2)

        # Add some applied changes
        operation_state.add_change("user", "user1", "create")
        operation_state.add_change("user", "user2", "update")

        result = await self.rollback_manager.execute_rollback(operation_state)

        assert result["success"] is True
        assert result["applied_changes_reverted"] == 2
        assert result["total_changes"] == 2
        assert len(result["rollback_results"]) == 2
        assert all(r["success"] for r in result["rollback_results"])

    @pytest.mark.asyncio
    async def test_execute_rollback_partial_failure(self):
        """Test rollback execution with some failures."""
        operation_state = OperationState(
            operation_id="test-rollback-456", operation_type="restore", start_time=datetime.now()
        )

        # Add rollback actions, one that fails
        async def successful_rollback():
            return {"action": "delete", "resource": "user1"}

        async def failing_rollback():
            raise Exception("Rollback failed")

        operation_state.add_rollback_action(successful_rollback)
        operation_state.add_rollback_action(failing_rollback)

        result = await self.rollback_manager.execute_rollback(operation_state)

        assert result["success"] is False
        assert result["applied_changes_reverted"] == 1  # Only one succeeded
        assert len(result["rollback_results"]) == 2
        assert result["rollback_results"][0]["success"] is True
        assert result["rollback_results"][1]["success"] is False


class TestErrorReporter:
    """Test error reporting and remediation suggestions."""

    def setup_method(self):
        """Set up test fixtures."""
        self.reporter = ErrorReporter()

    def test_generate_error_report_single_error(self):
        """Test generating error report for single error."""
        error_info = ErrorInfo(
            category=ErrorCategory.RATE_LIMITING,
            severity=ErrorSeverity.MEDIUM,
            message="Rate limit exceeded",
            suggested_actions=["Retry with backoff", "Reduce request rate"],
            remediation_steps=["Wait for rate limit reset", "Implement exponential backoff"],
        )

        report = self.reporter.generate_error_report([error_info])

        assert "report_id" in report
        assert "timestamp" in report
        assert report["summary"]["total_errors"] == 1
        assert report["summary"]["categories"] == ["rate_limiting"]
        assert "rate_limiting" in report["errors_by_category"]
        assert len(report["errors_by_category"]["rate_limiting"]) == 1
        assert "Retry with backoff" in report["remediation"]["immediate_actions"]
        assert "Wait for rate limit reset" in report["remediation"]["detailed_steps"]

    def test_generate_error_report_multiple_errors(self):
        """Test generating error report for multiple errors."""
        errors = [
            ErrorInfo(
                category=ErrorCategory.RATE_LIMITING,
                severity=ErrorSeverity.MEDIUM,
                message="Rate limit exceeded",
            ),
            ErrorInfo(
                category=ErrorCategory.AUTHORIZATION,
                severity=ErrorSeverity.HIGH,
                message="Access denied",
            ),
            ErrorInfo(
                category=ErrorCategory.NETWORK,
                severity=ErrorSeverity.CRITICAL,
                message="Connection failed",
            ),
        ]

        report = self.reporter.generate_error_report(errors)

        assert report["summary"]["total_errors"] == 3
        assert report["summary"]["critical_errors"] == 1
        assert report["summary"]["high_errors"] == 1
        assert len(report["summary"]["categories"]) == 3
        assert "rate_limiting" in report["errors_by_category"]
        assert "authorization" in report["errors_by_category"]
        assert "network" in report["errors_by_category"]

    def test_generate_recovery_options(self):
        """Test generation of recovery options."""
        recoverable_error = ErrorInfo(
            category=ErrorCategory.NETWORK, severity=ErrorSeverity.MEDIUM, recoverable=True
        )

        critical_error = ErrorInfo(
            category=ErrorCategory.VALIDATION, severity=ErrorSeverity.CRITICAL, recoverable=False
        )

        errors = [recoverable_error, critical_error]
        report = self.reporter.generate_error_report(errors)

        recovery_options = report["remediation"]["recovery_options"]
        assert "Retry operation with exponential backoff" in recovery_options
        assert "Manual intervention required for critical errors" in recovery_options

    def test_generate_next_steps(self):
        """Test generation of next steps."""
        errors = [
            ErrorInfo(category=ErrorCategory.AUTHORIZATION, severity=ErrorSeverity.HIGH),
            ErrorInfo(category=ErrorCategory.RATE_LIMITING, severity=ErrorSeverity.MEDIUM),
        ]

        context = {"operation_type": "backup"}
        report = self.reporter.generate_error_report(errors, context)

        next_steps = report["next_steps"]
        assert "Resolve high-severity errors to prevent operation failure" in next_steps
        assert "Review and update IAM permissions" in next_steps
        assert "Implement rate limiting and retry logic" in next_steps
        assert "Consider creating incremental backup to reduce load" in next_steps


class TestErrorHandlingSystemIntegration:
    """Test integration of the complete error handling system."""

    def test_create_error_handling_system(self):
        """Test creation of complete error handling system."""
        system = create_error_handling_system()

        assert "retry_handler" in system
        assert "error_analyzer" in system
        assert "partial_recovery_manager" in system
        assert "rollback_manager" in system
        assert "error_reporter" in system

        assert isinstance(system["retry_handler"], RetryHandler)
        assert isinstance(system["error_analyzer"], ErrorAnalyzer)
        assert isinstance(system["partial_recovery_manager"], PartialRecoveryManager)
        assert isinstance(system["rollback_manager"], RollbackManager)
        assert isinstance(system["error_reporter"], ErrorReporter)

    def test_create_error_handling_system_with_config(self):
        """Test creation with custom retry configuration."""
        custom_config = RetryConfig(max_retries=5, base_delay=0.5)
        system = create_error_handling_system(custom_config)

        assert system["retry_handler"].config.max_retries == 5
        assert system["retry_handler"].config.base_delay == 0.5


class TestOperationState:
    """Test operation state tracking."""

    def test_operation_state_initialization(self):
        """Test operation state initialization."""
        start_time = datetime.now()
        state = OperationState(
            operation_id="test-123", operation_type="backup", start_time=start_time
        )

        assert state.operation_id == "test-123"
        assert state.operation_type == "backup"
        assert state.start_time == start_time
        assert state.checkpoints == []
        assert state.applied_changes == []
        assert state.rollback_actions == []
        assert state.completed is False
        assert state.success is False

    def test_add_checkpoint(self):
        """Test adding checkpoints."""
        state = OperationState("test-123", "backup", datetime.now())

        checkpoint_data = {"users_collected": 10}
        state.add_checkpoint("users_collected", checkpoint_data)

        assert len(state.checkpoints) == 1
        assert state.checkpoints[0]["name"] == "users_collected"
        assert state.checkpoints[0]["data"] == checkpoint_data
        assert "timestamp" in state.checkpoints[0]

    def test_add_change(self):
        """Test adding applied changes."""
        state = OperationState("test-123", "restore", datetime.now())

        state.add_change("user", "user1", "create", None, {"name": "Test User"})

        assert len(state.applied_changes) == 1
        change = state.applied_changes[0]
        assert change["resource_type"] == "user"
        assert change["resource_id"] == "user1"
        assert change["action"] == "create"
        assert change["old_value"] is None
        assert change["new_value"] == {"name": "Test User"}
        assert "timestamp" in change

    def test_add_rollback_action(self):
        """Test adding rollback actions."""
        state = OperationState("test-123", "restore", datetime.now())

        async def test_rollback():
            return "rolled back"

        state.add_rollback_action(test_rollback)

        assert len(state.rollback_actions) == 1
        assert state.rollback_actions[0] == test_rollback


if __name__ == "__main__":
    pytest.main([__file__])
