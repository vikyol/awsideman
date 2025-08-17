"""Integration tests for backup CLI commands.

This module tests the backup CLI commands end-to-end, including:
- Creating backups with various options
- Listing backups with filtering
- Validating backup integrity
- Deleting backups with confirmation

Tests use mocked AWS services and storage backends to avoid
external dependencies while testing the complete CLI workflow.
"""

import tempfile
from datetime import datetime
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from src.awsideman.backup_restore.models import (
    BackupMetadata,
    BackupType,
    EncryptionMetadata,
    RetentionPolicy,
)
from src.awsideman.cli import app


@pytest.fixture
def cli_runner():
    """Create CLI runner for testing."""
    return CliRunner()


@pytest.fixture
def temp_backup_dir():
    """Create temporary directory for backup storage."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def mock_backup_metadata():
    """Create mock backup metadata for testing."""
    return BackupMetadata(
        backup_id="backup-20240117-143022-abc12345",
        timestamp=datetime(2024, 1, 17, 14, 30, 22),
        instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        backup_type=BackupType.FULL,
        version="1.0.0",
        source_account="123456789012",
        source_region="us-east-1",
        retention_policy=RetentionPolicy(),
        encryption_info=EncryptionMetadata(encrypted=True),
        resource_counts={"users": 150, "groups": 25, "permission_sets": 10, "assignments": 300},
        size_bytes=1024 * 1024,  # 1MB
        checksum="abc123def456",
    )


class TestBackupCreateCommand:
    """Test backup create command functionality."""

    @patch("src.awsideman.commands.backup.backup_operations.asyncio.run")
    @patch("src.awsideman.commands.backup.backup_operations.validate_profile")
    def test_create_full_backup_success(self, mock_validate_profile, mock_asyncio_run, cli_runner):
        """Test successful full backup creation."""
        # Setup mocks
        mock_validate_profile.return_value = (
            "default",
            {
                "sso_instance_arn": "arn:aws:sso:::instance/ssoins-1234567890abcdef",
                "account_id": "123456789012",
                "region": "us-east-1",
            },
        )

        mock_asyncio_run.return_value = {
            "success": True,
            "backup_id": "backup-20240117-143022-abc12345",
            "message": "Backup created successfully",
            "errors": [],
            "warnings": [],
            "duration": 45.2,
            "metadata": None,
        }

        # Run command
        result = cli_runner.invoke(app, ["backup", "create"])

        # Verify results
        assert result.exit_code == 0
        assert "✓ Backup created successfully!" in result.stdout
        assert "backup-20240117-143022-abc12345" in result.stdout
        assert "Duration: 45.20 seconds" in result.stdout

    def test_create_backup_invalid_type(self, cli_runner):
        """Test backup creation with invalid backup type."""
        result = cli_runner.invoke(app, ["backup", "create", "--type", "invalid"])

        assert result.exit_code == 1
        assert "Invalid backup type 'invalid'" in result.stdout

    def test_create_incremental_without_since(self, cli_runner):
        """Test incremental backup without since parameter."""
        result = cli_runner.invoke(app, ["backup", "create", "--type", "incremental"])

        assert result.exit_code == 1
        assert "Incremental backups require --since parameter" in result.stdout


class TestBackupListCommand:
    """Test backup list command functionality."""

    @patch("src.awsideman.commands.backup.backup_operations.asyncio.run")
    @patch("src.awsideman.commands.backup.backup_operations.validate_profile")
    def test_list_backups_success(
        self, mock_validate_profile, mock_asyncio_run, cli_runner, mock_backup_metadata
    ):
        """Test successful backup listing."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", {})
        mock_asyncio_run.return_value = {
            "success": True,
            "backups": [mock_backup_metadata.to_dict()],
            "count": 1,
            "filters": {},
        }

        # Run command
        result = cli_runner.invoke(app, ["backup", "list"])

        # Verify results
        assert result.exit_code == 0
        assert "backup-20240117-143022..." in result.stdout  # Truncated ID
        assert "2024-01-" in result.stdout  # Truncated date
        assert "14:30" in result.stdout  # Time part
        assert "FULL" in result.stdout
        assert "1024.0 KB" in result.stdout  # Size is in KB, not MB
        assert "Showing 1 backup(s)" in result.stdout

    def test_list_backups_invalid_type(self, cli_runner):
        """Test backup listing with invalid type filter."""
        result = cli_runner.invoke(app, ["backup", "list", "--type", "invalid"])

        assert result.exit_code == 1
        assert "Invalid backup type 'invalid'" in result.stdout


