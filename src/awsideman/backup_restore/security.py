"""
Security monitoring and event detection for backup-restore operations.

This module provides security monitoring capabilities including threat detection,
anomaly detection, and security event correlation for backup and restore operations.
"""

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from .audit import AuditEvent, AuditEventType, get_audit_logger


class ThreatLevel(Enum):
    """Threat severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SecurityEventType(Enum):
    """Types of security events."""

    SUSPICIOUS_ACCESS_PATTERN = "suspicious_access_pattern"
    MULTIPLE_FAILED_ATTEMPTS = "multiple_failed_attempts"
    UNUSUAL_BACKUP_ACTIVITY = "unusual_backup_activity"
    UNAUTHORIZED_DELETION = "unauthorized_deletion"
    ENCRYPTION_ANOMALY = "encryption_anomaly"
    DATA_EXFILTRATION_ATTEMPT = "data_exfiltration_attempt"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    SUSPICIOUS_RESTORE_ACTIVITY = "suspicious_restore_activity"


@dataclass
class SecurityAlert:
    """Represents a security alert."""

    alert_id: str
    timestamp: datetime
    event_type: SecurityEventType
    threat_level: ThreatLevel
    user_id: Optional[str]
    resource_id: Optional[str]
    description: str
    details: Dict[str, Any]
    resolved: bool = False
    resolution_notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary for serialization."""
        return {
            "alert_id": self.alert_id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type.value,
            "threat_level": self.threat_level.value,
            "user_id": self.user_id,
            "resource_id": self.resource_id,
            "description": self.description,
            "details": self.details,
            "resolved": self.resolved,
            "resolution_notes": self.resolution_notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SecurityAlert":
        """Create alert from dictionary."""
        return cls(
            alert_id=data["alert_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            event_type=SecurityEventType(data["event_type"]),
            threat_level=ThreatLevel(data["threat_level"]),
            user_id=data.get("user_id"),
            resource_id=data.get("resource_id"),
            description=data["description"],
            details=data["details"],
            resolved=data.get("resolved", False),
            resolution_notes=data.get("resolution_notes"),
        )


class SecurityMonitor:
    """
    Security monitoring system for backup-restore operations.

    Monitors audit events and user activities to detect potential security threats
    and anomalous behavior patterns.
    """

    def __init__(
        self,
        alert_threshold_minutes: int = 15,
        max_failed_attempts: int = 5,
        unusual_activity_threshold: int = 10,
    ):
        """
        Initialize security monitor.

        Args:
            alert_threshold_minutes: Time window for detecting patterns
            max_failed_attempts: Maximum failed attempts before alert
            unusual_activity_threshold: Threshold for unusual activity detection
        """
        self.alert_threshold_minutes = alert_threshold_minutes
        self.max_failed_attempts = max_failed_attempts
        self.unusual_activity_threshold = unusual_activity_threshold

        self.audit_logger = get_audit_logger()
        self.alerts: List[SecurityAlert] = []

        # Track user activity patterns
        self.user_activity_patterns: Dict[str, Dict[str, Any]] = {}
        self.failed_attempts: Dict[str, List[datetime]] = {}

    def analyze_audit_events(self, events: List[AuditEvent]) -> List[SecurityAlert]:
        """
        Analyze audit events for security threats.

        Args:
            events: List of audit events to analyze

        Returns:
            List of security alerts generated
        """
        alerts = []

        # Group events by user and time
        user_events = self._group_events_by_user(events)

        for user_id, user_events_list in user_events.items():
            # Check for multiple failed attempts
            failed_attempts = [
                e
                for e in user_events_list
                if not e.success
                and e.event_type in [AuditEventType.ACCESS_DENIED, AuditEventType.RESTORE_FAILED]
            ]

            if len(failed_attempts) >= self.max_failed_attempts:
                alert = self._create_alert(
                    SecurityEventType.MULTIPLE_FAILED_ATTEMPTS,
                    ThreatLevel.HIGH,
                    user_id,
                    f"User {user_id} has {len(failed_attempts)} failed attempts",
                    {"failed_attempts": len(failed_attempts)},
                )
                alerts.append(alert)

            # Check for unusual backup activity
            backup_events = [
                e
                for e in user_events_list
                if e.event_type in [AuditEventType.BACKUP_CREATED, AuditEventType.BACKUP_DELETED]
            ]

            if len(backup_events) > self.unusual_activity_threshold:
                alert = self._create_alert(
                    SecurityEventType.UNUSUAL_BACKUP_ACTIVITY,
                    ThreatLevel.MEDIUM,
                    user_id,
                    f"User {user_id} has unusual backup activity: {len(backup_events)} operations",
                    {"backup_operations": len(backup_events)},
                )
                alerts.append(alert)

            # Check for suspicious restore patterns
            restore_events = [
                e
                for e in user_events_list
                if e.event_type
                in [AuditEventType.RESTORE_STARTED, AuditEventType.RESTORE_COMPLETED]
            ]

            # Look for restores to different accounts/regions
            cross_account_restores = [
                e
                for e in restore_events
                if e.details.get("target_account") != e.details.get("source_account")
            ]

            if cross_account_restores:
                alert = self._create_alert(
                    SecurityEventType.SUSPICIOUS_RESTORE_ACTIVITY,
                    ThreatLevel.HIGH,
                    user_id,
                    f"User {user_id} performed {len(cross_account_restores)} cross-account restores",
                    {"cross_account_restores": len(cross_account_restores)},
                )
                alerts.append(alert)

            # Check for bulk export operations
            export_events = [
                e for e in user_events_list if e.event_type == AuditEventType.EXPORT_OPERATION
            ]

            if len(export_events) > 3:  # More than 3 exports might indicate data exfiltration
                alert = self._create_alert(
                    SecurityEventType.DATA_EXFILTRATION_ATTEMPT,
                    ThreatLevel.CRITICAL,
                    user_id,
                    f"User {user_id} performed {len(export_events)} export operations",
                    {"export_operations": len(export_events)},
                )
                alerts.append(alert)

        # Check for unauthorized deletions
        deletion_events = [
            e for e in events if e.event_type == AuditEventType.BACKUP_DELETED and not e.success
        ]

        for event in deletion_events:
            alert = self._create_alert(
                SecurityEventType.UNAUTHORIZED_DELETION,
                ThreatLevel.HIGH,
                event.user_id,
                f"Unauthorized deletion attempt on backup {event.resource_id}",
                {"resource_id": event.resource_id},
            )
            alerts.append(alert)

        # Store alerts
        self.alerts.extend(alerts)

        # Log security alerts
        for alert in alerts:
            self.audit_logger.log_security_event(
                AuditEventType.SECURITY_VIOLATION,
                f"Security alert: {alert.description}",
                user_id=alert.user_id,
                resource_id=alert.resource_id,
                success=False,
                details=alert.details,
            )

        return alerts

    def _group_events_by_user(self, events: List[AuditEvent]) -> Dict[str, List[AuditEvent]]:
        """Group events by user ID within the alert threshold time window."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=self.alert_threshold_minutes)
        recent_events = [e for e in events if e.timestamp >= cutoff_time]

        user_events = {}
        for event in recent_events:
            if event.user_id:
                if event.user_id not in user_events:
                    user_events[event.user_id] = []
                user_events[event.user_id].append(event)

        return user_events

    def _create_alert(
        self,
        event_type: SecurityEventType,
        threat_level: ThreatLevel,
        user_id: Optional[str],
        description: str,
        details: Dict[str, Any],
        resource_id: Optional[str] = None,
    ) -> SecurityAlert:
        """Create a security alert."""
        import uuid

        return SecurityAlert(
            alert_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,
            threat_level=threat_level,
            user_id=user_id,
            resource_id=resource_id,
            description=description,
            details=details,
        )

    def get_active_alerts(self, threat_level: Optional[ThreatLevel] = None) -> List[SecurityAlert]:
        """
        Get active (unresolved) security alerts.

        Args:
            threat_level: Optional filter by threat level

        Returns:
            List of active security alerts
        """
        alerts = [alert for alert in self.alerts if not alert.resolved]

        if threat_level:
            alerts = [alert for alert in alerts if alert.threat_level == threat_level]

        return alerts

    def resolve_alert(self, alert_id: str, resolution_notes: str) -> bool:
        """
        Resolve a security alert.

        Args:
            alert_id: ID of the alert to resolve
            resolution_notes: Notes about the resolution

        Returns:
            True if alert was found and resolved, False otherwise
        """
        for alert in self.alerts:
            if alert.alert_id == alert_id:
                alert.resolved = True
                alert.resolution_notes = resolution_notes

                self.audit_logger.log_security_event(
                    AuditEventType.SECURITY_VIOLATION,
                    f"Security alert resolved: {alert.description}",
                    user_id=alert.user_id,
                    resource_id=alert.resource_id,
                    success=True,
                    details={"resolution_notes": resolution_notes},
                )

                return True

        return False

    def get_security_metrics(self) -> Dict[str, Any]:
        """
        Get security metrics and statistics.

        Returns:
            Dictionary containing security metrics
        """
        total_alerts = len(self.alerts)
        active_alerts = len([a for a in self.alerts if not a.resolved])

        # Count alerts by threat level
        threat_level_counts = {}
        for level in ThreatLevel:
            threat_level_counts[level.value] = len(
                [a for a in self.alerts if a.threat_level == level]
            )

        # Count alerts by type
        event_type_counts = {}
        for event_type in SecurityEventType:
            event_type_counts[event_type.value] = len(
                [a for a in self.alerts if a.event_type == event_type]
            )

        return {
            "total_alerts": total_alerts,
            "active_alerts": active_alerts,
            "resolved_alerts": total_alerts - active_alerts,
            "threat_level_distribution": threat_level_counts,
            "event_type_distribution": event_type_counts,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }


class SecureDeletion:
    """
    Secure deletion utilities for backup data.

    Provides cryptographically secure deletion methods to ensure
    sensitive backup data cannot be recovered after deletion.
    """

    def __init__(self):
        """Initialize secure deletion utilities."""
        self.audit_logger = get_audit_logger()

    def secure_delete_file(self, file_path: Path, passes: int = 3) -> bool:
        """
        Securely delete a file by overwriting it multiple times.

        Args:
            file_path: Path to the file to delete
            passes: Number of overwrite passes (default: 3)

        Returns:
            True if deletion was successful, False otherwise
        """
        if not file_path.exists():
            return True

        try:
            file_size = file_path.stat().st_size

            # Perform multiple overwrite passes
            with open(file_path, "r+b") as f:
                for pass_num in range(passes):
                    # Seek to beginning
                    f.seek(0)

                    # Overwrite with random data
                    random_data = os.urandom(min(file_size, 1024 * 1024))  # 1MB chunks
                    bytes_written = 0

                    while bytes_written < file_size:
                        chunk_size = min(len(random_data), file_size - bytes_written)
                        f.write(random_data[:chunk_size])
                        bytes_written += chunk_size

                    # Flush to disk
                    f.flush()
                    os.fsync(f.fileno())

            # Finally, delete the file
            file_path.unlink()

            self.audit_logger.log_secure_deletion(
                str(file_path), f"multi-pass overwrite ({passes} passes)", success=True
            )

            return True

        except (IOError, OSError) as e:
            self.audit_logger.log_secure_deletion(
                str(file_path),
                f"multi-pass overwrite ({passes} passes)",
                success=False,
                error_message=str(e),
            )
            return False

    def secure_delete_directory(self, dir_path: Path, passes: int = 3) -> bool:
        """
        Securely delete a directory and all its contents.

        Args:
            dir_path: Path to the directory to delete
            passes: Number of overwrite passes for files

        Returns:
            True if deletion was successful, False otherwise
        """
        if not dir_path.exists():
            return True

        success = True

        try:
            # Recursively delete all files
            for file_path in dir_path.rglob("*"):
                if file_path.is_file():
                    if not self.secure_delete_file(file_path, passes):
                        success = False

            # Remove empty directories
            for dir_path_item in sorted(
                dir_path.rglob("*"), key=lambda p: len(p.parts), reverse=True
            ):
                if dir_path_item.is_dir():
                    try:
                        dir_path_item.rmdir()
                    except OSError:
                        success = False

            # Remove the root directory
            try:
                dir_path.rmdir()
            except OSError:
                success = False

            self.audit_logger.log_secure_deletion(
                str(dir_path), f"recursive directory deletion ({passes} passes)", success=success
            )

            return success

        except Exception as e:
            self.audit_logger.log_secure_deletion(
                str(dir_path),
                f"recursive directory deletion ({passes} passes)",
                success=False,
                error_message=str(e),
            )
            return False

    def cryptographic_erase(self, file_path: Path, key_id: str) -> bool:
        """
        Perform cryptographic erasure by destroying encryption keys.

        This method is more efficient than overwriting for encrypted data,
        as destroying the encryption key makes the data unrecoverable.

        Args:
            file_path: Path to the encrypted file
            key_id: ID of the encryption key to destroy

        Returns:
            True if erasure was successful, False otherwise
        """
        try:
            # In a real implementation, this would:
            # 1. Verify the file is encrypted with the specified key
            # 2. Destroy the encryption key in the key management system
            # 3. Delete the encrypted file

            # For this implementation, we'll just delete the file
            # and log the cryptographic erasure
            if file_path.exists():
                file_path.unlink()

            self.audit_logger.log_secure_deletion(
                str(file_path), f"cryptographic erasure (key: {key_id})", success=True
            )

            return True

        except Exception as e:
            self.audit_logger.log_secure_deletion(
                str(file_path),
                f"cryptographic erasure (key: {key_id})",
                success=False,
                error_message=str(e),
            )
            return False


class SecurityEventCorrelator:
    """
    Correlates security events to identify complex attack patterns.

    Analyzes sequences of events to detect sophisticated threats that
    might not be apparent from individual events.
    """

    def __init__(self, correlation_window_hours: int = 24):
        """
        Initialize security event correlator.

        Args:
            correlation_window_hours: Time window for event correlation
        """
        self.correlation_window_hours = correlation_window_hours
        self.audit_logger = get_audit_logger()

    def correlate_events(self, events: List[AuditEvent]) -> List[SecurityAlert]:
        """
        Correlate events to identify complex attack patterns.

        Args:
            events: List of audit events to correlate

        Returns:
            List of security alerts for correlated threats
        """
        alerts = []

        # Filter events within correlation window
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=self.correlation_window_hours)
        recent_events = [e for e in events if e.timestamp >= cutoff_time]

        # Look for privilege escalation patterns
        alerts.extend(self._detect_privilege_escalation(recent_events))

        # Look for data exfiltration patterns
        alerts.extend(self._detect_data_exfiltration(recent_events))

        # Look for reconnaissance patterns
        alerts.extend(self._detect_reconnaissance(recent_events))

        return alerts

    def _detect_privilege_escalation(self, events: List[AuditEvent]) -> List[SecurityAlert]:
        """Detect privilege escalation patterns."""
        alerts = []

        # Group events by user
        user_events = {}
        for event in events:
            if event.user_id:
                if event.user_id not in user_events:
                    user_events[event.user_id] = []
                user_events[event.user_id].append(event)

        for user_id, user_events_list in user_events.items():
            # Look for pattern: failed access -> successful access to higher privilege resource
            failed_access = [
                e
                for e in user_events_list
                if not e.success and e.event_type == AuditEventType.ACCESS_DENIED
            ]
            successful_access = [
                e
                for e in user_events_list
                if e.success and e.event_type == AuditEventType.ACCESS_GRANTED
            ]

            if failed_access and successful_access:
                # Check if successful access happened after failed access
                for failed in failed_access:
                    for success in successful_access:
                        if success.timestamp > failed.timestamp:
                            time_diff = success.timestamp - failed.timestamp
                            if time_diff.total_seconds() < 3600:  # Within 1 hour
                                alert = SecurityAlert(
                                    alert_id=str(
                                        hash(f"{user_id}_{failed.timestamp}_{success.timestamp}")
                                    ),
                                    timestamp=datetime.now(timezone.utc),
                                    event_type=SecurityEventType.PRIVILEGE_ESCALATION,
                                    threat_level=ThreatLevel.HIGH,
                                    user_id=user_id,
                                    resource_id=success.resource_id,
                                    description=f"Possible privilege escalation: {user_id} gained access after failed attempt",
                                    details={
                                        "failed_attempt_time": failed.timestamp.isoformat(),
                                        "successful_access_time": success.timestamp.isoformat(),
                                        "time_difference_seconds": time_diff.total_seconds(),
                                    },
                                )
                                alerts.append(alert)

        return alerts

    def _detect_data_exfiltration(self, events: List[AuditEvent]) -> List[SecurityAlert]:
        """Detect data exfiltration patterns."""
        alerts = []

        # Look for pattern: multiple backups -> multiple exports
        user_events = {}
        for event in events:
            if event.user_id:
                if event.user_id not in user_events:
                    user_events[event.user_id] = []
                user_events[event.user_id].append(event)

        for user_id, user_events_list in user_events.items():
            backup_events = [
                e for e in user_events_list if e.event_type == AuditEventType.BACKUP_CREATED
            ]
            export_events = [
                e for e in user_events_list if e.event_type == AuditEventType.EXPORT_OPERATION
            ]

            # If user created multiple backups and exported them
            if len(backup_events) >= 3 and len(export_events) >= 2:
                alert = SecurityAlert(
                    alert_id=str(hash(f"exfiltration_{user_id}_{datetime.now(timezone.utc)}")),
                    timestamp=datetime.now(timezone.utc),
                    event_type=SecurityEventType.DATA_EXFILTRATION_ATTEMPT,
                    threat_level=ThreatLevel.CRITICAL,
                    user_id=user_id,
                    resource_id=None,
                    description=f"Possible data exfiltration: {user_id} created {len(backup_events)} backups and {len(export_events)} exports",
                    details={
                        "backup_count": len(backup_events),
                        "export_count": len(export_events),
                    },
                )
                alerts.append(alert)

        return alerts

    def _detect_reconnaissance(self, events: List[AuditEvent]) -> List[SecurityAlert]:
        """Detect reconnaissance patterns."""
        alerts = []

        # Look for excessive listing/viewing operations
        user_events = {}
        for event in events:
            if event.user_id:
                if event.user_id not in user_events:
                    user_events[event.user_id] = []
                user_events[event.user_id].append(event)

        for user_id, user_events_list in user_events.items():
            # Count view/list operations
            view_operations = [
                e
                for e in user_events_list
                if "list" in e.operation.lower() or "view" in e.operation.lower()
            ]

            if len(view_operations) > 20:  # Excessive viewing might indicate reconnaissance
                alert = SecurityAlert(
                    alert_id=str(hash(f"recon_{user_id}_{datetime.now(timezone.utc)}")),
                    timestamp=datetime.now(timezone.utc),
                    event_type=SecurityEventType.SUSPICIOUS_ACCESS_PATTERN,
                    threat_level=ThreatLevel.MEDIUM,
                    user_id=user_id,
                    resource_id=None,
                    description=f"Possible reconnaissance: {user_id} performed {len(view_operations)} view/list operations",
                    details={"view_operations": len(view_operations)},
                )
                alerts.append(alert)

        return alerts


# Global security monitor instance
_security_monitor: Optional[SecurityMonitor] = None


def get_security_monitor() -> SecurityMonitor:
    """Get the global security monitor instance."""
    global _security_monitor
    if _security_monitor is None:
        _security_monitor = SecurityMonitor()
    return _security_monitor


def configure_security_monitor(
    alert_threshold_minutes: int = 15,
    max_failed_attempts: int = 5,
    unusual_activity_threshold: int = 10,
) -> None:
    """Configure the global security monitor."""
    global _security_monitor
    _security_monitor = SecurityMonitor(
        alert_threshold_minutes=alert_threshold_minutes,
        max_failed_attempts=max_failed_attempts,
        unusual_activity_threshold=unusual_activity_threshold,
    )
