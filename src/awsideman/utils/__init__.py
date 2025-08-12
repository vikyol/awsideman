"""Core utility modules for awsideman."""

# Configuration utilities
from .config import CONFIG_DIR, CONFIG_FILE_JSON, CONFIG_FILE_YAML, DEFAULT_CACHE_CONFIG, Config

# Error handling utilities
from .error_handler import get_error_handler, handle_status_error

# Data models
from .models import (
    AccountDetails,
    CacheConfig,
    CacheEntry,
    HierarchyPath,
    NodeType,
    OrganizationTree,
    OrgNode,
    PolicyInfo,
    PolicyList,
    PolicyType,
    TagDict,
)
from .status_factory import (
    StatusConfigBuilder,
    StatusFactory,
    create_default_status_factory,
    create_fast_status_factory,
    create_robust_status_factory,
)
from .status_infrastructure import (
    BaseStatusChecker,
    ConnectionError,
    FormatterRegistry,
    OutputFormatter,
    PermissionError,
    StatusCheckConfig,
    StatusCheckError,
    StatusOrchestrator,
    TimeoutError,
    formatter_registry,
)

# Status monitoring models and infrastructure
from .status_models import (
    BaseStatusResult,
    CleanupResult,
    FormattedOutput,
    HealthStatus,
    OrphanedAssignment,
    OrphanedAssignmentStatus,
    OutputFormat,
    PrincipalType,
    ProvisioningOperation,
    ProvisioningOperationStatus,
    ProvisioningStatus,
    ResourceInspectionStatus,
    ResourceStatus,
    ResourceType,
    StatusLevel,
    StatusReport,
    SummaryStatistics,
    SyncMonitorStatus,
    SyncProviderType,
    SyncStatus,
)

# Validation utilities
from .validators import (
    validate_email,
    validate_filter,
    validate_group_description,
    validate_group_name,
    validate_limit,
    validate_non_empty,
    validate_profile,
    validate_sso_instance,
    validate_uuid,
)

__all__ = [
    # Configuration
    "Config",
    "DEFAULT_CACHE_CONFIG",
    "CONFIG_DIR",
    "CONFIG_FILE_YAML",
    "CONFIG_FILE_JSON",
    # Error handling
    "get_error_handler",
    "handle_status_error",
    # Data models
    "NodeType",
    "PolicyType",
    "OrgNode",
    "AccountDetails",
    "PolicyInfo",
    "HierarchyPath",
    "CacheEntry",
    "CacheConfig",
    "OrganizationTree",
    "PolicyList",
    "TagDict",
    # Validators
    "validate_uuid",
    "validate_email",
    "validate_filter",
    "validate_non_empty",
    "validate_limit",
    "validate_group_name",
    "validate_group_description",
    "validate_profile",
    "validate_sso_instance",
    # Status monitoring models
    "StatusLevel",
    "PrincipalType",
    "ProvisioningOperationStatus",
    "SyncProviderType",
    "ResourceType",
    "OutputFormat",
    "BaseStatusResult",
    "HealthStatus",
    "ProvisioningOperation",
    "ProvisioningStatus",
    "OrphanedAssignment",
    "CleanupResult",
    "OrphanedAssignmentStatus",
    "SyncStatus",
    "SyncMonitorStatus",
    "ResourceStatus",
    "ResourceInspectionStatus",
    "SummaryStatistics",
    "StatusReport",
    "FormattedOutput",
    # Status infrastructure
    "StatusCheckError",
    "ConnectionError",
    "PermissionError",
    "TimeoutError",
    "StatusCheckConfig",
    "BaseStatusChecker",
    "StatusOrchestrator",
    "OutputFormatter",
    "FormatterRegistry",
    "formatter_registry",
    # Status factory
    "StatusFactory",
    "StatusConfigBuilder",
    "create_default_status_factory",
    "create_fast_status_factory",
    "create_robust_status_factory",
]
