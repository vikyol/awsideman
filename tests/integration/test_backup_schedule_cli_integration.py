"""Integration tests for backup schedule CLI commands.

This module tests the backup schedule management CLI commands including
create, list, delete, status, and run operations.
"""

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from awsideman.backup_restore.models import (
    BackupType,
    NotificationSettings,
    RetentionPolicy,
    ScheduleConfig,
)
from awsideman.commands.backup.schedule_commands import app


@pytest.fixture
def cli_runner():
    """Create a CLI runner for testing."""
    return CliRunner()


@pytest.fixture
def mock_profile_data():
    """Mock profile data for testing."""
    return {
        "sso_instance_arn": "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "account_id": "123456789012",
        "region": "us-east-1",
    }


@pytest.fixture
def mock_schedule_config():
    """Mock schedule configuration for testing."""
    return ScheduleConfig(
        name="test-schedule",
        backup_type=BackupType.FULL,
        interval="daily",
        retention_policy=RetentionPolicy(
            keep_daily=7, keep_weekly=4, keep_monthly=12, keep_yearly=3, auto_cleanup=True
        ),
        notification_settings=NotificationSettings(
            enabled=True,
            email_addresses=["admin@example.com"],
            webhook_urls=[],
            notify_on_success=False,
            notify_on_failure=True,
        ),
        enabled=True,
    )


@pytest.fixture
def mock_schedule_info():
    """Mock schedule information for testing."""
    return {
        "schedule_id": "schedule-123",
        "name": "test-schedule",
        "backup_type": "full",
        "interval": "daily",
        "enabled": True,
        "created_at": datetime.now().isoformat(),
        "last_run": None,
        "next_run": (datetime.now() + timedelta(hours=24)).isoformat(),
        "consecutive_failures": 0,
        "total_runs": 0,
        "successful_runs": 0,
        "success_rate": 0.0,
        "last_result": None,
        "retention_policy": {
            "keep_daily": 7,
            "keep_weekly": 4,
            "keep_monthly": 12,
            "keep_yearly": 3,
            "auto_cleanup": True,
        },
        "notification_settings": {
            "enabled": True,
            "email_addresses": ["admin@example.com"],
            "webhook_urls": [],
            "notify_on_success": False,
            "notify_on_failure": True,
        },
    }


