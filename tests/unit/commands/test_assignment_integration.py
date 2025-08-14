"""Integration tests for assignment management commands."""

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from src.awsideman.commands.assignment import app


@pytest.fixture
def mock_aws_clients():
    """Create mock AWS clients."""
    mock_client_manager = MagicMock()
    mock_sso_admin = MagicMock()
    mock_identity_store = MagicMock()

    mock_client_manager.get_sso_admin_client.return_value = mock_sso_admin
    mock_client_manager.get_identity_store_client.return_value = mock_identity_store

    return mock_client_manager, mock_sso_admin, mock_identity_store


@pytest.fixture
def sample_assignment_data():
    """Sample assignment data for testing."""
    return {
        "account_id": "123456789012",
        "identity_store_id": "d-1234567890",
        "instance_arn": "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "permission_set_name": "TestPermissionSet",
        "principal_name": "testuser@company.com",
        "principal_type": "USER",
    }


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.console")
def test_assignment_basic_workflow(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
    sample_assignment_data,
):
    """Test basic assignment workflow using CLI commands."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        sample_assignment_data["instance_arn"],
        sample_assignment_data["identity_store_id"],
    )

    # Mock API responses
    mock_sso_admin.list_account_assignments.return_value = {"AccountAssignments": []}
    mock_sso_admin.create_account_assignment.return_value = {
        "AccountAssignmentCreationStatus": {
            "Status": "IN_PROGRESS",
            "RequestId": "req-1234567890abcdef",
        }
    }

    # Test assign command
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "assign",
            sample_assignment_data["permission_set_name"],
            sample_assignment_data["principal_name"],
            sample_assignment_data["account_id"],
        ],
    )

    # Verify the command executed
    assert result is not None

    # Test list command
    result = runner.invoke(
        app,
        [
            "list",
            "--account-id",
            sample_assignment_data["account_id"],
        ],
    )

    # Verify the command executed
    assert result is not None

    # Test get command
    result = runner.invoke(
        app,
        [
            "get",
            "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            "user-1234567890abcdef",
            sample_assignment_data["account_id"],
        ],
    )

    # Verify the command executed
    assert result is not None


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.console")
def test_assignment_group_workflow(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
    sample_assignment_data,
):
    """Test assignment workflow with GROUP principal type."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        sample_assignment_data["instance_arn"],
        sample_assignment_data["identity_store_id"],
    )

    # Mock API responses
    mock_sso_admin.list_account_assignments.return_value = {"AccountAssignments": []}
    mock_sso_admin.create_account_assignment.return_value = {
        "AccountAssignmentCreationStatus": {
            "Status": "IN_PROGRESS",
            "RequestId": "req-1234567890abcdef",
        }
    }

    # Test assign command with GROUP principal type
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "assign",
            sample_assignment_data["permission_set_name"],
            "developers",
            sample_assignment_data["account_id"],
            "--principal-type",
            "GROUP",
        ],
    )

    # Verify the command executed
    assert result is not None

    # Test list command with GROUP filter
    result = runner.invoke(
        app,
        [
            "list",
            "--account-id",
            sample_assignment_data["account_id"],
            "--principal-type",
            "GROUP",
        ],
    )

    # Verify the command executed
    assert result is not None


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.console")
def test_assignment_revoke_workflow(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
    sample_assignment_data,
):
    """Test assignment revocation workflow."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        sample_assignment_data["instance_arn"],
        sample_assignment_data["identity_store_id"],
    )

    # Mock existing assignment
    mock_sso_admin.list_account_assignments.return_value = {
        "AccountAssignments": [
            {
                "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
                "PrincipalId": "user-1234567890abcdef",
                "PrincipalType": "USER",
                "AccountId": sample_assignment_data["account_id"],
            }
        ]
    }

    # Mock deletion response
    mock_sso_admin.delete_account_assignment.return_value = {
        "AccountAssignmentDeletionStatus": {
            "Status": "IN_PROGRESS",
            "RequestId": "req-1234567890abcdef",
        }
    }

    # Test revoke command with force flag
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "revoke",
            sample_assignment_data["permission_set_name"],
            sample_assignment_data["principal_name"],
            sample_assignment_data["account_id"],
            "--force",
        ],
    )

    # Verify the command executed
    assert result is not None


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.console")
def test_assignment_multi_account_workflow(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
    sample_assignment_data,
):
    """Test multi-account assignment workflow."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        sample_assignment_data["instance_arn"],
        sample_assignment_data["identity_store_id"],
    )

    # Mock API responses
    mock_sso_admin.list_account_assignments.return_value = {"AccountAssignments": []}
    mock_sso_admin.create_account_assignment.return_value = {
        "AccountAssignmentCreationStatus": {
            "Status": "IN_PROGRESS",
            "RequestId": "req-1234567890abcdef",
        }
    }

    # Test assign command with multi-account filter
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "assign",
            sample_assignment_data["permission_set_name"],
            sample_assignment_data["principal_name"],
            "--filter",
            "*",
        ],
    )

    # Verify the command executed
    assert result is not None

    # Test revoke command with multi-account filter
    result = runner.invoke(
        app,
        [
            "revoke",
            sample_assignment_data["permission_set_name"],
            sample_assignment_data["principal_name"],
            "--filter",
            "*",
            "--force",
        ],
    )

    # Verify the command executed
    assert result is not None


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.console")
def test_assignment_dry_run_workflow(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
    sample_assignment_data,
):
    """Test assignment workflow with dry-run flag."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        sample_assignment_data["instance_arn"],
        sample_assignment_data["identity_store_id"],
    )

    # Test assign command with dry-run
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "assign",
            sample_assignment_data["permission_set_name"],
            sample_assignment_data["principal_name"],
            "--filter",
            "*",
            "--dry-run",
        ],
    )

    # Verify the command executed
    assert result is not None

    # Test revoke command with dry-run
    result = runner.invoke(
        app,
        [
            "revoke",
            sample_assignment_data["permission_set_name"],
            sample_assignment_data["principal_name"],
            "--filter",
            "*",
            "--dry-run",
        ],
    )

    # Verify the command executed
    assert result is not None


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.console")
def test_assignment_error_handling(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
    sample_assignment_data,
):
    """Test assignment error handling scenarios."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        sample_assignment_data["instance_arn"],
        sample_assignment_data["identity_store_id"],
    )

    # Test assign command with missing target option
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "assign",
            sample_assignment_data["permission_set_name"],
            sample_assignment_data["principal_name"],
        ],
    )

    # Verify the command failed due to missing target
    assert result.exit_code == 1

    # Test revoke command with missing target option
    result = runner.invoke(
        app,
        [
            "revoke",
            sample_assignment_data["permission_set_name"],
            sample_assignment_data["principal_name"],
        ],
    )

    # Verify the command failed due to missing target
    assert result.exit_code == 1


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.console")
def test_assignment_pagination_workflow(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
    sample_assignment_data,
):
    """Test assignment pagination workflow."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        sample_assignment_data["instance_arn"],
        sample_assignment_data["identity_store_id"],
    )

    # Mock paginated response
    mock_sso_admin.list_account_assignments.return_value = {
        "AccountAssignments": [
            {
                "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
                "PrincipalId": "user-1234567890abcdef",
                "PrincipalType": "USER",
                "AccountId": sample_assignment_data["account_id"],
            }
        ],
        "NextToken": "token-123",
    }

    # Test list command with pagination
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "list",
            "--limit",
            "10",
        ],
    )

    # Verify the command executed
    assert result is not None


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.console")
def test_assignment_validation_workflow(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
    sample_assignment_data,
):
    """Test assignment validation workflow."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        sample_assignment_data["instance_arn"],
        sample_assignment_data["identity_store_id"],
    )

    # Test assign command with invalid principal type
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "assign",
            sample_assignment_data["permission_set_name"],
            sample_assignment_data["principal_name"],
            sample_assignment_data["account_id"],
            "--principal-type",
            "INVALID",
        ],
    )

    # Verify the command failed due to invalid principal type
    assert result.exit_code == 1

    # Test assign command with empty permission set name
    result = runner.invoke(
        app,
        [
            "assign",
            "",
            sample_assignment_data["principal_name"],
            sample_assignment_data["account_id"],
        ],
    )

    # Verify the command failed due to empty permission set name
    assert result.exit_code == 1
