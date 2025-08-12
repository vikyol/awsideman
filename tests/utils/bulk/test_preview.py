"""Tests for bulk operations preview functionality.

This module contains unit tests for the PreviewGenerator class and related
preview functionality for bulk operations.
"""
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from rich.console import Console

from src.awsideman.utils.bulk.preview import PreviewGenerator, PreviewSummary
from src.awsideman.utils.bulk.resolver import ResourceResolver


class TestPreviewSummary:
    """Test cases for PreviewSummary dataclass."""

    def test_preview_summary_creation(self):
        """Test PreviewSummary can be created with all fields."""
        summary = PreviewSummary(
            total_assignments=10,
            successful_resolutions=8,
            failed_resolutions=2,
            users=6,
            groups=4,
            unique_permission_sets=3,
            unique_accounts=2,
        )

        assert summary.total_assignments == 10
        assert summary.successful_resolutions == 8
        assert summary.failed_resolutions == 2
        assert summary.users == 6
        assert summary.groups == 4
        assert summary.unique_permission_sets == 3
        assert summary.unique_accounts == 2


class TestPreviewGenerator:
    """Test cases for PreviewGenerator class."""

    @pytest.fixture
    def console(self):
        """Create a mock console for testing."""
        return Mock(spec=Console)

    @pytest.fixture
    def preview_generator(self, console):
        """Create a PreviewGenerator instance for testing."""
        return PreviewGenerator(console)

    @pytest.fixture
    def sample_assignments(self):
        """Create sample assignment data for testing."""
        return [
            {
                "principal_name": "john.doe",
                "principal_type": "USER",
                "permission_set_name": "ReadOnlyAccess",
                "account_name": "Production",
                "principal_id": "user-123",
                "permission_set_arn": "arn:aws:sso:::permissionSet/ins-123/ps-456",
                "account_id": "123456789012",
                "resolution_success": True,
                "resolution_errors": [],
            },
            {
                "principal_name": "Developers",
                "principal_type": "GROUP",
                "permission_set_name": "PowerUserAccess",
                "account_name": "Development",
                "principal_id": "group-456",
                "permission_set_arn": "arn:aws:sso:::permissionSet/ins-123/ps-789",
                "account_id": "123456789013",
                "resolution_success": True,
                "resolution_errors": [],
            },
            {
                "principal_name": "invalid.user",
                "principal_type": "USER",
                "permission_set_name": "AdminAccess",
                "account_name": "Production",
                "principal_id": None,
                "permission_set_arn": "arn:aws:sso:::permissionSet/ins-123/ps-999",
                "account_id": "123456789012",
                "resolution_success": False,
                "resolution_errors": ["User invalid.user not found in Identity Store"],
            },
        ]

    def test_init(self, console):
        """Test PreviewGenerator initialization."""
        generator = PreviewGenerator(console)
        assert generator.console == console

    def test_calculate_summary(self, preview_generator, sample_assignments):
        """Test summary calculation from assignments."""
        summary = preview_generator._calculate_summary(sample_assignments)

        assert summary.total_assignments == 3
        assert summary.successful_resolutions == 2
        assert summary.failed_resolutions == 1
        assert summary.users == 2
        assert summary.groups == 1
        assert summary.unique_permission_sets == 3
        assert summary.unique_accounts == 2

    def test_calculate_summary_empty_assignments(self, preview_generator):
        """Test summary calculation with empty assignments list."""
        summary = preview_generator._calculate_summary([])

        assert summary.total_assignments == 0
        assert summary.successful_resolutions == 0
        assert summary.failed_resolutions == 0
        assert summary.users == 0
        assert summary.groups == 0
        assert summary.unique_permission_sets == 0
        assert summary.unique_accounts == 0

    def test_calculate_summary_all_users(self, preview_generator):
        """Test summary calculation with only user assignments."""
        assignments = [
            {
                "principal_name": "user1",
                "principal_type": "USER",
                "permission_set_name": "ReadOnly",
                "account_name": "Prod",
                "resolution_success": True,
            },
            {
                "principal_name": "user2",
                "principal_type": "USER",
                "permission_set_name": "ReadOnly",
                "account_name": "Prod",
                "resolution_success": True,
            },
        ]

        summary = preview_generator._calculate_summary(assignments)

        assert summary.users == 2
        assert summary.groups == 0
        assert summary.unique_permission_sets == 1
        assert summary.unique_accounts == 1

    def test_display_header_success(self, preview_generator, console):
        """Test header display with successful resolutions."""
        summary = PreviewSummary(
            total_assignments=2,
            successful_resolutions=2,
            failed_resolutions=0,
            users=1,
            groups=1,
            unique_permission_sets=2,
            unique_accounts=1,
        )

        preview_generator._display_header("assign", summary)

        # Verify console.print was called
        assert console.print.call_count >= 2

    def test_display_header_with_errors(self, preview_generator, console):
        """Test header display with resolution errors."""
        summary = PreviewSummary(
            total_assignments=3,
            successful_resolutions=2,
            failed_resolutions=1,
            users=2,
            groups=1,
            unique_permission_sets=2,
            unique_accounts=1,
        )

        preview_generator._display_header("revoke", summary)

        # Verify console.print was called
        assert console.print.call_count >= 2

    def test_display_summary_stats(self, preview_generator, console):
        """Test summary statistics display."""
        summary = PreviewSummary(
            total_assignments=5,
            successful_resolutions=4,
            failed_resolutions=1,
            users=3,
            groups=2,
            unique_permission_sets=3,
            unique_accounts=2,
        )

        preview_generator._display_summary_stats(summary)

        # Verify console.print was called
        assert console.print.call_count >= 2

    def test_display_assignment_table(self, preview_generator, console, sample_assignments):
        """Test assignment table display."""
        preview_generator._display_assignment_table(sample_assignments, "assign")

        # Verify console.print was called
        assert console.print.call_count >= 2

    def test_display_resolution_errors_with_errors(
        self, preview_generator, console, sample_assignments
    ):
        """Test resolution errors display when errors exist."""
        preview_generator._display_resolution_errors(sample_assignments)

        # Verify console.print was called (should display error table)
        assert console.print.call_count >= 2

    def test_display_resolution_errors_no_errors(self, preview_generator, console):
        """Test resolution errors display when no errors exist."""
        assignments = [
            {"principal_name": "john.doe", "resolution_success": True, "resolution_errors": []}
        ]

        preview_generator._display_resolution_errors(assignments)

        # Should not print anything when no errors
        console.print.assert_not_called()

    def test_generate_preview_report(self, preview_generator, sample_assignments):
        """Test complete preview report generation."""
        summary = preview_generator.generate_preview_report(sample_assignments, "assign")

        assert isinstance(summary, PreviewSummary)
        assert summary.total_assignments == 3
        assert summary.successful_resolutions == 2
        assert summary.failed_resolutions == 1

    @patch("src.awsideman.utils.bulk.preview.Confirm.ask")
    def test_prompt_user_confirmation_accept(self, mock_confirm, preview_generator):
        """Test user confirmation prompt when user accepts."""
        mock_confirm.return_value = True

        summary = PreviewSummary(
            total_assignments=2,
            successful_resolutions=2,
            failed_resolutions=0,
            users=1,
            groups=1,
            unique_permission_sets=2,
            unique_accounts=1,
        )

        result = preview_generator.prompt_user_confirmation("assign", summary)

        assert result is True
        mock_confirm.assert_called_once()

    @patch("src.awsideman.utils.bulk.preview.Confirm.ask")
    def test_prompt_user_confirmation_decline(self, mock_confirm, preview_generator):
        """Test user confirmation prompt when user declines."""
        mock_confirm.return_value = False

        summary = PreviewSummary(
            total_assignments=2,
            successful_resolutions=2,
            failed_resolutions=0,
            users=1,
            groups=1,
            unique_permission_sets=2,
            unique_accounts=1,
        )

        result = preview_generator.prompt_user_confirmation("assign", summary)

        assert result is False
        mock_confirm.assert_called_once()

    def test_prompt_user_confirmation_force_mode(self, preview_generator, console):
        """Test user confirmation prompt in force mode."""
        summary = PreviewSummary(
            total_assignments=2,
            successful_resolutions=2,
            failed_resolutions=0,
            users=1,
            groups=1,
            unique_permission_sets=2,
            unique_accounts=1,
        )

        result = preview_generator.prompt_user_confirmation("assign", summary, force=True)

        assert result is True
        console.print.assert_called_once()

    @patch("src.awsideman.utils.bulk.preview.Confirm.ask")
    def test_prompt_user_confirmation_with_errors(self, mock_confirm, preview_generator, console):
        """Test user confirmation prompt with resolution errors."""
        mock_confirm.return_value = True

        summary = PreviewSummary(
            total_assignments=3,
            successful_resolutions=2,
            failed_resolutions=1,
            users=2,
            groups=1,
            unique_permission_sets=2,
            unique_accounts=1,
        )

        result = preview_generator.prompt_user_confirmation("assign", summary)

        assert result is True
        mock_confirm.assert_called_once()
        # Should display warning panel
        assert console.print.call_count >= 2

    @patch("src.awsideman.utils.bulk.preview.Confirm.ask")
    def test_prompt_user_confirmation_keyboard_interrupt(
        self, mock_confirm, preview_generator, console
    ):
        """Test user confirmation prompt with keyboard interrupt."""
        mock_confirm.side_effect = KeyboardInterrupt()

        summary = PreviewSummary(
            total_assignments=2,
            successful_resolutions=2,
            failed_resolutions=0,
            users=1,
            groups=1,
            unique_permission_sets=2,
            unique_accounts=1,
        )

        result = preview_generator.prompt_user_confirmation("assign", summary)

        assert result is False
        console.print.assert_called_once()

    def test_prompt_user_confirmation_revoke_warning(self, preview_generator, console):
        """Test user confirmation prompt shows warning for revoke operations."""
        with patch("src.awsideman.utils.bulk.preview.Confirm.ask", return_value=True):
            summary = PreviewSummary(
                total_assignments=2,
                successful_resolutions=2,
                failed_resolutions=0,
                users=1,
                groups=1,
                unique_permission_sets=2,
                unique_accounts=1,
            )

            result = preview_generator.prompt_user_confirmation("revoke", summary)

            assert result is True
            # Should display revoke warning
            assert console.print.call_count >= 2

    def test_display_cancellation_message(self, preview_generator, console):
        """Test cancellation message display."""
        preview_generator.display_cancellation_message("assign")

        assert console.print.call_count >= 2

    def test_display_dry_run_message_success(self, preview_generator, console):
        """Test dry-run message display with successful validation."""
        summary = PreviewSummary(
            total_assignments=2,
            successful_resolutions=2,
            failed_resolutions=0,
            users=1,
            groups=1,
            unique_permission_sets=2,
            unique_accounts=1,
        )

        preview_generator.display_dry_run_message("assign", summary)

        assert console.print.call_count >= 2

    def test_display_dry_run_message_with_errors(self, preview_generator, console):
        """Test dry-run message display with resolution errors."""
        summary = PreviewSummary(
            total_assignments=3,
            successful_resolutions=2,
            failed_resolutions=1,
            users=2,
            groups=1,
            unique_permission_sets=2,
            unique_accounts=1,
        )

        preview_generator.display_dry_run_message("assign", summary)

        assert console.print.call_count >= 2

    @patch("src.awsideman.utils.bulk.processors.FileFormatDetector")
    def test_generate_preview_for_file(self, mock_detector, preview_generator):
        """Test preview generation from file."""
        # Mock file processor
        mock_processor = Mock()
        mock_processor.parse_assignments.return_value = [
            {
                "principal_name": "john.doe",
                "principal_type": "USER",
                "permission_set_name": "ReadOnly",
                "account_name": "Prod",
            }
        ]
        mock_detector.get_processor.return_value = mock_processor

        # Mock resolver
        mock_resolver = Mock(spec=ResourceResolver)
        mock_resolver.resolve_assignment.return_value = {
            "principal_name": "john.doe",
            "principal_type": "USER",
            "permission_set_name": "ReadOnly",
            "account_name": "Prod",
            "principal_id": "user-123",
            "permission_set_arn": "arn:aws:sso:::permissionSet/ins-123/ps-456",
            "account_id": "123456789012",
            "resolution_success": True,
            "resolution_errors": [],
        }

        file_path = Path("test.csv")
        assignments, summary = preview_generator.generate_preview_for_file(
            file_path, mock_resolver, "assign"
        )

        assert len(assignments) == 1
        assert isinstance(summary, PreviewSummary)
        assert summary.total_assignments == 1
        mock_detector.get_processor.assert_called_once_with(file_path)
        mock_processor.parse_assignments.assert_called_once()
        mock_resolver.resolve_assignment.assert_called_once()

    def test_validate_assignments_for_operation(self, preview_generator, sample_assignments):
        """Test assignment validation for operations."""
        valid_assignments = preview_generator.validate_assignments_for_operation(
            sample_assignments, "assign"
        )

        # Should return only assignments with successful resolution and required fields
        assert len(valid_assignments) == 2
        for assignment in valid_assignments:
            assert assignment["resolution_success"] is True
            assert assignment.get("principal_id")
            assert assignment.get("permission_set_arn")
            assert assignment.get("account_id")

    def test_validate_assignments_for_operation_empty(self, preview_generator):
        """Test assignment validation with empty list."""
        valid_assignments = preview_generator.validate_assignments_for_operation([], "assign")
        assert len(valid_assignments) == 0

    def test_validate_assignments_for_operation_all_invalid(self, preview_generator):
        """Test assignment validation with all invalid assignments."""
        invalid_assignments = [
            {
                "principal_name": "invalid.user",
                "resolution_success": False,
                "resolution_errors": ["User not found"],
            },
            {
                "principal_name": "another.user",
                "resolution_success": True,
                "principal_id": None,  # Missing required field
                "permission_set_arn": "arn:aws:sso:::permissionSet/ins-123/ps-456",
                "account_id": "123456789012",
            },
        ]

        valid_assignments = preview_generator.validate_assignments_for_operation(
            invalid_assignments, "assign"
        )

        assert len(valid_assignments) == 0

    def test_display_operation_summary_all_valid(self, preview_generator, console):
        """Test operation summary display with all valid assignments."""
        preview_generator.display_operation_summary("assign", 5, 5, 0)

        assert console.print.call_count >= 3

    def test_display_operation_summary_with_skipped(self, preview_generator, console):
        """Test operation summary display with skipped assignments."""
        preview_generator.display_operation_summary("assign", 5, 3, 2)

        assert console.print.call_count >= 3

    def test_display_operation_summary_revoke(self, preview_generator, console):
        """Test operation summary display for revoke operation."""
        preview_generator.display_operation_summary("revoke", 3, 3, 0)

        assert console.print.call_count >= 3


