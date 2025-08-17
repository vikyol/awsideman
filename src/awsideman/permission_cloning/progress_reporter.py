"""
Progress reporting and audit logging for permission cloning operations.

This module provides comprehensive progress reporting, audit logging, and performance
metrics tracking for all permission cloning operations including assignment copying
and permission set cloning.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Union
from uuid import uuid4

from ..utils.logging_config import StatusLoggingManager, get_status_logger
from .models import CloneResult, CopyResult, EntityReference


@dataclass
class ProgressUpdate:
    """Progress update information for operations."""

    operation_id: str
    operation_type: str
    current: int
    total: int
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def percentage(self) -> float:
        """Get completion percentage."""
        if self.total == 0:
            return 100.0
        return (self.current / self.total) * 100.0

    @property
    def is_complete(self) -> bool:
        """Check if operation is complete."""
        return self.current >= self.total


@dataclass
class OperationAuditLog:
    """Audit log entry for permission cloning operations."""

    operation_id: str
    operation_type: str
    user_id: Optional[str]
    timestamp: datetime
    source_entity: Optional[EntityReference]
    target_entity: Optional[EntityReference]
    source_permission_set: Optional[str]
    target_permission_set: Optional[str]
    action: str
    result: str
    details: Dict[str, Any]
    duration_ms: Optional[float] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "operation_id": self.operation_id,
            "operation_type": self.operation_type,
            "user_id": self.user_id,
            "timestamp": self.timestamp.isoformat(),
            "source_entity": (
                {
                    "type": self.source_entity.entity_type.value,
                    "id": self.source_entity.entity_id,
                    "name": self.source_entity.entity_name,
                }
                if self.source_entity
                else None
            ),
            "target_entity": (
                {
                    "type": self.target_entity.entity_type.value,
                    "id": self.target_entity.entity_id,
                    "name": self.target_entity.entity_name,
                }
                if self.target_entity
                else None
            ),
            "source_permission_set": self.source_permission_set,
            "target_permission_set": self.target_permission_set,
            "action": self.action,
            "result": self.result,
            "duration_ms": self.duration_ms,
            "error_message": self.error_message,
            "details": self.details,
        }


@dataclass
class PerformanceMetricsLog:
    """Performance metrics log entry."""

    operation_id: str
    operation_type: str
    timestamp: datetime
    metric_name: str
    metric_value: Union[int, float]
    metric_unit: str
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "operation_id": self.operation_id,
            "operation_type": self.operation_type,
            "timestamp": self.timestamp.isoformat(),
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "metric_unit": self.metric_unit,
            "context": self.context,
        }


class ProgressReporter:
    """
    Progress reporter for permission cloning operations.

    Provides real-time progress updates, comprehensive audit logging,
    and performance metrics tracking for all permission cloning operations.
    """

    def __init__(
        self, logging_manager: Optional[StatusLoggingManager] = None, user_id: Optional[str] = None
    ):
        """
        Initialize the progress reporter.

        Args:
            logging_manager: Optional logging manager instance
            user_id: Optional user ID for audit logging
        """
        self.logging_manager = logging_manager
        self.user_id = user_id

        # Set up loggers
        self.logger = get_status_logger("permission_cloning.progress")
        self.audit_logger = get_status_logger("permission_cloning.audit")
        self.performance_logger = get_status_logger("permission_cloning.performance")

        # Active operations tracking
        self._active_operations: Dict[str, Dict[str, Any]] = {}
        self._progress_callbacks: Dict[str, List[Callable[[ProgressUpdate], None]]] = {}

    def start_operation(
        self, operation_type: str, operation_id: Optional[str] = None, **context
    ) -> str:
        """
        Start tracking a new operation.

        Args:
            operation_type: Type of operation (e.g., 'copy_assignments', 'clone_permission_set')
            operation_id: Optional operation ID (generated if not provided)
            **context: Additional context information

        Returns:
            Operation ID for tracking
        """
        if not operation_id:
            operation_id = str(uuid4())

        start_time = datetime.now(timezone.utc)

        # Track operation
        self._active_operations[operation_id] = {
            "operation_type": operation_type,
            "start_time": start_time,
            "context": context,
            "progress_updates": [],
            "audit_logs": [],
            "performance_metrics": [],
        }

        # Initialize progress callbacks
        self._progress_callbacks[operation_id] = []

        # Log operation start
        self.logger.info(
            f"Starting {operation_type} operation",
            extra={
                "operation_id": operation_id,
                "operation_type": operation_type,
                "operation_start": True,
                **context,
            },
        )

        # Create audit log entry
        self._log_audit_event(
            operation_id=operation_id,
            operation_type=operation_type,
            action="operation_started",
            result="success",
            details=context,
        )

        return operation_id

    def update_progress(
        self, operation_id: str, current: int, total: int, message: str = "", **context
    ) -> None:
        """
        Update progress for an operation.

        Args:
            operation_id: Operation ID
            current: Current progress count
            total: Total items to process
            message: Progress message
            **context: Additional context information
        """
        if operation_id not in self._active_operations:
            self.logger.warning(f"Progress update for unknown operation: {operation_id}")
            return

        operation = self._active_operations[operation_id]

        # Create progress update
        progress_update = ProgressUpdate(
            operation_id=operation_id,
            operation_type=operation["operation_type"],
            current=current,
            total=total,
            message=message,
        )

        # Store progress update
        operation["progress_updates"].append(progress_update)

        # Log progress
        self.logger.info(
            f"Progress update: {current}/{total} ({progress_update.percentage:.1f}%) - {message}",
            extra={
                "operation_id": operation_id,
                "operation_type": operation["operation_type"],
                "progress_current": current,
                "progress_total": total,
                "progress_percentage": progress_update.percentage,
                "progress_message": message,
                "progress_update": True,
                **context,
            },
        )

        # Call progress callbacks
        for callback in self._progress_callbacks.get(operation_id, []):
            try:
                callback(progress_update)
            except Exception as e:
                self.logger.error(f"Error in progress callback: {str(e)}")

    def finish_operation(
        self,
        operation_id: str,
        success: bool = True,
        error_message: Optional[str] = None,
        **context,
    ) -> None:
        """
        Finish tracking an operation.

        Args:
            operation_id: Operation ID
            success: Whether operation was successful
            error_message: Optional error message if operation failed
            **context: Additional context information
        """
        if operation_id not in self._active_operations:
            self.logger.warning(f"Finish called for unknown operation: {operation_id}")
            return

        operation = self._active_operations[operation_id]
        end_time = datetime.now(timezone.utc)
        duration_ms = (end_time - operation["start_time"]).total_seconds() * 1000

        # Log operation completion
        level = logging.INFO if success else logging.ERROR
        status = "completed" if success else "failed"

        self.logger.log(
            level,
            f"Operation {status}: {operation['operation_type']} (duration: {duration_ms:.1f}ms)",
            extra={
                "operation_id": operation_id,
                "operation_type": operation["operation_type"],
                "operation_end": True,
                "success": success,
                "duration_ms": duration_ms,
                "error_message": error_message,
                **context,
            },
        )

        # Create audit log entry
        self._log_audit_event(
            operation_id=operation_id,
            operation_type=operation["operation_type"],
            action="operation_completed",
            result="success" if success else "failure",
            details={"duration_ms": duration_ms, "error_message": error_message, **context},
            duration_ms=duration_ms,
            error_message=error_message,
        )

        # Clean up
        del self._active_operations[operation_id]
        self._progress_callbacks.pop(operation_id, None)

    def log_assignment_copy_start(
        self,
        operation_id: str,
        source_entity: EntityReference,
        target_entity: EntityReference,
        total_assignments: int,
        filters_applied: Optional[str] = None,
    ) -> None:
        """
        Log the start of an assignment copy operation.

        Args:
            operation_id: Operation ID
            source_entity: Source entity reference
            target_entity: Target entity reference
            total_assignments: Total number of assignments to copy
            filters_applied: Description of filters applied
        """
        details = {
            "source_entity_type": source_entity.entity_type.value,
            "source_entity_id": source_entity.entity_id,
            "source_entity_name": source_entity.entity_name,
            "target_entity_type": target_entity.entity_type.value,
            "target_entity_id": target_entity.entity_id,
            "target_entity_name": target_entity.entity_name,
            "total_assignments": total_assignments,
            "filters_applied": filters_applied,
        }

        self._log_audit_event(
            operation_id=operation_id,
            operation_type="copy_assignments",
            action="copy_started",
            result="success",
            details=details,
            source_entity=source_entity,
            target_entity=target_entity,
        )

    def log_assignment_copy_result(
        self, operation_id: str, copy_result: CopyResult, duration_ms: float
    ) -> None:
        """
        Log the result of an assignment copy operation.

        Args:
            operation_id: Operation ID
            copy_result: Copy operation result
            duration_ms: Operation duration in milliseconds
        """
        details = {
            "assignments_copied": len(copy_result.assignments_copied),
            "assignments_skipped": len(copy_result.assignments_skipped),
            "rollback_id": copy_result.rollback_id,
            "success": copy_result.success,
            "error_message": copy_result.error_message,
            "copied_assignments": [
                {
                    "permission_set_name": assignment.permission_set_name,
                    "permission_set_arn": assignment.permission_set_arn,
                    "account_id": assignment.account_id,
                    "account_name": assignment.account_name,
                }
                for assignment in copy_result.assignments_copied
            ],
            "skipped_assignments": [
                {
                    "permission_set_name": assignment.permission_set_name,
                    "permission_set_arn": assignment.permission_set_arn,
                    "account_id": assignment.account_id,
                    "account_name": assignment.account_name,
                }
                for assignment in copy_result.assignments_skipped
            ],
        }

        self._log_audit_event(
            operation_id=operation_id,
            operation_type="copy_assignments",
            action="copy_completed",
            result="success" if copy_result.success else "failure",
            details=details,
            source_entity=copy_result.source,
            target_entity=copy_result.target,
            duration_ms=duration_ms,
            error_message=copy_result.error_message,
        )

    def log_permission_set_clone_start(
        self,
        operation_id: str,
        source_name: str,
        target_name: str,
        source_arn: Optional[str] = None,
    ) -> None:
        """
        Log the start of a permission set clone operation.

        Args:
            operation_id: Operation ID
            source_name: Source permission set name
            target_name: Target permission set name
            source_arn: Optional source permission set ARN
        """
        details = {
            "source_permission_set_name": source_name,
            "target_permission_set_name": target_name,
            "source_permission_set_arn": source_arn,
        }

        self._log_audit_event(
            operation_id=operation_id,
            operation_type="clone_permission_set",
            action="clone_started",
            result="success",
            details=details,
            source_permission_set=source_name,
            target_permission_set=target_name,
        )

    def log_permission_set_clone_result(
        self, operation_id: str, clone_result: CloneResult, duration_ms: float
    ) -> None:
        """
        Log the result of a permission set clone operation.

        Args:
            operation_id: Operation ID
            clone_result: Clone operation result
            duration_ms: Operation duration in milliseconds
        """
        details = {
            "source_name": clone_result.source_name,
            "target_name": clone_result.target_name,
            "rollback_id": clone_result.rollback_id,
            "success": clone_result.success,
            "error_message": clone_result.error_message,
        }

        # Add cloned configuration details if available
        if clone_result.cloned_config:
            config = clone_result.cloned_config
            details["cloned_config"] = {
                "description": config.description,
                "session_duration": config.session_duration,
                "relay_state_url": config.relay_state_url,
                "aws_managed_policies_count": len(config.aws_managed_policies),
                "customer_managed_policies_count": len(config.customer_managed_policies),
                "has_inline_policy": config.inline_policy is not None,
                "aws_managed_policies": config.aws_managed_policies,
                "customer_managed_policies": [
                    {"name": policy.name, "path": policy.path}
                    for policy in config.customer_managed_policies
                ],
            }

        self._log_audit_event(
            operation_id=operation_id,
            operation_type="clone_permission_set",
            action="clone_completed",
            result="success" if clone_result.success else "failure",
            details=details,
            source_permission_set=clone_result.source_name,
            target_permission_set=clone_result.target_name,
            duration_ms=duration_ms,
            error_message=clone_result.error_message,
        )

    def log_rollback_operation(
        self,
        operation_id: str,
        rollback_type: str,
        rollback_result: Dict[str, Any],
        duration_ms: float,
    ) -> None:
        """
        Log a rollback operation.

        Args:
            operation_id: Original operation ID being rolled back
            rollback_type: Type of rollback ('assignment_copy' or 'permission_set_clone')
            rollback_result: Result of the rollback operation
            duration_ms: Rollback duration in milliseconds
        """
        rollback_operation_id = f"rollback_{operation_id}"

        details = {
            "original_operation_id": operation_id,
            "rollback_type": rollback_type,
            "rollback_result": rollback_result,
        }

        self._log_audit_event(
            operation_id=rollback_operation_id,
            operation_type="rollback_operation",
            action=f"rollback_{rollback_type}",
            result="success" if rollback_result.get("success", False) else "failure",
            details=details,
            duration_ms=duration_ms,
            error_message=rollback_result.get("error"),
        )

        # Log structured rollback information
        self.logger.info(
            f"Rollback operation completed for {operation_id}",
            extra={
                "operation_id": rollback_operation_id,
                "original_operation_id": operation_id,
                "rollback_type": rollback_type,
                "rollback_success": rollback_result.get("success", False),
                "rollback_duration_ms": duration_ms,
                "rollback_details": rollback_result,
                "rollback_operation": True,
            },
        )

    def log_performance_metric(
        self,
        operation_id: str,
        operation_type: str,
        metric_name: str,
        metric_value: Union[int, float],
        metric_unit: str = "",
        **context,
    ) -> None:
        """
        Log a performance metric.

        Args:
            operation_id: Operation ID
            operation_type: Type of operation
            metric_name: Name of the metric
            metric_value: Metric value
            metric_unit: Unit of measurement
            **context: Additional context information
        """
        # Create performance metrics log entry
        metrics_log = PerformanceMetricsLog(
            operation_id=operation_id,
            operation_type=operation_type,
            timestamp=datetime.now(timezone.utc),
            metric_name=metric_name,
            metric_value=metric_value,
            metric_unit=metric_unit,
            context=context,
        )

        # Store in operation if active
        if operation_id in self._active_operations:
            self._active_operations[operation_id]["performance_metrics"].append(metrics_log)

        # Log performance metric
        self.performance_logger.info(
            f"Performance metric: {metric_name} = {metric_value} {metric_unit}",
            extra={
                "operation_id": operation_id,
                "operation_type": operation_type,
                "metric_name": metric_name,
                "metric_value": metric_value,
                "metric_unit": metric_unit,
                "performance_metric": True,
                **context,
            },
        )

    def add_progress_callback(
        self, operation_id: str, callback: Callable[[ProgressUpdate], None]
    ) -> None:
        """
        Add a progress callback for an operation.

        Args:
            operation_id: Operation ID
            callback: Callback function to call on progress updates
        """
        if operation_id not in self._progress_callbacks:
            self._progress_callbacks[operation_id] = []

        self._progress_callbacks[operation_id].append(callback)

    def get_operation_status(self, operation_id: str) -> Optional[Dict[str, Any]]:
        """
        Get current status of an operation.

        Args:
            operation_id: Operation ID

        Returns:
            Operation status information or None if not found
        """
        if operation_id not in self._active_operations:
            return None

        operation = self._active_operations[operation_id]
        latest_progress = (
            operation["progress_updates"][-1] if operation["progress_updates"] else None
        )

        return {
            "operation_id": operation_id,
            "operation_type": operation["operation_type"],
            "start_time": operation["start_time"].isoformat(),
            "context": operation["context"],
            "latest_progress": (
                {
                    "current": latest_progress.current,
                    "total": latest_progress.total,
                    "percentage": latest_progress.percentage,
                    "message": latest_progress.message,
                    "timestamp": latest_progress.timestamp.isoformat(),
                }
                if latest_progress
                else None
            ),
            "total_progress_updates": len(operation["progress_updates"]),
            "total_audit_logs": len(operation["audit_logs"]),
            "total_performance_metrics": len(operation["performance_metrics"]),
        }

    def get_active_operations(self) -> List[Dict[str, Any]]:
        """
        Get list of all active operations.

        Returns:
            List of active operation status information
        """
        return [
            self.get_operation_status(operation_id)
            for operation_id in self._active_operations.keys()
        ]

    def _log_audit_event(
        self,
        operation_id: str,
        operation_type: str,
        action: str,
        result: str,
        details: Dict[str, Any],
        source_entity: Optional[EntityReference] = None,
        target_entity: Optional[EntityReference] = None,
        source_permission_set: Optional[str] = None,
        target_permission_set: Optional[str] = None,
        duration_ms: Optional[float] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Log an audit event."""
        audit_log = OperationAuditLog(
            operation_id=operation_id,
            operation_type=operation_type,
            user_id=self.user_id,
            timestamp=datetime.now(timezone.utc),
            source_entity=source_entity,
            target_entity=target_entity,
            source_permission_set=source_permission_set,
            target_permission_set=target_permission_set,
            action=action,
            result=result,
            details=details,
            duration_ms=duration_ms,
            error_message=error_message,
        )

        # Store in operation if active
        if operation_id in self._active_operations:
            self._active_operations[operation_id]["audit_logs"].append(audit_log)

        # Log audit event
        self.audit_logger.info(
            f"Audit: {action} - {result}", extra={"audit_log": True, **audit_log.to_dict()}
        )


# Global progress reporter instance
_global_progress_reporter: Optional[ProgressReporter] = None


def get_progress_reporter(user_id: Optional[str] = None) -> ProgressReporter:
    """
    Get the global progress reporter instance.

    Args:
        user_id: Optional user ID for audit logging

    Returns:
        ProgressReporter instance
    """
    global _global_progress_reporter
    if _global_progress_reporter is None:
        _global_progress_reporter = ProgressReporter(user_id=user_id)
    return _global_progress_reporter


def set_progress_reporter(reporter: ProgressReporter) -> None:
    """
    Set the global progress reporter instance.

    Args:
        reporter: ProgressReporter instance to set as global
    """
    global _global_progress_reporter
    _global_progress_reporter = reporter
