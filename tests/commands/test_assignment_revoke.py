"""Tests for assignment revoke command."""
from unittest.mock import MagicMock, patch

import pytest
import typer
from botocore.exceptions import ClientError

from src.awsideman.commands.assignment import revoke_permission_set


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
def sample_assignment():
    """Sample assignment data for testing."""
    return {
        "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        "PrincipalId": "user-1234567890abcdef",
        "PrincipalType": "USER",
        "AccountId": "123456789012",
    }


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
@patch("src.awsideman.commands.assignment.resolve_permission_set_info")
@patch("src.awsideman.commands.assignment.resolve_principal_info")
@patch("src.awsideman.commands.assignment.typer.confirm")
@patch("src.awsideman.commands.assignment.console")
def test_revoke_assignment_successful_with_confirmation(
    mock_console,
    mock_confirm,
    mock_resolve_principal,
    mock_resolve_permission_set,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
    sample_assignment,
    sample_permission_set_info,
    sample_principal_info,
):
    """Test successful revoke_assignment operation with confirmation."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Mock the list_account_assignments API response (existing assignment)
    mock_sso_admin.list_account_assignments.return_value = {
        "AccountAssignments": [sample_assignment]
    }

    # Mock the delete_account_assignment API response
    mock_sso_admin.delete_account_assignment.return_value = {
        "AccountAssignmentDeletionStatus": {"Status": "IN_PROGRESS", "RequestId": "request-123"}
    }

    # Mock the resolve functions
    mock_resolve_permission_set.return_value = sample_permission_set_info
    mock_resolve_principal.return_value = sample_principal_info

    # Mock user confirmation
    mock_confirm.return_value = True

    # Call the function
    revoke_permission_set(
        permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        principal_id="user-1234567890abcdef",
        account_id="123456789012",
    )

    # Verify the function called the APIs correctly
    mock_sso_admin.list_account_assignments.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        AccountId="123456789012",
        PermissionSetArn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        PrincipalId="user-1234567890abcdef",
        PrincipalType="USER",
    )

    mock_sso_admin.delete_account_assignment.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        TargetId="123456789012",
        TargetType="AWS_ACCOUNT",
        PermissionSetArn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        PrincipalType="USER",
        PrincipalId="user-1234567890abcdef",
    )

    # Verify resolve functions were called
    mock_resolve_permission_set.assert_called_once()
    mock_resolve_principal.assert_called_once()

    # Verify confirmation was requested
    mock_confirm.assert_called_once()

    # Verify console output includes success message
    mock_console.print.assert_any_call(
        "[green]Permission set assignment revoked successfully![/green]"
    )


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.resolve_permission_set_info")
@patch("src.awsideman.commands.assignment.resolve_principal_info")
@patch("src.awsideman.commands.assignment.console")
def test_revoke_assignment_successful_with_force(
    mock_console,
    mock_resolve_principal,
    mock_resolve_permission_set,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
    sample_assignment,
    sample_permission_set_info,
    sample_principal_info,
):
    """Test successful revoke_assignment operation with force flag."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Mock the list_account_assignments API response (existing assignment)
    mock_sso_admin.list_account_assignments.return_value = {
        "AccountAssignments": [sample_assignment]
    }

    # Mock the delete_account_assignment API response
    mock_sso_admin.delete_account_assignment.return_value = {
        "AccountAssignmentDeletionStatus": {"Status": "IN_PROGRESS", "RequestId": "request-123"}
    }

    # Mock the resolve functions
    mock_resolve_permission_set.return_value = sample_permission_set_info
    mock_resolve_principal.return_value = sample_principal_info

    # Call the function with force flag
    revoke_permission_set(
        permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        principal_id="user-1234567890abcdef",
        account_id="123456789012",
        force=True,
    )

    # Verify the function called the delete API directly without confirmation
    mock_sso_admin.delete_account_assignment.assert_called_once()

    # Verify console output includes success message
    mock_console.print.assert_any_call(
        "[green]Permission set assignment revoked successfully![/green]"
    )


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.resolve_permission_set_info")
@patch("src.awsideman.commands.assignment.resolve_principal_info")
@patch("src.awsideman.commands.assignment.typer.confirm")
@patch("src.awsideman.commands.assignment.console")
def test_revoke_assignment_user_cancels_confirmation(
    mock_console,
    mock_confirm,
    mock_resolve_principal,
    mock_resolve_permission_set,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
    sample_assignment,
    sample_permission_set_info,
    sample_principal_info,
):
    """Test revoke_assignment when user cancels confirmation."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Mock the list_account_assignments API response (existing assignment)
    mock_sso_admin.list_account_assignments.return_value = {
        "AccountAssignments": [sample_assignment]
    }

    # Mock the resolve functions
    mock_resolve_permission_set.return_value = sample_permission_set_info
    mock_resolve_principal.return_value = sample_principal_info

    # Mock user cancellation
    mock_confirm.return_value = False

    # Call the function
    revoke_permission_set(
        permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        principal_id="user-1234567890abcdef",
        account_id="123456789012",
    )

    # Verify the delete API was not called
    mock_sso_admin.delete_account_assignment.assert_not_called()

    # Verify console output includes cancellation message
    mock_console.print.assert_any_call("[yellow]Assignment revocation cancelled.[/yellow]")


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.console")
def test_revoke_assignment_not_found(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
):
    """Test revoke_assignment when assignment is not found."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Mock the list_account_assignments API response with no assignments
    mock_sso_admin.list_account_assignments.return_value = {"AccountAssignments": []}

    # Call the function and expect exit
    with pytest.raises(typer.Exit):
        revoke_permission_set(
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            principal_id="user-1234567890abcdef",
            account_id="123456789012",
        )

    # Verify the console output
    mock_console.print.assert_any_call("[red]Error: Assignment not found.[/red]")
    mock_console.print.assert_any_call("[yellow]No assignment found for:[/yellow]")


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.console")
def test_revoke_assignment_with_group_principal(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
    sample_assignment,
):
    """Test revoke_assignment with GROUP principal type."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Modify sample assignment for group
    group_assignment = sample_assignment.copy()
    group_assignment["PrincipalType"] = "GROUP"
    group_assignment["PrincipalId"] = "group-1234567890abcdef"

    # Mock the list_account_assignments API response
    mock_sso_admin.list_account_assignments.return_value = {
        "AccountAssignments": [group_assignment]
    }

    # Mock the delete_account_assignment API response
    mock_sso_admin.delete_account_assignment.return_value = {
        "AccountAssignmentDeletionStatus": {"Status": "IN_PROGRESS", "RequestId": "request-123"}
    }

    # Call the function with GROUP principal type and force flag
    revoke_permission_set(
        permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        principal_id="group-1234567890abcdef",
        account_id="123456789012",
        principal_type="GROUP",
        force=True,
    )

    # Verify the function called the API with GROUP type
    mock_sso_admin.delete_account_assignment.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        TargetId="123456789012",
        TargetType="AWS_ACCOUNT",
        PermissionSetArn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        PrincipalType="GROUP",
        PrincipalId="group-1234567890abcdef",
    )


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.console")
def test_revoke_assignment_invalid_principal_type(
    mock_console, mock_validate_sso_instance, mock_validate_profile
):
    """Test revoke_assignment with invalid principal type."""
    # Setup mocks
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Call the function with invalid principal type and expect exit
    with pytest.raises(typer.Exit):
        revoke_permission_set(
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            principal_id="user-1234567890abcdef",
            account_id="123456789012",
            principal_type="INVALID",
        )

    # Verify the console output
    mock_console.print.assert_any_call("[red]Error: Invalid principal type 'INVALID'.[/red]")
    mock_console.print.assert_any_call(
        "[yellow]Principal type must be either 'USER' or 'GROUP'.[/yellow]"
    )


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.console")
def test_revoke_assignment_invalid_permission_set_arn(
    mock_console, mock_validate_sso_instance, mock_validate_profile
):
    """Test revoke_assignment with invalid permission set ARN format."""
    # Setup mocks
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Call the function with invalid ARN format and expect exit
    with pytest.raises(typer.Exit):
        revoke_permission_set(
            permission_set_arn="invalid-arn",
            principal_id="user-1234567890abcdef",
            account_id="123456789012",
        )

    # Verify the console output
    mock_console.print.assert_any_call("[red]Error: Invalid permission set ARN format.[/red]")
    mock_console.print.assert_any_call(
        "[yellow]Permission set ARN should start with 'arn:aws:sso:::permissionSet/'.[/yellow]"
    )


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.console")
def test_revoke_assignment_invalid_account_id(
    mock_console, mock_validate_sso_instance, mock_validate_profile
):
    """Test revoke_assignment with invalid account ID format."""
    # Setup mocks
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Call the function with invalid account ID and expect exit
    with pytest.raises(typer.Exit):
        revoke_permission_set(
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            principal_id="user-1234567890abcdef",
            account_id="invalid-account",
        )

    # Verify the console output
    mock_console.print.assert_any_call("[red]Error: Invalid account ID format.[/red]")
    mock_console.print.assert_any_call("[yellow]Account ID should be a 12-digit number.[/yellow]")


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.console")
def test_revoke_assignment_empty_principal_id(
    mock_console, mock_validate_sso_instance, mock_validate_profile
):
    """Test revoke_assignment with empty principal ID."""
    # Setup mocks
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Call the function with empty principal ID and expect exit
    with pytest.raises(typer.Exit):
        revoke_permission_set(
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            principal_id="   ",
            account_id="123456789012",
        )

    # Verify the console output
    mock_console.print.assert_any_call("[red]Error: Principal ID cannot be empty.[/red]")


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.handle_aws_error")
@patch("src.awsideman.commands.assignment.console")
def test_revoke_assignment_api_error(
    mock_console,
    mock_handle_aws_error,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
    sample_assignment,
):
    """Test revoke_assignment with API error."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Mock the list_account_assignments API response (existing assignment)
    mock_sso_admin.list_account_assignments.return_value = {
        "AccountAssignments": [sample_assignment]
    }

    # Mock the delete_account_assignment API error
    error_response = {
        "Error": {
            "Code": "AccessDeniedException",
            "Message": "User is not authorized to perform this action",
        }
    }
    mock_sso_admin.delete_account_assignment.side_effect = ClientError(
        error_response, "DeleteAccountAssignment"
    )

    # Call the function with force flag
    revoke_permission_set(
        permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        principal_id="user-1234567890abcdef",
        account_id="123456789012",
        force=True,
    )

    # Verify the error handler was called
    mock_handle_aws_error.assert_called_once()


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.console")
def test_revoke_assignment_client_creation_failure(
    mock_console, mock_aws_client_manager, mock_validate_sso_instance, mock_validate_profile
):
    """Test revoke_assignment when client creation fails."""
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
        revoke_permission_set(
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            principal_id="user-1234567890abcdef",
            account_id="123456789012",
        )

    # Verify the console output
    mock_console.print.assert_any_call(
        "[red]Error: Failed to create SSO admin client: Client creation failed[/red]"
    )


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.resolve_permission_set_info")
@patch("src.awsideman.commands.assignment.resolve_principal_info")
@patch("src.awsideman.commands.assignment.console")
def test_revoke_assignment_resolve_functions_fail(
    mock_console,
    mock_resolve_principal,
    mock_resolve_permission_set,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
    sample_assignment,
):
    """Test revoke_assignment when resolve functions fail."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Mock the list_account_assignments API response (existing assignment)
    mock_sso_admin.list_account_assignments.return_value = {
        "AccountAssignments": [sample_assignment]
    }

    # Mock the delete_account_assignment API response
    mock_sso_admin.delete_account_assignment.return_value = {
        "AccountAssignmentDeletionStatus": {"Status": "IN_PROGRESS", "RequestId": "request-123"}
    }

    # Mock the resolve functions to raise typer.Exit
    mock_resolve_permission_set.side_effect = typer.Exit(1)
    mock_resolve_principal.side_effect = typer.Exit(1)

    # Call the function with force flag
    revoke_permission_set(
        permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        principal_id="user-1234567890abcdef",
        account_id="123456789012",
        force=True,
    )

    # Verify resolve functions were called
    mock_resolve_permission_set.assert_called_once()
    mock_resolve_principal.assert_called_once()

    # Verify the delete API was still called
    mock_sso_admin.delete_account_assignment.assert_called_once()

    # Verify console output still displays success message with placeholder values
    mock_console.print.assert_any_call(
        "[green]Permission set assignment revoked successfully![/green]"
    )
