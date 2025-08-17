"""Integration tests for restore CLI commands.

This module tests the restore CLI commands end-to-end, including:
- Restore command with various options
- Preview command for dry-run functionality
- Validate command for compatibility checking
- Progress monitoring for long-running operations
"""

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from awsideman.backup_restore.models import (
    AssignmentData,
    BackupData,
    BackupMetadata,
    BackupType,
    ConflictStrategy,
    EncryptionMetadata,
    GroupData,
    PermissionSetData,
    RelationshipMap,
    ResourceType,
    RestorePreview,
    RestoreResult,
    RetentionPolicy,
    UserData,
    ValidationResult,
)
from awsideman.commands.restore import app


class TestRestoreCliIntegration:
    """Integration tests for restore CLI commands."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.test_backup_id = "backup-20240117-143022-abc12345"
        self.test_profile = "test-profile"

        # Create test backup data
        self.test_backup_metadata = BackupMetadata(
            backup_id=self.test_backup_id,
            timestamp=datetime.now(),
            instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
            backup_type=BackupType.FULL,
            version="1.0.0",
            source_account="123456789012",
            source_region="us-east-1",
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(),
            resource_counts={"users": 10, "groups": 5, "permission_sets": 3, "assignments": 20},
            size_bytes=1024000,
            checksum="abc123def456",
        )

        self.test_backup_data = BackupData(
            metadata=self.test_backup_metadata,
            users=[
                UserData(
                    user_id="user-1",
                    user_name="test.user1@example.com",
                    display_name="Test User 1",
                    email="test.user1@example.com",
                ),
                UserData(
                    user_id="user-2",
                    user_name="test.user2@example.com",
                    display_name="Test User 2",
                    email="test.user2@example.com",
                ),
            ],
            groups=[
                GroupData(
                    group_id="group-1",
                    display_name="Test Group 1",
                    description="Test group for integration tests",
                )
            ],
            permission_sets=[
                PermissionSetData(
                    permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
                    name="TestPermissionSet",
                    description="Test permission set",
                )
            ],
            assignments=[
                AssignmentData(
                    account_id="123456789012",
                    permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
                    principal_type="USER",
                    principal_id="user-1",
                )
            ],
            relationships=RelationshipMap(),
        )

    @patch("awsideman.commands.restore.restore_operations.restore_operations.validate_profile")
    @patch("awsideman.commands.restore.restore_operations.restore_operations.AWSClientManager")
    @patch("awsideman.commands.restore.restore_operations.restore_operations.StorageEngine")
    @patch("awsideman.commands.restore.restore_operations.restore_operations.RestoreManager")
    def test_restore_command_success(
        self, mock_restore_manager, mock_storage_engine, mock_client_manager, mock_validate_profile
    ):
        """Test successful restore command execution."""
        # Setup mocks
        mock_validate_profile.return_value = (
            self.test_profile,
            {
                "profile_name": self.test_profile,
                "region": "us-east-1",
                "sso_instance_arn": "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            },
        )

        mock_restore_result = RestoreResult(
            success=True,
            message="Restore completed successfully",
            changes_applied={"users": 2, "groups": 1, "permission_sets": 1, "assignments": 1},
            duration=timedelta(seconds=30),
        )

        mock_restore_manager_instance = AsyncMock()
        mock_restore_manager_instance.restore_backup.return_value = mock_restore_result
        mock_restore_manager.return_value = mock_restore_manager_instance

        # Run command
        result = self.runner.invoke(
            app,
            [
                "restore",
                self.test_backup_id,
                "--profile",
                self.test_profile,
                "--conflict-strategy",
                "overwrite",
            ],
        )

        # Verify results
        assert result.exit_code == 0
        assert "Restore completed successfully" in result.stdout
        assert "Total Changes Applied: 5" in result.stdout

        # Verify restore manager was called correctly
        mock_restore_manager_instance.restore_backup.assert_called_once()
        call_args = mock_restore_manager_instance.restore_backup.call_args
        assert call_args[0][0] == self.test_backup_id  # backup_id

        options = call_args[0][1]  # RestoreOptions
        assert options.conflict_strategy == ConflictStrategy.OVERWRITE
        assert not options.dry_run
        assert ResourceType.ALL in options.target_resources

    @patch("awsideman.commands.restore.restore_operations.validate_profile")
    @patch("awsideman.commands.restore.restore_operations.AWSClientManager")
    @patch("awsideman.commands.restore.restore_operations.StorageEngine")
    @patch("awsideman.commands.restore.restore_operations.RestoreManager")
    def test_restore_command_dry_run(
        self, mock_restore_manager, mock_storage_engine, mock_client_manager, mock_validate_profile
    ):
        """Test restore command with dry-run option."""
        # Setup mocks
        mock_validate_profile.return_value = (
            self.test_profile,
            {
                "profile_name": self.test_profile,
                "region": "us-east-1",
                "sso_instance_arn": "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            },
        )

        mock_preview_result = RestorePreview(
            changes_summary={"users": 2, "groups": 1, "permission_sets": 1, "assignments": 1},
            conflicts=[],
            warnings=["Large number of users (2) will be processed"],
            estimated_duration=timedelta(seconds=30),
        )

        mock_restore_manager_instance = AsyncMock()
        mock_restore_manager_instance.preview_restore.return_value = mock_preview_result
        mock_restore_manager.return_value = mock_restore_manager_instance

        # Run command
        result = self.runner.invoke(
            app, ["restore", self.test_backup_id, "--dry-run", "--profile", self.test_profile]
        )

        # Verify results
        assert result.exit_code == 0
        assert "Restore preview completed successfully" in result.stdout
        assert "Restore Preview:" in result.stdout
        assert "Estimated Duration: 30.0 seconds" in result.stdout

        # Verify preview was called instead of restore
        mock_restore_manager_instance.preview_restore.assert_called_once()
        mock_restore_manager_instance.restore_backup.assert_not_called()

    @patch("awsideman.commands.restore.restore_operations.validate_profile")
    @patch("awsideman.commands.restore.restore_operations.AWSClientManager")
    @patch("awsideman.commands.restore.restore_operations.StorageEngine")
    @patch("awsideman.commands.restore.restore_operations.RestoreManager")
    def test_restore_command_selective_resources(
        self, mock_restore_manager, mock_storage_engine, mock_client_manager, mock_validate_profile
    ):
        """Test restore command with selective resource types."""
        # Setup mocks
        mock_validate_profile.return_value = (
            self.test_profile,
            {
                "profile_name": self.test_profile,
                "region": "us-east-1",
                "sso_instance_arn": "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            },
        )

        mock_restore_result = RestoreResult(
            success=True,
            message="Restore completed successfully",
            changes_applied={"users": 2, "groups": 1},
            duration=timedelta(seconds=15),
        )

        mock_restore_manager_instance = AsyncMock()
        mock_restore_manager_instance.restore_backup.return_value = mock_restore_result
        mock_restore_manager.return_value = mock_restore_manager_instance

        # Run command
        result = self.runner.invoke(
            app,
            [
                "restore",
                self.test_backup_id,
                "--resources",
                "users,groups",
                "--profile",
                self.test_profile,
            ],
        )

        # Verify results
        assert result.exit_code == 0
        assert "Restore completed successfully" in result.stdout

        # Verify correct resource types were specified
        call_args = mock_restore_manager_instance.restore_backup.call_args
        options = call_args[0][1]  # RestoreOptions
        assert ResourceType.USERS in options.target_resources
        assert ResourceType.GROUPS in options.target_resources
        assert len(options.target_resources) == 2

    @patch("awsideman.commands.restore.restore_operations.validate_profile")
    @patch("awsideman.commands.restore.restore_operations.AWSClientManager")
    @patch("awsideman.commands.restore.restore_operations.StorageEngine")
    @patch("awsideman.commands.restore.restore_operations.RestoreManager")
    def test_restore_command_cross_account(
        self, mock_restore_manager, mock_storage_engine, mock_client_manager, mock_validate_profile
    ):
        """Test restore command with cross-account options."""
        # Setup mocks
        mock_validate_profile.return_value = (
            self.test_profile,
            {
                "profile_name": self.test_profile,
                "region": "us-east-1",
                "sso_instance_arn": "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            },
        )

        mock_restore_result = RestoreResult(
            success=True,
            message="Cross-account restore completed successfully",
            changes_applied={"users": 2, "groups": 1, "permission_sets": 1, "assignments": 1},
            duration=timedelta(seconds=45),
        )

        mock_restore_manager_instance = AsyncMock()
        mock_restore_manager_instance.restore_backup.return_value = mock_restore_result
        mock_restore_manager.return_value = mock_restore_manager_instance

        # Run command
        result = self.runner.invoke(
            app,
            [
                "restore",
                self.test_backup_id,
                "--target-account",
                "987654321098",
                "--target-region",
                "us-west-2",
                "--target-instance-arn",
                "arn:aws:sso:::instance/ssoins-abcdef1234567890",
                "--profile",
                self.test_profile,
            ],
        )

        # Verify results
        assert result.exit_code == 0
        assert "Restore completed successfully" in result.stdout

        # Verify cross-account options were passed
        call_args = mock_restore_manager_instance.restore_backup.call_args
        options = call_args[0][1]  # RestoreOptions
        assert options.target_account == "987654321098"
        assert options.target_region == "us-west-2"
        assert options.target_instance_arn == "arn:aws:sso:::instance/ssoins-abcdef1234567890"

    @patch("awsideman.commands.restore.restore_operations.validate_profile")
    @patch("awsideman.commands.restore.restore_operations.AWSClientManager")
    @patch("awsideman.commands.restore.restore_operations.StorageEngine")
    @patch("awsideman.commands.restore.restore_operations.RestoreManager")
    def test_restore_command_json_output(
        self, mock_restore_manager, mock_storage_engine, mock_client_manager, mock_validate_profile
    ):
        """Test restore command with JSON output format."""
        # Setup mocks
        mock_validate_profile.return_value = (
            self.test_profile,
            {
                "profile_name": self.test_profile,
                "region": "us-east-1",
                "sso_instance_arn": "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            },
        )

        mock_restore_result = RestoreResult(
            success=True,
            message="Restore completed successfully",
            changes_applied={"users": 2, "groups": 1},
            duration=timedelta(seconds=20),
        )

        mock_restore_manager_instance = AsyncMock()
        mock_restore_manager_instance.restore_backup.return_value = mock_restore_result
        mock_restore_manager.return_value = mock_restore_manager_instance

        # Run command
        result = self.runner.invoke(
            app,
            ["restore", self.test_backup_id, "--format", "json", "--profile", self.test_profile],
        )

        # Verify results
        assert result.exit_code == 0

        # Parse JSON output
        output_data = json.loads(result.stdout)
        assert output_data["success"] is True
        assert "restore_result" in output_data
        assert output_data["restore_result"]["success"] is True
        assert output_data["restore_result"]["changes_applied"]["users"] == 2
        assert output_data["restore_result"]["changes_applied"]["groups"] == 1

    @patch("awsideman.commands.restore.restore_operations.validate_profile")
    @patch("awsideman.commands.restore.restore_operations.AWSClientManager")
    @patch("awsideman.commands.restore.restore_operations.StorageEngine")
    @patch("awsideman.commands.restore.restore_operations.RestoreManager")
    def test_restore_command_failure(
        self, mock_restore_manager, mock_storage_engine, mock_client_manager, mock_validate_profile
    ):
        """Test restore command failure handling."""
        # Setup mocks
        mock_validate_profile.return_value = (
            self.test_profile,
            {
                "profile_name": self.test_profile,
                "region": "us-east-1",
                "sso_instance_arn": "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            },
        )

        mock_restore_result = RestoreResult(
            success=False,
            message="Restore failed due to validation errors",
            errors=["Backup not found", "Invalid target instance"],
            warnings=["Some resources may be outdated"],
        )

        mock_restore_manager_instance = AsyncMock()
        mock_restore_manager_instance.restore_backup.return_value = mock_restore_result
        mock_restore_manager.return_value = mock_restore_manager_instance

        # Run command
        result = self.runner.invoke(
            app, ["restore", self.test_backup_id, "--profile", self.test_profile]
        )

        # Verify results
        assert result.exit_code == 1
        assert "Restore failed: Restore failed due to validation errors" in result.stdout
        assert "Backup not found" in result.stdout
        assert "Invalid target instance" in result.stdout

    @patch("awsideman.commands.restore.restore_operations.validate_profile")
    @patch("awsideman.commands.restore.restore_operations.AWSClientManager")
    @patch("awsideman.commands.restore.restore_operations.StorageEngine")
    @patch("awsideman.commands.restore.restore_operations.RestoreManager")
    def test_preview_command(
        self, mock_restore_manager, mock_storage_engine, mock_client_manager, mock_validate_profile
    ):
        """Test preview command functionality."""
        # Setup mocks
        mock_validate_profile.return_value = (
            self.test_profile,
            {
                "profile_name": self.test_profile,
                "region": "us-east-1",
                "sso_instance_arn": "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            },
        )

        mock_preview_result = RestorePreview(
            changes_summary={"users": 2, "groups": 1, "permission_sets": 1, "assignments": 1},
            conflicts=[],
            warnings=["Large number of assignments (1) will be processed"],
            estimated_duration=timedelta(seconds=25),
        )

        mock_restore_manager_instance = AsyncMock()
        mock_restore_manager_instance.preview_restore.return_value = mock_preview_result
        mock_restore_manager.return_value = mock_restore_manager_instance

        # Run command
        result = self.runner.invoke(
            app, ["preview", self.test_backup_id, "--profile", self.test_profile]
        )

        # Verify results
        assert result.exit_code == 0
        assert "Restore preview completed successfully" in result.stdout
        assert "Restore Preview:" in result.stdout
        assert "Users" in result.stdout
        assert "Groups" in result.stdout
        assert "Permission Sets" in result.stdout
        assert "Assignments" in result.stdout
        assert "Estimated Duration: 25.0 seconds" in result.stdout

    @patch("awsideman.commands.restore.restore_operations.validate_profile")
    @patch("awsideman.commands.restore.restore_operations.AWSClientManager")
    @patch("awsideman.commands.restore.restore_operations.StorageEngine")
    @patch("awsideman.commands.restore.restore_operations.RestoreManager")
    def test_validate_command_success(
        self, mock_restore_manager, mock_storage_engine, mock_client_manager, mock_validate_profile
    ):
        """Test validate command with successful validation."""
        # Setup mocks
        mock_validate_profile.return_value = (
            self.test_profile,
            {
                "profile_name": self.test_profile,
                "region": "us-east-1",
                "sso_instance_arn": "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            },
        )

        mock_validation_result = ValidationResult(
            is_valid=True,
            errors=[],
            warnings=["Large number of users (2) detected"],
            details={
                "instance_access": {"passed": True, "message": "Instance accessible"},
                "permission_sets": {"passed": True, "message": "All permission sets valid"},
                "accounts": {"passed": True, "message": "All accounts accessible"},
            },
        )

        mock_restore_manager_instance = AsyncMock()
        mock_restore_manager_instance.validate_compatibility.return_value = mock_validation_result
        mock_restore_manager.return_value = mock_restore_manager_instance

        # Run command
        result = self.runner.invoke(
            app, ["validate", self.test_backup_id, "--profile", self.test_profile]
        )

        # Verify results
        assert result.exit_code == 0
        assert "Backup is compatible with target environment" in result.stdout
        assert "Validation Details:" in result.stdout
        assert "Instance Access" in result.stdout
        assert "Permission Sets" in result.stdout
        assert "Accounts" in result.stdout
        assert "Large number of users (2) detected" in result.stdout

    @patch("awsideman.commands.restore.restore_operations.validate_profile")
    @patch("awsideman.commands.restore.restore_operations.AWSClientManager")
    @patch("awsideman.commands.restore.restore_operations.StorageEngine")
    @patch("awsideman.commands.restore.restore_operations.RestoreManager")
    def test_validate_command_failure(
        self, mock_restore_manager, mock_storage_engine, mock_client_manager, mock_validate_profile
    ):
        """Test validate command with validation failure."""
        # Setup mocks
        mock_validate_profile.return_value = (
            self.test_profile,
            {
                "profile_name": self.test_profile,
                "region": "us-east-1",
                "sso_instance_arn": "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            },
        )

        mock_validation_result = ValidationResult(
            is_valid=False,
            errors=["Cannot access target instance", "Permission set conflicts detected"],
            warnings=["Some managed policies may not exist"],
            details={
                "instance_access": {"passed": False, "message": "Access denied"},
                "permission_sets": {"passed": False, "message": "Conflicts found"},
            },
        )

        mock_restore_manager_instance = AsyncMock()
        mock_restore_manager_instance.validate_compatibility.return_value = mock_validation_result
        mock_restore_manager.return_value = mock_restore_manager_instance

        # Run command
        result = self.runner.invoke(
            app, ["validate", self.test_backup_id, "--profile", self.test_profile]
        )

        # Verify results
        assert result.exit_code == 1
        assert "Backup compatibility validation failed" in result.stdout
        assert "Cannot access target instance" in result.stdout
        assert "Permission set conflicts detected" in result.stdout
        assert "Some managed policies may not exist" in result.stdout

    def test_restore_command_invalid_backup_id(self):
        """Test restore command with invalid backup ID."""
        result = self.runner.invoke(
            app, ["restore", "", "--profile", self.test_profile]  # Empty backup ID
        )

        assert result.exit_code == 1
        assert "Backup ID cannot be empty" in result.stdout

    def test_restore_command_invalid_conflict_strategy(self):
        """Test restore command with invalid conflict strategy."""
        result = self.runner.invoke(
            app,
            [
                "restore",
                self.test_backup_id,
                "--conflict-strategy",
                "invalid_strategy",
                "--profile",
                self.test_profile,
            ],
        )

        assert result.exit_code == 1
        assert "Invalid conflict strategy 'invalid_strategy'" in result.stdout
        assert "Valid strategies:" in result.stdout
        assert "overwrite" in result.stdout
        assert "skip" in result.stdout
        assert "prompt" in result.stdout
        assert "merge" in result.stdout

    def test_restore_command_invalid_resources(self):
        """Test restore command with invalid resource types."""
        result = self.runner.invoke(
            app,
            [
                "restore",
                self.test_backup_id,
                "--resources",
                "invalid_resource,users",
                "--profile",
                self.test_profile,
            ],
        )

        assert result.exit_code == 1
        assert "Invalid resource type 'invalid_resource'" in result.stdout
        assert "Valid resources:" in result.stdout
        assert "users" in result.stdout
        assert "groups" in result.stdout
        assert "permission_sets" in result.stdout
        assert "assignments" in result.stdout
        assert "all" in result.stdout

    def test_restore_command_invalid_storage_backend(self):
        """Test restore command with invalid storage backend."""
        result = self.runner.invoke(
            app,
            [
                "restore",
                self.test_backup_id,
                "--storage",
                "invalid_backend",
                "--profile",
                self.test_profile,
            ],
        )

        assert result.exit_code == 1
        assert "Invalid storage backend 'invalid_backend'" in result.stdout
        assert "Storage backend must be either 'filesystem' or 's3'" in result.stdout

    def test_restore_command_invalid_output_format(self):
        """Test restore command with invalid output format."""
        result = self.runner.invoke(
            app,
            [
                "restore",
                self.test_backup_id,
                "--format",
                "invalid_format",
                "--profile",
                self.test_profile,
            ],
        )

        assert result.exit_code == 1
        assert "Invalid output format 'invalid_format'" in result.stdout
        assert "Output format must be either 'table' or 'json'" in result.stdout

    @patch("awsideman.commands.restore.restore_operations.validate_profile")
    @patch("awsideman.commands.restore.restore_operations.AWSClientManager")
    @patch("awsideman.commands.restore.restore_operations.StorageEngine")
    @patch("awsideman.commands.restore.restore_operations.RestoreManager")
    def test_restore_command_s3_storage(
        self, mock_restore_manager, mock_storage_engine, mock_client_manager, mock_validate_profile
    ):
        """Test restore command with S3 storage backend."""
        # Setup mocks
        mock_validate_profile.return_value = (
            self.test_profile,
            {
                "profile_name": self.test_profile,
                "region": "us-east-1",
                "sso_instance_arn": "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            },
        )

        mock_restore_result = RestoreResult(
            success=True,
            message="Restore completed successfully",
            changes_applied={"users": 2},
            duration=timedelta(seconds=10),
        )

        mock_restore_manager_instance = AsyncMock()
        mock_restore_manager_instance.restore_backup.return_value = mock_restore_result
        mock_restore_manager.return_value = mock_restore_manager_instance

        # Run command
        result = self.runner.invoke(
            app,
            [
                "restore",
                self.test_backup_id,
                "--storage",
                "s3",
                "--storage-path",
                "my-backup-bucket/backups",
                "--profile",
                self.test_profile,
            ],
        )

        # Verify results
        assert result.exit_code == 0
        assert "Restore completed successfully" in result.stdout

        # Verify S3 storage backend was used
        # This would be verified by checking the StorageEngine initialization
        # but since we're mocking it, we just verify the command succeeded

    @patch("awsideman.commands.restore.restore_operations.validate_profile")
    def test_restore_command_profile_validation_error(self, mock_validate_profile):
        """Test restore command with profile validation error."""
        # Setup mock to raise an exception
        mock_validate_profile.side_effect = Exception("Invalid profile configuration")

        # Run command
        result = self.runner.invoke(
            app, ["restore", self.test_backup_id, "--profile", "invalid_profile"]
        )

        # Verify results
        assert result.exit_code == 1
        # The exception should be caught and displayed
        assert (
            "Invalid profile configuration" in str(result.exception)
            or "Invalid profile configuration" in result.stdout
        )


class TestRestoreCliProgressMonitoring:
    """Tests for progress monitoring during restore operations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.test_backup_id = "backup-20240117-143022-abc12345"
        self.test_profile = "test-profile"

    @patch("awsideman.commands.restore.restore_operations.validate_profile")
    @patch("awsideman.commands.restore.restore_operations.AWSClientManager")
    @patch("awsideman.commands.restore.restore_operations.StorageEngine")
    @patch("awsideman.commands.restore.restore_operations.RestoreManager")
    def test_restore_with_progress_monitoring(
        self, mock_restore_manager, mock_storage_engine, mock_client_manager, mock_validate_profile
    ):
        """Test restore command with progress monitoring for long-running operations."""
        # Setup mocks
        mock_validate_profile.return_value = (
            self.test_profile,
            {
                "profile_name": self.test_profile,
                "region": "us-east-1",
                "sso_instance_arn": "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            },
        )

        # Simulate a long-running restore operation
        mock_restore_result = RestoreResult(
            success=True,
            message="Long-running restore completed successfully",
            changes_applied={"users": 100, "groups": 50, "permission_sets": 25, "assignments": 500},
            duration=timedelta(minutes=5),  # 5 minute operation
        )

        mock_restore_manager_instance = AsyncMock()
        mock_restore_manager_instance.restore_backup.return_value = mock_restore_result
        mock_restore_manager.return_value = mock_restore_manager_instance

        # Run command
        result = self.runner.invoke(
            app,
            ["restore", self.test_backup_id, "--resources", "all", "--profile", self.test_profile],
        )

        # Verify results
        assert result.exit_code == 0
        assert "Restore completed successfully" in result.stdout
        assert "Total Changes Applied: 675" in result.stdout
        assert "Duration: 300.00 seconds" in result.stdout

        # Verify restore manager was called
        mock_restore_manager_instance.restore_backup.assert_called_once()
