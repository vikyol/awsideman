"""Tests for rollback list command."""

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
            metadata={"source": "bulk_assign", "batch_size": 10},
            rolled_back=False,
        ),
        OperationRecord(
            operation_id="op-456-revoke",
            timestamp=now - timedelta(hours=2),
            operation_type=OperationType.REVOKE,
            principal_id="group-456",
            principal_type=PrincipalType.GROUP,
            principal_name="Developers",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
            permission_set_name="PowerUserAccess",
            account_ids=["123456789012", "987654321098"],
            account_names=["Production", "Staging"],
            results=[
                OperationResult(account_id="123456789012", success=True, duration_ms=1200),
                OperationResult(
                    account_id="987654321098", success=False, error="Access denied", duration_ms=800
                ),
            ],
            metadata={"source": "individual_revoke"},
            rolled_back=True,
            rollback_operation_id="op-789-rollback",
        ),
        OperationRecord(
            operation_id="op-789-assign-old",
            timestamp=now - timedelta(days=45),
            operation_type=OperationType.ASSIGN,
            principal_id="user-789",
            principal_type=PrincipalType.USER,
            principal_name="jane.smith",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-789",
            permission_set_name="AdminAccess",
            account_ids=["555666777888"],
            account_names=["Development"],
            results=[OperationResult(account_id="555666777888", success=True, duration_ms=2000)],
            metadata={"source": "bulk_assign"},
            rolled_back=False,
        ),
    ]

    return operations


class TestRollbackListCommand:
    """Test cases for the rollback list command."""

    @patch("src.awsideman.commands.rollback.validate_profile")
    @patch("src.awsideman.commands.rollback.OperationLogger")
    def test_list_operations_basic(
        self, mock_logger_class, mock_validate_profile, runner, sample_operations
    ):
        """Test basic list operations functionality."""
        # Setup mocks
        mock_validate_profile.return_value = ("default", {})
        mock_logger = Mock()
        mock_logger_class.return_value = mock_logger
        mock_logger.get_operations.return_value = sample_operations[:2]  # Return first 2 operations

        # Run command
        result = runner.invoke(app, ["list"])

        # Verify result
        assert result.exit_code == 0
        assert "Operation ID" in result.stdout
        assert "Date" in result.stdout
        assert "Type" in result.stdout
        assert "Princip" in result.stdout  # Header is truncated in table
        assert "Set" in result.stdout  # Permission Set header is truncated
        assert "john.doe" in result.stdout
        assert "Develop" in result.stdout  # "Developers" is truncated
        assert "ReadOnl" in result.stdout  # "ReadOnlyAccess" is truncated
        assert "PowerUs" in result.stdout  # "PowerUserAccess" is truncated

        # Verify logger was called with correct parameters
        mock_logger.get_operations.assert_called_once_with(
            operation_type=None,
            principal=None,
            permission_set=None,
            days=30,
            limit=None,
        )

    def test_list_operations_invalid_operation_type(self, runner):
        """Test list operations with invalid operation type."""
        result = runner.invoke(app, ["list", "--operation-type", "invalid"])

        assert result.exit_code == 1
        assert "Invalid operation type 'invalid'" in result.stdout
        assert "Operation type must be either 'assign' or 'revoke'" in result.stdout
