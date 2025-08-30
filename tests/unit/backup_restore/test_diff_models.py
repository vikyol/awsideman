"""
Unit tests for backup diff data models.

Tests the diff models, validation, and serialization functionality.
"""

import json
from datetime import datetime

import pytest

from src.awsideman.backup_restore.diff_models import (
    AttributeChange,
    ChangeType,
    DiffFormat,
    DiffResult,
    DiffSummary,
    ResourceChange,
    ResourceDiff,
)


class TestChangeType:
    """Test ChangeType enum."""

    def test_change_type_values(self):
        """Test ChangeType enum values."""
        assert ChangeType.CREATED.value == "created"
        assert ChangeType.DELETED.value == "deleted"
        assert ChangeType.MODIFIED.value == "modified"

    def test_change_type_from_string(self):
        """Test creating ChangeType from string values."""
        assert ChangeType("created") == ChangeType.CREATED
        assert ChangeType("deleted") == ChangeType.DELETED
        assert ChangeType("modified") == ChangeType.MODIFIED


class TestDiffFormat:
    """Test DiffFormat enum."""

    def test_diff_format_values(self):
        """Test DiffFormat enum values."""
        assert DiffFormat.CONSOLE.value == "console"
        assert DiffFormat.JSON.value == "json"
        assert DiffFormat.CSV.value == "csv"
        assert DiffFormat.HTML.value == "html"

    def test_diff_format_from_string(self):
        """Test creating DiffFormat from string values."""
        assert DiffFormat("console") == DiffFormat.CONSOLE
        assert DiffFormat("json") == DiffFormat.JSON
        assert DiffFormat("csv") == DiffFormat.CSV
        assert DiffFormat("html") == DiffFormat.HTML


class TestAttributeChange:
    """Test AttributeChange model."""

    def test_attribute_change_creation(self):
        """Test creating AttributeChange with valid data."""
        change = AttributeChange(
            attribute_name="email", before_value="old@example.com", after_value="new@example.com"
        )

        assert change.attribute_name == "email"
        assert change.before_value == "old@example.com"
        assert change.after_value == "new@example.com"

    def test_attribute_change_serialization(self):
        """Test AttributeChange serialization to/from dict."""
        change = AttributeChange(
            attribute_name="display_name", before_value="John Doe", after_value="Jane Doe"
        )

        # Test to_dict
        data = change.to_dict()
        expected = {
            "attribute_name": "display_name",
            "before_value": "John Doe",
            "after_value": "Jane Doe",
        }
        assert data == expected

        # Test from_dict
        restored = AttributeChange.from_dict(data)
        assert restored.attribute_name == change.attribute_name
        assert restored.before_value == change.before_value
        assert restored.after_value == change.after_value

    def test_attribute_change_with_none_values(self):
        """Test AttributeChange with None values."""
        change = AttributeChange(
            attribute_name="description", before_value=None, after_value="New description"
        )

        assert change.attribute_name == "description"
        assert change.before_value is None
        assert change.after_value == "New description"

        # Test serialization with None values
        data = change.to_dict()
        restored = AttributeChange.from_dict(data)
        assert restored.before_value is None
        assert restored.after_value == "New description"


