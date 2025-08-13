"""Tests for permission set get command."""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
import typer
from botocore.exceptions import ClientError

from src.awsideman.commands.permission_set import get_permission_set


@pytest.fixture
def mock_aws_client():
    """Create a mock AWS client."""
    mock = MagicMock()
    # Mock SSO Admin client
    mock_sso_admin = MagicMock()
    mock.get_client.return_value = mock_sso_admin
    return mock, mock_sso_admin


@pytest.fixture
def sample_permission_set():
    """Sample permission set data for testing."""
    return {
        "Name": "AdminAccess",
        "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        "Description": "Provides admin access to AWS resources",
        "SessionDuration": "PT8H",
        "RelayState": "https://console.aws.amazon.com/",
        "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
        "LastModifiedDate": datetime(2023, 1, 2, 0, 0, 0),
    }


@pytest.fixture
def sample_managed_policies():
    """Sample managed policies for testing."""
    return [
        {"Name": "AdministratorAccess", "Arn": "arn:aws:iam::aws:policy/AdministratorAccess"},
        {"Name": "PowerUserAccess", "Arn": "arn:aws:iam::aws:policy/PowerUserAccess"},
    ]


@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.resolve_permission_set_identifier")
@patch("src.awsideman.commands.permission_set.console")
def test_get_permission_set_by_name_successful(
    mock_console,
    mock_resolve_identifier,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_permission_set,
    sample_managed_policies,
):
    """Test successful get_permission_set operation by name."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )
    mock_resolve_identifier.return_value = sample_permission_set["PermissionSetArn"]

    # Mock the describe_permission_set API response
    mock_sso_admin.describe_permission_set.return_value = {"PermissionSet": sample_permission_set}

    # Mock the list_managed_policies_in_permission_set API response
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = {
        "AttachedManagedPolicies": sample_managed_policies
    }

    # Call the function with permission set name
    result = get_permission_set("AdminAccess")

    # Verify the function called resolve_permission_set_identifier correctly
    mock_resolve_identifier.assert_called_with(
        mock_client, "arn:aws:sso:::instance/ssoins-1234567890abcdef", "AdminAccess"
    )

    # Verify the function called the APIs correctly
    mock_sso_admin.describe_permission_set.assert_called_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        PermissionSetArn=sample_permission_set["PermissionSetArn"],
    )

    mock_sso_admin.list_managed_policies_in_permission_set.assert_called_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        PermissionSetArn=sample_permission_set["PermissionSetArn"],
    )

    # Verify the function returned the correct data
    expected_result = sample_permission_set.copy()
    expected_result["PermissionSetArn"] = sample_permission_set["PermissionSetArn"]
    assert result == expected_result


@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.resolve_permission_set_identifier")
@patch("src.awsideman.commands.permission_set.console")
def test_get_permission_set_resource_not_found_exception(
    mock_console,
    mock_resolve_identifier,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
):
    """Test get_permission_set with ResourceNotFoundException."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )
    mock_resolve_identifier.return_value = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-nonexistent"
    )

    # Mock the describe_permission_set API error
    error_response = {
        "Error": {"Code": "ResourceNotFoundException", "Message": "Permission set not found"}
    }
    mock_sso_admin.describe_permission_set.side_effect = ClientError(
        error_response, "DescribePermissionSet"
    )

    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        get_permission_set("NonExistentPermissionSet")

    # Verify the function called the API correctly
    mock_sso_admin.describe_permission_set.assert_called_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        PermissionSetArn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-nonexistent",
    )

    # Verify the console output
    mock_console.print.assert_any_call(
        "[red]Error: Permission set 'NonExistentPermissionSet' not found.[/red]"
    )
    mock_console.print.assert_any_call(
        "[yellow]Check the permission set name or ARN and try again.[/yellow]"
    )
    mock_console.print.assert_any_call(
        "[yellow]Use 'awsideman permission-set list' to see all available permission sets.[/yellow]"
    )


@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.resolve_permission_set_identifier")
@patch("src.awsideman.commands.permission_set.console")
def test_get_permission_set_invalid_identifier_scenarios(
    mock_console,
    mock_resolve_identifier,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
):
    """Test get_permission_set with invalid identifier scenarios."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Mock resolve_permission_set_identifier to raise typer.Exit (identifier not found)
    mock_resolve_identifier.side_effect = typer.Exit(1)

    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        get_permission_set("InvalidIdentifier")

    # Verify that resolve_permission_set_identifier was called
    mock_resolve_identifier.assert_called_with(
        mock_client, "arn:aws:sso:::instance/ssoins-1234567890abcdef", "InvalidIdentifier"
    )

    # Verify that describe_permission_set was not called since identifier resolution failed
    mock_sso_admin.describe_permission_set.assert_not_called()


@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.resolve_permission_set_identifier")
@patch("src.awsideman.commands.permission_set.console")
def test_get_permission_set_api_error_handling(
    mock_console,
    mock_resolve_identifier,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
):
    """Test get_permission_set with general API error handling."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )
    mock_resolve_identifier.return_value = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    )

    # Mock the describe_permission_set API error
    error_response = {
        "Error": {
            "Code": "AccessDeniedException",
            "Message": "User is not authorized to perform this action",
        }
    }
    mock_sso_admin.describe_permission_set.side_effect = ClientError(
        error_response, "DescribePermissionSet"
    )

    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        get_permission_set("AdminAccess")

    # Verify the function called the API correctly
    mock_sso_admin.describe_permission_set.assert_called_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        PermissionSetArn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
    )

    # Verify the console output
    mock_console.print.assert_any_call(
        "[red]Error: AccessDeniedException - User is not authorized to perform this action[/red]"
    )
    mock_console.print.assert_any_call(
        "[yellow]This could be due to insufficient permissions or an issue with the AWS Identity Center service.[/yellow]"
    )
