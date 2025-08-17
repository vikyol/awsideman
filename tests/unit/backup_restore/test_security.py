"""
Unit tests for security monitoring and event detection functionality.

Tests the security monitoring system including threat detection,
anomaly detection, secure deletion, and event correlation.
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from src.awsideman.backup_restore.audit import AuditEvent, AuditEventType, AuditSeverity
from src.awsideman.backup_restore.security import (
    SecureDeletion,
    SecurityAlert,
    SecurityEventCorrelator,
    SecurityEventType,
    SecurityMonitor,
    ThreatLevel,
    configure_security_monitor,
    get_security_monitor,
)


class TestSecurityAlert:
    """Test SecurityAlert data model."""

    def test_security_alert_creation(self):
        """Test creating a security alert."""
        alert = SecurityAlert(
            alert_id="alert-123",
            timestamp=datetime.utcnow(),
            event_type=SecurityEventType.SUSPICIOUS_ACCESS_PATTERN,
            threat_level=ThreatLevel.HIGH,
            user_id="user123",
            resource_id="backup-456",
            description="Suspicious access pattern detected",
            details={"access_count": 10},
        )

        assert alert.alert_id == "alert-123"
        assert alert.event_type == SecurityEventType.SUSPICIOUS_ACCESS_PATTERN
        assert alert.threat_level == ThreatLevel.HIGH
        assert alert.user_id == "user123"
        assert alert.resource_id == "backup-456"
        assert alert.resolved is False

    def test_security_alert_serialization(self):
        """Test security alert serialization to/from dictionary."""
        timestamp = datetime.utcnow()
        alert = SecurityAlert(
            alert_id="alert-123",
            timestamp=timestamp,
            event_type=SecurityEventType.MULTIPLE_FAILED_ATTEMPTS,
            threat_level=ThreatLevel.CRITICAL,
            user_id="user123",
            resource_id="backup-456",
            description="Multiple failed attempts",
            details={"attempt_count": 5},
            resolved=True,
            resolution_notes="False positive",
        )

        # Convert to dict
        alert_dict = alert.to_dict()

        assert alert_dict["alert_id"] == "alert-123"
        assert alert_dict["timestamp"] == timestamp.isoformat()
        assert alert_dict["event_type"] == "multiple_failed_attempts"
        assert alert_dict["threat_level"] == "critical"
        assert alert_dict["user_id"] == "user123"
        assert alert_dict["resolved"] is True
        assert alert_dict["resolution_notes"] == "False positive"

        # Convert back to alert
        restored_alert = SecurityAlert.from_dict(alert_dict)

        assert restored_alert.alert_id == alert.alert_id
        assert restored_alert.timestamp == alert.timestamp
        assert restored_alert.event_type == alert.event_type
        assert restored_alert.threat_level == alert.threat_level
        assert restored_alert.user_id == alert.user_id
        assert restored_alert.resolved == alert.resolved
        assert restored_alert.resolution_notes == alert.resolution_notes


class TestSecurityMonitor:
    """Test SecurityMonitor functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.monitor = SecurityMonitor(
            alert_threshold_minutes=15, max_failed_attempts=3, unusual_activity_threshold=5
        )

    def test_security_monitor_initialization(self):
        """Test security monitor initialization."""
        assert self.monitor.alert_threshold_minutes == 15
        assert self.monitor.max_failed_attempts == 3
        assert self.monitor.unusual_activity_threshold == 5
        assert len(self.monitor.alerts) == 0

    def test_analyze_multiple_failed_attempts(self):
        """Test detection of multiple failed attempts."""
        # Create events with multiple failed attempts
        events = []
        user_id = "suspicious_user"

        for i in range(5):  # More than max_failed_attempts (3)
            event = AuditEvent(
                event_id=f"failed-{i}",
                timestamp=datetime.utcnow(),
                event_type=AuditEventType.ACCESS_DENIED,
                severity=AuditSeverity.WARNING,
                user_id=user_id,
                session_id=None,
                source_ip=None,
                resource_id=f"backup-{i}",
                resource_type="backup",
                operation="access_backup",
                details={},
                success=False,
            )
            events.append(event)

        alerts = self.monitor.analyze_audit_events(events)

        # Should generate alert for multiple failed attempts
        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.event_type == SecurityEventType.MULTIPLE_FAILED_ATTEMPTS
        assert alert.threat_level == ThreatLevel.HIGH
        assert alert.user_id == user_id
        assert "5 failed attempts" in alert.description

    def test_analyze_unusual_backup_activity(self):
        """Test detection of unusual backup activity."""
        # Create events with excessive backup operations
        events = []
        user_id = "busy_user"

        for i in range(7):  # More than unusual_activity_threshold (5)
            event = AuditEvent(
                event_id=f"backup-{i}",
                timestamp=datetime.utcnow(),
                event_type=AuditEventType.BACKUP_CREATED,
                severity=AuditSeverity.INFO,
                user_id=user_id,
                session_id=None,
                source_ip=None,
                resource_id=f"backup-{i}",
                resource_type="backup",
                operation="create_backup",
                details={},
                success=True,
            )
            events.append(event)

        alerts = self.monitor.analyze_audit_events(events)

        # Should generate alert for unusual backup activity
        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.event_type == SecurityEventType.UNUSUAL_BACKUP_ACTIVITY
        assert alert.threat_level == ThreatLevel.MEDIUM
        assert alert.user_id == user_id
        assert "7 operations" in alert.description

    def test_analyze_suspicious_restore_activity(self):
        """Test detection of suspicious restore activity."""
        # Create events with cross-account restores
        events = []
        user_id = "restore_user"

        for i in range(3):
            event = AuditEvent(
                event_id=f"restore-{i}",
                timestamp=datetime.utcnow(),
                event_type=AuditEventType.RESTORE_STARTED,
                severity=AuditSeverity.INFO,
                user_id=user_id,
                session_id=None,
                source_ip=None,
                resource_id=f"backup-{i}",
                resource_type="backup",
                operation="restore_backup",
                details={
                    "source_account": "123456789012",
                    "target_account": "987654321098",  # Different account
                },
                success=True,
            )
            events.append(event)

        alerts = self.monitor.analyze_audit_events(events)

        # Should generate alert for suspicious restore activity
        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.event_type == SecurityEventType.SUSPICIOUS_RESTORE_ACTIVITY
        assert alert.threat_level == ThreatLevel.HIGH
        assert alert.user_id == user_id
        assert "cross-account restores" in alert.description

    def test_analyze_data_exfiltration_attempt(self):
        """Test detection of data exfiltration attempts."""
        # Create events with multiple export operations
        events = []
        user_id = "export_user"

        for i in range(5):  # More than 3 exports
            event = AuditEvent(
                event_id=f"export-{i}",
                timestamp=datetime.utcnow(),
                event_type=AuditEventType.EXPORT_OPERATION,
                severity=AuditSeverity.INFO,
                user_id=user_id,
                session_id=None,
                source_ip=None,
                resource_id=f"backup-{i}",
                resource_type="backup",
                operation="export_backup",
                details={},
                success=True,
            )
            events.append(event)

        alerts = self.monitor.analyze_audit_events(events)

        # Should generate alert for data exfiltration attempt
        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.event_type == SecurityEventType.DATA_EXFILTRATION_ATTEMPT
        assert alert.threat_level == ThreatLevel.CRITICAL
        assert alert.user_id == user_id
        assert "5 export operations" in alert.description

    def test_analyze_unauthorized_deletion(self):
        """Test detection of unauthorized deletion attempts."""
        # Create events with failed deletion attempts
        events = [
            AuditEvent(
                event_id="delete-fail-1",
                timestamp=datetime.utcnow(),
                event_type=AuditEventType.BACKUP_DELETED,
                severity=AuditSeverity.ERROR,
                user_id="unauthorized_user",
                session_id=None,
                source_ip=None,
                resource_id="backup-123",
                resource_type="backup",
                operation="delete_backup",
                details={},
                success=False,
            )
        ]

        alerts = self.monitor.analyze_audit_events(events)

        # Should generate alert for unauthorized deletion
        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.event_type == SecurityEventType.UNAUTHORIZED_DELETION
        assert alert.threat_level == ThreatLevel.HIGH
        assert alert.user_id == "unauthorized_user"
        assert "backup-123" in alert.description

    def test_get_active_alerts(self):
        """Test getting active alerts."""
        # Create some alerts
        alert1 = SecurityAlert(
            alert_id="alert-1",
            timestamp=datetime.utcnow(),
            event_type=SecurityEventType.SUSPICIOUS_ACCESS_PATTERN,
            threat_level=ThreatLevel.HIGH,
            user_id="user1",
            resource_id="backup-1",
            description="Alert 1",
            details={},
        )

        alert2 = SecurityAlert(
            alert_id="alert-2",
            timestamp=datetime.utcnow(),
            event_type=SecurityEventType.MULTIPLE_FAILED_ATTEMPTS,
            threat_level=ThreatLevel.CRITICAL,
            user_id="user2",
            resource_id="backup-2",
            description="Alert 2",
            details={},
            resolved=True,
        )

        alert3 = SecurityAlert(
            alert_id="alert-3",
            timestamp=datetime.utcnow(),
            event_type=SecurityEventType.UNUSUAL_BACKUP_ACTIVITY,
            threat_level=ThreatLevel.MEDIUM,
            user_id="user3",
            resource_id="backup-3",
            description="Alert 3",
            details={},
        )

        self.monitor.alerts = [alert1, alert2, alert3]

        # Get all active alerts
        active_alerts = self.monitor.get_active_alerts()
        assert len(active_alerts) == 2  # alert1 and alert3 (alert2 is resolved)

        # Get active alerts by threat level
        high_alerts = self.monitor.get_active_alerts(ThreatLevel.HIGH)
        assert len(high_alerts) == 1
        assert high_alerts[0].alert_id == "alert-1"

    def test_resolve_alert(self):
        """Test resolving security alerts."""
        alert = SecurityAlert(
            alert_id="alert-123",
            timestamp=datetime.utcnow(),
            event_type=SecurityEventType.SUSPICIOUS_ACCESS_PATTERN,
            threat_level=ThreatLevel.HIGH,
            user_id="user1",
            resource_id="backup-1",
            description="Test alert",
            details={},
        )

        self.monitor.alerts = [alert]

        # Resolve alert
        result = self.monitor.resolve_alert("alert-123", "False positive")
        assert result is True
        assert alert.resolved is True
        assert alert.resolution_notes == "False positive"

        # Try to resolve non-existent alert
        result = self.monitor.resolve_alert("nonexistent", "Notes")
        assert result is False

    def test_get_security_metrics(self):
        """Test getting security metrics."""
        # Create alerts with different types and levels
        alerts = [
            SecurityAlert(
                "1",
                datetime.utcnow(),
                SecurityEventType.SUSPICIOUS_ACCESS_PATTERN,
                ThreatLevel.HIGH,
                "user1",
                "backup-1",
                "Alert 1",
                {},
            ),
            SecurityAlert(
                "2",
                datetime.utcnow(),
                SecurityEventType.MULTIPLE_FAILED_ATTEMPTS,
                ThreatLevel.CRITICAL,
                "user2",
                "backup-2",
                "Alert 2",
                {},
                resolved=True,
            ),
            SecurityAlert(
                "3",
                datetime.utcnow(),
                SecurityEventType.UNUSUAL_BACKUP_ACTIVITY,
                ThreatLevel.MEDIUM,
                "user3",
                "backup-3",
                "Alert 3",
                {},
            ),
        ]

        self.monitor.alerts = alerts

        metrics = self.monitor.get_security_metrics()

        assert metrics["total_alerts"] == 3
        assert metrics["active_alerts"] == 2
        assert metrics["resolved_alerts"] == 1
        assert metrics["threat_level_distribution"]["high"] == 1
        assert metrics["threat_level_distribution"]["critical"] == 1
        assert metrics["threat_level_distribution"]["medium"] == 1
        assert metrics["event_type_distribution"]["suspicious_access_pattern"] == 1


