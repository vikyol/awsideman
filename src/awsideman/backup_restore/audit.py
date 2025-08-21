"""
Audit logging and security event tracking for backup-restore operations.

This module provides comprehensive audit logging capabilities for all backup and restore
operations, including security events, access control violations, and operational activities.
"""

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..utils.logging_config import get_status_logger


class AuditEventType(Enum):
    """Types of audit events."""

    BACKUP_CREATED = "backup_created"
    BACKUP_DELETED = "backup_deleted"
    BACKUP_VALIDATED = "backup_validated"
    RESTORE_STARTED = "restore_started"
    RESTORE_COMPLETED = "restore_completed"
    RESTORE_FAILED = "restore_failed"
    ACCESS_GRANTED = "access_granted"
    ACCESS_DENIED = "access_denied"
    SECURITY_VIOLATION = "security_violation"
    ENCRYPTION_OPERATION = "encryption_operation"
    DECRYPTION_OPERATION = "decryption_operation"
    SECURE_DELETION = "secure_deletion"
    EXPORT_OPERATION = "export_operation"
    IMPORT_OPERATION = "import_operation"
    SCHEDULE_CREATED = "schedule_created"
    SCHEDULE_EXECUTED = "schedule_executed"
    RETENTION_CLEANUP = "retention_cleanup"


