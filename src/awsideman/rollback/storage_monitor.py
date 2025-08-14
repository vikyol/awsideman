"""Storage monitoring and alerting for rollback operations."""

import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from rich.console import Console

console = Console()


@dataclass
class StorageAlert:
    """Storage alert information."""

    alert_type: str
    severity: str  # "info", "warning", "error", "critical"
    message: str
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "alert_type": self.alert_type,
            "severity": self.severity,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StorageAlert":
        """Create from dictionary."""
        return cls(
            alert_type=data["alert_type"],
            severity=data["severity"],
            message=data["message"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {}),
        )


@dataclass
class StorageMetrics:
    """Storage metrics snapshot."""

    timestamp: datetime
    total_operations: int
    total_rollbacks: int
    operations_file_size: int
    rollbacks_file_size: int
    index_file_size: int
    total_storage_size: int
    compression_ratio: Optional[float] = None
    index_memory_usage: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_operations": self.total_operations,
            "total_rollbacks": self.total_rollbacks,
            "operations_file_size": self.operations_file_size,
            "rollbacks_file_size": self.rollbacks_file_size,
            "index_file_size": self.index_file_size,
            "total_storage_size": self.total_storage_size,
            "compression_ratio": self.compression_ratio,
            "index_memory_usage": self.index_memory_usage,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StorageMetrics":
        """Create from dictionary."""
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            total_operations=data["total_operations"],
            total_rollbacks=data["total_rollbacks"],
            operations_file_size=data["operations_file_size"],
            rollbacks_file_size=data["rollbacks_file_size"],
            index_file_size=data["index_file_size"],
            total_storage_size=data["total_storage_size"],
            compression_ratio=data.get("compression_ratio"),
            index_memory_usage=data.get("index_memory_usage", 0),
        )


