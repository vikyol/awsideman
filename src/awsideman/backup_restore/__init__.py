"""
AWS Identity Manager - Backup and Restore Module

This module provides comprehensive backup and restore capabilities for AWS Identity Center configurations.
"""

from .audit import (
    AuditEvent,
    AuditEventType,
    AuditLogger,
    AuditSeverity,
    configure_audit_logger,
    get_audit_logger,
)
from .backends import FileSystemStorageBackend, S3StorageBackend, StorageBackendFactory
from .collector import IdentityCenterCollector
from .encryption import (
    AESEncryptionProvider,
    EncryptionProviderFactory,
    FernetEncryptionProvider,
    NoOpEncryptionProvider,
)
from .export_import import (
    ExportImportError,
    ExportImportManager,
    FormatConverter,
    StreamingProcessor,
)
from .interfaces import (
    BackupManagerInterface,
    CollectorInterface,
    EncryptionProviderInterface,
    ExportImportManagerInterface,
    ProgressReporterInterface,
    RestoreManagerInterface,
    ScheduleManagerInterface,
    StorageBackendInterface,
    StorageEngineInterface,
)
from .manager import BackupManager
from .models import (
    BackupData,
    BackupMetadata,
    BackupOptions,
    BackupResult,
    BackupType,
    ConflictStrategy,
    EncryptionMetadata,
    ExportFormat,
    ImportSource,
    NotificationSettings,
    ResourceType,
    RestoreOptions,
    RestoreResult,
    RetentionPolicy,
    ScheduleConfig,
    ValidationResult,
)
from .monitoring import (
    Alert,
    AlertManager,
    AlertSeverity,
    BackupMonitor,
    MetricPoint,
    MetricsCollector,
    MonitoringDashboard,
    OperationMetrics,
    OperationStatus,
    OperationType,
    ProgressInfo,
    ProgressReporter,
    SystemMetrics,
)
from .rbac import (
    AccessControlInterface,
    AccessControlManager,
    FileBasedAccessControl,
    Permission,
    Role,
    User,
    configure_access_control,
    get_access_control_manager,
    get_role_permissions,
)
from .restore_manager import RestoreManager
from .schedule_manager import CronParser, ScheduleInfo, ScheduleManager
from .security import (
    SecureDeletion,
    SecurityAlert,
    SecurityEventCorrelator,
    SecurityEventType,
    SecurityMonitor,
    ThreatLevel,
    configure_security_monitor,
    get_security_monitor,
)
from .serialization import (
    BackupSerializer,
    CompressionType,
    DataSerializer,
    SerializationError,
    SerializationFormat,
    deserialize_backup_data,
    load_backup_from_file,
    save_backup_to_file,
    serialize_backup_data,
)
from .storage import StorageEngine
from .validation import BackupValidator, DataValidator, ValidationError

__all__ = [
    # Data Models
    "BackupData",
    "BackupMetadata",
    "BackupType",
    "RestoreOptions",
    "ConflictStrategy",
    "ResourceType",
    "BackupOptions",
    "RestoreResult",
    "BackupResult",
    "ValidationResult",
    "RetentionPolicy",
    "EncryptionMetadata",
    "ExportFormat",
    "ImportSource",
    "ScheduleConfig",
    "NotificationSettings",
    # Interfaces
    "BackupManagerInterface",
    "RestoreManagerInterface",
    "StorageEngineInterface",
    "CollectorInterface",
    "ExportImportManagerInterface",
    "ScheduleManagerInterface",
    "StorageBackendInterface",
    "EncryptionProviderInterface",
    "ProgressReporterInterface",
    # Validation
    "DataValidator",
    "BackupValidator",
    "ValidationError",
    # Manager
    "BackupManager",
    "RestoreManager",
    # Serialization
    "DataSerializer",
    "SerializationError",
    "SerializationFormat",
    "CompressionType",
    "serialize_backup_data",
    "deserialize_backup_data",
    "save_backup_to_file",
    "load_backup_from_file",
    # Collector
    "IdentityCenterCollector",
    # Storage
    "StorageEngine",
    "FileSystemStorageBackend",
    "S3StorageBackend",
    "StorageBackendFactory",
    # Encryption
    "FernetEncryptionProvider",
    "AESEncryptionProvider",
    "NoOpEncryptionProvider",
    "EncryptionProviderFactory",
    # Additional Serialization
    "BackupSerializer",
    # Export/Import
    "ExportImportManager",
    "ExportImportError",
    "FormatConverter",
    "StreamingProcessor",
    "AuditLogger",
    # Scheduling
    "ScheduleManager",
    "CronParser",
    "ScheduleInfo",
    # Monitoring
    "BackupMonitor",
    "ProgressReporter",
    "MetricsCollector",
    "AlertManager",
    "MonitoringDashboard",
    "OperationType",
    "OperationStatus",
    "AlertSeverity",
    "ProgressInfo",
    "MetricPoint",
    "OperationMetrics",
    "Alert",
    "SystemMetrics",
    # Audit Logging
    "AuditEvent",
    "AuditEventType",
    "AuditSeverity",
    "AuditLogger",
    "get_audit_logger",
    "configure_audit_logger",
    # Role-Based Access Control
    "Permission",
    "Role",
    "User",
    "get_role_permissions",
    "AccessControlInterface",
    "FileBasedAccessControl",
    "AccessControlManager",
    "get_access_control_manager",
    "configure_access_control",
    # Security Monitoring
    "ThreatLevel",
    "SecurityEventType",
    "SecurityAlert",
    "SecurityMonitor",
    "SecureDeletion",
    "SecurityEventCorrelator",
    "get_security_monitor",
    "configure_security_monitor",
]
