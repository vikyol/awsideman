"""Tests for permission set helper functions."""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
import typer
from botocore.exceptions import ClientError

from src.awsideman.commands.permission_set import (
    format_permission_set_for_display,
    resolve_permission_set_identifier,
    validate_aws_managed_policy_arn,
    validate_permission_set_description,
    validate_permission_set_name,
)


# Test validate_permission_set_name function
@patch("src.awsideman.commands.permission_set.console")
def test_validate_permission_set_name_valid(mock_console):
    """Test validate_permission_set_name with valid names."""
    valid_names = [
        "TestPermissionSet",
        "test-permission-set",
        "test_permission_set",
        "test.permission.set",
        "test@permission+set",
        "123456",
        "a" * 32,  # Maximum length
    ]

    for name in valid_names:
        assert validate_permission_set_name(name) is True
        mock_console.print.assert_not_called()
        mock_console.reset_mock()


@patch("src.awsideman.commands.permission_set.console")
def test_validate_permission_set_name_empty(mock_console):
    """Test validate_permission_set_name with empty name."""
    assert validate_permission_set_name("") is False
    mock_console.print.assert_called_once_with(
        "[red]Error: Permission set name cannot be empty.[/red]"
    )


@patch("src.awsideman.commands.permission_set.console")
def test_validate_permission_set_name_too_long(mock_console):
    """Test validate_permission_set_name with name exceeding maximum length."""
    assert validate_permission_set_name("a" * 33) is False
    mock_console.print.assert_called_once_with(
        "[red]Error: Permission set name cannot exceed 32 characters.[/red]"
    )


@patch("src.awsideman.commands.permission_set.console")
def test_validate_permission_set_name_invalid_characters(mock_console):
    """Test validate_permission_set_name with invalid characters."""
    invalid_names = [
        "test/permission/set",
        "test\\permission\\set",
        "test:permission:set",
        "test*permission*set",
        "test?permission?set",
        "test<permission>set",
        "test|permission|set",
        'test"permission"set',
        "test'permission'set",
        "test permission set",  # Space is invalid
    ]

    for name in invalid_names:
        assert validate_permission_set_name(name) is False
        mock_console.print.assert_any_call(
            "[red]Error: Permission set name contains invalid characters.[/red]"
        )
        mock_console.print.assert_any_call(
            "[yellow]Permission set names can only contain alphanumeric characters and the following special characters: +=,.@_-[/yellow]"
        )
        mock_console.reset_mock()


# Test validate_permission_set_description function
@patch("src.awsideman.commands.permission_set.console")
def test_validate_permission_set_description_valid(mock_console):
    """Test validate_permission_set_description with valid descriptions."""
    valid_descriptions = [
        "This is a valid description",
        "This is a valid description with special characters: !@#$%^&*()_+-=[]{}|;':\",./<>?",
        "a" * 700,  # Maximum length
        None,  # None is valid (optional description)
    ]

    for description in valid_descriptions:
        assert validate_permission_set_description(description) is True
        mock_console.print.assert_not_called()
        mock_console.reset_mock()


@patch("src.awsideman.commands.permission_set.console")
def test_validate_permission_set_description_too_long(mock_console):
    """Test validate_permission_set_description with description exceeding maximum length."""
    assert validate_permission_set_description("a" * 701) is False
    mock_console.print.assert_called_once_with(
        "[red]Error: Permission set description cannot exceed 700 characters.[/red]"
    )


# Test validate_aws_managed_policy_arn function
@patch("src.awsideman.commands.permission_set.console")
def test_validate_aws_managed_policy_arn_valid(mock_console):
    """Test validate_aws_managed_policy_arn with valid ARNs."""
    valid_arns = [
        "arn:aws:iam::aws:policy/AdministratorAccess",
        "arn:aws:iam::aws:policy/job-function/ViewOnlyAccess",
        "arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess",
        "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy",
    ]

    for arn in valid_arns:
        assert validate_aws_managed_policy_arn(arn) is True
        mock_console.print.assert_not_called()
        mock_console.reset_mock()


