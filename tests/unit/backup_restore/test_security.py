"""Tests for security monitoring and alerting functionality."""

from datetime import datetime, timedelta, timezone

from src.awsideman.backup_restore.audit import AuditEvent, AuditEventType, AuditSeverity
from src.awsideman.backup_restore.security import (
    SecurityAlert,
    SecurityEventCorrelator,
    SecurityEventType,
    SecurityMonitor,
    ThreatLevel,
)


class TestSecurityAlert:
    """Test security alert creation and management."""

    def test_security_alert_creation(self):
        """Test creating a security alert."""
        alert = SecurityAlert(
            alert_id="alert-123",
            timestamp=datetime.now(timezone.utc),
            event_type=SecurityEventType.SUSPICIOUS_ACCESS_PATTERN,
            threat_level=ThreatLevel.HIGH,
            user_id="suspicious-user",
            resource_id="backup-456",
            description="Multiple failed login attempts detected",
            details={"attempts": 5, "timeframe": "5 minutes"},
            resolved=False,
        )

        assert alert.alert_id == "alert-123"
        assert alert.event_type == SecurityEventType.SUSPICIOUS_ACCESS_PATTERN
        assert alert.threat_level == ThreatLevel.HIGH
        assert alert.description == "Multiple failed login attempts detected"

    def test_security_alert_serialization(self):
        """Test security alert serialization."""
        timestamp = datetime.now(timezone.utc)
        alert = SecurityAlert(
            alert_id="alert-456",
            timestamp=timestamp,
            event_type=SecurityEventType.DATA_EXFILTRATION_ATTEMPT,
            threat_level=ThreatLevel.CRITICAL,
            user_id="data-user",
            resource_id="backup-789",
            description="Large data export detected",
            details={"export_size": "1GB", "destination": "external"},
            resolved=False,
        )

        alert_dict = alert.to_dict()
        assert alert_dict["alert_id"] == "alert-456"
        assert alert_dict["event_type"] == "data_exfiltration_attempt"
        assert alert_dict["threat_level"] == "critical"
        assert alert_dict["timestamp"] == timestamp.isoformat()


