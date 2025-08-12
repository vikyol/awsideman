"""Tests for assignment list command."""
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
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
def sample_assignments():
    """Sample assignment data for testing."""
    return [
        {
            "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            "PrincipalId": "user-1234567890abcdef",
            "PrincipalType": "USER",
            "AccountId": "123456789012",
        },
        {
            "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-0987654321fedcba",
            "PrincipalId": "group-1234567890abcdef",
            "PrincipalType": "GROUP",
            "AccountId": "123456789012",
        },
    ]


@pytest.fixture
def sample_permission_set_info():
    """Sample permission set information."""
    return {
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef": {
            "Name": "AdminAccess"
        },
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-0987654321fedcba": {
            "Name": "ReadOnlyAccess"
        },
    }


@pytest.fixture
def sample_principal_info():
    """Sample principal information."""
    return {
        "USER:user-1234567890abcdef": {"DisplayName": "John Doe"},
        "GROUP:group-1234567890abcdef": {"DisplayName": "Administrators"},
    }


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.resolve_permission_set_info")
@patch("src.awsideman.commands.assignment.resolve_principal_info")
@patch("src.awsideman.commands.assignment.console")
def test_list_assignments_successful(
    mock_console,
    mock_resolve_principal,
    mock_resolve_permission_set,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
    sample_assignments,
    sample_permission_set_info,
    sample_principal_info,
):
    """Test successful list_assignments operation."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Mock the list_account_assignments API response
    mock_sso_admin.list_account_assignments.return_value = {
        "AccountAssignments": sample_assignments,
        "NextToken": None,
    }

    # Mock the resolve functions
    def mock_resolve_permission_set_side_effect(instance_arn, permission_set_arn, client):
        return sample_permission_set_info[permission_set_arn]

    def mock_resolve_principal_side_effect(identity_store_id, principal_id, principal_type, client):
        cache_key = f"{principal_type}:{principal_id}"
        return sample_principal_info[cache_key]

    mock_resolve_permission_set.side_effect = mock_resolve_permission_set_side_effect
    mock_resolve_principal.side_effect = mock_resolve_principal_side_effect

    # Call the function using CLI runner
    runner = CliRunner()
    result = runner.invoke(app, ["list"])

    # Verify the command executed successfully
    assert result.exit_code == 0

    # Verify the function calledga the APIs correctly
    mock_sso_admin.list_account_assignments.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef"
    )

    # Verify resolve functions were called for each assignment
    assert mock_resolve_permission_set.call_count == 2
    assert mock_resolve_principal.call_count == 2


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.resolve_permission_set_info")
@patch("src.awsideman.commands.assignment.resolve_principal_info")
@patch("src.awsideman.commands.assignment.console")
def test_list_assignments_with_filters(
    mock_console,
    mock_resolve_principal,
    mock_resolve_permission_set,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
    sample_assignments,
):
    """Test list_assignments with various filters."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Mock the list_account_assignments API response
    mock_sso_admin.list_account_assignments.return_value = {
        "AccountAssignments": sample_assignments,
        "NextToken": None,
    }

    # Mock the resolve functions
    mock_resolve_permission_set.return_value = {"Name": "AdminAccess"}
    mock_resolve_principal.return_value = {"DisplayName": "John Doe"}

    # Call the function with filters using CLI runner
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "list",
            "--account-id",
            "123456789012",
            "--permission-set-arn",
            "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            "--principal-id",
            "user-1234567890abcdef",
            "--principal-type",
            "USER",
        ],
    )

    # Verify the command executed successfully
    assert result.exit_code == 0

    # Verify the function called the API with correct filters
    mock_sso_admin.list_account_assignments.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        AccountId="123456789012",
        PermissionSetArn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
    )


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.resolve_permission_set_info")
@patch("src.awsideman.commands.assignment.resolve_principal_info")
@patch("src.awsideman.commands.assignment.console")
def test_list_assignments_with_pagination(
    mock_console,
    mock_resolve_principal,
    mock_resolve_permission_set,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
    sample_assignments,
):
    """Test list_assignments with pagination."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Mock the list_account_assignments API response with pagination
    mock_sso_admin.list_account_assignments.side_effect = [
        {"AccountAssignments": sample_assignments[:1], "NextToken": "next-token-123"},
        {"AccountAssignments": sample_assignments[1:], "NextToken": None},
    ]

    # Mock the resolve functions
    mock_resolve_permission_set.return_value = {"Name": "AdminAccess"}
    mock_resolve_principal.return_value = {"DisplayName": "John Doe"}

    # Call the function with limit using CLI runner
    runner = CliRunner()
    result = runner.invoke(app, ["list", "--limit", "10"])

    # Verify the command executed successfully
    assert result.exit_code == 0

    # Verify the function called the API twice for pagination
    assert mock_sso_admin.list_account_assignments.call_count == 2

    # Verify first call
    mock_sso_admin.list_account_assignments.assert_any_call(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef", MaxResults=10
    )

    # Verify second call with next token
    mock_sso_admin.list_account_assignments.assert_any_call(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        MaxResults=10,
        NextToken="next-token-123",
    )


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.console")
def test_list_assignments_empty_results(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
):
    """Test list_assignments with empty results."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Mock the list_account_assignments API response with no assignments
    mock_sso_admin.list_account_assignments.return_value = {
        "AccountAssignments": [],
        "NextToken": None,
    }

    # Call the function using CLI runner and expect non-zero exit code
    runner = CliRunner()
    result = runner.invoke(app, ["list"])

    # Verify the command exited with error code
    assert result.exit_code != 0

    # Verify the console output
    mock_console.print.assert_any_call("[yellow]No assignments found.[/yellow]")


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.console")
def test_list_assignments_invalid_principal_type(
    mock_console, mock_aws_client_manager, mock_validate_sso_instance, mock_validate_profile
):
    """Test list_assignments with invalid principal type."""
    # Setup mocks
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Call the function with invalid principal type using CLI runner
    runner = CliRunner()
    result = runner.invoke(app, ["list", "--principal-type", "INVALID"])

    # Verify the command exited with error code
    assert result.exit_code != 0

    # Verify the console output
    mock_console.print.assert_any_call("[red]Error: Invalid principal type 'INVALID'.[/red]")
    mock_console.print.assert_any_call(
        "[yellow]Principal type must be either 'USER' or 'GROUP'.[/yellow]"
    )


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.console")
def test_list_assignments_invalid_limit(
    mock_console, mock_aws_client_manager, mock_validate_sso_instance, mock_validate_profile
):
    """Test list_assignments with invalid limit."""
    # Setup mocks
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Call the function with invalid limit using CLI runner
    runner = CliRunner()
    result = runner.invoke(app, ["list", "--limit", "0"])

    # Verify the command exited with error code
    assert result.exit_code != 0

    # Verify the console output
    mock_console.print.assert_any_call("[red]Error: Limit must be a positive integer.[/red]")


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.handle_aws_error")
@patch("src.awsideman.commands.assignment.console")
def test_list_assignments_api_error(
    mock_console,
    mock_handle_aws_error,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
):
    """Test list_assignments with API error."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Mock the list_account_assignments API error
    error_response = {
        "Error": {
            "Code": "AccessDeniedException",
            "Message": "User is not authorized to perform this action",
        }
    }
    mock_sso_admin.list_account_assignments.side_effect = ClientError(
        error_response, "ListAccountAssignments"
    )

    # Call the function using CLI runner
    runner = CliRunner()
    runner.invoke(app, ["list"])

    # The command should handle the error gracefully
    # Verify the error handler was called
    mock_handle_aws_error.assert_called_once()


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.resolve_permission_set_info")
@patch("src.awsideman.commands.assignment.resolve_principal_info")
@patch("src.awsideman.commands.assignment.console")
def test_list_assignments_principal_id_without_type(
    mock_console,
    mock_resolve_principal,
    mock_resolve_permission_set,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
    sample_assignments,
):
    """Test list_assignments with principal ID but no type (defaults to USER)."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Mock the list_account_assignments API response
    mock_sso_admin.list_account_assignments.return_value = {
        "AccountAssignments": sample_assignments,
        "NextToken": None,
    }

    # Mock the resolve functions
    mock_resolve_permission_set.return_value = {"Name": "AdminAccess"}
    mock_resolve_principal.return_value = {"DisplayName": "John Doe"}

    # Call the function with principal ID but no type using CLI runner
    runner = CliRunner()
    result = runner.invoke(app, ["list", "--principal-id", "user-1234567890abcdef"])

    # Verify the command executed successfully
    assert result.exit_code == 0

    # Verify warning message is displayed
    mock_console.print.assert_any_call(
        "[yellow]Warning: Principal ID provided without principal type. Using default type 'USER' for filtering.[/yellow]"
    )

    # Verify the function called the API with default USER type
    mock_sso_admin.list_account_assignments.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
    )
