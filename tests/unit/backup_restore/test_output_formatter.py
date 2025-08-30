"""
Unit tests for backup diff output formatter.
"""

from datetime import datetime
from unittest.mock import patch

import pytest

from src.awsideman.backup_restore.diff_models import (
    AttributeChange,
    ChangeType,
    DiffResult,
    DiffSummary,
    ResourceChange,
    ResourceDiff,
)
from src.awsideman.backup_restore.output_formatter import Colors, OutputFormatter


class TestColors:
    """Test color functionality."""

    def test_disable_colors(self):
        """Test that disable_colors removes all color codes."""
        # Store original values
        original_red = Colors.RED
        original_reset = Colors.RESET

        try:
            Colors.disable_colors()
            assert Colors.RED == ""
            assert Colors.GREEN == ""
            assert Colors.RESET == ""
        finally:
            # Restore original values
            Colors.RED = original_red
            Colors.RESET = original_reset


class TestOutputFormatter:
    """Test output formatter functionality."""

    @pytest.fixture
    def formatter(self):
        """Create a formatter instance without colors for testing."""
        return OutputFormatter(use_colors=False)

    @pytest.fixture
    def formatter_with_colors(self):
        """Create a formatter instance with colors."""
        return OutputFormatter(use_colors=True)

    @pytest.fixture
    def sample_diff_result(self):
        """Create a sample diff result for testing."""
        source_timestamp = datetime(2025, 1, 15, 10, 0, 0)
        target_timestamp = datetime(2025, 1, 16, 10, 0, 0)

        # Create some sample changes
        user_created = ResourceChange(
            change_type=ChangeType.CREATED,
            resource_type="users",
            resource_id="user123",
            resource_name="john.doe@example.com",
        )

        user_deleted = ResourceChange(
            change_type=ChangeType.DELETED,
            resource_type="users",
            resource_id="user456",
            resource_name="jane.smith@example.com",
        )

        user_modified = ResourceChange(
            change_type=ChangeType.MODIFIED,
            resource_type="users",
            resource_id="user789",
            resource_name="bob.wilson@example.com",
            attribute_changes=[
                AttributeChange(
                    attribute_name="display_name",
                    before_value="Bob Wilson",
                    after_value="Robert Wilson",
                ),
                AttributeChange(
                    attribute_name="title", before_value="Developer", after_value="Senior Developer"
                ),
            ],
        )

        group_created = ResourceChange(
            change_type=ChangeType.CREATED,
            resource_type="groups",
            resource_id="group123",
            resource_name="Developers",
        )

        # Create resource diffs
        user_diff = ResourceDiff(
            resource_type="users",
            created=[user_created],
            deleted=[user_deleted],
            modified=[user_modified],
        )

        group_diff = ResourceDiff(resource_type="groups", created=[group_created])

        permission_set_diff = ResourceDiff(resource_type="permission_sets")
        assignment_diff = ResourceDiff(resource_type="assignments")

        # Create summary
        summary = DiffSummary(
            total_changes=4,
            changes_by_type={"users": 3, "groups": 1, "permission_sets": 0, "assignments": 0},
            changes_by_action={"created": 2, "deleted": 1, "modified": 1},
        )

        return DiffResult(
            source_backup_id="backup_20250115",
            target_backup_id="backup_20250116",
            source_timestamp=source_timestamp,
            target_timestamp=target_timestamp,
            user_diff=user_diff,
            group_diff=group_diff,
            permission_set_diff=permission_set_diff,
            assignment_diff=assignment_diff,
            summary=summary,
        )

    @pytest.fixture
    def empty_diff_result(self):
        """Create an empty diff result (no changes)."""
        source_timestamp = datetime(2025, 1, 15, 10, 0, 0)
        target_timestamp = datetime(2025, 1, 16, 10, 0, 0)

        user_diff = ResourceDiff(resource_type="users")
        group_diff = ResourceDiff(resource_type="groups")
        permission_set_diff = ResourceDiff(resource_type="permission_sets")
        assignment_diff = ResourceDiff(resource_type="assignments")

        summary = DiffSummary(total_changes=0, changes_by_type={}, changes_by_action={})

        return DiffResult(
            source_backup_id="backup_20250115",
            target_backup_id="backup_20250116",
            source_timestamp=source_timestamp,
            target_timestamp=target_timestamp,
            user_diff=user_diff,
            group_diff=group_diff,
            permission_set_diff=permission_set_diff,
            assignment_diff=assignment_diff,
            summary=summary,
        )

    def test_format_console_no_changes(self, formatter, empty_diff_result):
        """Test console formatting when there are no changes."""
        output = formatter.format_console(empty_diff_result)

        assert "Backup Comparison Results" in output
        assert "backup_20250115" in output
        assert "backup_20250116" in output
        assert "No changes detected" in output
        assert "2025-01-15 10:00:00 UTC" in output
        assert "2025-01-16 10:00:00 UTC" in output

    def test_format_console_with_changes(self, formatter, sample_diff_result):
        """Test console formatting with changes."""
        output = formatter.format_console(sample_diff_result)

        # Check header
        assert "Backup Comparison Results" in output
        assert "backup_20250115" in output
        assert "backup_20250116" in output

        # Check summary
        assert "Summary" in output
        assert "Total Changes: 4" in output
        assert "Created: 2" in output
        assert "Deleted: 1" in output
        assert "Modified: 1" in output

        # Check resource sections
        assert "Users (3 changes)" in output
        assert "Groups (1 changes)" in output

        # Check specific changes
        assert "john.doe@example.com" in output
        assert "jane.smith@example.com" in output
        assert "bob.wilson@example.com" in output
        assert "Developers" in output

        # Check attribute changes
        assert "display_name" in output
        assert "Bob Wilson" in output
        assert "Robert Wilson" in output
        assert "title" in output
        assert "Developer" in output
        assert "Senior Developer" in output

    def test_format_console_with_colors(self, formatter_with_colors, sample_diff_result):
        """Test console formatting with color codes."""
        # Reset colors to ensure they are enabled for this test
        Colors.RED = "\033[91m"
        Colors.GREEN = "\033[92m"
        Colors.YELLOW = "\033[93m"
        Colors.BOLD = "\033[1m"
        Colors.RESET = "\033[0m"

        output = formatter_with_colors.format_console(sample_diff_result)

        # Should contain ANSI color codes (can be \033[ or \x1b[)
        assert "\033[" in output or "\x1b[" in output  # ANSI escape sequence
        assert Colors.BOLD in output
        assert Colors.GREEN in output
        assert Colors.RED in output
        assert Colors.YELLOW in output
        assert Colors.RESET in output

    def test_format_resource_change_created(self, formatter):
        """Test formatting of created resource change."""
        change = ResourceChange(
            change_type=ChangeType.CREATED,
            resource_type="users",
            resource_id="user123",
            resource_name="test.user@example.com",
        )

        lines = formatter._format_resource_change(change, indent="  ")

        assert len(lines) >= 1
        assert "test.user@example.com" in lines[0]
        assert "+" in lines[0]  # Created icon

    def test_format_resource_change_deleted(self, formatter):
        """Test formatting of deleted resource change."""
        change = ResourceChange(
            change_type=ChangeType.DELETED,
            resource_type="users",
            resource_id="user123",
            resource_name="test.user@example.com",
        )

        lines = formatter._format_resource_change(change, indent="  ")

        assert len(lines) >= 1
        assert "test.user@example.com" in lines[0]
        assert "-" in lines[0]  # Deleted icon

    def test_format_resource_change_modified(self, formatter):
        """Test formatting of modified resource change."""
        change = ResourceChange(
            change_type=ChangeType.MODIFIED,
            resource_type="users",
            resource_id="user123",
            resource_name="test.user@example.com",
            attribute_changes=[
                AttributeChange(
                    attribute_name="email",
                    before_value="old@example.com",
                    after_value="new@example.com",
                )
            ],
        )

        lines = formatter._format_resource_change(change, indent="  ")

        assert len(lines) >= 1
        assert "test.user@example.com" in lines[0]
        assert "~" in lines[0]  # Modified icon

        # Check attribute change formatting
        output = "\n".join(lines)
        assert "email:" in output
        assert "old@example.com" in output
        assert "new@example.com" in output

    def test_format_resource_change_with_id_only(self, formatter):
        """Test formatting when only resource ID is available."""
        change = ResourceChange(
            change_type=ChangeType.CREATED, resource_type="users", resource_id="user123"
        )

        lines = formatter._format_resource_change(change, indent="  ")

        assert len(lines) >= 1
        assert "user123" in lines[0]

    def test_format_resource_change_with_different_name_and_id(self, formatter):
        """Test formatting when name and ID are different."""
        change = ResourceChange(
            change_type=ChangeType.CREATED,
            resource_type="users",
            resource_id="user123",
            resource_name="John Doe",
        )

        lines = formatter._format_resource_change(change, indent="  ")

        assert len(lines) >= 2
        assert "John Doe" in lines[0]
        assert "ID: user123" in lines[1]

    def test_format_attribute_change(self, formatter):
        """Test formatting of attribute changes."""
        attr_change = AttributeChange(
            attribute_name="status", before_value="active", after_value="inactive"
        )

        lines = formatter._format_attribute_change(attr_change, indent="    ")

        assert len(lines) == 3
        assert "status:" in lines[0]
        assert "active" in lines[1]
        assert "inactive" in lines[2]

    def test_format_value_none(self, formatter):
        """Test formatting of None values."""
        result = formatter._format_value(None)
        assert result == "(none)"

    def test_format_value_string(self, formatter):
        """Test formatting of string values."""
        result = formatter._format_value("test string")
        assert result == '"test string"'

    def test_format_value_list(self, formatter):
        """Test formatting of list values."""
        result = formatter._format_value(["item1", "item2"])
        assert result == "['item1', 'item2']"

    def test_format_value_dict(self, formatter):
        """Test formatting of dict values."""
        result = formatter._format_value({"key": "value"})
        assert result == "{'key': 'value'}"

    def test_format_value_other(self, formatter):
        """Test formatting of other value types."""
        result = formatter._format_value(123)
        assert result == "123"

    def test_format_timestamp(self, formatter):
        """Test timestamp formatting."""
        timestamp = datetime(2025, 1, 15, 14, 30, 45)
        result = formatter._format_timestamp(timestamp)
        assert result == "2025-01-15 14:30:45 UTC"

    def test_get_action_color(self, formatter_with_colors):
        """Test action color mapping."""
        assert formatter_with_colors._get_action_color("created") == Colors.GREEN
        assert formatter_with_colors._get_action_color("deleted") == Colors.RED
        assert formatter_with_colors._get_action_color("modified") == Colors.YELLOW
        assert formatter_with_colors._get_action_color("unknown") == Colors.WHITE

    def test_get_action_icon(self, formatter):
        """Test action icon mapping."""
        assert formatter._get_action_icon("created") == "✓"
        assert formatter._get_action_icon("deleted") == "✗"
        assert formatter._get_action_icon("modified") == "~"
        assert formatter._get_action_icon("unknown") == "•"

    def test_format_resource_section_empty(self, formatter):
        """Test formatting of empty resource section."""
        resource_diff = ResourceDiff(resource_type="users")

        lines = formatter._format_resource_section("Users", resource_diff)

        # Should have header but no content
        assert len(lines) >= 2
        assert "Users (0 changes)" in lines[0]

    def test_format_resource_section_with_all_change_types(self, formatter):
        """Test formatting of resource section with all change types."""
        created_change = ResourceChange(
            change_type=ChangeType.CREATED,
            resource_type="users",
            resource_id="user1",
            resource_name="User One",
        )

        deleted_change = ResourceChange(
            change_type=ChangeType.DELETED,
            resource_type="users",
            resource_id="user2",
            resource_name="User Two",
        )

        modified_change = ResourceChange(
            change_type=ChangeType.MODIFIED,
            resource_type="users",
            resource_id="user3",
            resource_name="User Three",
        )

        resource_diff = ResourceDiff(
            resource_type="users",
            created=[created_change],
            deleted=[deleted_change],
            modified=[modified_change],
        )

        lines = formatter._format_resource_section("Users", resource_diff)
        output = "\n".join(lines)

        assert "Users (3 changes)" in output
        assert "Created (1):" in output
        assert "Deleted (1):" in output
        assert "Modified (1):" in output
        assert "User One" in output
        assert "User Two" in output
        assert "User Three" in output

    def test_initialization_with_colors_disabled(self):
        """Test formatter initialization with colors disabled."""
        with patch.object(Colors, "disable_colors") as mock_disable:
            OutputFormatter(use_colors=False)
            mock_disable.assert_called_once()

    def test_initialization_with_colors_enabled(self):
        """Test formatter initialization with colors enabled."""
        with patch.object(Colors, "disable_colors") as mock_disable:
            OutputFormatter(use_colors=True)
            mock_disable.assert_not_called()

    def test_format_json_with_changes(self, formatter, sample_diff_result):
        """Test JSON formatting with changes."""
        import json

        output = formatter.format_json(sample_diff_result)

        # Parse JSON to verify structure
        data = json.loads(output)

        # Check metadata
        assert "format_version" in data
        assert data["format_version"] == "1.0"
        assert "generated_at" in data

        # Check basic structure
        assert data["source_backup_id"] == "backup_20250115"
        assert data["target_backup_id"] == "backup_20250116"
        assert data["has_changes"] is True

        # Check timestamps
        assert data["source_timestamp"] == "2025-01-15T10:00:00"
        assert data["target_timestamp"] == "2025-01-16T10:00:00"

        # Check summary
        assert data["summary"]["total_changes"] == 4
        assert data["summary"]["changes_by_action"]["created"] == 2
        assert data["summary"]["changes_by_action"]["deleted"] == 1
        assert data["summary"]["changes_by_action"]["modified"] == 1

        # Check user diff
        user_diff = data["user_diff"]
        assert user_diff["resource_type"] == "users"
        assert user_diff["total_changes"] == 3
        assert len(user_diff["created"]) == 1
        assert len(user_diff["deleted"]) == 1
        assert len(user_diff["modified"]) == 1

        # Check specific user changes
        created_user = user_diff["created"][0]
        assert created_user["resource_id"] == "user123"
        assert created_user["resource_name"] == "john.doe@example.com"
        assert created_user["change_type"] == "created"

        modified_user = user_diff["modified"][0]
        assert modified_user["resource_id"] == "user789"
        assert len(modified_user["attribute_changes"]) == 2

        # Check attribute changes
        attr_changes = modified_user["attribute_changes"]
        display_name_change = next(
            (change for change in attr_changes if change["attribute_name"] == "display_name"), None
        )
        assert display_name_change is not None
        assert display_name_change["before_value"] == "Bob Wilson"
        assert display_name_change["after_value"] == "Robert Wilson"

        # Check group diff
        group_diff = data["group_diff"]
        assert group_diff["resource_type"] == "groups"
        assert group_diff["total_changes"] == 1
        assert len(group_diff["created"]) == 1

        created_group = group_diff["created"][0]
        assert created_group["resource_id"] == "group123"
        assert created_group["resource_name"] == "Developers"

    def test_format_json_no_changes(self, formatter, empty_diff_result):
        """Test JSON formatting when there are no changes."""
        import json

        output = formatter.format_json(empty_diff_result)
        data = json.loads(output)

        assert data["has_changes"] is False
        assert data["summary"]["total_changes"] == 0
        assert len(data["user_diff"]["created"]) == 0
        assert len(data["user_diff"]["deleted"]) == 0
        assert len(data["user_diff"]["modified"]) == 0

    def test_format_json_structure_completeness(self, formatter, sample_diff_result):
        """Test that JSON output includes all expected fields."""
        import json

        output = formatter.format_json(sample_diff_result)
        data = json.loads(output)

        # Check all top-level fields are present
        expected_fields = {
            "source_backup_id",
            "target_backup_id",
            "source_timestamp",
            "target_timestamp",
            "user_diff",
            "group_diff",
            "permission_set_diff",
            "assignment_diff",
            "summary",
            "has_changes",
            "format_version",
            "generated_at",
        }
        assert set(data.keys()) == expected_fields

        # Check resource diff structure
        for resource_type in ["user_diff", "group_diff", "permission_set_diff", "assignment_diff"]:
            resource_diff = data[resource_type]
            expected_resource_fields = {
                "resource_type",
                "created",
                "deleted",
                "modified",
                "total_changes",
            }
            assert set(resource_diff.keys()) == expected_resource_fields

    def test_format_csv_with_changes(self, formatter, sample_diff_result):
        """Test CSV formatting with changes."""
        import csv
        from io import StringIO

        output = formatter.format_csv(sample_diff_result)

        # Parse CSV to verify structure
        reader = csv.reader(StringIO(output))
        rows = list(reader)

        # Check header
        expected_headers = [
            "Resource Type",
            "Change Type",
            "Resource ID",
            "Resource Name",
            "Attribute Name",
            "Before Value",
            "After Value",
            "Source Backup",
            "Target Backup",
            "Source Timestamp",
            "Target Timestamp",
        ]
        assert rows[0] == expected_headers

        # Should have header + data rows
        assert len(rows) > 1

        # Check that we have the expected number of data rows
        # 1 created user + 1 deleted user + 2 modified user attributes + 1 created group = 5 rows
        data_rows = rows[1:]
        assert len(data_rows) == 5

        # Check created user row
        created_user_row = next(
            (row for row in data_rows if row[1] == "created" and row[0] == "users"), None
        )
        assert created_user_row is not None
        assert created_user_row[2] == "user123"  # Resource ID
        assert created_user_row[3] == "john.doe@example.com"  # Resource Name
        assert created_user_row[7] == "backup_20250115"  # Source Backup
        assert created_user_row[8] == "backup_20250116"  # Target Backup

        # Check deleted user row
        deleted_user_row = next(
            (row for row in data_rows if row[1] == "deleted" and row[0] == "users"), None
        )
        assert deleted_user_row is not None
        assert deleted_user_row[2] == "user456"  # Resource ID
        assert deleted_user_row[3] == "jane.smith@example.com"  # Resource Name

        # Check modified user attribute rows
        modified_rows = [
            row
            for row in data_rows
            if row[1] == "modified" and row[0] == "users" and row[2] == "user789"
        ]
        assert len(modified_rows) == 2

        # Check display_name change
        display_name_row = next((row for row in modified_rows if row[4] == "display_name"), None)
        assert display_name_row is not None
        assert display_name_row[5] == "Bob Wilson"  # Before Value
        assert display_name_row[6] == "Robert Wilson"  # After Value

        # Check title change
        title_row = next((row for row in modified_rows if row[4] == "title"), None)
        assert title_row is not None
        assert title_row[5] == "Developer"  # Before Value
        assert title_row[6] == "Senior Developer"  # After Value

        # Check created group row
        created_group_row = next(
            (row for row in data_rows if row[1] == "created" and row[0] == "groups"), None
        )
        assert created_group_row is not None
        assert created_group_row[2] == "group123"  # Resource ID
        assert created_group_row[3] == "Developers"  # Resource Name

    def test_format_csv_no_changes(self, formatter, empty_diff_result):
        """Test CSV formatting when there are no changes."""
        import csv
        from io import StringIO

        output = formatter.format_csv(empty_diff_result)

        # Parse CSV to verify structure
        reader = csv.reader(StringIO(output))
        rows = list(reader)

        # Should only have header row
        assert len(rows) == 1
        expected_headers = [
            "Resource Type",
            "Change Type",
            "Resource ID",
            "Resource Name",
            "Attribute Name",
            "Before Value",
            "After Value",
            "Source Backup",
            "Target Backup",
            "Source Timestamp",
            "Target Timestamp",
        ]
        assert rows[0] == expected_headers

    def test_format_csv_complex_values(self, formatter):
        """Test CSV formatting with complex values (dict, list, None)."""
        import csv
        from io import StringIO

        # Create a change with complex values
        change = ResourceChange(
            change_type=ChangeType.MODIFIED,
            resource_type="users",
            resource_id="user123",
            resource_name="test.user@example.com",
            before_value={"key": "old_value", "list": [1, 2, 3]},
            after_value={"key": "new_value", "list": [4, 5, 6]},
            attribute_changes=[
                AttributeChange(
                    attribute_name="metadata",
                    before_value={"tags": ["old"]},
                    after_value={"tags": ["new"]},
                ),
                AttributeChange(attribute_name="status", before_value=None, after_value="active"),
            ],
        )

        user_diff = ResourceDiff(resource_type="users", modified=[change])

        diff_result = DiffResult(
            source_backup_id="backup1",
            target_backup_id="backup2",
            source_timestamp=datetime(2025, 1, 15, 10, 0, 0),
            target_timestamp=datetime(2025, 1, 16, 10, 0, 0),
            user_diff=user_diff,
            group_diff=ResourceDiff(resource_type="groups"),
            permission_set_diff=ResourceDiff(resource_type="permission_sets"),
            assignment_diff=ResourceDiff(resource_type="assignments"),
            summary=DiffSummary(total_changes=1),
        )

        output = formatter.format_csv(diff_result)

        # Parse CSV
        reader = csv.reader(StringIO(output))
        rows = list(reader)

        # Should have header + 2 attribute change rows
        assert len(rows) == 3

        # Check metadata attribute row (complex values)
        metadata_row = rows[1]
        assert metadata_row[4] == "metadata"  # Attribute Name
        assert '{"tags": ["old"]}' in metadata_row[5]  # Before Value (JSON)
        assert '{"tags": ["new"]}' in metadata_row[6]  # After Value (JSON)

        # Check status attribute row (None value)
        status_row = rows[2]
        assert status_row[4] == "status"  # Attribute Name
        assert status_row[5] == ""  # Before Value (None becomes empty string)
        assert status_row[6] == "active"  # After Value

    def test_format_csv_resource_without_attribute_changes(self, formatter):
        """Test CSV formatting for resources without detailed attribute changes."""
        import csv
        from io import StringIO

        # Create a modified change without attribute_changes but with before/after values
        change = ResourceChange(
            change_type=ChangeType.MODIFIED,
            resource_type="permission_sets",
            resource_id="ps123",
            resource_name="TestPermissionSet",
            before_value={"description": "Old description"},
            after_value={"description": "New description"},
        )

        permission_set_diff = ResourceDiff(resource_type="permission_sets", modified=[change])

        diff_result = DiffResult(
            source_backup_id="backup1",
            target_backup_id="backup2",
            source_timestamp=datetime(2025, 1, 15, 10, 0, 0),
            target_timestamp=datetime(2025, 1, 16, 10, 0, 0),
            user_diff=ResourceDiff(resource_type="users"),
            group_diff=ResourceDiff(resource_type="groups"),
            permission_set_diff=permission_set_diff,
            assignment_diff=ResourceDiff(resource_type="assignments"),
            summary=DiffSummary(total_changes=1),
        )

        output = formatter.format_csv(diff_result)

        # Parse CSV
        reader = csv.reader(StringIO(output))
        rows = list(reader)

        # Should have header + 1 data row
        assert len(rows) == 2

        data_row = rows[1]
        assert data_row[0] == "permission_sets"  # Resource Type
        assert data_row[1] == "modified"  # Change Type
        assert data_row[2] == "ps123"  # Resource ID
        assert data_row[3] == "TestPermissionSet"  # Resource Name
        assert data_row[4] == ""  # Attribute Name (empty)
        assert '{"description": "Old description"}' in data_row[5]  # Before Value
        assert '{"description": "New description"}' in data_row[6]  # After Value

    def test_format_csv_timestamps_format(self, formatter, sample_diff_result):
        """Test that CSV timestamps are in ISO format."""
        import csv
        from io import StringIO

        output = formatter.format_csv(sample_diff_result)

        # Parse CSV
        reader = csv.reader(StringIO(output))
        rows = list(reader)

        # Check timestamp format in first data row
        data_row = rows[1]
        source_timestamp = data_row[9]
        target_timestamp = data_row[10]

        # Should be ISO format
        assert source_timestamp == "2025-01-15T10:00:00"
        assert target_timestamp == "2025-01-16T10:00:00"

    def test_json_output_is_valid_json(self, formatter, sample_diff_result):
        """Test that JSON output is valid JSON that can be parsed."""
        import json

        output = formatter.format_json(sample_diff_result)

        # Should not raise an exception
        try:
            parsed = json.loads(output)
            assert isinstance(parsed, dict)
        except json.JSONDecodeError:
            pytest.fail("JSON output is not valid JSON")

    def test_csv_output_is_valid_csv(self, formatter, sample_diff_result):
        """Test that CSV output is valid CSV that can be parsed."""
        import csv
        from io import StringIO

        output = formatter.format_csv(sample_diff_result)

        # Should not raise an exception
        try:
            reader = csv.reader(StringIO(output))
            rows = list(reader)
            assert len(rows) > 0
        except csv.Error:
            pytest.fail("CSV output is not valid CSV")

    def test_format_html_with_changes(self, formatter, sample_diff_result):
        """Test HTML formatting with changes."""
        output = formatter.format_html(sample_diff_result)

        # Check HTML structure
        assert output.startswith("<!DOCTYPE html>")
        assert '<html lang="en">' in output
        assert "</html>" in output
        assert "<head>" in output
        assert "<body>" in output

        # Check title
        assert "<title>AWS Identity Center Backup Comparison Report</title>" in output

        # Check header content
        assert "AWS Identity Center Backup Comparison" in output
        assert "backup_20250115" in output
        assert "backup_20250116" in output
        assert "2025-01-15 10:00:00 UTC" in output
        assert "2025-01-16 10:00:00 UTC" in output

        # Check summary dashboard
        assert "summary-dashboard" in output
        assert ">4<" in output  # Total changes
        assert ">2<" in output  # Created
        assert ">1<" in output  # Deleted and Modified

        # Check navigation
        assert "nav-link" in output
        assert "Users (3)" in output
        assert "Groups (1)" in output

        # Check resource sections
        assert 'id="users"' in output
        assert 'id="groups"' in output
        assert "Users (3 changes)" in output
        assert "Groups (1 changes)" in output

        # Check specific changes
        assert "john.doe@example.com" in output
        assert "jane.smith@example.com" in output
        assert "bob.wilson@example.com" in output
        assert "Developers" in output

        # Check attribute changes
        assert "display_name" in output
        assert "Bob Wilson" in output
        assert "Robert Wilson" in output
        assert "title" in output
        assert "Developer" in output
        assert "Senior Developer" in output

        # Check CSS classes
        assert "change-group created" in output
        assert "change-group deleted" in output
        assert "change-group modified" in output
        assert "changes-table" in output
        assert "attribute-changes" in output

    def test_format_html_no_changes(self, formatter, empty_diff_result):
        """Test HTML formatting when there are no changes."""
        output = formatter.format_html(empty_diff_result)

        # Check HTML structure
        assert output.startswith("<!DOCTYPE html>")
        assert '<html lang="en">' in output
        assert "</html>" in output

        # Check no changes message
        assert "no-changes" in output
        assert "No Changes Detected" in output
        assert "The backups are identical" in output
        assert "success-icon" in output
        assert "✓" in output

        # Should not have navigation section or resource sections (actual HTML elements)
        assert "Jump to Section" not in output
        assert '<div class="resource-section">' not in output

    def test_format_html_css_styles(self, formatter, sample_diff_result):
        """Test that HTML output includes CSS styles."""
        output = formatter.format_html(sample_diff_result)

        # Check that CSS is included
        assert "<style>" in output
        assert "</style>" in output

        # Check for key CSS classes
        assert ".container" in output
        assert ".header" in output
        assert ".summary-dashboard" in output
        assert ".resource-section" in output
        assert ".changes-table" in output
        assert ".attribute-changes" in output

        # Check for responsive design
        assert "@media (max-width: 768px)" in output

        # Check for color coding
        assert "border-top-color: #28a745" in output  # Green for created
        assert "border-top-color: #dc3545" in output  # Red for deleted
        assert "border-top-color: #ffc107" in output  # Yellow for modified

    def test_format_html_navigation_links(self, formatter, sample_diff_result):
        """Test HTML navigation links generation."""
        output = formatter.format_html(sample_diff_result)

        # Check navigation section
        assert "Jump to Section" in output

        # Check links to sections with changes
        assert 'href="#users"' in output
        assert 'href="#groups"' in output

        # Should not have links to sections without changes
        assert 'href="#permission-sets"' not in output
        assert 'href="#assignments"' not in output

    def test_format_html_tables_structure(self, formatter, sample_diff_result):
        """Test HTML table structure for changes."""
        output = formatter.format_html(sample_diff_result)

        # Check table structure
        assert '<table class="changes-table">' in output
        assert "<thead>" in output
        assert "<tbody>" in output
        assert "</table>" in output

        # Check table headers
        assert "<th>Resource Name</th>" in output
        assert "<th>Resource ID</th>" in output
        assert "<th>Changes</th>" in output  # For modified resources

        # Check table rows
        assert "<tr>" in output
        assert "<td>" in output

    def test_format_html_attribute_changes_display(self, formatter):
        """Test HTML formatting of attribute changes."""
        # Create a change with attribute changes
        change = ResourceChange(
            change_type=ChangeType.MODIFIED,
            resource_type="users",
            resource_id="user123",
            resource_name="test.user@example.com",
            attribute_changes=[
                AttributeChange(
                    attribute_name="email",
                    before_value="old@example.com",
                    after_value="new@example.com",
                ),
                AttributeChange(attribute_name="status", before_value=None, after_value="active"),
            ],
        )

        html = formatter._format_html_attribute_changes(change.attribute_changes)

        # Check attribute changes structure
        assert "attribute-changes" in html
        assert "attribute-change" in html
        assert "attribute-name" in html
        assert "value-change" in html
        assert "before-value" in html
        assert "after-value" in html

        # Check content
        assert "email" in html
        assert "old@example.com" in html
        assert "new@example.com" in html
        assert "status" in html
        assert "(none)" in html  # None value formatting
        assert "active" in html

    def test_format_html_escape_special_characters(self, formatter):
        """Test HTML escaping of special characters."""
        # Test the escape function directly
        assert formatter._escape_html("<script>") == "&lt;script&gt;"
        assert formatter._escape_html("&amp;") == "&amp;amp;"
        assert formatter._escape_html('"quotes"') == "&quot;quotes&quot;"
        assert formatter._escape_html("'single'") == "&#x27;single&#x27;"

        # Test with a change containing special characters
        change = ResourceChange(
            change_type=ChangeType.CREATED,
            resource_type="users",
            resource_id="user<123>",
            resource_name="test&user@example.com",
        )

        user_diff = ResourceDiff(resource_type="users", created=[change])

        diff_result = DiffResult(
            source_backup_id="backup1",
            target_backup_id="backup2",
            source_timestamp=datetime(2025, 1, 15, 10, 0, 0),
            target_timestamp=datetime(2025, 1, 16, 10, 0, 0),
            user_diff=user_diff,
            group_diff=ResourceDiff(resource_type="groups"),
            permission_set_diff=ResourceDiff(resource_type="permission_sets"),
            assignment_diff=ResourceDiff(resource_type="assignments"),
            summary=DiffSummary(total_changes=1),
        )

        output = formatter.format_html(diff_result)

        # Check that special characters are escaped
        assert "user&lt;123&gt;" in output
        assert "test&amp;user@example.com" in output
        assert "<script>" not in output  # Should not contain unescaped script tags

    def test_format_html_footer(self, formatter):
        """Test HTML footer generation."""
        footer = formatter._format_html_footer()

        assert "footer" in footer
        assert "Report generated on" in footer
        assert "AWS Identity Manager (awsideman)" in footer
        assert "UTC" in footer

    def test_format_html_value_formatting(self, formatter):
        """Test HTML value formatting for different data types."""
        # Test None
        assert formatter._format_value_for_html(None) == "(none)"

        # Test string
        assert formatter._format_value_for_html("test") == '"test"'

        # Test dict
        result = formatter._format_value_for_html({"key": "value"})
        assert '"key": "value"' in result

        # Test list
        result = formatter._format_value_for_html(["item1", "item2"])
        assert '"item1"' in result
        assert '"item2"' in result

        # Test other types
        assert formatter._format_value_for_html(123) == "123"

    def test_format_html_responsive_design(self, formatter, sample_diff_result):
        """Test that HTML includes responsive design elements."""
        output = formatter.format_html(sample_diff_result)

        # Check viewport meta tag
        assert '<meta name="viewport" content="width=device-width, initial-scale=1.0">' in output

        # Check responsive CSS
        assert "@media (max-width: 768px)" in output
        assert "grid-template-columns: 1fr" in output  # Mobile layout
        assert "flex-direction: column" in output  # Mobile navigation

    def test_format_html_accessibility(self, formatter, sample_diff_result):
        """Test HTML accessibility features."""
        output = formatter.format_html(sample_diff_result)

        # Check language attribute
        assert 'lang="en"' in output

        # Check proper heading hierarchy
        assert "<h1>" in output
        assert "<h2>" in output
        assert "<h3>" in output

        # Check table structure
        assert "<thead>" in output
        assert "<th>" in output
        assert "<tbody>" in output

    def test_format_html_complete_document_structure(self, formatter, sample_diff_result):
        """Test that HTML output is a complete, valid document."""
        output = formatter.format_html(sample_diff_result)

        # Check document structure
        assert output.startswith("<!DOCTYPE html>")
        assert output.endswith("</html>")

        # Check required elements
        assert '<html lang="en">' in output
        assert "<head>" in output
        assert "</head>" in output
        assert "<body>" in output
        assert "</body>" in output

        # Check meta tags
        assert '<meta charset="UTF-8">' in output
        assert '<meta name="viewport"' in output

        # Check title
        assert "<title>" in output
        assert "</title>" in output

    def test_format_html_section_ids(self, formatter, sample_diff_result):
        """Test that HTML sections have proper IDs for navigation."""
        output = formatter.format_html(sample_diff_result)

        # Check section IDs
        assert 'id="users"' in output
        assert 'id="groups"' in output

        # Should not have IDs for sections without changes
        assert 'id="permission-sets"' not in output
        assert 'id="assignments"' not in output

    def test_format_html_change_group_classes(self, formatter, sample_diff_result):
        """Test that change groups have proper CSS classes."""
        output = formatter.format_html(sample_diff_result)

        # Check change group classes
        assert "change-group created" in output
        assert "change-group deleted" in output
        assert "change-group modified" in output

        # Check that each change type has its own styling
        assert "Created (" in output
        assert "Deleted (" in output
        assert "Modified (" in output
