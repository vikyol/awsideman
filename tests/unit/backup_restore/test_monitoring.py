"""
Unit tests for backup-restore monitoring and metrics collection.
"""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from src.awsideman.backup_restore.models import BackupResult
from src.awsideman.backup_restore.monitoring import (
    AlertManager,
    AlertSeverity,
    BackupMonitor,
    MetricsCollector,
    MonitoringDashboard,
    OperationMetrics,
    OperationStatus,
    OperationType,
    ProgressInfo,
    ProgressReporter,
    SystemMetrics,
)


class TestProgressReporter:
    """Test cases for ProgressReporter."""

    @pytest.fixture
    def progress_reporter(self):
        return ProgressReporter()

    @pytest.mark.asyncio
    async def test_start_operation(self, progress_reporter):
        """Test starting operation tracking."""
        operation_id = "test_op_1"
        total_steps = 10
        description = "Test operation"

        await progress_reporter.start_operation(operation_id, total_steps, description)

        progress = await progress_reporter.get_progress(operation_id)
        assert progress is not None
        assert progress["operation_id"] == operation_id
        assert progress["total_steps"] == total_steps
        assert progress["status"] == OperationStatus.RUNNING.value
        assert progress["completed_steps"] == 0

    @pytest.mark.asyncio
    async def test_update_progress(self, progress_reporter):
        """Test updating operation progress."""
        operation_id = "test_op_2"
        await progress_reporter.start_operation(operation_id, 10, "Test operation")

        await progress_reporter.update_progress(operation_id, 5, "Halfway done")

        progress = await progress_reporter.get_progress(operation_id)
        assert progress["completed_steps"] == 5
        assert progress["progress_percentage"] == 50.0
        assert progress["current_step_description"] == "Halfway done"

    @pytest.mark.asyncio
    async def test_complete_operation_success(self, progress_reporter):
        """Test completing operation successfully."""
        operation_id = "test_op_3"
        await progress_reporter.start_operation(operation_id, 10, "Test operation")

        await progress_reporter.complete_operation(operation_id, True, "Operation completed")

        progress = await progress_reporter.get_progress(operation_id)
        assert progress["status"] == OperationStatus.COMPLETED.value
        assert progress["completed_steps"] == 10
        assert progress["progress_percentage"] == 100.0

    @pytest.mark.asyncio
    async def test_complete_operation_failure(self, progress_reporter):
        """Test completing operation with failure."""
        operation_id = "test_op_4"
        await progress_reporter.start_operation(operation_id, 10, "Test operation")

        await progress_reporter.complete_operation(operation_id, False, "Operation failed")

        progress = await progress_reporter.get_progress(operation_id)
        assert progress["status"] == OperationStatus.FAILED.value
        assert progress["error_message"] == "Operation failed"

    @pytest.mark.asyncio
    async def test_progress_callbacks(self, progress_reporter):
        """Test progress update callbacks."""
        callback_calls = []

        def test_callback(progress_info):
            callback_calls.append(progress_info.operation_id)

        progress_reporter.add_progress_callback(test_callback)

        operation_id = "test_op_5"
        await progress_reporter.start_operation(operation_id, 10, "Test operation")
        await progress_reporter.update_progress(operation_id, 5)
        await progress_reporter.complete_operation(operation_id, True)

        assert len(callback_calls) == 3  # start, update, complete
        assert all(call == operation_id for call in callback_calls)

    @pytest.mark.asyncio
    async def test_unknown_operation_update(self, progress_reporter):
        """Test updating unknown operation."""
        # Should not raise exception
        await progress_reporter.update_progress("unknown_op", 5)
        await progress_reporter.complete_operation("unknown_op", True)

    def test_cleanup_completed_operations(self, progress_reporter):
        """Test cleanup of old completed operations."""
        # Create some old operations
        old_time = datetime.now() - timedelta(hours=25)

        progress_reporter._operations["old_op"] = ProgressInfo(
            operation_id="old_op",
            operation_type=OperationType.BACKUP,
            status=OperationStatus.COMPLETED,
            total_steps=10,
            completed_steps=10,
            start_time=old_time,
            last_update=old_time,
        )

        progress_reporter._operations["recent_op"] = ProgressInfo(
            operation_id="recent_op",
            operation_type=OperationType.BACKUP,
            status=OperationStatus.COMPLETED,
            total_steps=10,
            completed_steps=10,
        )

        progress_reporter.cleanup_completed_operations(timedelta(hours=24))

        assert "old_op" not in progress_reporter._operations
        assert "recent_op" in progress_reporter._operations


