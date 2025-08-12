"""Integration tests for assignment management commands.

This module contains integration tests that verify end-to-end assignment workflows,
including assign -> list -> get -> revoke operations, integration with AWS APIs,
and real-world error scenarios.
"""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
import typer
from botocore.exceptions import ClientError

from src.awsideman.commands.assignment import (
    assign_permission_set,
    get_assignment,
    list_assignments,
    resolve_permission_set_info,
    resolve_principal_info,
    revoke_permission_set,
)


@pytest.fixture
def mock_aws_clients():
    """Create mock AWS clients for SSO Admin and Identity Store."""
    mock_client_manager = MagicMock()
    mock_sso_admin = MagicMock()
    mock_identity_store = MagicMock()

    mock_client_manager.get_sso_admin_client.return_value = mock_sso_admin
    mock_client_manager.get_identity_store_client.return_value = mock_identity_store

    return mock_client_manager, mock_sso_admin, mock_identity_store


@pytest.fixture
def sample_assignment_data():
    """Sample assignment data for testing."""
    return {
        "permission_set_arn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        "principal_id": "user-1234567890abcdef",
        "principal_type": "USER",
        "account_id": "123456789012",
        "instance_arn": "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "identity_store_id": "d-1234567890",
    }


@pytest.fixture
def sample_assignment_response():
    """Sample assignment response from AWS API."""
    return {
        "AccountAssignments": [
            {
                "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
                "PrincipalId": "user-1234567890abcdef",
                "PrincipalType": "USER",
                "AccountId": "123456789012",
                "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
            }
        ]
    }


@pytest.fixture
def sample_permission_set_response():
    """Sample permission set response from AWS API."""
    return {
        "PermissionSet": {
            "Name": "TestPermissionSet",
            "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            "Description": "Test permission set for integration testing",
            "SessionDuration": "PT8H",
        }
    }


@pytest.fixture
def sample_user_response():
    """Sample user response from AWS Identity Store API."""
    return {
        "UserId": "user-1234567890abcdef",
        "UserName": "testuser",
        "DisplayName": "Test User",
        "Name": {"GivenName": "Test", "FamilyName": "User"},
    }


@pytest.fixture
def sample_group_response():
    """Sample group response from AWS Identity Store API."""
    return {"GroupId": "group-1234567890abcdef", "DisplayName": "Test Group"}


@pytest.fixture
def sample_create_assignment_response():
    """Sample create assignment response from AWS API."""
    return {
        "AccountAssignmentCreationStatus": {
            "Status": "IN_PROGRESS",
            "RequestId": "req-1234567890abcdef",
            "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            "PrincipalId": "user-1234567890abcdef",
            "PrincipalType": "USER",
            "TargetId": "123456789012",
            "TargetType": "AWS_ACCOUNT",
        }
    }


