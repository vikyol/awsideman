"""Tests for rollback cleanup and retention policies."""

import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from src.awsideman.rollback.cleanup_scheduler import CleanupScheduler, get_global_scheduler
from src.awsideman.rollback.logger import OperationLogger
from src.awsideman.rollback.models import (
    OperationRecord,
    OperationResult,
    OperationType,
    PrincipalType,
)
from src.awsideman.rollback.storage import OperationStore
from src.awsideman.utils.config import Config


class TestOperationStoreCleanup:
    """Test cleanup functionality in OperationStore."""

    def setup_method(self):
        """Setup test method with temporary storage."""
        self.temp_dir = tempfile.mkdtemp()
        self.store = OperationStore(self.temp_dir)

    def _create_test_operation(self, days_ago: int = 0) -> OperationRecord:
        """Create a test operation record."""
        timestamp = datetime.now(timezone.utc) - timedelta(days=days_ago)

        operation = OperationRecord(
            operation_id=f"test-op-{days_ago}",
            timestamp=timestamp,
            operation_type=OperationType.ASSIGN,
            principal_id="test-user",
            principal_type=PrincipalType.USER,
            principal_name="Test User",
            permission_set_arn="arn:aws:sso:::permissionSet/test",
            permission_set_name="TestPermissionSet",
            account_ids=["123456789012"],
            account_names=["Test Account"],
            results=[OperationResult(account_id="123456789012", success=True)],
        )

        return operation

    def test_cleanup_old_operations(self):
        """Test cleanup of old operations."""
        # Create operations of different ages
        old_op = self._create_test_operation(days_ago=100)
        recent_op = self._create_test_operation(days_ago=30)

        # Store operations
        self.store.store_operation(old_op)
        self.store.store_operation(recent_op)

        # Verify both operations exist
        assert len(self.store.get_operations()) == 2

        # Clean up operations older than 90 days
        removed_count = self.store.cleanup_old_operations(days=90)

        # Verify old operation was removed
        assert removed_count == 1
        remaining_ops = self.store.get_operations()
        assert len(remaining_ops) == 1
        assert remaining_ops[0].operation_id == "test-op-30"

    def test_cleanup_by_count_limit(self):
        """Test cleanup by operation count limit."""
        # Create multiple operations
        for i in range(15):
            op = self._create_test_operation(days_ago=i)
            self.store.store_operation(op)

        # Verify all operations exist
        assert len(self.store.get_operations()) == 15

        # Clean up to keep only 10 operations
        removed_count = self.store.cleanup_by_count_limit(max_operations=10)

        # Verify 5 operations were removed
        assert removed_count == 5
        remaining_ops = self.store.get_operations()
        assert len(remaining_ops) == 10

        # Verify the newest operations were kept
        operation_ids = [op.operation_id for op in remaining_ops]
        for i in range(10):
            assert f"test-op-{i}" in operation_ids

    def test_cleanup_rollback_records(self):
        """Test cleanup of rollback records."""
        # Create rollback records
        old_rollback = {
            "rollback_id": "old-rollback",
            "timestamp": (datetime.now(timezone.utc) - timedelta(days=100)).isoformat(),
            "original_operation_id": "test-op-1",
        }
        recent_rollback = {
            "rollback_id": "recent-rollback",
            "timestamp": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
            "original_operation_id": "test-op-2",
        }

        # Store rollback records
        self.store.store_rollback_record(old_rollback)
        self.store.store_rollback_record(recent_rollback)

        # Verify both records exist
        rollbacks_data = self.store._read_rollbacks_file()
        assert len(rollbacks_data["rollbacks"]) == 2

        # Clean up rollback records older than 90 days
        removed_count = self.store.cleanup_rollback_records(days=90)

        # Verify old rollback was removed
        assert removed_count == 1
        rollbacks_data = self.store._read_rollbacks_file()
        assert len(rollbacks_data["rollbacks"]) == 1
        assert rollbacks_data["rollbacks"][0]["rollback_id"] == "recent-rollback"

    def test_file_rotation(self):
        """Test file rotation when files get too large."""
        # Create many operations to make file large
        for i in range(100):
            op = self._create_test_operation(days_ago=i)
            self.store.store_operation(op)

        # Force rotation with very small size limit
        rotated = self.store.rotate_files_if_needed(max_size_mb=0.001)  # Very small limit

        # Verify operations file was rotated
        assert rotated["operations"] is True

        # Verify backup file was created
        backup_files = list(self.store.storage_dir.glob("operations_*.json"))
        assert len(backup_files) == 1

        # Verify new operations file is empty
        data = self.store._read_operations_file()
        assert len(data["operations"]) == 0

    def test_get_file_sizes(self):
        """Test getting file sizes."""
        # Create some operations
        for i in range(5):
            op = self._create_test_operation(days_ago=i)
            self.store.store_operation(op)

        sizes = self.store.get_file_sizes()

        assert "operations_file" in sizes
        assert "rollbacks_file" in sizes
        assert sizes["operations_file"] > 0
        assert sizes["rollbacks_file"] > 0


