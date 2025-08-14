"""Integration tests for rollback commands."""

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
def sample_operation():
    """Create a sample operation for testing."""
    now = datetime.now(timezone.utc)

    return OperationRecord(
        operation_id="op-integration-test",
        timestamp=now - timedelta(hours=1),
        operation_type=OperationType.ASSIGN,
        principal_id="user-integration",
        principal_type=PrincipalType.USER,
        principal_name="integration.user",
        permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-integration",
        permission_set_name="IntegrationTestAccess",
        account_ids=["123456789012"],
        account_names=["TestAccount"],
        results=[OperationResult(account_id="123456789012", success=True, duration_ms=1500)],
        metadata={"source": "integration_test"},
        rolled_back=False,
    )


class TestRollbackIntegration:
    """Integration test cases for rollback commands."""

    @patch("src.awsideman.commands.rollback.validate_profile")
    @patch("src.awsideman.commands.rollback.OperationLogger")
    def test_list_and_apply_workflow(
        self, mock_logger_class, mock_validate_profile, runner, sample_operation
    ):
        """Test the complete workflow of listing operations and applying rollback."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", {})
        mock_logger = Mock()
        mock_logger_class.return_value = mock_logger

        # Test 1: List operations
        mock_logger.get_operations.return_value = [sample_operation]

        result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        assert "op-integ..." in result.stdout  # Operation ID truncated
        assert "integra" in result.stdout  # "integration.user" is truncated
        assert "Integrat" in result.stdout  # "IntegrationTestAccess" is truncated

        # Test 2: Apply rollback in dry-run mode
        mock_logger.get_operation.return_value = sample_operation

        result = runner.invoke(app, ["apply", "op-integration-test", "--dry-run"])

        assert result.exit_code == 0
        assert "Found operation: assign operation" in result.stdout
        assert "The following assignments will be revoked:" in result.stdout
        assert "integration.user" in result.stdout
        assert "IntegrationTestAccess" in result.stdout
        assert "TestAccount" in result.stdout and "123456789012" in result.stdout
        assert "REVOKE" in result.stdout
        assert "Dry-run completed successfully!" in result.stdout

        # Verify that the logger was called correctly
        mock_logger.get_operation.assert_called_with("op-integration-test")

    @patch("src.awsideman.commands.rollback.validate_profile")
    @patch("src.awsideman.commands.rollback.OperationLogger")
    def test_status_command_integration(
        self, mock_logger_class, mock_validate_profile, runner, sample_operation
    ):
        """Test the status command integration."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", {})
        mock_logger = Mock()
        mock_logger_class.return_value = mock_logger

        # Mock storage stats and operations
        mock_logger.get_storage_stats.return_value = {"file_count": 1}
        mock_logger.get_operations.side_effect = [
            [sample_operation],  # Recent operations
            [sample_operation],  # All operations
        ]

        result = runner.invoke(app, ["status"])

        assert result.exit_code == 0
        assert "Rollback System Status" in result.stdout
        assert "Total Operations" in result.stdout
        assert "1" in result.stdout  # Should show 1 operation
        assert "Assign Operations" in result.stdout
        assert "System Health" in result.stdout
        assert "Healthy" in result.stdout
        assert "Recent Activity (Last 7 Days)" in result.stdout

        # Verify logger calls
        assert mock_logger.get_operations.call_count == 2
        mock_logger.get_storage_stats.assert_called_once()

    @patch("src.awsideman.commands.rollback.validate_profile")
    @patch("src.awsideman.commands.rollback.OperationLogger")
    def test_json_output_integration(
        self, mock_logger_class, mock_validate_profile, runner, sample_operation
    ):
        """Test JSON output format integration."""
        # Setup mocks
        mock_validate_profile.return_value = ("test-profile", {})
        mock_logger = Mock()
        mock_logger_class.return_value = mock_logger
        mock_logger.get_operations.return_value = [sample_operation]

        # Test JSON output
        result = runner.invoke(app, ["list", "--format", "json"])

        assert result.exit_code == 0

        # Parse JSON output
        import json

        output_data = json.loads(result.stdout)

        # Verify JSON structure
        assert "operations" in output_data
        assert "total_count" in output_data
        assert "filters" in output_data
        assert "profile" in output_data

        assert output_data["total_count"] == 1
        assert output_data["profile"] == "test-profile"
        assert len(output_data["operations"]) == 1

        # Verify operation data
        operation_data = output_data["operations"][0]
        assert operation_data["operation_id"] == "op-integration-test"
        assert operation_data["operation_type"] == "assign"
        assert operation_data["principal_name"] == "integration.user"
        assert operation_data["permission_set_name"] == "IntegrationTestAccess"
        assert operation_data["rolled_back"] is False

    @patch("src.awsideman.commands.rollback.validate_profile")
    @patch("src.awsideman.commands.rollback.OperationLogger")
    def test_error_handling_integration(self, mock_logger_class, mock_validate_profile, runner):
        """Test error handling across different commands."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", {})

        # Test 1: Logger initialization error affects all commands
        mock_logger_class.side_effect = Exception("Storage error")

        # List command should fail
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 1
        assert "Failed to initialize operation logger" in result.stdout

        # Apply command should fail
        result = runner.invoke(app, ["apply", "op-123"])
        assert result.exit_code == 1
        assert "Failed to initialize operation logger" in result.stdout

        # Status command should fail
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 1
        assert "Failed to initialize operation logger" in result.stdout

        # Test 2: Operation not found error
        mock_logger_class.side_effect = None  # Reset
        mock_logger = Mock()
        mock_logger_class.return_value = mock_logger
        mock_logger.get_operation.return_value = None

        result = runner.invoke(app, ["apply", "nonexistent-op"])
        assert result.exit_code == 1
        assert "Operation not found: nonexistent-op" in result.stdout

    @patch("src.awsideman.commands.rollback.validate_profile")
    @patch("src.awsideman.commands.rollback.OperationLogger")
    def test_filtering_integration(self, mock_logger_class, mock_validate_profile, runner):
        """Test filtering functionality integration."""
        # Create multiple operations for filtering tests
        now = datetime.now(timezone.utc)

        operations = [
            OperationRecord(
                operation_id="op-assign-1",
                timestamp=now - timedelta(hours=1),
                operation_type=OperationType.ASSIGN,
                principal_id="user-1",
                principal_type=PrincipalType.USER,
                principal_name="user.one",
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-1",
                permission_set_name="ReadOnlyAccess",
                account_ids=["123456789012"],
                account_names=["Production"],
                results=[
                    OperationResult(account_id="123456789012", success=True, duration_ms=1000)
                ],
                metadata={},
                rolled_back=False,
            ),
            OperationRecord(
                operation_id="op-revoke-1",
                timestamp=now - timedelta(hours=2),
                operation_type=OperationType.REVOKE,
                principal_id="group-1",
                principal_type=PrincipalType.GROUP,
                principal_name="developers",
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-2",
                permission_set_name="PowerUserAccess",
                account_ids=["987654321098"],
                account_names=["Staging"],
                results=[
                    OperationResult(account_id="987654321098", success=True, duration_ms=1200)
                ],
                metadata={},
                rolled_back=False,
            ),
        ]

        # Setup mocks
        mock_validate_profile.return_value = ("default", {})
        mock_logger = Mock()
        mock_logger_class.return_value = mock_logger

        # Test filtering by operation type
        mock_logger.get_operations.return_value = [operations[0]]  # Only assign operation

        result = runner.invoke(app, ["list", "--operation-type", "assign"])

        assert result.exit_code == 0
        assert "user.one" in result.stdout
        assert "ReadOnl" in result.stdout  # Truncated

        # Verify filter was passed to logger
        mock_logger.get_operations.assert_called_with(
            operation_type="assign",
            principal=None,
            permission_set=None,
            days=30,
            limit=None,
        )

        # Test filtering by principal
        mock_logger.get_operations.return_value = [operations[1]]  # Only group operation

        result = runner.invoke(app, ["list", "--principal", "developers"])

        assert result.exit_code == 0
        assert "developers" in result.stdout
        assert "PowerUs" in result.stdout  # Truncated

        # Verify filter was passed to logger
        mock_logger.get_operations.assert_called_with(
            operation_type=None,
            principal="developers",
            permission_set=None,
            days=30,
            limit=None,
        )