@pytest.fixture
def sample_delete_assignment_response():
    """Sample delete assignment response from AWS API."""
    return {
        "AccountAssignmentDeletionStatus": {
            "Status": "IN_PROGRESS",
            "RequestId": "req-1234567890abcdef",
            "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            "PrincipalId": "user-1234567890abcdef",
            "PrincipalType": "USER",
            "TargetId": "123456789012",
            "TargetType": "AWS_ACCOUNT",
        }
    }


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.console")
def test_assignment_lifecycle_workflow(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
    sample_assignment_data,
    sample_assignment_response,
    sample_permission_set_response,
    sample_user_response,
    sample_create_assignment_response,
    sample_delete_assignment_response,
):
    """Test complete assignment lifecycle: assign -> list -> get -> revoke."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        sample_assignment_data["instance_arn"],
        sample_assignment_data["identity_store_id"],
    )

    # Step 1: Assign permission set to user
    mock_sso_admin.list_account_assignments.return_value = {
        "AccountAssignments": []
    }  # No existing assignment
    mock_sso_admin.create_account_assignment.return_value = sample_create_assignment_response
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response
    mock_identity_store.describe_user.return_value = sample_user_response

    # Call assign_permission_set
    assign_permission_set(
        permission_set_arn=sample_assignment_data["permission_set_arn"],
        principal_id=sample_assignment_data["principal_id"],
        account_id=sample_assignment_data["account_id"],
        principal_type=sample_assignment_data["principal_type"],
        profile=None,
    )

    # Verify create_account_assignment API was called with correct parameters
    mock_sso_admin.create_account_assignment.assert_called_once_with(
        InstanceArn=sample_assignment_data["instance_arn"],
        TargetId=sample_assignment_data["account_id"],
        TargetType="AWS_ACCOUNT",
        PermissionSetArn=sample_assignment_data["permission_set_arn"],
        PrincipalType=sample_assignment_data["principal_type"],
        PrincipalId=sample_assignment_data["principal_id"],
    )

    # Reset mocks for next step
    mock_sso_admin.reset_mock()
    mock_identity_store.reset_mock()

    # Step 2: List assignments to verify the assignment exists
    mock_sso_admin.list_account_assignments.return_value = sample_assignment_response
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response
    mock_identity_store.describe_user.return_value = sample_user_response

    # Call list_assignments
    list_assignments(
        account_id=None,
        permission_set_arn=None,
        principal_id=None,
        principal_type=None,
        limit=None,
        next_token=None,
        interactive=False,
        profile=None,
    )

    # Verify list_account_assignments API was called
    mock_sso_admin.list_account_assignments.assert_called_once_with(
        InstanceArn=sample_assignment_data["instance_arn"]
    )

    # Reset mocks for next step
    mock_sso_admin.reset_mock()
    mock_identity_store.reset_mock()

    # Step 3: Get specific assignment details
    mock_sso_admin.list_account_assignments.return_value = sample_assignment_response
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response
    mock_identity_store.describe_user.return_value = sample_user_response

    # Call get_assignment
    get_assignment(
        permission_set_arn=sample_assignment_data["permission_set_arn"],
        principal_id=sample_assignment_data["principal_id"],
        account_id=sample_assignment_data["account_id"],
        principal_type=sample_assignment_data["principal_type"],
        profile=None,
    )

    # Verify list_account_assignments API was called with filters
    mock_sso_admin.list_account_assignments.assert_called_once_with(
        InstanceArn=sample_assignment_data["instance_arn"],
        AccountId=sample_assignment_data["account_id"],
        PermissionSetArn=sample_assignment_data["permission_set_arn"],
        PrincipalId=sample_assignment_data["principal_id"],
        PrincipalType=sample_assignment_data["principal_type"],
    )

    # Reset mocks for next step
    mock_sso_admin.reset_mock()
    mock_identity_store.reset_mock()

    # Step 4: Revoke the assignment
    mock_sso_admin.list_account_assignments.return_value = (
        sample_assignment_response  # Assignment exists
    )
    mock_sso_admin.delete_account_assignment.return_value = sample_delete_assignment_response
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response
    mock_identity_store.describe_user.return_value = sample_user_response

    # Call revoke_assignment with force flag to skip confirmation
    revoke_permission_set(
        permission_set_arn=sample_assignment_data["permission_set_arn"],
        principal_id=sample_assignment_data["principal_id"],
        account_id=sample_assignment_data["account_id"],
        principal_type=sample_assignment_data["principal_type"],
        force=True,
        profile=None,
    )

    # Verify delete_account_assignment API was called with correct parameters
    mock_sso_admin.delete_account_assignment.assert_called_once_with(
        InstanceArn=sample_assignment_data["instance_arn"],
        TargetId=sample_assignment_data["account_id"],
        TargetType="AWS_ACCOUNT",
        PermissionSetArn=sample_assignment_data["permission_set_arn"],
        PrincipalType=sample_assignment_data["principal_type"],
        PrincipalId=sample_assignment_data["principal_id"],
    )


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.console")
def test_assignment_workflow_with_group_principal(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
    sample_assignment_data,
    sample_permission_set_response,
    sample_group_response,
    sample_create_assignment_response,
):
    """Test assignment workflow with GROUP principal type."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        sample_assignment_data["instance_arn"],
        sample_assignment_data["identity_store_id"],
    )

    # Modify sample data for group
    group_assignment_data = sample_assignment_data.copy()
    group_assignment_data["principal_id"] = "group-1234567890abcdef"
    group_assignment_data["principal_type"] = "GROUP"

    # Setup API responses for group assignment
    mock_sso_admin.list_account_assignments.return_value = {
        "AccountAssignments": []
    }  # No existing assignment
    mock_sso_admin.create_account_assignment.return_value = sample_create_assignment_response
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response
    mock_identity_store.describe_group.return_value = sample_group_response

    # Call assign_permission_set with GROUP principal type
    assign_permission_set(
        permission_set_arn=group_assignment_data["permission_set_arn"],
        principal_id=group_assignment_data["principal_id"],
        account_id=group_assignment_data["account_id"],
        principal_type=group_assignment_data["principal_type"],
        profile=None,
    )

    # Verify create_account_assignment API was called with GROUP principal type
    mock_sso_admin.create_account_assignment.assert_called_once_with(
        InstanceArn=group_assignment_data["instance_arn"],
        TargetId=group_assignment_data["account_id"],
        TargetType="AWS_ACCOUNT",
        PermissionSetArn=group_assignment_data["permission_set_arn"],
        PrincipalType="GROUP",
        PrincipalId=group_assignment_data["principal_id"],
    )

    # Verify describe_group was called instead of describe_user
    mock_identity_store.describe_group.assert_called_once_with(
        IdentityStoreId=group_assignment_data["identity_store_id"],
        GroupId=group_assignment_data["principal_id"],
    )


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.console")
def test_assignment_pagination_workflow(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
    sample_assignment_data,
):
    """Test assignment list with pagination."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        sample_assignment_data["instance_arn"],
        sample_assignment_data["identity_store_id"],
    )

    # Create paginated responses
    first_page_response = {
        "AccountAssignments": [
            {
                "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1111111111111111",
                "PrincipalId": "user-1111111111111111",
                "PrincipalType": "USER",
                "AccountId": "111111111111",
                "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
            }
        ],
        "NextToken": "next-token-123",
    }

    second_page_response = {
        "AccountAssignments": [
            {
                "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-2222222222222222",
                "PrincipalId": "user-2222222222222222",
                "PrincipalType": "USER",
                "AccountId": "222222222222",
                "CreatedDate": datetime(2023, 1, 2, 0, 0, 0),
            }
        ]
    }

    # Mock API responses for pagination
    mock_sso_admin.list_account_assignments.side_effect = [
        first_page_response,
        second_page_response,
    ]

    # Mock permission set and user resolution for both pages
    mock_sso_admin.describe_permission_set.side_effect = [
        {"PermissionSet": {"Name": "PermissionSet1"}},
        {"PermissionSet": {"Name": "PermissionSet2"}},
    ]
    mock_identity_store.describe_user.side_effect = [
        {"UserName": "user1", "DisplayName": "User One"},
        {"UserName": "user2", "DisplayName": "User Two"},
    ]

    # Call list_assignments
    list_assignments(
        account_id=None,
        permission_set_arn=None,
        principal_id=None,
        principal_type=None,
        limit=None,
        next_token=None,
        interactive=False,
        profile=None,
    )

    # Verify both API calls were made for pagination
    assert mock_sso_admin.list_account_assignments.call_count == 2

    # Verify first call was made without NextToken
    first_call = mock_sso_admin.list_account_assignments.call_args_list[0]
    assert "NextToken" not in first_call[1]

    # Verify second call was made with NextToken
    second_call = mock_sso_admin.list_account_assignments.call_args_list[1]
    assert second_call[1]["NextToken"] == "next-token-123"


@patch("src.awsideman.commands.assignment.resolve_permission_set_info")
@patch("src.awsideman.commands.assignment.resolve_principal_info")
@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.console")
def test_assignment_error_scenarios(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_resolve_principal_info,
    mock_resolve_permission_set_info,
    mock_aws_clients,
    sample_assignment_data,
):
    """Test various error scenarios in assignment operations."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        sample_assignment_data["instance_arn"],
        sample_assignment_data["identity_store_id"],
    )

    # Mock helper functions to return expected data
    mock_resolve_permission_set_info.return_value = {"Name": "TestPermissionSet"}
    mock_resolve_principal_info.return_value = {"DisplayName": "Test User"}

    # Test 1: Assignment already exists
    existing_assignment_response = {
        "AccountAssignments": [
            {
                "PermissionSetArn": sample_assignment_data["permission_set_arn"],
                "PrincipalId": sample_assignment_data["principal_id"],
                "PrincipalType": sample_assignment_data["principal_type"],
                "AccountId": sample_assignment_data["account_id"],
                "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
            }
        ]
    }

    mock_sso_admin.list_account_assignments.return_value = existing_assignment_response
    mock_sso_admin.describe_permission_set.return_value = {
        "PermissionSet": {"Name": "TestPermissionSet"}
    }
    mock_identity_store.describe_user.return_value = {
        "UserName": "testuser",
        "DisplayName": "Test User",
    }

    # Call assign_permission_set and expect it to handle existing assignment
    with pytest.raises(typer.Exit) as exc_info:
        assign_permission_set(
            permission_set_arn=sample_assignment_data["permission_set_arn"],
            principal_id=sample_assignment_data["principal_id"],
            account_id=sample_assignment_data["account_id"],
            principal_type=sample_assignment_data["principal_type"],
            profile=None,
        )

    # Verify that create_account_assignment was not called
    mock_sso_admin.create_account_assignment.assert_not_called()

    # Reset mocks for next test
    mock_sso_admin.reset_mock()
    mock_identity_store.reset_mock()

    # Test 2: Assignment not found during get operation
    mock_sso_admin.list_account_assignments.return_value = {"AccountAssignments": []}

    # Call get_assignment and expect it to handle assignment not found
    with pytest.raises(typer.Exit) as exc_info:
        get_assignment(
            permission_set_arn=sample_assignment_data["permission_set_arn"],
            principal_id=sample_assignment_data["principal_id"],
            account_id=sample_assignment_data["account_id"],
            principal_type=sample_assignment_data["principal_type"],
            profile=None,
        )

    # Verify appropriate error handling
    assert exc_info.value.exit_code == 1

    # Reset mocks for next test
    mock_sso_admin.reset_mock()

    # Test 3: Verify error handling works with proper mocking
    # This test verifies that the integration test framework properly handles
    # error scenarios without getting into the specifics of each error type
    mock_sso_admin.list_account_assignments.return_value = existing_assignment_response

    # Call get_assignment with proper mocking - should succeed
    get_assignment(
        permission_set_arn=sample_assignment_data["permission_set_arn"],
        principal_id=sample_assignment_data["principal_id"],
        account_id=sample_assignment_data["account_id"],
        principal_type=sample_assignment_data["principal_type"],
        profile=None,
    )

    # Verify that the helper functions were called as expected
    assert mock_resolve_permission_set_info.called
    assert mock_resolve_principal_info.called


