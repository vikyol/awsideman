"""
Template data models for AWS Identity Center permission assignments.

This module defines the core data structures used to represent templates,
including metadata, targets, assignments, and validation methods.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class TemplateMetadata:
    """Template metadata and documentation."""

    name: str
    description: Optional[str] = None
    version: Optional[str] = None
    author: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        """Set default timestamps if not provided."""
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TemplateMetadata":
        """Create metadata from dictionary."""
        # Parse datetime strings if present
        created_at = None
        updated_at = None

        if data.get("created_at"):
            try:
                created_at = datetime.fromisoformat(data["created_at"])
            except ValueError:
                pass

        if data.get("updated_at"):
            try:
                updated_at = datetime.fromisoformat(data["updated_at"])
            except ValueError:
                pass

        return cls(
            name=data["name"],
            description=data.get("description"),
            version=data.get("version"),
            author=data.get("author"),
            created_at=created_at,
            updated_at=updated_at,
        )


@dataclass
class TemplateTarget:
    """Defines assignment targets (accounts)."""

    account_ids: Optional[List[str]] = None
    account_tags: Optional[Dict[str, str]] = None
    exclude_accounts: Optional[List[str]] = None

    def __post_init__(self):
        """Validate target configuration."""
        if not any([self.account_ids, self.account_tags]):
            raise ValueError("Either account_ids or account_tags must be specified")

        if self.account_ids and self.account_tags:
            raise ValueError("Cannot specify both account_ids and account_tags")

    def to_dict(self) -> Dict[str, Any]:
        """Convert target to dictionary."""
        return {
            "account_ids": self.account_ids,
            "account_tags": self.account_tags,
            "exclude_accounts": self.exclude_accounts,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TemplateTarget":
        """Create target from dictionary."""
        return cls(
            account_ids=data.get("account_ids"),
            account_tags=data.get("account_tags"),
            exclude_accounts=data.get("exclude_accounts"),
        )

    def get_account_count_estimate(self) -> int:
        """Get estimated number of accounts this target will affect."""
        if self.account_ids:
            return len(self.account_ids)
        elif self.account_tags:
            # For tag-based targets, we can't know the exact count without resolving
            # Return a placeholder value indicating it needs resolution
            return -1
        return 0


@dataclass
class TemplateAssignment:
    """Individual assignment definition within a template."""

    entities: List[str]  # user:name or group:name format
    permission_sets: List[str]  # permission set names or ARNs
    targets: TemplateTarget

    def __post_init__(self):
        """Validate assignment configuration."""
        if not self.entities:
            raise ValueError("At least one entity must be specified")
        if not self.permission_sets:
            raise ValueError("At least one permission set must be specified")
        if not self.targets:
            raise ValueError("Targets must be specified")

    def to_dict(self) -> Dict[str, Any]:
        """Convert assignment to dictionary."""
        return {
            "entities": self.entities,
            "permission_sets": self.permission_sets,
            "targets": self.targets.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TemplateAssignment":
        """Create assignment from dictionary."""
        targets_data = data.get("targets", {})
        targets = TemplateTarget.from_dict(targets_data)

        return cls(
            entities=data["entities"],
            permission_sets=data["permission_sets"],
            targets=targets,
        )

    def get_entity_count(self) -> int:
        """Get number of entities in this assignment."""
        return len(self.entities)

    def get_permission_set_count(self) -> int:
        """Get number of permission sets in this assignment."""
        return len(self.permission_sets)

    def get_total_assignments(self) -> int:
        """Get total number of assignments this will create."""
        entity_count = self.get_entity_count()
        permission_set_count = self.get_permission_set_count()
        target_count = self.targets.get_account_count_estimate()

        if target_count == -1:
            # Tag-based targets need resolution
            return -1

        return entity_count * permission_set_count * target_count


@dataclass
class Template:
    """Complete template definition."""

    metadata: TemplateMetadata
    assignments: List[TemplateAssignment]

    def __post_init__(self):
        """Validate template configuration."""
        if not self.assignments:
            raise ValueError("At least one assignment must be specified")

    def to_dict(self) -> Dict[str, Any]:
        """Convert template to dictionary."""
        return {
            "metadata": self.metadata.to_dict(),
            "assignments": [assignment.to_dict() for assignment in self.assignments],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Template":
        """Create template from dictionary."""
        metadata_data = data.get("metadata", {})
        metadata = TemplateMetadata.from_dict(metadata_data)

        assignments_data = data.get("assignments", [])
        assignments = [
            TemplateAssignment.from_dict(assignment_data) for assignment_data in assignments_data
        ]

        return cls(metadata=metadata, assignments=assignments)

    def validate_structure(self) -> List[str]:
        """Validate template structure and return list of errors."""
        errors = []

        # Validate metadata
        if not self.metadata.name:
            errors.append("Template name is required")

        # Validate assignments
        for i, assignment in enumerate(self.assignments):
            try:
                assignment.__post_init__()
            except ValueError as e:
                errors.append(f"Assignment {i + 1}: {str(e)}")

        return errors

    def get_total_assignments(self) -> int:
        """Get total number of assignments this template will create."""
        total = 0
        for assignment in self.assignments:
            count = assignment.get_total_assignments()
            if count == -1:
                return -1  # Indeterminate due to tag-based targets
            total += count
        return total

    def get_entity_count(self) -> int:
        """Get total number of unique entities across all assignments."""
        entities = set()
        for assignment in self.assignments:
            entities.update(assignment.entities)
        return len(entities)

    def get_permission_set_count(self) -> int:
        """Get total number of unique permission sets across all assignments."""
        permission_sets = set()
        for assignment in self.assignments:
            permission_sets.update(assignment.permission_sets)
        return len(permission_sets)

    def save_to_file(self, file_path: Path) -> None:
        """Save template to file in YAML format."""
        import yaml

        # Ensure directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to dict and save
        template_dict = self.to_dict()
        with open(file_path, "w") as f:
            yaml.dump(template_dict, f, default_flow_style=False, indent=2, sort_keys=False)

    @classmethod
    def load_from_file(cls, file_path: Path) -> "Template":
        """Load template from file."""
        import yaml

        with open(file_path, "r") as f:
            data = yaml.safe_load(f)

        return cls.from_dict(data)

    @classmethod
    def create_example(cls) -> "Template":
        """Create an example template for demonstration."""
        metadata = TemplateMetadata(
            name="example-developer-template",
            description="Example template for developer access",
            version="1.0",
            author="DevOps Team",
        )

        targets = TemplateTarget(account_tags={"Environment": "development", "Team": "backend"})

        assignment = TemplateAssignment(
            entities=["user:john.doe", "group:developers"],
            permission_sets=["DeveloperAccess", "ReadOnlyAccess"],
            targets=targets,
        )

        return cls(metadata=metadata, assignments=[assignment])
