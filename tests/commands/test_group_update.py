"""Tests for group update command."""
from unittest.mock import MagicMock, patch

import pytest
import typer
from botocore.exceptions import ClientError

from src.awsideman.commands.group import update_group


@pytest.fixture
def mock_aws_client():
    """Create a mock AWS client."""
    mock = MagicMock()
    # Mock identity store client
    mock_identity_store = MagicMock()
    mock.get_identity_store_client.return_value = mock_identity_store
    return mock, mock_identity_store


@pytest.fixture
def sample_group():
    """Sample group data for testing."""
    return {
        "GroupId": "1234567890",
        "DisplayName": "engineering",
        "Description": "Engineering team group",
        "CreatedDate": "2023-01-01T00:00:00Z",
        "LastModifiedDate": "2023-01-01T00:00:00Z",
    }


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
@patch("src.awsideman.commands.group.re.match")
def test_update_group_successful(
    mock_re_match,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_group,
):
    """Test successful update_group operation."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Mock UUID pattern match
    mock_re_match.return_value = True

    # Mock the describe_group API response (before update)
    mock_identity_store.describe_group.return_value = sample_group

    # Mock the update_group API response
    mock_identity_store.update_group.return_value = {}

    # Updated group data
    updated_group = sample_group.copy()
    updated_group["Description"] = "Updated engineering team group"
    updated_group["LastModifiedDate"] = "2023-01-02T00:00:00Z"

    # Mock the describe_group API response (after update)
    mock_identity_store.describe_group.side_effect = [sample_group, updated_group]

    # Call the function
    result = update_group(identifier="1234567890", description="Updated engineering team group")

    # Verify the function called the APIs correctly
    mock_identity_store.describe_group.assert_any_call(
        IdentityStoreId="d-1234567890", GroupId="1234567890"
    )

    # Check that update_group was called with the correct operations
    mock_identity_store.update_group.assert_called_once()
    call_args = mock_identity_store.update_group.call_args[1]
    assert call_args["IdentityStoreId"] == "d-1234567890"
    assert call_args["GroupId"] == "1234567890"

    # Check that the operations include the updated fields
    operations = call_args["Operations"]

    # Find the description update operation
    description_op = next(
        (op for op in operations if op.get("AttributePath") == "Description"), None
    )
    assert description_op is not None
    assert description_op["AttributeValue"] == "Updated engineering team group"

    # Verify the function returned the correct data
    assert result == updated_group

    # Verify the console output
    mock_console.print.assert_any_call("[green]Group updated successfully![/green]")


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
@patch("src.awsideman.commands.group.re.match")
def test_update_group_by_name(
    mock_re_match,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_group,
):
    """Test update_group by name instead of ID."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Mock UUID pattern match (not a UUID)
    mock_re_match.return_value = False

    # Mock the list_groups API response
    mock_identity_store.list_groups.return_value = {"Groups": [sample_group], "NextToken": None}

    # Mock the describe_group API response
    mock_identity_store.describe_group.return_value = sample_group

    # Mock the update_group API response
    mock_identity_store.update_group.return_value = {}

    # Updated group data
    updated_group = sample_group.copy()
    updated_group["Description"] = "Updated engineering team group"

    # Mock the describe_group API response (after update)
    mock_identity_store.describe_group.side_effect = [sample_group, updated_group]

    # Call the function
    update_group(identifier="engineering", description="Updated engineering team group")

    # Verify the function called the APIs correctly
    mock_identity_store.list_groups.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        Filters=[{"AttributePath": "DisplayName", "AttributeValue": "engineering"}],
    )

    # Check that update_group was called with the correct operations
    mock_identity_store.update_group.assert_called_once()
    call_args = mock_identity_store.update_group.call_args[1]
    assert call_args["IdentityStoreId"] == "d-1234567890"
    assert call_args["GroupId"] == "1234567890"

    # Verify the console output
    mock_console.print.assert_any_call("[green]Found group: engineering (ID: 1234567890)[/green]")
    mock_console.print.assert_any_call("[green]Group updated successfully![/green]")


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
@patch("src.awsideman.commands.group.re.match")
def test_update_group_not_found(
    mock_re_match,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
):
    """Test update_group with group not found."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Mock UUID pattern match
    mock_re_match.return_value = True

    # Mock the describe_group API error
    error_response = {"Error": {"Code": "ResourceNotFoundException", "Message": "Group not found"}}
    mock_identity_store.describe_group.side_effect = ClientError(error_response, "DescribeGroup")

    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        update_group(identifier="nonexistent", description="New Description")

    # Verify the console output
    mock_console.print.assert_any_call("[red]Error: Group 'nonexistent' not found.[/red]")


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
@patch("src.awsideman.commands.group.re.match")
def test_update_group_api_error(
    mock_re_match,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_group,
):
    """Test update_group with API error."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Mock UUID pattern match
    mock_re_match.return_value = True

    # Mock the describe_group API response
    mock_identity_store.describe_group.return_value = sample_group

    # Mock the update_group API error
    error_response = {
        "Error": {
            "Code": "AccessDeniedException",
            "Message": "User is not authorized to perform this action",
        }
    }
    mock_identity_store.update_group.side_effect = ClientError(error_response, "UpdateGroup")

    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        update_group(identifier="1234567890", description="Updated Description")

    # Verify the console output
    mock_console.print.assert_any_call(
        "[red]Error (AccessDeniedException): User is not authorized to perform this action[/red]"
    )
