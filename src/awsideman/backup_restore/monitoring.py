"""
Monitoring and metrics collection for backup and restore operations.

This module provides comprehensive monitoring capabilities including progress tracking,
metrics collection, alerting, and dashboard integration for backup-restore operations.
"""

import json
import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .interfaces import ProgressReporterInterface
from .models import BackupResult, RestoreResult


class OperationType(Enum):
    """Types of operations that can be monitored."""

    BACKUP = "backup"
    RESTORE = "restore"
    VALIDATION = "validation"
    EXPORT = "export"
    IMPORT = "import"
    CLEANUP = "cleanup"


class OperationStatus(Enum):
    """Status of monitored operations."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AlertSeverity(Enum):
    """Severity levels for alerts."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ProgressInfo:
    """Information about operation progress."""

    operation_id: str
    operation_type: OperationType
    status: OperationStatus
    total_steps: int
    completed_steps: int
    current_step_description: str = ""
    start_time: datetime = field(default_factory=datetime.now)
    last_update: datetime = field(default_factory=datetime.now)
    estimated_completion: Optional[datetime] = None
    error_message: Optional[str] = None

    @property
    def progress_percentage(self) -> float:
        """Calculate progress as percentage."""
        if self.total_steps == 0:
            return 0.0
        return min(100.0, (self.completed_steps / self.total_steps) * 100.0)

    @property
    def elapsed_time(self) -> timedelta:
        """Calculate elapsed time since operation start."""
        return datetime.now() - self.start_time

    @property
    def estimated_remaining_time(self) -> Optional[timedelta]:
        """Estimate remaining time based on current progress."""
        if self.completed_steps == 0 or self.total_steps == 0:
            return None

        elapsed = self.elapsed_time
        progress_ratio = self.completed_steps / self.total_steps

        if progress_ratio > 0:
            total_estimated = elapsed / progress_ratio
            return total_estimated - elapsed

        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "operation_id": self.operation_id,
            "operation_type": self.operation_type.value,
            "status": self.status.value,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "current_step_description": self.current_step_description,
            "start_time": self.start_time.isoformat(),
            "last_update": self.last_update.isoformat(),
            "estimated_completion": (
                self.estimated_completion.isoformat() if self.estimated_completion else None
            ),
            "error_message": self.error_message,
            "progress_percentage": self.progress_percentage,
            "elapsed_time": self.elapsed_time.total_seconds(),
            "estimated_remaining_time": (
                self.estimated_remaining_time.total_seconds()
                if self.estimated_remaining_time
                else None
            ),
        }


@dataclass
class MetricPoint:
    """A single metric data point."""

    timestamp: datetime
    value: float
    labels: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {"timestamp": self.timestamp.isoformat(), "value": self.value, "labels": self.labels}


@dataclass
class OperationMetrics:
    """Metrics for a completed operation."""

    operation_id: str
    operation_type: OperationType
    status: OperationStatus
    duration: timedelta
    resource_counts: Dict[str, int] = field(default_factory=dict)
    data_size_bytes: int = 0
    error_count: int = 0
    warning_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "operation_id": self.operation_id,
            "operation_type": self.operation_type.value,
            "status": self.status.value,
            "duration": self.duration.total_seconds(),
            "resource_counts": self.resource_counts,
            "data_size_bytes": self.data_size_bytes,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
        }


@dataclass
class Alert:
    """Alert for monitoring events."""

    alert_id: str
    severity: AlertSeverity
    title: str
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    operation_id: Optional[str] = None
    labels: Dict[str, str] = field(default_factory=dict)
    resolved: bool = False
    resolved_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "alert_id": self.alert_id,
            "severity": self.severity.value,
            "title": self.title,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "operation_id": self.operation_id,
            "labels": self.labels,
            "resolved": self.resolved,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