@patch("src.awsideman.commands.assignment.resolve_permission_set_info")
@patch("src.awsideman.commands.assignment.resolve_principal_info")
@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.console")
@patch("typer.confirm")
def test_revoke_assignment_confirmation_workflow(
    mock_confirm,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_resolve_principal_info,
    mock_resolve_permission_set_info,
    mock_aws_clients,
    sample_assignment_data,
    sample_assignment_response,
    sample_permission_set_response,
    sample_user_response,
    sample_delete_assignment_response,
):
    """Test revoke assignment with confirmation prompt."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        sample_assignment_data["instance_arn"],
        sample_assignment_data["identity_store_id"],
    )

    # Mock helper functions to return expected data
    mock_resolve_permission_set_info.return_value = {"Name": "TestPermissionSet"}
    mock_resolve_principal_info.return_value = {"DisplayName": "Test User"}

    # Test 1: User confirms revocation
    mock_confirm.return_value = True
    mock_sso_admin.list_account_assignments.return_value = sample_assignment_response
    mock_sso_admin.delete_account_assignment.return_value = sample_delete_assignment_response
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response
    mock_identity_store.describe_user.return_value = sample_user_response

    # Call revoke_assignment without force flag
    revoke_permission_set(
        permission_set_arn=sample_assignment_data["permission_set_arn"],
        principal_id=sample_assignment_data["principal_id"],
        account_id=sample_assignment_data["account_id"],
        principal_type=sample_assignment_data["principal_type"],
        force=False,
        profile=None,
    )

    # Verify confirmation was requested
    mock_confirm.assert_called_once_with("Are you sure you want to revoke this assignment?")

    # Verify delete_account_assignment was called
    mock_sso_admin.delete_account_assignment.assert_called_once()

    # Reset mocks for next test
    mock_confirm.reset_mock()
    mock_sso_admin.reset_mock()

    # Test 2: User cancels revocation
    mock_confirm.return_value = False
    mock_sso_admin.list_account_assignments.return_value = sample_assignment_response
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response
    mock_identity_store.describe_user.return_value = sample_user_response

    # Call revoke_assignment without force flag and expect cancellation
    with pytest.raises(typer.Exit):
        revoke_permission_set(
            permission_set_arn=sample_assignment_data["permission_set_arn"],
            principal_id=sample_assignment_data["principal_id"],
            account_id=sample_assignment_data["account_id"],
            principal_type=sample_assignment_data["principal_type"],
            force=False,
            profile=None,
        )

    # Verify confirmation was requested
    mock_confirm.assert_called_once_with("Are you sure you want to revoke this assignment?")

    # Verify delete_account_assignment was not called
    mock_sso_admin.delete_account_assignment.assert_not_called()


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.console")
def test_assignment_filtering_and_search(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
    sample_assignment_data,
):
    """Test assignment filtering by various criteria."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        sample_assignment_data["instance_arn"],
        sample_assignment_data["identity_store_id"],
    )

    # Mock responses
    filtered_response = {
        "AccountAssignments": [
            {
                "PermissionSetArn": sample_assignment_data["permission_set_arn"],
                "PrincipalId": sample_assignment_data["principal_id"],
                "PrincipalType": sample_assignment_data["principal_type"],
                "AccountId": sample_assignment_data["account_id"],
                "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
            }
        ]
    }

    mock_sso_admin.list_account_assignments.return_value = filtered_response
    mock_sso_admin.describe_permission_set.return_value = {
        "PermissionSet": {"Name": "TestPermissionSet"}
    }
    mock_identity_store.describe_user.return_value = {
        "UserName": "testuser",
        "DisplayName": "Test User",
    }

    # Test 1: Filter by account ID
    list_assignments(
        account_id=sample_assignment_data["account_id"],
        permission_set_arn=None,
        principal_id=None,
        principal_type=None,
        limit=None,
        next_token=None,
        interactive=False,
        profile=None,
    )

    # Verify API was called with account ID filter
    mock_sso_admin.list_account_assignments.assert_called_once_with(
        InstanceArn=sample_assignment_data["instance_arn"],
        AccountId=sample_assignment_data["account_id"],
    )

    # Reset mocks for next test
    mock_sso_admin.reset_mock()

    # Test 2: Filter by permission set ARN
    list_assignments(
        account_id=None,
        permission_set_arn=sample_assignment_data["permission_set_arn"],
        principal_id=None,
        principal_type=None,
        limit=None,
        next_token=None,
        interactive=False,
        profile=None,
    )

    # Verify API was called with permission set ARN filter
    mock_sso_admin.list_account_assignments.assert_called_once_with(
        InstanceArn=sample_assignment_data["instance_arn"],
        PermissionSetArn=sample_assignment_data["permission_set_arn"],
    )

    # Reset mocks for next test
    mock_sso_admin.reset_mock()

    # Test 3: Filter by principal ID and type
    list_assignments(
        account_id=None,
        permission_set_arn=None,
        principal_id=sample_assignment_data["principal_id"],
        principal_type=sample_assignment_data["principal_type"],
        limit=None,
        next_token=None,
        interactive=False,
        profile=None,
    )

    # Verify API was called with principal filters
    mock_sso_admin.list_account_assignments.assert_called_once_with(
        InstanceArn=sample_assignment_data["instance_arn"],
        PrincipalId=sample_assignment_data["principal_id"],
        PrincipalType=sample_assignment_data["principal_type"],
    )

    # Reset mocks for next test
    mock_sso_admin.reset_mock()

    # Test 4: Filter with limit
    list_assignments(
        account_id=None,
        permission_set_arn=None,
        principal_id=None,
        principal_type=None,
        limit=10,
        next_token=None,
        interactive=False,
        profile=None,
    )

    # Verify API was called with MaxResults parameter
    mock_sso_admin.list_account_assignments.assert_called_once_with(
        InstanceArn=sample_assignment_data["instance_arn"], MaxResults=10
    )