class TestPreviewGeneratorIntegration:
    """Integration tests for PreviewGenerator with real Rich console."""

    @pytest.fixture
    def real_console(self):
        """Create a real Rich console with string output for testing."""
        string_io = StringIO()
        return Console(file=string_io, width=120, legacy_windows=False)

    @pytest.fixture
    def preview_generator(self, real_console):
        """Create a PreviewGenerator with real console."""
        return PreviewGenerator(real_console)

    def test_generate_preview_report_real_output(self, preview_generator, real_console):
        """Test preview report generation with real Rich output."""
        assignments = [
            {
                "principal_name": "john.doe",
                "principal_type": "USER",
                "permission_set_name": "ReadOnlyAccess",
                "account_name": "Production",
                "principal_id": "user-123",
                "permission_set_arn": "arn:aws:sso:::permissionSet/ins-123/ps-456",
                "account_id": "123456789012",
                "resolution_success": True,
                "resolution_errors": [],
            }
        ]

        summary = preview_generator.generate_preview_report(assignments, "assign")

        # Get the output
        output = real_console.file.getvalue()

        # Verify summary is correct
        assert summary.total_assignments == 1
        assert summary.successful_resolutions == 1
        assert summary.failed_resolutions == 0

        # Verify output contains expected content
        assert "Preview Report" in output
        assert "john.doe" in output
        assert "ReadOnlyAccess" in output
        assert "Production" in output

    def test_display_resolution_errors_real_output(self, preview_generator, real_console):
        """Test resolution errors display with real Rich output."""
        assignments = [
            {
                "principal_name": "invalid.user",
                "principal_type": "USER",
                "permission_set_name": "AdminAccess",
                "account_name": "Production",
                "resolution_success": False,
                "resolution_errors": ["User invalid.user not found in Identity Store"],
            }
        ]

        preview_generator._display_resolution_errors(assignments)

        # Get the output
        output = real_console.file.getvalue()

        # Verify output contains error information
        assert "Resolution Errors" in output
        assert "invalid.user" in output
        assert "User invalid.user not found" in output
