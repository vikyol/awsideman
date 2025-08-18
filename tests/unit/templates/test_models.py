"""
Unit tests for template data models.

Tests the Template, TemplateMetadata, TemplateTarget, and TemplateAssignment classes
including validation, serialization, and utility methods.
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

from src.awsideman.templates.models import (
    Template,
    TemplateAssignment,
    TemplateMetadata,
    TemplateTarget,
)


class TestTemplateMetadata:
    """Test cases for TemplateMetadata class."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        metadata = TemplateMetadata(name="test-template")

        assert metadata.name == "test-template"
        assert metadata.description is None
        assert metadata.version is None
        assert metadata.author is None
        assert metadata.created_at is not None
        assert metadata.updated_at is not None
        assert isinstance(metadata.created_at, datetime)
        assert isinstance(metadata.updated_at, datetime)

    def test_init_with_all_values(self):
        """Test initialization with all values provided."""
        created_at = datetime(2023, 1, 1, 12, 0, 0)
        updated_at = datetime(2023, 1, 2, 12, 0, 0)

        metadata = TemplateMetadata(
            name="test-template",
            description="Test description",
            version="1.0.0",
            author="Test Author",
            created_at=created_at,
            updated_at=updated_at,
        )

        assert metadata.name == "test-template"
        assert metadata.description == "Test description"
        assert metadata.version == "1.0.0"
        assert metadata.author == "Test Author"
        assert metadata.created_at == created_at
        assert metadata.updated_at == updated_at

    def test_to_dict(self):
        """Test conversion to dictionary."""
        created_at = datetime(2023, 1, 1, 12, 0, 0)
        updated_at = datetime(2023, 1, 2, 12, 0, 0)

        metadata = TemplateMetadata(
            name="test-template",
            description="Test description",
            version="1.0.0",
            author="Test Author",
            created_at=created_at,
            updated_at=updated_at,
        )

        data = metadata.to_dict()

        assert data["name"] == "test-template"
        assert data["description"] == "Test description"
        assert data["version"] == "1.0.0"
        assert data["author"] == "Test Author"
        assert data["created_at"] == "2023-01-01T12:00:00"
        assert data["updated_at"] == "2023-01-02T12:00:00"

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "name": "test-template",
            "description": "Test description",
            "version": "1.0.0",
            "author": "Test Author",
            "created_at": "2023-01-01T12:00:00",
            "updated_at": "2023-01-02T12:00:00",
        }

        metadata = TemplateMetadata.from_dict(data)

        assert metadata.name == "test-template"
        assert metadata.description == "Test description"
        assert metadata.version == "1.0.0"
        assert metadata.author == "Test Author"
        assert metadata.created_at == datetime(2023, 1, 1, 12, 0, 0)
        assert metadata.updated_at == datetime(2023, 1, 2, 12, 0, 0)

    def test_from_dict_with_invalid_dates(self):
        """Test creation from dictionary with invalid dates."""
        data = {"name": "test-template", "created_at": "invalid-date", "updated_at": "also-invalid"}

        metadata = TemplateMetadata.from_dict(data)

        assert metadata.name == "test-template"
        assert metadata.created_at is not None  # Should use current time
        assert metadata.updated_at is not None  # Should use current time


