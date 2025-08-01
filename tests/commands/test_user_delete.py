"""Tests for user delete command."""
import pytest
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError

from src.awsideman.commands.user import delete_user


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
        "UserName": "deleteuser",
        "Name": {
            "GivenName": "Delete",
            "FamilyName": "User"
        },
        "DisplayName": "Delete User",
        "Emails": [
            {
                "Value": "delete.user@example.com",
                "Primary": True
            }
        ],
        "Status": "ENABLED"
    }


@patch("src.awsideman.commands.user.validate_profile")
@patch("src.awsideman.commands.user.validate_sso_instance")
@patch("src.awsideman.commands.user.AWSClientManager")
@patch("src.awsideman.commands.user.console")
@patch("src.awsideman.commands.user.get_single_key")
def test_delete_user_with_force(
    mock_get_single_key,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_user
):
    """Test delete_user with force option."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the describe_user API response
    mock_identity_store.describe_user.return_value = sample_user
    
    # Mock the delete_user API response
    mock_identity_store.delete_user.return_value = {}
    
    # Call the function with force option
    result = delete_user(
        user_id="1234567890",
        force=True
    )
    
    # Verify the function called the APIs correctly
    mock_identity_store.describe_user.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        UserId="1234567890"
    )
    
    mock_identity_store.delete_user.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        UserId="1234567890"
    )
    
    # Verify the function returned the correct data
    assert result is True
    
    # Verify the console output
    mock_console.print.assert_any_call("[green]User 'deleteuser' (Delete User) deleted successfully.[/green]")
    
    # Verify that get_single_key was not called (no confirmation needed)
    mock_get_single_key.assert_not_called()


@patch("src.awsideman.commands.user.validate_profile")
@patch("src.awsideman.commands.user.validate_sso_instance")
@patch("src.awsideman.commands.user.AWSClientManager")
@patch("src.awsideman.commands.user.console")
@patch("src.awsideman.commands.user.get_single_key")
def test_delete_user_with_confirmation_yes(
    mock_get_single_key,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_user
):
    """Test delete_user with confirmation (yes)."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the describe_user API response
    mock_identity_store.describe_user.return_value = sample_user
    
    # Mock the delete_user API response
    mock_identity_store.delete_user.return_value = {}
    
    # Mock user confirmation (y)
    mock_get_single_key.return_value = "y"
    
    # Call the function without force option
    result = delete_user(
        user_id="1234567890",
        force=False
    )
    
    # Verify the function called the APIs correctly
    mock_identity_store.describe_user.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        UserId="1234567890"
    )
    
    mock_identity_store.delete_user.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        UserId="1234567890"
    )
    
    # Verify the function returned the correct data
    assert result is True
    
    # Verify the console output
    mock_console.print.assert_any_call("[green]User 'deleteuser' (Delete User) deleted successfully.[/green]")
    
    # Verify that get_single_key was called for confirmation
    mock_get_single_key.assert_called_once()


@patch("src.awsideman.commands.user.validate_profile")
@patch("src.awsideman.commands.user.validate_sso_instance")
@patch("src.awsideman.commands.user.AWSClientManager")
@patch("src.awsideman.commands.user.console")
@patch("src.awsideman.commands.user.get_single_key")
def test_delete_user_with_confirmation_no(
    mock_get_single_key,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_user
):
    """Test delete_user with confirmation (no)."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the describe_user API response
    mock_identity_store.describe_user.return_value = sample_user
    
    # Mock user confirmation (n)
    mock_get_single_key.return_value = "n"
    
    # Call the function without force option
    with pytest.raises(typer.Exit):
        delete_user(
            user_id="1234567890",
            force=False
        )
    
    # Verify the describe_user API was called
    mock_identity_store.describe_user.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        UserId="1234567890"
    )
    
    # Verify the delete_user API was NOT called
    mock_identity_store.delete_user.assert_not_called()
    
    # Verify the console output
    mock_console.print.assert_any_call("[yellow]User deletion cancelled.[/yellow]")
    
    # Verify that get_single_key was called for confirmation
    mock_get_single_key.assert_called_once()


@patch("src.awsideman.commands.user.validate_profile")
@patch("src.awsideman.commands.user.validate_sso_instance")
@patch("src.awsideman.commands.user.AWSClientManager")
@patch("src.awsideman.commands.user.console")
def test_delete_user_not_found(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client
):
    """Test delete_user with user not found."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
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
        delete_user(
            user_id="nonexistent",
            force=True
        )
    
    # Verify the console output
    mock_console.print.assert_any_call("[red]Error: User 'nonexistent' not found.[/red]")


@patch("src.awsideman.commands.user.validate_profile")
@patch("src.awsideman.commands.user.validate_sso_instance")
@patch("src.awsideman.commands.user.AWSClientManager")
@patch("src.awsideman.commands.user.console")
@patch("src.awsideman.commands.user.get_single_key")
def test_delete_user_api_error(
    mock_get_single_key,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_user
):
    """Test delete_user with API error."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the describe_user API response
    mock_identity_store.describe_user.return_value = sample_user
    
    # Mock user confirmation (y)
    mock_get_single_key.return_value = "y"
    
    # Mock the delete_user API error
    error_response = {
        "Error": {
            "Code": "AccessDeniedException",
            "Message": "User is not authorized to perform this action"
        }
    }
    mock_identity_store.delete_user.side_effect = ClientError(error_response, "DeleteUser")
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        delete_user(
            user_id="1234567890",
            force=False
        )
    
    # Verify the console output
    mock_console.print.assert_any_call("[red]Error (AccessDeniedException): User is not authorized to perform this action[/red]")