class TestResourceChange:
    """Test ResourceChange model."""

    def test_resource_change_creation(self):
        """Test creating ResourceChange with valid data."""
        change = ResourceChange(
            change_type=ChangeType.CREATED,
            resource_type="users",
            resource_id="user-123",
            resource_name="testuser",
        )

        assert change.change_type == ChangeType.CREATED
        assert change.resource_type == "users"
        assert change.resource_id == "user-123"
        assert change.resource_name == "testuser"
        assert change.before_value is None
        assert change.after_value is None
        assert len(change.attribute_changes) == 0

    def test_resource_change_validation_errors(self):
        """Test ResourceChange validation with invalid data."""
        # Test empty resource_id
        with pytest.raises(ValueError, match="resource_id cannot be empty"):
            ResourceChange(
                change_type=ChangeType.CREATED,
                resource_type="users",
                resource_id="",
                resource_name="testuser",
            )

        # Test empty resource_type
        with pytest.raises(ValueError, match="resource_type cannot be empty"):
            ResourceChange(
                change_type=ChangeType.CREATED,
                resource_type="",
                resource_id="user-123",
                resource_name="testuser",
            )

    def test_resource_change_with_attribute_changes(self):
        """Test ResourceChange with attribute changes."""
        attr_change = AttributeChange(
            attribute_name="email", before_value="old@example.com", after_value="new@example.com"
        )

        change = ResourceChange(
            change_type=ChangeType.MODIFIED,
            resource_type="users",
            resource_id="user-123",
            resource_name="testuser",
            attribute_changes=[attr_change],
        )

        assert len(change.attribute_changes) == 1
        assert change.attribute_changes[0].attribute_name == "email"

    def test_resource_change_serialization(self):
        """Test ResourceChange serialization to/from dict."""
        attr_change = AttributeChange(
            attribute_name="display_name", before_value="Old Name", after_value="New Name"
        )

        change = ResourceChange(
            change_type=ChangeType.MODIFIED,
            resource_type="users",
            resource_id="user-123",
            resource_name="testuser",
            before_value={"display_name": "Old Name"},
            after_value={"display_name": "New Name"},
            attribute_changes=[attr_change],
        )

        # Test to_dict
        data = change.to_dict()
        assert data["change_type"] == "modified"
        assert data["resource_type"] == "users"
        assert data["resource_id"] == "user-123"
        assert data["resource_name"] == "testuser"
        assert len(data["attribute_changes"]) == 1

        # Test from_dict
        restored = ResourceChange.from_dict(data)
        assert restored.change_type == ChangeType.MODIFIED
        assert restored.resource_type == "users"
        assert restored.resource_id == "user-123"
        assert restored.resource_name == "testuser"
        assert len(restored.attribute_changes) == 1
        assert restored.attribute_changes[0].attribute_name == "display_name"


class TestResourceDiff:
    """Test ResourceDiff model."""

    def test_resource_diff_creation(self):
        """Test creating ResourceDiff with valid data."""
        diff = ResourceDiff(resource_type="users")

        assert diff.resource_type == "users"
        assert len(diff.created) == 0
        assert len(diff.deleted) == 0
        assert len(diff.modified) == 0
        assert diff.total_changes == 0
        assert not diff.has_changes

    def test_resource_diff_with_changes(self):
        """Test ResourceDiff with various changes."""
        created_change = ResourceChange(
            change_type=ChangeType.CREATED,
            resource_type="users",
            resource_id="user-1",
            resource_name="newuser",
        )

        deleted_change = ResourceChange(
            change_type=ChangeType.DELETED,
            resource_type="users",
            resource_id="user-2",
            resource_name="olduser",
        )

        modified_change = ResourceChange(
            change_type=ChangeType.MODIFIED,
            resource_type="users",
            resource_id="user-3",
            resource_name="modifieduser",
        )

        diff = ResourceDiff(
            resource_type="users",
            created=[created_change],
            deleted=[deleted_change],
            modified=[modified_change],
        )

        assert len(diff.created) == 1
        assert len(diff.deleted) == 1
        assert len(diff.modified) == 1
        assert diff.total_changes == 3
        assert diff.has_changes

    def test_resource_diff_serialization(self):
        """Test ResourceDiff serialization to/from dict."""
        change = ResourceChange(
            change_type=ChangeType.CREATED,
            resource_type="users",
            resource_id="user-1",
            resource_name="testuser",
        )

        diff = ResourceDiff(resource_type="users", created=[change])

        # Test to_dict
        data = diff.to_dict()
        assert data["resource_type"] == "users"
        assert len(data["created"]) == 1
        assert len(data["deleted"]) == 0
        assert len(data["modified"]) == 0
        assert data["total_changes"] == 1

        # Test from_dict
        restored = ResourceDiff.from_dict(data)
        assert restored.resource_type == "users"
        assert len(restored.created) == 1
        assert len(restored.deleted) == 0
        assert len(restored.modified) == 0
        assert restored.total_changes == 1


