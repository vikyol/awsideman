"""Tests for group membership commands."""
import pytest
import re
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError
import typer

from src.awsideman.commands.group import list_members, add_member, remove_member, _find_user_id


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
        "LastModifiedDate": "2023-01-02T00:00:00Z"
    }


@pytest.fixture
def sample_user():
    """Sample user data for testing."""
    return {
        "UserId": "0987654321",
        "UserName": "johndoe",
        "DisplayName": "John Doe",
        "Name": {
            "GivenName": "John",
            "FamilyName": "Doe"
        },
        "Emails": [
            {
                "Value": "john.doe@example.com",
                "Primary": True
            }
        ],
        "Status": "ENABLED"
    }


@pytest.fixture
def sample_memberships():
    """Sample group membership data for testing."""
    return [
        {
            "MembershipId": "membership-1",
            "GroupId": "1234567890",
            "MemberId": {
                "UserId": "0987654321"
            }
        },
        {
            "MembershipId": "membership-2",
            "GroupId": "1234567890",
            "MemberId": {
                "UserId": "1122334455"
            }
        }
    ]


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
def test_list_members_by_id_successful(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_group,
    sample_user,
    sample_memberships
):
    """Test successful list_members operation by group ID."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Use a valid UUID format for the group ID
    group_id = "12345678-1234-1234-1234-123456789012"
    
    # Mock the describe_group API response
    mock_identity_store.describe_group.return_value = sample_group
    
    # Mock the list_group_memberships API response
    mock_identity_store.list_group_memberships.return_value = {
        "GroupMemberships": sample_memberships,
        "NextToken": None
    }
    
    # Mock the describe_user API response
    mock_identity_store.describe_user.return_value = sample_user
    
    # Call the function with group ID
    result, next_token, returned_group_id = list_members(group_id)
    
    # Verify the function called the APIs correctly
    mock_identity_store.describe_group.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        GroupId=group_id
    )
    
    mock_identity_store.list_group_memberships.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        GroupId=group_id
    )
    
    # Verify the function returned the correct data
    assert len(result) == 2  # Two members in the sample data
    assert next_token is None
    assert returned_group_id == group_id


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
def test_list_members_by_name_successful(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_group,
    sample_user,
    sample_memberships
):
    """Test successful list_members operation by group name."""
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
    
    # Mock the list_group_memberships API response
    mock_identity_store.list_group_memberships.return_value = {
        "GroupMemberships": sample_memberships,
        "NextToken": None
    }
    
    # Mock the describe_user API response
    mock_identity_store.describe_user.return_value = sample_user
    
    # Call the function with group name
    result, next_token, returned_group_id = list_members("Administrators")
    
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
    
    mock_identity_store.list_group_memberships.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        GroupId="1234567890"
    )
    
    # Verify the function returned the correct data
    assert len(result) == 2  # Two members in the sample data
    assert next_token is None
    assert returned_group_id == "1234567890"


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
def test_list_members_with_pagination(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_group,
    sample_user,
    sample_memberships
):
    """Test list_members with pagination."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Use a valid UUID format for the group ID
    group_id = "12345678-1234-1234-1234-123456789012"
    
    # Mock the describe_group API response
    mock_identity_store.describe_group.return_value = sample_group
    
    # Mock the list_group_memberships API response with pagination
    mock_identity_store.list_group_memberships.return_value = {
        "GroupMemberships": sample_memberships[:1],  # Return only the first membership
        "NextToken": "next-page-token"
    }
    
    # Mock the describe_user API response
    mock_identity_store.describe_user.return_value = sample_user
    
    # Mock get_single_key to simulate user pressing a key other than Enter
    with patch("src.awsideman.commands.group.get_single_key", return_value="q"):
        # Call the function with group ID and limit
        result, next_token, returned_group_id = list_members(group_id, limit=1)
        
        # Verify the function called the APIs correctly
        mock_identity_store.list_group_memberships.assert_called_once_with(
            IdentityStoreId="d-1234567890",
            GroupId=group_id,
            MaxResults=1
        )
        
        # Verify the function returned the correct data
        assert len(result) == 1  # Only one member in the first page
        assert next_token == "next-page-token"
        assert returned_group_id == group_id


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
def test_list_members_empty_group(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_group
):
    """Test list_members with an empty group."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Use a valid UUID format for the group ID
    group_id = "12345678-1234-1234-1234-123456789012"
    
    # Mock the describe_group API response
    mock_identity_store.describe_group.return_value = sample_group
    
    # Mock the list_group_memberships API response with no memberships
    mock_identity_store.list_group_memberships.return_value = {
        "GroupMemberships": [],
        "NextToken": None
    }
    
    # Call the function with group ID
    result, next_token, returned_group_id = list_members(group_id)
    
    # Verify the function called the APIs correctly
    mock_identity_store.list_group_memberships.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        GroupId=group_id
    )
    
    # Verify the function returned the correct data
    assert result == []
    assert next_token is None
    assert returned_group_id == group_id
    
    # Verify the console output
    mock_console.print.assert_any_call(f"[yellow]No members found in group '{sample_group['DisplayName']}'.[/yellow]")


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
def test_list_members_group_not_found(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client
):
    """Test list_members with group not found."""
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
        list_members("nonexistent")
    
    # Verify the console output
    mock_console.print.assert_any_call("[red]Error: No group found with name 'nonexistent'.[/red]")


@patch("src.awsideman.commands.group._find_user_id")
@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
def test_add_member_successful(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_find_user_id,
    mock_aws_client,
    sample_group,
    sample_user
):
    """Test successful add_member operation."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the find_user_id function
    mock_find_user_id.return_value = sample_user["UserId"]
    
    # Mock the describe_group API response
    mock_identity_store.describe_group.return_value = sample_group
    
    # Mock the describe_user API response
    mock_identity_store.describe_user.return_value = sample_user
    
    # Mock the list_group_memberships API response (user not already a member)
    mock_identity_store.list_group_memberships.return_value = {
        "GroupMemberships": [],
        "NextToken": None
    }
    
    # Mock the create_group_membership API response
    mock_identity_store.create_group_membership.return_value = {
        "MembershipId": "new-membership-id"
    }
    
    # Call the function
    result = add_member("Administrators", "johndoe")
    
    # Verify the function called the APIs correctly
    mock_identity_store.create_group_membership.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        GroupId=sample_group["GroupId"],
        MemberId={
            "UserId": sample_user["UserId"]
        }
    )
    
    # Verify the function returned the correct data
    assert result == "new-membership-id"
    
    # Verify the console output
    mock_console.print.assert_any_call(f"[green]User '{sample_user['UserName']}' successfully added to group '{sample_group['DisplayName']}'.[/green]")


