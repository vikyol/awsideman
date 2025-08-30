"""
Data models for backup diff operations.

This module defines all the data structures used for comparing backups and
identifying differences between AWS Identity Center configurations at different
points in time.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ChangeType(Enum):
    """Types of changes that can occur to resources."""

    CREATED = "created"
    DELETED = "deleted"
    MODIFIED = "modified"


class DiffFormat(Enum):
    """Supported output formats for diff results."""

    CONSOLE = "console"
    JSON = "json"
    CSV = "csv"
    HTML = "html"


@dataclass
class AttributeChange:
    """Represents a change to a specific attribute of a resource."""

    attribute_name: str
    before_value: Any
    after_value: Any

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "attribute_name": self.attribute_name,
            "before_value": self.before_value,
            "after_value": self.after_value,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AttributeChange":
        """Create from dictionary."""
        return cls(
            attribute_name=data["attribute_name"],
            before_value=data["before_value"],
            after_value=data["after_value"],
        )


@dataclass
class ResourceChange:
    """Represents a change to a single resource."""

    change_type: ChangeType
    resource_type: str  # users, groups, permission_sets, assignments
    resource_id: str
    resource_name: Optional[str] = None
    before_value: Optional[Dict[str, Any]] = None
    after_value: Optional[Dict[str, Any]] = None
    attribute_changes: List[AttributeChange] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Post-initialization validation."""
        if not self.resource_id:
            raise ValueError("resource_id cannot be empty")
        if not self.resource_type:
            raise ValueError("resource_type cannot be empty")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "change_type": self.change_type.value,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "resource_name": self.resource_name,
            "before_value": self.before_value,
            "after_value": self.after_value,
            "attribute_changes": [change.to_dict() for change in self.attribute_changes],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResourceChange":
        """Create from dictionary."""
        return cls(
            change_type=ChangeType(data["change_type"]),
            resource_type=data["resource_type"],
            resource_id=data["resource_id"],
            resource_name=data.get("resource_name"),
            before_value=data.get("before_value"),
            after_value=data.get("after_value"),
            attribute_changes=[
                AttributeChange.from_dict(change) for change in data.get("attribute_changes", [])
            ],
        )


@dataclass
class ResourceDiff:
    """Differences for a specific resource type."""

    resource_type: str
    created: List[ResourceChange] = field(default_factory=list)
    deleted: List[ResourceChange] = field(default_factory=list)
    modified: List[ResourceChange] = field(default_factory=list)

    @property
    def total_changes(self) -> int:
        """Get total number of changes for this resource type."""
        return len(self.created) + len(self.deleted) + len(self.modified)

    @property
    def has_changes(self) -> bool:
        """Check if there are any changes for this resource type."""
        return self.total_changes > 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "resource_type": self.resource_type,
            "created": [change.to_dict() for change in self.created],
            "deleted": [change.to_dict() for change in self.deleted],
            "modified": [change.to_dict() for change in self.modified],
            "total_changes": self.total_changes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResourceDiff":
        """Create from dictionary."""
        return cls(
            resource_type=data["resource_type"],
            created=[ResourceChange.from_dict(change) for change in data.get("created", [])],
            deleted=[ResourceChange.from_dict(change) for change in data.get("deleted", [])],
            modified=[ResourceChange.from_dict(change) for change in data.get("modified", [])],
        )


@dataclass
class DiffSummary:
    """High-level summary of changes between two backups."""

    total_changes: int
    changes_by_type: Dict[str, int] = field(default_factory=dict)  # resource_type -> change_count
    changes_by_action: Dict[str, int] = field(default_factory=dict)  # action -> change_count

    def __post_init__(self) -> None:
        """Post-initialization validation."""
        if self.total_changes < 0:
            raise ValueError("total_changes cannot be negative")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total_changes": self.total_changes,
            "changes_by_type": self.changes_by_type,
            "changes_by_action": self.changes_by_action,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DiffSummary":
        """Create from dictionary."""
        return cls(
            total_changes=data["total_changes"],
            changes_by_type=data.get("changes_by_type", {}),
            changes_by_action=data.get("changes_by_action", {}),
        )


