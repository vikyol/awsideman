"""Integration tests for permission set commands."""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
import typer
from botocore.exceptions import ClientError

from src.awsideman.commands.permission_set import (
    create_permission_set,
    delete_permission_set,
    get_permission_set,
    update_permission_set,
)


@pytest.fixture
def mock_aws_client():
    """Create a mock AWS client."""
    mock = MagicMock()
    # Mock SSO Admin client
    mock_sso_admin = MagicMock()
    mock.get_client.return_value = mock_sso_admin
    return mock, mock_sso_admin


@pytest.fixture
def sample_permission_set_response():
    """Sample permission set response for testing."""
    return {
        "PermissionSet": {
            "Name": "TestPermissionSet",
            "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            "Description": "Test permission set description",
            "SessionDuration": "PT8H",
            "RelayState": "https://console.aws.amazon.com/",
            "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
            "LastModifiedDate": datetime(2023, 1, 2, 0, 0, 0),
        }
    }


@pytest.fixture
def sample_updated_permission_set_response():
    """Sample updated permission set response for testing."""
    return {
        "PermissionSet": {
            "Name": "TestPermissionSet",
            "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            "Description": "Updated test permission set description",
            "SessionDuration": "PT12H",
            "RelayState": "https://console.aws.amazon.com/ec2/",
            "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
            "LastModifiedDate": datetime(2023, 1, 3, 0, 0, 0),
        }
    }


@pytest.fixture
def sample_create_response():
    """Sample create permission set response for testing."""
    return {
        "PermissionSet": {
            "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
        }
    }


@pytest.fixture
def sample_managed_policies_response():
    """Sample managed policies response for testing."""
    return {
        "AttachedManagedPolicies": [
            {"Name": "AdministratorAccess", "Arn": "arn:aws:iam::aws:policy/AdministratorAccess"}
        ]
    }


@pytest.fixture
def sample_updated_managed_policies_response():
    """Sample updated managed policies response for testing."""
    return {
        "AttachedManagedPolicies": [
            {"Name": "AdministratorAccess", "Arn": "arn:aws:iam::aws:policy/AdministratorAccess"},
            {"Name": "ReadOnlyAccess", "Arn": "arn:aws:iam::aws:policy/ReadOnlyAccess"},
        ]
    }


