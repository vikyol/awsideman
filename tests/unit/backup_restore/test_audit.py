"""
Unit tests for audit logging functionality.

Tests the audit logging system including event creation, logging,
querying, and retention management.
"""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.awsideman.backup_restore.audit import (
    AuditEvent,
    AuditEventType,
    AuditLogger,
    AuditSeverity,
    configure_audit_logger,
    get_audit_logger,
)


class TestAuditEvent:
    """Test AuditEvent data model."""

    def test_audit_event_creation(self):
        """Test creating an audit event."""
        event = AuditEvent(
            event_id="test-123",
            timestamp=datetime.utcnow(),
            event_type=AuditEventType.BACKUP_CREATED,
            severity=AuditSeverity.INFO,
            user_id="user123",
            session_id="session456",
            source_ip="192.168.1.1",
            resource_id="backup-789",
            resource_type="backup",
            operation="create_backup",
            details={"size": 1024},
            success=True,
        )

        assert event.event_id == "test-123"
        assert event.event_type == AuditEventType.BACKUP_CREATED
        assert event.severity == AuditSeverity.INFO
        assert event.user_id == "user123"
        assert event.success is True

    def test_audit_event_to_dict(self):
        """Test converting audit event to dictionary."""
        timestamp = datetime.utcnow()
        event = AuditEvent(
            event_id="test-123",
            timestamp=timestamp,
            event_type=AuditEventType.BACKUP_CREATED,
            severity=AuditSeverity.INFO,
            user_id="user123",
            session_id=None,
            source_ip=None,
            resource_id="backup-789",
            resource_type="backup",
            operation="create_backup",
            details={"size": 1024},
            success=True,
        )

        event_dict = event.to_dict()

        assert event_dict["event_id"] == "test-123"
        assert event_dict["timestamp"] == timestamp.isoformat()
        assert event_dict["event_type"] == "backup_created"
        assert event_dict["severity"] == "info"
        assert event_dict["user_id"] == "user123"
        assert event_dict["details"] == {"size": 1024}
        assert event_dict["success"] is True

    def test_audit_event_from_dict(self):
        """Test creating audit event from dictionary."""
        timestamp = datetime.utcnow()
        event_dict = {
            "event_id": "test-123",
            "timestamp": timestamp.isoformat(),
            "event_type": "backup_created",
            "severity": "info",
            "user_id": "user123",
            "session_id": None,
            "source_ip": None,
            "resource_id": "backup-789",
            "resource_type": "backup",
            "operation": "create_backup",
            "details": {"size": 1024},
            "success": True,
        }

        event = AuditEvent.from_dict(event_dict)

        assert event.event_id == "test-123"
        assert event.event_type == AuditEventType.BACKUP_CREATED
        assert event.severity == AuditSeverity.INFO
        assert event.user_id == "user123"
        assert event.details == {"size": 1024}
        assert event.success is True


