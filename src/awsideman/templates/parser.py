"""
Template parser for YAML and JSON formats.

This module handles parsing of template files in various formats,
with automatic format detection and comprehensive error handling.
"""

import json
import logging
from pathlib import Path
from typing import List

from .interfaces import TemplateParserInterface
from .models import Template

logger = logging.getLogger(__name__)


class TemplateParser(TemplateParserInterface):
    """Handles parsing of template files in YAML/JSON formats."""

    def __init__(self):
        """Initialize the template parser."""
        self._yaml_available = self._check_yaml_availability()

    def parse_file(self, file_path: Path) -> Template:
        """Parse template from file."""
        if not file_path.exists():
            raise FileNotFoundError(f"Template file not found: {file_path}")

        if not file_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        # Read file content
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError as e:
            raise ValueError(f"Failed to read template file: {e}")

        # Detect format and parse
        format_type = self._detect_format(file_path)
        return self.parse_string(content, format_type)

    def parse_string(self, content: str, format: str) -> Template:
        """Parse template from string content."""
        if not content.strip():
            raise ValueError("Template content is empty")

        try:
            if format.lower() == "yaml":
                return self._parse_yaml(content)
            elif format.lower() == "json":
                return self._parse_json(content)
            else:
                raise ValueError(f"Unsupported format: {format}")
        except Exception as e:
            logger.error(f"Failed to parse template content: {e}")
            raise ValueError(f"Failed to parse template: {e}")

    def _detect_format(self, file_path: Path) -> str:
        """Auto-detect file format from extension."""
        suffix = file_path.suffix.lower()

        if suffix in [".yaml", ".yml"]:
            return "yaml"
        elif suffix == ".json":
            return "json"
        else:
            # Default to YAML if no extension or unknown extension
            logger.warning(f"Unknown file extension '{suffix}', defaulting to YAML format")
            return "yaml"

    def _parse_yaml(self, content: str) -> Template:
        """Parse YAML content."""
        if not self._yaml_available:
            raise ImportError(
                "PyYAML is required for YAML parsing. Install with: pip install PyYAML"
            )

        try:
            import yaml

            data = yaml.safe_load(content)

            if data is None:
                raise ValueError("YAML content is empty or contains only comments")

            if not isinstance(data, dict):
                raise ValueError("YAML content must be a dictionary")

            return Template.from_dict(data)

        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML format: {e}")
        except Exception as e:
            raise ValueError(f"Failed to parse YAML content: {e}")

    def _parse_json(self, content: str) -> Template:
        """Parse JSON content."""
        try:
            data = json.loads(content)

            if not isinstance(data, dict):
                raise ValueError("JSON content must be a dictionary")

            return Template.from_dict(data)

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format: {e}")
        except Exception as e:
            raise ValueError(f"Failed to parse JSON content: {e}")

    def _check_yaml_availability(self) -> bool:
        """Check if PyYAML is available."""
        try:
            import yaml  # noqa: F401

            return True
        except ImportError:
            logger.warning("PyYAML not available. YAML parsing will not work.")
            return False

    def validate_file_format(self, file_path: Path) -> List[str]:
        """Validate that a file can be parsed as a template."""
        errors = []

        try:
            # Try to parse the file
            template = self.parse_file(file_path)

            # Validate template structure
            structure_errors = template.validate_structure()
            errors.extend(structure_errors)

        except Exception as e:
            errors.append(f"Parsing error: {str(e)}")

        return errors

    def get_supported_formats(self) -> List[str]:
        """Get list of supported file formats."""
        formats = ["json"]
        if self._yaml_available:
            formats.append("yaml")
        return formats

    def create_template_file(
        self, file_path: Path, template: Template, format: str = "yaml"
    ) -> None:
        """Create a template file with the given content."""
        if format.lower() == "yaml":
            template.save_to_file(file_path)
        elif format.lower() == "json":
            # Save as JSON
            template_dict = template.to_dict()
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(template_dict, f, indent=2, ensure_ascii=False)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def get_template_preview(self, file_path: Path, max_lines: int = 20) -> str:
        """Get a preview of the template file content."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            if len(lines) <= max_lines:
                return "".join(lines)
            else:
                preview_lines = lines[:max_lines]
                preview_lines.append(
                    f"\n... (showing first {max_lines} lines, file has {len(lines)} total lines)"
                )
                return "".join(preview_lines)

        except Exception as e:
            return f"Error reading file: {e}"
