"""Tests for assignment assign command."""

from unittest.mock import MagicMock, patch

import pytest
import typer
from botocore.exceptions import ClientError

from src.awsideman.commands.assignment import assign_single_account


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
def sample_permission_set_info():
    """Sample permission set information."""
    return {"Name": "AdminAccess"}


@pytest.fixture
def sample_principal_info():
    """Sample principal information."""
    return {"DisplayName": "John Doe"}


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.resolve_permission_set_identifier")
@patch("src.awsideman.commands.assignment.ResourceResolver")
@patch("src.awsideman.commands.assignment.console")
def test_assign_permission_set_successful(
    mock_console,
    mock_resource_resolver,
    mock_resolve_permission_set,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
    sample_permission_set_info,
    sample_principal_info,
):
    """Test successful assign_single_account operation."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Mock the resolve_permission_set_identifier function
    mock_resolve_permission_set.return_value = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    )

    # Mock the ResourceResolver
    mock_resolver_instance = MagicMock()
    mock_resource_resolver.return_value = mock_resolver_instance
    mock_resolver_instance.resolve_principal_name.return_value = MagicMock(
        success=True, resolved_value="user-1234567890abcdef"
    )

    # Mock the list_account_assignments API response (no existing assignment)
    mock_sso_admin.list_account_assignments.return_value = {"AccountAssignments": []}

    # Mock the create_account_assignment API response
    mock_sso_admin.create_account_assignment.return_value = {
        "AccountAssignmentCreationStatus": {"Status": "IN_PROGRESS", "RequestId": "request-123"}
    }

    # Call the function
    assign_single_account("AdminAccess", "john.doe@company.com", "123456789012")

    # Verify the function called the APIs correctly
    mock_sso_admin.list_account_assignments.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        AccountId="123456789012",
        PermissionSetArn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
    )

    mock_sso_admin.create_account_assignment.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        TargetId="123456789012",
        TargetType="AWS_ACCOUNT",
        PermissionSetArn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        PrincipalType="USER",
        PrincipalId="user-1234567890abcdef",
    )

    # Verify resolve functions were called
    mock_resolve_permission_set.assert_called_once()
    mock_resolver_instance.resolve_principal_name.assert_called_once()

    # Verify console output includes success message
    mock_console.print.assert_any_call(
        "[green]✓ Assignment creation initiated successfully.[/green]"
    )


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.resolve_permission_set_identifier")
@patch("src.awsideman.commands.assignment.ResourceResolver")
@patch("src.awsideman.commands.assignment.console")
def test_assign_permission_set_with_group(
    mock_console,
    mock_resource_resolver,
    mock_resolve_permission_set,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
    sample_permission_set_info,
    sample_principal_info,
):
    """Test assign_single_account with GROUP principal type."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Mock the resolve_permission_set_identifier function
    mock_resolve_permission_set.return_value = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    )

    # Mock the ResourceResolver
    mock_resolver_instance = MagicMock()
    mock_resource_resolver.return_value = mock_resolver_instance
    mock_resolver_instance.resolve_principal_name.return_value = MagicMock(
        success=True, resolved_value="group-1234567890abcdef"
    )

    # Mock the list_account_assignments API response (no existing assignment)
    mock_sso_admin.list_account_assignments.return_value = {"AccountAssignments": []}

    # Mock the create_account_assignment API response
    mock_sso_admin.create_account_assignment.return_value = {
        "AccountAssignmentCreationStatus": {"Status": "IN_PROGRESS", "RequestId": "request-123"}
    }

    # Call the function with GROUP principal type
    assign_single_account("AdminAccess", "developers", "123456789012", principal_type="GROUP")

    # Verify the function called the API with GROUP type
    mock_sso_admin.create_account_assignment.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        TargetId="123456789012",
        TargetType="AWS_ACCOUNT",
        PermissionSetArn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        PrincipalType="GROUP",
        PrincipalId="group-1234567890abcdef",
    )


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.resolve_permission_set_identifier")
@patch("src.awsideman.commands.assignment.ResourceResolver")
@patch("src.awsideman.commands.assignment.console")
def test_assign_permission_set_already_exists(
    mock_console,
    mock_resource_resolver,
    mock_resolve_permission_set,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
    sample_permission_set_info,
    sample_principal_info,
):
    """Test assign_single_account when assignment already exists."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Mock the resolve_permission_set_identifier function
    mock_resolve_permission_set.return_value = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    )

    # Mock the ResourceResolver
    mock_resolver_instance = MagicMock()
    mock_resource_resolver.return_value = mock_resolver_instance
    mock_resolver_instance.resolve_principal_name.return_value = MagicMock(
        success=True, resolved_value="user-1234567890abcdef"
    )

    # Mock the list_account_assignments API response (existing assignment)
    mock_sso_admin.list_account_assignments.return_value = {
        "AccountAssignments": [
            {
                "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
                "PrincipalId": "user-1234567890abcdef",
                "PrincipalType": "USER",
                "AccountId": "123456789012",
            }
        ]
    }

    # Call the function
    assign_single_account("AdminAccess", "john.doe@company.com", "123456789012")

    # Verify create_account_assignment was not called
    mock_sso_admin.create_account_assignment.assert_not_called()

    # Verify console output includes already exists message
    mock_console.print.assert_any_call("[yellow]Assignment already exists.[/yellow]")


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.console")
def test_assign_permission_set_invalid_principal_type(
    mock_console, mock_validate_sso_instance, mock_validate_profile
):
    """Test assign_single_account with invalid principal type."""
    # Setup mocks
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Call the function with invalid principal type and expect exit
    with pytest.raises(typer.Exit):
        assign_single_account(
            "AdminAccess", "john.doe@company.com", "123456789012", principal_type="INVALID"
        )

    # Verify the console output
    mock_console.print.assert_any_call("[red]Error: Invalid principal type 'INVALID'.[/red]")
    mock_console.print.assert_any_call(
        "[yellow]Principal type must be either 'USER' or 'GROUP'.[/yellow]"
    )


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.console")
def test_assign_permission_set_invalid_permission_set_arn(
    mock_console, mock_validate_sso_instance, mock_validate_profile
):
    """Test assign_single_account with invalid permission set name."""
    # Setup mocks
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Call the function with empty permission set name and expect exit
    with pytest.raises(typer.Exit):
        assign_single_account("", "john.doe@company.com", "123456789012")

    # Verify the console output
    mock_console.print.assert_any_call("[red]Error: Permission set name cannot be empty.[/red]")


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.console")
def test_assign_permission_set_invalid_account_id(
    mock_console, mock_validate_sso_instance, mock_validate_profile
):
    """Test assign_single_account with invalid account ID format."""
    # Setup mocks
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Call the function with invalid account ID and expect exit
    with pytest.raises(typer.Exit):
        assign_single_account("AdminAccess", "john.doe@company.com", "invalid-account")

    # Verify the console output
    mock_console.print.assert_any_call("[red]Error: Invalid account ID format.[/red]")
    mock_console.print.assert_any_call("[yellow]Account ID should be a 12-digit number.[/yellow]")


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.console")
def test_assign_permission_set_empty_principal_id(
    mock_console, mock_validate_sso_instance, mock_validate_profile
):
    """Test assign_single_account with empty principal name."""
    # Setup mocks
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Call the function with empty principal name and expect exit
    with pytest.raises(typer.Exit):
        assign_single_account("AdminAccess", "   ", "123456789012")

    # Verify the console output
    mock_console.print.assert_any_call("[red]Error: Principal name cannot be empty.[/red]")


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.resolve_permission_set_identifier")
@patch("src.awsideman.commands.assignment.ResourceResolver")
@patch("src.awsideman.commands.assignment.handle_aws_error")
@patch("src.awsideman.commands.assignment.console")
def test_assign_permission_set_api_error(
    mock_console,
    mock_handle_aws_error,
    mock_resource_resolver,
    mock_resolve_permission_set,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
):
    """Test assign_single_account with API error."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Mock the resolve_permission_set_identifier function
    mock_resolve_permission_set.return_value = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    )

    # Mock the ResourceResolver
    mock_resolver_instance = MagicMock()
    mock_resource_resolver.return_value = mock_resolver_instance
    mock_resolver_instance.resolve_principal_name.return_value = MagicMock(
        success=True, resolved_value="user-1234567890abcdef"
    )

    # Mock the list_account_assignments API response (no existing assignment)
    mock_sso_admin.list_account_assignments.return_value = {"AccountAssignments": []}

    # Mock the create_account_assignment API error
    error_response = {
        "Error": {
            "Code": "AccessDeniedException",
            "Message": "User is not authorized to perform this action",
        }
    }
    mock_sso_admin.create_account_assignment.side_effect = ClientError(
        error_response, "CreateAccountAssignment"
    )

    # Call the function
    assign_single_account("AdminAccess", "john.doe@company.com", "123456789012")

    # Verify the error handler was called
    mock_handle_aws_error.assert_called_once()


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.console")
def test_assign_permission_set_client_creation_failure(
    mock_console, mock_aws_client_manager, mock_validate_sso_instance, mock_validate_profile
):
    """Test assign_single_account when client creation fails."""
    # Setup mocks
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Mock client creation failure
    mock_aws_client_manager.return_value.get_sso_admin_client.side_effect = Exception(
        "Client creation failed"
    )

    # Call the function and expect exit
    with pytest.raises(typer.Exit):
        assign_single_account("AdminAccess", "john.doe@company.com", "123456789012")

    # Verify the console output
    mock_console.print.assert_any_call(
        "[red]Error: Failed to create SSO admin client: Client creation failed[/red]"
    )


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.resolve_permission_set_identifier")
@patch("src.awsideman.commands.assignment.ResourceResolver")
@patch("src.awsideman.commands.assignment.console")
def test_assign_permission_set_resolve_functions_fail(
    mock_console,
    mock_resource_resolver,
    mock_resolve_permission_set,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
):
    """Test assign_single_account when resolve functions fail."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Mock the resolve_permission_set_identifier function to raise typer.Exit
    mock_resolve_permission_set.side_effect = typer.Exit(1)

    # Call the function and expect exit
    with pytest.raises(typer.Exit):
        assign_single_account("AdminAccess", "john.doe@company.com", "123456789012")

    # Verify resolve function was called
    mock_resolve_permission_set.assert_called_once()


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.resolve_permission_set_identifier")
@patch("src.awsideman.commands.assignment.ResourceResolver")
@patch("src.awsideman.commands.assignment.handle_aws_error")
@patch("src.awsideman.commands.assignment.console")
def test_assign_permission_set_duplicate_assignment_handling(
    mock_console,
    mock_handle_aws_error,
    mock_resource_resolver,
    mock_resolve_permission_set,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
    sample_permission_set_info,
    sample_principal_info,
):
    """Test assign_single_account handles duplicate assignment error from API."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Mock the resolve_permission_set_identifier function
    mock_resolve_permission_set.return_value = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    )

    # Mock the ResourceResolver
    mock_resolver_instance = MagicMock()
    mock_resource_resolver.return_value = mock_resolver_instance
    mock_resolver_instance.resolve_principal_name.return_value = MagicMock(
        success=True, resolved_value="user-1234567890abcdef"
    )

    # Mock the list_account_assignments API response (no existing assignment)
    mock_sso_admin.list_account_assignments.return_value = {"AccountAssignments": []}

    # Mock the create_account_assignment API error for duplicate
    error_response = {
        "Error": {"Code": "ConflictException", "Message": "Assignment already exists"}
    }
    mock_sso_admin.create_account_assignment.side_effect = ClientError(
        error_response, "CreateAccountAssignment"
    )

    # Call the function
    assign_single_account("AdminAccess", "john.doe@company.com", "123456789012")

    # Verify the function attempted to create the assignment
    mock_sso_admin.create_account_assignment.assert_called_once()

    # Verify the error handler was called
    mock_handle_aws_error.assert_called_once()