@patch("src.awsideman.commands.permission_set.validate_permission_set_name")
@patch("src.awsideman.commands.permission_set.validate_permission_set_description")
@patch("src.awsideman.commands.permission_set.validate_aws_managed_policy_arn")
@patch("src.awsideman.commands.permission_set.resolve_permission_set_identifier")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
@patch("typer.confirm")
def test_permission_set_lifecycle(
    mock_confirm,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_resolve_identifier,
    mock_validate_policy_arn,
    mock_validate_description,
    mock_validate_name,
    mock_aws_client,
    sample_permission_set_response,
    sample_updated_permission_set_response,
    sample_create_response,
    sample_managed_policies_response,
    sample_updated_managed_policies_response,
):
    """Test complete permission set lifecycle (create, get, update, delete)."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )
    mock_validate_name.return_value = True
    mock_validate_description.return_value = True
    mock_validate_policy_arn.return_value = True
    mock_confirm.return_value = True

    # Set up permission set ARN
    permission_set_arn = "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    mock_resolve_identifier.return_value = permission_set_arn

    # Step 1: Create permission set
    # Mock create_permission_set API response
    mock_sso_admin.create_permission_set.return_value = sample_create_response
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = (
        sample_managed_policies_response
    )

    # Call create_permission_set
    result = create_permission_set(
        name="TestPermissionSet",
        description="Test permission set description",
        session_duration="PT8H",
        relay_state="https://console.aws.amazon.com/",
        managed_policy=["arn:aws:iam::aws:policy/AdministratorAccess"],
        profile=None,
    )

    # Verify create_permission_set API was called with correct parameters
    mock_sso_admin.create_permission_set.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        Name="TestPermissionSet",
        Description="Test permission set description",
        SessionDuration="PT8H",
        RelayState="https://console.aws.amazon.com/",
    )

    # Verify attach_managed_policy_to_permission_set API was called
    mock_sso_admin.attach_managed_policy_to_permission_set.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        PermissionSetArn=permission_set_arn,
        ManagedPolicyArn="arn:aws:iam::aws:policy/AdministratorAccess",
    )

    # Reset mocks for next step
    mock_sso_admin.reset_mock()

    # Step 2: Get permission set
    # Mock describe_permission_set API response
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = (
        sample_managed_policies_response
    )

    # Call get_permission_set
    result = get_permission_set(identifier="TestPermissionSet", profile=None)

    # Verify describe_permission_set API was called
    mock_sso_admin.describe_permission_set.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        PermissionSetArn=permission_set_arn,
    )

    # Verify list_managed_policies_in_permission_set API was called
    mock_sso_admin.list_managed_policies_in_permission_set.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        PermissionSetArn=permission_set_arn,
    )

    # Reset mocks for next step
    mock_sso_admin.reset_mock()

    # Step 3: Update permission set
    # Mock update_permission_set API response
    mock_sso_admin.update_permission_set.return_value = {}
    mock_sso_admin.describe_permission_set.return_value = sample_updated_permission_set_response
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = (
        sample_updated_managed_policies_response
    )

    # Call update_permission_set
    result = update_permission_set(  # noqa: F841
        identifier="TestPermissionSet",
        description="Updated test permission set description",
        session_duration="PT12H",
        relay_state="https://console.aws.amazon.com/ec2/",
        add_managed_policy=["arn:aws:iam::aws:policy/ReadOnlyAccess"],
        remove_managed_policy=None,
        profile=None,
    )

    # Verify update_permission_set API was called with correct parameters
    mock_sso_admin.update_permission_set.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        PermissionSetArn=permission_set_arn,
        Description="Updated test permission set description",
        SessionDuration="PT12H",
        RelayState="https://console.aws.amazon.com/ec2/",
    )

    # Verify attach_managed_policy_to_permission_set API was called for the new policy
    mock_sso_admin.attach_managed_policy_to_permission_set.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        PermissionSetArn=permission_set_arn,
        ManagedPolicyArn="arn:aws:iam::aws:policy/ReadOnlyAccess",
    )

    # Reset mocks for next step
    mock_sso_admin.reset_mock()

    # Step 4: Delete permission set
    # Mock delete_permission_set API response
    mock_sso_admin.delete_permission_set.return_value = {}
    mock_sso_admin.describe_permission_set.return_value = sample_updated_permission_set_response

    # Call delete_permission_set
    delete_permission_set(identifier="TestPermissionSet", profile=None)

    # Verify delete_permission_set API was called
    mock_sso_admin.delete_permission_set.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        PermissionSetArn=permission_set_arn,
    )


@patch("src.awsideman.commands.permission_set.validate_permission_set_name")
@patch("src.awsideman.commands.permission_set.validate_permission_set_description")
@patch("src.awsideman.commands.permission_set.validate_aws_managed_policy_arn")
@patch("src.awsideman.commands.permission_set.resolve_permission_set_identifier")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_command_chaining_and_data_consistency(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_resolve_identifier,
    mock_validate_policy_arn,
    mock_validate_description,
    mock_validate_name,
    mock_aws_client,
    sample_permission_set_response,
    sample_create_response,
    sample_managed_policies_response,
):
    """Test command chaining and data consistency."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )
    mock_validate_name.return_value = True
    mock_validate_description.return_value = True
    mock_validate_policy_arn.return_value = True

    # Set up permission set ARN
    permission_set_arn = "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    mock_resolve_identifier.return_value = permission_set_arn

    # Step 1: Create permission set
    mock_sso_admin.create_permission_set.return_value = sample_create_response
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = (
        sample_managed_policies_response
    )

    # Call create_permission_set
    create_permission_set(
        name="TestPermissionSet",
        description="Test permission set description",
        session_duration="PT8H",
        relay_state="https://console.aws.amazon.com/",
        managed_policy=["arn:aws:iam::aws:policy/AdministratorAccess"],
        profile=None,
    )

    # Step 2: Get permission set to verify data consistency
    get_result = get_permission_set(identifier="TestPermissionSet", profile=None)

    # Verify that the get_result contains the same data as what was created
    assert get_result["Name"] == "TestPermissionSet"
    assert get_result["Description"] == "Test permission set description"
    assert get_result["SessionDuration"] == "PT8H"
    assert get_result["RelayState"] == "https://console.aws.amazon.com/"
    assert get_result["PermissionSetArn"] == permission_set_arn