class StorageMonitor:
    """Monitor storage usage and generate alerts."""

    def __init__(
        self,
        storage_directory: Optional[str] = None,
        alert_handlers: Optional[List[Callable[[StorageAlert], None]]] = None,
        monitoring_interval: int = 300,  # 5 minutes
    ):
        """Initialize storage monitor.

        Args:
            storage_directory: Directory to monitor
            alert_handlers: List of functions to handle alerts
            monitoring_interval: Monitoring interval in seconds
        """
        if storage_directory:
            self.storage_dir = Path(storage_directory).expanduser()
        else:
            self.storage_dir = Path.home() / ".awsideman" / "operations"

        self.alert_handlers = alert_handlers or [self._default_alert_handler]
        self.monitoring_interval = monitoring_interval

        # Monitoring state
        self._monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Alert history
        self.alerts_file = self.storage_dir / "storage_alerts.json"
        self.metrics_file = self.storage_dir / "storage_metrics.json"

        # Thresholds
        self.thresholds = {
            "max_file_size_mb": 100,
            "max_total_size_mb": 500,
            "max_operations": 50000,
            "min_compression_ratio": 0.3,
            "max_index_memory_mb": 50,
        }

        # Ensure directory exists
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _default_alert_handler(self, alert: StorageAlert) -> None:
        """Default alert handler that prints to console."""
        color_map = {
            "info": "blue",
            "warning": "yellow",
            "error": "red",
            "critical": "bold red",
        }

        color = color_map.get(alert.severity, "white")
        console.print(
            f"[{color}]Storage Alert ({alert.severity.upper()}): {alert.message}[/{color}]"
        )

    def set_thresholds(self, **thresholds) -> None:
        """Update monitoring thresholds."""
        self.thresholds.update(thresholds)

    def add_alert_handler(self, handler: Callable[[StorageAlert], None]) -> None:
        """Add an alert handler."""
        self.alert_handlers.append(handler)

    def start_monitoring(self) -> None:
        """Start background monitoring."""
        with self._lock:
            if self._monitoring:
                return

            self._monitoring = True
            self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._monitor_thread.start()

    def stop_monitoring(self) -> None:
        """Stop background monitoring."""
        with self._lock:
            self._monitoring = False
            if self._monitor_thread:
                self._monitor_thread.join(timeout=5)
                self._monitor_thread = None

    def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._monitoring:
            try:
                self.check_storage_health()
                time.sleep(self.monitoring_interval)
            except Exception as e:
                self._emit_alert(
                    "monitoring_error",
                    "error",
                    f"Storage monitoring error: {str(e)}",
                    {"error_type": type(e).__name__},
                )
                time.sleep(self.monitoring_interval)

    def check_storage_health(self) -> List[StorageAlert]:
        """Check storage health and return any alerts."""
        alerts = []

        try:
            # Collect current metrics
            metrics = self._collect_metrics()

            # Check file sizes
            if metrics.operations_file_size > self.thresholds["max_file_size_mb"] * 1024 * 1024:
                alerts.append(
                    self._create_alert(
                        "large_operations_file",
                        "warning",
                        f"Operations file is large: {metrics.operations_file_size / 1024 / 1024:.1f}MB",
                        {"file_size_mb": metrics.operations_file_size / 1024 / 1024},
                    )
                )

            if metrics.rollbacks_file_size > self.thresholds["max_file_size_mb"] * 1024 * 1024:
                alerts.append(
                    self._create_alert(
                        "large_rollbacks_file",
                        "warning",
                        f"Rollbacks file is large: {metrics.rollbacks_file_size / 1024 / 1024:.1f}MB",
                        {"file_size_mb": metrics.rollbacks_file_size / 1024 / 1024},
                    )
                )

            # Check total storage size
            if metrics.total_storage_size > self.thresholds["max_total_size_mb"] * 1024 * 1024:
                alerts.append(
                    self._create_alert(
                        "high_storage_usage",
                        "error",
                        f"Total storage usage is high: {metrics.total_storage_size / 1024 / 1024:.1f}MB",
                        {"total_size_mb": metrics.total_storage_size / 1024 / 1024},
                    )
                )

            # Check operation count
            if metrics.total_operations > self.thresholds["max_operations"]:
                alerts.append(
                    self._create_alert(
                        "high_operation_count",
                        "warning",
                        f"High number of operations: {metrics.total_operations}",
                        {"operation_count": metrics.total_operations},
                    )
                )

            # Check compression ratio
            if (
                metrics.compression_ratio is not None
                and metrics.compression_ratio > self.thresholds["min_compression_ratio"]
            ):
                alerts.append(
                    self._create_alert(
                        "poor_compression",
                        "info",
                        f"Poor compression ratio: {metrics.compression_ratio:.2f}",
                        {"compression_ratio": metrics.compression_ratio},
                    )
                )

            # Check index memory usage
            if metrics.index_memory_usage > self.thresholds["max_index_memory_mb"] * 1024 * 1024:
                alerts.append(
                    self._create_alert(
                        "high_index_memory",
                        "warning",
                        f"High index memory usage: {metrics.index_memory_usage / 1024 / 1024:.1f}MB",
                        {"memory_usage_mb": metrics.index_memory_usage / 1024 / 1024},
                    )
                )

            # Check disk space
            disk_usage = self._get_disk_usage()
            if disk_usage and disk_usage["free_percent"] < 10:
                alerts.append(
                    self._create_alert(
                        "low_disk_space",
                        "critical",
                        f"Low disk space: {disk_usage['free_percent']:.1f}% free",
                        disk_usage,
                    )
                )

            # Store metrics
            self._store_metrics(metrics)

            # Emit alerts
            for alert in alerts:
                self._emit_alert_object(alert)

        except Exception as e:
            error_alert = self._create_alert(
                "health_check_error",
                "error",
                f"Health check failed: {str(e)}",
                {"error_type": type(e).__name__},
            )
            alerts.append(error_alert)
            self._emit_alert_object(error_alert)

        return alerts

    def _collect_metrics(self) -> StorageMetrics:
        """Collect current storage metrics."""
        operations_file = self.storage_dir / "operations.json"
        operations_gz_file = self.storage_dir / "operations.json.gz"
        rollbacks_file = self.storage_dir / "rollbacks.json"
        rollbacks_gz_file = self.storage_dir / "rollbacks.json.gz"
        index_file = self.storage_dir / "operation_index.json"

        # Get file sizes
        operations_size = 0
        if operations_file.exists():
            operations_size = operations_file.stat().st_size
        elif operations_gz_file.exists():
            operations_size = operations_gz_file.stat().st_size

        rollbacks_size = 0
        if rollbacks_file.exists():
            rollbacks_size = rollbacks_file.stat().st_size
        elif rollbacks_gz_file.exists():
            rollbacks_size = rollbacks_gz_file.stat().st_size

        index_size = index_file.stat().st_size if index_file.exists() else 0

        # Count operations and rollbacks
        total_operations = 0
        total_rollbacks = 0
        compression_ratio = None
        index_memory = 0

        try:
            # Try to read index for quick counts
            if index_file.exists():
                with open(index_file, "r") as f:
                    index_data = json.load(f)
                    total_operations = len(index_data)
                    index_memory = len(json.dumps(index_data).encode("utf-8"))

            # Try to get compression ratio
            if operations_gz_file.exists():
                # Estimate compression ratio
                try:
                    import gzip

                    with gzip.open(operations_gz_file, "rt") as f:
                        uncompressed_data = f.read()
                    uncompressed_size = len(uncompressed_data.encode("utf-8"))
                    if uncompressed_size > 0:
                        compression_ratio = operations_size / uncompressed_size
                except Exception:
                    pass

        except Exception:
            pass

        total_size = operations_size + rollbacks_size + index_size

        return StorageMetrics(
            timestamp=datetime.now(timezone.utc),
            total_operations=total_operations,
            total_rollbacks=total_rollbacks,
            operations_file_size=operations_size,
            rollbacks_file_size=rollbacks_size,
            index_file_size=index_size,
            total_storage_size=total_size,
            compression_ratio=compression_ratio,
            index_memory_usage=index_memory,
        )

    def _get_disk_usage(self) -> Optional[Dict[str, Any]]:
        """Get disk usage information."""
        try:
            stat = os.statvfs(self.storage_dir)
            total_bytes = stat.f_frsize * stat.f_blocks
            free_bytes = stat.f_frsize * stat.f_available
            used_bytes = total_bytes - free_bytes

            return {
                "total_bytes": total_bytes,
                "used_bytes": used_bytes,
                "free_bytes": free_bytes,
                "free_percent": (free_bytes / total_bytes * 100) if total_bytes > 0 else 0,
                "used_percent": (used_bytes / total_bytes * 100) if total_bytes > 0 else 0,
            }
        except (OSError, AttributeError):
            return None

    def _create_alert(
        self,
        alert_type: str,
        severity: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StorageAlert:
        """Create a storage alert."""
        return StorageAlert(
            alert_type=alert_type,
            severity=severity,
            message=message,
            timestamp=datetime.now(timezone.utc),
            metadata=metadata or {},
        )

    def _emit_alert(
        self,
        alert_type: str,
        severity: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit an alert to all handlers."""
        alert = self._create_alert(alert_type, severity, message, metadata)
        self._emit_alert_object(alert)

    def _emit_alert_object(self, alert: StorageAlert) -> None:
        """Emit an alert object to all handlers."""
        # Store alert
        self._store_alert(alert)

        # Send to handlers
        for handler in self.alert_handlers:
            try:
                handler(alert)
            except Exception as e:
                console.print(f"[red]Alert handler error: {str(e)}[/red]")

    def _store_alert(self, alert: StorageAlert) -> None:
        """Store alert to file."""
        try:
            alerts = []
            if self.alerts_file.exists():
                with open(self.alerts_file, "r") as f:
                    data = json.load(f)
                    alerts = [StorageAlert.from_dict(a) for a in data.get("alerts", [])]

            alerts.append(alert)

            # Keep only last 1000 alerts
            if len(alerts) > 1000:
                alerts = alerts[-1000:]

            with open(self.alerts_file, "w") as f:
                json.dump({"alerts": [a.to_dict() for a in alerts]}, f, separators=(",", ":"))
        except Exception:
            pass  # Don't fail if we can't store alerts

    def _store_metrics(self, metrics: StorageMetrics) -> None:
        """Store metrics to file."""
        try:
            metrics_list = []
            if self.metrics_file.exists():
                with open(self.metrics_file, "r") as f:
                    data = json.load(f)
                    metrics_list = [StorageMetrics.from_dict(m) for m in data.get("metrics", [])]

            metrics_list.append(metrics)

            # Keep only last 1000 metrics (about 3.5 days at 5-minute intervals)
            if len(metrics_list) > 1000:
                metrics_list = metrics_list[-1000:]

            with open(self.metrics_file, "w") as f:
                json.dump(
                    {"metrics": [m.to_dict() for m in metrics_list]}, f, separators=(",", ":")
                )
        except Exception:
            pass  # Don't fail if we can't store metrics

    def get_recent_alerts(self, hours: int = 24) -> List[StorageAlert]:
        """Get recent alerts."""
        if not self.alerts_file.exists():
            return []

        cutoff_time = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff_time = cutoff_time.replace(hour=cutoff_time.hour - hours)

        try:
            with open(self.alerts_file, "r") as f:
                data = json.load(f)
                alerts = [StorageAlert.from_dict(a) for a in data.get("alerts", [])]

                return [a for a in alerts if a.timestamp >= cutoff_time]
        except Exception:
            return []

    def get_recent_metrics(self, hours: int = 24) -> List[StorageMetrics]:
        """Get recent metrics."""
        if not self.metrics_file.exists():
            return []

        cutoff_time = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff_time = cutoff_time.replace(hour=cutoff_time.hour - hours)

        try:
            with open(self.metrics_file, "r") as f:
                data = json.load(f)
                metrics = [StorageMetrics.from_dict(m) for m in data.get("metrics", [])]

                return [m for m in metrics if m.timestamp >= cutoff_time]
        except Exception:
            return []

    def get_storage_summary(self) -> Dict[str, Any]:
        """Get storage summary with current status."""
        try:
            current_metrics = self._collect_metrics()
            recent_alerts = self.get_recent_alerts(24)

            # Count alerts by severity
            alert_counts = {"info": 0, "warning": 0, "error": 0, "critical": 0}
            for alert in recent_alerts:
                alert_counts[alert.severity] = alert_counts.get(alert.severity, 0) + 1

            return {
                "current_metrics": current_metrics.to_dict(),
                "recent_alerts_24h": len(recent_alerts),
                "alert_counts": alert_counts,
                "monitoring_active": self._monitoring,
                "thresholds": self.thresholds,
                "storage_directory": str(self.storage_dir),
            }
        except Exception as e:
            return {
                "error": f"Failed to get storage summary: {str(e)}",
                "monitoring_active": self._monitoring,
                "storage_directory": str(self.storage_dir),
            }