class TestOperationLoggerCleanup:
    """Test cleanup functionality in OperationLogger."""

    def setup_method(self):
        """Setup test method with temporary storage."""
        self.temp_dir = tempfile.mkdtemp()
        self.logger = OperationLogger(self.temp_dir)

    def test_perform_maintenance(self):
        """Test comprehensive maintenance operation."""
        # Create operations of different ages and quantities
        for i in range(20):
            self.logger.log_operation(
                operation_type="assign",
                principal_id=f"user-{i}",
                principal_type="USER",
                principal_name=f"User {i}",
                permission_set_arn="arn:aws:sso:::permissionSet/test",
                permission_set_name="TestPermissionSet",
                account_ids=["123456789012"],
                account_names=["Test Account"],
                results=[{"account_id": "123456789012", "success": True}],
                metadata={"created_days_ago": i},
            )

        # Manually adjust timestamps to simulate age
        data = self.logger.store._read_operations_file()
        for i, op in enumerate(data["operations"]):
            old_timestamp = datetime.now(timezone.utc) - timedelta(days=i)
            op["timestamp"] = old_timestamp.isoformat()
        self.logger.store._write_operations_file(data)

        # Run maintenance
        results = self.logger.perform_maintenance(
            retention_days=10, max_operations=15, max_file_size_mb=50
        )

        # Verify results structure
        assert "operations_removed_by_age" in results
        assert "operations_removed_by_count" in results
        assert "rollbacks_removed" in results
        assert "files_rotated" in results
        assert "storage_stats_before" in results
        assert "storage_stats_after" in results

        # Verify operations were cleaned up
        assert results["operations_removed_by_age"] >= 0
        remaining_ops = self.logger.get_operations()
        assert len(remaining_ops) <= 15


class TestCleanupScheduler:
    """Test cleanup scheduler functionality."""

    def setup_method(self):
        """Setup test method."""
        self.temp_dir = tempfile.mkdtemp()
        self.mock_config = Mock(spec=Config)
        self.mock_config.get_rollback_config.return_value = {
            "enabled": True,
            "auto_cleanup": True,
            "retention_days": 90,
            "max_operations": 10000,
        }
        self.scheduler = CleanupScheduler(self.mock_config)

    def test_scheduler_start_stop(self):
        """Test starting and stopping the scheduler."""
        assert not self.scheduler.is_running()

        # Start scheduler
        self.scheduler.start(interval_hours=1)
        assert self.scheduler.is_running()

        # Stop scheduler
        stopped = self.scheduler.stop(timeout=2.0)
        assert stopped
        assert not self.scheduler.is_running()

    def test_run_cleanup_now(self):
        """Test running cleanup immediately."""
        results = self.scheduler.run_cleanup_now()

        assert "cleanup_time" in results
        assert "operations_removed_by_age" in results
        assert "operations_removed_by_count" in results
        assert "rollbacks_removed" in results
        assert self.scheduler._last_cleanup is not None

    def test_cleanup_disabled_in_config(self):
        """Test cleanup when disabled in configuration."""
        self.mock_config.get_rollback_config.return_value = {"enabled": False, "auto_cleanup": True}

        results = self.scheduler.run_cleanup_now()

        assert results["skipped"] is True
        assert "Rollback disabled" in results["reason"]

    def test_should_run_cleanup(self):
        """Test cleanup scheduling logic."""
        # Should run when never run before
        assert self.scheduler.should_run_cleanup(interval_hours=24)

        # Run cleanup to set last cleanup time
        self.scheduler.run_cleanup_now()

        # Should not run immediately after
        assert not self.scheduler.should_run_cleanup(interval_hours=24)

        # Simulate time passing
        self.scheduler._last_cleanup = datetime.now() - timedelta(hours=25)
        assert self.scheduler.should_run_cleanup(interval_hours=24)

    def test_should_not_run_when_auto_cleanup_disabled(self):
        """Test that cleanup doesn't run when auto_cleanup is disabled."""
        self.mock_config.get_rollback_config.return_value = {
            "enabled": True,
            "auto_cleanup": False,
            "retention_days": 90,
            "max_operations": 10000,
        }

        assert not self.scheduler.should_run_cleanup(interval_hours=24)

    def test_cleanup_callback(self):
        """Test cleanup callback functionality."""
        callback_results = []

        def test_callback(results):
            callback_results.append(results)

        self.scheduler.set_cleanup_callback(test_callback)
        self.scheduler.run_cleanup_now()

        assert len(callback_results) == 1
        assert "cleanup_time" in callback_results[0]

    def test_get_status(self):
        """Test getting scheduler status."""
        status = self.scheduler.get_status()

        assert "running" in status
        assert "auto_cleanup_enabled" in status
        assert "rollback_enabled" in status
        assert "last_cleanup" in status
        assert "retention_days" in status
        assert "max_operations" in status
        assert "storage_stats" in status

    def test_get_next_cleanup_time(self):
        """Test getting next cleanup time."""
        # Should be None when never run
        assert self.scheduler.get_next_cleanup_time() is None

        # Run cleanup
        self.scheduler.run_cleanup_now()

        # Should have next cleanup time
        next_time = self.scheduler.get_next_cleanup_time(interval_hours=24)
        assert next_time is not None
        assert next_time > datetime.now()


