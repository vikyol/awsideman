"""Data models for AWS Identity Center status monitoring and health checking."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class StatusLevel(str, Enum):
    """Enumeration for status levels."""

    HEALTHY = "Healthy"
    WARNING = "Warning"
    CRITICAL = "Critical"
    CONNECTION_FAILED = "Connection Failed"


class PrincipalType(str, Enum):
    """Enumeration for principal types."""

    USER = "USER"
    GROUP = "GROUP"


class ProvisioningOperationStatus(str, Enum):
    """Enumeration for provisioning operation statuses."""

    IN_PROGRESS = "IN_PROGRESS"
    FAILED = "FAILED"
    SUCCEEDED = "SUCCEEDED"


class SyncProviderType(str, Enum):
    """Enumeration for external identity provider types."""

    ACTIVE_DIRECTORY = "ACTIVE_DIRECTORY"
    EXTERNAL_SAML = "EXTERNAL_SAML"
    AZURE_AD = "AZURE_AD"


class ResourceType(str, Enum):
    """Enumeration for resource types."""

    USER = "USER"
    GROUP = "GROUP"
    PERMISSION_SET = "PERMISSION_SET"


class OutputFormat(str, Enum):
    """Enumeration for output formats."""

    TABLE = "table"
    JSON = "json"
    CSV = "csv"


@dataclass
class BaseStatusResult:
    """
    Base class for all status results with common error handling.

    Provides consistent structure for status results across all components
    with standardized error handling and metadata tracking.
    """

    timestamp: datetime
    status: StatusLevel
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Ensure collections are properly initialized."""
        if self.details is None:  # type: ignore
            self.details = {}
        if self.errors is None:  # type: ignore
            self.errors = []

    def is_healthy(self) -> bool:
        """Check if the status is healthy."""
        return self.status == StatusLevel.HEALTHY

    def has_warnings(self) -> bool:
        """Check if the status has warnings."""
        return self.status == StatusLevel.WARNING

    def is_critical(self) -> bool:
        """Check if the status is critical."""
        return self.status == StatusLevel.CRITICAL

    def has_connection_failed(self) -> bool:
        """Check if connection has failed."""
        return self.status == StatusLevel.CONNECTION_FAILED

    def add_error(self, error: str) -> None:
        """Add an error message to the result."""
        self.errors.append(error)

    def add_detail(self, key: str, value: Any) -> None:
        """Add a detail to the result."""
        self.details[key] = value

    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return len(self.errors) > 0


@dataclass
class HealthStatus(BaseStatusResult):
    """
    Health status for Identity Center instance.

    Represents the overall health of the Identity Center instance
    including connectivity and service availability.
    """

    service_available: bool = True
    connectivity_status: str = "Connected"
    response_time_ms: Optional[float] = None
    last_successful_check: Optional[datetime] = None

    def get_health_summary(self) -> str:
        """Get a concise health summary."""
        if self.has_connection_failed():
            return f"Connection Failed: {self.message}"
        elif self.is_critical():
            return f"Critical: {self.message}"
        elif self.has_warnings():
            return f"Warning: {self.message}"
        else:
            return f"Healthy: {self.message}"


@dataclass
class ProvisioningOperation:
    """
    Represents an active or completed provisioning operation.

    Tracks individual provisioning operations including their status,
    timing, and associated resources.
    """

    operation_id: str
    operation_type: str
    status: ProvisioningOperationStatus
    target_id: str
    target_type: str
    created_date: datetime
    failure_reason: Optional[str] = None
    estimated_completion: Optional[datetime] = None

    def is_active(self) -> bool:
        """Check if the operation is currently active."""
        return self.status == ProvisioningOperationStatus.IN_PROGRESS

    def has_failed(self) -> bool:
        """Check if the operation has failed."""
        return self.status == ProvisioningOperationStatus.FAILED

    def is_completed(self) -> bool:
        """Check if the operation has completed successfully."""
        return self.status == ProvisioningOperationStatus.SUCCEEDED

    def get_duration_minutes(self) -> Optional[float]:
        """Get operation duration in minutes if completed."""
        if self.estimated_completion and self.created_date:
            delta = self.estimated_completion - self.created_date
            return delta.total_seconds() / 60
        return None