@patch("src.awsideman.commands.permission_set.console")
def test_validate_aws_managed_policy_arn_empty(mock_console):
    """Test validate_aws_managed_policy_arn with empty ARN."""
    assert validate_aws_managed_policy_arn("") is False
    mock_console.print.assert_called_once_with("[red]Error: Policy ARN cannot be empty.[/red]")


@patch("src.awsideman.commands.permission_set.console")
def test_validate_aws_managed_policy_arn_invalid_format(mock_console):
    """Test validate_aws_managed_policy_arn with invalid ARN format."""
    invalid_arns = [
        "AdministratorAccess",
        "arn:aws:iam::123456789012:policy/MyCustomPolicy",  # Customer managed policy
        "arn:aws:s3:::my-bucket",  # Not a policy ARN
        "arn:aws:iam::aws:role/service-role/AmazonECSTaskExecutionRole",  # Role ARN, not policy
    ]

    for arn in invalid_arns:
        assert validate_aws_managed_policy_arn(arn) is False
        mock_console.print.assert_any_call("[red]Error: Invalid AWS managed policy ARN.[/red]")
        mock_console.print.assert_any_call(
            "[yellow]AWS managed policy ARNs should start with 'arn:aws:iam::aws:policy/'.[/yellow]"
        )
        mock_console.print.assert_any_call(
            "[yellow]Example: arn:aws:iam::aws:policy/AdministratorAccess[/yellow]"
        )
        mock_console.reset_mock()