class TestSecureDeletion:
    """Test SecureDeletion functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.secure_deletion = SecureDeletion()
        self.temp_dir = tempfile.mkdtemp()

    def test_secure_delete_file_success(self):
        """Test successful secure file deletion."""
        # Create test file
        test_file = Path(self.temp_dir) / "test_file.txt"
        test_content = "sensitive data" * 100
        test_file.write_text(test_content)

        assert test_file.exists()

        # Secure delete
        result = self.secure_deletion.secure_delete_file(test_file, passes=2)

        assert result is True
        assert not test_file.exists()

    def test_secure_delete_file_nonexistent(self):
        """Test secure deletion of non-existent file."""
        nonexistent_file = Path(self.temp_dir) / "nonexistent.txt"

        # Should return True (already deleted)
        result = self.secure_deletion.secure_delete_file(nonexistent_file)
        assert result is True

    @patch("builtins.open", side_effect=IOError("Permission denied"))
    def test_secure_delete_file_failure(self, mock_open):
        """Test secure file deletion failure."""
        test_file = Path(self.temp_dir) / "test_file.txt"
        test_file.write_text("test content")

        result = self.secure_deletion.secure_delete_file(test_file)
        assert result is False

    def test_secure_delete_directory_success(self):
        """Test successful secure directory deletion."""
        # Create test directory with files
        test_dir = Path(self.temp_dir) / "test_dir"
        test_dir.mkdir()

        # Create files in directory
        (test_dir / "file1.txt").write_text("content1")
        (test_dir / "file2.txt").write_text("content2")

        # Create subdirectory with file
        subdir = test_dir / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").write_text("content3")

        assert test_dir.exists()

        # Secure delete directory
        result = self.secure_deletion.secure_delete_directory(test_dir, passes=1)

        assert result is True
        assert not test_dir.exists()

    def test_secure_delete_directory_nonexistent(self):
        """Test secure deletion of non-existent directory."""
        nonexistent_dir = Path(self.temp_dir) / "nonexistent"

        # Should return True (already deleted)
        result = self.secure_deletion.secure_delete_directory(nonexistent_dir)
        assert result is True

    def test_cryptographic_erase(self):
        """Test cryptographic erasure."""
        # Create test file
        test_file = Path(self.temp_dir) / "encrypted_file.dat"
        test_file.write_bytes(b"encrypted data")

        assert test_file.exists()

        # Perform cryptographic erase
        result = self.secure_deletion.cryptographic_erase(test_file, "key-123")

        assert result is True
        assert not test_file.exists()

    def test_cryptographic_erase_nonexistent(self):
        """Test cryptographic erasure of non-existent file."""
        nonexistent_file = Path(self.temp_dir) / "nonexistent.dat"

        # Should return True (already deleted)
        result = self.secure_deletion.cryptographic_erase(nonexistent_file, "key-123")
        assert result is True


class TestSecurityEventCorrelator:
    """Test SecurityEventCorrelator functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.correlator = SecurityEventCorrelator(correlation_window_hours=24)

    def test_correlator_initialization(self):
        """Test security event correlator initialization."""
        assert self.correlator.correlation_window_hours == 24

    def test_detect_privilege_escalation(self):
        """Test detection of privilege escalation patterns."""
        user_id = "escalation_user"
        base_time = datetime.utcnow()

        # Create pattern: failed access followed by successful access
        events = [
            AuditEvent(
                event_id="failed-access",
                timestamp=base_time,
                event_type=AuditEventType.ACCESS_DENIED,
                severity=AuditSeverity.WARNING,
                user_id=user_id,
                session_id=None,
                source_ip=None,
                resource_id="backup-123",
                resource_type="backup",
                operation="access_backup",
                details={},
                success=False,
            ),
            AuditEvent(
                event_id="successful-access",
                timestamp=base_time + timedelta(minutes=30),
                event_type=AuditEventType.ACCESS_GRANTED,
                severity=AuditSeverity.INFO,
                user_id=user_id,
                session_id=None,
                source_ip=None,
                resource_id="backup-456",
                resource_type="backup",
                operation="access_backup",
                details={},
                success=True,
            ),
        ]

        alerts = self.correlator.correlate_events(events)

        # Should detect privilege escalation
        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.event_type == SecurityEventType.PRIVILEGE_ESCALATION
        assert alert.threat_level == ThreatLevel.HIGH
        assert alert.user_id == user_id

    def test_detect_data_exfiltration(self):
        """Test detection of data exfiltration patterns."""
        user_id = "exfiltration_user"
        base_time = datetime.utcnow()

        # Create pattern: multiple backups followed by multiple exports
        events = []

        # Create multiple backup events
        for i in range(3):
            events.append(
                AuditEvent(
                    event_id=f"backup-{i}",
                    timestamp=base_time + timedelta(minutes=i * 10),
                    event_type=AuditEventType.BACKUP_CREATED,
                    severity=AuditSeverity.INFO,
                    user_id=user_id,
                    session_id=None,
                    source_ip=None,
                    resource_id=f"backup-{i}",
                    resource_type="backup",
                    operation="create_backup",
                    details={},
                    success=True,
                )
            )

        # Create multiple export events
        for i in range(2):
            events.append(
                AuditEvent(
                    event_id=f"export-{i}",
                    timestamp=base_time + timedelta(hours=1, minutes=i * 10),
                    event_type=AuditEventType.EXPORT_OPERATION,
                    severity=AuditSeverity.INFO,
                    user_id=user_id,
                    session_id=None,
                    source_ip=None,
                    resource_id=f"backup-{i}",
                    resource_type="backup",
                    operation="export_backup",
                    details={},
                    success=True,
                )
            )

        alerts = self.correlator.correlate_events(events)

        # Should detect data exfiltration
        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.event_type == SecurityEventType.DATA_EXFILTRATION_ATTEMPT
        assert alert.threat_level == ThreatLevel.CRITICAL
        assert alert.user_id == user_id

    def test_detect_reconnaissance(self):
        """Test detection of reconnaissance patterns."""
        user_id = "recon_user"
        base_time = datetime.utcnow()

        # Create excessive view/list operations
        events = []
        for i in range(25):  # More than 20 view operations
            events.append(
                AuditEvent(
                    event_id=f"view-{i}",
                    timestamp=base_time + timedelta(minutes=i),
                    event_type=AuditEventType.ACCESS_GRANTED,
                    severity=AuditSeverity.INFO,
                    user_id=user_id,
                    session_id=None,
                    source_ip=None,
                    resource_id=f"backup-{i}",
                    resource_type="backup",
                    operation="list_backups",
                    details={},
                    success=True,
                )
            )

        alerts = self.correlator.correlate_events(events)

        # Should detect reconnaissance
        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.event_type == SecurityEventType.SUSPICIOUS_ACCESS_PATTERN
        assert alert.threat_level == ThreatLevel.MEDIUM
        assert alert.user_id == user_id

    def test_correlate_events_time_window(self):
        """Test that correlation respects time window."""
        user_id = "test_user"
        base_time = datetime.utcnow()

        # Create events outside correlation window
        old_events = [
            AuditEvent(
                event_id="old-event",
                timestamp=base_time - timedelta(hours=25),  # Outside 24-hour window
                event_type=AuditEventType.ACCESS_DENIED,
                severity=AuditSeverity.WARNING,
                user_id=user_id,
                session_id=None,
                source_ip=None,
                resource_id="backup-old",
                resource_type="backup",
                operation="access_backup",
                details={},
                success=False,
            )
        ]

        alerts = self.correlator.correlate_events(old_events)

        # Should not generate alerts for old events
        assert len(alerts) == 0


