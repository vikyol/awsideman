"""Tests for group get command."""
import pytest
import re
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError
import typer

from src.awsideman.commands.group import get_group


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
        "DisplayName": "Administrators",
        "Description": "Admin group with full access",
        "CreatedDate": "2023-01-01T00:00:00Z",
        "LastModifiedDate": "2023-01-02T00:00:00Z",
        "ExternalIds": [
            {
                "Issuer": "example.com",
                "Id": "admin-group"
            }
        ]
    }


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
def test_get_group_by_id_successful(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_group
):
    """Test successful get_group operation by group ID."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Use a valid UUID format for the group ID
    group_id = "12345678-1234-1234-1234-123456789012"
    
    # Mock the describe_group API response
    mock_identity_store.describe_group.return_value = sample_group
    
    # Call the function with group ID
    result = get_group(group_id)
    
    # Verify the function called the API correctly
    mock_identity_store.describe_group.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        GroupId=group_id
    )
    
    # Verify the function returned the correct data
    assert result == sample_group


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
def test_get_group_by_name_successful(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_group
):
    """Test successful get_group operation by group name."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the list_groups API response
    mock_identity_store.list_groups.return_value = {
        "Groups": [sample_group],
        "NextToken": None
    }
    
    # Mock the describe_group API response
    mock_identity_store.describe_group.return_value = sample_group
    
    # Call the function with group name
    result = get_group("Administrators")
    
    # Verify the function called the APIs correctly
    mock_identity_store.list_groups.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        Filters=[
            {
                "AttributePath": "DisplayName",
                "AttributeValue": "Administrators"
            }
        ]
    )
    
    mock_identity_store.describe_group.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        GroupId="1234567890"
    )
    
    # Verify the function returned the correct data
    assert result == sample_group


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
def test_get_group_not_found(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client
):
    """Test get_group with group not found."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the list_groups API response (empty)
    mock_identity_store.list_groups.return_value = {
        "Groups": [],
        "NextToken": None
    }
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        get_group("nonexistent")
    
    # Verify the console output
    mock_console.print.assert_any_call("[red]Error: No group found with name 'nonexistent'.[/red]")


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
def test_get_group_api_error(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client
):
    """Test get_group with API error."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Use a valid UUID format for the group ID
    group_id = "12345678-1234-1234-1234-123456789012"
    
    # Mock the describe_group API error
    error_response = {
        "Error": {
            "Code": "ResourceNotFoundException",
            "Message": "Group not found"
        }
    }
    mock_identity_store.describe_group.side_effect = ClientError(error_response, "DescribeGroup")
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        get_group(group_id)
    
    # Verify the console output
    mock_console.print.assert_any_call(f"[red]Error: Group '{group_id}' not found.[/red]")


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
def test_get_group_multiple_matches(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_group
):
    """Test get_group with multiple matching groups."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Create a second group with the same name
    second_group = sample_group.copy()
    second_group["GroupId"] = "0987654321"
    
    # Mock the list_groups API response with multiple groups
    mock_identity_store.list_groups.return_value = {
        "Groups": [sample_group, second_group],
        "NextToken": None
    }
    
    # Mock the describe_group API response
    mock_identity_store.describe_group.return_value = sample_group
    
    # Call the function with group name
    result = get_group("Administrators")
    
    # Verify the warning was displayed
    mock_console.print.assert_any_call("[yellow]Warning: Multiple groups found matching 'Administrators'. Showing the first match.[/yellow]")
    
    # Verify the function called the describe_group API with the first group's ID
    mock_identity_store.describe_group.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        GroupId="1234567890"
    )
    
    # Verify the function returned the correct data
    assert result == sample_group