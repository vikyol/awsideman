"""Integration tests for backup monitoring CLI commands.

This module tests the backup monitoring CLI commands including
status, metrics, and health operations.
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from awsideman.commands.backup.monitoring_commands import app


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
def mock_system_status():
    """Mock system status data for testing."""
    return {
        "overall_status": "healthy",
        "components": {
            "storage": {"status": "healthy", "message": "Storage accessible, 5 backups found"},
            "scheduler": {"status": "healthy", "message": "Running, 2 active schedules"},
            "monitor": {"status": "healthy", "message": "Monitoring active"},
        },
        "statistics": {
            "total_backups": 5,
            "active_schedules": 2,
            "storage_used": "1.2 GB",
            "last_backup_time": "2024-01-17 14:30:22",
            "success_rate_7d": 0.95,
        },
        "warnings": [],
        "errors": [],
    }


@pytest.fixture
def mock_backup_metrics():
    """Mock backup metrics data for testing."""
    return {
        "total_backups": 10,
        "successful_backups": 9,
        "failed_backups": 1,
        "success_rate": 0.9,
        "avg_duration": 120.5,
        "total_storage": "2.5 GB",
        "backup_types": {
            "full": {"count": 6, "success_rate": 0.83},
            "incremental": {"count": 4, "success_rate": 1.0},
        },
        "daily_breakdown": {
            "2024-01-17": {"total": 2, "successful": 2, "failed": 0, "success_rate": 1.0},
            "2024-01-16": {"total": 3, "successful": 2, "failed": 1, "success_rate": 0.67},
            "2024-01-15": {"total": 1, "successful": 1, "failed": 0, "success_rate": 1.0},
        },
        "performance": {
            "min_duration": 45.2,
            "max_duration": 300.8,
            "avg_duration": 120.5,
            "median_duration": 115.0,
        },
    }


@pytest.fixture
def mock_health_status():
    """Mock health status data for testing."""
    return {
        "overall_health": "healthy",
        "checks": {
            "storage_connectivity": {
                "status": "pass",
                "message": "Storage is accessible",
                "last_checked": datetime.now().isoformat(),
            },
            "scheduler_status": {
                "status": "pass",
                "message": "Scheduler is running",
                "last_checked": datetime.now().isoformat(),
            },
            "recent_backups": {
                "status": "pass",
                "message": "2 backups in last 24 hours",
                "last_checked": datetime.now().isoformat(),
            },
        },
        "recommendations": [],
        "warnings": [],
        "critical_issues": [],
    }


class TestStatusCommand:
    """Test the status command."""

    @patch("awsideman.commands.backup.monitoring_commands.validate_profile")
    @patch("awsideman.commands.backup.monitoring_commands.asyncio.run")
    def test_show_system_status_success(
        self,
        mock_asyncio_run,
        mock_validate_profile,
        cli_runner,
        mock_profile_data,
        mock_system_status,
    ):
        """Test successful system status display."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {"success": True, "status": mock_system_status}

        # Run command
        result = cli_runner.invoke(app, ["status"])

        # Verify result
        assert result.exit_code == 0
        assert "Overall Status: HEALTHY" in result.stdout
        assert "Component Status" in result.stdout
        assert "Storage" in result.stdout
        assert "Scheduler" in result.stdout
        assert "Monitor" in result.stdout
        assert "System Statistics" in result.stdout
        assert "Total Backups" in result.stdout
        assert "5" in result.stdout  # total_backups
        assert "2" in result.stdout  # active_schedules
        mock_asyncio_run.assert_called_once()

    @patch("awsideman.commands.backup.monitoring_commands.validate_profile")
    @patch("awsideman.commands.backup.monitoring_commands.asyncio.run")
    def test_show_system_status_with_warnings(
        self,
        mock_asyncio_run,
        mock_validate_profile,
        cli_runner,
        mock_profile_data,
        mock_system_status,
    ):
        """Test system status display with warnings."""
        # Modify mock to include warnings
        mock_system_status["overall_status"] = "warning"
        mock_system_status["warnings"] = ["No recent backups", "Storage usage high"]
        mock_system_status["components"]["scheduler"]["status"] = "warning"
        mock_system_status["components"]["scheduler"]["message"] = "Scheduler not running"

        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {"success": True, "status": mock_system_status}

        # Run command
        result = cli_runner.invoke(app, ["status"])

        # Verify result
        assert result.exit_code == 0
        assert "Overall Status: WARNING" in result.stdout
        assert "System Warnings" in result.stdout
        assert "No recent backups" in result.stdout
        assert "Storage usage high" in result.stdout

    @patch("awsideman.commands.backup.monitoring_commands.validate_profile")
    @patch("awsideman.commands.backup.monitoring_commands.asyncio.run")
    def test_show_system_status_json_format(
        self,
        mock_asyncio_run,
        mock_validate_profile,
        cli_runner,
        mock_profile_data,
        mock_system_status,
    ):
        """Test system status with JSON output format."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {"success": True, "status": mock_system_status}

        # Run command
        result = cli_runner.invoke(app, ["status", "--format", "json"])

        # Verify result
        assert result.exit_code == 0
        output_data = json.loads(result.stdout)
        assert output_data["success"] is True
        assert output_data["status"]["overall_status"] == "healthy"

    def test_show_system_status_invalid_storage(self, cli_runner):
        """Test status command with invalid storage backend."""
        result = cli_runner.invoke(app, ["status", "--storage", "invalid"])

        assert result.exit_code == 1
        assert "Invalid storage backend" in result.stdout

    @patch("awsideman.commands.backup.monitoring_commands.validate_profile")
    @patch("awsideman.commands.backup.monitoring_commands.asyncio.run")
    def test_show_system_status_failure(
        self, mock_asyncio_run, mock_validate_profile, cli_runner, mock_profile_data
    ):
        """Test system status failure."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {
            "success": False,
            "message": "Failed to get system status",
            "errors": ["Storage connection failed"],
        }

        # Run command
        result = cli_runner.invoke(app, ["status"])

        # Verify result
        assert result.exit_code == 1
        assert "Failed to get system status" in result.stdout
        assert "Storage connection failed" in result.stdout


