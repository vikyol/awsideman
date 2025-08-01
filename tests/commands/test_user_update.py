"""Tests for user update command."""
import pytest
import re
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError

from src.awsideman.commands.user import update_user


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
        "UserName": "existinguser",
        "Name": {
            "GivenName": "Existing",
            "FamilyName": "User"
        },
        "DisplayName": "Existing User",
        "Emails": [
            {
                "Value": "existing.user@example.com",
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
def test_update_user_successful(
    mock_re_match,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_user
):
    """Test successful update_user operation."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock email validation
    mock_re_match.return_value = True
    
    # Mock the describe_user API response (before update)
    mock_identity_store.describe_user.return_value = sample_user
    
    # Mock the update_user API response
    mock_identity_store.update_user.return_value = {}
    
    # Updated user data
    updated_user = sample_user.copy()
    updated_user["DisplayName"] = "Updated User"
    updated_user["Name"]["GivenName"] = "Updated"
    updated_user["Emails"][0]["Value"] = "updated.user@example.com"
    
    # Mock the describe_user API response (after update)
    mock_identity_store.describe_user.side_effect = [sample_user, updated_user]
    
    # Call the function
    result = update_user(
        user_id="1234567890",
        username=None,
        email="updated.user@example.com",
        given_name="Updated",
        family_name=None,
        display_name="Updated User"
    )
    
    # Verify the function called the APIs correctly
    mock_identity_store.describe_user.assert_any_call(
        IdentityStoreId="d-1234567890",
        UserId="1234567890"
    )
    
    # Check that update_user was called with the correct operations
    mock_identity_store.update_user.assert_called_once()
    call_args = mock_identity_store.update_user.call_args[1]
    assert call_args["IdentityStoreId"] == "d-1234567890"
    assert call_args["UserId"] == "1234567890"
    
    # Check that the operations include the updated fields
    operations = call_args["Operations"]
    
    # Find the email update operation
    email_op = next((op for op in operations if op.get("AttributePath") == "Emails"), None)
    assert email_op is not None
    assert email_op["AttributeValue"][0]["Value"] == "updated.user@example.com"
    
    # Find the given name update operation
    name_op = next((op for op in operations if op.get("AttributePath") == "Name.GivenName"), None)
    assert name_op is not None
    assert name_op["AttributeValue"] == "Updated"
    
    # Find the display name update operation
    display_name_op = next((op for op in operations if op.get("AttributePath") == "DisplayName"), None)
    assert display_name_op is not None
    assert display_name_op["AttributeValue"] == "Updated User"
    
    # Verify the function returned the correct data
    assert result == updated_user
    
    # Verify the console output
    mock_console.print.assert_any_call("[green]User updated successfully![/green]")


@patch("src.awsideman.commands.user.validate_profile")
@patch("src.awsideman.commands.user.validate_sso_instance")
@patch("src.awsideman.commands.user.AWSClientManager")
@patch("src.awsideman.commands.user.console")
@patch("src.awsideman.commands.user.re.match")
def test_update_user_no_changes(
    mock_re_match,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_user
):
    """Test update_user with no changes."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the describe_user API response
    mock_identity_store.describe_user.return_value = sample_user
    
    # Call the function with no changes
    with pytest.raises(typer.Exit):
        update_user(
            user_id="1234567890"
        )
    
    # Verify the console output
    mock_console.print.assert_any_call("[yellow]No update parameters provided. User remains unchanged.[/yellow]")


@patch("src.awsideman.commands.user.validate_profile")
@patch("src.awsideman.commands.user.validate_sso_instance")
@patch("src.awsideman.commands.user.AWSClientManager")
@patch("src.awsideman.commands.user.console")
@patch("src.awsideman.commands.user.re.match")
def test_update_user_not_found(
    mock_re_match,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client
):
    """Test update_user with user not found."""
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
        update_user(
            user_id="nonexistent",
            display_name="New Display Name"
        )
    
    # Verify the console output
    mock_console.print.assert_any_call("[red]Error: User 'nonexistent' not found.[/red]")


@patch("src.awsideman.commands.user.validate_profile")
@patch("src.awsideman.commands.user.validate_sso_instance")
@patch("src.awsideman.commands.user.AWSClientManager")
@patch("src.awsideman.commands.user.console")
@patch("src.awsideman.commands.user.re.match")
def test_update_user_invalid_email(
    mock_re_match,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_user
):
    """Test update_user with invalid email."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the describe_user API response
    mock_identity_store.describe_user.return_value = sample_user
    
    # Mock email validation (invalid)
    mock_re_match.return_value = False
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        update_user(
            user_id="1234567890",
            email="invalid-email"
        )
    
    # Verify the console output
    mock_console.print.assert_any_call("[red]Error: Invalid email format.[/red]")


@patch("src.awsideman.commands.user.validate_profile")
@patch("src.awsideman.commands.user.validate_sso_instance")
@patch("src.awsideman.commands.user.AWSClientManager")
@patch("src.awsideman.commands.user.console")
@patch("src.awsideman.commands.user.re.match")
def test_update_user_api_error(
    mock_re_match,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_user
):
    """Test update_user with API error."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock email validation
    mock_re_match.return_value = True
    
    # Mock the describe_user API response
    mock_identity_store.describe_user.return_value = sample_user
    
    # Mock the update_user API error
    error_response = {
        "Error": {
            "Code": "AccessDeniedException",
            "Message": "User is not authorized to perform this action"
        }
    }
    mock_identity_store.update_user.side_effect = ClientError(error_response, "UpdateUser")
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        update_user(
            user_id="1234567890",
            display_name="Updated User"
        )
    
    # Verify the console output
    mock_console.print.assert_any_call("[red]Error (AccessDeniedException): User is not authorized to perform this action[/red]")