class TestTemplateTarget:
    """Test cases for TemplateTarget class."""

    def test_init_with_account_ids(self):
        """Test initialization with account IDs."""
        target = TemplateTarget(account_ids=["123456789012", "234567890123"])

        assert target.account_ids == ["123456789012", "234567890123"]
        assert target.account_tags is None
        assert target.exclude_accounts is None

    def test_init_with_account_tags(self):
        """Test initialization with account tags."""
        target = TemplateTarget(account_tags={"Environment": "production", "Team": "backend"})

        assert target.account_tags == {"Environment": "production", "Team": "backend"}
        assert target.account_ids is None
        assert target.exclude_accounts is None

    def test_init_with_exclude_accounts(self):
        """Test initialization with exclude accounts."""
        target = TemplateTarget(account_ids=["123456789012"], exclude_accounts=["234567890123"])

        assert target.account_ids == ["123456789012"]
        assert target.exclude_accounts == ["234567890123"]

    def test_init_with_both_account_ids_and_tags_raises_error(self):
        """Test that providing both account_ids and account_tags raises an error."""
        with pytest.raises(ValueError, match="Cannot specify both account_ids and account_tags"):
            TemplateTarget(account_ids=["123456789012"], account_tags={"Environment": "production"})

    def test_init_with_neither_account_ids_nor_tags_raises_error(self):
        """Test that providing neither account_ids nor account_tags raises an error."""
        with pytest.raises(
            ValueError, match="Either account_ids or account_tags must be specified"
        ):
            TemplateTarget()

    def test_to_dict(self):
        """Test conversion to dictionary."""
        target = TemplateTarget(account_ids=["123456789012"], exclude_accounts=["234567890123"])

        data = target.to_dict()

        assert data["account_ids"] == ["123456789012"]
        assert data["exclude_accounts"] == ["234567890123"]

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {"account_ids": ["123456789012"], "exclude_accounts": ["234567890123"]}

        target = TemplateTarget.from_dict(data)

        assert target.account_ids == ["123456789012"]
        assert target.exclude_accounts == ["234567890123"]

    def test_get_account_count_estimate_with_ids(self):
        """Test account count estimation with account IDs."""
        target = TemplateTarget(account_ids=["123456789012", "234567890123"])
        assert target.get_account_count_estimate() == 2

    def test_get_account_count_estimate_with_tags(self):
        """Test account count estimation with account tags."""
        target = TemplateTarget(account_tags={"Environment": "production"})
        assert target.get_account_count_estimate() == -1  # Indeterminate


class TestTemplateAssignment:
    """Test cases for TemplateAssignment class."""

    def test_init_valid(self):
        """Test valid initialization."""
        targets = TemplateTarget(account_ids=["123456789012"])
        assignment = TemplateAssignment(
            entities=["user:john.doe", "group:developers"],
            permission_sets=["DeveloperAccess", "ReadOnlyAccess"],
            targets=targets,
        )

        assert assignment.entities == ["user:john.doe", "group:developers"]
        assert assignment.permission_sets == ["DeveloperAccess", "ReadOnlyAccess"]
        assert assignment.targets == targets

    def test_init_without_entities_raises_error(self):
        """Test that initialization without entities raises an error."""
        targets = TemplateTarget(account_ids=["123456789012"])

        with pytest.raises(ValueError, match="At least one entity must be specified"):
            TemplateAssignment(entities=[], permission_sets=["DeveloperAccess"], targets=targets)

    def test_init_without_permission_sets_raises_error(self):
        """Test that initialization without permission sets raises an error."""
        targets = TemplateTarget(account_ids=["123456789012"])

        with pytest.raises(ValueError, match="At least one permission set must be specified"):
            TemplateAssignment(entities=["user:john.doe"], permission_sets=[], targets=targets)

    def test_init_without_targets_raises_error(self):
        """Test that initialization without targets raises an error."""
        with pytest.raises(ValueError, match="Targets must be specified"):
            TemplateAssignment(
                entities=["user:john.doe"], permission_sets=["DeveloperAccess"], targets=None
            )

    def test_to_dict(self):
        """Test conversion to dictionary."""
        targets = TemplateTarget(account_ids=["123456789012"])
        assignment = TemplateAssignment(
            entities=["user:john.doe"], permission_sets=["DeveloperAccess"], targets=targets
        )

        data = assignment.to_dict()

        assert data["entities"] == ["user:john.doe"]
        assert data["permission_sets"] == ["DeveloperAccess"]
        assert data["targets"]["account_ids"] == ["123456789012"]

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "entities": ["user:john.doe"],
            "permission_sets": ["DeveloperAccess"],
            "targets": {"account_ids": ["123456789012"]},
        }

        assignment = TemplateAssignment.from_dict(data)

        assert assignment.entities == ["user:john.doe"]
        assert assignment.permission_sets == ["DeveloperAccess"]
        assert assignment.targets.account_ids == ["123456789012"]

    def test_get_entity_count(self):
        """Test entity count calculation."""
        targets = TemplateTarget(account_ids=["123456789012"])
        assignment = TemplateAssignment(
            entities=["user:john.doe", "group:developers"],
            permission_sets=["DeveloperAccess"],
            targets=targets,
        )

        assert assignment.get_entity_count() == 2

    def test_get_permission_set_count(self):
        """Test permission set count calculation."""
        targets = TemplateTarget(account_ids=["123456789012"])
        assignment = TemplateAssignment(
            entities=["user:john.doe"],
            permission_sets=["DeveloperAccess", "ReadOnlyAccess"],
            targets=targets,
        )

        assert assignment.get_permission_set_count() == 2

    def test_get_total_assignments(self):
        """Test total assignments calculation."""
        targets = TemplateTarget(account_ids=["123456789012", "234567890123"])
        assignment = TemplateAssignment(
            entities=["user:john.doe", "group:developers"],
            permission_sets=["DeveloperAccess", "ReadOnlyAccess"],
            targets=targets,
        )

        # 2 entities * 2 permission sets * 2 accounts = 8 assignments
        assert assignment.get_total_assignments() == 8

    def test_get_total_assignments_with_tag_targets(self):
        """Test total assignments calculation with tag-based targets."""
        targets = TemplateTarget(account_tags={"Environment": "production"})
        assignment = TemplateAssignment(
            entities=["user:john.doe"], permission_sets=["DeveloperAccess"], targets=targets
        )

        # Tag-based targets return -1 (indeterminate)
        assert assignment.get_total_assignments() == -1


