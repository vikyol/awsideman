"""
Unit tests for the TemplateParser class.

Tests YAML and JSON parsing functionality including format detection,
error handling, and file operations.
"""

from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from src.awsideman.templates.models import Template
from src.awsideman.templates.parser import TemplateParser


class TestTemplateParser:
    """Test cases for TemplateParser class."""

    @pytest.fixture
    def parser(self):
        """Create a TemplateParser instance."""
        return TemplateParser()

    @pytest.fixture
    def sample_yaml_content(self):
        """Sample YAML template content."""
        return """
metadata:
  name: "test-template"
  description: "Test template"
  version: "1.0"
  author: "Test Author"

assignments:
  - entities:
      - "user:john.doe"
      - "group:developers"
    permission_sets:
      - "DeveloperAccess"
      - "ReadOnlyAccess"
    targets:
      account_ids:
        - "123456789012"
        - "234567890123"
"""

    @pytest.fixture
    def sample_json_content(self):
        """Sample JSON template content."""
        return """
{
  "metadata": {
    "name": "test-template",
    "description": "Test template",
    "version": "1.0",
    "author": "Test Author"
  },
  "assignments": [
    {
      "entities": [
        "user:john.doe",
        "group:developers"
      ],
      "permission_sets": [
        "DeveloperAccess",
        "ReadOnlyAccess"
      ],
      "targets": {
        "account_ids": [
          "123456789012",
          "234567890123"
        ]
      }
    }
  ]
}
"""

    def test_init(self, parser):
        """Test parser initialization."""
        assert parser._yaml_available in [True, False]  # Depends on PyYAML availability

    def test_detect_format_yaml(self, parser):
        """Test YAML format detection."""
        yaml_files = [
            Path("template.yaml"),
            Path("template.yml"),
            Path("/path/to/template.yaml"),
            Path("no_extension"),  # Should default to YAML
        ]

        for file_path in yaml_files:
            format_type = parser._detect_format(file_path)
            assert format_type == "yaml"

    def test_detect_format_json(self, parser):
        """Test JSON format detection."""
        json_file = Path("template.json")
        format_type = parser._detect_format(json_file)
        assert format_type == "json"

    def test_parse_yaml_success(self, parser, sample_yaml_content):
        """Test successful YAML parsing."""
        with patch("yaml.safe_load") as mock_yaml_load:
            mock_yaml_load.return_value = {
                "metadata": {"name": "test-template"},
                "assignments": [
                    {
                        "entities": ["user:john.doe"],
                        "permission_sets": ["DeveloperAccess"],
                        "targets": {"account_ids": ["123456789012"]},
                    }
                ],
            }

            template = parser._parse_yaml(sample_yaml_content)

            assert isinstance(template, Template)
            assert template.metadata.name == "test-template"
            mock_yaml_load.assert_called_once()

    def test_parse_yaml_empty_content(self, parser):
        """Test YAML parsing with empty content."""
        with patch("yaml.safe_load") as mock_yaml_load:
            mock_yaml_load.return_value = None

            with pytest.raises(ValueError, match="YAML content is empty or contains only comments"):
                parser._parse_yaml("")

    def test_parse_yaml_invalid_content(self, parser):
        """Test YAML parsing with invalid content."""
        with patch("yaml.safe_load") as mock_yaml_load:
            mock_yaml_load.return_value = "not a dict"

            with pytest.raises(ValueError, match="YAML content must be a dictionary"):
                parser._parse_yaml("invalid content")

    def test_parse_yaml_yaml_error(self, parser):
        """Test YAML parsing with YAML error."""
        with patch("yaml.safe_load") as mock_yaml_load:
            from yaml import YAMLError

            mock_yaml_load.side_effect = YAMLError("Invalid YAML")

            with pytest.raises(ValueError, match="Invalid YAML format"):
                parser._parse_yaml("invalid yaml")

    def test_parse_json_success(self, parser, sample_json_content):
        """Test successful JSON parsing."""
        template = parser._parse_json(sample_json_content)

        assert isinstance(template, Template)
        assert template.metadata.name == "test-template"
        assert len(template.assignments) == 1
        assert template.assignments[0].entities == ["user:john.doe", "group:developers"]

    def test_parse_json_invalid_content(self, parser):
        """Test JSON parsing with invalid content."""
        with pytest.raises(ValueError, match="Invalid JSON format"):
            parser._parse_json("{ invalid json }")

    def test_parse_json_not_dict(self, parser):
        """Test JSON parsing with non-dict content."""
        with pytest.raises(ValueError, match="JSON content must be a dictionary"):
            parser._parse_json('"not a dict"')

    def test_parse_string_yaml(self, parser, sample_yaml_content):
        """Test parsing string content as YAML."""
        with patch.object(parser, "_parse_yaml") as mock_parse_yaml:
            mock_template = MagicMock(spec=Template)
            mock_parse_yaml.return_value = mock_template

            result = parser.parse_string(sample_yaml_content, "yaml")

            assert result == mock_template
            mock_parse_yaml.assert_called_once_with(sample_yaml_content)

    def test_parse_string_json(self, parser, sample_json_content):
        """Test parsing string content as JSON."""
        with patch.object(parser, "_parse_json") as mock_parse_json:
            mock_template = MagicMock(spec=Template)
            mock_parse_json.return_value = mock_template

            result = parser.parse_string(sample_json_content, "json")

            assert result == mock_template
            mock_parse_json.assert_called_once_with(sample_json_content)

    def test_parse_string_unsupported_format(self, parser):
        """Test parsing string with unsupported format."""
        with pytest.raises(ValueError, match="Unsupported format"):
            parser.parse_string("content", "xml")

    def test_parse_string_empty_content(self, parser):
        """Test parsing empty string content."""
        with pytest.raises(ValueError, match="Template content is empty"):
            parser.parse_string("", "yaml")

    def test_parse_file_success(self, parser, sample_yaml_content):
        """Test successful file parsing."""
        file_path = Path("/tmp/test.yaml")

        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("builtins.open", mock_open(read_data=sample_yaml_content)):
                    with patch.object(parser, "_parse_yaml") as mock_parse_yaml:
                        mock_template = MagicMock(spec=Template)
                        mock_parse_yaml.return_value = mock_template

                        result = parser.parse_file(file_path)

                        assert result == mock_template
                        mock_parse_yaml.assert_called_once_with(sample_yaml_content)

    def test_parse_file_not_found(self, parser):
        """Test parsing non-existent file."""
        file_path = Path("/tmp/nonexistent.yaml")

        with pytest.raises(FileNotFoundError, match="Template file not found"):
            parser.parse_file(file_path)

    def test_parse_file_not_a_file(self, parser):
        """Test parsing directory as file."""
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.is_file", return_value=False):
                file_path = Path("/tmp/directory")

                with pytest.raises(ValueError, match="Path is not a file"):
                    parser.parse_file(file_path)

    def test_validate_file_format_success(self, parser):
        """Test successful file format validation."""
        file_path = Path("/tmp/test.yaml")

        with patch.object(parser, "parse_file") as mock_parse_file:
            mock_template = MagicMock(spec=Template)
            mock_template.validate_structure.return_value = []
            mock_parse_file.return_value = mock_template

            errors = parser.validate_file_format(file_path)

            assert len(errors) == 0
            mock_parse_file.assert_called_once_with(file_path)

    def test_validate_file_format_with_errors(self, parser):
        """Test file format validation with errors."""
        file_path = Path("/tmp/test.yaml")

        with patch.object(parser, "parse_file") as mock_parse_file:
            mock_template = MagicMock(spec=Template)
            mock_template.validate_structure.return_value = ["Error 1", "Error 2"]
            mock_parse_file.return_value = mock_template

            errors = parser.validate_file_format(file_path)

            assert len(errors) == 2
            assert "Error 1" in errors
            assert "Error 2" in errors

    def test_validate_file_format_parsing_error(self, parser):
        """Test file format validation with parsing error."""
        file_path = Path("/tmp/test.yaml")

        with patch.object(parser, "parse_file") as mock_parse_file:
            mock_parse_file.side_effect = ValueError("Parsing failed")

            errors = parser.validate_file_format(file_path)

            assert len(errors) == 1
            assert "Parsing error: Parsing failed" in errors[0]

    def test_get_supported_formats(self, parser):
        """Test getting supported formats."""
        formats = parser.get_supported_formats()

        assert "json" in formats
        # YAML availability depends on PyYAML installation
        if parser._yaml_available:
            assert "yaml" in formats

    def test_create_template_file_yaml(self, parser):
        """Test creating template file in YAML format."""
        template = Template.create_example()
        file_path = Path("/tmp/test.yaml")

        with patch.object(template, "save_to_file") as mock_save:
            parser.create_template_file(file_path, template, "yaml")
            mock_save.assert_called_once_with(file_path)

    def test_create_template_file_json(self, parser):
        """Test creating template file in JSON format."""
        template = Template.create_example()
        file_path = Path("/tmp/test.json")

        with patch("builtins.open", mock_open()) as mock_file:
            parser.create_template_file(file_path, template, "json")
            mock_file.assert_called_once()

    def test_create_template_file_unsupported_format(self, parser):
        """Test creating template file with unsupported format."""
        template = Template.create_example()
        file_path = Path("/tmp/test.xml")

        with pytest.raises(ValueError, match="Unsupported format"):
            parser.create_template_file(file_path, template, "xml")

    def test_get_template_preview_success(self, parser):
        """Test getting template preview."""
        file_path = Path("/tmp/test.yaml")
        content = "line 1\nline 2\nline 3\nline 4\nline 5"

        with patch("builtins.open", mock_open(read_data=content)):
            preview = parser.get_template_preview(file_path, max_lines=3)

            assert "line 1" in preview
            assert "line 2" in preview
            assert "line 3" in preview
            assert "line 4" not in preview
            assert "showing first 3 lines" in preview

    def test_get_template_preview_short_file(self, parser):
        """Test getting preview of short file."""
        file_path = Path("/tmp/test.yaml")
        content = "line 1\nline 2"

        with patch("builtins.open", mock_open(read_data=content)):
            preview = parser.get_template_preview(file_path, max_lines=10)

            assert preview == content

    def test_get_template_preview_error(self, parser):
        """Test getting preview with file read error."""
        file_path = Path("/tmp/test.yaml")

        with patch("builtins.open", mock_open()) as mock_file:
            mock_file.side_effect = Exception("Read error")

            preview = parser.get_template_preview(file_path)

            assert "Error reading file: Read error" in preview