class TestSecurityMonitor:
    """Test security monitoring functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.monitor = SecurityMonitor(
            alert_threshold_minutes=15,
            max_failed_attempts=3,
            unusual_activity_threshold=5,
        )

    def test_analyze_multiple_failed_attempts(self):
        """Test detection of multiple failed attempts."""
        # Create multiple failed access attempts
        events = []
        for i in range(5):
            events.append(
                AuditEvent(
                    event_id=f"event-{i}",
                    timestamp=datetime.now(timezone.utc) - timedelta(minutes=i),
                    event_type=AuditEventType.ACCESS_DENIED,
                    severity=AuditSeverity.WARNING,
                    user_id="test-user",
                    session_id=None,
                    source_ip="192.168.1.100",
                    resource_id=f"backup-{i}",
                    resource_type="backup",
                    operation="access_backup",
                    details={"reason": "invalid_credentials"},
                    success=False,
                )
            )

        # Add one successful attempt
        events.append(
            AuditEvent(
                event_id="event-success",
                timestamp=datetime.now(timezone.utc),
                event_type=AuditEventType.ACCESS_GRANTED,
                severity=AuditSeverity.INFO,
                user_id="test-user",
                session_id=None,
                source_ip="192.168.1.100",
                resource_id="backup-success",
                resource_type="backup",
                operation="access_backup",
                details={"reason": "valid_credentials"},
                success=True,
            )
        )

        alerts = self.monitor.analyze_audit_events(events)
        assert len(alerts) == 1
        assert alerts[0].event_type == SecurityEventType.MULTIPLE_FAILED_ATTEMPTS
        assert alerts[0].threat_level == ThreatLevel.HIGH

    def test_analyze_unusual_backup_activity(self):
        """Test detection of unusual backup activity."""
        # Create unusual backup pattern
        events = []
        for i in range(10):
            events.append(
                AuditEvent(
                    event_id=f"backup-{i}",
                    timestamp=datetime.now(timezone.utc) - timedelta(minutes=i * 2),
                    event_type=AuditEventType.BACKUP_CREATED,
                    severity=AuditSeverity.INFO,
                    user_id="backup-user",
                    session_id=None,
                    source_ip="10.0.0.10",
                    resource_id=f"backup-{i}",
                    resource_type="backup",
                    operation="create_backup",
                    details={"backup_size": "100MB", "type": "full"},
                    success=True,
                )
            )

        alerts = self.monitor.analyze_audit_events(events)
        assert len(alerts) == 1
        assert alerts[0].event_type == SecurityEventType.UNUSUAL_BACKUP_ACTIVITY
        assert alerts[0].threat_level == ThreatLevel.MEDIUM

    def test_analyze_suspicious_restore_activity(self):
        """Test detection of suspicious restore activity."""
        # Create suspicious restore pattern with cross-account restores
        events = []
        for i in range(8):
            events.append(
                AuditEvent(
                    event_id=f"restore-{i}",
                    timestamp=datetime.now(timezone.utc) - timedelta(minutes=i),
                    event_type=AuditEventType.RESTORE_STARTED,
                    severity=AuditSeverity.INFO,
                    user_id="restore-user",
                    session_id=None,
                    source_ip="10.0.0.20",
                    resource_id=f"backup-{i}",
                    resource_type="backup",
                    operation="restore_backup",
                    details={
                        "backup_id": f"backup-{i}",
                        "restore_type": "full",
                        "source_account": "123456789012",
                        "target_account": "987654321098",  # Different account to trigger cross-account alert
                    },
                    success=True,
                )
            )

        alerts = self.monitor.analyze_audit_events(events)
        assert len(alerts) == 1
        assert alerts[0].event_type == SecurityEventType.SUSPICIOUS_RESTORE_ACTIVITY
        assert alerts[0].threat_level == ThreatLevel.HIGH

    def test_analyze_data_exfiltration_attempt(self):
        """Test detection of data exfiltration attempts."""
        # Create data exfiltration pattern with both backups and exports
        events = []
        # Add backup events (need at least 3) - within 15 minute window
        for i in range(3):
            events.append(
                AuditEvent(
                    event_id=f"backup-{i}",
                    timestamp=datetime.now(timezone.utc)
                    - timedelta(minutes=i * 2),  # 0, 2, 4 minutes ago
                    event_type=AuditEventType.BACKUP_CREATED,
                    severity=AuditSeverity.INFO,
                    user_id="export-user",
                    session_id=None,
                    source_ip="10.0.0.30",
                    resource_id=f"backup-{i}",
                    resource_type="backup",
                    operation="create_backup",
                    details={"backup_size": "100MB", "backup_type": "full"},
                    success=True,
                )
            )

        # Add export events (need at least 2) - within 15 minute window
        for i in range(6):
            events.append(
                AuditEvent(
                    event_id=f"export-{i}",
                    timestamp=datetime.now(timezone.utc)
                    - timedelta(minutes=i * 1),  # 0, 1, 2, 3, 4, 5 minutes ago
                    event_type=AuditEventType.EXPORT_OPERATION,
                    severity=AuditSeverity.INFO,
                    user_id="export-user",
                    session_id=None,
                    source_ip="10.0.0.30",
                    resource_id=f"backup-{i}",
                    resource_type="backup",
                    operation="export_backup",
                    details={"export_size": "500MB", "format": "csv"},
                    success=True,
                )
            )

        alerts = self.monitor.analyze_audit_events(events)
        assert len(alerts) == 1
        assert alerts[0].event_type == SecurityEventType.DATA_EXFILTRATION_ATTEMPT
        assert alerts[0].threat_level == ThreatLevel.CRITICAL

    def test_analyze_unauthorized_deletion(self):
        """Test detection of unauthorized deletion attempts."""
        # Create unauthorized deletion pattern
        events = [
            AuditEvent(
                event_id="delete-attempt",
                timestamp=datetime.now(timezone.utc),
                event_type=AuditEventType.BACKUP_DELETED,
                severity=AuditSeverity.ERROR,
                user_id="delete-user",
                session_id=None,
                source_ip="10.0.0.40",
                resource_id="backup-123",
                resource_type="backup",
                operation="delete_backup",
                details={"backup_id": "backup-123", "reason": "cleanup"},
                success=False,
            )
        ]

        alerts = self.monitor.analyze_audit_events(events)
        assert len(alerts) == 1
        assert alerts[0].event_type == SecurityEventType.UNAUTHORIZED_DELETION
        assert alerts[0].threat_level == ThreatLevel.HIGH

    def test_get_active_alerts(self):
        """Test retrieving active security alerts."""
        # Create some alerts
        alert1 = SecurityAlert(
            alert_id="alert-1",
            timestamp=datetime.now(timezone.utc),
            event_type=SecurityEventType.SUSPICIOUS_ACCESS_PATTERN,
            threat_level=ThreatLevel.HIGH,
            user_id="user1",
            resource_id="backup-1",
            description="Test alert 1",
            details={},
            resolved=False,
        )

        alert2 = SecurityAlert(
            alert_id="alert-2",
            timestamp=datetime.now(timezone.utc),
            event_type=SecurityEventType.DATA_EXFILTRATION_ATTEMPT,
            threat_level=ThreatLevel.CRITICAL,
            user_id="user2",
            resource_id="backup-2",
            description="Test alert 2",
            details={},
            resolved=False,
        )

        # Add alerts to monitor
        self.monitor.alerts = [alert1, alert2]

        # Test filtering by threat level
        high_alerts = self.monitor.get_active_alerts(ThreatLevel.HIGH)
        assert len(high_alerts) == 1
        assert high_alerts[0].alert_id == "alert-1"

        # Test filtering by threat level only (method doesn't support event_type filtering)
        critical_alerts = self.monitor.get_active_alerts(ThreatLevel.CRITICAL)
        assert len(critical_alerts) == 1
        assert critical_alerts[0].alert_id == "alert-2"

    def test_resolve_alert(self):
        """Test resolving security alerts."""
        alert = SecurityAlert(
            alert_id="alert-resolve",
            timestamp=datetime.now(timezone.utc),
            event_type=SecurityEventType.SUSPICIOUS_ACCESS_PATTERN,
            threat_level=ThreatLevel.MEDIUM,
            user_id="user1",
            resource_id="backup-1",
            description="Test alert to resolve",
            details={},
            resolved=False,
        )

        self.monitor.alerts = [alert]
        assert len(self.monitor.alerts) == 1

        # Resolve the alert
        result = self.monitor.resolve_alert("alert-resolve", "False positive")
        assert result is True
        assert alert.resolved is True
        assert alert.resolution_notes == "False positive"

    def test_get_security_metrics(self):
        """Test retrieving security metrics."""
        # Create some test alerts
        alerts = []
        for i in range(5):
            alerts.append(
                SecurityAlert(
                    alert_id=f"alert-{i}",
                    timestamp=datetime.now(timezone.utc),
                    event_type=SecurityEventType.SUSPICIOUS_ACCESS_PATTERN,
                    threat_level=ThreatLevel.HIGH,
                    user_id=f"user{i}",
                    resource_id=f"backup-{i}",
                    description=f"Test alert {i}",
                    details={},
                    resolved=False,
                )
            )

        self.monitor.alerts = alerts

        metrics = self.monitor.get_security_metrics()
        assert metrics["total_alerts"] == 5
        assert metrics["active_alerts"] == 5
        assert metrics["threat_level_distribution"]["high"] == 5


class TestSecurityEventCorrelator:
    """Test security event correlation functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.correlator = SecurityEventCorrelator(correlation_window_hours=2)

    def test_detect_privilege_escalation(self):
        """Test detection of privilege escalation patterns."""
        base_time = datetime.now(timezone.utc)

        # Create events showing privilege escalation
        events = [
            AuditEvent(
                event_id="event-1",
                timestamp=base_time - timedelta(hours=1),
                event_type=AuditEventType.ACCESS_DENIED,
                severity=AuditSeverity.WARNING,
                user_id="user1",
                session_id=None,
                source_ip="192.168.1.100",
                resource_id="backup-123",
                resource_type="backup",
                operation="access_backup",
                details={"resource": "backup-123", "permission": "read"},
                success=False,
            ),
            AuditEvent(
                event_id="event-2",
                timestamp=base_time - timedelta(minutes=30),
                event_type=AuditEventType.ACCESS_GRANTED,
                severity=AuditSeverity.INFO,
                user_id="user1",
                session_id=None,
                source_ip="192.168.1.100",
                resource_id="backup-123",
                resource_type="backup",
                operation="access_backup",
                details={"resource": "backup-123", "permission": "admin"},
                success=True,
            ),
        ]

        patterns = self.correlator.correlate_events(events)
        assert len(patterns) == 1
        assert patterns[0].event_type == SecurityEventType.PRIVILEGE_ESCALATION
        assert patterns[0].user_id == "user1"

    def test_detect_data_exfiltration(self):
        """Test detection of data exfiltration patterns."""
        base_time = datetime.now(timezone.utc)

        # Create events showing data exfiltration (need 3+ backups AND 2+ exports)
        events = []

        # Add backup events (need at least 3)
        for i in range(3):
            events.append(
                AuditEvent(
                    event_id=f"backup-{i}",
                    timestamp=base_time - timedelta(minutes=45 + i * 5),
                    event_type=AuditEventType.BACKUP_CREATED,
                    severity=AuditSeverity.INFO,
                    user_id="user1",
                    session_id=None,
                    source_ip="192.168.1.100",
                    resource_id=f"backup-{i}",
                    resource_type="backup",
                    operation="create_backup",
                    details={"backup_size": "100MB", "backup_type": "full"},
                    success=True,
                )
            )

        # Add export events (need at least 2)
        for i in range(2):
            events.append(
                AuditEvent(
                    event_id=f"export-{i}",
                    timestamp=base_time - timedelta(minutes=30 + i * 5),
                    event_type=AuditEventType.EXPORT_OPERATION,
                    severity=AuditSeverity.INFO,
                    user_id="user1",
                    session_id=None,
                    source_ip="192.168.1.100",
                    resource_id=f"backup-{i}",
                    resource_type="backup",
                    operation="export_backup",
                    details={"export_size": "500MB", "format": "json"},
                    success=True,
                )
            )

        patterns = self.correlator.correlate_events(events)
        assert len(patterns) == 1
        assert patterns[0].event_type == SecurityEventType.DATA_EXFILTRATION_ATTEMPT
        assert patterns[0].user_id == "user1"

    def test_detect_reconnaissance(self):
        """Test detection of reconnaissance patterns."""
        base_time = datetime.now(timezone.utc)

        # Create events showing reconnaissance (need more than 20 view/list operations)
        events = []
        for i in range(25):  # More than 20 to trigger reconnaissance alert
            events.append(
                AuditEvent(
                    event_id=f"event-{i}",
                    timestamp=base_time - timedelta(minutes=i),
                    event_type=AuditEventType.ACCESS_GRANTED,
                    severity=AuditSeverity.INFO,
                    user_id="user1",
                    session_id=None,
                    source_ip="192.168.1.100",
                    resource_id=f"resource-{i}",
                    resource_type="backup",
                    operation="list_backups",  # This contains "list" to trigger reconnaissance detection
                    details={"resource_type": "backup", "count": 10},
                    success=True,
                )
            )

        patterns = self.correlator.correlate_events(events)
        assert len(patterns) == 1
        assert patterns[0].event_type == SecurityEventType.SUSPICIOUS_ACCESS_PATTERN
        assert patterns[0].user_id == "user1"

    def test_correlate_events_time_window(self):
        """Test that correlation respects time windows."""
        base_time = datetime.now(timezone.utc)

        # Create events outside correlation window
        events = [
            AuditEvent(
                event_id="event-1",
                timestamp=base_time - timedelta(hours=3),  # Outside window
                event_type=AuditEventType.ACCESS_DENIED,
                severity=AuditSeverity.WARNING,
                user_id="user1",
                session_id=None,
                source_ip="192.168.1.100",
                resource_id="backup-old",
                resource_type="backup",
                operation="access_backup",
                details={},
                success=False,
            ),
            AuditEvent(
                event_id="event-2",
                timestamp=base_time - timedelta(minutes=30),  # Inside window
                event_type=AuditEventType.ACCESS_DENIED,
                severity=AuditSeverity.WARNING,
                user_id="user1",
                session_id=None,
                source_ip="192.168.1.100",
                resource_id="backup-recent",
                resource_type="backup",
                operation="access_backup",
                details={},
                success=False,
            ),
        ]

        patterns = self.correlator.correlate_events(events)
        # Should not correlate events outside the time window
        assert len(patterns) == 0


