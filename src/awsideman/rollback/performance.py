"""Performance monitoring and optimization for rollback operations."""

import json
import os
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

console = Console()


@dataclass
class PerformanceMetric:
    """Individual performance metric."""

    name: str
    value: float
    unit: str
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PerformanceMetric":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            value=data["value"],
            unit=data["unit"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {}),
        )


@dataclass
class OperationMetrics:
    """Performance metrics for a rollback operation."""

    operation_id: str
    rollback_operation_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    total_actions: int = 0
    completed_actions: int = 0
    failed_actions: int = 0
    batch_size: int = 10
    metrics: List[PerformanceMetric] = field(default_factory=list)

    @property
    def duration_ms(self) -> Optional[int]:
        """Get operation duration in milliseconds."""
        if self.end_time:
            return int((self.end_time - self.start_time).total_seconds() * 1000)
        return None

    @property
    def actions_per_second(self) -> Optional[float]:
        """Get actions per second rate."""
        if self.end_time and self.completed_actions > 0:
            duration_seconds = (self.end_time - self.start_time).total_seconds()
            if duration_seconds > 0:
                return self.completed_actions / duration_seconds
        return None

    def add_metric(
        self, name: str, value: float, unit: str, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Add a performance metric."""
        metric = PerformanceMetric(
            name=name,
            value=value,
            unit=unit,
            timestamp=datetime.now(timezone.utc),
            metadata=metadata or {},
        )
        self.metrics.append(metric)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "operation_id": self.operation_id,
            "rollback_operation_id": self.rollback_operation_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "total_actions": self.total_actions,
            "completed_actions": self.completed_actions,
            "failed_actions": self.failed_actions,
            "batch_size": self.batch_size,
            "duration_ms": self.duration_ms,
            "actions_per_second": self.actions_per_second,
            "metrics": [m.to_dict() for m in self.metrics],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OperationMetrics":
        """Create from dictionary."""
        return cls(
            operation_id=data["operation_id"],
            rollback_operation_id=data["rollback_operation_id"],
            start_time=datetime.fromisoformat(data["start_time"]),
            end_time=datetime.fromisoformat(data["end_time"]) if data.get("end_time") else None,
            total_actions=data.get("total_actions", 0),
            completed_actions=data.get("completed_actions", 0),
            failed_actions=data.get("failed_actions", 0),
            batch_size=data.get("batch_size", 10),
            metrics=[PerformanceMetric.from_dict(m) for m in data.get("metrics", [])],
        )


class PerformanceTracker:
    """Tracks performance metrics for rollback operations."""

    def __init__(self, storage_directory: Optional[str] = None):
        """Initialize performance tracker.

        Args:
            storage_directory: Directory to store performance metrics
        """
        self.storage_directory = storage_directory or os.path.expanduser("~/.awsideman/performance")
        self.metrics_file = Path(self.storage_directory) / "rollback_metrics.json"
        self.current_operations: Dict[str, OperationMetrics] = {}
        self._lock = threading.Lock()

        # Ensure storage directory exists
        Path(self.storage_directory).mkdir(parents=True, exist_ok=True)

    def start_operation_tracking(
        self,
        operation_id: str,
        rollback_operation_id: str,
        total_actions: int,
        batch_size: int = 10,
    ) -> OperationMetrics:
        """Start tracking performance for a rollback operation.

        Args:
            operation_id: Original operation ID
            rollback_operation_id: Rollback operation ID
            total_actions: Total number of actions to perform
            batch_size: Batch size for processing

        Returns:
            OperationMetrics instance for tracking
        """
        with self._lock:
            metrics = OperationMetrics(
                operation_id=operation_id,
                rollback_operation_id=rollback_operation_id,
                start_time=datetime.now(timezone.utc),
                total_actions=total_actions,
                batch_size=batch_size,
            )
            self.current_operations[rollback_operation_id] = metrics
            return metrics

    def update_operation_progress(
        self,
        rollback_operation_id: str,
        completed_actions: int,
        failed_actions: int,
    ) -> None:
        """Update progress for an operation.

        Args:
            rollback_operation_id: Rollback operation ID
            completed_actions: Number of completed actions
            failed_actions: Number of failed actions
        """
        with self._lock:
            if rollback_operation_id in self.current_operations:
                metrics = self.current_operations[rollback_operation_id]
                metrics.completed_actions = completed_actions
                metrics.failed_actions = failed_actions

    def add_operation_metric(
        self,
        rollback_operation_id: str,
        name: str,
        value: float,
        unit: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add a metric to an operation.

        Args:
            rollback_operation_id: Rollback operation ID
            name: Metric name
            value: Metric value
            unit: Metric unit
            metadata: Additional metadata
        """
        with self._lock:
            if rollback_operation_id in self.current_operations:
                self.current_operations[rollback_operation_id].add_metric(
                    name, value, unit, metadata
                )

    def finish_operation_tracking(self, rollback_operation_id: str) -> Optional[OperationMetrics]:
        """Finish tracking an operation and persist metrics.

        Args:
            rollback_operation_id: Rollback operation ID

        Returns:
            Final OperationMetrics if found
        """
        with self._lock:
            if rollback_operation_id not in self.current_operations:
                return None

            metrics = self.current_operations[rollback_operation_id]
            metrics.end_time = datetime.now(timezone.utc)

            # Calculate final metrics
            if metrics.duration_ms:
                metrics.add_metric("total_duration", metrics.duration_ms, "ms")

            if metrics.actions_per_second:
                metrics.add_metric("throughput", metrics.actions_per_second, "actions/sec")

            # Calculate success rate
            if metrics.total_actions > 0:
                success_rate = (metrics.completed_actions / metrics.total_actions) * 100
                metrics.add_metric("success_rate", success_rate, "percent")

            # Persist metrics
            self._persist_metrics(metrics)

            # Remove from current operations
            del self.current_operations[rollback_operation_id]

            return metrics

    def _persist_metrics(self, metrics: OperationMetrics) -> None:
        """Persist metrics to storage.

        Args:
            metrics: Metrics to persist
        """
        try:
            # Load existing metrics
            existing_metrics = []
            if self.metrics_file.exists():
                with open(self.metrics_file, "r") as f:
                    data = json.load(f)
                    existing_metrics = data.get("operations", [])

            # Add new metrics
            existing_metrics.append(metrics.to_dict())

            # Keep only last 1000 operations to prevent unbounded growth
            if len(existing_metrics) > 1000:
                existing_metrics = existing_metrics[-1000:]

            # Save back to file
            with open(self.metrics_file, "w") as f:
                json.dump({"operations": existing_metrics}, f, indent=2)

        except Exception as e:
            console.print(
                f"[yellow]Warning: Could not persist performance metrics: {str(e)}[/yellow]"
            )

    def get_operation_metrics(self, rollback_operation_id: str) -> Optional[OperationMetrics]:
        """Get metrics for a specific operation.

        Args:
            rollback_operation_id: Rollback operation ID

        Returns:
            OperationMetrics if found
        """
        # Check current operations first
        with self._lock:
            if rollback_operation_id in self.current_operations:
                return self.current_operations[rollback_operation_id]

        # Check persisted metrics
        try:
            if self.metrics_file.exists():
                with open(self.metrics_file, "r") as f:
                    data = json.load(f)
                    for op_data in data.get("operations", []):
                        if op_data.get("rollback_operation_id") == rollback_operation_id:
                            return OperationMetrics.from_dict(op_data)
        except Exception:
            pass

        return None

    def get_performance_summary(self, days: int = 30) -> Dict[str, Any]:
        """Get performance summary for recent operations.

        Args:
            days: Number of days to include in summary

        Returns:
            Performance summary dictionary
        """
        cutoff_time = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff_time = cutoff_time.replace(day=cutoff_time.day - days)

        operations = []

        try:
            if self.metrics_file.exists():
                with open(self.metrics_file, "r") as f:
                    data = json.load(f)
                    for op_data in data.get("operations", []):
                        start_time = datetime.fromisoformat(op_data["start_time"])
                        if start_time >= cutoff_time:
                            operations.append(OperationMetrics.from_dict(op_data))
        except Exception:
            pass

        if not operations:
            return {
                "total_operations": 0,
                "total_actions": 0,
                "average_duration_ms": 0,
                "average_throughput": 0,
                "average_success_rate": 0,
                "total_duration_ms": 0,
            }

        total_actions = sum(op.total_actions for op in operations)
        total_duration_ms = sum(op.duration_ms or 0 for op in operations)
        completed_operations = [op for op in operations if op.end_time]

        avg_duration = (
            sum(op.duration_ms or 0 for op in completed_operations) / len(completed_operations)
            if completed_operations
            else 0
        )
        avg_throughput = (
            sum(op.actions_per_second or 0 for op in completed_operations)
            / len(completed_operations)
            if completed_operations
            else 0
        )

        # Calculate average success rate
        success_rates = []
        for op in operations:
            if op.total_actions > 0:
                success_rate = (op.completed_actions / op.total_actions) * 100
                success_rates.append(success_rate)

        avg_success_rate = sum(success_rates) / len(success_rates) if success_rates else 0

        return {
            "total_operations": len(operations),
            "total_actions": total_actions,
            "average_duration_ms": int(avg_duration),
            "average_throughput": round(avg_throughput, 2),
            "average_success_rate": round(avg_success_rate, 2),
            "total_duration_ms": total_duration_ms,
        }


class ProgressTracker:
    """Tracks and displays progress for long-running rollback operations."""

    def __init__(self, show_progress: bool = True):
        """Initialize progress tracker.

        Args:
            show_progress: Whether to show progress bars
        """
        self.show_progress = show_progress
        self.progress: Optional[Progress] = None
        self.task_id: Optional[TaskID] = None
        self._lock = threading.Lock()

    @contextmanager
    def track_operation(self, description: str, total: int):
        """Context manager for tracking operation progress.

        Args:
            description: Description of the operation
            total: Total number of items to process
        """
        # Disable progress bars in test environments to prevent hangs
        if not self.show_progress or "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ:
            yield self
            return

        with self._lock:
            self.progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TextColumn("({task.completed}/{task.total})"),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
                console=console,
            )

            with self.progress:
                self.task_id = self.progress.add_task(description, total=total)
                yield self

    def update_progress(self, completed: int, description: Optional[str] = None) -> None:
        """Update progress.

        Args:
            completed: Number of completed items
            description: Optional updated description
        """
        if not self.show_progress or not self.progress or self.task_id is None:
            return

        with self._lock:
            self.progress.update(self.task_id, completed=completed)
            if description:
                self.progress.update(self.task_id, description=description)

    def advance_progress(self, amount: int = 1) -> None:
        """Advance progress by specified amount.

        Args:
            amount: Amount to advance
        """
        if not self.show_progress or not self.progress or self.task_id is None:
            return

        with self._lock:
            self.progress.advance(self.task_id, amount)