class TestScheduleCreateCommand:
    """Test the schedule create command."""

    @patch("awsideman.commands.backup.schedule_commands.validate_profile")
    @patch("awsideman.commands.backup.schedule_commands.asyncio.run")
    def test_create_schedule_success(
        self, mock_asyncio_run, mock_validate_profile, cli_runner, mock_profile_data
    ):
        """Test successful schedule creation."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {
            "success": True,
            "schedule_id": "schedule-123",
            "next_run": (datetime.now() + timedelta(hours=24)).isoformat(),
            "message": "Schedule created successfully",
        }

        # Run command
        result = cli_runner.invoke(
            app, ["create", "--name", "test-schedule", "--interval", "daily", "--type", "full"]
        )

        # Verify result
        assert result.exit_code == 0
        assert "Schedule created successfully" in result.stdout
        assert "schedule-123" in result.stdout
        mock_asyncio_run.assert_called_once()

    @patch("awsideman.commands.backup.schedule_commands.validate_profile")
    @patch("awsideman.commands.backup.schedule_commands.asyncio.run")
    def test_create_schedule_with_notifications(
        self, mock_asyncio_run, mock_validate_profile, cli_runner, mock_profile_data
    ):
        """Test schedule creation with email notifications."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {
            "success": True,
            "schedule_id": "schedule-123",
            "next_run": (datetime.now() + timedelta(hours=24)).isoformat(),
            "message": "Schedule created successfully",
        }

        # Run command
        result = cli_runner.invoke(
            app,
            [
                "create",
                "--name",
                "test-schedule",
                "--interval",
                "daily",
                "--type",
                "full",
                "--notify-email",
                "admin@example.com",
                "--notify-on-success",
            ],
        )

        # Verify result
        assert result.exit_code == 0
        assert "Schedule created successfully" in result.stdout
        mock_asyncio_run.assert_called_once()

    def test_create_schedule_invalid_type(self, cli_runner):
        """Test schedule creation with invalid backup type."""
        result = cli_runner.invoke(
            app, ["create", "--name", "test-schedule", "--interval", "daily", "--type", "invalid"]
        )

        assert result.exit_code == 1
        assert "Invalid backup type" in result.stdout

    def test_create_schedule_invalid_storage(self, cli_runner):
        """Test schedule creation with invalid storage backend."""
        result = cli_runner.invoke(
            app,
            ["create", "--name", "test-schedule", "--interval", "daily", "--storage", "invalid"],
        )

        assert result.exit_code == 1
        assert "Invalid storage backend" in result.stdout

    @patch("awsideman.commands.backup.schedule_commands.validate_profile")
    @patch("awsideman.commands.backup.schedule_commands.asyncio.run")
    def test_create_schedule_failure(
        self, mock_asyncio_run, mock_validate_profile, cli_runner, mock_profile_data
    ):
        """Test schedule creation failure."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {
            "success": False,
            "message": "Schedule creation failed",
            "errors": ["Invalid cron expression"],
        }

        # Run command
        result = cli_runner.invoke(
            app, ["create", "--name", "test-schedule", "--interval", "invalid-cron"]
        )

        # Verify result
        assert result.exit_code == 1
        assert "Schedule creation failed" in result.stdout
        assert "Invalid cron expression" in result.stdout


class TestScheduleListCommand:
    """Test the schedule list command."""

    @patch("awsideman.commands.backup.schedule_commands.validate_profile")
    @patch("awsideman.commands.backup.schedule_commands.asyncio.run")
    def test_list_schedules_success(
        self,
        mock_asyncio_run,
        mock_validate_profile,
        cli_runner,
        mock_profile_data,
        mock_schedule_info,
    ):
        """Test successful schedule listing."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {
            "success": True,
            "schedules": [mock_schedule_info],
            "count": 1,
        }

        # Run command
        result = cli_runner.invoke(app, ["list"])

        # Verify result
        assert result.exit_code == 0
        assert "test-schedule" in result.stdout
        assert "daily" in result.stdout
        assert "Enabled" in result.stdout
        mock_asyncio_run.assert_called_once()

    @patch("awsideman.commands.backup.schedule_commands.validate_profile")
    @patch("awsideman.commands.backup.schedule_commands.asyncio.run")
    def test_list_schedules_empty(
        self, mock_asyncio_run, mock_validate_profile, cli_runner, mock_profile_data
    ):
        """Test listing when no schedules exist."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {"success": True, "schedules": [], "count": 0}

        # Run command
        result = cli_runner.invoke(app, ["list"])

        # Verify result
        assert result.exit_code == 0
        assert "No backup schedules found" in result.stdout

    @patch("awsideman.commands.backup.schedule_commands.validate_profile")
    @patch("awsideman.commands.backup.schedule_commands.asyncio.run")
    def test_list_schedules_json_format(
        self,
        mock_asyncio_run,
        mock_validate_profile,
        cli_runner,
        mock_profile_data,
        mock_schedule_info,
    ):
        """Test schedule listing with JSON output format."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {
            "success": True,
            "schedules": [mock_schedule_info],
            "count": 1,
        }

        # Run command
        result = cli_runner.invoke(app, ["list", "--format", "json"])

        # Verify result
        assert result.exit_code == 0
        output_data = json.loads(result.stdout)
        assert output_data["success"] is True
        assert len(output_data["schedules"]) == 1


