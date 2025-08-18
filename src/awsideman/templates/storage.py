"""
Template storage manager for AWS Identity Center templates.

This module handles template file storage, discovery, and management operations
including listing, loading, saving, and deleting templates.
"""

import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .interfaces import ConfigProtocol, TemplateStorageInterface
from .models import Template, TemplateMetadata
from .parser import TemplateParser

logger = logging.getLogger(__name__)


@dataclass
class TemplateInfo:
    """Basic template information for listing."""

    name: str
    file_path: Path
    metadata: TemplateMetadata
    assignment_count: int
    entity_count: int
    permission_set_count: int
    last_modified: datetime

    def __post_init__(self):
        """Set last_modified if not provided."""
        if not hasattr(self, "last_modified"):
            self.last_modified = datetime.now()


class TemplateStorageManager(TemplateStorageInterface):
    """Manages template file storage and discovery."""

    def __init__(self, config: Optional[ConfigProtocol] = None):
        """Initialize the template storage manager."""
        self.config = config
        self.templates_dir = self._get_templates_directory()
        self.parser = TemplateParser()

        # Ensure templates directory exists
        self._ensure_templates_directory()

    def list_templates(self) -> List[TemplateInfo]:
        """List all available templates."""
        templates = []

        if not self.templates_dir.exists():
            return templates

        # Find all template files
        template_files = []
        for pattern in ["*.yaml", "*.yml", "*.json"]:
            template_files.extend(self.templates_dir.glob(pattern))

        for file_path in template_files:
            try:
                template_info = self._get_template_info(file_path)
                if template_info:
                    templates.append(template_info)
            except Exception as e:
                logger.warning(f"Failed to read template info from {file_path}: {e}")
                continue

        # Sort by name
        templates.sort(key=lambda t: t.name.lower())
        return templates

    def get_template(self, name: str) -> Optional[Template]:
        """Load template by name."""
        # First try exact name match
        template_path = self._find_template_by_name(name)
        if template_path:
            return self._load_template_from_path(template_path)

        # Try partial name match
        template_path = self._find_template_by_partial_name(name)
        if template_path:
            return self._load_template_from_path(template_path)

        return None

    def save_template(self, template: Template, file_path: Optional[Path] = None) -> Path:
        """Save template to storage."""
        if file_path is None:
            # Generate default filename
            filename = f"{template.metadata.name}.yaml"
            file_path = self.templates_dir / filename

        # Ensure directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Save template
            template.save_to_file(file_path)
            logger.info(f"Template saved to {file_path}")
            return file_path
        except Exception as e:
            logger.error(f"Failed to save template: {e}")
            raise

    def delete_template(self, name: str) -> bool:
        """Delete template from storage."""
        template_path = self._find_template_by_name(name)
        if not template_path:
            return False

        try:
            template_path.unlink()
            logger.info(f"Template deleted: {template_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete template {name}: {e}")
            return False

    def template_exists(self, name: str) -> bool:
        """Check if template exists."""
        return self._find_template_by_name(name) is not None

    def get_template_path(self, name: str) -> Optional[Path]:
        """Get the file path for a template by name."""
        return self._find_template_by_name(name)

    def copy_template(self, source_name: str, target_name: str) -> bool:
        """Copy a template with a new name."""
        source_path = self._find_template_by_name(source_name)
        if not source_path:
            return False

        try:
            # Load source template
            source_template = self._load_template_from_path(source_path)
            if not source_template:
                return False

            # Update metadata
            source_template.metadata.name = target_name
            source_template.metadata.updated_at = datetime.now()

            # Save as new template
            target_filename = f"{target_name}.yaml"
            target_path = self.templates_dir / target_filename

            source_template.save_to_file(target_path)
            logger.info(f"Template copied from {source_name} to {target_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to copy template {source_name}: {e}")
            return False

    def backup_template(self, name: str) -> Optional[Path]:
        """Create a backup of a template."""
        template_path = self._find_template_by_name(name)
        if not template_path:
            return None

        try:
            # Create backup filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"{template_path.stem}_{timestamp}{template_path.suffix}"
            backup_path = self.templates_dir / backup_filename

            # Copy file
            shutil.copy2(template_path, backup_path)
            logger.info(f"Template backup created: {backup_path}")
            return backup_path

        except Exception as e:
            logger.error(f"Failed to create backup for template {name}: {e}")
            return None

    def get_templates_by_tag(self, tag_key: str, tag_value: str) -> List[TemplateInfo]:
        """Find templates that have specific metadata tags."""
        templates = []

        for template_info in self.list_templates():
            # Check if template has the specified tag
            if hasattr(template_info.metadata, "tags"):
                template_tags = getattr(template_info.metadata, "tags", {})
                if template_tags.get(tag_key) == tag_value:
                    templates.append(template_info)

        return templates

    def _get_templates_directory(self) -> Path:
        """Get templates directory from config or default."""
        if self.config:
            # Try to get from config
            config_dir = self.config.get("templates.storage_directory")
            if config_dir:
                return Path(config_dir).expanduser()

        # Default to ~/.awsideman/templates
        default_dir = Path.home() / ".awsideman" / "templates"
        return default_dir

    def _ensure_templates_directory(self) -> None:
        """Ensure the templates directory exists."""
        if not self.templates_dir.exists():
            self.templates_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created templates directory: {self.templates_dir}")

    def _find_template_by_name(self, name: str) -> Optional[Path]:
        """Find template file by exact name match."""
        # Try different extensions
        for ext in [".yaml", ".yml", ".json"]:
            file_path = self.templates_dir / f"{name}{ext}"
            if file_path.exists():
                return file_path

        return None

    def _find_template_by_partial_name(self, partial_name: str) -> Optional[Path]:
        """Find template file by partial name match."""
        partial_name_lower = partial_name.lower()

        for template_info in self.list_templates():
            if partial_name_lower in template_info.name.lower():
                return template_info.file_path

        return None

    def _load_template_from_path(self, file_path: Path) -> Optional[Template]:
        """Load template from file path."""
        try:
            return self.parser.parse_file(file_path)
        except Exception as e:
            logger.error(f"Failed to load template from {file_path}: {e}")
            return None

    def _get_template_info(self, file_path: Path) -> Optional[TemplateInfo]:
        """Get template information from file."""
        try:
            # Load template
            template = self.parser.parse_file(file_path)
            if not template:
                return None

            # Get file stats
            stat = file_path.stat()
            last_modified = datetime.fromtimestamp(stat.st_mtime)

            return TemplateInfo(
                name=template.metadata.name,
                file_path=file_path,
                metadata=template.metadata,
                assignment_count=len(template.assignments),
                entity_count=template.get_entity_count(),
                permission_set_count=template.get_permission_set_count(),
                last_modified=last_modified,
            )

        except Exception as e:
            logger.warning(f"Failed to get template info from {file_path}: {e}")
            return None

    def get_storage_stats(self) -> dict:
        """Get storage statistics."""
        templates = self.list_templates()

        total_templates = len(templates)
        total_entities = sum(t.entity_count for t in templates)
        total_permission_sets = sum(t.permission_set_count for t in templates)

        # Calculate total size
        total_size = 0
        for template in templates:
            if template.file_path.exists():
                total_size += template.file_path.stat().st_size

        # Calculate total assignments more accurately
        total_actual_assignments = 0
        has_tag_based = False

        for template_info in templates:
            try:
                # Load the actual template to get accurate assignment count
                template = self._load_template_from_path(template_info.file_path)
                if template:
                    count = template.get_total_assignments()
                    if count >= 0:
                        total_actual_assignments += count
                    else:
                        has_tag_based = True
            except Exception:
                # If we can't load the template, skip it
                continue

        # Format the total assignments display
        if has_tag_based:
            total_assignments_display = f"{total_actual_assignments}+ (some tag-based)"
        else:
            total_assignments_display = str(total_actual_assignments)

        return {
            "total_templates": total_templates,
            "total_assignments": total_assignments_display,
            "total_entities": total_entities,
            "total_permission_sets": total_permission_sets,
            "total_size_bytes": total_size,
            "storage_directory": str(self.templates_dir),
        }
