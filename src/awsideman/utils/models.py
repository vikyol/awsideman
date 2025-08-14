"""Data models for AWS Organizations structure and metadata."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional


class NodeType(str, Enum):
    """Enumeration for organization node types."""

    ROOT = "ROOT"
    OU = "OU"
    ACCOUNT = "ACCOUNT"


class PolicyType(str, Enum):
    """Enumeration for AWS Organizations policy types."""

    SERVICE_CONTROL_POLICY = "SERVICE_CONTROL_POLICY"
    RESOURCE_CONTROL_POLICY = "RESOURCE_CONTROL_POLICY"


@dataclass
class OrgNode:
    """
    Represents a node in the AWS Organizations hierarchy.

    This can be a root, organizational unit (OU), or account.
    """

    id: str
    name: str
    type: NodeType
    children: List["OrgNode"]

    def __post_init__(self):
        """Ensure children is always a list."""
        if self.children is None:
            self.children = []

    def add_child(self, child: "OrgNode") -> None:
        """Add a child node to this node."""
        self.children.append(child)

    def is_root(self) -> bool:
        """Check if this node is a root."""
        return self.type == NodeType.ROOT

    def is_ou(self) -> bool:
        """Check if this node is an organizational unit."""
        return self.type == NodeType.OU

    def is_account(self) -> bool:
        """Check if this node is an account."""
        return self.type == NodeType.ACCOUNT


@dataclass
class AccountDetails:
    """
    Comprehensive metadata for an AWS account.

    Contains all relevant information about an account including
    its organizational context and metadata.
    """

    id: str
    name: str
    email: str
    status: str
    joined_timestamp: datetime
    tags: Dict[str, str]
    ou_path: List[str]  # List of OU IDs or names from root to account

    def __post_init__(self):
        """Ensure collections are properly initialized."""
        if self.tags is None:
            self.tags = {}
        if self.ou_path is None:
            self.ou_path = []

    def get_tag(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get a tag value by key."""
        return self.tags.get(key, default)

    def has_tag(self, key: str, value: Optional[str] = None) -> bool:
        """Check if account has a specific tag, optionally with a specific value."""
        if key not in self.tags:
            return False
        if value is None:
            return True
        return self.tags[key] == value


@dataclass
class PolicyInfo:
    """
    Information about a policy attached to an organization target.

    Represents either a Service Control Policy (SCP) or Resource Control Policy (RCP).
    """

    id: str
    name: str
    type: PolicyType
    description: Optional[str]
    aws_managed: bool
    attachment_point: str  # ID of the target where policy is attached
    attachment_point_name: Optional[str]  # Human-readable name of attachment point
    effective_status: str  # Status of the policy (e.g., "ENABLED", "DISABLED")

    def __post_init__(self):
        """Set default values for optional fields."""
        if self.description is None:
            self.description = ""
        if self.attachment_point_name is None:
            self.attachment_point_name = self.attachment_point

    def is_scp(self) -> bool:
        """Check if this is a Service Control Policy."""
        return self.type == PolicyType.SERVICE_CONTROL_POLICY

    def is_rcp(self) -> bool:
        """Check if this is a Resource Control Policy."""
        return self.type == PolicyType.RESOURCE_CONTROL_POLICY


@dataclass
class HierarchyPath:
    """
    Represents a path through the organization hierarchy.

    Contains both IDs and names for each level from root to target.
    """

    ids: List[str]  # List of IDs from root to target
    names: List[str]  # List of names from root to target
    types: List[NodeType]  # List of node types from root to target

    def __post_init__(self):
        """Ensure all lists are properly initialized and have same length."""
        if self.ids is None:
            self.ids = []
        if self.names is None:
            self.names = []
        if self.types is None:
            self.types = []

        # Ensure all lists have the same length
        max_len = max(len(self.ids), len(self.names), len(self.types))
        self.ids.extend([""] * (max_len - len(self.ids)))
        self.names.extend([""] * (max_len - len(self.names)))
        self.types.extend([NodeType.OU] * (max_len - len(self.types)))

    def depth(self) -> int:
        """Get the depth of the hierarchy path."""
        return len(self.ids)

    def get_path_string(self, separator: str = " → ") -> str:
        """Get a human-readable string representation of the path."""
        return separator.join(self.names)

    def get_id_path_string(self, separator: str = "/") -> str:
        """Get a string representation of the path using IDs."""
        return separator.join(self.ids)


# Cache-related data models