@dataclass
class ProvisioningStatus(BaseStatusResult):
    """
    Status of user provisioning operations.

    Aggregates information about all provisioning operations
    including active, failed, and completed operations.
    """

    active_operations: List[ProvisioningOperation] = field(default_factory=list)
    failed_operations: List[ProvisioningOperation] = field(default_factory=list)
    completed_operations: List[ProvisioningOperation] = field(default_factory=list)
    pending_count: int = 0
    estimated_completion: Optional[datetime] = None

    def __post_init__(self) -> None:
        """Initialize parent and ensure collections are properly set."""
        super().__post_init__()
        if self.active_operations is None:  # type: ignore
            self.active_operations = []
        if self.failed_operations is None:  # type: ignore
            self.failed_operations = []
        if self.completed_operations is None:  # type: ignore
            self.completed_operations = []

    def get_total_operations(self) -> int:
        """Get total number of operations."""
        return (
            len(self.active_operations)
            + len(self.failed_operations)
            + len(self.completed_operations)
        )

    def get_failure_rate(self) -> float:
        """Calculate failure rate as percentage."""
        total = self.get_total_operations()
        if total == 0:
            return 0.0
        return (len(self.failed_operations) / total) * 100.0

    def has_active_operations(self) -> bool:
        """Check if there are active operations."""
        return len(self.active_operations) > 0

    def has_failed_operations(self) -> bool:
        """Check if there are failed operations."""
        return len(self.failed_operations) > 0


@dataclass
class OrphanedAssignment:
    """
    Represents a permission set assignment with a deleted principal.

    Contains details about assignments where the principal (user or group)
    has been deleted from the identity provider but the assignment remains.
    """

    assignment_id: str
    permission_set_arn: str
    permission_set_name: str
    account_id: str
    account_name: Optional[str]
    principal_id: str
    principal_type: PrincipalType
    principal_name: Optional[str]  # May be None if principal is deleted
    error_message: str
    created_date: datetime
    last_accessed: Optional[datetime] = None

    def get_display_name(self) -> str:
        """Get a human-readable display name for the assignment."""
        principal_display = self.principal_name or f"Deleted {self.principal_type.value}"
        account_display = self.account_name or self.account_id
        return f"{principal_display} → {self.permission_set_name} @ {account_display}"

    def is_user_assignment(self) -> bool:
        """Check if this is a user assignment."""
        return self.principal_type == PrincipalType.USER

    def is_group_assignment(self) -> bool:
        """Check if this is a group assignment."""
        return self.principal_type == PrincipalType.GROUP

    def get_age_days(self) -> int:
        """Get the age of the assignment in days."""
        now = datetime.now(timezone.utc)
        created = self.created_date

        # Handle timezone-naive created_date by assuming UTC
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)

        delta = now - created
        return delta.days


@dataclass
class CleanupResult:
    """
    Result of orphaned assignment cleanup operation.

    Tracks the outcome of cleanup operations including
    success/failure counts and error details.
    """

    total_attempted: int
    successful_cleanups: int
    failed_cleanups: int
    cleanup_errors: List[str] = field(default_factory=list)
    cleaned_assignments: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    def __post_init__(self) -> None:
        """Ensure collections are properly initialized."""
        if self.cleanup_errors is None:  # type: ignore
            self.cleanup_errors = []
        if self.cleaned_assignments is None:  # type: ignore
            self.cleaned_assignments = []

    def get_success_rate(self) -> float:
        """Calculate cleanup success rate as percentage."""
        if self.total_attempted == 0:
            return 0.0
        return (self.successful_cleanups / self.total_attempted) * 100.0

    def has_failures(self) -> bool:
        """Check if there were any cleanup failures."""
        return self.failed_cleanups > 0

    def is_complete_success(self) -> bool:
        """Check if all cleanups were successful."""
        return self.failed_cleanups == 0 and self.successful_cleanups > 0