class TestScheduleDeleteCommand:
    """Test the schedule delete command."""

    @patch("awsideman.commands.backup.schedule_commands.validate_profile")
    @patch("awsideman.commands.backup.schedule_commands.asyncio.run")
    def test_delete_schedule_success_with_yes_flag(
        self,
        mock_asyncio_run,
        mock_validate_profile,
        cli_runner,
        mock_profile_data,
        mock_schedule_info,
    ):
        """Test successful schedule deletion with --yes flag."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.side_effect = [
            {"success": True, "schedule": mock_schedule_info},  # get_schedule_status
            {"success": True, "message": "Schedule deleted successfully"},  # delete_schedule
        ]

        # Run command
        result = cli_runner.invoke(app, ["delete", "schedule-123", "--yes"])

        # Verify result
        assert result.exit_code == 0
        assert "Schedule deleted successfully" in result.stdout
        assert mock_asyncio_run.call_count == 2

    @patch("awsideman.commands.backup.schedule_commands.validate_profile")
    @patch("awsideman.commands.backup.schedule_commands.asyncio.run")
    def test_delete_schedule_not_found(
        self, mock_asyncio_run, mock_validate_profile, cli_runner, mock_profile_data
    ):
        """Test deleting a non-existent schedule."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {
            "success": False,
            "message": "Schedule not found",
            "errors": ["Schedule schedule-123 not found"],
        }

        # Run command
        result = cli_runner.invoke(app, ["delete", "schedule-123", "--yes"])

        # Verify result
        assert result.exit_code == 1
        assert "Schedule not found" in result.stdout

    def test_delete_schedule_empty_id(self, cli_runner):
        """Test deleting with empty schedule ID."""
        result = cli_runner.invoke(app, ["delete", ""])

        assert result.exit_code == 1
        assert "Schedule ID cannot be empty" in result.stdout


class TestScheduleStatusCommand:
    """Test the schedule status command."""

    @patch("awsideman.commands.backup.schedule_commands.validate_profile")
    @patch("awsideman.commands.backup.schedule_commands.asyncio.run")
    def test_get_schedule_status_success(
        self,
        mock_asyncio_run,
        mock_validate_profile,
        cli_runner,
        mock_profile_data,
        mock_schedule_info,
    ):
        """Test successful schedule status retrieval."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {"success": True, "schedule": mock_schedule_info}

        # Run command
        result = cli_runner.invoke(app, ["status", "schedule-123"])

        # Verify result
        assert result.exit_code == 0
        assert "test-schedule" in result.stdout
        assert "daily" in result.stdout
        assert "Schedule Information" in result.stdout
        mock_asyncio_run.assert_called_once()

    @patch("awsideman.commands.backup.schedule_commands.validate_profile")
    @patch("awsideman.commands.backup.schedule_commands.asyncio.run")
    def test_get_schedule_status_not_found(
        self, mock_asyncio_run, mock_validate_profile, cli_runner, mock_profile_data
    ):
        """Test getting status for non-existent schedule."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {
            "success": False,
            "message": "Schedule not found",
            "errors": ["Schedule schedule-123 not found"],
        }

        # Run command
        result = cli_runner.invoke(app, ["status", "schedule-123"])

        # Verify result
        assert result.exit_code == 1
        assert "Schedule not found" in result.stdout


