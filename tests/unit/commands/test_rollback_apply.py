"""Tests for rollback apply command."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from src.awsideman.commands.rollback import app
from src.awsideman.rollback.models import (
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
def sample_assign_operation():
    """Create a sample assign operation for testing."""
    now = datetime.now(timezone.utc)

    return OperationRecord(
        operation_id="op-123-assign",
        timestamp=now - timedelta(hours=1),
        operation_type=OperationType.ASSIGN,
        principal_id="user-123",
        principal_type=PrincipalType.USER,
        principal_name="john.doe",
        permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
        permission_set_name="ReadOnlyAccess",
        account_ids=["123456789012", "987654321098"],
        account_names=["Production", "Staging"],
        results=[
            OperationResult(account_id="123456789012", success=True, duration_ms=1500),
            OperationResult(account_id="987654321098", success=True, duration_ms=1200),
        ],
        metadata={"source": "bulk_assign", "batch_size": 10},
        rolled_back=False,
    )


class TestRollbackApplyCommand:
    """Test cases for the rollback apply command."""

    def test_apply_rollback_empty_operation_id(self, runner):
        """Test apply rollback with empty operation ID."""
        result = runner.invoke(app, ["apply", ""])

        assert result.exit_code == 1
        assert "Operation ID cannot be empty" in result.stdout

    def test_apply_rollback_invalid_batch_size_zero(self, runner):
        """Test apply rollback with invalid batch size (zero)."""
        result = runner.invoke(app, ["apply", "op-123", "--batch-size", "0"])

        assert result.exit_code == 1
        assert "Batch size must be between 1 and 50" in result.stdout

    @patch("src.awsideman.commands.rollback.validate_profile")
    @patch("src.awsideman.commands.rollback.OperationLogger")
    def test_apply_rollback_operation_not_found(
        self, mock_logger_class, mock_validate_profile, runner
    ):
        """Test apply rollback when operation is not found."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", {})
        mock_logger = Mock()
        mock_logger_class.return_value = mock_logger
        mock_logger.get_operation.return_value = None  # Operation not found

        # Run command
        result = runner.invoke(app, ["apply", "nonexistent-op-id"])

        # Verify result
        assert result.exit_code == 1
        assert "Operation not found: nonexistent-op-id" in result.stdout
        assert "Use 'awsideman rollback list' to see available operations" in result.stdout

        # Verify logger was called
        mock_logger.get_operation.assert_called_once_with("nonexistent-op-id")

    @patch("src.awsideman.commands.rollback.validate_profile")
    @patch("src.awsideman.commands.rollback.OperationLogger")
    def test_apply_rollback_assign_operation_dry_run(
        self, mock_logger_class, mock_validate_profile, runner, sample_assign_operation
    ):
        """Test apply rollback for assign operation in dry-run mode."""
        # Setup mocks
        mock_validate_profile.return_value = ("test-profile", {})
        mock_logger = Mock()
        mock_logger_class.return_value = mock_logger
        mock_logger.get_operation.return_value = sample_assign_operation

        # Run command in dry-run mode
        result = runner.invoke(app, ["apply", "op-123-assign", "--dry-run"])

        # Verify result
        assert result.exit_code == 0
        assert "Found operation: assign operation" in result.stdout
        assert "The following assignments will be revoked:" in result.stdout
        assert "john.doe" in result.stdout
        assert "ReadOnlyAccess" in result.stdout
        assert "Production (123456789012)" in result.stdout
        assert "Staging (987654321098)" in result.stdout
        assert "REVOKE" in result.stdout
        assert "Dry-run completed successfully!" in result.stdout
        assert "No changes were made" in result.stdout

    @patch("src.awsideman.commands.rollback.validate_profile")
    @patch("src.awsideman.commands.rollback.OperationLogger")
    def test_apply_rollback_confirmation_cancelled(
        self, mock_logger_class, mock_validate_profile, runner, sample_assign_operation
    ):
        """Test apply rollback when user cancels confirmation."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", {})
        mock_logger = Mock()
        mock_logger_class.return_value = mock_logger
        mock_logger.get_operation.return_value = sample_assign_operation

        # Run command and simulate user cancelling
        result = runner.invoke(app, ["apply", "op-123-assign"], input="n\n")

        # Verify result
        assert result.exit_code == 0
        assert "Do you want to proceed with the rollback?" in result.stdout
        assert "Rollback cancelled by user" in result.stdout

    @patch("src.awsideman.commands.rollback.validate_profile")
    @patch("src.awsideman.commands.rollback.OperationLogger")
    def test_apply_rollback_with_yes_flag(
        self, mock_logger_class, mock_validate_profile, runner, sample_assign_operation
    ):
        """Test apply rollback with --yes flag to skip confirmation."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", {})
        mock_logger = Mock()
        mock_logger_class.return_value = mock_logger
        mock_logger.get_operation.return_value = sample_assign_operation

        # Run command with --yes flag
        result = runner.invoke(app, ["apply", "op-123-assign", "--yes"])

        # Verify result
        assert result.exit_code == 0

        # Should not ask for confirmation
        assert "Do you want to proceed with the rollback?" not in result.stdout

        # Should proceed to execution (which shows placeholder message for now)
        assert "Executing rollback operation" in result.stdout
        assert "Rollback execution is not yet implemented" in result.stdout

    @patch("src.awsideman.commands.rollback.validate_profile")
    @patch("src.awsideman.commands.rollback.OperationLogger")
    def test_apply_rollback_custom_batch_size(
        self, mock_logger_class, mock_validate_profile, runner, sample_assign_operation
    ):
        """Test apply rollback with custom batch size."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", {})
        mock_logger = Mock()
        mock_logger_class.return_value = mock_logger
        mock_logger.get_operation.return_value = sample_assign_operation

        # Run command with custom batch size
        result = runner.invoke(app, ["apply", "op-123-assign", "--batch-size", "5", "--dry-run"])

        # Verify result
        assert result.exit_code == 0
        assert "Batch size: 5" in result.stdout

    @patch("src.awsideman.commands.rollback.validate_profile")
    @patch("src.awsideman.commands.rollback.OperationLogger")
    def test_apply_rollback_logger_initialization_error(
        self, mock_logger_class, mock_validate_profile, runner
    ):
        """Test apply rollback when logger initialization fails."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", {})
        mock_logger_class.side_effect = Exception("Storage directory not accessible")

        # Run command
        result = runner.invoke(app, ["apply", "op-123"])

        # Verify result
        assert result.exit_code == 1
        assert "Failed to initialize operation logger" in result.stdout
        assert "Storage directory not accessible" in result.stdout

    @patch("src.awsideman.commands.rollback.validate_profile")
    @patch("src.awsideman.commands.rollback.OperationLogger")
    def test_apply_rollback_operation_lookup_error(
        self, mock_logger_class, mock_validate_profile, runner
    ):
        """Test apply rollback when operation lookup fails."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", {})
        mock_logger = Mock()
        mock_logger_class.return_value = mock_logger
        mock_logger.get_operation.side_effect = Exception("Database connection failed")

        # Run command
        result = runner.invoke(app, ["apply", "op-123"])

        # Verify result
        assert result.exit_code == 1
        assert "Error validating operation" in result.stdout
        assert "Database connection failed" in result.stdout

    def test_apply_rollback_argument_validation(self, runner):
        """Test apply rollback command argument validation."""
        # Test empty operation ID
        result = runner.invoke(app, ["apply", "   "])  # Whitespace only
        assert result.exit_code == 1
        assert "Operation ID cannot be empty" in result.stdout

        # Test invalid batch size - negative
        result = runner.invoke(app, ["apply", "op-123", "--batch-size", "-1"])
        assert result.exit_code == 1
        assert "Batch size must be between 1 and 50" in result.stdout

        # Test invalid batch size - too large
        result = runner.invoke(app, ["apply", "op-123", "--batch-size", "100"])
        assert result.exit_code == 1
        assert "Batch size must be between 1 and 50" in result.stdout

        # Test valid batch size at boundaries
        # These should pass validation (though they'll fail later due to missing operation)
        result = runner.invoke(app, ["apply", "op-123", "--batch-size", "1", "--dry-run"])
        assert "Batch size must be between 1 and 50" not in result.stdout

        result = runner.invoke(app, ["apply", "op-123", "--batch-size", "50", "--dry-run"])
        assert "Batch size must be between 1 and 50" not in result.stdout

    @patch("src.awsideman.commands.rollback.validate_profile")
    @patch("src.awsideman.commands.rollback.OperationLogger")
    def test_apply_rollback_operation_details_display(
        self, mock_logger_class, mock_validate_profile, runner, sample_assign_operation
    ):
        """Test that operation details are displayed correctly."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", {})
        mock_logger = Mock()
        mock_logger_class.return_value = mock_logger
        mock_logger.get_operation.return_value = sample_assign_operation

        # Run command in dry-run mode
        result = runner.invoke(app, ["apply", "op-123-assign", "--dry-run"])

        # Verify result
        assert result.exit_code == 0

        # Check operation details panel
        assert "Operation Information" in result.stdout
        assert "op-123-assign" in result.stdout
        assert "ASSIGN" in result.stdout

        # Check principal information
        assert "Principal Information" in result.stdout
        assert "john.doe" in result.stdout
        assert "USER" in result.stdout
        assert "user-123" in result.stdout

        # Check permission set information
        assert "Permission Set Information" in result.stdout
        assert "ReadOnlyAccess" in result.stdout
        assert "arn:aws:sso:::permissionSet/ssoins-123/ps-123" in result.stdout

        # Check results summary
        assert "Results Summary" in result.stdout
        assert "Total Accounts: 2" in result.stdout
        assert "Successful: 2" in result.stdout

        # Check metadata
        assert "Metadata" in result.stdout
        assert "source: bulk_assign" in result.stdout
        assert "batch_size: 10" in result.stdout