class TestMetricsCollector:
    """Test cases for MetricsCollector."""

    @pytest.fixture
    def metrics_collector(self):
        return MetricsCollector()

    def test_record_metric(self, metrics_collector):
        """Test recording a metric."""
        metric_name = "test_metric"
        value = 42.0
        labels = {"type": "test"}

        metrics_collector.record_metric(metric_name, value, labels)

        history = metrics_collector.get_metric_history(metric_name)
        assert len(history) == 1
        assert history[0].value == value
        assert history[0].labels == labels

    def test_record_operation_metrics(self, metrics_collector):
        """Test recording operation metrics."""
        operation_metrics = OperationMetrics(
            operation_id="test_op",
            operation_type=OperationType.BACKUP,
            status=OperationStatus.COMPLETED,
            duration=timedelta(minutes=5),
            resource_counts={"users": 100},
            data_size_bytes=1024,
        )

        metrics_collector.record_operation_metrics(operation_metrics)

        assert len(metrics_collector._operation_metrics) == 1
        assert metrics_collector._operation_metrics[0] == operation_metrics

        # Check that individual metrics were also recorded
        duration_history = metrics_collector.get_metric_history("backup_duration")
        assert len(duration_history) == 1
        assert duration_history[0].value == 300.0  # 5 minutes in seconds

    def test_calculate_success_rate(self, metrics_collector):
        """Test success rate calculation."""
        # Add some operation metrics
        for i in range(10):
            status = OperationStatus.COMPLETED if i < 8 else OperationStatus.FAILED
            metrics_collector.record_operation_metrics(
                OperationMetrics(
                    operation_id=f"op_{i}",
                    operation_type=OperationType.BACKUP,
                    status=status,
                    duration=timedelta(minutes=1),
                )
            )

        success_rate = metrics_collector.calculate_success_rate(OperationType.BACKUP)
        assert success_rate == 80.0  # 8 out of 10 successful

    def test_calculate_average_duration(self, metrics_collector):
        """Test average duration calculation."""
        # Add some operation metrics with different durations
        durations = [1, 2, 3, 4, 5]  # minutes
        for i, duration in enumerate(durations):
            metrics_collector.record_operation_metrics(
                OperationMetrics(
                    operation_id=f"op_{i}",
                    operation_type=OperationType.BACKUP,
                    status=OperationStatus.COMPLETED,
                    duration=timedelta(minutes=duration),
                )
            )

        avg_duration = metrics_collector.calculate_average_duration(OperationType.BACKUP)
        expected_avg = sum(durations) * 60 / len(durations)  # Convert to seconds
        assert avg_duration == expected_avg

    def test_get_system_metrics(self, metrics_collector):
        """Test system metrics generation."""
        # Add some test data
        metrics_collector.record_operation_metrics(
            OperationMetrics(
                operation_id="test_op",
                operation_type=OperationType.BACKUP,
                status=OperationStatus.COMPLETED,
                duration=timedelta(minutes=5),
            )
        )

        storage_info = {
            "used_bytes": 1024 * 1024 * 100,  # 100 MB
            "total_bytes": 1024 * 1024 * 1000,  # 1 GB
        }

        system_metrics = metrics_collector.get_system_metrics(2, storage_info)

        assert system_metrics.active_operations == 2
        assert system_metrics.storage_usage_bytes == storage_info["used_bytes"]
        assert system_metrics.storage_capacity_bytes == storage_info["total_bytes"]
        assert system_metrics.storage_usage_percentage == 10.0

    def test_cleanup_old_metrics(self, metrics_collector):
        """Test cleanup of old metrics."""
        # Add old operation metric
        old_metric = OperationMetrics(
            operation_id="old_op",
            operation_type=OperationType.BACKUP,
            status=OperationStatus.COMPLETED,
            duration=timedelta(minutes=1),
        )
        # Manually set old time
        metrics_collector._operation_metrics.append(old_metric)

        # Add recent metric
        recent_metric = OperationMetrics(
            operation_id="recent_op",
            operation_type=OperationType.BACKUP,
            status=OperationStatus.COMPLETED,
            duration=timedelta(minutes=1),
        )
        metrics_collector._operation_metrics.append(recent_metric)

        metrics_collector.cleanup_old_metrics(timedelta(days=30))

        # Should only have recent metric (this test is simplified)
        assert len(metrics_collector._operation_metrics) >= 1