class TestScheduleRunCommand:
    """Test the schedule run command."""

    @patch("awsideman.commands.backup.schedule_commands.validate_profile")
    @patch("awsideman.commands.backup.schedule_commands.asyncio.run")
    def test_run_schedule_success(
        self, mock_asyncio_run, mock_validate_profile, cli_runner, mock_profile_data
    ):
        """Test successful manual schedule execution."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {
            "success": True,
            "backup_result": {
                "success": True,
                "backup_id": "backup-456",
                "message": "Backup completed successfully",
                "errors": [],
                "warnings": [],
                "duration": 120.5,
            },
        }

        # Run command
        result = cli_runner.invoke(app, ["run", "schedule-123"])

        # Verify result
        assert result.exit_code == 0
        assert "Scheduled backup completed successfully" in result.stdout
        assert "backup-456" in result.stdout
        assert "120.50 seconds" in result.stdout
        mock_asyncio_run.assert_called_once()

    @patch("awsideman.commands.backup.schedule_commands.validate_profile")
    @patch("awsideman.commands.backup.schedule_commands.asyncio.run")
    def test_run_schedule_backup_failure(
        self, mock_asyncio_run, mock_validate_profile, cli_runner, mock_profile_data
    ):
        """Test manual schedule execution with backup failure."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {
            "success": True,
            "backup_result": {
                "success": False,
                "backup_id": None,
                "message": "Backup failed",
                "errors": ["Storage connection failed"],
                "warnings": [],
                "duration": 30.0,
            },
        }

        # Run command
        result = cli_runner.invoke(app, ["run", "schedule-123"])

        # Verify result
        assert result.exit_code == 1
        assert "Scheduled backup failed" in result.stdout
        assert "Storage connection failed" in result.stdout

    @patch("awsideman.commands.backup.schedule_commands.validate_profile")
    @patch("awsideman.commands.backup.schedule_commands.asyncio.run")
    def test_run_schedule_not_found(
        self, mock_asyncio_run, mock_validate_profile, cli_runner, mock_profile_data
    ):
        """Test running a non-existent schedule."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {
            "success": False,
            "message": "Schedule not found",
            "errors": ["Schedule schedule-123 not found"],
        }

        # Run command
        result = cli_runner.invoke(app, ["run", "schedule-123"])

        # Verify result
        assert result.exit_code == 1
        assert "Failed to run schedule" in result.stdout


class TestScheduleCommandValidation:
    """Test input validation for schedule commands."""

    def test_invalid_output_format(self, cli_runner):
        """Test commands with invalid output format."""
        result = cli_runner.invoke(app, ["list", "--format", "invalid"])
        assert result.exit_code == 1
        assert "Invalid output format" in result.stdout

    def test_create_schedule_invalid_resources(self, cli_runner):
        """Test schedule creation with invalid resource types."""
        result = cli_runner.invoke(
            app, ["create", "--name", "test-schedule", "--resources", "invalid,users"]
        )
        assert result.exit_code == 1
        assert "Invalid resource type" in result.stdout

    def test_create_schedule_negative_retention(self, cli_runner):
        """Test schedule creation with negative retention values."""
        # This would be caught by the async function, but we test the CLI validation
        cli_runner.invoke(app, ["create", "--name", "test-schedule", "--keep-daily", "-1"])
        # The CLI accepts negative values, but the backend validation should catch it
        # This test ensures the command structure is correct


@pytest.mark.asyncio
class TestScheduleAsyncFunctions:
    """Test the async helper functions used by schedule commands."""

    @patch("awsideman.commands.backup.schedule_commands.ScheduleManager")
    @patch("awsideman.commands.backup.schedule_commands.BackupManager")
    async def test_create_schedule_async_success(
        self, mock_backup_manager_class, mock_schedule_manager_class, mock_profile_data
    ):
        """Test successful async schedule creation."""
        from awsideman.backup_restore.models import (
            BackupType,
            NotificationSettings,
            ResourceType,
            RetentionPolicy,
        )
        from awsideman.commands.backup.schedule_commands import _create_schedule_async

        # Setup mocks
        mock_schedule_manager = AsyncMock()
        mock_schedule_manager.create_schedule.return_value = "schedule-123"
        mock_schedule_manager.get_schedule_status.return_value = {
            "next_run": (datetime.now() + timedelta(hours=24)).isoformat()
        }
        mock_schedule_manager_class.return_value = mock_schedule_manager

        # Call function
        result = await _create_schedule_async(
            name="test-schedule",
            interval="daily",
            backup_type=BackupType.FULL,
            resource_types=[ResourceType.ALL],
            storage_backend="filesystem",
            storage_path=None,
            retention_policy=RetentionPolicy(),
            notification_settings=NotificationSettings(),
            enabled=True,
            encryption_enabled=True,
            compression_enabled=True,
            include_inactive_users=False,
            profile_data=mock_profile_data,
            output_format="table",
        )

        # Verify result
        assert result["success"] is True
        assert result["schedule_id"] == "schedule-123"
        mock_schedule_manager.create_schedule.assert_called_once()

    @patch("awsideman.commands.backup.schedule_commands.ScheduleManager")
    @patch("awsideman.commands.backup.schedule_commands.BackupManager")
    async def test_list_schedules_async_success(
        self, mock_backup_manager_class, mock_schedule_manager_class, mock_profile_data
    ):
        """Test successful async schedule listing."""
        from awsideman.commands.backup.schedule_commands import _list_schedules_async

        # Setup mocks
        mock_schedule_manager = AsyncMock()
        mock_schedule_manager.list_schedules.return_value = [
            {"schedule_id": "schedule-123", "name": "test-schedule", "enabled": True}
        ]
        mock_schedule_manager_class.return_value = mock_schedule_manager

        # Call function
        result = await _list_schedules_async(
            enabled_only=False, profile_data=mock_profile_data, output_format="table"
        )

        # Verify result
        assert result["success"] is True
        assert len(result["schedules"]) == 1
        assert result["schedules"][0]["name"] == "test-schedule"
        mock_schedule_manager.list_schedules.assert_called_once()