class AuditSeverity(Enum):
    """Severity levels for audit events."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """Represents a single audit event."""

    event_id: str
    timestamp: datetime
    event_type: AuditEventType
    severity: AuditSeverity
    user_id: Optional[str]
    session_id: Optional[str]
    source_ip: Optional[str]
    resource_id: Optional[str]
    resource_type: Optional[str]
    operation: str
    details: Dict[str, Any]
    success: bool
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert audit event to dictionary for serialization."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "source_ip": self.source_ip,
            "resource_id": self.resource_id,
            "resource_type": self.resource_type,
            "operation": self.operation,
            "details": self.details,
            "success": self.success,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuditEvent":
        """Create audit event from dictionary."""
        return cls(
            event_id=data["event_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            event_type=AuditEventType(data["event_type"]),
            severity=AuditSeverity(data["severity"]),
            user_id=data.get("user_id"),
            session_id=data.get("session_id"),
            source_ip=data.get("source_ip"),
            resource_id=data.get("resource_id"),
            resource_type=data.get("resource_type"),
            operation=data["operation"],
            details=data["details"],
            success=data["success"],
            error_message=data.get("error_message"),
        )


class AuditLogger:
    """
    Comprehensive audit logging system for backup-restore operations.

    Provides structured logging of all security-relevant events and operations
    with support for multiple output formats and storage backends.
    """

    def __init__(
        self,
        log_file: Optional[Path] = None,
        enable_console: bool = True,
        enable_structured: bool = True,
        retention_days: int = 365,
    ):
        """
        Initialize audit logger.

        Args:
            log_file: Path to audit log file
            enable_console: Whether to log to console
            enable_structured: Whether to use structured JSON logging
            retention_days: Number of days to retain audit logs
        """
        self.log_file = log_file or Path("audit.log")
        self.enable_console = enable_console
        self.enable_structured = enable_structured
        self.retention_days = retention_days

        # Set up logger
        self.logger = get_status_logger(f"audit.{__name__}")

        # Configure file handler for audit logs
        if self.log_file:
            try:
                # Create parent directory if it doesn't exist
                self.log_file.parent.mkdir(parents=True, exist_ok=True)
                file_handler = logging.FileHandler(self.log_file)
                file_handler.setLevel(logging.INFO)

                if self.enable_structured:
                    formatter = logging.Formatter("%(message)s")
                else:
                    formatter = logging.Formatter(
                        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                    )

                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)
            except (IOError, OSError):
                # If file handler creation fails, continue without file logging
                pass

    def log_event(self, event: AuditEvent) -> None:
        """
        Log an audit event.

        Args:
            event: The audit event to log
        """
        if self.enable_structured:
            log_message = json.dumps(event.to_dict(), default=str)
        else:
            log_message = (
                f"Event: {event.event_type.value} | "
                f"User: {event.user_id} | "
                f"Resource: {event.resource_id} | "
                f"Operation: {event.operation} | "
                f"Success: {event.success}"
            )

        # Log based on severity
        if event.severity == AuditSeverity.CRITICAL:
            self.logger.critical(log_message)
        elif event.severity == AuditSeverity.ERROR:
            self.logger.error(log_message)
        elif event.severity == AuditSeverity.WARNING:
            self.logger.warning(log_message)
        else:
            self.logger.info(log_message)

    def log_backup_operation(
        self,
        operation: str,
        backup_id: Optional[str] = None,
        user_id: Optional[str] = None,
        success: bool = True,
        details: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Log a backup-related operation.

        Args:
            operation: Description of the operation
            backup_id: ID of the backup involved
            user_id: ID of the user performing the operation
            success: Whether the operation succeeded
            details: Additional operation details
            error_message: Error message if operation failed
        """
        event_type = AuditEventType.BACKUP_CREATED
        if "delete" in operation.lower():
            event_type = AuditEventType.BACKUP_DELETED
        elif "validate" in operation.lower():
            event_type = AuditEventType.BACKUP_VALIDATED

        severity = AuditSeverity.INFO if success else AuditSeverity.ERROR

        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,
            severity=severity,
            user_id=user_id,
            session_id=None,  # Could be populated from context
            source_ip=None,  # Could be populated from context
            resource_id=backup_id,
            resource_type="backup",
            operation=operation,
            details=details or {},
            success=success,
            error_message=error_message,
        )

        self.log_event(event)

    def log_restore_operation(
        self,
        operation: str,
        backup_id: Optional[str] = None,
        user_id: Optional[str] = None,
        success: bool = True,
        details: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Log a restore-related operation.

        Args:
            operation: Description of the operation
            backup_id: ID of the backup being restored
            user_id: ID of the user performing the operation
            success: Whether the operation succeeded
            details: Additional operation details
            error_message: Error message if operation failed
        """
        event_type = AuditEventType.RESTORE_STARTED
        if "complete" in operation.lower():
            event_type = AuditEventType.RESTORE_COMPLETED
        elif "fail" in operation.lower():
            event_type = AuditEventType.RESTORE_FAILED

        severity = AuditSeverity.INFO if success else AuditSeverity.ERROR

        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,
            severity=severity,
            user_id=user_id,
            session_id=None,
            source_ip=None,
            resource_id=backup_id,
            resource_type="backup",
            operation=operation,
            details=details or {},
            success=success,
            error_message=error_message,
        )

        self.log_event(event)

    def log_security_event(
        self,
        event_type: AuditEventType,
        operation: str,
        user_id: Optional[str] = None,
        resource_id: Optional[str] = None,
        success: bool = False,
        details: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Log a security-related event.

        Args:
            event_type: Type of security event
            operation: Description of the operation
            user_id: ID of the user involved
            resource_id: ID of the resource involved
            success: Whether the operation succeeded
            details: Additional event details
            error_message: Error message if applicable
        """
        severity = AuditSeverity.WARNING if success else AuditSeverity.CRITICAL

        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            event_type=event_type,
            severity=severity,
            user_id=user_id,
            session_id=None,
            source_ip=None,
            resource_id=resource_id,
            resource_type="security",
            operation=operation,
            details=details or {},
            success=success,
            error_message=error_message,
        )

        self.log_event(event)

    def log_access_attempt(
        self,
        resource_id: str,
        user_id: Optional[str] = None,
        granted: bool = False,
        reason: Optional[str] = None,
    ) -> None:
        """
        Log an access attempt to a backup resource.

        Args:
            resource_id: ID of the resource being accessed
            user_id: ID of the user attempting access
            granted: Whether access was granted
            reason: Reason for access decision
        """
        event_type = AuditEventType.ACCESS_GRANTED if granted else AuditEventType.ACCESS_DENIED
        severity = AuditSeverity.INFO if granted else AuditSeverity.WARNING

        details = {}
        if reason:
            details["reason"] = reason

        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            event_type=event_type,
            severity=severity,
            user_id=user_id,
            session_id=None,
            source_ip=None,
            resource_id=resource_id,
            resource_type="backup",
            operation="access_attempt",
            details=details,
            success=granted,
            error_message=None if granted else f"Access denied: {reason}",
        )

        self.log_event(event)

    def log_encryption_operation(
        self,
        operation: str,
        resource_id: Optional[str] = None,
        key_id: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Log an encryption/decryption operation.

        Args:
            operation: Type of encryption operation
            resource_id: ID of the resource being encrypted/decrypted
            key_id: ID of the encryption key used
            success: Whether the operation succeeded
            error_message: Error message if operation failed
        """
        event_type = (
            AuditEventType.ENCRYPTION_OPERATION
            if "encrypt" in operation.lower()
            else AuditEventType.DECRYPTION_OPERATION
        )

        severity = AuditSeverity.INFO if success else AuditSeverity.ERROR

        details = {}
        if key_id:
            details["key_id"] = key_id

        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            event_type=event_type,
            severity=severity,
            user_id=None,
            session_id=None,
            source_ip=None,
            resource_id=resource_id,
            resource_type="encryption",
            operation=operation,
            details=details,
            success=success,
            error_message=error_message,
        )

        self.log_event(event)

    def log_secure_deletion(
        self,
        resource_id: str,
        deletion_method: str,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Log a secure deletion operation.

        Args:
            resource_id: ID of the resource being deleted
            deletion_method: Method used for secure deletion
            success: Whether the deletion succeeded
            error_message: Error message if deletion failed
        """
        severity = AuditSeverity.INFO if success else AuditSeverity.ERROR

        details = {"deletion_method": deletion_method}

        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            event_type=AuditEventType.SECURE_DELETION,
            severity=severity,
            user_id=None,
            session_id=None,
            source_ip=None,
            resource_id=resource_id,
            resource_type="backup",
            operation="secure_deletion",
            details=details,
            success=success,
            error_message=error_message,
        )

        self.log_event(event)

    def query_events(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[AuditEventType]] = None,
        user_id: Optional[str] = None,
        resource_id: Optional[str] = None,
        limit: int = 1000,
    ) -> List[AuditEvent]:
        """
        Query audit events with filtering.

        Args:
            start_time: Start time for event query
            end_time: End time for event query
            event_types: List of event types to filter by
            user_id: User ID to filter by
            resource_id: Resource ID to filter by
            limit: Maximum number of events to return

        Returns:
            List of matching audit events
        """
        # This is a simplified implementation
        # In a production system, this would query a database or log aggregation system
        events = []

        if not self.log_file.exists():
            return events

        try:
            with open(self.log_file, "r") as f:
                for line in f:
                    if not line.strip():
                        continue

                    try:
                        event_data = json.loads(line.strip())
                        event = AuditEvent.from_dict(event_data)

                        # Apply filters
                        if start_time and event.timestamp < start_time:
                            continue
                        if end_time and event.timestamp > end_time:
                            continue
                        if event_types and event.event_type not in event_types:
                            continue
                        if user_id and event.user_id != user_id:
                            continue
                        if resource_id and event.resource_id != resource_id:
                            continue

                        events.append(event)

                        if len(events) >= limit:
                            break

                    except (json.JSONDecodeError, KeyError, ValueError):
                        # Skip malformed log entries
                        continue

        except IOError:
            # Log file not accessible
            pass

        return events

    def cleanup_old_logs(self) -> None:
        """Clean up audit logs older than retention period."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=self.retention_days)

        # This is a simplified implementation
        # In production, this would be more sophisticated
        if self.log_file.exists():
            try:
                # Read all events
                events = []
                with open(self.log_file, "r") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            event_data = json.loads(line.strip())
                            event_time = datetime.fromisoformat(event_data["timestamp"])
                            if event_time >= cutoff_time:
                                events.append(line.strip())
                        except (json.JSONDecodeError, KeyError, ValueError):
                            continue

                # Write back only recent events
                with open(self.log_file, "w") as f:
                    for event_line in events:
                        f.write(event_line + "\n")

            except IOError:
                pass


# Global audit logger instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get the global audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


def configure_audit_logger(
    log_file: Optional[Path] = None,
    enable_console: bool = True,
    enable_structured: bool = True,
    retention_days: int = 365,
) -> None:
    """Configure the global audit logger."""
    global _audit_logger
    _audit_logger = AuditLogger(
        log_file=log_file,
        enable_console=enable_console,
        enable_structured=enable_structured,
        retention_days=retention_days,
    )