class TestAuditLogger:
    """Test AuditLogger functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.log_file = Path(self.temp_dir) / "test_audit.log"

    def test_audit_logger_initialization(self):
        """Test audit logger initialization."""
        logger = AuditLogger(
            log_file=self.log_file, enable_console=False, enable_structured=True, retention_days=30
        )

        assert logger.log_file == self.log_file
        assert logger.enable_console is False
        assert logger.enable_structured is True
        assert logger.retention_days == 30

    def test_log_event_structured(self):
        """Test logging an event in structured format."""
        logger = AuditLogger(log_file=self.log_file, enable_console=False, enable_structured=True)

        event = AuditEvent(
            event_id="test-123",
            timestamp=datetime.utcnow(),
            event_type=AuditEventType.BACKUP_CREATED,
            severity=AuditSeverity.INFO,
            user_id="user123",
            session_id=None,
            source_ip=None,
            resource_id="backup-789",
            resource_type="backup",
            operation="create_backup",
            details={"size": 1024},
            success=True,
        )

        logger.log_event(event)

        # Verify log file was created and contains the event
        assert self.log_file.exists()

        with open(self.log_file, "r") as f:
            log_content = f.read().strip()
            logged_event = json.loads(log_content)

            assert logged_event["event_id"] == "test-123"
            assert logged_event["event_type"] == "backup_created"
            assert logged_event["user_id"] == "user123"

    def test_log_backup_operation(self):
        """Test logging backup operations."""
        logger = AuditLogger(log_file=self.log_file, enable_console=False, enable_structured=True)

        logger.log_backup_operation(
            operation="create_full_backup",
            backup_id="backup-123",
            user_id="user456",
            success=True,
            details={"type": "full", "size": 2048},
        )

        assert self.log_file.exists()

        with open(self.log_file, "r") as f:
            log_content = f.read().strip()
            logged_event = json.loads(log_content)

            assert logged_event["event_type"] == "backup_created"
            assert logged_event["operation"] == "create_full_backup"
            assert logged_event["resource_id"] == "backup-123"
            assert logged_event["user_id"] == "user456"
            assert logged_event["success"] is True
            assert logged_event["details"]["type"] == "full"

    def test_log_restore_operation(self):
        """Test logging restore operations."""
        logger = AuditLogger(log_file=self.log_file, enable_console=False, enable_structured=True)

        logger.log_restore_operation(
            operation="restore_backup",
            backup_id="backup-123",
            user_id="user456",
            success=False,
            error_message="Insufficient permissions",
        )

        assert self.log_file.exists()

        with open(self.log_file, "r") as f:
            log_content = f.read().strip()
            logged_event = json.loads(log_content)

            assert logged_event["event_type"] == "restore_started"
            assert logged_event["operation"] == "restore_backup"
            assert logged_event["resource_id"] == "backup-123"
            assert logged_event["user_id"] == "user456"
            assert logged_event["success"] is False
            assert logged_event["error_message"] == "Insufficient permissions"

    def test_log_security_event(self):
        """Test logging security events."""
        logger = AuditLogger(log_file=self.log_file, enable_console=False, enable_structured=True)

        logger.log_security_event(
            event_type=AuditEventType.ACCESS_DENIED,
            operation="access_backup",
            user_id="user789",
            resource_id="backup-456",
            success=False,
            details={"reason": "insufficient_permissions"},
            error_message="Access denied",
        )

        assert self.log_file.exists()

        with open(self.log_file, "r") as f:
            log_content = f.read().strip()
            logged_event = json.loads(log_content)

            assert logged_event["event_type"] == "access_denied"
            assert logged_event["operation"] == "access_backup"
            assert logged_event["user_id"] == "user789"
            assert logged_event["resource_id"] == "backup-456"
            assert logged_event["success"] is False
            assert logged_event["severity"] == "critical"

    def test_log_access_attempt(self):
        """Test logging access attempts."""
        logger = AuditLogger(log_file=self.log_file, enable_console=False, enable_structured=True)

        # Test granted access
        logger.log_access_attempt(
            resource_id="backup-123", user_id="user456", granted=True, reason="Valid permissions"
        )

        # Test denied access
        logger.log_access_attempt(
            resource_id="backup-456",
            user_id="user789",
            granted=False,
            reason="Insufficient permissions",
        )

        assert self.log_file.exists()

        with open(self.log_file, "r") as f:
            log_lines = f.read().strip().split("\n")

            # Check granted access log
            granted_event = json.loads(log_lines[0])
            assert granted_event["event_type"] == "access_granted"
            assert granted_event["success"] is True
            assert granted_event["severity"] == "info"

            # Check denied access log
            denied_event = json.loads(log_lines[1])
            assert denied_event["event_type"] == "access_denied"
            assert denied_event["success"] is False
            assert denied_event["severity"] == "warning"

    def test_log_encryption_operation(self):
        """Test logging encryption operations."""
        logger = AuditLogger(log_file=self.log_file, enable_console=False, enable_structured=True)

        logger.log_encryption_operation(
            operation="encrypt_backup", resource_id="backup-123", key_id="key-456", success=True
        )

        assert self.log_file.exists()

        with open(self.log_file, "r") as f:
            log_content = f.read().strip()
            logged_event = json.loads(log_content)

            assert logged_event["event_type"] == "encryption_operation"
            assert logged_event["operation"] == "encrypt_backup"
            assert logged_event["resource_id"] == "backup-123"
            assert logged_event["details"]["key_id"] == "key-456"
            assert logged_event["success"] is True

    def test_log_secure_deletion(self):
        """Test logging secure deletion operations."""
        logger = AuditLogger(log_file=self.log_file, enable_console=False, enable_structured=True)

        logger.log_secure_deletion(
            resource_id="backup-123", deletion_method="multi-pass overwrite", success=True
        )

        assert self.log_file.exists()

        with open(self.log_file, "r") as f:
            log_content = f.read().strip()
            logged_event = json.loads(log_content)

            assert logged_event["event_type"] == "secure_deletion"
            assert logged_event["operation"] == "secure_deletion"
            assert logged_event["resource_id"] == "backup-123"
            assert logged_event["details"]["deletion_method"] == "multi-pass overwrite"
            assert logged_event["success"] is True

    def test_query_events(self):
        """Test querying audit events."""
        logger = AuditLogger(log_file=self.log_file, enable_console=False, enable_structured=True)

        # Log multiple events
        events_to_log = [
            ("backup_operation", "user1", AuditEventType.BACKUP_CREATED),
            ("restore_operation", "user2", AuditEventType.RESTORE_STARTED),
            ("backup_operation", "user1", AuditEventType.BACKUP_DELETED),
        ]

        for operation, user_id, event_type in events_to_log:
            event = AuditEvent(
                event_id=f"test-{operation}-{user_id}",
                timestamp=datetime.utcnow(),
                event_type=event_type,
                severity=AuditSeverity.INFO,
                user_id=user_id,
                session_id=None,
                source_ip=None,
                resource_id=f"resource-{user_id}",
                resource_type="backup",
                operation=operation,
                details={},
                success=True,
            )
            logger.log_event(event)

        # Query all events
        all_events = logger.query_events()
        assert len(all_events) == 3

        # Query events by user
        user1_events = logger.query_events(user_id="user1")
        assert len(user1_events) == 2
        assert all(e.user_id == "user1" for e in user1_events)

        # Query events by type
        backup_events = logger.query_events(event_types=[AuditEventType.BACKUP_CREATED])
        assert len(backup_events) == 1
        assert backup_events[0].event_type == AuditEventType.BACKUP_CREATED

    def test_cleanup_old_logs(self):
        """Test cleaning up old audit logs."""
        logger = AuditLogger(
            log_file=self.log_file, enable_console=False, enable_structured=True, retention_days=1
        )

        # Create events with different timestamps
        old_timestamp = datetime.utcnow() - timedelta(days=2)
        recent_timestamp = datetime.utcnow()

        old_event = AuditEvent(
            event_id="old-event",
            timestamp=old_timestamp,
            event_type=AuditEventType.BACKUP_CREATED,
            severity=AuditSeverity.INFO,
            user_id="user1",
            session_id=None,
            source_ip=None,
            resource_id="backup-old",
            resource_type="backup",
            operation="create_backup",
            details={},
            success=True,
        )

        recent_event = AuditEvent(
            event_id="recent-event",
            timestamp=recent_timestamp,
            event_type=AuditEventType.BACKUP_CREATED,
            severity=AuditSeverity.INFO,
            user_id="user2",
            session_id=None,
            source_ip=None,
            resource_id="backup-recent",
            resource_type="backup",
            operation="create_backup",
            details={},
            success=True,
        )

        logger.log_event(old_event)
        logger.log_event(recent_event)

        # Verify both events are logged
        all_events = logger.query_events()
        assert len(all_events) == 2

        # Clean up old logs
        logger.cleanup_old_logs()

        # Verify only recent event remains
        remaining_events = logger.query_events()
        assert len(remaining_events) == 1
        assert remaining_events[0].event_id == "recent-event"


class TestAuditLoggerGlobal:
    """Test global audit logger functions."""

    def test_get_audit_logger(self):
        """Test getting global audit logger."""
        logger1 = get_audit_logger()
        logger2 = get_audit_logger()

        # Should return the same instance
        assert logger1 is logger2

    def test_configure_audit_logger(self):
        """Test configuring global audit logger."""
        temp_dir = tempfile.mkdtemp()
        log_file = Path(temp_dir) / "configured_audit.log"

        configure_audit_logger(
            log_file=log_file, enable_console=False, enable_structured=True, retention_days=60
        )

        logger = get_audit_logger()
        assert logger.log_file == log_file
        assert logger.enable_console is False
        assert logger.enable_structured is True
        assert logger.retention_days == 60


@pytest.fixture
def sample_audit_event():
    """Fixture providing a sample audit event."""
    return AuditEvent(
        event_id="test-event-123",
        timestamp=datetime.utcnow(),
        event_type=AuditEventType.BACKUP_CREATED,
        severity=AuditSeverity.INFO,
        user_id="test-user",
        session_id="test-session",
        source_ip="192.168.1.100",
        resource_id="test-backup",
        resource_type="backup",
        operation="create_backup",
        details={"size": 1024, "type": "full"},
        success=True,
    )


def test_audit_event_serialization_roundtrip(sample_audit_event):
    """Test that audit events can be serialized and deserialized correctly."""
    # Convert to dict
    event_dict = sample_audit_event.to_dict()

    # Convert back to object
    restored_event = AuditEvent.from_dict(event_dict)

    # Verify all fields match
    assert restored_event.event_id == sample_audit_event.event_id
    assert restored_event.timestamp == sample_audit_event.timestamp
    assert restored_event.event_type == sample_audit_event.event_type
    assert restored_event.severity == sample_audit_event.severity
    assert restored_event.user_id == sample_audit_event.user_id
    assert restored_event.session_id == sample_audit_event.session_id
    assert restored_event.source_ip == sample_audit_event.source_ip
    assert restored_event.resource_id == sample_audit_event.resource_id
    assert restored_event.resource_type == sample_audit_event.resource_type
    assert restored_event.operation == sample_audit_event.operation
    assert restored_event.details == sample_audit_event.details
    assert restored_event.success == sample_audit_event.success
    assert restored_event.error_message == sample_audit_event.error_message


def test_audit_logger_handles_missing_log_file():
    """Test that audit logger handles missing log file gracefully."""
    non_existent_file = Path("/non/existent/path/audit.log")

    logger = AuditLogger(log_file=non_existent_file, enable_console=False, enable_structured=True)

    # Should not raise an exception
    events = logger.query_events()
    assert events == []


def test_audit_logger_handles_malformed_log_entries():
    """Test that audit logger handles malformed log entries gracefully."""
    temp_dir = tempfile.mkdtemp()
    log_file = Path(temp_dir) / "malformed_audit.log"

    # Create log file with malformed entries
    with open(log_file, "w") as f:
        f.write('{"valid": "json", "but": "missing_required_fields"}\n')
        f.write("invalid json line\n")
        f.write(
            '{"event_id": "valid-event", "timestamp": "2023-01-01T00:00:00", "event_type": "backup_created", "severity": "info", "operation": "test", "details": {}, "success": true}\n'
        )

    logger = AuditLogger(log_file=log_file, enable_console=False, enable_structured=True)

    # Should only return valid events
    events = logger.query_events()
    assert len(events) == 1
    assert events[0].event_id == "valid-event"
