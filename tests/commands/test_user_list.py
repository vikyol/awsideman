"""Tests for user list command."""
from unittest.mock import MagicMock, patch

import pytest
import typer
from botocore.exceptions import ClientError

from src.awsideman.commands.user import list_users


@pytest.fixture
def mock_aws_client():
    """Create a mock AWS client."""
    mock = MagicMock()
    # Mock identity store client
    mock_identity_store = MagicMock()
    mock.get_identity_store_client.return_value = mock_identity_store
    return mock, mock_identity_store


@pytest.fixture
def sample_users():
    """Sample user data for testing."""
    return [
        {
            "UserId": "1234567890",
            "UserName": "user1",
            "Name": {"GivenName": "John", "FamilyName": "Doe"},
            "DisplayName": "John Doe",
            "Emails": [{"Value": "john.doe@example.com", "Primary": True}],
            "Status": "ENABLED",
        },
        {
            "UserId": "0987654321",
            "UserName": "user2",
            "Name": {"GivenName": "Jane", "FamilyName": "Smith"},
            "DisplayName": "Jane Smith",
            "Emails": [{"Value": "jane.smith@example.com", "Primary": True}],
            "Status": "ENABLED",
        },
    ]


@patch("src.awsideman.commands.user.validate_profile")
@patch("src.awsideman.commands.user.validate_sso_instance")
@patch("src.awsideman.commands.user.AWSClientManager")
@patch("src.awsideman.commands.user.console")
@patch("src.awsideman.commands.user.get_single_key")
def test_list_users_successful(
    mock_get_single_key,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_users,
):
    """Test successful list_users operation."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Mock the list_users API response
    mock_identity_store.list_users.return_value = {"Users": sample_users, "NextToken": None}

    # Call the function
    result, next_token = list_users()

    # Verify the function called the API correctly
    mock_identity_store.list_users.assert_called_once_with(IdentityStoreId="d-1234567890")

    # Verify the function returned the correct data
    assert result == sample_users
    assert next_token is None

    # Verify the console output
    mock_console.print.assert_any_call("[green]Found 2 users.[/green]")


@patch("src.awsideman.commands.user.validate_profile")
@patch("src.awsideman.commands.user.validate_sso_instance")
@patch("src.awsideman.commands.user.AWSClientManager")
@patch("src.awsideman.commands.user.console")
@patch("src.awsideman.commands.user.get_single_key")
def test_list_users_with_filter(
    mock_get_single_key,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_users,
):
    """Test list_users with filter."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Mock the list_users API response
    mock_identity_store.list_users.return_value = {"Users": [sample_users[0]], "NextToken": None}

    # Call the function with filter
    result, next_token = list_users(filter="UserName=user1")

    # Verify the function called the API correctly
    mock_identity_store.list_users.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        Filters=[{"AttributePath": "UserName", "AttributeValue": "user1"}],
    )

    # Verify the function returned the correct data
    assert result == [sample_users[0]]
    assert next_token is None


@patch("src.awsideman.commands.user.validate_profile")
@patch("src.awsideman.commands.user.validate_sso_instance")
@patch("src.awsideman.commands.user.AWSClientManager")
@patch("src.awsideman.commands.user.console")
@patch("src.awsideman.commands.user.get_single_key")
def test_list_users_with_pagination(
    mock_get_single_key,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_users,
):
    """Test list_users with pagination."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Mock the list_users API response with pagination
    mock_identity_store.list_users.return_value = {
        "Users": [sample_users[0]],
        "NextToken": "next-page-token",
    }

    # Mock user pressing a key other than Enter to stop pagination
    mock_get_single_key.return_value = "q"

    # Call the function
    result, next_token = list_users()

    # Verify the function called the API correctly
    mock_identity_store.list_users.assert_called_once_with(IdentityStoreId="d-1234567890")

    # Verify the function returned the correct data
    assert result == [sample_users[0]]
    assert next_token == "next-page-token"

    # Verify the console output for pagination
    mock_console.print.assert_any_call("[green]Found 1 users (more results available).[/green]")
    mock_console.print.assert_any_call(
        "\n[blue]Press ENTER to see the next page, or any other key to exit...[/blue]"
    )
    mock_console.print.assert_any_call("\n[yellow]Pagination stopped.[/yellow]")


@patch("src.awsideman.commands.user.validate_profile")
@patch("src.awsideman.commands.user.validate_sso_instance")
@patch("src.awsideman.commands.user.AWSClientManager")
@patch("src.awsideman.commands.user.console")
def test_list_users_with_limit(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_users,
):
    """Test list_users with limit."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Mock the list_users API response
    mock_identity_store.list_users.return_value = {"Users": [sample_users[0]], "NextToken": None}

    # Call the function with limit
    result, next_token = list_users(limit=1)

    # Verify the function called the API correctly
    mock_identity_store.list_users.assert_called_once_with(
        IdentityStoreId="d-1234567890", MaxResults=1
    )

    # Verify the function returned the correct data
    assert result == [sample_users[0]]
    assert next_token is None

    # Verify the console output
    mock_console.print.assert_any_call("[green]Found 1 users (showing up to 1 results).[/green]")


@patch("src.awsideman.commands.user.validate_profile")
@patch("src.awsideman.commands.user.validate_sso_instance")
@patch("src.awsideman.commands.user.AWSClientManager")
@patch("src.awsideman.commands.user.console")
def test_list_users_empty_result(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
):
    """Test list_users with empty result."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Mock the list_users API response with empty result
    mock_identity_store.list_users.return_value = {"Users": [], "NextToken": None}

    # Call the function
    result, next_token = list_users()

    # Verify the function called the API correctly
    mock_identity_store.list_users.assert_called_once_with(IdentityStoreId="d-1234567890")

    # Verify the function returned the correct data
    assert result == []
    assert next_token is None

    # Verify the console output
    mock_console.print.assert_any_call("[yellow]No users found.[/yellow]")


@patch("src.awsideman.commands.user.validate_profile")
@patch("src.awsideman.commands.user.validate_sso_instance")
@patch("src.awsideman.commands.user.AWSClientManager")
@patch("src.awsideman.commands.user.console")
def test_list_users_api_error(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
):
    """Test list_users with API error."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Mock the list_users API error
    error_response = {
        "Error": {
            "Code": "AccessDeniedException",
            "Message": "User is not authorized to perform this action",
        }
    }
    mock_identity_store.list_users.side_effect = ClientError(error_response, "ListUsers")

    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        list_users()

    # Verify the function called the API correctly
    mock_identity_store.list_users.assert_called_once_with(IdentityStoreId="d-1234567890")

    # Verify the console output
    mock_console.print.assert_any_call(
        "[red]Error (AccessDeniedException): User is not authorized to perform this action[/red]"
    )


@patch("src.awsideman.commands.user.validate_profile")
@patch("src.awsideman.commands.user.validate_sso_instance")
@patch("src.awsideman.commands.user.AWSClientManager")
@patch("src.awsideman.commands.user.console")
def test_list_users_invalid_filter_format(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
):
    """Test list_users with invalid filter format."""
    # Setup mocks
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )

    # Call the function with invalid filter format
    with pytest.raises(typer.Exit):
        list_users(filter="invalid-filter")

    # Verify the console output
    mock_console.print.assert_any_call(
        "[red]Error: Filter must be in the format 'attribute=value'[/red]"
    )