class TestTemplate:
    """Test cases for Template class."""

    def test_init_valid(self):
        """Test valid initialization."""
        metadata = TemplateMetadata(name="test-template")
        targets = TemplateTarget(account_ids=["123456789012"])
        assignment = TemplateAssignment(
            entities=["user:john.doe"], permission_sets=["DeveloperAccess"], targets=targets
        )

        template = Template(metadata=metadata, assignments=[assignment])

        assert template.metadata == metadata
        assert template.assignments == [assignment]

    def test_init_without_assignments_raises_error(self):
        """Test that initialization without assignments raises an error."""
        metadata = TemplateMetadata(name="test-template")

        with pytest.raises(ValueError, match="At least one assignment must be specified"):
            Template(metadata=metadata, assignments=[])

    def test_to_dict(self):
        """Test conversion to dictionary."""
        metadata = TemplateMetadata(name="test-template")
        targets = TemplateTarget(account_ids=["123456789012"])
        assignment = TemplateAssignment(
            entities=["user:john.doe"], permission_sets=["DeveloperAccess"], targets=targets
        )

        template = Template(metadata=metadata, assignments=[assignment])
        data = template.to_dict()

        assert data["metadata"]["name"] == "test-template"
        assert len(data["assignments"]) == 1
        assert data["assignments"][0]["entities"] == ["user:john.doe"]

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "metadata": {"name": "test-template"},
            "assignments": [
                {
                    "entities": ["user:john.doe"],
                    "permission_sets": ["DeveloperAccess"],
                    "targets": {"account_ids": ["123456789012"]},
                }
            ],
        }

        template = Template.from_dict(data)

        assert template.metadata.name == "test-template"
        assert len(template.assignments) == 1
        assert template.assignments[0].entities == ["user:john.doe"]

    def test_validate_structure_valid(self):
        """Test structure validation with valid template."""
        metadata = TemplateMetadata(name="test-template")
        targets = TemplateTarget(account_ids=["123456789012"])
        assignment = TemplateAssignment(
            entities=["user:john.doe"], permission_sets=["DeveloperAccess"], targets=targets
        )

        template = Template(metadata=metadata, assignments=[assignment])
        errors = template.validate_structure()

        assert len(errors) == 0

    def test_validate_structure_invalid_metadata(self):
        """Test structure validation with invalid metadata."""
        metadata = TemplateMetadata(name="")  # Empty name
        targets = TemplateTarget(account_ids=["123456789012"])
        assignment = TemplateAssignment(
            entities=["user:john.doe"], permission_sets=["DeveloperAccess"], targets=targets
        )

        template = Template(metadata=metadata, assignments=[assignment])
        errors = template.validate_structure()

        assert len(errors) == 1
        assert "Template name is required" in errors[0]

    def test_get_total_assignments(self):
        """Test total assignments calculation."""
        metadata = TemplateMetadata(name="test-template")
        targets = TemplateTarget(account_ids=["123456789012", "234567890123"])
        assignment = TemplateAssignment(
            entities=["user:john.doe", "group:developers"],
            permission_sets=["DeveloperAccess", "ReadOnlyAccess"],
            targets=targets,
        )

        template = Template(metadata=metadata, assignments=[assignment])

        # 2 entities * 2 permission sets * 2 accounts = 8 assignments
        assert template.get_total_assignments() == 8

    def test_get_entity_count(self):
        """Test entity count calculation."""
        metadata = TemplateMetadata(name="test-template")
        targets = TemplateTarget(account_ids=["123456789012"])
        assignment1 = TemplateAssignment(
            entities=["user:john.doe", "user:jane.smith"],
            permission_sets=["DeveloperAccess"],
            targets=targets,
        )
        assignment2 = TemplateAssignment(
            entities=["group:developers", "user:john.doe"],  # john.doe appears twice
            permission_sets=["ReadOnlyAccess"],
            targets=targets,
        )

        template = Template(metadata=metadata, assignments=[assignment1, assignment2])

        # Should count unique entities: user:john.doe, user:jane.smith, group:developers
        assert template.get_entity_count() == 3

    def test_get_permission_set_count(self):
        """Test permission set count calculation."""
        metadata = TemplateMetadata(name="test-template")
        targets = TemplateTarget(account_ids=["123456789012"])
        assignment1 = TemplateAssignment(
            entities=["user:john.doe"],
            permission_sets=["DeveloperAccess", "ReadOnlyAccess"],
            targets=targets,
        )
        assignment2 = TemplateAssignment(
            entities=["group:developers"],
            permission_sets=["AdminAccess", "DeveloperAccess"],  # DeveloperAccess appears twice
            targets=targets,
        )

        template = Template(metadata=metadata, assignments=[assignment1, assignment2])

        # Should count unique permission sets: DeveloperAccess, ReadOnlyAccess, AdminAccess
        assert template.get_permission_set_count() == 3

    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.dump")
    def test_save_to_file(self, mock_yaml_dump, mock_file):
        """Test saving template to file."""
        metadata = TemplateMetadata(name="test-template")
        targets = TemplateTarget(account_ids=["123456789012"])
        assignment = TemplateAssignment(
            entities=["user:john.doe"], permission_sets=["DeveloperAccess"], targets=targets
        )

        template = Template(metadata=metadata, assignments=[assignment])
        file_path = Path("/tmp/test.yaml")

        template.save_to_file(file_path)

        mock_file.assert_called_once()
        mock_yaml_dump.assert_called_once()

    @patch("builtins.open", new_callable=mock_open, read_data="metadata:\n  name: test-template")
    @patch("yaml.safe_load")
    def test_load_from_file(self, mock_yaml_load, mock_file):
        """Test loading template from file."""
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

        file_path = Path("/tmp/test.yaml")
        template = Template.load_from_file(file_path)

        mock_file.assert_called_once()
        mock_yaml_load.assert_called_once()
        assert template.metadata.name == "test-template"

    def test_create_example(self):
        """Test creating example template."""
        template = Template.create_example()

        assert template.metadata.name == "example-developer-template"
        assert template.metadata.description == "Example template for developer access"
        assert len(template.assignments) == 1

        assignment = template.assignments[0]
        assert "user:john.doe" in assignment.entities
        assert "group:developers" in assignment.entities
        assert "DeveloperAccess" in assignment.permission_sets
        assert "ReadOnlyAccess" in assignment.permission_sets
        assert assignment.targets.account_tags == {"Environment": "development", "Team": "backend"}
