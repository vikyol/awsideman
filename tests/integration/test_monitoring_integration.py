"""
Integration tests for backup-restore monitoring system.
"""

import asyncio
from datetime import datetime, timedelta

import pytest

from src.awsideman.backup_restore.models import (
    BackupMetadata,
    BackupResult,
    BackupType,
    EncryptionMetadata,
    RestoreResult,
    RetentionPolicy,
)
from src.awsideman.backup_restore.monitoring import (
    AlertSeverity,
    BackupMonitor,
    OperationStatus,
    OperationType,
)


class TestMonitoringIntegration:
    """Integration tests for the complete monitoring system."""

    @pytest.fixture
    def backup_monitor(self):
        return BackupMonitor()

    @pytest.mark.asyncio
    async def test_complete_backup_monitoring_workflow(self, backup_monitor):
        """Test complete backup operation monitoring workflow."""
        operation_id = "backup_integration_test"

        # Start backup monitoring
        await backup_monitor.start_operation_monitoring(
            operation_id=operation_id,
            operation_type=OperationType.BACKUP,
            total_steps=5,
            description="Integration test backup",
        )

        # Simulate backup progress
        await backup_monitor.update_operation_progress(operation_id, 1, "Collecting users")
        await backup_monitor.update_operation_progress(operation_id, 2, "Collecting groups")
        await backup_monitor.update_operation_progress(
            operation_id, 3, "Collecting permission sets"
        )
        await backup_monitor.update_operation_progress(operation_id, 4, "Collecting assignments")
        await backup_monitor.update_operation_progress(operation_id, 5, "Finalizing backup")

        # Create backup result
        backup_metadata = BackupMetadata(
            backup_id="backup_123",
            timestamp=datetime.now(),
            instance_arn="arn:aws:sso:::instance/ssoins-123456789",
            backup_type=BackupType.FULL,
            version="1.0.0",
            source_account="123456789012",
            source_region="us-east-1",
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(),
            resource_counts={"users": 100, "groups": 20, "permission_sets": 10, "assignments": 200},
            size_bytes=1024 * 1024,  # 1 MB
        )

        backup_result = BackupResult(
            success=True,
            backup_id="backup_123",
            message="Backup completed successfully",
            metadata=backup_metadata,
        )

        # Complete monitoring
        await backup_monitor.complete_operation_monitoring(operation_id, True, backup_result)

        # Verify progress tracking
        progress = await backup_monitor.progress_reporter.get_progress(operation_id)
        assert progress is not None
        assert progress["status"] == OperationStatus.COMPLETED.value
        assert progress["progress_percentage"] == 100.0

        # Verify metrics collection
        assert len(backup_monitor.metrics_collector._operation_metrics) == 1
        recorded_metric = backup_monitor.metrics_collector._operation_metrics[0]
        assert recorded_metric.operation_id == operation_id
        assert recorded_metric.operation_type == OperationType.BACKUP
        assert recorded_metric.status == OperationStatus.COMPLETED
        assert recorded_metric.resource_counts == backup_metadata.resource_counts
        assert recorded_metric.data_size_bytes == backup_metadata.size_bytes

    @pytest.mark.asyncio
    async def test_failed_backup_monitoring_with_alerts(self, backup_monitor):
        """Test monitoring of failed backup operation with automatic alerting."""
        operation_id = "failed_backup_test"

        # Start backup monitoring
        await backup_monitor.start_operation_monitoring(
            operation_id=operation_id,
            operation_type=OperationType.BACKUP,
            total_steps=5,
            description="Failed backup test",
        )

        # Simulate partial progress
        await backup_monitor.update_operation_progress(operation_id, 2, "Processing users")

        # Simulate failure
        backup_result = BackupResult(
            success=False,
            message="Backup failed due to network timeout",
            errors=["Connection timeout to AWS API"],
        )

        # Complete monitoring with failure
        await backup_monitor.complete_operation_monitoring(operation_id, False, backup_result)

        # Verify progress tracking shows failure
        progress = await backup_monitor.progress_reporter.get_progress(operation_id)
        assert progress["status"] == OperationStatus.FAILED.value

        # Verify metrics recorded failure
        assert len(backup_monitor.metrics_collector._operation_metrics) == 1
        recorded_metric = backup_monitor.metrics_collector._operation_metrics[0]
        assert recorded_metric.status == OperationStatus.FAILED
        assert recorded_metric.error_count == 1

        # Verify alert was created
        active_alerts = backup_monitor.alert_manager.get_active_alerts()
        failure_alerts = [a for a in active_alerts if "Operation Failed" in a.title]
        assert len(failure_alerts) == 1
        assert failure_alerts[0].severity == AlertSeverity.ERROR
        assert operation_id in failure_alerts[0].message

    @pytest.mark.asyncio
    async def test_restore_monitoring_workflow(self, backup_monitor):
        """Test restore operation monitoring workflow."""
        operation_id = "restore_integration_test"

        # Start restore monitoring
        await backup_monitor.start_operation_monitoring(
            operation_id=operation_id,
            operation_type=OperationType.RESTORE,
            total_steps=4,
            description="Integration test restore",
        )

        # Simulate restore progress
        await backup_monitor.update_operation_progress(operation_id, 1, "Validating backup")
        await backup_monitor.update_operation_progress(operation_id, 2, "Restoring users")
        await backup_monitor.update_operation_progress(operation_id, 3, "Restoring groups")
        await backup_monitor.update_operation_progress(operation_id, 4, "Restoring assignments")

        # Create restore result
        restore_result = RestoreResult(
            success=True,
            message="Restore completed successfully",
            changes_applied={"users": 50, "groups": 10, "assignments": 100},
        )

        # Complete monitoring
        await backup_monitor.complete_operation_monitoring(operation_id, True, restore_result)

        # Verify metrics collection
        assert len(backup_monitor.metrics_collector._operation_metrics) == 1
        recorded_metric = backup_monitor.metrics_collector._operation_metrics[0]
        assert recorded_metric.operation_type == OperationType.RESTORE
        assert recorded_metric.status == OperationStatus.COMPLETED
        assert recorded_metric.resource_counts == restore_result.changes_applied

    def test_dashboard_integration_with_real_data(self, backup_monitor):
        """Test dashboard integration with real monitoring data."""
        # Add some historical data
        from src.awsideman.backup_restore.monitoring import OperationMetrics

        for i in range(5):
            backup_monitor.metrics_collector.record_operation_metrics(
                OperationMetrics(
                    operation_id=f"historical_backup_{i}",
                    operation_type=OperationType.BACKUP,
                    status=OperationStatus.COMPLETED if i < 4 else OperationStatus.FAILED,
                    duration=timedelta(minutes=5 + i),
                    resource_counts={"users": 100 + i * 10},
                    data_size_bytes=1024 * 1024 * (i + 1),
                )
            )

        # Create some alerts
        backup_monitor.alert_manager.create_alert(
            "test_alert_1", AlertSeverity.WARNING, "Test Warning", "This is a test warning"
        )

        backup_monitor.alert_manager.create_alert(
            "test_alert_2", AlertSeverity.ERROR, "Test Error", "This is a test error"
        )

        # Get dashboard data
        storage_info = {
            "used_bytes": 500 * 1024 * 1024,  # 500 MB
            "total_bytes": 1000 * 1024 * 1024,  # 1 GB
        }

        dashboard_data = backup_monitor.dashboard.get_dashboard_data(storage_info)

        # Verify dashboard data structure
        assert "system_metrics" in dashboard_data
        assert "active_operations" in dashboard_data
        assert "active_alerts" in dashboard_data
        assert "recent_metrics" in dashboard_data

        # Verify system metrics
        system_metrics = dashboard_data["system_metrics"]
        assert system_metrics["storage_usage_percentage"] == 50.0
        assert system_metrics["success_rate_24h"] == 80.0  # 4 out of 5 successful

        # Verify alerts
        assert len(dashboard_data["active_alerts"]) == 2
        alert_titles = [alert["title"] for alert in dashboard_data["active_alerts"]]
        assert "Test Warning" in alert_titles
        assert "Test Error" in alert_titles

    def test_metrics_export_integration(self, backup_monitor):
        """Test metrics export functionality with real data."""
        # Add some test metrics
        from src.awsideman.backup_restore.monitoring import OperationMetrics

        for i in range(3):
            backup_monitor.metrics_collector.record_operation_metrics(
                OperationMetrics(
                    operation_id=f"export_test_backup_{i}",
                    operation_type=OperationType.BACKUP,
                    status=OperationStatus.COMPLETED,
                    duration=timedelta(minutes=5),
                    resource_counts={"users": 100},
                    data_size_bytes=1024 * 1024,
                )
            )

        # Test Prometheus export
        prometheus_output = backup_monitor.dashboard.export_metrics_for_external_dashboard(
            "prometheus"
        )
        assert "backup_operations_total" in prometheus_output
        assert "backup_operation_duration_seconds" in prometheus_output
        assert 'status="completed"' in prometheus_output

        # Test JSON export
        json_output = backup_monitor.dashboard.export_metrics_for_external_dashboard("json")
        import json

        data = json.loads(json_output)

        assert "operations" in data
        assert len(data["operations"]) == 3
        assert all(op["operation_type"] == "backup" for op in data["operations"])

    def test_system_health_monitoring_integration(self, backup_monitor):
        """Test integrated system health monitoring."""
        # Simulate various system conditions

        # Test 1: High storage usage
        storage_info_high = {
            "used_bytes": 920 * 1024 * 1024,  # 920 MB
            "total_bytes": 1000 * 1024 * 1024,  # 1 GB (92% usage)
        }

        alerts = backup_monitor.check_system_health(storage_info_high)
        storage_alerts = [a for a in alerts if "Storage" in a.title]
        assert len(storage_alerts) == 1
        assert storage_alerts[0].severity == AlertSeverity.CRITICAL

        # Test 2: Low success rate
        # Add many failed operations
        from src.awsideman.backup_restore.monitoring import OperationMetrics

        for i in range(10):
            backup_monitor.metrics_collector.record_operation_metrics(
                OperationMetrics(
                    operation_id=f"failed_op_{i}",
                    operation_type=OperationType.BACKUP,
                    status=OperationStatus.FAILED,
                    duration=timedelta(minutes=1),
                )
            )

        storage_info_normal = {"used_bytes": 100 * 1024 * 1024, "total_bytes": 1000 * 1024 * 1024}

        alerts = backup_monitor.check_system_health(storage_info_normal)
        success_rate_alerts = [a for a in alerts if "Success Rate" in a.title]
        assert len(success_rate_alerts) == 1
        assert success_rate_alerts[0].severity == AlertSeverity.ERROR

    @pytest.mark.asyncio
    async def test_concurrent_operations_monitoring(self, backup_monitor):
        """Test monitoring multiple concurrent operations."""
        operation_ids = ["concurrent_op_1", "concurrent_op_2", "concurrent_op_3"]

        # Start multiple operations
        for i, op_id in enumerate(operation_ids):
            await backup_monitor.start_operation_monitoring(
                operation_id=op_id,
                operation_type=OperationType.BACKUP,
                total_steps=10,
                description=f"Concurrent backup {i+1}",
            )

        # Update progress for all operations
        for op_id in operation_ids:
            await backup_monitor.update_operation_progress(op_id, 5, "Halfway done")

        # Complete operations with different outcomes
        await backup_monitor.complete_operation_monitoring(operation_ids[0], True)
        await backup_monitor.complete_operation_monitoring(operation_ids[1], True)
        await backup_monitor.complete_operation_monitoring(operation_ids[2], False)

        # Verify all operations were tracked
        all_operations = backup_monitor.progress_reporter.get_all_operations()
        assert len(all_operations) == 3

        # Verify metrics were recorded for all operations
        assert len(backup_monitor.metrics_collector._operation_metrics) == 3

        # Verify success rate calculation
        success_rate = backup_monitor.metrics_collector.calculate_success_rate(OperationType.BACKUP)
        assert abs(success_rate - 66.67) < 0.1  # 2 out of 3 successful

    def test_monitoring_cleanup_integration(self, backup_monitor):
        """Test integrated cleanup of monitoring data."""
        # Add old data to all components
        old_time = datetime.now() - timedelta(days=2)

        # Add old progress info
        from src.awsideman.backup_restore.monitoring import ProgressInfo

        backup_monitor.progress_reporter._operations["old_op"] = ProgressInfo(
            operation_id="old_op",
            operation_type=OperationType.BACKUP,
            status=OperationStatus.COMPLETED,
            total_steps=10,
            completed_steps=10,
            start_time=old_time,
            last_update=old_time,
        )

        # Add old alert
        backup_monitor.alert_manager.create_alert(
            "old_alert", AlertSeverity.INFO, "Old Alert", "This is an old alert"
        )
        backup_monitor.alert_manager.resolve_alert("old_alert")
        backup_monitor.alert_manager._alerts["old_alert"].resolved_at = old_time

        # Add recent data
        backup_monitor.progress_reporter._operations["recent_op"] = ProgressInfo(
            operation_id="recent_op",
            operation_type=OperationType.BACKUP,
            status=OperationStatus.COMPLETED,
            total_steps=10,
            completed_steps=10,
        )

        backup_monitor.alert_manager.create_alert(
            "recent_alert", AlertSeverity.INFO, "Recent Alert", "This is a recent alert"
        )

        # Perform cleanup
        backup_monitor.cleanup_old_data()

        # Verify old data was cleaned up
        assert "old_op" not in backup_monitor.progress_reporter._operations
        assert "recent_op" in backup_monitor.progress_reporter._operations

        # Note: The cleanup uses default max_age of 7 days, but we set old_time to 2 days ago
        # So the old alert won't be cleaned up. Let's check that cleanup was called instead.
        # For a proper test, we'd need to set the old_time to more than 7 days ago.
        old_time_for_cleanup = datetime.now() - timedelta(days=8)
        backup_monitor.alert_manager._alerts["old_alert"].resolved_at = old_time_for_cleanup
        backup_monitor.cleanup_old_data()

        assert "old_alert" not in backup_monitor.alert_manager._alerts
        assert "recent_alert" in backup_monitor.alert_manager._alerts

    def test_error_handling_in_monitoring(self, backup_monitor):
        """Test error handling in monitoring system."""

        # Test callback error handling
        def failing_callback(progress_info):
            raise Exception("Callback error")

        backup_monitor.progress_reporter.add_progress_callback(failing_callback)

        # This should not raise an exception despite the failing callback
        asyncio.run(
            backup_monitor.start_operation_monitoring(
                "error_test_op", OperationType.BACKUP, 10, "Error handling test"
            )
        )

        # Verify operation was still tracked despite callback error
        progress = asyncio.run(backup_monitor.progress_reporter.get_progress("error_test_op"))
        assert progress is not None

        # Test alert handler error handling
        def failing_alert_handler(alert):
            raise Exception("Alert handler error")

        backup_monitor.alert_manager.add_alert_handler(failing_alert_handler)

        # This should not raise an exception despite the failing handler
        backup_monitor.alert_manager.create_alert(
            "error_test_alert", AlertSeverity.INFO, "Error Test Alert", "Testing error handling"
        )

        # Verify alert was still created despite handler error
        assert "error_test_alert" in backup_monitor.alert_manager._alerts


if __name__ == "__main__":
    pytest.main([__file__])