@patch("src.awsideman.commands.group._find_user_id")
@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
def test_add_member_already_member(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_find_user_id,
    mock_aws_client,
    sample_group,
    sample_user,
    sample_memberships
):
    """Test add_member when user is already a member."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the find_user_id function
    mock_find_user_id.return_value = sample_user["UserId"]
    
    # Mock the describe_group API response
    mock_identity_store.describe_group.return_value = sample_group
    
    # Mock the describe_user API response
    mock_identity_store.describe_user.return_value = sample_user
    
    # Mock the list_group_memberships API response (user already a member)
    mock_identity_store.list_group_memberships.return_value = {
        "GroupMemberships": [
            {
                "MembershipId": "existing-membership-id",
                "GroupId": sample_group["GroupId"],
                "MemberId": {
                    "UserId": sample_user["UserId"]
                }
            }
        ],
        "NextToken": None
    }
    
    # Call the function
    result = add_member("Administrators", "johndoe")
    
    # Verify the create_group_membership API was not called
    mock_identity_store.create_group_membership.assert_not_called()
    
    # Verify the console output
    mock_console.print.assert_any_call(f"[yellow]User '{sample_user['UserName']}' is already a member of group '{sample_group['DisplayName']}'.[/yellow]")


@patch("src.awsideman.commands.group._find_user_id")
@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
def test_remove_member_successful(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_find_user_id,
    mock_aws_client,
    sample_group,
    sample_user,
    sample_memberships
):
    """Test successful remove_member operation."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the find_user_id function
    mock_find_user_id.return_value = sample_user["UserId"]
    
    # Mock the describe_group API response
    mock_identity_store.describe_group.return_value = sample_group
    
    # Mock the describe_user API response
    mock_identity_store.describe_user.return_value = sample_user
    
    # Mock the list_group_memberships API response (user is a member)
    mock_identity_store.list_group_memberships.return_value = {
        "GroupMemberships": [
            {
                "MembershipId": "existing-membership-id",
                "GroupId": sample_group["GroupId"],
                "MemberId": {
                    "UserId": sample_user["UserId"]
                }
            }
        ],
        "NextToken": None
    }
    
    # Call the function
    result = remove_member("Administrators", "johndoe")
    
    # Verify the function called the APIs correctly
    mock_identity_store.delete_group_membership.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        MembershipId="existing-membership-id"
    )
    
    # Verify the function returned the correct data
    assert result == "existing-membership-id"
    
    # Verify the console output
    mock_console.print.assert_any_call(f"[green]User '{sample_user['UserName']}' successfully removed from group '{sample_group['DisplayName']}'.[/green]")


