"""Tests for group list command."""
import pytest
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError
import typer

from src.awsideman.commands.group import _list_groups_internal as list_groups


@pytest.fixture
def mock_aws_client():
    """Create a mock AWS client."""
    mock = MagicMock()
    # Mock identity store client
    mock_identity_store = MagicMock()
    mock.get_identity_store_client.return_value = mock_identity_store
    return mock, mock_identity_store


@pytest.fixture
def sample_groups():
    """Sample group data for testing."""
    return [
        {
            "GroupId": "1234567890",
            "DisplayName": "Administrators",
            "Description": "Admin group with full access"
        },
        {
            "GroupId": "0987654321",
            "DisplayName": "Developers",
            "Description": "Development team members"
        }
    ]


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
@patch("src.awsideman.commands.group.get_single_key")
def test_list_groups_successful(
    mock_get_single_key,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_groups
):
    """Test successful list_groups operation."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the list_groups API response
    mock_identity_store.list_groups.return_value = {
        "Groups": sample_groups,
        "NextToken": None
    }
    
    # Call the function
    result, next_token = list_groups()
    
    # Verify the function called the API correctly
    mock_identity_store.list_groups.assert_called_once_with(
        IdentityStoreId="d-1234567890"
    )
    
    # Verify the function returned the correct data
    assert result == sample_groups
    assert next_token is None
    
    # Verify the console output
    mock_console.print.assert_any_call("[green]Found 2 groups.[/green]")


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
@patch("src.awsideman.commands.group.get_single_key")
def test_list_groups_with_filter(
    mock_get_single_key,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_groups
):
    """Test list_groups with filter."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the list_groups API response
    mock_identity_store.list_groups.return_value = {
        "Groups": [sample_groups[0]],
        "NextToken": None
    }
    
    # Call the function with filter
    result, next_token = list_groups(filter="DisplayName=Administrators")
    
    # Verify the function called the API correctly
    mock_identity_store.list_groups.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        Filters=[
            {
                "AttributePath": "DisplayName",
                "AttributeValue": "Administrators"
            }
        ]
    )
    
    # Verify the function returned the correct data
    assert result == [sample_groups[0]]
    assert next_token is None


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
@patch("src.awsideman.commands.group.get_single_key")
def test_list_groups_with_pagination(
    mock_get_single_key,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_groups
):
    """Test list_groups with pagination."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the list_groups API response with pagination
    mock_identity_store.list_groups.return_value = {
        "Groups": [sample_groups[0]],
        "NextToken": "next-page-token"
    }
    
    # Mock user pressing a key other than Enter to stop pagination
    mock_get_single_key.return_value = "q"
    
    # Call the function
    result, next_token = list_groups()
    
    # Verify the function called the API correctly
    mock_identity_store.list_groups.assert_called_once_with(
        IdentityStoreId="d-1234567890"
    )
    
    # Verify the function returned the correct data
    assert result == [sample_groups[0]]
    assert next_token == "next-page-token"
    
    # Verify the console output for pagination
    mock_console.print.assert_any_call("[green]Found 1 groups (more results available).[/green]")
    mock_console.print.assert_any_call("\n[blue]Press ENTER to see the next page, or any other key to exit...[/blue]")
    mock_console.print.assert_any_call("\n[yellow]Pagination stopped.[/yellow]")


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
def test_list_groups_with_limit(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_groups
):
    """Test list_groups with limit."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the list_groups API response
    mock_identity_store.list_groups.return_value = {
        "Groups": [sample_groups[0]],
        "NextToken": None
    }
    
    # Call the function with limit
    result, next_token = list_groups(limit=1)
    
    # Verify the function called the API correctly
    mock_identity_store.list_groups.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        MaxResults=1
    )
    
    # Verify the function returned the correct data
    assert result == [sample_groups[0]]
    assert next_token is None
    
    # Verify the console output
    mock_console.print.assert_any_call("[green]Found 1 groups (showing up to 1 results).[/green]")


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
def test_list_groups_empty_result(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client
):
    """Test list_groups with empty result."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the list_groups API response with empty result
    mock_identity_store.list_groups.return_value = {
        "Groups": [],
        "NextToken": None
    }
    
    # Call the function
    result, next_token = list_groups()
    
    # Verify the function called the API correctly
    mock_identity_store.list_groups.assert_called_once_with(
        IdentityStoreId="d-1234567890"
    )
    
    # Verify the function returned the correct data
    assert result == []
    assert next_token is None
    
    # Verify the console output
    mock_console.print.assert_any_call("[yellow]No groups found.[/yellow]")


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
def test_list_groups_api_error(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client
):
    """Test list_groups with API error."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the list_groups API error
    error_response = {
        "Error": {
            "Code": "AccessDeniedException",
            "Message": "User is not authorized to perform this action"
        }
    }
    mock_identity_store.list_groups.side_effect = ClientError(error_response, "ListGroups")
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        list_groups()
    
    # Verify the function called the API correctly
    mock_identity_store.list_groups.assert_called_once_with(
        IdentityStoreId="d-1234567890"
    )
    
    # Verify the console output
    mock_console.print.assert_any_call("[red]Error (AccessDeniedException): User is not authorized to perform this action[/red]")


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
def test_list_groups_invalid_filter_format(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client
):
    """Test list_groups with invalid filter format."""
    # Setup mocks
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Call the function with invalid filter format
    with pytest.raises(typer.Exit):
        list_groups(filter="invalid-filter")
    
    # Verify the console output
    mock_console.print.assert_any_call("[red]Error: Filter must be in the format 'attribute=value'[/red]")