class TestDiffSummary:
    """Test DiffSummary model."""

    def test_diff_summary_creation(self):
        """Test creating DiffSummary with valid data."""
        summary = DiffSummary(
            total_changes=5,
            changes_by_type={"users": 2, "groups": 3},
            changes_by_action={"created": 2, "deleted": 1, "modified": 2},
        )

        assert summary.total_changes == 5
        assert summary.changes_by_type["users"] == 2
        assert summary.changes_by_type["groups"] == 3
        assert summary.changes_by_action["created"] == 2

    def test_diff_summary_validation_errors(self):
        """Test DiffSummary validation with invalid data."""
        # Test negative total_changes
        with pytest.raises(ValueError, match="total_changes cannot be negative"):
            DiffSummary(total_changes=-1)

    def test_diff_summary_serialization(self):
        """Test DiffSummary serialization to/from dict."""
        summary = DiffSummary(
            total_changes=3,
            changes_by_type={"users": 1, "groups": 2},
            changes_by_action={"created": 1, "modified": 2},
        )

        # Test to_dict
        data = summary.to_dict()
        expected = {
            "total_changes": 3,
            "changes_by_type": {"users": 1, "groups": 2},
            "changes_by_action": {"created": 1, "modified": 2},
        }
        assert data == expected

        # Test from_dict
        restored = DiffSummary.from_dict(data)
        assert restored.total_changes == 3
        assert restored.changes_by_type == {"users": 1, "groups": 2}
        assert restored.changes_by_action == {"created": 1, "modified": 2}