def test_security_monitor_integration():
    """Test integration between security monitor and event correlator."""
    monitor = SecurityMonitor(max_failed_attempts=3)  # Lower threshold to match test
    correlator = SecurityEventCorrelator()

    # Create security events
    base_time = datetime.now(timezone.utc)
    events = [
        AuditEvent(
            event_id="event-1",
            timestamp=base_time - timedelta(minutes=5),
            event_type=AuditEventType.ACCESS_DENIED,
            severity=AuditSeverity.WARNING,
            user_id="user1",
            session_id=None,
            source_ip="192.168.1.100",
            resource_id="backup-123",
            resource_type="backup",
            operation="access_backup",
            details={"reason": "invalid_credentials"},
            success=False,
        ),
        AuditEvent(
            event_id="event-2",
            timestamp=base_time - timedelta(minutes=3),
            event_type=AuditEventType.ACCESS_DENIED,
            severity=AuditSeverity.WARNING,
            user_id="user1",
            session_id=None,
            source_ip="192.168.1.100",
            resource_id="backup-123",
            resource_type="backup",
            operation="access_backup",
            details={"reason": "invalid_credentials"},
            success=False,
        ),
        AuditEvent(
            event_id="event-3",
            timestamp=base_time - timedelta(minutes=1),
            event_type=AuditEventType.ACCESS_DENIED,
            severity=AuditSeverity.WARNING,
            user_id="user1",
            session_id=None,
            source_ip="192.168.1.100",
            resource_id="backup-123",
            resource_type="backup",
            operation="access_backup",
            details={"reason": "invalid_credentials"},
            success=False,
        ),
    ]

    # Analyze events with monitor
    alerts = monitor.analyze_audit_events(events)
    assert len(alerts) == 1
    assert alerts[0].event_type == SecurityEventType.MULTIPLE_FAILED_ATTEMPTS

    # Correlate events
    patterns = correlator.correlate_events(events)
    # The correlator doesn't detect multiple failed attempts as a separate pattern
    # It only detects privilege escalation, data exfiltration, and reconnaissance
    assert len(patterns) == 0