@dataclass
class SystemMetrics:
    """System-wide metrics for monitoring."""

    timestamp: datetime = field(default_factory=datetime.now)
    active_operations: int = 0
    total_operations_today: int = 0
    success_rate_24h: float = 0.0
    average_backup_duration: float = 0.0
    average_restore_duration: float = 0.0
    storage_usage_bytes: int = 0
    storage_capacity_bytes: int = 0
    failed_operations_24h: int = 0

    @property
    def storage_usage_percentage(self) -> float:
        """Calculate storage usage as percentage."""
        if self.storage_capacity_bytes == 0:
            return 0.0
        return (self.storage_usage_bytes / self.storage_capacity_bytes) * 100.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "active_operations": self.active_operations,
            "total_operations_today": self.total_operations_today,
            "success_rate_24h": self.success_rate_24h,
            "average_backup_duration": self.average_backup_duration,
            "average_restore_duration": self.average_restore_duration,
            "storage_usage_bytes": self.storage_usage_bytes,
            "storage_capacity_bytes": self.storage_capacity_bytes,
            "storage_usage_percentage": self.storage_usage_percentage,
            "failed_operations_24h": self.failed_operations_24h,
        }


class ProgressReporter(ProgressReporterInterface):
    """Implementation of progress reporting for backup-restore operations."""

    def __init__(self):
        self._operations: Dict[str, ProgressInfo] = {}
        self._callbacks: List[Callable[[ProgressInfo], None]] = []
        self._logger = logging.getLogger(__name__)

    async def start_operation(
        self,
        operation_id: str,
        total_steps: int,
        description: str,
        operation_type: OperationType = OperationType.BACKUP,
    ) -> None:
        """Start tracking progress for an operation."""
        progress_info = ProgressInfo(
            operation_id=operation_id,
            operation_type=operation_type,
            status=OperationStatus.RUNNING,
            total_steps=total_steps,
            completed_steps=0,
            current_step_description=description,
        )

        self._operations[operation_id] = progress_info
        self._logger.info(f"Started operation {operation_id}: {description}")

        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(progress_info)
            except Exception as e:
                self._logger.error(f"Error in progress callback: {e}")

    async def update_progress(
        self, operation_id: str, completed_steps: int, message: Optional[str] = None
    ) -> None:
        """Update progress for an operation."""
        if operation_id not in self._operations:
            self._logger.warning(f"Unknown operation ID: {operation_id}")
            return

        progress_info = self._operations[operation_id]
        progress_info.completed_steps = completed_steps
        progress_info.last_update = datetime.now()

        if message:
            progress_info.current_step_description = message

        # Update estimated completion time
        if progress_info.completed_steps > 0:
            remaining_time = progress_info.estimated_remaining_time
            if remaining_time:
                progress_info.estimated_completion = datetime.now() + remaining_time

        self._logger.debug(
            f"Progress update for {operation_id}: {progress_info.progress_percentage:.1f}%"
        )

        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(progress_info)
            except Exception as e:
                self._logger.error(f"Error in progress callback: {e}")

    async def complete_operation(
        self, operation_id: str, success: bool, message: Optional[str] = None
    ) -> None:
        """Mark an operation as complete."""
        if operation_id not in self._operations:
            self._logger.warning(f"Unknown operation ID: {operation_id}")
            return

        progress_info = self._operations[operation_id]
        progress_info.status = OperationStatus.COMPLETED if success else OperationStatus.FAILED
        progress_info.last_update = datetime.now()

        if not success and message:
            progress_info.error_message = message

        if success:
            progress_info.completed_steps = progress_info.total_steps

        self._logger.info(f"Operation {operation_id} {'completed' if success else 'failed'}")

        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(progress_info)
            except Exception as e:
                self._logger.error(f"Error in progress callback: {e}")

    async def get_progress(self, operation_id: str) -> Optional[Dict[str, Any]]:
        """Get current progress for an operation."""
        if operation_id not in self._operations:
            return None

        return self._operations[operation_id].to_dict()

    def add_progress_callback(self, callback: Callable[[ProgressInfo], None]) -> None:
        """Add a callback to be notified of progress updates."""
        self._callbacks.append(callback)

    def remove_progress_callback(self, callback: Callable[[ProgressInfo], None]) -> None:
        """Remove a progress callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def get_all_operations(self) -> Dict[str, Dict[str, Any]]:
        """Get progress information for all operations."""
        return {op_id: info.to_dict() for op_id, info in self._operations.items()}

    def cleanup_completed_operations(self, max_age: timedelta = timedelta(hours=24)) -> None:
        """Clean up old completed operations."""
        cutoff_time = datetime.now() - max_age
        to_remove = []

        for op_id, info in self._operations.items():
            if info.status in [OperationStatus.COMPLETED, OperationStatus.FAILED]:
                if info.last_update < cutoff_time:
                    to_remove.append(op_id)

        for op_id in to_remove:
            del self._operations[op_id]
            self._logger.debug(f"Cleaned up old operation: {op_id}")


class MetricsCollector:
    """Collects and aggregates metrics for backup-restore operations."""

    def __init__(self, max_history_size: int = 10000):
        self._metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history_size))
        self._operation_metrics: List[OperationMetrics] = []
        self._logger = logging.getLogger(__name__)

    def record_metric(
        self, metric_name: str, value: float, labels: Optional[Dict[str, str]] = None
    ) -> None:
        """Record a metric value."""
        metric_point = MetricPoint(timestamp=datetime.now(), value=value, labels=labels or {})

        self._metrics[metric_name].append(metric_point)
        self._logger.debug(f"Recorded metric {metric_name}: {value}")

    def record_operation_metrics(self, metrics: OperationMetrics) -> None:
        """Record metrics for a completed operation."""
        self._operation_metrics.append(metrics)

        # Also record individual metrics
        self.record_metric(
            f"{metrics.operation_type.value}_duration",
            metrics.duration.total_seconds(),
            {"status": metrics.status.value},
        )

        self.record_metric(
            f"{metrics.operation_type.value}_data_size",
            metrics.data_size_bytes,
            {"status": metrics.status.value},
        )

        if metrics.error_count > 0:
            self.record_metric(f"{metrics.operation_type.value}_errors", metrics.error_count)

    def get_metric_history(
        self, metric_name: str, since: Optional[datetime] = None
    ) -> List[MetricPoint]:
        """Get historical values for a metric."""
        if metric_name not in self._metrics:
            return []

        metrics = list(self._metrics[metric_name])

        if since:
            metrics = [m for m in metrics if m.timestamp >= since]

        return metrics

    def calculate_success_rate(
        self, operation_type: OperationType, time_window: timedelta = timedelta(hours=24)
    ) -> float:
        """Calculate success rate for operations within a time window."""
        cutoff_time = datetime.now() - time_window

        relevant_ops = [
            op
            for op in self._operation_metrics
            if op.operation_type == operation_type and (datetime.now() - op.duration) >= cutoff_time
        ]

        if not relevant_ops:
            return 0.0

        successful_ops = [op for op in relevant_ops if op.status == OperationStatus.COMPLETED]
        return len(successful_ops) / len(relevant_ops) * 100.0

    def calculate_average_duration(
        self, operation_type: OperationType, time_window: timedelta = timedelta(hours=24)
    ) -> float:
        """Calculate average operation duration within a time window."""
        cutoff_time = datetime.now() - time_window

        relevant_ops = [
            op
            for op in self._operation_metrics
            if op.operation_type == operation_type
            and op.status == OperationStatus.COMPLETED
            and (datetime.now() - op.duration) >= cutoff_time
        ]

        if not relevant_ops:
            return 0.0

        total_duration = sum(op.duration.total_seconds() for op in relevant_ops)
        return total_duration / len(relevant_ops)

    def get_system_metrics(
        self, active_operations: int, storage_info: Dict[str, Any]
    ) -> SystemMetrics:
        """Generate current system metrics."""
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        last_24h = now - timedelta(hours=24)

        # Count operations from today
        today_ops = [op for op in self._operation_metrics if (now - op.duration) >= today_start]

        # Count failed operations in last 24h
        failed_24h = [
            op
            for op in self._operation_metrics
            if op.status == OperationStatus.FAILED and (now - op.duration) >= last_24h
        ]

        return SystemMetrics(
            timestamp=now,
            active_operations=active_operations,
            total_operations_today=len(today_ops),
            success_rate_24h=self.calculate_success_rate(OperationType.BACKUP, timedelta(hours=24)),
            average_backup_duration=self.calculate_average_duration(OperationType.BACKUP),
            average_restore_duration=self.calculate_average_duration(OperationType.RESTORE),
            storage_usage_bytes=storage_info.get("used_bytes", 0),
            storage_capacity_bytes=storage_info.get("total_bytes", 0),
            failed_operations_24h=len(failed_24h),
        )

    def cleanup_old_metrics(self, max_age: timedelta = timedelta(days=30)) -> None:
        """Clean up old metrics to prevent memory growth."""
        cutoff_time = datetime.now() - max_age

        # Clean up operation metrics
        self._operation_metrics = [
            op for op in self._operation_metrics if (datetime.now() - op.duration) >= cutoff_time
        ]

        # Clean up metric points
        for metric_name, points in self._metrics.items():
            # Convert to list, filter, and recreate deque
            filtered_points = [p for p in points if p.timestamp >= cutoff_time]
            self._metrics[metric_name] = deque(filtered_points, maxlen=points.maxlen)


class AlertManager:
    """Manages alerts for backup-restore operations."""

    def __init__(self):
        self._alerts: Dict[str, Alert] = {}
        self._alert_handlers: List[Callable[[Alert], None]] = []
        self._logger = logging.getLogger(__name__)

    def create_alert(
        self,
        alert_id: str,
        severity: AlertSeverity,
        title: str,
        message: str,
        operation_id: Optional[str] = None,
        labels: Optional[Dict[str, str]] = None,
    ) -> Alert:
        """Create a new alert."""
        alert = Alert(
            alert_id=alert_id,
            severity=severity,
            title=title,
            message=message,
            operation_id=operation_id,
            labels=labels or {},
        )

        self._alerts[alert_id] = alert
        self._logger.warning(f"Alert created: {title} - {message}")

        # Notify handlers
        for handler in self._alert_handlers:
            try:
                handler(alert)
            except Exception as e:
                self._logger.error(f"Error in alert handler: {e}")

        return alert

    def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an alert."""
        if alert_id not in self._alerts:
            return False

        alert = self._alerts[alert_id]
        alert.resolved = True
        alert.resolved_at = datetime.now()

        self._logger.info(f"Alert resolved: {alert.title}")
        return True

    def get_active_alerts(self, severity: Optional[AlertSeverity] = None) -> List[Alert]:
        """Get all active (unresolved) alerts."""
        alerts = [alert for alert in self._alerts.values() if not alert.resolved]

        if severity:
            alerts = [alert for alert in alerts if alert.severity == severity]

        return sorted(alerts, key=lambda a: a.timestamp, reverse=True)

    def add_alert_handler(self, handler: Callable[[Alert], None]) -> None:
        """Add an alert handler."""
        self._alert_handlers.append(handler)

    def remove_alert_handler(self, handler: Callable[[Alert], None]) -> None:
        """Remove an alert handler."""
        if handler in self._alert_handlers:
            self._alert_handlers.remove(handler)

    def cleanup_old_alerts(self, max_age: timedelta = timedelta(days=7)) -> None:
        """Clean up old resolved alerts."""
        cutoff_time = datetime.now() - max_age
        to_remove = []

        for alert_id, alert in self._alerts.items():
            if alert.resolved and alert.resolved_at and alert.resolved_at < cutoff_time:
                to_remove.append(alert_id)

        for alert_id in to_remove:
            del self._alerts[alert_id]
            self._logger.debug(f"Cleaned up old alert: {alert_id}")