@patch("src.awsideman.commands.permission_set.validate_permission_set_name")
@patch("src.awsideman.commands.permission_set.validate_permission_set_description")
@patch("src.awsideman.commands.permission_set.validate_aws_managed_policy_arn")
@patch("src.awsideman.commands.permission_set.resolve_permission_set_identifier")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_error_recovery_scenarios(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_resolve_identifier,
    mock_validate_policy_arn,
    mock_validate_description,
    mock_validate_name,
    mock_aws_client,
    sample_permission_set_response,
    sample_create_response,
):
    """Test error recovery scenarios."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )
    mock_validate_name.return_value = True
    mock_validate_description.return_value = True
    mock_validate_policy_arn.return_value = True

    # Set up permission set ARN
    permission_set_arn = "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    mock_resolve_identifier.return_value = permission_set_arn

    # Scenario 1: Create permission set succeeds but policy attachment fails
    mock_sso_admin.create_permission_set.return_value = sample_create_response
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response

    # Mock policy attachment to fail with AccessDeniedException
    error_response = {
        "Error": {
            "Code": "AccessDeniedException",
            "Message": "User is not authorized to perform this action",
        }
    }
    mock_sso_admin.attach_managed_policy_to_permission_set.side_effect = ClientError(
        error_response, "AttachManagedPolicyToPermissionSet"
    )
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = {
        "AttachedManagedPolicies": []
    }

    # Call create_permission_set and expect it to handle the policy attachment failure gracefully
    with pytest.raises(typer.Exit) as exc_info:
        create_permission_set(
            name="TestPermissionSet",
            description="Test permission set description",
            session_duration="PT8H",
            relay_state="https://console.aws.amazon.com/",
            managed_policy=["arn:aws:iam::aws:policy/AdministratorAccess"],
            profile=None,
        )

    # Verify that the permission set was created despite the policy attachment failure
    mock_sso_admin.create_permission_set.assert_called_once()
    mock_sso_admin.attach_managed_policy_to_permission_set.assert_called_once()

    # Reset mocks for next scenario
    mock_sso_admin.reset_mock()

    # Scenario 2: Update permission set with invalid policy ARN
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response
    mock_sso_admin.update_permission_set.return_value = {}
    mock_validate_policy_arn.side_effect = [False, True]  # First policy invalid, second valid

    # Call update_permission_set with one invalid and one valid policy
    with pytest.raises(typer.Exit) as exc_info:
        update_permission_set(
            identifier="TestPermissionSet",
            description=None,
            session_duration=None,
            relay_state=None,
            add_managed_policy=["invalid:arn", "arn:aws:iam::aws:policy/ReadOnlyAccess"],
            remove_managed_policy=None,
            profile=None,
        )

    # Verify that validate_aws_managed_policy_arn was called twice
    assert mock_validate_policy_arn.call_count == 2

    # Reset mocks for next scenario
    mock_sso_admin.reset_mock()
    mock_validate_policy_arn.reset_mock()
    mock_validate_policy_arn.side_effect = None
    mock_validate_policy_arn.return_value = True

    # Scenario 3: Delete non-existent permission set
    # Mock delete_permission_set to raise ResourceNotFoundException
    error_response = {
        "Error": {"Code": "ResourceNotFoundException", "Message": "Permission set not found"}
    }
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response
    mock_sso_admin.delete_permission_set.side_effect = ClientError(
        error_response, "DeletePermissionSet"
    )

    # Call delete_permission_set and expect it to handle the error
    with pytest.raises(typer.Exit) as exc_info:  # noqa: F841
        delete_permission_set(identifier="NonExistentPermissionSet", profile=None)

    # Verify that appropriate error messages were displayed
    mock_console.print.assert_any_call(
        "[red]Error: Permission set 'NonExistentPermissionSet' not found.[/red]"
    )