class TestDiffResult:
    """Test DiffResult model."""

    def test_diff_result_creation(self):
        """Test creating DiffResult with valid data."""
        source_timestamp = datetime(2025, 1, 1, 12, 0, 0)
        target_timestamp = datetime(2025, 1, 2, 12, 0, 0)

        user_diff = ResourceDiff(resource_type="users")
        group_diff = ResourceDiff(resource_type="groups")
        permission_set_diff = ResourceDiff(resource_type="permission_sets")
        assignment_diff = ResourceDiff(resource_type="assignments")

        summary = DiffSummary(total_changes=0)

        result = DiffResult(
            source_backup_id="backup-1",
            target_backup_id="backup-2",
            source_timestamp=source_timestamp,
            target_timestamp=target_timestamp,
            user_diff=user_diff,
            group_diff=group_diff,
            permission_set_diff=permission_set_diff,
            assignment_diff=assignment_diff,
            summary=summary,
        )

        assert result.source_backup_id == "backup-1"
        assert result.target_backup_id == "backup-2"
        assert result.source_timestamp == source_timestamp
        assert result.target_timestamp == target_timestamp
        assert not result.has_changes

    def test_diff_result_validation_errors(self):
        """Test DiffResult validation with invalid data."""
        source_timestamp = datetime(2025, 1, 1, 12, 0, 0)
        target_timestamp = datetime(2025, 1, 2, 12, 0, 0)

        user_diff = ResourceDiff(resource_type="users")
        group_diff = ResourceDiff(resource_type="groups")
        permission_set_diff = ResourceDiff(resource_type="permission_sets")
        assignment_diff = ResourceDiff(resource_type="assignments")
        summary = DiffSummary(total_changes=0)

        # Test empty source_backup_id
        with pytest.raises(ValueError, match="source_backup_id cannot be empty"):
            DiffResult(
                source_backup_id="",
                target_backup_id="backup-2",
                source_timestamp=source_timestamp,
                target_timestamp=target_timestamp,
                user_diff=user_diff,
                group_diff=group_diff,
                permission_set_diff=permission_set_diff,
                assignment_diff=assignment_diff,
                summary=summary,
            )

        # Test empty target_backup_id
        with pytest.raises(ValueError, match="target_backup_id cannot be empty"):
            DiffResult(
                source_backup_id="backup-1",
                target_backup_id="",
                source_timestamp=source_timestamp,
                target_timestamp=target_timestamp,
                user_diff=user_diff,
                group_diff=group_diff,
                permission_set_diff=permission_set_diff,
                assignment_diff=assignment_diff,
                summary=summary,
            )

    def test_diff_result_with_changes(self):
        """Test DiffResult with actual changes."""
        source_timestamp = datetime(2025, 1, 1, 12, 0, 0)
        target_timestamp = datetime(2025, 1, 2, 12, 0, 0)

        # Create a user change
        user_change = ResourceChange(
            change_type=ChangeType.CREATED,
            resource_type="users",
            resource_id="user-1",
            resource_name="newuser",
        )

        user_diff = ResourceDiff(resource_type="users", created=[user_change])
        group_diff = ResourceDiff(resource_type="groups")
        permission_set_diff = ResourceDiff(resource_type="permission_sets")
        assignment_diff = ResourceDiff(resource_type="assignments")

        # Summary will be auto-calculated
        summary = DiffSummary(total_changes=0)

        result = DiffResult(
            source_backup_id="backup-1",
            target_backup_id="backup-2",
            source_timestamp=source_timestamp,
            target_timestamp=target_timestamp,
            user_diff=user_diff,
            group_diff=group_diff,
            permission_set_diff=permission_set_diff,
            assignment_diff=assignment_diff,
            summary=summary,
        )

        # Check that summary was auto-updated
        assert result.has_changes
        assert result.summary.total_changes == 1
        assert result.summary.changes_by_type["users"] == 1
        assert result.summary.changes_by_action["created"] == 1

    def test_diff_result_resource_type_correction(self):
        """Test that DiffResult corrects resource types in diffs."""
        source_timestamp = datetime(2025, 1, 1, 12, 0, 0)
        target_timestamp = datetime(2025, 1, 2, 12, 0, 0)

        # Create diffs with wrong resource types
        user_diff = ResourceDiff(resource_type="wrong_type")
        group_diff = ResourceDiff(resource_type="wrong_type")
        permission_set_diff = ResourceDiff(resource_type="wrong_type")
        assignment_diff = ResourceDiff(resource_type="wrong_type")

        summary = DiffSummary(total_changes=0)

        result = DiffResult(
            source_backup_id="backup-1",
            target_backup_id="backup-2",
            source_timestamp=source_timestamp,
            target_timestamp=target_timestamp,
            user_diff=user_diff,
            group_diff=group_diff,
            permission_set_diff=permission_set_diff,
            assignment_diff=assignment_diff,
            summary=summary,
        )

        # Check that resource types were corrected
        assert result.user_diff.resource_type == "users"
        assert result.group_diff.resource_type == "groups"
        assert result.permission_set_diff.resource_type == "permission_sets"
        assert result.assignment_diff.resource_type == "assignments"

    def test_diff_result_serialization(self):
        """Test DiffResult serialization to/from dict."""
        source_timestamp = datetime(2025, 1, 1, 12, 0, 0)
        target_timestamp = datetime(2025, 1, 2, 12, 0, 0)

        user_diff = ResourceDiff(resource_type="users")
        group_diff = ResourceDiff(resource_type="groups")
        permission_set_diff = ResourceDiff(resource_type="permission_sets")
        assignment_diff = ResourceDiff(resource_type="assignments")
        summary = DiffSummary(total_changes=0)

        result = DiffResult(
            source_backup_id="backup-1",
            target_backup_id="backup-2",
            source_timestamp=source_timestamp,
            target_timestamp=target_timestamp,
            user_diff=user_diff,
            group_diff=group_diff,
            permission_set_diff=permission_set_diff,
            assignment_diff=assignment_diff,
            summary=summary,
        )

        # Test to_dict
        data = result.to_dict()
        assert data["source_backup_id"] == "backup-1"
        assert data["target_backup_id"] == "backup-2"
        assert data["source_timestamp"] == source_timestamp.isoformat()
        assert data["target_timestamp"] == target_timestamp.isoformat()
        assert data["has_changes"] is False

        # Test from_dict
        restored = DiffResult.from_dict(data)
        assert restored.source_backup_id == "backup-1"
        assert restored.target_backup_id == "backup-2"
        assert restored.source_timestamp == source_timestamp
        assert restored.target_timestamp == target_timestamp
        assert not restored.has_changes

    def test_diff_result_json_serialization(self):
        """Test DiffResult JSON serialization compatibility."""
        source_timestamp = datetime(2025, 1, 1, 12, 0, 0)
        target_timestamp = datetime(2025, 1, 2, 12, 0, 0)

        user_diff = ResourceDiff(resource_type="users")
        group_diff = ResourceDiff(resource_type="groups")
        permission_set_diff = ResourceDiff(resource_type="permission_sets")
        assignment_diff = ResourceDiff(resource_type="assignments")
        summary = DiffSummary(total_changes=0)

        result = DiffResult(
            source_backup_id="backup-1",
            target_backup_id="backup-2",
            source_timestamp=source_timestamp,
            target_timestamp=target_timestamp,
            user_diff=user_diff,
            group_diff=group_diff,
            permission_set_diff=permission_set_diff,
            assignment_diff=assignment_diff,
            summary=summary,
        )

        # Test JSON serialization
        data = result.to_dict()
        json_str = json.dumps(data)

        # Test JSON deserialization
        restored_data = json.loads(json_str)
        restored = DiffResult.from_dict(restored_data)

        assert restored.source_backup_id == result.source_backup_id
        assert restored.target_backup_id == result.target_backup_id
        assert restored.source_timestamp == result.source_timestamp
        assert restored.target_timestamp == result.target_timestamp