class MonitoringDashboard:
    """Dashboard integration for monitoring backup-restore operations."""

    def __init__(
        self,
        progress_reporter: ProgressReporter,
        metrics_collector: MetricsCollector,
        alert_manager: AlertManager,
    ):
        self.progress_reporter = progress_reporter
        self.metrics_collector = metrics_collector
        self.alert_manager = alert_manager
        self._logger = logging.getLogger(__name__)

    def get_dashboard_data(self, storage_info: Dict[str, Any]) -> Dict[str, Any]:
        """Get comprehensive dashboard data."""
        active_operations = len(
            [
                op
                for op in self.progress_reporter.get_all_operations().values()
                if op["status"] == OperationStatus.RUNNING.value
            ]
        )

        system_metrics = self.metrics_collector.get_system_metrics(active_operations, storage_info)
        active_alerts = self.alert_manager.get_active_alerts()

        return {
            "system_metrics": system_metrics.to_dict(),
            "active_operations": self.progress_reporter.get_all_operations(),
            "active_alerts": [alert.to_dict() for alert in active_alerts],
            "recent_metrics": {
                "backup_success_rate": system_metrics.success_rate_24h,
                "average_backup_duration": system_metrics.average_backup_duration,
                "average_restore_duration": system_metrics.average_restore_duration,
                "storage_usage_percentage": system_metrics.storage_usage_percentage,
            },
        }

    def export_metrics_for_external_dashboard(self, format_type: str = "prometheus") -> str:
        """Export metrics in format suitable for external dashboards."""
        if format_type.lower() == "prometheus":
            return self._export_prometheus_metrics()
        elif format_type.lower() == "json":
            return self._export_json_metrics()
        else:
            raise ValueError(f"Unsupported export format: {format_type}")

    def _export_prometheus_metrics(self) -> str:
        """Export metrics in Prometheus format."""
        lines = []

        # Add help and type information
        lines.append("# HELP backup_operations_total Total number of backup operations")
        lines.append("# TYPE backup_operations_total counter")

        # Export operation counts by type and status
        operation_counts = defaultdict(int)
        for op in self.metrics_collector._operation_metrics:
            key = f"{op.operation_type.value}_{op.status.value}"
            operation_counts[key] += 1

        for key, count in operation_counts.items():
            op_type, status = key.rsplit("_", 1)
            lines.append(f'backup_operations_total{{type="{op_type}",status="{status}"}} {count}')

        # Export duration metrics
        lines.append("# HELP backup_operation_duration_seconds Duration of backup operations")
        lines.append("# TYPE backup_operation_duration_seconds histogram")

        for op in self.metrics_collector._operation_metrics[-100:]:  # Last 100 operations
            duration = op.duration.total_seconds()
            lines.append(
                f'backup_operation_duration_seconds{{type="{op.operation_type.value}"}} {duration}'
            )

        return "\n".join(lines)

    def _export_json_metrics(self) -> str:
        """Export metrics in JSON format."""
        metrics_data = {
            "timestamp": datetime.now().isoformat(),
            "operations": [op.to_dict() for op in self.metrics_collector._operation_metrics],
            "active_operations": self.progress_reporter.get_all_operations(),
            "alerts": [alert.to_dict() for alert in self.alert_manager.get_active_alerts()],
        }

        return json.dumps(metrics_data, indent=2)


