"""Tests for user get command."""
import pytest
import re
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError

from src.awsideman.commands.user import get_user


@pytest.fixture
def mock_aws_client():
    """Create a mock AWS client."""
    mock = MagicMock()
    # Mock identity store client
    mock_identity_store = MagicMock()
    mock.get_identity_store_client.return_value = mock_identity_store
    return mock, mock_identity_store


@pytest.fixture
def sample_user():
    """Sample user data for testing."""
    return {
        "UserId": "1234567890",
        "UserName": "testuser",
        "Name": {
            "GivenName": "Test",
            "FamilyName": "User"
        },
        "DisplayName": "Test User",
        "Emails": [
            {
                "Value": "test.user@example.com",
                "Primary": True
            }
        ],
        "Status": "ENABLED"
    }


@patch("src.awsideman.commands.user.validate_profile")
@patch("src.awsideman.commands.user.validate_sso_instance")
@patch("src.awsideman.commands.user.AWSClientManager")
@patch("src.awsideman.commands.user.console")
@patch("src.awsideman.commands.user.re.match")
def test_get_user_by_id_successful(
    mock_re_match,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_user
):
    """Test successful get_user operation by user ID."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock UUID pattern match
    mock_re_match.return_value = True
    
    # Mock the describe_user API response
    mock_identity_store.describe_user.return_value = sample_user
    
    # Call the function with user ID
    result = get_user("1234567890")
    
    # Verify the function called the API correctly
    mock_identity_store.describe_user.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        UserId="1234567890"
    )
    
    # Verify the function returned the correct data
    assert result == sample_user


@patch("src.awsideman.commands.user.validate_profile")
@patch("src.awsideman.commands.user.validate_sso_instance")
@patch("src.awsideman.commands.user.AWSClientManager")
@patch("src.awsideman.commands.user.console")
@patch("src.awsideman.commands.user.re.match")
def test_get_user_by_username_successful(
    mock_re_match,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_user
):
    """Test successful get_user operation by username."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock UUID pattern match (not a UUID)
    mock_re_match.return_value = False
    
    # Mock the list_users API response
    mock_identity_store.list_users.return_value = {
        "Users": [sample_user],
        "NextToken": None
    }
    
    # Mock the describe_user API response
    mock_identity_store.describe_user.return_value = sample_user
    
    # Call the function with username
    result = get_user("testuser")
    
    # Verify the function called the APIs correctly
    mock_identity_store.list_users.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        Filters=[
            {
                "AttributePath": "UserName",
                "AttributeValue": "testuser"
            }
        ]
    )
    
    mock_identity_store.describe_user.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        UserId="1234567890"
    )
    
    # Verify the function returned the correct data
    assert result == sample_user


@patch("src.awsideman.commands.user.validate_profile")
@patch("src.awsideman.commands.user.validate_sso_instance")
@patch("src.awsideman.commands.user.AWSClientManager")
@patch("src.awsideman.commands.user.console")
@patch("src.awsideman.commands.user.re.match")
def test_get_user_by_email_successful(
    mock_re_match,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_user
):
    """Test successful get_user operation by email."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock UUID pattern match (not a UUID)
    mock_re_match.return_value = False
    
    # Mock the list_users API response for username search (empty)
    mock_identity_store.list_users.side_effect = [
        # First call for username search returns empty
        {
            "Users": [],
            "NextToken": None
        },
        # Second call for getting all users
        {
            "Users": [sample_user],
            "NextToken": None
        }
    ]
    
    # Mock the describe_user API response
    mock_identity_store.describe_user.return_value = sample_user
    
    # Call the function with email
    result = get_user("test.user@example.com")
    
    # Verify the function called the APIs correctly
    assert mock_identity_store.list_users.call_count == 2
    
    # First call should be searching by username
    mock_identity_store.list_users.assert_any_call(
        IdentityStoreId="d-1234567890",
        Filters=[
            {
                "AttributePath": "UserName",
                "AttributeValue": "test.user@example.com"
            }
        ]
    )
    
    # Second call should be getting all users
    mock_identity_store.list_users.assert_any_call(
        IdentityStoreId="d-1234567890"
    )
    
    mock_identity_store.describe_user.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        UserId="1234567890"
    )
    
    # Verify the function returned the correct data
    assert result == sample_user


@patch("src.awsideman.commands.user.validate_profile")
@patch("src.awsideman.commands.user.validate_sso_instance")
@patch("src.awsideman.commands.user.AWSClientManager")
@patch("src.awsideman.commands.user.console")
@patch("src.awsideman.commands.user.re.match")
def test_get_user_not_found(
    mock_re_match,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client
):
    """Test get_user with user not found."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock UUID pattern match (not a UUID)
    mock_re_match.return_value = False
    
    # Mock the list_users API response (empty for both username and all users)
    mock_identity_store.list_users.side_effect = [
        # First call for username search returns empty
        {
            "Users": [],
            "NextToken": None
        },
        # Second call for getting all users also returns empty
        {
            "Users": [],
            "NextToken": None
        }
    ]
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        get_user("nonexistent")
    
    # Verify the console output
    mock_console.print.assert_any_call("[red]Error: No user found with username or email 'nonexistent'.[/red]")


@patch("src.awsideman.commands.user.validate_profile")
@patch("src.awsideman.commands.user.validate_sso_instance")
@patch("src.awsideman.commands.user.AWSClientManager")
@patch("src.awsideman.commands.user.console")
@patch("src.awsideman.commands.user.re.match")
def test_get_user_api_error(
    mock_re_match,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client
):
    """Test get_user with API error."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock UUID pattern match (is a UUID)
    mock_re_match.return_value = True
    
    # Mock the describe_user API error
    error_response = {
        "Error": {
            "Code": "ResourceNotFoundException",
            "Message": "User not found"
        }
    }
    mock_identity_store.describe_user.side_effect = ClientError(error_response, "DescribeUser")
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        get_user("1234567890")
    
    # Verify the console output
    mock_console.print.assert_any_call("[red]Error: User '1234567890' not found.[/red]")