@contextmanager
def measure_time(
    name: str,
    tracker: Optional[PerformanceTracker] = None,
    rollback_operation_id: Optional[str] = None,
):
    """Context manager for measuring execution time.

    Args:
        name: Name of the measurement
        tracker: Optional performance tracker to record to
        rollback_operation_id: Optional rollback operation ID
    """
    start_time = time.time()
    try:
        yield
    finally:
        duration_ms = (time.time() - start_time) * 1000
        if tracker and rollback_operation_id:
            tracker.add_operation_metric(rollback_operation_id, name, duration_ms, "ms")


class PerformanceBenchmark:
    """Performance benchmarking utilities for rollback operations."""

    @staticmethod
    def benchmark_operation_types() -> Dict[str, Dict[str, float]]:
        """Benchmark different operation types.

        Returns:
            Benchmark results by operation type
        """
        # This would be implemented with actual AWS API calls in a real benchmark
        # For now, return estimated benchmarks based on typical performance
        return {
            "assign": {
                "avg_duration_ms": 2500,
                "min_duration_ms": 1500,
                "max_duration_ms": 5000,
                "success_rate": 98.5,
            },
            "revoke": {
                "avg_duration_ms": 2000,
                "min_duration_ms": 1200,
                "max_duration_ms": 4000,
                "success_rate": 99.2,
            },
        }

    @staticmethod
    def benchmark_batch_sizes() -> Dict[int, Dict[str, float]]:
        """Benchmark different batch sizes.

        Returns:
            Benchmark results by batch size
        """
        # Estimated performance characteristics for different batch sizes
        return {
            1: {"throughput": 0.4, "memory_mb": 50, "error_rate": 1.0},
            5: {"throughput": 1.8, "memory_mb": 75, "error_rate": 1.2},
            10: {"throughput": 3.2, "memory_mb": 100, "error_rate": 1.5},
            20: {"throughput": 5.1, "memory_mb": 150, "error_rate": 2.1},
            50: {"throughput": 8.5, "memory_mb": 300, "error_rate": 3.5},
        }

    @staticmethod
    def get_optimization_recommendations(metrics: OperationMetrics) -> List[str]:
        """Get optimization recommendations based on metrics.

        Args:
            metrics: Operation metrics to analyze

        Returns:
            List of optimization recommendations
        """
        recommendations = []

        # Analyze throughput
        if metrics.actions_per_second and metrics.actions_per_second < 2.0:
            recommendations.append("Consider increasing batch size to improve throughput")

        # Analyze success rate
        success_rate = (
            (metrics.completed_actions / metrics.total_actions * 100)
            if metrics.total_actions > 0
            else 0
        )
        if success_rate < 95:
            recommendations.append(
                "High failure rate detected - consider implementing retry logic or reducing batch size"
            )

        # Analyze duration
        if metrics.duration_ms and metrics.total_actions > 0:
            avg_time_per_action = metrics.duration_ms / metrics.total_actions
            if avg_time_per_action > 3000:  # 3 seconds per action
                recommendations.append(
                    "High latency per action - consider optimizing AWS API calls or network connectivity"
                )

        # Analyze batch size efficiency
        if metrics.batch_size > 20 and success_rate < 98:
            recommendations.append(
                "Large batch size with failures - consider reducing batch size for better reliability"
            )

        if metrics.batch_size < 5 and metrics.total_actions > 50:
            recommendations.append(
                "Small batch size for large operation - consider increasing batch size for better performance"
            )

        return recommendations