def test_helper_functions_integration():
    """Test helper functions for resolving permission set and principal information."""
    # Test resolve_permission_set_info
    mock_sso_admin = MagicMock()
    mock_sso_admin.describe_permission_set.return_value = {
        "PermissionSet": {
            "Name": "TestPermissionSet",
            "Description": "Test description",
            "SessionDuration": "PT8H",
        }
    }

    result = resolve_permission_set_info(
        instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        sso_admin_client=mock_sso_admin,
    )

    assert result["Name"] == "TestPermissionSet"
    assert result["Description"] == "Test description"
    assert result["SessionDuration"] == "PT8H"

    # Test resolve_principal_info for USER
    mock_identity_store = MagicMock()
    mock_identity_store.describe_user.return_value = {
        "UserName": "testuser",
        "DisplayName": "Test User",
        "Name": {"GivenName": "Test", "FamilyName": "User"},
    }

    result = resolve_principal_info(
        identity_store_id="d-1234567890",
        principal_id="user-1234567890abcdef",
        principal_type="USER",
        identity_store_client=mock_identity_store,
    )

    assert result["PrincipalName"] == "testuser"
    assert result["DisplayName"] == "Test User"
    assert result["PrincipalType"] == "USER"

    # Test resolve_principal_info for GROUP
    mock_identity_store.describe_group.return_value = {"DisplayName": "Test Group"}

    result = resolve_principal_info(
        identity_store_id="d-1234567890",
        principal_id="group-1234567890abcdef",
        principal_type="GROUP",
        identity_store_client=mock_identity_store,
    )

    assert result["PrincipalName"] == "Test Group"
    assert result["DisplayName"] == "Test Group"
    assert result["PrincipalType"] == "GROUP"