class TestGlobalSecurityMonitor:
    """Test global security monitor functions."""

    def test_get_security_monitor(self):
        """Test getting global security monitor."""
        monitor1 = get_security_monitor()
        monitor2 = get_security_monitor()

        # Should return the same instance
        assert monitor1 is monitor2

    def test_configure_security_monitor(self):
        """Test configuring global security monitor."""
        configure_security_monitor(
            alert_threshold_minutes=30, max_failed_attempts=10, unusual_activity_threshold=20
        )

        monitor = get_security_monitor()
        assert monitor.alert_threshold_minutes == 30
        assert monitor.max_failed_attempts == 10
        assert monitor.unusual_activity_threshold == 20


@pytest.fixture
def sample_audit_events():
    """Fixture providing sample audit events for testing."""
    base_time = datetime.utcnow()

    return [
        AuditEvent(
            event_id="event-1",
            timestamp=base_time,
            event_type=AuditEventType.BACKUP_CREATED,
            severity=AuditSeverity.INFO,
            user_id="user1",
            session_id=None,
            source_ip=None,
            resource_id="backup-1",
            resource_type="backup",
            operation="create_backup",
            details={},
            success=True,
        ),
        AuditEvent(
            event_id="event-2",
            timestamp=base_time + timedelta(minutes=5),
            event_type=AuditEventType.ACCESS_DENIED,
            severity=AuditSeverity.WARNING,
            user_id="user2",
            session_id=None,
            source_ip=None,
            resource_id="backup-2",
            resource_type="backup",
            operation="access_backup",
            details={},
            success=False,
        ),
    ]