@patch("src.awsideman.commands.group._find_user_id")
@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
def test_remove_member_not_member(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_find_user_id,
    mock_aws_client,
    sample_group,
    sample_user
):
    """Test remove_member when user is not a member."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the find_user_id function
    mock_find_user_id.return_value = sample_user["UserId"]
    
    # Mock the describe_group API response
    mock_identity_store.describe_group.return_value = sample_group
    
    # Mock the describe_user API response
    mock_identity_store.describe_user.return_value = sample_user
    
    # Mock the list_group_memberships API response (user not a member)
    mock_identity_store.list_group_memberships.return_value = {
        "GroupMemberships": [],
        "NextToken": None
    }
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        remove_member("Administrators", "johndoe")
    
    # Verify the delete_group_membership API was not called
    mock_identity_store.delete_group_membership.assert_not_called()
    
    # Verify the console output
    mock_console.print.assert_any_call(f"[yellow]User '{sample_user['UserName']}' is not a member of group '{sample_group['DisplayName']}'.[/yellow]")


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
def test_find_user_id_by_id(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_user
):
    """Test _find_user_id with user ID."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    
    # Use a valid UUID format for the user ID
    user_id = "12345678-1234-1234-1234-123456789012"
    
    # Mock the describe_user API response
    mock_identity_store.describe_user.return_value = sample_user
    
    # Call the function
    result = _find_user_id(mock_identity_store, "d-1234567890", user_id)
    
    # Verify the function called the API correctly
    mock_identity_store.describe_user.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        UserId=user_id
    )
    
    # Verify the function returned the correct data
    assert result == user_id


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
def test_find_user_id_by_username(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_user
):
    """Test _find_user_id with username."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    
    # Mock the list_users API response
    mock_identity_store.list_users.return_value = {
        "Users": [sample_user],
        "NextToken": None
    }
    
    # Call the function
    result = _find_user_id(mock_identity_store, "d-1234567890", "johndoe")
    
    # Verify the function called the API correctly
    mock_identity_store.list_users.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        Filters=[
            {
                "AttributePath": "UserName",
                "AttributeValue": "johndoe"
            }
        ]
    )
    
    # Verify the function returned the correct data
    assert result == sample_user["UserId"]


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
def test_find_user_id_by_email(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_user
):
    """Test _find_user_id with email."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    
    # Mock the list_users API response for username search (empty)
    mock_identity_store.list_users.side_effect = [
        # First call for username search returns empty
        {
            "Users": [],
            "NextToken": None
        },
        # Second call for listing all users
        {
            "Users": [sample_user],
            "NextToken": None
        }
    ]
    
    # Call the function
    result = _find_user_id(mock_identity_store, "d-1234567890", "john.doe@example.com")
    
    # Verify the function called the APIs correctly
    assert mock_identity_store.list_users.call_count == 2
    
    # Verify the function returned the correct data
    assert result == sample_user["UserId"]


@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
def test_find_user_id_not_found(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client
):
    """Test _find_user_id with user not found."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    
    # Mock the list_users API response for username search (empty)
    mock_identity_store.list_users.side_effect = [
        # First call for username search returns empty
        {
            "Users": [],
            "NextToken": None
        },
        # Second call for listing all users also returns empty
        {
            "Users": [],
            "NextToken": None
        }
    ]
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        _find_user_id(mock_identity_store, "d-1234567890", "nonexistent")
    
    # Verify the console output
    mock_console.print.assert_any_call("[red]Error: No user found with identifier 'nonexistent'.[/red]")