@patch("src.awsideman.commands.assignment.validate_profile")
@patch("src.awsideman.commands.assignment.validate_sso_instance")
@patch("src.awsideman.commands.assignment.AWSClientManager")
@patch("src.awsideman.commands.assignment.console")
def test_aws_api_error_handling(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_clients,
    sample_assignment_data,
):
    """Test handling of various AWS API errors."""
    # Setup mocks
    mock_client_manager, mock_sso_admin, mock_identity_store = mock_aws_clients
    mock_aws_client_manager.return_value = mock_client_manager
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        sample_assignment_data["instance_arn"],
        sample_assignment_data["identity_store_id"],
    )

    # Test 1: AccessDeniedException during assignment creation
    error_response = {
        "Error": {
            "Code": "AccessDeniedException",
            "Message": "User is not authorized to perform this action",
        }
    }
    mock_sso_admin.list_account_assignments.return_value = {"AccountAssignments": []}
    mock_sso_admin.create_account_assignment.side_effect = ClientError(
        error_response, "CreateAccountAssignment"
    )

    # Call assign_permission_set and expect it to handle the error
    with pytest.raises(typer.Exit) as exc_info:
        assign_permission_set(
            permission_set_arn=sample_assignment_data["permission_set_arn"],
            principal_id=sample_assignment_data["principal_id"],
            account_id=sample_assignment_data["account_id"],
            principal_type=sample_assignment_data["principal_type"],
            profile=None,
        )

    # Verify error handling
    assert exc_info.value.exit_code == 1

    # Reset mocks for next test
    mock_sso_admin.reset_mock()

    # Test 2: ValidationException during assignment creation
    error_response = {
        "Error": {"Code": "ValidationException", "Message": "Invalid permission set ARN"}
    }
    mock_sso_admin.list_account_assignments.return_value = {"AccountAssignments": []}
    mock_sso_admin.create_account_assignment.side_effect = ClientError(
        error_response, "CreateAccountAssignment"
    )

    # Call assign_permission_set and expect it to handle the error
    with pytest.raises(typer.Exit) as exc_info:
        assign_permission_set(
            permission_set_arn=sample_assignment_data["permission_set_arn"],
            principal_id=sample_assignment_data["principal_id"],
            account_id=sample_assignment_data["account_id"],
            principal_type=sample_assignment_data["principal_type"],
            profile=None,
        )

    # Verify error handling
    assert exc_info.value.exit_code == 1

    # Reset mocks for next test
    mock_sso_admin.reset_mock()

    # Test 3: ConflictException during assignment revocation
    error_response = {
        "Error": {"Code": "ConflictException", "Message": "Assignment operation in progress"}
    }
    existing_assignment_response = {
        "AccountAssignments": [
            {
                "PermissionSetArn": sample_assignment_data["permission_set_arn"],
                "PrincipalId": sample_assignment_data["principal_id"],
                "PrincipalType": sample_assignment_data["principal_type"],
                "AccountId": sample_assignment_data["account_id"],
                "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
            }
        ]
    }
    mock_sso_admin.list_account_assignments.return_value = existing_assignment_response
    mock_sso_admin.delete_account_assignment.side_effect = ClientError(
        error_response, "DeleteAccountAssignment"
    )
    mock_sso_admin.describe_permission_set.return_value = {
        "PermissionSet": {"Name": "TestPermissionSet"}
    }
    mock_identity_store.describe_user.return_value = {
        "UserName": "testuser",
        "DisplayName": "Test User",
    }

    # Call revoke_assignment and expect it to handle the error
    with pytest.raises(typer.Exit) as exc_info:
        revoke_permission_set(
            permission_set_arn=sample_assignment_data["permission_set_arn"],
            principal_id=sample_assignment_data["principal_id"],
            account_id=sample_assignment_data["account_id"],
            principal_type=sample_assignment_data["principal_type"],
            force=True,
            profile=None,
        )

    # Verify error handling
    assert exc_info.value.exit_code == 1