class TestGlobalScheduler:
    """Test global scheduler functionality."""

    def teardown_method(self):
        """Cleanup after each test."""
        # Stop any running global scheduler
        from src.awsideman.rollback.cleanup_scheduler import stop_global_scheduler

        stop_global_scheduler()

    def test_get_global_scheduler(self):
        """Test getting global scheduler instance."""
        scheduler1 = get_global_scheduler()
        scheduler2 = get_global_scheduler()

        # Should return the same instance
        assert scheduler1 is scheduler2

    def test_start_stop_global_scheduler(self):
        """Test starting and stopping global scheduler."""
        from src.awsideman.rollback.cleanup_scheduler import (
            start_global_scheduler,
            stop_global_scheduler,
        )

        # Start global scheduler
        start_global_scheduler(interval_hours=1)
        scheduler = get_global_scheduler()
        assert scheduler.is_running()

        # Stop global scheduler
        stopped = stop_global_scheduler(timeout=2.0)
        assert stopped


class TestCleanupIntegration:
    """Integration tests for cleanup functionality."""

    def setup_method(self):
        """Setup test method with temporary storage."""
        self.temp_dir = tempfile.mkdtemp()
        self.logger = OperationLogger(self.temp_dir)

    def test_full_cleanup_cycle(self):
        """Test a complete cleanup cycle with real data."""
        # Create operations with various ages
        operations_data = [
            (150, "very-old"),  # Should be removed by age
            (100, "old"),  # Should be removed by age
            (50, "medium"),  # Should be kept
            (30, "recent"),  # Should be kept
            (10, "very-recent"),  # Should be kept
        ]

        for days_ago, suffix in operations_data:
            self.logger.log_operation(
                operation_type="assign",
                principal_id=f"user-{suffix}",
                principal_type="USER",
                principal_name=f"User {suffix}",
                permission_set_arn="arn:aws:sso:::permissionSet/test",
                permission_set_name="TestPermissionSet",
                account_ids=["123456789012"],
                account_names=["Test Account"],
                results=[{"account_id": "123456789012", "success": True}],
            )

        # Manually adjust timestamps
        data = self.logger.store._read_operations_file()
        for i, (days_ago, suffix) in enumerate(operations_data):
            old_timestamp = datetime.now(timezone.utc) - timedelta(days=days_ago)
            data["operations"][i]["timestamp"] = old_timestamp.isoformat()
        self.logger.store._write_operations_file(data)

        # Verify initial state
        initial_ops = self.logger.get_operations()
        assert len(initial_ops) == 5

        # Run cleanup with 90-day retention
        results = self.logger.perform_maintenance(
            retention_days=90, max_operations=10000, max_file_size_mb=50
        )

        # Verify cleanup results
        assert results["operations_removed_by_age"] == 2  # very-old and old

        # Verify remaining operations
        remaining_ops = self.logger.get_operations()
        assert len(remaining_ops) == 3

        remaining_names = [op.principal_name for op in remaining_ops]
        assert "User medium" in remaining_names
        assert "User recent" in remaining_names
        assert "User very-recent" in remaining_names
        assert "User very-old" not in remaining_names
        assert "User old" not in remaining_names


if __name__ == "__main__":
    pytest.main([__file__])