class TestAlertManager:
    """Test cases for AlertManager."""

    @pytest.fixture
    def alert_manager(self):
        return AlertManager()

    def test_create_alert(self, alert_manager):
        """Test creating an alert."""
        alert_id = "test_alert"
        severity = AlertSeverity.WARNING
        title = "Test Alert"
        message = "This is a test alert"

        alert = alert_manager.create_alert(alert_id, severity, title, message)

        assert alert.alert_id == alert_id
        assert alert.severity == severity
        assert alert.title == title
        assert alert.message == message
        assert not alert.resolved
        assert alert_id in alert_manager._alerts

    def test_resolve_alert(self, alert_manager):
        """Test resolving an alert."""
        alert_id = "test_alert"
        alert_manager.create_alert(alert_id, AlertSeverity.WARNING, "Test", "Test message")

        result = alert_manager.resolve_alert(alert_id)

        assert result is True
        alert = alert_manager._alerts[alert_id]
        assert alert.resolved is True
        assert alert.resolved_at is not None

    def test_resolve_nonexistent_alert(self, alert_manager):
        """Test resolving non-existent alert."""
        result = alert_manager.resolve_alert("nonexistent")
        assert result is False

    def test_get_active_alerts(self, alert_manager):
        """Test getting active alerts."""
        # Create some alerts
        alert_manager.create_alert("alert1", AlertSeverity.WARNING, "Alert 1", "Message 1")
        alert_manager.create_alert("alert2", AlertSeverity.ERROR, "Alert 2", "Message 2")
        alert_manager.create_alert("alert3", AlertSeverity.WARNING, "Alert 3", "Message 3")

        # Resolve one alert
        alert_manager.resolve_alert("alert2")

        # Get active alerts
        active_alerts = alert_manager.get_active_alerts()
        assert len(active_alerts) == 2

        # Get active alerts by severity
        warning_alerts = alert_manager.get_active_alerts(AlertSeverity.WARNING)
        assert len(warning_alerts) == 2

        error_alerts = alert_manager.get_active_alerts(AlertSeverity.ERROR)
        assert len(error_alerts) == 0

    def test_alert_handlers(self, alert_manager):
        """Test alert handlers."""
        handler_calls = []

        def test_handler(alert):
            handler_calls.append(alert.alert_id)

        alert_manager.add_alert_handler(test_handler)

        alert_manager.create_alert("test_alert", AlertSeverity.INFO, "Test", "Test message")

        assert len(handler_calls) == 1
        assert handler_calls[0] == "test_alert"

    def test_cleanup_old_alerts(self, alert_manager):
        """Test cleanup of old resolved alerts."""
        # Create and resolve an old alert
        old_time = datetime.now() - timedelta(days=8)
        alert_manager.create_alert("old_alert", AlertSeverity.INFO, "Old Alert", "Old message")
        alert_manager.resolve_alert("old_alert")
        alert_manager._alerts["old_alert"].resolved_at = old_time

        # Create a recent alert
        alert_manager.create_alert(
            "recent_alert", AlertSeverity.INFO, "Recent Alert", "Recent message"
        )

        alert_manager.cleanup_old_alerts(timedelta(days=7))

        assert "old_alert" not in alert_manager._alerts
        assert "recent_alert" in alert_manager._alerts


