"""
Unit tests for permission cloning progress reporter.

Tests the progress reporting, audit logging, and performance metrics
functionality for permission cloning operations.
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from src.awsideman.permission_cloning.models import (
    CloneResult,
    CopyResult,
    CustomerManagedPolicy,
    EntityReference,
    EntityType,
    PermissionAssignment,
    PermissionSetConfig,
)
from src.awsideman.permission_cloning.progress_reporter import (
    OperationAuditLog,
    PerformanceMetricsLog,
    ProgressReporter,
    ProgressUpdate,
    get_progress_reporter,
    set_progress_reporter,
)
from src.awsideman.utils.logging_config import StatusLoggingManager


class TestProgressUpdate:
    """Test ProgressUpdate data class."""

    def test_progress_update_creation(self):
        """Test creating a progress update."""
        update = ProgressUpdate(
            operation_id="test-op-123",
            operation_type="copy_assignments",
            current=50,
            total=100,
            message="Processing assignments",
        )

        assert update.operation_id == "test-op-123"
        assert update.operation_type == "copy_assignments"
        assert update.current == 50
        assert update.total == 100
        assert update.message == "Processing assignments"
        assert update.percentage == 50.0
        assert not update.is_complete
        assert isinstance(update.timestamp, datetime)

    def test_progress_update_percentage_calculation(self):
        """Test percentage calculation in progress updates."""
        # Normal case
        update = ProgressUpdate("op1", "test", 25, 100, "test")
        assert update.percentage == 25.0

        # Complete case
        update = ProgressUpdate("op1", "test", 100, 100, "test")
        assert update.percentage == 100.0
        assert update.is_complete

        # Zero total case
        update = ProgressUpdate("op1", "test", 0, 0, "test")
        assert update.percentage == 100.0
        assert update.is_complete

    def test_progress_update_completion_check(self):
        """Test completion check in progress updates."""
        # Not complete
        update = ProgressUpdate("op1", "test", 50, 100, "test")
        assert not update.is_complete

        # Complete
        update = ProgressUpdate("op1", "test", 100, 100, "test")
        assert update.is_complete

        # Over complete
        update = ProgressUpdate("op1", "test", 150, 100, "test")
        assert update.is_complete


class TestOperationAuditLog:
    """Test OperationAuditLog data class."""

    def test_audit_log_creation(self):
        """Test creating an audit log entry."""
        source_entity = EntityReference(
            entity_type=EntityType.USER, entity_id="user-123", entity_name="test.user"
        )

        audit_log = OperationAuditLog(
            operation_id="test-op-123",
            operation_type="copy_assignments",
            user_id="admin-user",
            timestamp=datetime.now(timezone.utc),
            source_entity=source_entity,
            target_entity=None,
            source_permission_set=None,
            target_permission_set=None,
            action="operation_started",
            result="success",
            details={"test": "data"},
            duration_ms=1500.0,
            error_message=None,
        )

        assert audit_log.operation_id == "test-op-123"
        assert audit_log.operation_type == "copy_assignments"
        assert audit_log.user_id == "admin-user"
        assert audit_log.source_entity == source_entity
        assert audit_log.action == "operation_started"
        assert audit_log.result == "success"
        assert audit_log.details == {"test": "data"}
        assert audit_log.duration_ms == 1500.0

    def test_audit_log_to_dict(self):
        """Test converting audit log to dictionary."""
        source_entity = EntityReference(
            entity_type=EntityType.GROUP, entity_id="group-456", entity_name="test-group"
        )

        audit_log = OperationAuditLog(
            operation_id="test-op-456",
            operation_type="clone_permission_set",
            user_id="admin-user",
            timestamp=datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            source_entity=source_entity,
            target_entity=None,
            source_permission_set="source-ps",
            target_permission_set="target-ps",
            action="clone_completed",
            result="success",
            details={"policies": 3},
            duration_ms=2000.0,
            error_message=None,
        )

        result = audit_log.to_dict()

        assert result["operation_id"] == "test-op-456"
        assert result["operation_type"] == "clone_permission_set"
        assert result["user_id"] == "admin-user"
        assert result["timestamp"] == "2023-01-01T12:00:00+00:00"
        assert result["source_entity"]["type"] == "GROUP"
        assert result["source_entity"]["id"] == "group-456"
        assert result["source_entity"]["name"] == "test-group"
        assert result["target_entity"] is None
        assert result["source_permission_set"] == "source-ps"
        assert result["target_permission_set"] == "target-ps"
        assert result["action"] == "clone_completed"
        assert result["result"] == "success"
        assert result["duration_ms"] == 2000.0
        assert result["error_message"] is None
        assert result["details"] == {"policies": 3}


class TestPerformanceMetricsLog:
    """Test PerformanceMetricsLog data class."""

    def test_performance_metrics_creation(self):
        """Test creating a performance metrics log entry."""
        metrics_log = PerformanceMetricsLog(
            operation_id="test-op-789",
            operation_type="copy_assignments",
            timestamp=datetime.now(timezone.utc),
            metric_name="throughput",
            metric_value=15.5,
            metric_unit="assignments/second",
            context={"batch_size": 10},
        )

        assert metrics_log.operation_id == "test-op-789"
        assert metrics_log.operation_type == "copy_assignments"
        assert metrics_log.metric_name == "throughput"
        assert metrics_log.metric_value == 15.5
        assert metrics_log.metric_unit == "assignments/second"
        assert metrics_log.context == {"batch_size": 10}

    def test_performance_metrics_to_dict(self):
        """Test converting performance metrics to dictionary."""
        metrics_log = PerformanceMetricsLog(
            operation_id="test-op-789",
            operation_type="copy_assignments",
            timestamp=datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            metric_name="duration_ms",
            metric_value=1500,
            metric_unit="milliseconds",
            context={"assignments_count": 25},
        )

        result = metrics_log.to_dict()

        assert result["operation_id"] == "test-op-789"
        assert result["operation_type"] == "copy_assignments"
        assert result["timestamp"] == "2023-01-01T12:00:00+00:00"
        assert result["metric_name"] == "duration_ms"
        assert result["metric_value"] == 1500
        assert result["metric_unit"] == "milliseconds"
        assert result["context"] == {"assignments_count": 25}


class TestProgressReporter:
    """Test ProgressReporter class."""

    @pytest.fixture
    def mock_logging_manager(self):
        """Create a mock logging manager."""
        return Mock(spec=StatusLoggingManager)

    @pytest.fixture
    def progress_reporter(self, mock_logging_manager):
        """Create a progress reporter instance."""
        with patch(
            "src.awsideman.permission_cloning.progress_reporter.get_status_logger"
        ) as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger

            reporter = ProgressReporter(logging_manager=mock_logging_manager, user_id="test-user")
            reporter.logger = mock_logger
            reporter.audit_logger = mock_logger
            reporter.performance_logger = mock_logger

            return reporter

    def test_start_operation(self, progress_reporter):
        """Test starting an operation."""
        operation_id = progress_reporter.start_operation(
            operation_type="copy_assignments", source_entity="user:test", target_entity="group:test"
        )

        assert operation_id in progress_reporter._active_operations
        operation = progress_reporter._active_operations[operation_id]
        assert operation["operation_type"] == "copy_assignments"
        assert "source_entity" in operation["context"]
        assert "target_entity" in operation["context"]
        assert operation["progress_updates"] == []
        assert len(operation["audit_logs"]) == 1  # operation_started audit log
        assert operation["performance_metrics"] == []

        # Check logging calls
        progress_reporter.logger.info.assert_called()
        progress_reporter.audit_logger.info.assert_called()

    def test_start_operation_with_custom_id(self, progress_reporter):
        """Test starting an operation with custom ID."""
        custom_id = "custom-op-123"
        operation_id = progress_reporter.start_operation(
            operation_type="clone_permission_set", operation_id=custom_id
        )

        assert operation_id == custom_id
        assert custom_id in progress_reporter._active_operations

    def test_update_progress(self, progress_reporter):
        """Test updating progress for an operation."""
        operation_id = progress_reporter.start_operation("test_operation")

        # Mock progress callback
        callback = Mock()
        progress_reporter.add_progress_callback(operation_id, callback)

        # Update progress
        progress_reporter.update_progress(operation_id, 50, 100, "Processing items")

        # Check operation state
        operation = progress_reporter._active_operations[operation_id]
        assert len(operation["progress_updates"]) == 1

        update = operation["progress_updates"][0]
        assert update.current == 50
        assert update.total == 100
        assert update.message == "Processing items"
        assert update.percentage == 50.0

        # Check callback was called
        callback.assert_called_once()

        # Check logging
        progress_reporter.logger.info.assert_called()

    def test_update_progress_unknown_operation(self, progress_reporter):
        """Test updating progress for unknown operation."""
        progress_reporter.update_progress("unknown-op", 50, 100, "test")

        # Should log warning
        progress_reporter.logger.warning.assert_called()

    def test_finish_operation_success(self, progress_reporter):
        """Test finishing an operation successfully."""
        operation_id = progress_reporter.start_operation("test_operation")

        progress_reporter.finish_operation(operation_id, success=True, test_data="value")

        # Operation should be removed
        assert operation_id not in progress_reporter._active_operations
        assert operation_id not in progress_reporter._progress_callbacks

        # Check logging
        progress_reporter.logger.log.assert_called()
        progress_reporter.audit_logger.info.assert_called()

    def test_finish_operation_failure(self, progress_reporter):
        """Test finishing an operation with failure."""
        operation_id = progress_reporter.start_operation("test_operation")

        progress_reporter.finish_operation(operation_id, success=False, error_message="Test error")

        # Operation should be removed
        assert operation_id not in progress_reporter._active_operations

        # Check error logging
        progress_reporter.logger.log.assert_called()

    def test_finish_operation_unknown(self, progress_reporter):
        """Test finishing unknown operation."""
        progress_reporter.finish_operation("unknown-op", success=True)

        # Should log warning
        progress_reporter.logger.warning.assert_called()

    def test_log_assignment_copy_start(self, progress_reporter):
        """Test logging assignment copy start."""
        operation_id = progress_reporter.start_operation("copy_assignments")

        source_entity = EntityReference(
            entity_type=EntityType.USER, entity_id="user-123", entity_name="test.user"
        )
        target_entity = EntityReference(
            entity_type=EntityType.GROUP, entity_id="group-456", entity_name="test-group"
        )

        progress_reporter.log_assignment_copy_start(
            operation_id, source_entity, target_entity, 10, "filter: accounts=123"
        )

        # Check audit log was created
        operation = progress_reporter._active_operations[operation_id]
        assert len(operation["audit_logs"]) == 2  # start + copy_started

        copy_start_log = operation["audit_logs"][1]
        assert copy_start_log.action == "copy_started"
        assert copy_start_log.source_entity == source_entity
        assert copy_start_log.target_entity == target_entity
        assert copy_start_log.details["total_assignments"] == 10
        assert copy_start_log.details["filters_applied"] == "filter: accounts=123"

    def test_log_assignment_copy_result(self, progress_reporter):
        """Test logging assignment copy result."""
        operation_id = progress_reporter.start_operation("copy_assignments")

        source_entity = EntityReference(
            entity_type=EntityType.USER, entity_id="user-123", entity_name="test.user"
        )
        target_entity = EntityReference(
            entity_type=EntityType.GROUP, entity_id="group-456", entity_name="test-group"
        )

        assignment = PermissionAssignment(
            permission_set_arn="arn:aws:sso:::permissionSet/ps-123",
            permission_set_name="TestPS",
            account_id="123456789012",
            account_name="test-account",
        )

        copy_result = CopyResult(
            source=source_entity,
            target=target_entity,
            assignments_copied=[assignment],
            assignments_skipped=[],
            rollback_id="rollback-123",
            success=True,
            error_message=None,
        )

        progress_reporter.log_assignment_copy_result(operation_id, copy_result, 1500.0)

        # Check audit log was created
        operation = progress_reporter._active_operations[operation_id]
        assert len(operation["audit_logs"]) == 2  # start + copy_completed

        copy_result_log = operation["audit_logs"][1]
        assert copy_result_log.action == "copy_completed"
        assert copy_result_log.result == "success"
        assert copy_result_log.duration_ms == 1500.0
        assert copy_result_log.details["assignments_copied"] == 1
        assert copy_result_log.details["assignments_skipped"] == 0
        assert copy_result_log.details["rollback_id"] == "rollback-123"

    def test_log_permission_set_clone_start(self, progress_reporter):
        """Test logging permission set clone start."""
        operation_id = progress_reporter.start_operation("clone_permission_set")

        progress_reporter.log_permission_set_clone_start(
            operation_id, "source-ps", "target-ps", "arn:aws:sso:::permissionSet/ps-123"
        )

        # Check audit log was created
        operation = progress_reporter._active_operations[operation_id]
        assert len(operation["audit_logs"]) == 2  # start + clone_started

        clone_start_log = operation["audit_logs"][1]
        assert clone_start_log.action == "clone_started"
        assert clone_start_log.source_permission_set == "source-ps"
        assert clone_start_log.target_permission_set == "target-ps"
        assert (
            clone_start_log.details["source_permission_set_arn"]
            == "arn:aws:sso:::permissionSet/ps-123"
        )

    def test_log_permission_set_clone_result(self, progress_reporter):
        """Test logging permission set clone result."""
        operation_id = progress_reporter.start_operation("clone_permission_set")

        cloned_config = PermissionSetConfig(
            name="target-ps",
            description="Test permission set",
            session_duration="PT1H",
            relay_state_url=None,
            aws_managed_policies=["arn:aws:iam::aws:policy/ReadOnlyAccess"],
            customer_managed_policies=[CustomerManagedPolicy(name="CustomPolicy", path="/")],
            inline_policy='{"Version": "2012-10-17", "Statement": []}',
        )

        clone_result = CloneResult(
            source_name="source-ps",
            target_name="target-ps",
            cloned_config=cloned_config,
            rollback_id="rollback-456",
            success=True,
            error_message=None,
        )

        progress_reporter.log_permission_set_clone_result(operation_id, clone_result, 2000.0)

        # Check audit log was created
        operation = progress_reporter._active_operations[operation_id]
        assert len(operation["audit_logs"]) == 2  # start + clone_completed

        clone_result_log = operation["audit_logs"][1]
        assert clone_result_log.action == "clone_completed"
        assert clone_result_log.result == "success"
        assert clone_result_log.duration_ms == 2000.0
        assert clone_result_log.details["rollback_id"] == "rollback-456"
        assert clone_result_log.details["cloned_config"]["aws_managed_policies_count"] == 1
        assert clone_result_log.details["cloned_config"]["customer_managed_policies_count"] == 1
        assert clone_result_log.details["cloned_config"]["has_inline_policy"] is True

    def test_log_rollback_operation(self, progress_reporter):
        """Test logging rollback operation."""
        rollback_result = {
            "operation_id": "original-op-123",
            "success": True,
            "success_count": 5,
            "failure_count": 0,
            "total_actions": 5,
        }

        progress_reporter.log_rollback_operation(
            "original-op-123", "assignment_copy", rollback_result, 1000.0
        )

        # Check logging calls
        progress_reporter.audit_logger.info.assert_called()
        progress_reporter.logger.info.assert_called()

    def test_log_performance_metric(self, progress_reporter):
        """Test logging performance metric."""
        operation_id = progress_reporter.start_operation("test_operation")

        progress_reporter.log_performance_metric(
            operation_id,
            "copy_assignments",
            "throughput",
            15.5,
            "assignments/second",
            batch_size=10,
        )

        # Check performance metric was stored
        operation = progress_reporter._active_operations[operation_id]
        assert len(operation["performance_metrics"]) == 1

        metric = operation["performance_metrics"][0]
        assert metric.metric_name == "throughput"
        assert metric.metric_value == 15.5
        assert metric.metric_unit == "assignments/second"
        assert metric.context["batch_size"] == 10

        # Check logging
        progress_reporter.performance_logger.info.assert_called()

    def test_add_progress_callback(self, progress_reporter):
        """Test adding progress callback."""
        operation_id = progress_reporter.start_operation("test_operation")
        callback = Mock()

        progress_reporter.add_progress_callback(operation_id, callback)

        assert operation_id in progress_reporter._progress_callbacks
        assert callback in progress_reporter._progress_callbacks[operation_id]

        # Test callback is called on progress update
        progress_reporter.update_progress(operation_id, 50, 100, "test")
        callback.assert_called_once()

    def test_progress_callback_error_handling(self, progress_reporter):
        """Test error handling in progress callbacks."""
        operation_id = progress_reporter.start_operation("test_operation")

        # Add callback that raises exception
        def failing_callback(update):
            raise Exception("Callback error")

        progress_reporter.add_progress_callback(operation_id, failing_callback)

        # Update progress should not fail
        progress_reporter.update_progress(operation_id, 50, 100, "test")

        # Error should be logged
        progress_reporter.logger.error.assert_called()

    def test_get_operation_status(self, progress_reporter):
        """Test getting operation status."""
        operation_id = progress_reporter.start_operation("test_operation", test_context="value")

        # Add some progress updates
        progress_reporter.update_progress(operation_id, 25, 100, "First update")
        progress_reporter.update_progress(operation_id, 50, 100, "Second update")

        status = progress_reporter.get_operation_status(operation_id)

        assert status is not None
        assert status["operation_id"] == operation_id
        assert status["operation_type"] == "test_operation"
        assert status["context"]["test_context"] == "value"
        assert status["latest_progress"]["current"] == 50
        assert status["latest_progress"]["total"] == 100
        assert status["latest_progress"]["percentage"] == 50.0
        assert status["latest_progress"]["message"] == "Second update"
        assert status["total_progress_updates"] == 2

    def test_get_operation_status_unknown(self, progress_reporter):
        """Test getting status for unknown operation."""
        status = progress_reporter.get_operation_status("unknown-op")
        assert status is None

    def test_get_active_operations(self, progress_reporter):
        """Test getting all active operations."""
        # Start multiple operations
        op1 = progress_reporter.start_operation("operation1")
        op2 = progress_reporter.start_operation("operation2")

        active_ops = progress_reporter.get_active_operations()

        assert len(active_ops) == 2
        operation_ids = [op["operation_id"] for op in active_ops]
        assert op1 in operation_ids
        assert op2 in operation_ids

    def test_get_active_operations_empty(self, progress_reporter):
        """Test getting active operations when none exist."""
        active_ops = progress_reporter.get_active_operations()
        assert active_ops == []


class TestGlobalProgressReporter:
    """Test global progress reporter functions."""

    def test_get_progress_reporter(self):
        """Test getting global progress reporter."""
        # Clear global instance
        import src.awsideman.permission_cloning.progress_reporter as pr_module

        pr_module._global_progress_reporter = None

        reporter = get_progress_reporter("test-user")
        assert reporter is not None
        assert reporter.user_id == "test-user"

        # Should return same instance on second call
        reporter2 = get_progress_reporter()
        assert reporter2 is reporter

    def test_set_progress_reporter(self):
        """Test setting global progress reporter."""
        custom_reporter = ProgressReporter(user_id="custom-user")
        set_progress_reporter(custom_reporter)

        retrieved_reporter = get_progress_reporter()
        assert retrieved_reporter is custom_reporter
        assert retrieved_reporter.user_id == "custom-user"


if __name__ == "__main__":
    pytest.main([__file__])
