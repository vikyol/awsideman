"""
Data models for backup and restore operations.

This module defines all the data structures used throughout the backup-restore system,
including backup metadata, restore options, and various configuration objects.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional


class BackupType(Enum):
    """Types of backup operations."""

    FULL = "full"
    INCREMENTAL = "incremental"


class ConflictStrategy(Enum):
    """Strategies for handling conflicts during restore operations."""

    OVERWRITE = "overwrite"
    SKIP = "skip"
    PROMPT = "prompt"
    MERGE = "merge"


class ResourceType(Enum):
    """Types of Identity Center resources that can be backed up."""

    USERS = "users"
    GROUPS = "groups"
    PERMISSION_SETS = "permission_sets"
    ASSIGNMENTS = "assignments"
    ALL = "all"


@dataclass
class EncryptionMetadata:
    """Metadata about encryption used for backup data."""

    algorithm: str = "AES-256"
    key_id: Optional[str] = None
    iv: Optional[str] = None
    encrypted: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "algorithm": self.algorithm,
            "key_id": self.key_id,
            "iv": self.iv,
            "encrypted": self.encrypted,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EncryptionMetadata":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class RetentionPolicy:
    """Policy for backup retention and cleanup."""

    keep_daily: int = 7
    keep_weekly: int = 4
    keep_monthly: int = 12
    keep_yearly: int = 3
    auto_cleanup: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "keep_daily": self.keep_daily,
            "keep_weekly": self.keep_weekly,
            "keep_monthly": self.keep_monthly,
            "keep_yearly": self.keep_yearly,
            "auto_cleanup": self.auto_cleanup,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RetentionPolicy":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class BackupMetadata:
    """Metadata associated with a backup."""

    backup_id: str
    timestamp: datetime
    instance_arn: str
    backup_type: BackupType
    version: str
    source_account: str
    source_region: str
    retention_policy: RetentionPolicy
    encryption_info: EncryptionMetadata
    resource_counts: Dict[str, int] = field(default_factory=dict)
    size_bytes: int = 0
    checksum: Optional[str] = None
    storage_backend: Optional[str] = None  # 'filesystem' or 's3'
    storage_location: Optional[str] = None  # Path or bucket/prefix
    optimization_info: Optional[Dict[str, Any]] = None  # Performance optimization metadata

    def __post_init__(self):
        """Post-initialization validation."""
        if not self.backup_id:
            raise ValueError("backup_id cannot be empty")
        if not self.instance_arn:
            raise ValueError("instance_arn cannot be empty")

    def calculate_checksum(self, data: bytes) -> str:
        """Calculate and store checksum for backup data."""
        self.checksum = hashlib.sha256(data).hexdigest()
        return self.checksum

    def verify_checksum(self, data: bytes) -> bool:
        """Verify data against stored checksum."""
        if not self.checksum:
            return False
        return self.checksum == hashlib.sha256(data).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "backup_id": self.backup_id,
            "timestamp": self.timestamp.isoformat(),
            "instance_arn": self.instance_arn,
            "backup_type": self.backup_type.value,
            "version": self.version,
            "source_account": self.source_account,
            "source_region": self.source_region,
            "retention_policy": self.retention_policy.to_dict(),
            "encryption_info": self.encryption_info.to_dict(),
            "resource_counts": self.resource_counts,
            "size_bytes": self.size_bytes,
            "checksum": self.checksum,
            "storage_backend": self.storage_backend,
            "storage_location": self.storage_location,
            "optimization_info": self.optimization_info,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BackupMetadata":
        """Create from dictionary."""
        return cls(
            backup_id=data["backup_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            instance_arn=data["instance_arn"],
            backup_type=BackupType(data["backup_type"]),
            version=data["version"],
            source_account=data["source_account"],
            source_region=data["source_region"],
            retention_policy=RetentionPolicy.from_dict(data["retention_policy"]),
            encryption_info=EncryptionMetadata.from_dict(data["encryption_info"]),
            resource_counts=data.get("resource_counts", {}),
            size_bytes=data.get("size_bytes", 0),
            checksum=data.get("checksum"),
            storage_backend=data.get("storage_backend"),
            storage_location=data.get("storage_location"),
            optimization_info=data.get("optimization_info"),
        )


@dataclass
class UserData:
    """Identity Center user data for backup."""

    user_id: str
    user_name: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    active: bool = True
    external_ids: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "display_name": self.display_name,
            "email": self.email,
            "given_name": self.given_name,
            "family_name": self.family_name,
            "active": self.active,
            "external_ids": self.external_ids,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserData":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class GroupData:
    """Identity Center group data for backup."""

    group_id: str
    display_name: str
    description: Optional[str] = None
    members: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "group_id": self.group_id,
            "display_name": self.display_name,
            "description": self.description,
            "members": self.members,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GroupData":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class PermissionSetData:
    """Identity Center permission set data for backup."""

    permission_set_arn: str
    name: str
    description: Optional[str] = None
    session_duration: Optional[str] = None
    relay_state: Optional[str] = None
    inline_policy: Optional[str] = None
    managed_policies: List[str] = field(default_factory=list)
    customer_managed_policies: List[Dict[str, str]] = field(default_factory=list)
    permissions_boundary: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "permission_set_arn": self.permission_set_arn,
            "name": self.name,
            "description": self.description,
            "session_duration": self.session_duration,
            "relay_state": self.relay_state,
            "inline_policy": self.inline_policy,
            "managed_policies": self.managed_policies,
            "customer_managed_policies": self.customer_managed_policies,
            "permissions_boundary": self.permissions_boundary,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PermissionSetData":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class AssignmentData:
    """Identity Center assignment data for backup."""

    account_id: str
    permission_set_arn: str
    principal_type: str  # USER or GROUP
    principal_id: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "account_id": self.account_id,
            "permission_set_arn": self.permission_set_arn,
            "principal_type": self.principal_type,
            "principal_id": self.principal_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AssignmentData":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class RelationshipMap:
    """Maps relationships between different resources."""

    user_groups: Dict[str, List[str]] = field(default_factory=dict)  # user_id -> group_ids
    group_members: Dict[str, List[str]] = field(default_factory=dict)  # group_id -> user_ids
    permission_set_assignments: Dict[str, List[str]] = field(
        default_factory=dict
    )  # ps_arn -> assignment_ids

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "user_groups": self.user_groups,
            "group_members": self.group_members,
            "permission_set_assignments": self.permission_set_assignments,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RelationshipMap":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class BackupData:
    """Complete backup data structure."""

    metadata: BackupMetadata
    users: List[UserData] = field(default_factory=list)
    groups: List[GroupData] = field(default_factory=list)
    permission_sets: List[PermissionSetData] = field(default_factory=list)
    assignments: List[AssignmentData] = field(default_factory=list)
    relationships: RelationshipMap = field(default_factory=RelationshipMap)
    checksums: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        """Post-initialization validation and checksum calculation."""
        self._update_resource_counts()
        self._calculate_checksums()

    def _update_resource_counts(self):
        """Update resource counts in metadata."""
        self.metadata.resource_counts = {
            "users": len(self.users),
            "groups": len(self.groups),
            "permission_sets": len(self.permission_sets),
            "assignments": len(self.assignments),
        }

    def _calculate_checksums(self):
        """Calculate checksums for each resource type."""
        self.checksums = {
            "users": self._calculate_resource_checksum(self.users),
            "groups": self._calculate_resource_checksum(self.groups),
            "permission_sets": self._calculate_resource_checksum(self.permission_sets),
            "assignments": self._calculate_resource_checksum(self.assignments),
            "relationships": self._calculate_resource_checksum([self.relationships]),
        }

    def _calculate_resource_checksum(self, resources: List[Any]) -> str:
        """Calculate checksum for a list of resources."""
        data = json.dumps(
            [r.to_dict() if hasattr(r, "to_dict") else r for r in resources],
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(data.encode()).hexdigest()

    def verify_integrity(self) -> bool:
        """Verify backup data integrity using checksums."""
        current_checksums = {
            "users": self._calculate_resource_checksum(self.users),
            "groups": self._calculate_resource_checksum(self.groups),
            "permission_sets": self._calculate_resource_checksum(self.permission_sets),
            "assignments": self._calculate_resource_checksum(self.assignments),
            "relationships": self._calculate_resource_checksum([self.relationships]),
        }
        return current_checksums == self.checksums

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "metadata": self.metadata.to_dict(),
            "users": [user.to_dict() for user in self.users],
            "groups": [group.to_dict() for group in self.groups],
            "permission_sets": [ps.to_dict() for ps in self.permission_sets],
            "assignments": [assignment.to_dict() for assignment in self.assignments],
            "relationships": self.relationships.to_dict(),
            "checksums": self.checksums,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BackupData":
        """Create from dictionary."""
        return cls(
            metadata=BackupMetadata.from_dict(data["metadata"]),
            users=[UserData.from_dict(u) for u in data.get("users", [])],
            groups=[GroupData.from_dict(g) for g in data.get("groups", [])],
            permission_sets=[
                PermissionSetData.from_dict(ps) for ps in data.get("permission_sets", [])
            ],
            assignments=[AssignmentData.from_dict(a) for a in data.get("assignments", [])],
            relationships=RelationshipMap.from_dict(data.get("relationships", {})),
            checksums=data.get("checksums", {}),
        )


@dataclass
class CrossAccountConfig:
    """Configuration for cross-account operations."""

    target_account_id: str
    role_arn: str
    external_id: Optional[str] = None
    session_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "target_account_id": self.target_account_id,
            "role_arn": self.role_arn,
            "external_id": self.external_id,
            "session_name": self.session_name,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CrossAccountConfig":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class BackupOptions:
    """Options for backup operations."""

    backup_type: BackupType = BackupType.FULL
    resource_types: List[ResourceType] = field(default_factory=lambda: [ResourceType.ALL])
    include_inactive_users: bool = False
    since: Optional[datetime] = None  # For incremental backups
    encryption_enabled: bool = True
    compression_enabled: bool = True
    parallel_collection: bool = True
    cross_account_configs: List[CrossAccountConfig] = field(
        default_factory=list
    )  # For cross-account backups
    skip_duplicate_check: bool = False  # Skip duplicate backup detection
    delete_duplicates: bool = False  # Delete duplicate backups if found

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "backup_type": self.backup_type.value,
            "resource_types": [rt.value for rt in self.resource_types],
            "include_inactive_users": self.include_inactive_users,
            "since": self.since.isoformat() if self.since else None,
            "encryption_enabled": self.encryption_enabled,
            "compression_enabled": self.compression_enabled,
            "parallel_collection": self.parallel_collection,
            "cross_account_configs": [config.to_dict() for config in self.cross_account_configs],
            "skip_duplicate_check": self.skip_duplicate_check,
            "delete_duplicates": self.delete_duplicates,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BackupOptions":
        """Create from dictionary."""
        return cls(
            backup_type=BackupType(data.get("backup_type", "full")),
            resource_types=[ResourceType(rt) for rt in data.get("resource_types", ["all"])],
            include_inactive_users=data.get("include_inactive_users", False),
            since=datetime.fromisoformat(data["since"]) if data.get("since") else None,
            encryption_enabled=data.get("encryption_enabled", True),
            compression_enabled=data.get("compression_enabled", True),
            parallel_collection=data.get("parallel_collection", True),
            cross_account_configs=[
                CrossAccountConfig.from_dict(config)
                for config in data.get("cross_account_configs", [])
            ],
            skip_duplicate_check=data.get("skip_duplicate_check", False),
            delete_duplicates=data.get("delete_duplicates", False),
        )


@dataclass
class ResourceMapping:
    """Mapping configuration for cross-account/region resource restoration."""

    source_account_id: str
    target_account_id: str
    source_region: Optional[str] = None
    target_region: Optional[str] = None
    permission_set_name_mappings: Dict[str, str] = field(
        default_factory=dict
    )  # old_name -> new_name

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "source_account_id": self.source_account_id,
            "target_account_id": self.target_account_id,
            "source_region": self.source_region,
            "target_region": self.target_region,
            "permission_set_name_mappings": self.permission_set_name_mappings,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResourceMapping":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class RestoreOptions:
    """Options for restore operations."""

    target_resources: List[ResourceType] = field(default_factory=lambda: [ResourceType.ALL])
    conflict_strategy: ConflictStrategy = ConflictStrategy.PROMPT
    dry_run: bool = False
    target_account: Optional[str] = None
    target_region: Optional[str] = None
    target_instance_arn: Optional[str] = None
    resource_mappings: Dict[str, str] = field(default_factory=dict)  # Legacy simple mappings
    skip_validation: bool = False
    cross_account_config: Optional[CrossAccountConfig] = None  # For cross-account restore
    resource_mapping_configs: List[ResourceMapping] = field(
        default_factory=list
    )  # Advanced mappings

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "target_resources": [rt.value for rt in self.target_resources],
            "conflict_strategy": self.conflict_strategy.value,
            "dry_run": self.dry_run,
            "target_account": self.target_account,
            "target_region": self.target_region,
            "target_instance_arn": self.target_instance_arn,
            "resource_mappings": self.resource_mappings,
            "skip_validation": self.skip_validation,
            "cross_account_config": (
                self.cross_account_config.to_dict() if self.cross_account_config else None
            ),
            "resource_mapping_configs": [
                mapping.to_dict() for mapping in self.resource_mapping_configs
            ],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RestoreOptions":
        """Create from dictionary."""
        return cls(
            target_resources=[ResourceType(rt) for rt in data.get("target_resources", ["all"])],
            conflict_strategy=ConflictStrategy(data.get("conflict_strategy", "prompt")),
            dry_run=data.get("dry_run", False),
            target_account=data.get("target_account"),
            target_region=data.get("target_region"),
            target_instance_arn=data.get("target_instance_arn"),
            resource_mappings=data.get("resource_mappings", {}),
            skip_validation=data.get("skip_validation", False),
            cross_account_config=(
                CrossAccountConfig.from_dict(data["cross_account_config"])
                if data.get("cross_account_config")
                else None
            ),
            resource_mapping_configs=[
                ResourceMapping.from_dict(mapping)
                for mapping in data.get("resource_mapping_configs", [])
            ],
        )


@dataclass
class ConflictInfo:
    """Information about a conflict during restore."""

    resource_type: ResourceType
    resource_id: str
    conflict_type: str
    existing_value: Any
    new_value: Any
    suggested_action: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "resource_type": self.resource_type.value,
            "resource_id": self.resource_id,
            "conflict_type": self.conflict_type,
            "existing_value": self.existing_value,
            "new_value": self.new_value,
            "suggested_action": self.suggested_action,
        }


@dataclass
class RestorePreview:
    """Preview of restore operation changes."""

    changes_summary: Dict[str, int] = field(default_factory=dict)
    conflicts: List[ConflictInfo] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    estimated_duration: Optional[timedelta] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "changes_summary": self.changes_summary,
            "conflicts": [c.to_dict() for c in self.conflicts],
            "warnings": self.warnings,
            "estimated_duration": (
                self.estimated_duration.total_seconds() if self.estimated_duration else None
            ),
        }


@dataclass
class ValidationResult:
    """Result of backup or restore validation."""

    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "details": self.details,
        }


@dataclass
class BackupResult:
    """Result of backup operation."""

    success: bool
    backup_id: Optional[str] = None
    message: str = ""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Optional[BackupMetadata] = None
    duration: Optional[timedelta] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "backup_id": self.backup_id,
            "message": self.message,
            "errors": self.errors,
            "warnings": self.warnings,
            "metadata": self.metadata.to_dict() if self.metadata else None,
            "duration": self.duration.total_seconds() if self.duration else None,
        }


@dataclass
class RestoreResult:
    """Result of restore operation."""

    success: bool
    message: str = ""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    changes_applied: Dict[str, int] = field(default_factory=dict)
    duration: Optional[timedelta] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "message": self.message,
            "errors": self.errors,
            "warnings": self.warnings,
            "changes_applied": self.changes_applied,
            "duration": self.duration.total_seconds() if self.duration else None,
        }


@dataclass
class ExportFormat:
    """Configuration for export format."""

    format_type: str  # JSON, YAML, CSV
    compression: Optional[str] = None  # gzip, zip
    encryption: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "format_type": self.format_type,
            "compression": self.compression,
            "encryption": self.encryption,
        }


@dataclass
class ImportSource:
    """Configuration for import source."""

    source_type: str  # filesystem, s3, url
    location: str
    credentials: Optional[Dict[str, str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "source_type": self.source_type,
            "location": self.location,
            "credentials": self.credentials,
        }


@dataclass
class NotificationSettings:
    """Settings for backup notifications."""

    enabled: bool = True
    email_addresses: List[str] = field(default_factory=list)
    webhook_urls: List[str] = field(default_factory=list)
    notify_on_success: bool = False
    notify_on_failure: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "enabled": self.enabled,
            "email_addresses": self.email_addresses,
            "webhook_urls": self.webhook_urls,
            "notify_on_success": self.notify_on_success,
            "notify_on_failure": self.notify_on_failure,
        }


@dataclass
class ScheduleConfig:
    """Configuration for scheduled backups."""

    name: str
    backup_type: BackupType
    interval: str  # cron expression or predefined (daily, weekly, monthly)
    retention_policy: RetentionPolicy
    notification_settings: NotificationSettings
    enabled: bool = True
    backup_options: Optional[BackupOptions] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "backup_type": self.backup_type.value,
            "interval": self.interval,
            "retention_policy": self.retention_policy.to_dict(),
            "notification_settings": self.notification_settings.to_dict(),
            "enabled": self.enabled,
            "backup_options": self.backup_options.to_dict() if self.backup_options else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduleConfig":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            backup_type=BackupType(data["backup_type"]),
            interval=data["interval"],
            retention_policy=RetentionPolicy.from_dict(data["retention_policy"]),
            notification_settings=NotificationSettings(**data["notification_settings"]),
            enabled=data.get("enabled", True),
            backup_options=(
                BackupOptions.from_dict(data["backup_options"])
                if data.get("backup_options")
                else None
            ),
        )


@dataclass
class PerformanceConfig:
    """Configuration for performance optimization during backup and restore."""

    parallel_collection: bool = True
    compression_enabled: bool = True
    encryption_enabled: bool = True
    max_concurrent_requests: int = 10
    max_concurrent_downloads: int = 5
    max_concurrent_uploads: int = 5
    max_concurrent_restores: int = 5
    max_concurrent_validations: int = 10
    max_concurrent_exports: int = 5
    max_concurrent_imports: int = 5

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "parallel_collection": self.parallel_collection,
            "compression_enabled": self.compression_enabled,
            "encryption_enabled": self.encryption_enabled,
            "max_concurrent_requests": self.max_concurrent_requests,
            "max_concurrent_downloads": self.max_concurrent_downloads,
            "max_concurrent_uploads": self.max_concurrent_uploads,
            "max_concurrent_restores": self.max_concurrent_restores,
            "max_concurrent_validations": self.max_concurrent_validations,
            "max_concurrent_exports": self.max_concurrent_exports,
            "max_concurrent_imports": self.max_concurrent_imports,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PerformanceConfig":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class PerformanceMetrics:
    """Metrics for performance monitoring and optimization."""

    operation_id: str
    operation_type: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration: Optional[timedelta] = None
    compression_ratio: Optional[float] = None
    deduplication_ratio: Optional[float] = None
    parallel_workers: Optional[int] = None
    memory_usage_mb: Optional[float] = None
    cpu_usage_percent: Optional[float] = None
    storage_size_bytes: Optional[int] = None
    network_io_bytes: Optional[int] = None
    error_count: int = 0
    warning_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "operation_id": self.operation_id,
            "operation_type": self.operation_type,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration": self.duration.total_seconds() if self.duration else None,
            "compression_ratio": self.compression_ratio,
            "deduplication_ratio": self.deduplication_ratio,
            "parallel_workers": self.parallel_workers,
            "memory_usage_mb": self.memory_usage_mb,
            "cpu_usage_percent": self.cpu_usage_percent,
            "storage_size_bytes": self.storage_size_bytes,
            "network_io_bytes": self.network_io_bytes,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PerformanceMetrics":
        """Create from dictionary."""
        return cls(
            operation_id=data["operation_id"],
            operation_type=data["operation_type"],
            start_time=datetime.fromisoformat(data["start_time"]),
            end_time=datetime.fromisoformat(data["end_time"]) if data.get("end_time") else None,
            duration=timedelta(seconds=data["duration"]) if data.get("duration") else None,
            compression_ratio=data.get("compression_ratio"),
            deduplication_ratio=data.get("deduplication_ratio"),
            parallel_workers=data.get("parallel_workers"),
            memory_usage_mb=data.get("memory_usage_mb"),
            cpu_usage_percent=data.get("cpu_usage_percent"),
            storage_size_bytes=data.get("storage_size_bytes"),
            network_io_bytes=data.get("network_io_bytes"),
            error_count=data.get("error_count", 0),
            warning_count=data.get("warning_count", 0),
        )


@dataclass
class ResourceUsageMetrics:
    """Real-time resource usage metrics."""

    timestamp: datetime
    cpu_percent: float
    memory_rss_mb: float
    memory_vms_mb: float
    memory_percent: float
    system_cpu_percent: float
    system_memory_percent: float
    file_descriptors: int
    thread_count: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "cpu_percent": self.cpu_percent,
            "memory_rss_mb": self.memory_rss_mb,
            "memory_vms_mb": self.memory_vms_mb,
            "memory_percent": self.memory_percent,
            "system_cpu_percent": self.system_cpu_percent,
            "system_memory_percent": self.system_memory_percent,
            "file_descriptors": self.file_descriptors,
            "thread_count": self.thread_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResourceUsageMetrics":
        """Create from dictionary."""
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            cpu_percent=data["cpu_percent"],
            memory_rss_mb=data["memory_rss_mb"],
            memory_vms_mb=data["memory_vms_mb"],
            memory_percent=data["memory_percent"],
            system_cpu_percent=data["system_cpu_percent"],
            system_memory_percent=data["system_memory_percent"],
            file_descriptors=data["file_descriptors"],
            thread_count=data["thread_count"],
        )