class TestMetricsCommand:
    """Test the metrics command."""

    @patch("awsideman.commands.backup.monitoring_commands.validate_profile")
    @patch("awsideman.commands.backup.monitoring_commands.asyncio.run")
    def test_show_backup_metrics_success(
        self,
        mock_asyncio_run,
        mock_validate_profile,
        cli_runner,
        mock_profile_data,
        mock_backup_metrics,
    ):
        """Test successful backup metrics display."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {"success": True, "metrics": mock_backup_metrics}

        # Run command
        result = cli_runner.invoke(app, ["metrics", "--days", "7"])

        # Verify result
        assert result.exit_code == 0
        assert "Backup Metrics Summary" in result.stdout
        assert "Total Backups" in result.stdout
        assert "10" in result.stdout  # total_backups
        assert "90.0%" in result.stdout  # success_rate
        assert "Backup Types" in result.stdout
        assert "Daily Breakdown" in result.stdout
        assert "Performance Metrics" in result.stdout
        assert "120.5 seconds" in result.stdout  # avg_duration
        mock_asyncio_run.assert_called_once()

    @patch("awsideman.commands.backup.monitoring_commands.validate_profile")
    @patch("awsideman.commands.backup.monitoring_commands.asyncio.run")
    def test_show_backup_metrics_custom_days(
        self,
        mock_asyncio_run,
        mock_validate_profile,
        cli_runner,
        mock_profile_data,
        mock_backup_metrics,
    ):
        """Test backup metrics with custom days parameter."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {"success": True, "metrics": mock_backup_metrics}

        # Run command
        result = cli_runner.invoke(app, ["metrics", "--days", "30"])

        # Verify result
        assert result.exit_code == 0
        assert "Collecting backup metrics for last 30 days" in result.stdout
        mock_asyncio_run.assert_called_once()

    def test_show_backup_metrics_invalid_days(self, cli_runner):
        """Test metrics command with invalid days parameter."""
        result = cli_runner.invoke(app, ["metrics", "--days", "0"])

        assert result.exit_code == 1
        assert "Days must be a positive integer" in result.stdout

    @patch("awsideman.commands.backup.monitoring_commands.validate_profile")
    @patch("awsideman.commands.backup.monitoring_commands.asyncio.run")
    def test_show_backup_metrics_json_format(
        self,
        mock_asyncio_run,
        mock_validate_profile,
        cli_runner,
        mock_profile_data,
        mock_backup_metrics,
    ):
        """Test backup metrics with JSON output format."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {"success": True, "metrics": mock_backup_metrics}

        # Run command
        result = cli_runner.invoke(app, ["metrics", "--format", "json"])

        # Verify result
        assert result.exit_code == 0
        output_data = json.loads(result.stdout)
        assert output_data["success"] is True
        assert output_data["metrics"]["total_backups"] == 10

    @patch("awsideman.commands.backup.monitoring_commands.validate_profile")
    @patch("awsideman.commands.backup.monitoring_commands.asyncio.run")
    def test_show_backup_metrics_failure(
        self, mock_asyncio_run, mock_validate_profile, cli_runner, mock_profile_data
    ):
        """Test backup metrics failure."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {
            "success": False,
            "message": "Failed to get metrics",
            "errors": ["Database connection failed"],
        }

        # Run command
        result = cli_runner.invoke(app, ["metrics"])

        # Verify result
        assert result.exit_code == 1
        assert "Failed to get metrics" in result.stdout
        assert "Database connection failed" in result.stdout