def test_security_monitor_integration(sample_audit_events):
    """Test security monitor integration with audit events."""
    monitor = SecurityMonitor()

    # Should not generate alerts for normal activity
    alerts = monitor.analyze_audit_events(sample_audit_events)
    assert len(alerts) == 0

    # Add more failed attempts to trigger alert
    failed_events = []
    for i in range(5):
        failed_events.append(
            AuditEvent(
                event_id=f"failed-{i}",
                timestamp=datetime.utcnow(),
                event_type=AuditEventType.ACCESS_DENIED,
                severity=AuditSeverity.WARNING,
                user_id="suspicious_user",
                session_id=None,
                source_ip=None,
                resource_id=f"backup-{i}",
                resource_type="backup",
                operation="access_backup",
                details={},
                success=False,
            )
        )

    alerts = monitor.analyze_audit_events(failed_events)
    assert len(alerts) == 1
    assert alerts[0].event_type == SecurityEventType.MULTIPLE_FAILED_ATTEMPTS


def test_secure_deletion_integration():
    """Test secure deletion integration."""
    temp_dir = tempfile.mkdtemp()
    secure_deletion = SecureDeletion()

    # Create test files
    test_files = []
    for i in range(3):
        test_file = Path(temp_dir) / f"test_file_{i}.txt"
        test_file.write_text(f"sensitive content {i}")
        test_files.append(test_file)

    # Verify files exist
    for test_file in test_files:
        assert test_file.exists()

    # Secure delete all files
    for test_file in test_files:
        result = secure_deletion.secure_delete_file(test_file)
        assert result is True
        assert not test_file.exists()


