"""
Unit tests for the TemplateStorageManager class.

Tests template file storage, discovery, and management operations
including listing, loading, saving, and deleting templates.
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.awsideman.templates.models import (
    Template,
    TemplateAssignment,
    TemplateMetadata,
    TemplateTarget,
)
from src.awsideman.templates.storage import TemplateInfo, TemplateStorageManager


class TestTemplateStorageManager:
    """Test cases for TemplateStorageManager class."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock configuration object."""
        config = MagicMock()
        config.get.return_value = None  # Default to None for storage directory
        return config

    @pytest.fixture
    def storage_manager(self, mock_config):
        """Create a TemplateStorageManager instance with mocked config."""
        with patch("pathlib.Path.home", return_value=Path("/home/testuser")):
            with patch("pathlib.Path.mkdir"):
                manager = TemplateStorageManager(config=mock_config)
                # Mock the templates directory to avoid actual file system operations
                manager.templates_dir = Path("/tmp/test-templates")
                return manager

    @pytest.fixture
    def sample_template(self):
        """Create a sample template for testing."""
        metadata = TemplateMetadata(
            name="test-template", description="Test template", version="1.0", author="Test Author"
        )
        targets = TemplateTarget(account_ids=["123456789012"])
        assignment = TemplateAssignment(
            entities=["user:john.doe"], permission_sets=["DeveloperAccess"], targets=targets
        )
        return Template(metadata=metadata, assignments=[assignment])

    @pytest.fixture
    def sample_template_info(self):
        """Create a sample TemplateInfo object."""
        metadata = TemplateMetadata(name="test-template")
        return TemplateInfo(
            name="test-template",
            file_path=Path("/tmp/test-templates/test-template.yaml"),
            metadata=metadata,
            assignment_count=1,
            entity_count=1,
            permission_set_count=1,
            last_modified=datetime.now(),
        )

    def test_init_with_config(self, mock_config):
        """Test initialization with configuration."""
        with patch("pathlib.Path.home", return_value=Path("/home/testuser")):
            with patch("pathlib.Path.mkdir"):
                manager = TemplateStorageManager(config=mock_config)
                assert manager.config == mock_config

    def test_init_without_config(self):
        """Test initialization without configuration."""
        with patch("pathlib.Path.home", return_value=Path("/home/testuser")):
            with patch("pathlib.Path.mkdir"):
                manager = TemplateStorageManager()
                assert manager.config is None

    def test_get_templates_directory_from_config(self, mock_config):
        """Test getting templates directory from config."""
        mock_config.get.return_value = "~/.custom/templates"

        with patch("pathlib.Path.home", return_value=Path("/home/testuser")):
            with patch("pathlib.Path.mkdir"):
                manager = TemplateStorageManager(config=mock_config)
                # Mock the templates directory
                manager.templates_dir = Path("/home/testuser/.custom/templates")
                assert str(manager.templates_dir) == "/home/testuser/.custom/templates"

    def test_get_templates_directory_default(self, mock_config):
        """Test getting default templates directory."""
        mock_config.get.return_value = None

        with patch("pathlib.Path.home", return_value=Path("/home/testuser")):
            with patch("pathlib.Path.mkdir"):
                manager = TemplateStorageManager(config=mock_config)
                # Mock the templates directory
                manager.templates_dir = Path("/home/testuser/.awsideman/templates")
                assert str(manager.templates_dir) == "/home/testuser/.awsideman/templates"

    def test_ensure_templates_directory(self, storage_manager):
        """Test ensuring templates directory exists."""
        with patch("pathlib.Path.exists", return_value=False):
            with patch("pathlib.Path.mkdir") as mock_mkdir:
                storage_manager._ensure_templates_directory()
                mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

    def test_list_templates_empty_directory(self, storage_manager):
        """Test listing templates from empty directory."""
        with patch("pathlib.Path.exists", return_value=False):
            templates = storage_manager.list_templates()
            assert len(templates) == 0

    def test_list_templates_with_files(self, storage_manager):
        """Test listing templates with existing files."""
        # Mock template files
        mock_files = [
            Path("/tmp/test-templates/template1.yaml"),
            Path("/tmp/test-templates/template2.json"),
            Path("/tmp/test-templates/template3.yml"),
        ]

        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.glob") as mock_glob:
                mock_glob.side_effect = [
                    [mock_files[0]],  # *.yaml
                    [mock_files[1]],  # *.yml
                    [mock_files[2]],  # *.json
                ]

                with patch.object(storage_manager, "_get_template_info") as mock_get_info:
                    # Create proper mock objects with name attribute
                    mock_info1 = MagicMock()
                    mock_info1.name = "template1"
                    mock_info2 = MagicMock()
                    mock_info2.name = "template2"
                    mock_info3 = MagicMock()
                    mock_info3.name = "template3"

                    mock_get_info.side_effect = [mock_info1, mock_info2, mock_info3]

                    templates = storage_manager.list_templates()
                    assert len(templates) == 3

    def test_get_template_by_exact_name(self, storage_manager):
        """Test getting template by exact name."""
        template_path = Path("/tmp/test-templates/test-template.yaml")

        with patch.object(storage_manager, "_find_template_by_name", return_value=template_path):
            with patch.object(storage_manager, "_load_template_from_path") as mock_load:
                mock_template = MagicMock(spec=Template)
                mock_load.return_value = mock_template

                result = storage_manager.get_template("test-template")
                assert result == mock_template

    def test_get_template_by_partial_name(self, storage_manager):
        """Test getting template by partial name."""
        template_path = Path("/tmp/test-templates/test-template.yaml")

        with patch.object(storage_manager, "_find_template_by_name", return_value=None):
            with patch.object(
                storage_manager, "_find_template_by_partial_name", return_value=template_path
            ):
                with patch.object(storage_manager, "_load_template_from_path") as mock_load:
                    mock_template = MagicMock(spec=Template)
                    mock_load.return_value = mock_template

                    result = storage_manager.get_template("test")
                    assert result == mock_template

    def test_get_template_not_found(self, storage_manager):
        """Test getting template that doesn't exist."""
        with patch.object(storage_manager, "_find_template_by_name", return_value=None):
            with patch.object(storage_manager, "_find_template_by_partial_name", return_value=None):
                result = storage_manager.get_template("nonexistent")
                assert result is None

    def test_save_template_with_default_path(self, storage_manager, sample_template):
        """Test saving template with default path."""
        with patch.object(sample_template, "save_to_file") as mock_save:
            with patch("pathlib.Path.mkdir"):
                result_path = storage_manager.save_template(sample_template)

                expected_path = Path("/tmp/test-templates/test-template.yaml")
                assert result_path == expected_path
                mock_save.assert_called_once_with(expected_path)

    def test_save_template_with_custom_path(self, storage_manager, sample_template):
        """Test saving template with custom path."""
        custom_path = Path("/tmp/custom/path/template.yaml")

        with patch.object(sample_template, "save_to_file") as mock_save:
            with patch("pathlib.Path.mkdir"):
                result_path = storage_manager.save_template(sample_template, custom_path)

                assert result_path == custom_path
                mock_save.assert_called_once_with(custom_path)

    def test_save_template_error(self, storage_manager, sample_template):
        """Test saving template with error."""
        with patch.object(sample_template, "save_to_file", side_effect=Exception("Save failed")):
            with pytest.raises(Exception, match="Save failed"):
                storage_manager.save_template(sample_template)

    def test_delete_template_success(self, storage_manager):
        """Test successful template deletion."""
        template_path = Path("/tmp/test-templates/test-template.yaml")

        with patch.object(storage_manager, "_find_template_by_name", return_value=template_path):
            with patch("pathlib.Path.unlink") as mock_unlink:
                result = storage_manager.delete_template("test-template")

                assert result is True
                # The unlink method is called on the Path object, not with the path as argument
                mock_unlink.assert_called_once()

    def test_delete_template_not_found(self, storage_manager):
        """Test deleting template that doesn't exist."""
        with patch.object(storage_manager, "_find_template_by_name", return_value=None):
            result = storage_manager.delete_template("nonexistent")
            assert result is False

    def test_delete_template_error(self, storage_manager):
        """Test deleting template with error."""
        template_path = Path("/tmp/test-templates/test-template.yaml")

        with patch.object(storage_manager, "_find_template_by_name", return_value=template_path):
            with patch("pathlib.Path.unlink", side_effect=Exception("Delete failed")):
                result = storage_manager.delete_template("test-template")
                assert result is False

    def test_template_exists_true(self, storage_manager):
        """Test checking if template exists."""
        template_path = Path("/tmp/test-templates/test-template.yaml")

        with patch.object(storage_manager, "_find_template_by_name", return_value=template_path):
            result = storage_manager.template_exists("test-template")
            assert result is True

    def test_template_exists_false(self, storage_manager):
        """Test checking if template doesn't exist."""
        with patch.object(storage_manager, "_find_template_by_name", return_value=None):
            result = storage_manager.template_exists("nonexistent")
            assert result is False

    def test_get_template_path(self, storage_manager):
        """Test getting template file path."""
        template_path = Path("/tmp/test-templates/test-template.yaml")

        with patch.object(storage_manager, "_find_template_by_name", return_value=template_path):
            result = storage_manager.get_template_path("test-template")
            assert result == template_path

    def test_copy_template_success(self, storage_manager):
        """Test successful template copying."""
        source_path = Path("/tmp/test-templates/source-template.yaml")

        with patch.object(storage_manager, "_find_template_by_name", return_value=source_path):
            with patch.object(storage_manager, "_load_template_from_path") as mock_load:
                # Create a proper mock template with metadata
                mock_template = MagicMock()
                mock_metadata = MagicMock()
                mock_metadata.name = "source-template"
                mock_template.metadata = mock_metadata
                mock_load.return_value = mock_template

                with patch.object(mock_template, "save_to_file"):
                    result = storage_manager.copy_template("source-template", "target-template")
                    assert result is True

    def test_copy_template_source_not_found(self, storage_manager):
        """Test copying template that doesn't exist."""
        with patch.object(storage_manager, "_find_template_by_name", return_value=None):
            result = storage_manager.copy_template("source", "target")
            assert result is False

    def test_backup_template_success(self, storage_manager):
        """Test successful template backup."""
        template_path = Path("/tmp/test-templates/test-template.yaml")

        with patch.object(storage_manager, "_find_template_by_name", return_value=template_path):
            with patch("shutil.copy2") as mock_copy:
                mock_copy.return_value = None

                result = storage_manager.backup_template("test-template")

                assert result is not None
                mock_copy.assert_called_once()

    def test_backup_template_not_found(self, storage_manager):
        """Test backing up template that doesn't exist."""
        with patch.object(storage_manager, "_find_template_by_name", return_value=None):
            result = storage_manager.backup_template("nonexistent")
            assert result is None

    def test_get_templates_by_tag(self, storage_manager):
        """Test finding templates by tag."""
        mock_template_info = MagicMock()
        mock_metadata = MagicMock()
        mock_metadata.tags = {"Environment": "production"}
        mock_template_info.metadata = mock_metadata

        with patch.object(storage_manager, "list_templates", return_value=[mock_template_info]):
            result = storage_manager.get_templates_by_tag("Environment", "production")
            assert len(result) == 1

    def test_find_template_by_name(self, storage_manager):
        """Test finding template by exact name."""
        json_path = Path("/tmp/test-templates/test-template.json")

        with patch("pathlib.Path.exists") as mock_exists:
            mock_exists.side_effect = [False, False, True]  # Only JSON exists

            result = storage_manager._find_template_by_name("test-template")
            assert result == json_path

    def test_find_template_by_partial_name(self, storage_manager):
        """Test finding template by partial name."""
        mock_template_info = MagicMock(spec=TemplateInfo)
        mock_template_info.name = "test-template"
        mock_template_info.file_path = Path("/tmp/test-templates/test-template.yaml")

        with patch.object(storage_manager, "list_templates", return_value=[mock_template_info]):
            result = storage_manager._find_template_by_partial_name("test")
            assert result == mock_template_info.file_path

    def test_load_template_from_path(self, storage_manager):
        """Test loading template from file path."""
        file_path = Path("/tmp/test-templates/test-template.yaml")

        with patch.object(storage_manager.parser, "parse_file") as mock_parse:
            mock_template = MagicMock(spec=Template)
            mock_parse.return_value = mock_template

            result = storage_manager._load_template_from_path(file_path)
            assert result == mock_template

    def test_get_template_info(self, storage_manager):
        """Test getting template information from file."""
        file_path = Path("/tmp/test-templates/test-template.yaml")

        with patch.object(storage_manager.parser, "parse_file") as mock_parse:
            # Create a proper mock template with all required attributes
            mock_template = MagicMock()
            mock_metadata = MagicMock()
            mock_metadata.name = "test-template"
            mock_template.metadata = mock_metadata
            mock_template.assignments = [MagicMock()]
            mock_template.get_entity_count.return_value = 1
            mock_template.get_permission_set_count.return_value = 1
            mock_parse.return_value = mock_template

            with patch("pathlib.Path.stat") as mock_stat:
                mock_stat.return_value.st_mtime = 1234567890

                result = storage_manager._get_template_info(file_path)

                assert result is not None
                assert result.name == "test-template"
                assert result.assignment_count == 1

    def test_get_storage_stats(self, storage_manager):
        """Test getting storage statistics."""
        mock_template_info = MagicMock(spec=TemplateInfo)
        mock_template_info.assignment_count = 2
        mock_template_info.entity_count = 3
        mock_template_info.permission_set_count = 4
        mock_template_info.file_path = Path("/tmp/test.yaml")

        # Mock the template loading to return a proper template
        mock_template = MagicMock()
        mock_template.get_total_assignments.return_value = 2

        with patch.object(storage_manager, "list_templates", return_value=[mock_template_info]):
            with patch.object(
                storage_manager, "_load_template_from_path", return_value=mock_template
            ):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.stat") as mock_stat:
                        mock_stat.return_value.st_size = 1024

                        stats = storage_manager.get_storage_stats()

                        assert stats["total_templates"] == 1
                        assert stats["total_assignments"] == "2"
                        assert stats["total_entities"] == 3
                        assert stats["total_permission_sets"] == 4
                        assert stats["total_size_bytes"] == 1024
                        assert stats["storage_directory"] == "/tmp/test-templates"
