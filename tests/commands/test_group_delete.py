"""Tests for group delete command."""
import pytest
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError
import typer

from src.awsideman.commands.group import delete_group


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
        "DisplayName": "TestGroup",
        "Description": "Test group for deletion"
    }


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
@patch("src.awsideman.commands.group.get_single_key")
def test_delete_group_with_force(
    mock_get_single_key,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_group
):
    """Test delete_group with force option."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the describe_group API response
    mock_identity_store.describe_group.return_value = sample_group
    
    # Mock the delete_group API response
    mock_identity_store.delete_group.return_value = {}
    
    # Call the function with force option
    result = delete_group(
        identifier="1234567890",
        force=True
    )
    
    # Verify the function called the APIs correctly
    mock_identity_store.describe_group.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        GroupId="1234567890"
    )
    
    mock_identity_store.delete_group.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        GroupId="1234567890"
    )
    
    # Verify the function returned the correct data
    assert result is True
    
    # Verify the console output
    mock_console.print.assert_any_call("[green]Group 'TestGroup' deleted successfully.[/green]")
    
    # Verify that get_single_key was not called (no confirmation needed)
    mock_get_single_key.assert_not_called()


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
@patch("src.awsideman.commands.group.get_single_key")
def test_delete_group_with_confirmation_yes(
    mock_get_single_key,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_group
):
    """Test delete_group with confirmation (yes)."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the describe_group API response
    mock_identity_store.describe_group.return_value = sample_group
    
    # Mock the delete_group API response
    mock_identity_store.delete_group.return_value = {}
    
    # Mock user confirmation (y)
    mock_get_single_key.return_value = "y"
    
    # Call the function without force option
    result = delete_group(
        identifier="1234567890",
        force=False
    )
    
    # Verify the function called the APIs correctly
    mock_identity_store.describe_group.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        GroupId="1234567890"
    )
    
    mock_identity_store.delete_group.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        GroupId="1234567890"
    )
    
    # Verify the function returned the correct data
    assert result is True
    
    # Verify the console output
    mock_console.print.assert_any_call("[green]Group 'TestGroup' deleted successfully.[/green]")
    
    # Verify that get_single_key was called for confirmation
    mock_get_single_key.assert_called_once()


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
@patch("src.awsideman.commands.group.get_single_key")
def test_delete_group_with_confirmation_no(
    mock_get_single_key,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_group
):
    """Test delete_group with confirmation (no)."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the describe_group API response
    mock_identity_store.describe_group.return_value = sample_group
    
    # Mock user confirmation (n)
    mock_get_single_key.return_value = "n"
    
    # Call the function without force option
    with pytest.raises(typer.Exit):
        delete_group(
            identifier="1234567890",
            force=False
        )
    
    # Verify the describe_group API was called
    mock_identity_store.describe_group.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        GroupId="1234567890"
    )
    
    # Verify the delete_group API was NOT called
    mock_identity_store.delete_group.assert_not_called()
    
    # Verify the console output
    mock_console.print.assert_any_call("\n[yellow]Group deletion cancelled.[/yellow]")
    
    # Verify that get_single_key was called for confirmation
    mock_get_single_key.assert_called_once()


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
def test_delete_group_not_found(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client
):
    """Test delete_group with group not found."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
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
        delete_group(
            identifier="nonexistent",
            force=True
        )
    
    # Verify the console output
    mock_console.print.assert_any_call("[red]Error: Group with ID 'nonexistent' not found.[/red]")


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
def test_delete_group_by_name(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_group
):
    """Test delete_group by name."""
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
    
    # Mock the delete_group API response
    mock_identity_store.delete_group.return_value = {}
    
    # Call the function with force option
    result = delete_group(
        identifier="TestGroup",
        force=True
    )
    
    # Verify the function called the APIs correctly
    mock_identity_store.list_groups.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        Filters=[
            {
                "AttributePath": "DisplayName",
                "AttributeValue": "TestGroup"
            }
        ]
    )
    
    mock_identity_store.describe_group.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        GroupId="1234567890"
    )
    
    mock_identity_store.delete_group.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        GroupId="1234567890"
    )
    
    # Verify the function returned the correct data
    assert result is True
    
    # Verify the console output
    mock_console.print.assert_any_call("[green]Group 'TestGroup' deleted successfully.[/green]")


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
@patch("src.awsideman.commands.group.get_single_key")
def test_delete_group_api_error(
    mock_get_single_key,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_group
):
    """Test delete_group with API error."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the describe_group API response
    mock_identity_store.describe_group.return_value = sample_group
    
    # Mock user confirmation (y)
    mock_get_single_key.return_value = "y"
    
    # Mock the delete_group API error
    error_response = {
        "Error": {
            "Code": "AccessDeniedException",
            "Message": "User is not authorized to perform this action"
        }
    }
    mock_identity_store.delete_group.side_effect = ClientError(error_response, "DeleteGroup")
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        delete_group(
            identifier="1234567890",
            force=False
        )
    
    # Verify the console output
    mock_console.print.assert_any_call("[red]Error (AccessDeniedException): User is not authorized to perform this action[/red]")