@dataclass
class CacheEntry:
    """
    Represents a cached data entry with metadata.

    Stores the actual cached data along with metadata needed
    for cache management including expiration and operation tracking.
    """

    data: Any  # The actual cached data
    created_at: float  # Timestamp when entry was created (Unix timestamp)
    ttl: int  # Time-to-live in seconds
    key: str  # Cache key
    operation: str  # AWS operation that generated this data

    def is_expired(self, current_time: Optional[float] = None) -> bool:
        """Check if the cache entry has expired.

        Args:
            current_time: Optional current timestamp. If not provided, uses current time.

        Returns:
            True if the entry has expired, False otherwise
        """
        if current_time is None:
            import time

            current_time = time.time()

        return (current_time - self.created_at) > self.ttl

    def age_seconds(self, current_time: Optional[float] = None) -> float:
        """Get the age of the cache entry in seconds.

        Args:
            current_time: Optional current timestamp. If not provided, uses current time.

        Returns:
            Age in seconds
        """
        if current_time is None:
            import time

            current_time = time.time()

        return current_time - self.created_at

    def remaining_ttl(self, current_time: Optional[float] = None) -> float:
        """Get the remaining TTL in seconds.

        Args:
            current_time: Optional current timestamp. If not provided, uses current time.

        Returns:
            Remaining TTL in seconds (negative if expired)
        """
        if current_time is None:
            import time

            current_time = time.time()

        return self.ttl - (current_time - self.created_at)


@dataclass
class CacheConfig:
    """
    Configuration settings for the cache system.

    Defines cache behavior including TTL settings, size limits,
    and operation-specific configurations.
    """

    enabled: bool = True  # Whether caching is enabled
    default_ttl: int = 3600  # Default TTL in seconds (1 hour)
    operation_ttls: Dict[str, int] = field(default_factory=dict)  # Operation-specific TTLs
    max_size_mb: int = 100  # Maximum cache size in MB

    def get_ttl_for_operation(self, operation: str) -> int:
        """Get TTL for a specific operation.

        Args:
            operation: AWS operation name

        Returns:
            TTL in seconds for the operation
        """
        return self.operation_ttls.get(operation, self.default_ttl)

    def set_operation_ttl(self, operation: str, ttl: int) -> None:
        """Set TTL for a specific operation.

        Args:
            operation: AWS operation name
            ttl: TTL in seconds
        """
        self.operation_ttls[operation] = ttl

    def max_size_bytes(self) -> int:
        """Get maximum cache size in bytes.

        Returns:
            Maximum size in bytes
        """
        return self.max_size_mb * 1024 * 1024


# Multi-account operation data models


@dataclass
class AccountInfo:
    """
    Account metadata and tag matching for multi-account operations.

    Contains essential account information needed for filtering and
    multi-account operations including tag-based filtering support.
    """

    account_id: str
    account_name: str
    email: str
    status: str
    tags: Dict[str, str] = field(default_factory=dict)
    ou_path: List[str] = field(default_factory=list)

    def matches_tag_filter(self, tag_key: str, tag_value: str) -> bool:
        """Check if account matches a specific tag filter.

        Args:
            tag_key: The tag key to match
            tag_value: The tag value to match

        Returns:
            True if account has the specified tag key-value pair
        """
        return self.tags.get(tag_key) == tag_value

    def get_display_name(self) -> str:
        """Get a human-readable display name for the account.

        Returns:
            Account name with ID in parentheses
        """
        return f"{self.account_name} ({self.account_id})"

    def has_tag(self, key: str, value: Optional[str] = None) -> bool:
        """Check if account has a specific tag, optionally with a specific value.

        Args:
            key: Tag key to check
            value: Optional tag value to match

        Returns:
            True if account has the tag (and value if specified)
        """
        if key not in self.tags:
            return False
        if value is None:
            return True
        return self.tags[key] == value


@dataclass
class AccountResult:
    """
    Individual account operation result for multi-account operations.

    Tracks the outcome of a single account operation including
    success/failure status, error details, and performance metrics.
    """

    account_id: str
    account_name: str
    status: Literal["success", "failed", "skipped"]
    error_message: Optional[str] = None
    processing_time: float = 0.0
    retry_count: int = 0
    timestamp: Optional[float] = None

    def __post_init__(self):
        """Set timestamp if not provided."""
        if self.timestamp is None:
            import time

            self.timestamp = time.time()

    def is_successful(self) -> bool:
        """Check if the operation was successful.

        Returns:
            True if status is 'success'
        """
        return self.status == "success"

    def get_error_summary(self) -> str:
        """Get a concise error summary for display.

        Returns:
            Error message or status if no error message
        """
        if self.error_message:
            return self.error_message
        return f"Status: {self.status}"

    def get_display_name(self) -> str:
        """Get a human-readable display name for the account.

        Returns:
            Account name with ID in parentheses
        """
        return f"{self.account_name} ({self.account_id})"


