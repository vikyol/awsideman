"""Tests for rollback status command."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from src.awsideman.commands.rollback import app
from src.awsideman.utils.rollback.models import (
    OperationRecord,
    OperationResult,
    OperationType,
    PrincipalType,
)


@pytest.fixture
def runner():
    """Create a CLI runner for testing."""
    return CliRunner()


@pytest.fixture
def sample_operations():
    """Create sample operation records for testing."""
    now = datetime.now(timezone.utc)

    operations = [
        # Recent assign operation
        OperationRecord(
            operation_id="op-123-assign",
            timestamp=now - timedelta(hours=1),
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="john.doe",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
            permission_set_name="ReadOnlyAccess",
            account_ids=["123456789012"],
            account_names=["Production"],
            results=[OperationResult(account_id="123456789012", success=True, duration_ms=1500)],
            metadata={"source": "bulk_assign"},
            rolled_back=False,
        ),
        # Recent revoke operation
        OperationRecord(
            operation_id="op-456-revoke",
            timestamp=now - timedelta(hours=2),
            operation_type=OperationType.REVOKE,
            principal_id="group-456",
            principal_type=PrincipalType.GROUP,
            principal_name="Developers",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
            permission_set_name="PowerUserAccess",
            account_ids=["123456789012"],
            account_names=["Production"],
            results=[OperationResult(account_id="123456789012", success=True, duration_ms=1200)],
            metadata={"source": "individual_revoke"},
            rolled_back=True,
            rollback_operation_id="op-rollback-123",
        ),
    ]

    return operations


class TestRollbackStatusCommand:
    """Test cases for the rollback status command."""

    @patch("src.awsideman.commands.rollback.validate_profile")
    @patch("src.awsideman.commands.rollback.OperationLogger")
    def test_status_basic_functionality(
        self, mock_logger_class, mock_validate_profile, runner, sample_operations
    ):
        """Test basic status command functionality."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", {})
        mock_logger = Mock()
        mock_logger_class.return_value = mock_logger

        # Mock storage stats
        mock_logger.get_storage_stats.return_value = {"file_count": 2, "total_size": 1024}

        # Mock operations - recent (7 days) and all operations
        recent_operations = sample_operations  # Both operations are recent
        all_operations = sample_operations

        mock_logger.get_operations.side_effect = [
            recent_operations,  # First call for recent operations (7 days)
            all_operations,  # Second call for all operations (1000 limit)
        ]

        # Run command
        result = runner.invoke(app, ["status"])

        # Verify result
        assert result.exit_code == 0
        assert "Rollback System Status" in result.stdout
        assert "Profile: default" in result.stdout

        # Check metrics table
        assert "Total Operations" in result.stdout
        assert "2" in result.stdout  # Total operations count
        assert "Assign Operations" in result.stdout
        assert "1" in result.stdout  # 1 assign operation
        assert "Revoke Operations" in result.stdout
        assert "1" in result.stdout  # 1 revoke operation
        assert "Rolled Back" in result.stdout
        assert "1" in result.stdout  # 1 rolled back operation
        assert "Recent Activity" in result.stdout
        assert "2 (7 days)" in result.stdout  # 2 recent operations
        assert "Storage Files" in result.stdout
        assert "2" in result.stdout  # 2 storage files
        assert "System Health" in result.stdout
        assert "Healthy" in result.stdout

        # Verify logger calls
        assert mock_logger.get_operations.call_count == 2
        mock_logger.get_storage_stats.assert_called_once()

    @patch("src.awsideman.commands.rollback.validate_profile")
    @patch("src.awsideman.commands.rollback.OperationLogger")
    def test_status_no_operations(self, mock_logger_class, mock_validate_profile, runner):
        """Test status command when no operations exist."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", {})
        mock_logger = Mock()
        mock_logger_class.return_value = mock_logger

        mock_logger.get_storage_stats.return_value = {"file_count": 0}
        mock_logger.get_operations.return_value = []  # No operations

        # Run command
        result = runner.invoke(app, ["status"])

        # Verify result
        assert result.exit_code == 0

        # Check metrics show zero values
        assert "Total Operations" in result.stdout
        assert "0" in result.stdout
        assert "System Health" in result.stdout
        assert "No Data" in result.stdout
        assert "No operations tracked yet" in result.stdout

        # Should not show recent activity table
        assert "Recent Activity (Last 7 Days)" not in result.stdout

    @patch("src.awsideman.commands.rollback.validate_profile")
    @patch("src.awsideman.commands.rollback.OperationLogger")
    def test_status_logger_initialization_error(
        self, mock_logger_class, mock_validate_profile, runner
    ):
        """Test status command when logger initialization fails."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", {})
        mock_logger_class.side_effect = Exception("Storage directory not accessible")

        # Run command
        result = runner.invoke(app, ["status"])

        # Verify result
        assert result.exit_code == 1
        assert "Failed to initialize operation logger" in result.stdout
        assert "Storage directory not accessible" in result.stdout
