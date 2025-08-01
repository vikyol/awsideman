"""Tests for user create command."""
import pytest
import re
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError

from src.awsideman.commands.user import create_user


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
        "UserName": "newuser",
        "Name": {
            "GivenName": "New",
            "FamilyName": "User"
        },
        "DisplayName": "New User",
        "Emails": [
            {
                "Value": "new.user@example.com",
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
def test_create_user_successful(
    mock_re_match,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_user
):
    """Test successful create_user operation."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock email validation
    mock_re_match.return_value = True
    
    # Mock the list_users API response (no existing user)
    mock_identity_store.list_users.return_value = {
        "Users": [],
        "NextToken": None
    }
    
    # Mock the create_user API response
    mock_identity_store.create_user.return_value = {
        "UserId": "1234567890"
    }
    
    # Mock the describe_user API response
    mock_identity_store.describe_user.return_value = sample_user
    
    # Call the function
    user_id, user_attributes = create_user(
        username="newuser",
        email="new.user@example.com",
        given_name="New",
        family_name="User",
        display_name="New User"
    )
    
    # Verify the function called the APIs correctly
    mock_identity_store.list_users.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        Filters=[
            {
                "AttributePath": "UserName",
                "AttributeValue": "newuser"
            }
        ]
    )
    
    mock_identity_store.create_user.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        UserName="newuser",
        Emails=[
            {
                "Value": "new.user@example.com",
                "Primary": True
            }
        ],
        Name={
            "GivenName": "New",
            "FamilyName": "User"
        },
        DisplayName="New User"
    )
    
    mock_identity_store.describe_user.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        UserId="1234567890"
    )
    
    # Verify the function returned the correct data
    assert user_id == "1234567890"
    assert user_attributes == {
        "UserName": "newuser",
        "Emails": [
            {
                "Value": "new.user@example.com",
                "Primary": True
            }
        ],
        "Name": {
            "GivenName": "New",
            "FamilyName": "User"
        },
        "DisplayName": "New User"
    }
    
    # Verify the console output
    mock_console.print.assert_any_call("[green]User created successfully![/green]")


@patch("src.awsideman.commands.user.validate_profile")
@patch("src.awsideman.commands.user.validate_sso_instance")
@patch("src.awsideman.commands.user.AWSClientManager")
@patch("src.awsideman.commands.user.console")
@patch("src.awsideman.commands.user.re.match")
def test_create_user_minimal_info(
    mock_re_match,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client
):
    """Test create_user with minimal information."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock email validation
    mock_re_match.return_value = True
    
    # Mock the list_users API response (no existing user)
    mock_identity_store.list_users.return_value = {
        "Users": [],
        "NextToken": None
    }
    
    # Mock the create_user API response
    mock_identity_store.create_user.return_value = {
        "UserId": "1234567890"
    }
    
    # Mock the describe_user API response
    mock_identity_store.describe_user.return_value = {
        "UserId": "1234567890",
        "UserName": "minimaluser",
        "Emails": [
            {
                "Value": "minimal@example.com",
                "Primary": True
            }
        ],
        "Status": "ENABLED"
    }
    
    # Call the function with minimal info
    user_id, user_attributes = create_user(
        username="minimaluser",
        email="minimal@example.com"
    )
    
    # Verify the function called the APIs correctly
    mock_identity_store.create_user.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        UserName="minimaluser",
        Emails=[
            {
                "Value": "minimal@example.com",
                "Primary": True
            }
        ]
    )
    
    # Verify the function returned the correct data
    assert user_id == "1234567890"
    assert user_attributes == {
        "UserName": "minimaluser",
        "Emails": [
            {
                "Value": "minimal@example.com",
                "Primary": True
            }
        ]
    }


@patch("src.awsideman.commands.user.validate_profile")
@patch("src.awsideman.commands.user.validate_sso_instance")
@patch("src.awsideman.commands.user.AWSClientManager")
@patch("src.awsideman.commands.user.console")
@patch("src.awsideman.commands.user.re.match")
def test_create_user_duplicate_username(
    mock_re_match,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_user
):
    """Test create_user with duplicate username."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock email validation
    mock_re_match.return_value = True
    
    # Mock the list_users API response (existing user)
    mock_identity_store.list_users.return_value = {
        "Users": [sample_user],
        "NextToken": None
    }
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        create_user(
            username="newuser",
            email="new.user@example.com"
        )
    
    # Verify the console output
    mock_console.print.assert_any_call("[red]Error: A user with username 'newuser' already exists.[/red]")


@patch("src.awsideman.commands.user.validate_profile")
@patch("src.awsideman.commands.user.validate_sso_instance")
@patch("src.awsideman.commands.user.AWSClientManager")
@patch("src.awsideman.commands.user.console")
@patch("src.awsideman.commands.user.re.match")
def test_create_user_invalid_email(
    mock_re_match,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client
):
    """Test create_user with invalid email."""
    # Setup mocks
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock email validation (invalid)
    mock_re_match.return_value = False
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        create_user(
            username="newuser",
            email="invalid-email"
        )
    
    # Verify the console output
    mock_console.print.assert_any_call("[red]Error: Invalid email format.[/red]")


@patch("src.awsideman.commands.user.validate_profile")
@patch("src.awsideman.commands.user.validate_sso_instance")
@patch("src.awsideman.commands.user.AWSClientManager")
@patch("src.awsideman.commands.user.console")
@patch("src.awsideman.commands.user.re.match")
def test_create_user_api_error(
    mock_re_match,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client
):
    """Test create_user with API error."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock email validation
    mock_re_match.return_value = True
    
    # Mock the list_users API response (no existing user)
    mock_identity_store.list_users.return_value = {
        "Users": [],
        "NextToken": None
    }
    
    # Mock the create_user API error
    error_response = {
        "Error": {
            "Code": "AccessDeniedException",
            "Message": "User is not authorized to perform this action"
        }
    }
    mock_identity_store.create_user.side_effect = ClientError(error_response, "CreateUser")
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        create_user(
            username="newuser",
            email="new.user@example.com"
        )
    
    # Verify the console output
    mock_console.print.assert_any_call("[red]Error (AccessDeniedException): User is not authorized to perform this action[/red]")