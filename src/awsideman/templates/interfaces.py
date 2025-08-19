"""
Core interfaces and base classes for template operations.

This module defines the abstract interfaces and base classes that all template
components must implement, ensuring consistent behavior across the template system.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Optional, Protocol

from ..permission_cloning.models import EntityReference

if TYPE_CHECKING:
    from .executor import ExecutionResult, PreviewResult
    from .models import Template, TemplateInfo
    from .validator import ValidationResult


class TemplateParserInterface(ABC):
    """Abstract interface for template parsers."""

    @abstractmethod
    def parse_file(self, file_path: Path) -> "Template":
        """Parse template from file."""
        pass

    @abstractmethod
    def parse_string(self, content: str, format: str) -> "Template":
        """Parse template from string content."""
        pass


class TemplateValidatorInterface(ABC):
    """Abstract interface for template validators."""

    @abstractmethod
    def validate_template(self, template: "Template") -> "ValidationResult":
        """Comprehensive template validation."""
        pass

    @abstractmethod
    def validate_structure(self, template: "Template") -> List[str]:
        """Validate template structure and required fields."""
        pass

    @abstractmethod
    def validate_entities(self, template: "Template") -> List[str]:
        """Validate that all entities exist and are resolvable."""
        pass

    @abstractmethod
    def validate_permission_sets(self, template: "Template") -> List[str]:
        """Validate that all permission sets exist."""
        pass

    @abstractmethod
    def validate_accounts(self, template: "Template") -> List[str]:
        """Validate account IDs and tag filters."""
        pass


class TemplateStorageInterface(ABC):
    """Abstract interface for template storage operations."""

    @abstractmethod
    def list_templates(self) -> List["TemplateInfo"]:
        """List all available templates."""
        pass

    @abstractmethod
    def get_template(self, name: str) -> Optional["Template"]:
        """Load template by name."""
        pass

    @abstractmethod
    def save_template(self, template: "Template", file_path: Optional[Path] = None) -> Path:
        """Save template to storage."""
        pass

    @abstractmethod
    def delete_template(self, name: str) -> bool:
        """Delete template from storage."""
        pass

    @abstractmethod
    def template_exists(self, name: str) -> bool:
        """Check if template exists."""
        pass


class TemplateExecutorInterface(ABC):
    """Abstract interface for template execution operations."""

    @abstractmethod
    def apply_template(self, template: "Template", dry_run: bool = False) -> "ExecutionResult":
        """Apply template assignments."""
        pass

    @abstractmethod
    def preview_template(self, template: "Template") -> "PreviewResult":
        """Generate preview of template execution."""
        pass


class EntityResolverProtocol(Protocol):
    """Protocol for entity resolution operations."""

    def resolve_entity_by_name(
        self, entity_type: str, entity_name: str
    ) -> Optional[EntityReference]:
        """Resolve entity by name."""
        pass

    def validate_entity(self, entity: EntityReference) -> Any:
        """Validate entity exists."""
        pass


class AWSClientManagerProtocol(Protocol):
    """Protocol for AWS client management operations."""

    def get_identity_center_client(self):
        """Get Identity Center client."""
        pass

    def get_identity_store_client(self):
        """Get Identity Store client."""
        pass

    def get_organizations_client(self):
        """Get Organizations client."""
        pass


class AssignmentCopierProtocol(Protocol):
    """Protocol for assignment copying operations."""

    def copy_assignments(
        self,
        source: EntityReference,
        target: EntityReference,
        filters: Optional[Any] = None,
        preview: bool = False,
        progress_callback: Optional[Any] = None,
    ) -> Any:
        """Copy assignments between entities."""
        pass


class ConfigProtocol(Protocol):
    """Protocol for configuration operations."""

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        pass

    def set(self, key: str, value: Any) -> None:
        """Set configuration value."""
        pass