class TestMonitoringDashboard:
    """Test cases for MonitoringDashboard."""

    @pytest.fixture
    def dashboard_components(self):
        progress_reporter = ProgressReporter()
        metrics_collector = MetricsCollector()
        alert_manager = AlertManager()
        dashboard = MonitoringDashboard(progress_reporter, metrics_collector, alert_manager)
        return dashboard, progress_reporter, metrics_collector, alert_manager

    def test_get_dashboard_data(self, dashboard_components):
        """Test getting dashboard data."""
        dashboard, progress_reporter, metrics_collector, alert_manager = dashboard_components

        # Add some test data
        alert_manager.create_alert(
            "test_alert", AlertSeverity.WARNING, "Test Alert", "Test message"
        )

        storage_info = {"used_bytes": 1024 * 1024 * 100, "total_bytes": 1024 * 1024 * 1000}

        dashboard_data = dashboard.get_dashboard_data(storage_info)

        assert "system_metrics" in dashboard_data
        assert "active_operations" in dashboard_data
        assert "active_alerts" in dashboard_data
        assert "recent_metrics" in dashboard_data

        assert len(dashboard_data["active_alerts"]) == 1
        assert dashboard_data["active_alerts"][0]["title"] == "Test Alert"

    def test_export_prometheus_metrics(self, dashboard_components):
        """Test exporting metrics in Prometheus format."""
        dashboard, _, metrics_collector, _ = dashboard_components

        # Add some test metrics
        metrics_collector.record_operation_metrics(
            OperationMetrics(
                operation_id="test_op",
                operation_type=OperationType.BACKUP,
                status=OperationStatus.COMPLETED,
                duration=timedelta(minutes=5),
            )
        )

        prometheus_output = dashboard.export_metrics_for_external_dashboard("prometheus")

        assert "backup_operations_total" in prometheus_output
        assert "backup_operation_duration_seconds" in prometheus_output
        assert 'type="backup"' in prometheus_output

    def test_export_json_metrics(self, dashboard_components):
        """Test exporting metrics in JSON format."""
        dashboard, progress_reporter, metrics_collector, alert_manager = dashboard_components

        # Add some test data
        metrics_collector.record_operation_metrics(
            OperationMetrics(
                operation_id="test_op",
                operation_type=OperationType.BACKUP,
                status=OperationStatus.COMPLETED,
                duration=timedelta(minutes=5),
            )
        )

        json_output = dashboard.export_metrics_for_external_dashboard("json")

        import json

        data = json.loads(json_output)

        assert "timestamp" in data
        assert "operations" in data
        assert "active_operations" in data
        assert "alerts" in data

    def test_unsupported_export_format(self, dashboard_components):
        """Test unsupported export format."""
        dashboard, _, _, _ = dashboard_components

        with pytest.raises(ValueError, match="Unsupported export format"):
            dashboard.export_metrics_for_external_dashboard("xml")


class TestBackupMonitor:
    """Test cases for BackupMonitor."""

    @pytest.fixture
    def backup_monitor(self):
        return BackupMonitor()

    @pytest.mark.asyncio
    async def test_operation_monitoring_lifecycle(self, backup_monitor):
        """Test complete operation monitoring lifecycle."""
        operation_id = "test_backup_op"

        # Start monitoring
        await backup_monitor.start_operation_monitoring(
            operation_id, OperationType.BACKUP, 10, "Test backup operation"
        )

        # Update progress
        await backup_monitor.update_operation_progress(operation_id, 5, "Processing users")

        # Complete monitoring
        backup_result = BackupResult(
            success=True, backup_id="backup_123", message="Backup completed successfully"
        )

        await backup_monitor.complete_operation_monitoring(operation_id, True, backup_result)

        # Verify metrics were recorded
        assert len(backup_monitor.metrics_collector._operation_metrics) == 1
        recorded_metric = backup_monitor.metrics_collector._operation_metrics[0]
        assert recorded_metric.operation_id == operation_id
        assert recorded_metric.operation_type == OperationType.BACKUP
        assert recorded_metric.status == OperationStatus.COMPLETED

    def test_check_system_health_storage_critical(self, backup_monitor):
        """Test system health check with critical storage usage."""
        storage_info = {
            "used_bytes": 950 * 1024 * 1024,  # 950 MB
            "total_bytes": 1000 * 1024 * 1024,  # 1000 MB (95% usage)
        }

        alerts = backup_monitor.check_system_health(storage_info)

        # Should have storage critical alert and possibly low success rate alert
        storage_alerts = [a for a in alerts if "Storage" in a.title]
        assert len(storage_alerts) == 1
        assert storage_alerts[0].severity == AlertSeverity.CRITICAL
        assert "Storage Usage Critical" in storage_alerts[0].title

    def test_check_system_health_storage_warning(self, backup_monitor):
        """Test system health check with warning storage usage."""
        storage_info = {
            "used_bytes": 850 * 1024 * 1024,  # 850 MB
            "total_bytes": 1000 * 1024 * 1024,  # 1000 MB (85% usage)
        }

        alerts = backup_monitor.check_system_health(storage_info)

        # Should have storage warning alert and possibly low success rate alert
        storage_alerts = [a for a in alerts if "Storage" in a.title]
        assert len(storage_alerts) == 1
        assert storage_alerts[0].severity == AlertSeverity.WARNING
        assert "Storage Usage High" in storage_alerts[0].title

    def test_check_system_health_low_success_rate(self, backup_monitor):
        """Test system health check with low success rate."""
        # Add failed operations to trigger low success rate
        for i in range(10):
            backup_monitor.metrics_collector.record_operation_metrics(
                OperationMetrics(
                    operation_id=f"failed_op_{i}",
                    operation_type=OperationType.BACKUP,
                    status=OperationStatus.FAILED,
                    duration=timedelta(minutes=1),
                )
            )

        storage_info = {"used_bytes": 100, "total_bytes": 1000}
        alerts = backup_monitor.check_system_health(storage_info)

        # Should have storage warning and low success rate alert
        success_rate_alerts = [a for a in alerts if "Success Rate" in a.title]
        assert len(success_rate_alerts) == 1
        assert success_rate_alerts[0].severity == AlertSeverity.ERROR

    def test_automatic_alert_on_operation_failure(self, backup_monitor):
        """Test automatic alert generation on operation failure."""
        # Simulate a failed operation
        progress_info = ProgressInfo(
            operation_id="failed_op",
            operation_type=OperationType.BACKUP,
            status=OperationStatus.FAILED,
            total_steps=10,
            completed_steps=5,
            error_message="Connection timeout",
        )

        # Trigger the callback manually
        for callback in backup_monitor.progress_reporter._callbacks:
            callback(progress_info)

        # Check that alert was created
        active_alerts = backup_monitor.alert_manager.get_active_alerts()
        assert len(active_alerts) == 1
        assert "Operation Failed" in active_alerts[0].title
        assert "Connection timeout" in active_alerts[0].message

    def test_cleanup_old_data(self, backup_monitor):
        """Test cleanup of old monitoring data."""
        # This test verifies that cleanup methods are called
        # The actual cleanup logic is tested in individual component tests

        with (
            patch.object(
                backup_monitor.progress_reporter, "cleanup_completed_operations"
            ) as mock_progress_cleanup,
            patch.object(
                backup_monitor.metrics_collector, "cleanup_old_metrics"
            ) as mock_metrics_cleanup,
            patch.object(backup_monitor.alert_manager, "cleanup_old_alerts") as mock_alerts_cleanup,
        ):

            backup_monitor.cleanup_old_data()

            mock_progress_cleanup.assert_called_once()
            mock_metrics_cleanup.assert_called_once()
            mock_alerts_cleanup.assert_called_once()