@dataclass
class DiffResult:
    """Complete diff result between two backups."""

    source_backup_id: str
    target_backup_id: str
    source_timestamp: datetime
    target_timestamp: datetime
    user_diff: ResourceDiff
    group_diff: ResourceDiff
    permission_set_diff: ResourceDiff
    assignment_diff: ResourceDiff
    summary: DiffSummary

    def __post_init__(self) -> None:
        """Post-initialization validation and summary calculation."""
        if not self.source_backup_id:
            raise ValueError("source_backup_id cannot be empty")
        if not self.target_backup_id:
            raise ValueError("target_backup_id cannot be empty")

        # Ensure all resource diffs have correct resource types
        if self.user_diff.resource_type != "users":
            self.user_diff.resource_type = "users"
        if self.group_diff.resource_type != "groups":
            self.group_diff.resource_type = "groups"
        if self.permission_set_diff.resource_type != "permission_sets":
            self.permission_set_diff.resource_type = "permission_sets"
        if self.assignment_diff.resource_type != "assignments":
            self.assignment_diff.resource_type = "assignments"

        # Update summary if not provided or inconsistent
        self._update_summary()

    def _update_summary(self) -> None:
        """Update the summary based on current diff data."""
        total_changes = (
            self.user_diff.total_changes
            + self.group_diff.total_changes
            + self.permission_set_diff.total_changes
            + self.assignment_diff.total_changes
        )

        changes_by_type = {
            "users": self.user_diff.total_changes,
            "groups": self.group_diff.total_changes,
            "permission_sets": self.permission_set_diff.total_changes,
            "assignments": self.assignment_diff.total_changes,
        }

        changes_by_action = {
            "created": (
                len(self.user_diff.created)
                + len(self.group_diff.created)
                + len(self.permission_set_diff.created)
                + len(self.assignment_diff.created)
            ),
            "deleted": (
                len(self.user_diff.deleted)
                + len(self.group_diff.deleted)
                + len(self.permission_set_diff.deleted)
                + len(self.assignment_diff.deleted)
            ),
            "modified": (
                len(self.user_diff.modified)
                + len(self.group_diff.modified)
                + len(self.permission_set_diff.modified)
                + len(self.assignment_diff.modified)
            ),
        }

        self.summary = DiffSummary(
            total_changes=total_changes,
            changes_by_type=changes_by_type,
            changes_by_action=changes_by_action,
        )

    @property
    def has_changes(self) -> bool:
        """Check if there are any changes between the backups."""
        return any(
            [
                self.user_diff.has_changes,
                self.group_diff.has_changes,
                self.permission_set_diff.has_changes,
                self.assignment_diff.has_changes,
            ]
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "source_backup_id": self.source_backup_id,
            "target_backup_id": self.target_backup_id,
            "source_timestamp": self.source_timestamp.isoformat(),
            "target_timestamp": self.target_timestamp.isoformat(),
            "user_diff": self.user_diff.to_dict(),
            "group_diff": self.group_diff.to_dict(),
            "permission_set_diff": self.permission_set_diff.to_dict(),
            "assignment_diff": self.assignment_diff.to_dict(),
            "summary": self.summary.to_dict(),
            "has_changes": self.has_changes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DiffResult":
        """Create from dictionary."""
        return cls(
            source_backup_id=data["source_backup_id"],
            target_backup_id=data["target_backup_id"],
            source_timestamp=datetime.fromisoformat(data["source_timestamp"]),
            target_timestamp=datetime.fromisoformat(data["target_timestamp"]),
            user_diff=ResourceDiff.from_dict(data["user_diff"]),
            group_diff=ResourceDiff.from_dict(data["group_diff"]),
            permission_set_diff=ResourceDiff.from_dict(data["permission_set_diff"]),
            assignment_diff=ResourceDiff.from_dict(data["assignment_diff"]),
            summary=DiffSummary.from_dict(data["summary"]),
        )