class TestBackupValidateCommand:
    """Test backup validate command functionality."""

    @patch("src.awsideman.commands.backup.backup_operations.asyncio.run")
    @patch("src.awsideman.commands.backup.backup_operations.validate_profile")
    def test_validate_backup_success(self, mock_validate_profile, mock_asyncio_run, cli_runner):
        """Test successful backup validation."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", {})
        mock_asyncio_run.return_value = {
            "success": True,
            "validation": {
                "is_valid": True,
                "errors": [],
                "warnings": [],
                "details": {
                    "checksum_verification": {"passed": True, "message": "Checksums match"},
                    "data_structure": {"passed": True, "message": "Structure is valid"},
                    "completeness": {"passed": True, "message": "All resources present"},
                },
            },
        }

        # Run command
        result = cli_runner.invoke(app, ["backup", "validate", "backup-20240117-143022-abc12345"])

        # Verify results
        assert result.exit_code == 0
        assert "✓ Backup validation passed!" in result.stdout
        assert "Backup is valid and complete" in result.stdout

    def test_validate_backup_empty_id(self, cli_runner):
        """Test validation with empty backup ID."""
        result = cli_runner.invoke(app, ["backup", "validate", ""])

        assert result.exit_code == 1
        assert "Backup ID cannot be empty" in result.stdout


class TestBackupDeleteCommand:
    """Test backup delete command functionality."""

    @patch("src.awsideman.commands.backup.backup_operations.asyncio.run")
    @patch("src.awsideman.commands.backup.backup_operations.validate_profile")
    def test_delete_backup_with_yes_flag(
        self, mock_validate_profile, mock_asyncio_run, cli_runner, mock_backup_metadata
    ):
        """Test backup deletion with --yes flag (no confirmation)."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", {})
        mock_asyncio_run.side_effect = [
            {"success": True, "metadata": mock_backup_metadata},  # First call for metadata
            {"success": True},  # Second call for deletion
        ]

        # Run command
        result = cli_runner.invoke(
            app, ["backup", "delete", "backup-20240117-143022-abc12345", "--yes"]
        )

        # Verify results
        assert result.exit_code == 0
        assert "✓ Backup deleted successfully!" in result.stdout

    def test_delete_backup_empty_id(self, cli_runner):
        """Test deletion with empty backup ID."""
        result = cli_runner.invoke(app, ["backup", "delete", ""])

        assert result.exit_code == 1
        assert "Backup ID cannot be empty" in result.stdout


class TestBackupCommandIntegration:
    """Test integration scenarios across backup commands."""

    @patch("src.awsideman.commands.backup.backup_operations.validate_profile")
    def test_invalid_storage_backend_across_commands(self, mock_validate_profile, cli_runner):
        """Test invalid storage backend handling across all commands."""
        mock_validate_profile.return_value = ("default", {})

        commands_to_test = [
            ["backup", "create", "--storage", "invalid"],
            ["backup", "list", "--storage", "invalid"],
            ["backup", "validate", "test-backup", "--storage", "invalid"],
            ["backup", "delete", "test-backup", "--storage", "invalid"],
        ]

        for command in commands_to_test:
            result = cli_runner.invoke(app, command)
            assert result.exit_code == 1
            assert "Invalid storage backend 'invalid'" in result.stdout

    @patch("src.awsideman.commands.backup.backup_operations.validate_profile")
    def test_invalid_output_format_across_commands(self, mock_validate_profile, cli_runner):
        """Test invalid output format handling across applicable commands."""
        mock_validate_profile.return_value = ("default", {})

        commands_to_test = [
            ["backup", "create", "--format", "invalid"],
            ["backup", "list", "--format", "invalid"],
            ["backup", "validate", "test-backup", "--format", "invalid"],
        ]

        for command in commands_to_test:
            result = cli_runner.invoke(app, command)
            assert result.exit_code == 1
            assert "Invalid output format 'invalid'" in result.stdout