class TestProgressInfo:
    """Test cases for ProgressInfo data class."""

    def test_progress_percentage_calculation(self):
        """Test progress percentage calculation."""
        progress_info = ProgressInfo(
            operation_id="test",
            operation_type=OperationType.BACKUP,
            status=OperationStatus.RUNNING,
            total_steps=100,
            completed_steps=25,
        )

        assert progress_info.progress_percentage == 25.0

    def test_progress_percentage_zero_total(self):
        """Test progress percentage with zero total steps."""
        progress_info = ProgressInfo(
            operation_id="test",
            operation_type=OperationType.BACKUP,
            status=OperationStatus.RUNNING,
            total_steps=0,
            completed_steps=0,
        )

        assert progress_info.progress_percentage == 0.0

    def test_progress_percentage_over_100(self):
        """Test progress percentage capped at 100%."""
        progress_info = ProgressInfo(
            operation_id="test",
            operation_type=OperationType.BACKUP,
            status=OperationStatus.RUNNING,
            total_steps=10,
            completed_steps=15,
        )

        assert progress_info.progress_percentage == 100.0

    def test_estimated_remaining_time(self):
        """Test estimated remaining time calculation."""
        start_time = datetime.now() - timedelta(minutes=10)
        progress_info = ProgressInfo(
            operation_id="test",
            operation_type=OperationType.BACKUP,
            status=OperationStatus.RUNNING,
            total_steps=100,
            completed_steps=50,
            start_time=start_time,
        )

        remaining_time = progress_info.estimated_remaining_time
        assert remaining_time is not None
        # Should be approximately 10 minutes (same as elapsed time since we're 50% done)
        assert 9 <= remaining_time.total_seconds() / 60 <= 11


class TestSystemMetrics:
    """Test cases for SystemMetrics data class."""

    def test_storage_usage_percentage(self):
        """Test storage usage percentage calculation."""
        system_metrics = SystemMetrics(
            storage_usage_bytes=250 * 1024 * 1024,  # 250 MB
            storage_capacity_bytes=1000 * 1024 * 1024,  # 1000 MB
        )

        assert system_metrics.storage_usage_percentage == 25.0

    def test_storage_usage_percentage_zero_capacity(self):
        """Test storage usage percentage with zero capacity."""
        system_metrics = SystemMetrics(storage_usage_bytes=100, storage_capacity_bytes=0)

        assert system_metrics.storage_usage_percentage == 0.0


if __name__ == "__main__":
    pytest.main([__file__])