def test_security_event_correlation_complex_pattern():
    """Test complex security event correlation patterns."""
    correlator = SecurityEventCorrelator(correlation_window_hours=1)

    base_time = datetime.now(timezone.utc)

    # Create complex pattern: user accesses multiple resources, then exports data
    events = []

    # Add backup events (need at least 3 for data exfiltration detection)
    for i in range(3):
        events.append(
            AuditEvent(
                event_id=f"backup-{i}",
                timestamp=base_time - timedelta(minutes=45 + i * 5),
                event_type=AuditEventType.BACKUP_CREATED,
                severity=AuditSeverity.INFO,
                user_id="user1",
                session_id=None,
                source_ip="192.168.1.100",
                resource_id=f"backup-{i}",
                resource_type="backup",
                operation="create_backup",
                details={"backup_size": "100MB", "backup_type": "full"},
                success=True,
            )
        )

    # Add export events (need at least 2 for data exfiltration detection)
    for i in range(2):
        events.append(
            AuditEvent(
                event_id=f"export-{i}",
                timestamp=base_time - timedelta(minutes=15 + i * 5),
                event_type=AuditEventType.EXPORT_OPERATION,
                severity=AuditSeverity.INFO,
                user_id="user1",
                session_id=None,
                source_ip="192.168.1.100",
                resource_id=f"backup-{i}",
                resource_type="backup",
                operation="export_backup",
                details={"export_size": "1GB", "format": "json"},
                success=True,
            )
        )

    patterns = correlator.correlate_events(events)
    assert len(patterns) == 1
    assert patterns[0].event_type == SecurityEventType.DATA_EXFILTRATION_ATTEMPT
    assert patterns[0].user_id == "user1"