# Test format_permission_set_for_display function
def test_format_permission_set_for_display_basic():
    """Test format_permission_set_for_display with basic permission set data."""
    permission_set = {
        "Name": "TestPermissionSet",
        "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        "Description": "Test permission set description",
        "SessionDuration": "PT8H",
        "RelayState": "https://console.aws.amazon.com/",
        "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
        "LastModifiedDate": datetime(2023, 1, 2, 0, 0, 0),
    }

    formatted = format_permission_set_for_display(permission_set)

    assert formatted["Name"] == "TestPermissionSet"
    assert (
        formatted["ARN"]
        == "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    )
    assert formatted["Description"] == "Test permission set description"
    assert formatted["Session Duration"] == "8 hour(s)"
    assert formatted["Relay State"] == "https://console.aws.amazon.com/"
    assert formatted["Created"] == "2023-01-01 00:00:00"
    assert formatted["Last Modified"] == "2023-01-02 00:00:00"


def test_format_permission_set_for_display_missing_fields():
    """Test format_permission_set_for_display with missing fields."""
    permission_set = {
        "Name": "TestPermissionSet",
        "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
    }

    formatted = format_permission_set_for_display(permission_set)

    assert formatted["Name"] == "TestPermissionSet"
    assert (
        formatted["ARN"]
        == "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    )
    assert formatted["Description"] == "N/A"
    assert formatted["Session Duration"] == "1 hour(s)"  # Default is PT1H
    assert formatted["Relay State"] == "N/A"
    assert "Created" not in formatted
    assert "Last Modified" not in formatted


def test_format_permission_set_for_display_minutes_duration():
    """Test format_permission_set_for_display with minutes duration."""
    permission_set = {
        "Name": "TestPermissionSet",
        "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        "SessionDuration": "PT30M",
    }

    formatted = format_permission_set_for_display(permission_set)

    assert formatted["Session Duration"] == "30 minute(s)"


def test_format_permission_set_for_display_custom_duration():
    """Test format_permission_set_for_display with custom duration format."""
    permission_set = {
        "Name": "TestPermissionSet",
        "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        "SessionDuration": "P1DT2H",  # Non-standard format
    }

    formatted = format_permission_set_for_display(permission_set)

    assert formatted["Session Duration"] == "P1DT2H"  # Should be preserved as-is


# Test resolve_permission_set_identifier function
@patch("src.awsideman.commands.permission_set.console")
def test_resolve_permission_set_identifier_with_arn(mock_console):
    """Test resolve_permission_set_identifier with ARN."""
    aws_client = MagicMock()
    instance_arn = "arn:aws:sso:::instance/ssoins-1234567890abcdef"
    permission_set_arn = "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"

    result = resolve_permission_set_identifier(aws_client, instance_arn, permission_set_arn)

    assert result == permission_set_arn
    aws_client.get_client.assert_not_called()  # Should not make API calls if ARN is provided


@patch("src.awsideman.commands.permission_set.console")
def test_resolve_permission_set_identifier_with_name_found(mock_console):
    """Test resolve_permission_set_identifier with name that is found."""
    # Setup mocks
    aws_client = MagicMock()
    mock_sso_admin = MagicMock()
    aws_client.get_client.return_value = mock_sso_admin

    instance_arn = "arn:aws:sso:::instance/ssoins-1234567890abcdef"
    permission_set_name = "TestPermissionSet"
    permission_set_arn = "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"

    # Mock paginator
    mock_paginator = MagicMock()
    mock_sso_admin.get_paginator.return_value = mock_paginator

    # Mock paginate response
    mock_paginator.paginate.return_value = [{"PermissionSets": [permission_set_arn]}]

    # Mock describe_permission_set response
    mock_sso_admin.describe_permission_set.return_value = {
        "PermissionSet": {"Name": permission_set_name, "PermissionSetArn": permission_set_arn}
    }

    # Call the function
    result = resolve_permission_set_identifier(aws_client, instance_arn, permission_set_name)

    # Verify the result
    assert result == permission_set_arn

    # Verify the API calls
    aws_client.get_client.assert_called_once_with("sso-admin")
    mock_sso_admin.get_paginator.assert_called_once_with("list_permission_sets")
    mock_paginator.paginate.assert_called_once_with(InstanceArn=instance_arn)
    mock_sso_admin.describe_permission_set.assert_called_once_with(
        InstanceArn=instance_arn, PermissionSetArn=permission_set_arn
    )


@patch("src.awsideman.commands.permission_set.console")
def test_resolve_permission_set_identifier_with_name_not_found(mock_console):
    """Test resolve_permission_set_identifier with name that is not found."""
    # Setup mocks
    aws_client = MagicMock()
    mock_sso_admin = MagicMock()
    aws_client.get_client.return_value = mock_sso_admin

    instance_arn = "arn:aws:sso:::instance/ssoins-1234567890abcdef"
    permission_set_name = "NonExistentPermissionSet"
    permission_set_arn = "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"

    # Mock paginator
    mock_paginator = MagicMock()
    mock_sso_admin.get_paginator.return_value = mock_paginator

    # Mock paginate response
    mock_paginator.paginate.return_value = [{"PermissionSets": [permission_set_arn]}]

    # Mock describe_permission_set response for a different permission set
    mock_sso_admin.describe_permission_set.return_value = {
        "PermissionSet": {"Name": "DifferentPermissionSet", "PermissionSetArn": permission_set_arn}
    }

    # Call the function and expect exit
    with pytest.raises(typer.Exit) as exc_info:
        resolve_permission_set_identifier(aws_client, instance_arn, permission_set_name)

    # Verify exit code is 1
    assert exc_info.value.exit_code == 1

    # Verify error messages
    mock_console.print.assert_any_call(
        f"[red]Error: Permission set with name '{permission_set_name}' not found.[/red]"
    )
    mock_console.print.assert_any_call(
        "[yellow]Check the permission set name and try again.[/yellow]"
    )
    mock_console.print.assert_any_call(
        "[yellow]Use 'awsideman permission-set list' to see all available permission sets.[/yellow]"
    )


@patch("src.awsideman.commands.permission_set.console")
def test_resolve_permission_set_identifier_with_multiple_pages(mock_console):
    """Test resolve_permission_set_identifier with multiple pages of results."""
    # Setup mocks
    aws_client = MagicMock()
    mock_sso_admin = MagicMock()
    aws_client.get_client.return_value = mock_sso_admin

    instance_arn = "arn:aws:sso:::instance/ssoins-1234567890abcdef"
    permission_set_name = "TestPermissionSet"
    permission_set_arn1 = "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1111111111111111"
    permission_set_arn2 = "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-2222222222222222"
    permission_set_arn3 = "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-3333333333333333"

    # Mock paginator
    mock_paginator = MagicMock()
    mock_sso_admin.get_paginator.return_value = mock_paginator

    # Mock paginate response with multiple pages
    mock_paginator.paginate.return_value = [
        {"PermissionSets": [permission_set_arn1, permission_set_arn2]},
        {"PermissionSets": [permission_set_arn3]},
    ]

    # Mock describe_permission_set responses
    def mock_describe_permission_set(**kwargs):
        arn = kwargs.get("PermissionSetArn")
        if arn == permission_set_arn1:
            return {
                "PermissionSet": {
                    "Name": "OtherPermissionSet1",
                    "PermissionSetArn": permission_set_arn1,
                }
            }
        elif arn == permission_set_arn2:
            return {
                "PermissionSet": {
                    "Name": "OtherPermissionSet2",
                    "PermissionSetArn": permission_set_arn2,
                }
            }
        elif arn == permission_set_arn3:
            return {
                "PermissionSet": {
                    "Name": permission_set_name,
                    "PermissionSetArn": permission_set_arn3,
                }
            }
        return {}

    mock_sso_admin.describe_permission_set.side_effect = mock_describe_permission_set

    # Call the function
    result = resolve_permission_set_identifier(aws_client, instance_arn, permission_set_name)

    # Verify the result
    assert result == permission_set_arn3

    # Verify the API calls
    aws_client.get_client.assert_called_once_with("sso-admin")
    mock_sso_admin.get_paginator.assert_called_once_with("list_permission_sets")
    mock_paginator.paginate.assert_called_once_with(InstanceArn=instance_arn)

    # Should have called describe_permission_set for each ARN until finding the match
    assert mock_sso_admin.describe_permission_set.call_count == 3


@patch("src.awsideman.commands.permission_set.handle_aws_error")
@patch("src.awsideman.commands.permission_set.console")
def test_resolve_permission_set_identifier_with_client_error(mock_console, mock_handle_aws_error):
    """Test resolve_permission_set_identifier with AWS client error."""
    # Setup mocks
    aws_client = MagicMock()
    mock_sso_admin = MagicMock()
    aws_client.get_client.return_value = mock_sso_admin

    instance_arn = "arn:aws:sso:::instance/ssoins-1234567890abcdef"
    permission_set_name = "TestPermissionSet"

    # Mock client error
    error_response = {
        "Error": {
            "Code": "AccessDeniedException",
            "Message": "User is not authorized to perform this action",
        }
    }
    client_error = ClientError(error_response, "ListPermissionSets")
    mock_sso_admin.get_paginator.side_effect = client_error

    # Call the function and expect the error to be re-raised
    with pytest.raises(ClientError):
        resolve_permission_set_identifier(aws_client, instance_arn, permission_set_name)

    # Verify error handling was called with any ClientError and operation name
    mock_handle_aws_error.assert_called_once()
    args, kwargs = mock_handle_aws_error.call_args
    assert isinstance(args[0], ClientError)
    assert args[1] == "ListPermissionSets"


@patch("src.awsideman.commands.permission_set.handle_network_error")
@patch("src.awsideman.commands.permission_set.console")
def test_resolve_permission_set_identifier_with_network_error(
    mock_console, mock_handle_network_error
):
    """Test resolve_permission_set_identifier with network error."""
    # Setup mocks
    aws_client = MagicMock()
    mock_sso_admin = MagicMock()
    aws_client.get_client.return_value = mock_sso_admin

    instance_arn = "arn:aws:sso:::instance/ssoins-1234567890abcdef"
    permission_set_name = "TestPermissionSet"

    # Mock network error
    from botocore.exceptions import EndpointConnectionError

    network_error = EndpointConnectionError(
        endpoint_url="https://sso-admin.us-east-1.amazonaws.com"
    )
    mock_sso_admin.get_paginator.side_effect = network_error

    # Call the function and expect the error to be re-raised
    with pytest.raises(EndpointConnectionError):
        resolve_permission_set_identifier(aws_client, instance_arn, permission_set_name)

    # Verify error handling was called with any EndpointConnectionError
    mock_handle_network_error.assert_called_once()
    args = mock_handle_network_error.call_args[0]
    assert isinstance(args[0], EndpointConnectionError)