@dataclass
class OrphanedAssignmentStatus(BaseStatusResult):
    """
    Status of orphaned permission set assignments.

    Aggregates information about orphaned assignments and provides
    cleanup functionality and reporting.
    """

    orphaned_assignments: List[OrphanedAssignment] = field(default_factory=list)
    cleanup_available: bool = True
    last_cleanup: Optional[datetime] = None
    cleanup_history: List[CleanupResult] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Initialize parent and ensure collections are properly set."""
        super().__post_init__()
        if self.orphaned_assignments is None:  # type: ignore
            self.orphaned_assignments = []
        if self.cleanup_history is None:  # type: ignore
            self.cleanup_history = []

    def get_orphaned_count(self) -> int:
        """Get total number of orphaned assignments."""
        return len(self.orphaned_assignments)

    def get_user_orphans(self) -> List[OrphanedAssignment]:
        """Get orphaned user assignments."""
        return [a for a in self.orphaned_assignments if a.is_user_assignment()]

    def get_group_orphans(self) -> List[OrphanedAssignment]:
        """Get orphaned group assignments."""
        return [a for a in self.orphaned_assignments if a.is_group_assignment()]

    def has_orphaned_assignments(self) -> bool:
        """Check if there are any orphaned assignments."""
        return len(self.orphaned_assignments) > 0

    def get_accounts_with_orphans(self) -> List[str]:
        """Get list of account IDs that have orphaned assignments."""
        return list(set(a.account_id for a in self.orphaned_assignments))


@dataclass
class SyncStatus:
    """
    Synchronization status for an external identity provider.

    Tracks the synchronization state between Identity Center
    and external identity providers.
    """

    provider_name: str
    provider_type: SyncProviderType
    last_sync_time: Optional[datetime]
    sync_status: str
    next_sync_time: Optional[datetime] = None
    error_message: Optional[str] = None
    sync_duration_minutes: Optional[float] = None
    objects_synced: Optional[int] = None

    def is_sync_overdue(self, threshold_hours: int = 24) -> bool:
        """Check if synchronization is overdue."""
        if not self.last_sync_time:
            return True

        threshold = datetime.now(timezone.utc) - timedelta(hours=threshold_hours)
        return self.last_sync_time < threshold

    def has_sync_errors(self) -> bool:
        """Check if there are synchronization errors."""
        return self.error_message is not None

    def get_sync_age_hours(self) -> Optional[float]:
        """Get age of last sync in hours."""
        if not self.last_sync_time:
            return None

        delta = datetime.now(timezone.utc) - self.last_sync_time
        return delta.total_seconds() / 3600

    def is_healthy(self) -> bool:
        """Check if sync status is healthy."""
        return not self.has_sync_errors() and not self.is_sync_overdue()


@dataclass
class SyncMonitorStatus(BaseStatusResult):
    """
    Overall synchronization monitoring status.

    Aggregates synchronization status from all configured
    external identity providers.
    """

    sync_providers: List[SyncStatus] = field(default_factory=list)
    providers_configured: int = 0
    providers_healthy: int = 0
    providers_with_errors: int = 0

    def __post_init__(self) -> None:
        """Initialize parent and calculate provider counts."""
        super().__post_init__()
        if self.sync_providers is None:  # type: ignore
            self.sync_providers = []

        self.providers_configured = len(self.sync_providers)
        self.providers_healthy = len([p for p in self.sync_providers if p.is_healthy()])
        self.providers_with_errors = len([p for p in self.sync_providers if p.has_sync_errors()])

    def has_providers_configured(self) -> bool:
        """Check if any providers are configured."""
        return self.providers_configured > 0

    def get_overdue_providers(self) -> List[SyncStatus]:
        """Get list of providers with overdue synchronization."""
        return [p for p in self.sync_providers if p.is_sync_overdue()]

    def get_error_providers(self) -> List[SyncStatus]:
        """Get list of providers with sync errors."""
        return [p for p in self.sync_providers if p.has_sync_errors()]

    def get_health_percentage(self) -> float:
        """Get percentage of healthy providers."""
        if self.providers_configured == 0:
            return 100.0
        return (self.providers_healthy / self.providers_configured) * 100.0


@dataclass
class ResourceStatus:
    """
    Status information for a specific resource.

    Contains detailed status information for individual
    Identity Center resources like users, groups, or permission sets.
    """

    resource_id: str
    resource_name: str
    resource_type: ResourceType
    exists: bool
    status: StatusLevel
    last_updated: Optional[datetime] = None
    configuration: Dict[str, Any] = field(default_factory=dict)
    health_details: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None

    def __post_init__(self) -> None:
        """Ensure collections are properly initialized."""
        if self.configuration is None:  # type: ignore
            self.configuration = {}
        if self.health_details is None:  # type: ignore
            self.health_details = {}

    def is_healthy(self) -> bool:
        """Check if the resource is healthy."""
        return self.exists and self.status == StatusLevel.HEALTHY

    def has_issues(self) -> bool:
        """Check if the resource has any issues."""
        return not self.exists or self.status in [StatusLevel.WARNING, StatusLevel.CRITICAL]

    def get_display_name(self) -> str:
        """Get a human-readable display name."""
        return f"{self.resource_name} ({self.resource_type.value})"

    def get_age_days(self) -> Optional[int]:
        """Get age of resource in days since last update."""
        if not self.last_updated:
            return None

        delta = datetime.now(timezone.utc) - self.last_updated
        return delta.days


@dataclass
class ResourceInspectionStatus(BaseStatusResult):
    """
    Status result for resource inspection operations.

    Contains results from inspecting specific Identity Center resources
    including suggestions for similar resources when target not found.
    """

    target_resource: Optional[ResourceStatus] = None
    similar_resources: List[str] = field(default_factory=list)
    inspection_type: Optional[ResourceType] = None

    def __post_init__(self) -> None:
        """Initialize parent and ensure collections are properly set."""
        super().__post_init__()
        if self.similar_resources is None:  # type: ignore
            self.similar_resources = []

    def resource_found(self) -> bool:
        """Check if the target resource was found."""
        return self.target_resource is not None and self.target_resource.exists

    def has_suggestions(self) -> bool:
        """Check if there are similar resource suggestions."""
        return len(self.similar_resources) > 0

    def get_resource_summary(self) -> str:
        """Get a summary of the resource inspection."""
        if self.resource_found() and self.target_resource is not None:
            return f"Found: {self.target_resource.get_display_name()}"
        elif self.has_suggestions():
            return f"Not found, {len(self.similar_resources)} similar resources available"
        else:
            return "Resource not found, no similar resources"


@dataclass
class SummaryStatistics:
    """
    Summary statistics for Identity Center deployment.

    Provides aggregate counts and metrics for the overall
    Identity Center deployment including users, groups, and assignments.
    """

    total_users: int
    total_groups: int
    total_permission_sets: int
    total_assignments: int
    active_accounts: int
    last_updated: datetime
    user_creation_dates: Dict[str, datetime] = field(default_factory=dict)
    group_creation_dates: Dict[str, datetime] = field(default_factory=dict)
    permission_set_creation_dates: Dict[str, datetime] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Ensure collections are properly initialized."""
        if self.user_creation_dates is None:  # type: ignore
            self.user_creation_dates = {}
        if self.group_creation_dates is None:  # type: ignore
            self.group_creation_dates = {}
        if self.permission_set_creation_dates is None:  # type: ignore
            self.permission_set_creation_dates = {}

    def get_total_principals(self) -> int:
        """Get total number of principals (users + groups)."""
        return self.total_users + self.total_groups

    def get_assignments_per_account(self) -> float:
        """Get average assignments per account."""
        if self.active_accounts == 0:
            return 0.0
        return self.total_assignments / self.active_accounts

    def get_assignments_per_permission_set(self) -> float:
        """Get average assignments per permission set."""
        if self.total_permission_sets == 0:
            return 0.0
        return self.total_assignments / self.total_permission_sets

    def get_newest_user_date(self) -> Optional[datetime]:
        """Get creation date of newest user."""
        if not self.user_creation_dates:
            return None
        return max(self.user_creation_dates.values())

    def get_oldest_user_date(self) -> Optional[datetime]:
        """Get creation date of oldest user."""
        if not self.user_creation_dates:
            return None
        return min(self.user_creation_dates.values())