@dataclass
class MultiAccountAssignment:
    """
    Multi-account assignment model with name resolution capabilities.

    Represents a permission set assignment or revocation operation
    across multiple accounts with support for name resolution.
    """

    permission_set_name: str
    principal_name: str
    principal_type: str
    accounts: List[AccountInfo]
    operation: Literal["assign", "revoke"]

    # Resolved values (populated after name resolution)
    permission_set_arn: Optional[str] = None
    principal_id: Optional[str] = None

    def get_total_operations(self) -> int:
        """Get the total number of operations to be performed.

        Returns:
            Number of accounts multiplied by operations per account
        """
        return len(self.accounts)

    def validate(self) -> List[str]:
        """Validate the assignment configuration.

        Returns:
            List of validation error messages
        """
        errors = []

        if not self.permission_set_name.strip():
            errors.append("Permission set name cannot be empty")

        if not self.principal_name.strip():
            errors.append("Principal name cannot be empty")

        if self.principal_type not in ["USER", "GROUP"]:
            errors.append(f"Invalid principal type: {self.principal_type}")

        if not self.accounts:
            errors.append("At least one account must be specified")

        if self.operation not in ["assign", "revoke"]:
            errors.append(f"Invalid operation: {self.operation}")

        return errors

    def is_resolved(self) -> bool:
        """Check if names have been resolved to ARNs/IDs.

        Returns:
            True if both permission set ARN and principal ID are resolved
        """
        return self.permission_set_arn is not None and self.principal_id is not None

    def get_account_ids(self) -> List[str]:
        """Get list of account IDs for this assignment.

        Returns:
            List of account IDs
        """
        return [account.account_id for account in self.accounts]


@dataclass
class MultiAccountResults:
    """
    Aggregation class for multi-account operation results with success rate calculations.

    Collects and analyzes results from multi-account operations providing
    summary statistics and success rate calculations.
    """

    total_accounts: int
    successful_accounts: List[AccountResult]
    failed_accounts: List[AccountResult]
    skipped_accounts: List[AccountResult]
    operation_type: str
    duration: float
    batch_size: int

    def __post_init__(self):
        """Validate that account counts match."""
        calculated_total = (
            len(self.successful_accounts) + len(self.failed_accounts) + len(self.skipped_accounts)
        )
        if calculated_total != self.total_accounts:
            # Auto-correct total_accounts to match actual results
            self.total_accounts = calculated_total

    @property
    def success_rate(self) -> float:
        """Calculate the success rate as a percentage.

        Returns:
            Success rate as a float between 0.0 and 100.0
        """
        if self.total_accounts == 0:
            return 0.0
        return (len(self.successful_accounts) / self.total_accounts) * 100.0

    @property
    def failure_rate(self) -> float:
        """Calculate the failure rate as a percentage.

        Returns:
            Failure rate as a float between 0.0 and 100.0
        """
        if self.total_accounts == 0:
            return 0.0
        return (len(self.failed_accounts) / self.total_accounts) * 100.0

    @property
    def skip_rate(self) -> float:
        """Calculate the skip rate as a percentage.

        Returns:
            Skip rate as a float between 0.0 and 100.0
        """
        if self.total_accounts == 0:
            return 0.0
        return (len(self.skipped_accounts) / self.total_accounts) * 100.0

    def get_summary_stats(self) -> Dict[str, Any]:
        """Get comprehensive summary statistics.

        Returns:
            Dictionary containing all relevant statistics
        """
        return {
            "total_accounts": self.total_accounts,
            "successful_count": len(self.successful_accounts),
            "failed_count": len(self.failed_accounts),
            "skipped_count": len(self.skipped_accounts),
            "success_rate": round(self.success_rate, 2),
            "failure_rate": round(self.failure_rate, 2),
            "skip_rate": round(self.skip_rate, 2),
            "operation_type": self.operation_type,
            "duration_seconds": round(self.duration, 2),
            "batch_size": self.batch_size,
            "average_processing_time": self._calculate_average_processing_time(),
        }

    def _calculate_average_processing_time(self) -> float:
        """Calculate average processing time per account.

        Returns:
            Average processing time in seconds
        """
        all_results = self.successful_accounts + self.failed_accounts + self.skipped_accounts
        if not all_results:
            return 0.0

        total_time = sum(result.processing_time for result in all_results)
        return round(total_time / len(all_results), 3)

    def has_failures(self) -> bool:
        """Check if there were any failures.

        Returns:
            True if any accounts failed
        """
        return len(self.failed_accounts) > 0

    def is_complete_success(self) -> bool:
        """Check if all operations were successful.

        Returns:
            True if all accounts succeeded (no failures or skips)
        """
        return len(self.failed_accounts) == 0 and len(self.skipped_accounts) == 0

    def get_failed_account_ids(self) -> List[str]:
        """Get list of account IDs that failed.

        Returns:
            List of account IDs for failed operations
        """
        return [result.account_id for result in self.failed_accounts]

    def get_successful_account_ids(self) -> List[str]:
        """Get list of account IDs that succeeded.

        Returns:
            List of account IDs for successful operations
        """
        return [result.account_id for result in self.successful_accounts]


# Type aliases for common use cases
OrganizationTree = List[OrgNode]
PolicyList = List[PolicyInfo]
TagDict = Dict[str, str]
MultiAccountResultsList = List[AccountResult]