def test_security_event_correlation_complex_pattern():
    """Test complex security event correlation patterns."""
    correlator = SecurityEventCorrelator()
    user_id = "complex_user"
    base_time = datetime.utcnow()

    # Create complex attack pattern:
    # 1. Failed access attempts (reconnaissance)
    # 2. Successful access (privilege escalation)
    # 3. Multiple backups (data collection)
    # 4. Multiple exports (exfiltration)

    events = []

    # Failed access attempts
    for i in range(3):
        events.append(
            AuditEvent(
                event_id=f"failed-{i}",
                timestamp=base_time + timedelta(minutes=i * 5),
                event_type=AuditEventType.ACCESS_DENIED,
                severity=AuditSeverity.WARNING,
                user_id=user_id,
                session_id=None,
                source_ip=None,
                resource_id=f"backup-{i}",
                resource_type="backup",
                operation="access_backup",
                details={},
                success=False,
            )
        )

    # Successful access
    events.append(
        AuditEvent(
            event_id="successful-access",
            timestamp=base_time + timedelta(minutes=20),
            event_type=AuditEventType.ACCESS_GRANTED,
            severity=AuditSeverity.INFO,
            user_id=user_id,
            session_id=None,
            source_ip=None,
            resource_id="backup-sensitive",
            resource_type="backup",
            operation="access_backup",
            details={},
            success=True,
        )
    )

    # Multiple backups
    for i in range(4):
        events.append(
            AuditEvent(
                event_id=f"backup-{i}",
                timestamp=base_time + timedelta(minutes=30 + i * 5),
                event_type=AuditEventType.BACKUP_CREATED,
                severity=AuditSeverity.INFO,
                user_id=user_id,
                session_id=None,
                source_ip=None,
                resource_id=f"backup-new-{i}",
                resource_type="backup",
                operation="create_backup",
                details={},
                success=True,
            )
        )

    # Multiple exports
    for i in range(3):
        events.append(
            AuditEvent(
                event_id=f"export-{i}",
                timestamp=base_time + timedelta(hours=1, minutes=i * 10),
                event_type=AuditEventType.EXPORT_OPERATION,
                severity=AuditSeverity.INFO,
                user_id=user_id,
                session_id=None,
                source_ip=None,
                resource_id=f"backup-new-{i}",
                resource_type="backup",
                operation="export_backup",
                details={},
                success=True,
            )
        )

    alerts = correlator.correlate_events(events)

    # Should detect multiple threat patterns
    assert len(alerts) >= 2  # At least privilege escalation and data exfiltration

    alert_types = {alert.event_type for alert in alerts}
    assert SecurityEventType.PRIVILEGE_ESCALATION in alert_types
    assert SecurityEventType.DATA_EXFILTRATION_ATTEMPT in alert_types