@dataclass
class StatusReport:
    """
    Comprehensive status report aggregating all status types.

    Central model that combines results from all status checking components
    to provide a complete view of Identity Center health and status.
    """

    timestamp: datetime
    overall_health: HealthStatus
    provisioning_status: ProvisioningStatus
    orphaned_assignment_status: OrphanedAssignmentStatus
    sync_status: SyncMonitorStatus
    summary_statistics: SummaryStatistics
    resource_inspections: List[ResourceInspectionStatus] = field(default_factory=list)
    check_duration_seconds: float = 0.0

    def __post_init__(self) -> None:
        """Ensure collections are properly initialized."""
        if self.resource_inspections is None:  # type: ignore
            self.resource_inspections = []

    def get_overall_status_level(self) -> StatusLevel:
        """Determine overall status level from all components."""
        # Connection failure takes precedence
        if self.overall_health.has_connection_failed():
            return StatusLevel.CONNECTION_FAILED

        # Check for critical issues
        critical_conditions = [
            self.overall_health.is_critical(),
            self.provisioning_status.is_critical(),
            self.orphaned_assignment_status.is_critical(),
            self.sync_status.is_critical(),
        ]

        if any(critical_conditions):
            return StatusLevel.CRITICAL

        # Check for warnings
        warning_conditions = [
            self.overall_health.has_warnings(),
            self.provisioning_status.has_warnings(),
            self.orphaned_assignment_status.has_warnings(),
            self.sync_status.has_warnings(),
            self.orphaned_assignment_status.has_orphaned_assignments(),
            len(self.sync_status.get_overdue_providers()) > 0,
        ]

        if any(warning_conditions):
            return StatusLevel.WARNING

        return StatusLevel.HEALTHY

    def get_status_summary(self) -> str:
        """Get a concise status summary."""
        status_level = self.get_overall_status_level()

        if status_level == StatusLevel.CONNECTION_FAILED:
            return "Identity Center connection failed"
        elif status_level == StatusLevel.CRITICAL:
            return "Critical issues detected"
        elif status_level == StatusLevel.WARNING:
            return "Warnings detected - review recommended"
        else:
            return "All systems healthy"

    def has_issues(self) -> bool:
        """Check if there are any issues requiring attention."""
        return self.get_overall_status_level() != StatusLevel.HEALTHY

    def get_issue_count(self) -> int:
        """Get total number of issues across all components."""
        count = 0
        count += len(self.overall_health.errors)
        count += len(self.provisioning_status.errors)
        count += len(self.orphaned_assignment_status.errors)
        count += len(self.sync_status.errors)
        count += self.orphaned_assignment_status.get_orphaned_count()
        count += len(self.sync_status.get_error_providers())
        return count

    def get_component_statuses(self) -> Dict[str, StatusLevel]:
        """Get status level for each component."""
        return {
            "health": self.overall_health.status,
            "provisioning": self.provisioning_status.status,
            "orphaned_assignments": self.orphaned_assignment_status.status,
            "sync": self.sync_status.status,
        }


@dataclass
class FormattedOutput:
    """
    Formatted output for different display formats.

    Contains the formatted status data in the requested format
    along with metadata about the formatting.
    """

    format_type: OutputFormat
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        """Ensure metadata is properly initialized."""
        if self.metadata is None:  # type: ignore
            self.metadata = {}

    def get_content_length(self) -> int:
        """Get length of formatted content."""
        return len(self.content)

    def is_json_format(self) -> bool:
        """Check if output is in JSON format."""
        return self.format_type == OutputFormat.JSON

    def is_csv_format(self) -> bool:
        """Check if output is in CSV format."""
        return self.format_type == OutputFormat.CSV

    def is_table_format(self) -> bool:
        """Check if output is in table format."""
        return self.format_type == OutputFormat.TABLE


# Type aliases for common use cases
StatusResultList = List[BaseStatusResult]
OrphanedAssignmentList = List[OrphanedAssignment]
ProvisioningOperationList = List[ProvisioningOperation]
SyncStatusList = List[SyncStatus]
ResourceStatusList = List[ResourceStatus]