class BackupMonitor:
    """Main monitoring coordinator for backup-restore operations."""

    def __init__(self):
        self.progress_reporter = ProgressReporter()
        self.metrics_collector = MetricsCollector()
        self.alert_manager = AlertManager()
        self.dashboard = MonitoringDashboard(
            self.progress_reporter, self.metrics_collector, self.alert_manager
        )
        self._logger = logging.getLogger(__name__)

        # Set up automatic alerting based on metrics
        self._setup_automatic_alerts()

    def _setup_automatic_alerts(self) -> None:
        """Set up automatic alert generation based on metrics."""

        # Add progress callback to detect failed operations
        def on_progress_update(progress_info: ProgressInfo):
            if progress_info.status == OperationStatus.FAILED:
                self.alert_manager.create_alert(
                    alert_id=f"operation_failed_{progress_info.operation_id}",
                    severity=AlertSeverity.ERROR,
                    title=f"{progress_info.operation_type.value.title()} Operation Failed",
                    message=f"Operation {progress_info.operation_id} failed: {progress_info.error_message}",
                    operation_id=progress_info.operation_id,
                )

        self.progress_reporter.add_progress_callback(on_progress_update)

    async def start_operation_monitoring(
        self, operation_id: str, operation_type: OperationType, total_steps: int, description: str
    ) -> None:
        """Start monitoring an operation."""
        await self.progress_reporter.start_operation(
            operation_id, total_steps, description, operation_type
        )

    async def update_operation_progress(
        self, operation_id: str, completed_steps: int, message: Optional[str] = None
    ) -> None:
        """Update operation progress."""
        await self.progress_reporter.update_progress(operation_id, completed_steps, message)

    async def complete_operation_monitoring(
        self, operation_id: str, success: bool, result: Optional[Any] = None
    ) -> None:
        """Complete operation monitoring and record metrics."""
        await self.progress_reporter.complete_operation(operation_id, success)

        # Record operation metrics
        progress_info = self.progress_reporter._operations.get(operation_id)
        if progress_info:
            metrics = OperationMetrics(
                operation_id=operation_id,
                operation_type=progress_info.operation_type,
                status=progress_info.status,
                duration=progress_info.elapsed_time,
                resource_counts=self._extract_resource_counts(result),
                data_size_bytes=self._extract_data_size(result),
                error_count=1 if not success else 0,
                warning_count=self._extract_warning_count(result),
            )

            self.metrics_collector.record_operation_metrics(metrics)

    def _extract_resource_counts(self, result: Optional[Any]) -> Dict[str, int]:
        """Extract resource counts from operation result."""
        if isinstance(result, BackupResult) and result.metadata:
            return result.metadata.resource_counts
        elif isinstance(result, RestoreResult):
            return result.changes_applied
        return {}

    def _extract_data_size(self, result: Optional[Any]) -> int:
        """Extract data size from operation result."""
        if isinstance(result, BackupResult) and result.metadata:
            return result.metadata.size_bytes
        return 0

    def _extract_warning_count(self, result: Optional[Any]) -> int:
        """Extract warning count from operation result."""
        if hasattr(result, "warnings"):
            return len(result.warnings)
        return 0

    def check_system_health(self, storage_info: Dict[str, Any]) -> List[Alert]:
        """Check system health and generate alerts if needed."""
        alerts = []

        # Check storage usage
        if storage_info.get("total_bytes", 0) > 0:
            usage_percentage = (
                storage_info.get("used_bytes", 0) / storage_info["total_bytes"]
            ) * 100

            if usage_percentage > 90:
                alert = self.alert_manager.create_alert(
                    alert_id="storage_critical",
                    severity=AlertSeverity.CRITICAL,
                    title="Storage Usage Critical",
                    message=f"Storage usage is at {usage_percentage:.1f}%",
                )
                alerts.append(alert)
            elif usage_percentage > 80:
                alert = self.alert_manager.create_alert(
                    alert_id="storage_warning",
                    severity=AlertSeverity.WARNING,
                    title="Storage Usage High",
                    message=f"Storage usage is at {usage_percentage:.1f}%",
                )
                alerts.append(alert)

        # Check success rate
        success_rate = self.metrics_collector.calculate_success_rate(
            OperationType.BACKUP, timedelta(hours=24)
        )

        if success_rate < 50:
            alert = self.alert_manager.create_alert(
                alert_id="low_success_rate",
                severity=AlertSeverity.ERROR,
                title="Low Backup Success Rate",
                message=f"Backup success rate in last 24h is {success_rate:.1f}%",
            )
            alerts.append(alert)

        return alerts

    def cleanup_old_data(self) -> None:
        """Clean up old monitoring data."""
        self.progress_reporter.cleanup_completed_operations()
        self.metrics_collector.cleanup_old_metrics()
        self.alert_manager.cleanup_old_alerts()
        self._logger.info("Cleaned up old monitoring data")