class TestHealthCommand:
    """Test the health command."""

    @patch("awsideman.commands.backup.monitoring_commands.validate_profile")
    @patch("awsideman.commands.backup.monitoring_commands.asyncio.run")
    def test_check_system_health_success(
        self,
        mock_asyncio_run,
        mock_validate_profile,
        cli_runner,
        mock_profile_data,
        mock_health_status,
    ):
        """Test successful system health check."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {"success": True, "health": mock_health_status}

        # Run command
        result = cli_runner.invoke(app, ["health"])

        # Verify result
        assert result.exit_code == 0
        assert "Overall Health: HEALTHY" in result.stdout
        assert "Health Checks" in result.stdout
        assert "Storage Connectivity" in result.stdout
        assert "Scheduler Status" in result.stdout
        assert "Recent Backups" in result.stdout
        assert "PASS" in result.stdout
        mock_asyncio_run.assert_called_once()

    @patch("awsideman.commands.backup.monitoring_commands.validate_profile")
    @patch("awsideman.commands.backup.monitoring_commands.asyncio.run")
    def test_check_system_health_with_warnings(
        self,
        mock_asyncio_run,
        mock_validate_profile,
        cli_runner,
        mock_profile_data,
        mock_health_status,
    ):
        """Test system health check with warnings."""
        # Modify mock to include warnings
        mock_health_status["overall_health"] = "warning"
        mock_health_status["checks"]["recent_backups"]["status"] = "warning"
        mock_health_status["checks"]["recent_backups"]["message"] = "No backups in last 24 hours"
        mock_health_status["warnings"] = ["Recent Backups: No backups in last 24 hours"]
        mock_health_status["recommendations"] = ["Consider running a manual backup"]

        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {"success": True, "health": mock_health_status}

        # Run command
        result = cli_runner.invoke(app, ["health"])

        # Verify result
        assert result.exit_code == 0
        assert "Overall Health: WARNING" in result.stdout
        assert "Health Warnings" in result.stdout
        assert "No backups in last 24 hours" in result.stdout
        assert "Recommendations" in result.stdout
        assert "Consider running a manual backup" in result.stdout

    @patch("awsideman.commands.backup.monitoring_commands.validate_profile")
    @patch("awsideman.commands.backup.monitoring_commands.asyncio.run")
    def test_check_system_health_critical(
        self,
        mock_asyncio_run,
        mock_validate_profile,
        cli_runner,
        mock_profile_data,
        mock_health_status,
    ):
        """Test system health check with critical issues."""
        # Modify mock to include critical issues
        mock_health_status["overall_health"] = "critical"
        mock_health_status["checks"]["storage_connectivity"]["status"] = "fail"
        mock_health_status["checks"]["storage_connectivity"][
            "message"
        ] = "Storage connectivity failed"
        mock_health_status["critical_issues"] = [
            "Storage Connectivity: Storage connectivity failed"
        ]
        mock_health_status["recommendations"] = [
            "Check storage configuration and network connectivity"
        ]

        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {"success": True, "health": mock_health_status}

        # Run command
        result = cli_runner.invoke(app, ["health"])

        # Verify result
        assert result.exit_code == 1  # Critical health should exit with error code
        assert "Overall Health: CRITICAL" in result.stdout
        assert "Critical Issues" in result.stdout
        assert "Storage connectivity failed" in result.stdout

    @patch("awsideman.commands.backup.monitoring_commands.validate_profile")
    @patch("awsideman.commands.backup.monitoring_commands.asyncio.run")
    def test_check_system_health_json_format(
        self,
        mock_asyncio_run,
        mock_validate_profile,
        cli_runner,
        mock_profile_data,
        mock_health_status,
    ):
        """Test system health check with JSON output format."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {"success": True, "health": mock_health_status}

        # Run command
        result = cli_runner.invoke(app, ["health", "--format", "json"])

        # Verify result
        assert result.exit_code == 0
        output_data = json.loads(result.stdout)
        assert output_data["success"] is True
        assert output_data["health"]["overall_health"] == "healthy"

    @patch("awsideman.commands.backup.monitoring_commands.validate_profile")
    @patch("awsideman.commands.backup.monitoring_commands.asyncio.run")
    def test_check_system_health_failure(
        self, mock_asyncio_run, mock_validate_profile, cli_runner, mock_profile_data
    ):
        """Test system health check failure."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", mock_profile_data)
        mock_asyncio_run.return_value = {
            "success": False,
            "message": "Failed to check system health",
            "errors": ["Health check service unavailable"],
        }

        # Run command
        result = cli_runner.invoke(app, ["health"])

        # Verify result
        assert result.exit_code == 1
        assert "Failed to check system health" in result.stdout
        assert "Health check service unavailable" in result.stdout


class TestMonitoringCommandValidation:
    """Test input validation for monitoring commands."""

    def test_invalid_output_format(self, cli_runner):
        """Test commands with invalid output format."""
        result = cli_runner.invoke(app, ["status", "--format", "invalid"])
        assert result.exit_code == 1
        assert "Invalid output format" in result.stdout

        result = cli_runner.invoke(app, ["metrics", "--format", "invalid"])
        assert result.exit_code == 1
        assert "Invalid output format" in result.stdout

        result = cli_runner.invoke(app, ["health", "--format", "invalid"])
        assert result.exit_code == 1
        assert "Invalid output format" in result.stdout

    def test_invalid_storage_backend(self, cli_runner):
        """Test commands with invalid storage backend."""
        result = cli_runner.invoke(app, ["status", "--storage", "invalid"])
        assert result.exit_code == 1
        assert "Invalid storage backend" in result.stdout

        result = cli_runner.invoke(app, ["metrics", "--storage", "invalid"])
        assert result.exit_code == 1
        assert "Invalid storage backend" in result.stdout

        result = cli_runner.invoke(app, ["health", "--storage", "invalid"])
        assert result.exit_code == 1
        assert "Invalid storage backend" in result.stdout


@pytest.mark.asyncio
class TestMonitoringAsyncFunctions:
    """Test the async helper functions used by monitoring commands."""

    @patch("awsideman.commands.backup.monitoring_commands.ScheduleManager")
    @patch("awsideman.commands.backup.monitoring_commands.BackupManager")
    async def test_get_system_status_async_success(
        self, mock_backup_manager_class, mock_schedule_manager_class, mock_profile_data
    ):
        """Test successful async system status retrieval."""
        from awsideman.commands.backup.monitoring_commands import _get_system_status_async

        # Setup mocks
        mock_backup_manager = AsyncMock()
        mock_backup_manager.list_backups.return_value = [MagicMock(), MagicMock()]  # 2 backups
        mock_backup_manager_class.return_value = mock_backup_manager

        mock_schedule_manager = MagicMock()
        mock_schedule_manager.get_scheduler_status.return_value = {
            "running": True,
            "enabled_schedules": 2,
        }
        mock_schedule_manager.list_schedules.return_value = [{"enabled": True}, {"enabled": True}]
        mock_schedule_manager_class.return_value = mock_schedule_manager

        # Call function
        result = await _get_system_status_async(
            storage_backend="filesystem",
            storage_path=None,
            profile_data=mock_profile_data,
            output_format="table",
        )

        # Verify result
        assert result["success"] is True
        assert result["status"]["overall_status"] == "healthy"
        assert result["status"]["components"]["storage"]["status"] == "healthy"
        assert result["status"]["components"]["scheduler"]["status"] == "healthy"

    @patch("awsideman.commands.backup.monitoring_commands.BackupManager")
    async def test_get_backup_metrics_async_success(
        self, mock_backup_manager_class, mock_profile_data
    ):
        """Test successful async backup metrics retrieval."""
        from awsideman.commands.backup.monitoring_commands import _get_backup_metrics_async

        # Setup mocks
        mock_backup_manager = AsyncMock()
        mock_backup_manager.list_backups.return_value = [
            MagicMock(),
            MagicMock(),
            MagicMock(),
        ]  # 3 backups
        mock_backup_manager_class.return_value = mock_backup_manager

        # Call function
        result = await _get_backup_metrics_async(
            days=7,
            storage_backend="filesystem",
            storage_path=None,
            profile_data=mock_profile_data,
            output_format="table",
        )

        # Verify result
        assert result["success"] is True
        assert result["metrics"]["total_backups"] == 3
        mock_backup_manager.list_backups.assert_called_once()

    @patch("awsideman.commands.backup.monitoring_commands.ScheduleManager")
    @patch("awsideman.commands.backup.monitoring_commands.BackupManager")
    async def test_check_system_health_async_success(
        self, mock_backup_manager_class, mock_schedule_manager_class, mock_profile_data
    ):
        """Test successful async system health check."""
        from awsideman.commands.backup.monitoring_commands import _check_system_health_async

        # Setup mocks
        mock_backup_manager = AsyncMock()
        mock_backup_manager.list_backups.side_effect = [
            [],  # First call for storage connectivity
            [MagicMock()],  # Second call for recent backups
        ]
        mock_backup_manager_class.return_value = mock_backup_manager

        mock_schedule_manager = MagicMock()
        mock_schedule_manager.get_scheduler_status.return_value = {"running": True}
        mock_schedule_manager_class.return_value = mock_schedule_manager

        # Call function
        result = await _check_system_health_async(
            storage_backend="filesystem",
            storage_path=None,
            profile_data=mock_profile_data,
            output_format="table",
        )

        # Verify result
        assert result["success"] is True
        assert result["health"]["overall_health"] == "healthy"
        assert result["health"]["checks"]["storage_connectivity"]["status"] == "pass"
        assert result["health"]["checks"]["scheduler_status"]["status"] == "pass"
        assert result["health"]["checks"]["recent_backups"]["status"] == "pass"
