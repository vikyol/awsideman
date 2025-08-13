"""Tests for permission set update command."""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
import typer
from botocore.exceptions import ClientError, EndpointConnectionError

from src.awsideman.commands.permission_set import update_permission_set


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
            "Description": "Updated test permission set description",
            "SessionDuration": "PT4H",
            "RelayState": "https://console.aws.amazon.com/",
            "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
            "LastModifiedDate": datetime(2023, 1, 2, 0, 0, 0),
        }
    }


@pytest.fixture
def sample_managed_policies_response():
    """Sample managed policies response for testing."""
    return {
        "AttachedManagedPolicies": [
            {"Name": "AdministratorAccess", "Arn": "arn:aws:iam::aws:policy/AdministratorAccess"},
            {"Name": "ReadOnlyAccess", "Arn": "arn:aws:iam::aws:policy/ReadOnlyAccess"},
        ]
    }


@patch("src.awsideman.commands.permission_set.resolve_permission_set_identifier")
@patch("src.awsideman.commands.permission_set.validate_permission_set_description")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_update_permission_set_successful_basic_attributes(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_validate_description,
    mock_resolve_identifier,
    mock_aws_client,
    sample_permission_set_response,
    sample_managed_policies_response,
):
    """Test successful update_permission_set operation with basic attributes."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_description.return_value = True
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )
    mock_resolve_identifier.return_value = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    )

    # Mock the update_permission_set API response
    mock_sso_admin.update_permission_set.return_value = {}

    # Mock the describe_permission_set API response
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response

    # Mock the list_managed_policies_in_permission_set API response
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = (
        sample_managed_policies_response
    )

    # Call the function with basic attribute updates
    result = update_permission_set(
        identifier="TestPermissionSet",
        description="Updated test permission set description",
        session_duration="PT4H",
        relay_state="https://console.aws.amazon.com/",
        add_managed_policy=None,
        remove_managed_policy=None,
        profile=None,
    )

    # Verify input validation was called
    mock_validate_description.assert_called_with("Updated test permission set description")

    # Verify identifier resolution was called
    mock_resolve_identifier.assert_called_with(
        mock_client, "arn:aws:sso:::instance/ssoins-1234567890abcdef", "TestPermissionSet"
    )

    # Verify the function called the APIs correctly
    mock_sso_admin.update_permission_set.assert_called_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        PermissionSetArn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        Description="Updated test permission set description",
        SessionDuration="PT4H",
        RelayState="https://console.aws.amazon.com/",
    )

    # Verify describe_permission_set was called to get updated details
    mock_sso_admin.describe_permission_set.assert_called_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        PermissionSetArn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
    )

    # Verify list_managed_policies_in_permission_set was called
    mock_sso_admin.list_managed_policies_in_permission_set.assert_called_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        PermissionSetArn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
    )

    # Verify the function returned the correct data
    assert result["PermissionSet"]["Name"] == "TestPermissionSet"
    assert result["PermissionSet"]["Description"] == "Updated test permission set description"
    assert result["PermissionSet"]["SessionDuration"] == "PT4H"
    assert result["PermissionSet"]["RelayState"] == "https://console.aws.amazon.com/"
    assert len(result["AttachedManagedPolicies"]) == 2
    assert result["AttachedPolicies"] == []
    assert result["DetachedPolicies"] == []

    # Verify the console output
    mock_console.print.assert_any_call(
        "[blue]Updating permission set 'TestPermissionSet'...[/blue]"
    )
    mock_console.print.assert_any_call(
        "[green]Permission set attributes updated successfully.[/green]"
    )
    mock_console.print.assert_any_call(
        "[green]Updated description: Updated test permission set description[/green]"
    )
    mock_console.print.assert_any_call("[green]Updated session duration: PT4H[/green]")
    mock_console.print.assert_any_call(
        "[green]Updated relay state: https://console.aws.amazon.com/[/green]"
    )


@patch("src.awsideman.commands.permission_set.resolve_permission_set_identifier")
@patch("src.awsideman.commands.permission_set.validate_aws_managed_policy_arn")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_update_permission_set_successful_add_managed_policies(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_validate_policy_arn,
    mock_resolve_identifier,
    mock_aws_client,
    sample_permission_set_response,
    sample_managed_policies_response,
):
    """Test successful update_permission_set operation with adding managed policies."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_policy_arn.return_value = True
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )
    mock_resolve_identifier.return_value = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    )

    # Mock the attach_managed_policy_to_permission_set API response
    mock_sso_admin.attach_managed_policy_to_permission_set.return_value = {}

    # Mock the describe_permission_set API response
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response

    # Mock the list_managed_policies_in_permission_set API response
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = (
        sample_managed_policies_response
    )

    # Call the function with managed policies to add
    managed_policies_to_add = [
        "arn:aws:iam::aws:policy/PowerUserAccess",
        "arn:aws:iam::aws:policy/ViewOnlyAccess",
    ]
    result = update_permission_set(
        identifier="TestPermissionSet",
        description=None,
        session_duration=None,
        relay_state=None,
        add_managed_policy=managed_policies_to_add,
        remove_managed_policy=None,
        profile=None,
    )

    # Verify policy validation was called for each policy
    assert mock_validate_policy_arn.call_count == 4  # 2 for validation, 2 for attachment
    mock_validate_policy_arn.assert_any_call("arn:aws:iam::aws:policy/PowerUserAccess")
    mock_validate_policy_arn.assert_any_call("arn:aws:iam::aws:policy/ViewOnlyAccess")

    # Verify attach_managed_policy_to_permission_set was called for each policy
    assert mock_sso_admin.attach_managed_policy_to_permission_set.call_count == 2
    mock_sso_admin.attach_managed_policy_to_permission_set.assert_any_call(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        PermissionSetArn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        ManagedPolicyArn="arn:aws:iam::aws:policy/PowerUserAccess",
    )
    mock_sso_admin.attach_managed_policy_to_permission_set.assert_any_call(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        PermissionSetArn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        ManagedPolicyArn="arn:aws:iam::aws:policy/ViewOnlyAccess",
    )

    # Verify the function returned the correct data with attached policies
    assert len(result["AttachedPolicies"]) == 2
    assert result["AttachedPolicies"][0]["Name"] == "PowerUserAccess"
    assert result["AttachedPolicies"][0]["Arn"] == "arn:aws:iam::aws:policy/PowerUserAccess"
    assert result["AttachedPolicies"][1]["Name"] == "ViewOnlyAccess"
    assert result["AttachedPolicies"][1]["Arn"] == "arn:aws:iam::aws:policy/ViewOnlyAccess"
    assert result["DetachedPolicies"] == []

    # Verify the console output
    mock_console.print.assert_any_call("[blue]Attaching 2 managed policies...[/blue]")
    mock_console.print.assert_any_call("[green]Attached policy: PowerUserAccess[/green]")
    mock_console.print.assert_any_call("[green]Attached policy: ViewOnlyAccess[/green]")


@patch("src.awsideman.commands.permission_set.resolve_permission_set_identifier")
@patch("src.awsideman.commands.permission_set.validate_aws_managed_policy_arn")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_update_permission_set_successful_remove_managed_policies(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_validate_policy_arn,
    mock_resolve_identifier,
    mock_aws_client,
    sample_permission_set_response,
    sample_managed_policies_response,
):
    """Test successful update_permission_set operation with removing managed policies."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_policy_arn.return_value = True
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )
    mock_resolve_identifier.return_value = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    )

    # Mock the detach_managed_policy_from_permission_set API response
    mock_sso_admin.detach_managed_policy_from_permission_set.return_value = {}

    # Mock the describe_permission_set API response
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response

    # Mock the list_managed_policies_in_permission_set API response
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = (
        sample_managed_policies_response
    )

    # Call the function with managed policies to remove
    managed_policies_to_remove = ["arn:aws:iam::aws:policy/AdministratorAccess"]
    result = update_permission_set(
        identifier="TestPermissionSet",
        description=None,
        session_duration=None,
        relay_state=None,
        add_managed_policy=None,
        remove_managed_policy=managed_policies_to_remove,
        profile=None,
    )

    # Verify policy validation was called for each policy
    assert mock_validate_policy_arn.call_count == 2  # 1 for validation, 1 for detachment
    mock_validate_policy_arn.assert_any_call("arn:aws:iam::aws:policy/AdministratorAccess")

    # Verify detach_managed_policy_from_permission_set was called
    mock_sso_admin.detach_managed_policy_from_permission_set.assert_called_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        PermissionSetArn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        ManagedPolicyArn="arn:aws:iam::aws:policy/AdministratorAccess",
    )

    # Verify the function returned the correct data with detached policies
    assert result["AttachedPolicies"] == []
    assert len(result["DetachedPolicies"]) == 1
    assert result["DetachedPolicies"][0]["Name"] == "AdministratorAccess"
    assert result["DetachedPolicies"][0]["Arn"] == "arn:aws:iam::aws:policy/AdministratorAccess"

    # Verify the console output
    mock_console.print.assert_any_call("[blue]Detaching 1 managed policies...[/blue]")
    mock_console.print.assert_any_call("[green]Detached policy: AdministratorAccess[/green]")


@patch("src.awsideman.commands.permission_set.resolve_permission_set_identifier")
@patch("src.awsideman.commands.permission_set.validate_permission_set_description")
@patch("src.awsideman.commands.permission_set.validate_aws_managed_policy_arn")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_update_permission_set_successful_combined_operations(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_validate_policy_arn,
    mock_validate_description,
    mock_resolve_identifier,
    mock_aws_client,
    sample_permission_set_response,
    sample_managed_policies_response,
):
    """Test successful update_permission_set operation with combined attribute and policy updates."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_description.return_value = True
    mock_validate_policy_arn.return_value = True
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )
    mock_resolve_identifier.return_value = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    )

    # Mock the update_permission_set API response
    mock_sso_admin.update_permission_set.return_value = {}

    # Mock the attach/detach managed policy API responses
    mock_sso_admin.attach_managed_policy_to_permission_set.return_value = {}
    mock_sso_admin.detach_managed_policy_from_permission_set.return_value = {}

    # Mock the describe_permission_set API response
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response

    # Mock the list_managed_policies_in_permission_set API response
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = (
        sample_managed_policies_response
    )

    # Call the function with combined updates
    result = update_permission_set(
        identifier="TestPermissionSet",
        description="Updated description",
        session_duration="PT2H",
        relay_state=None,
        add_managed_policy=["arn:aws:iam::aws:policy/PowerUserAccess"],
        remove_managed_policy=["arn:aws:iam::aws:policy/AdministratorAccess"],
        profile=None,
    )

    # Verify all validations were called
    mock_validate_description.assert_called_with("Updated description")
    assert mock_validate_policy_arn.call_count == 4  # 2 for validation, 2 for operations

    # Verify the update_permission_set API was called
    mock_sso_admin.update_permission_set.assert_called_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        PermissionSetArn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        Description="Updated description",
        SessionDuration="PT2H",
    )

    # Verify policy operations were called
    mock_sso_admin.attach_managed_policy_to_permission_set.assert_called()
    mock_sso_admin.detach_managed_policy_from_permission_set.assert_called()

    # Verify the function returned the correct data
    assert len(result["AttachedPolicies"]) == 1
    assert len(result["DetachedPolicies"]) == 1
    assert result["AttachedPolicies"][0]["Name"] == "PowerUserAccess"
    assert result["DetachedPolicies"][0]["Name"] == "AdministratorAccess"


@patch("src.awsideman.commands.permission_set.resolve_permission_set_identifier")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_update_permission_set_successful_minimal_update(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_resolve_identifier,
    mock_aws_client,
    sample_permission_set_response,
    sample_managed_policies_response,
):
    """Test successful update_permission_set operation with minimal parameters."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )
    mock_resolve_identifier.return_value = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    )

    # Mock the update_permission_set API response
    mock_sso_admin.update_permission_set.return_value = {}

    # Mock the describe_permission_set API response
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response

    # Mock the list_managed_policies_in_permission_set API response
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = (
        sample_managed_policies_response
    )

    # Call the function with only session duration update
    result = update_permission_set(
        identifier="TestPermissionSet",
        description=None,
        session_duration="PT6H",
        relay_state=None,
        add_managed_policy=None,
        remove_managed_policy=None,
        profile=None,
    )

    # Verify the update_permission_set API was called with only session duration
    mock_sso_admin.update_permission_set.assert_called_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        PermissionSetArn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        SessionDuration="PT6H",
    )

    # Verify no policy operations were called
    mock_sso_admin.attach_managed_policy_to_permission_set.assert_not_called()
    mock_sso_admin.detach_managed_policy_from_permission_set.assert_not_called()

    # Verify the function returned the correct data
    assert result["AttachedPolicies"] == []
    assert result["DetachedPolicies"] == []

    # Verify the console output
    mock_console.print.assert_any_call("[green]Updated session duration: PT6H[/green]")


@patch("src.awsideman.commands.permission_set.resolve_permission_set_identifier")
@patch("src.awsideman.commands.permission_set.validate_aws_managed_policy_arn")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_update_permission_set_policy_attachment_partial_failure(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_validate_policy_arn,
    mock_resolve_identifier,
    mock_aws_client,
    sample_permission_set_response,
    sample_managed_policies_response,
):
    """Test update_permission_set with partial policy attachment failure."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_policy_arn.return_value = True
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )
    mock_resolve_identifier.return_value = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    )

    # Mock the attach_managed_policy_to_permission_set API response with one failure
    error_response = {"Error": {"Code": "ResourceNotFoundException", "Message": "Policy not found"}}
    mock_sso_admin.attach_managed_policy_to_permission_set.side_effect = [
        {},  # First policy succeeds
        ClientError(error_response, "AttachManagedPolicyToPermissionSet"),  # Second policy fails
    ]

    # Mock the describe_permission_set API response
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response

    # Mock the list_managed_policies_in_permission_set API response
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = (
        sample_managed_policies_response
    )

    # Call the function with managed policies
    managed_policies = [
        "arn:aws:iam::aws:policy/PowerUserAccess",
        "arn:aws:iam::aws:policy/NonExistentPolicy",
    ]
    result = update_permission_set(
        identifier="TestPermissionSet",
        description=None,
        session_duration=None,
        relay_state=None,
        add_managed_policy=managed_policies,
        remove_managed_policy=None,
        profile=None,
    )

    # Verify attach_managed_policy_to_permission_set was called for each policy
    assert mock_sso_admin.attach_managed_policy_to_permission_set.call_count == 2

    # Verify only the successful policy is in the result
    assert len(result["AttachedPolicies"]) == 1
    assert result["AttachedPolicies"][0]["Name"] == "PowerUserAccess"

    # Verify the console output includes warning for failed policy
    mock_console.print.assert_any_call("[green]Attached policy: PowerUserAccess[/green]")
    mock_console.print.assert_any_call(
        "[yellow]Warning: Failed to attach policy arn:aws:iam::aws:policy/NonExistentPolicy: ResourceNotFoundException - Policy not found[/yellow]"
    )
    mock_console.print.assert_any_call(
        "[yellow]The permission set was updated but not all policies were attached.[/yellow]"
    )


@patch("src.awsideman.commands.permission_set.resolve_permission_set_identifier")
@patch("src.awsideman.commands.permission_set.validate_aws_managed_policy_arn")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_update_permission_set_policy_detachment_partial_failure(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_validate_policy_arn,
    mock_resolve_identifier,
    mock_aws_client,
    sample_permission_set_response,
    sample_managed_policies_response,
):
    """Test update_permission_set with partial policy detachment failure."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_policy_arn.return_value = True
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )
    mock_resolve_identifier.return_value = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    )

    # Mock the detach_managed_policy_from_permission_set API response with one failure
    error_response = {
        "Error": {
            "Code": "ResourceNotFoundException",
            "Message": "Policy not attached to permission set",
        }
    }
    mock_sso_admin.detach_managed_policy_from_permission_set.side_effect = [
        {},  # First policy succeeds
        ClientError(error_response, "DetachManagedPolicyFromPermissionSet"),  # Second policy fails
    ]

    # Mock the describe_permission_set API response
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response

    # Mock the list_managed_policies_in_permission_set API response
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = (
        sample_managed_policies_response
    )

    # Call the function with managed policies to remove
    managed_policies = [
        "arn:aws:iam::aws:policy/AdministratorAccess",
        "arn:aws:iam::aws:policy/NotAttachedPolicy",
    ]
    result = update_permission_set(
        identifier="TestPermissionSet",
        description=None,
        session_duration=None,
        relay_state=None,
        add_managed_policy=None,
        remove_managed_policy=managed_policies,
        profile=None,
    )

    # Verify detach_managed_policy_from_permission_set was called for each policy
    assert mock_sso_admin.detach_managed_policy_from_permission_set.call_count == 2

    # Verify only the successful policy is in the result
    assert len(result["DetachedPolicies"]) == 1
    assert result["DetachedPolicies"][0]["Name"] == "AdministratorAccess"

    # Verify the console output includes warning for failed policy
    mock_console.print.assert_any_call("[green]Detached policy: AdministratorAccess[/green]")
    mock_console.print.assert_any_call(
        "[yellow]Policy arn:aws:iam::aws:policy/NotAttachedPolicy is not attached to this permission set.[/yellow]"
    )


@patch("src.awsideman.commands.permission_set.resolve_permission_set_identifier")
@patch("src.awsideman.commands.permission_set.validate_aws_managed_policy_arn")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_update_permission_set_conflict_exception_policy_attachment(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_validate_policy_arn,
    mock_resolve_identifier,
    mock_aws_client,
    sample_permission_set_response,
    sample_managed_policies_response,
):
    """Test update_permission_set with ConflictException during policy attachment."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_policy_arn.return_value = True
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )
    mock_resolve_identifier.return_value = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    )

    # Mock the attach_managed_policy_to_permission_set API response with ConflictException
    error_response = {
        "Error": {"Code": "ConflictException", "Message": "Policy is already attached"}
    }
    mock_sso_admin.attach_managed_policy_to_permission_set.side_effect = ClientError(
        error_response, "AttachManagedPolicyToPermissionSet"
    )

    # Mock the describe_permission_set API response
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response

    # Mock the list_managed_policies_in_permission_set API response
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = (
        sample_managed_policies_response
    )

    # Call the function with managed policy to add
    result = update_permission_set(
        identifier="TestPermissionSet",
        description=None,
        session_duration=None,
        relay_state=None,
        add_managed_policy=["arn:aws:iam::aws:policy/AdministratorAccess"],
        remove_managed_policy=None,
        profile=None,
    )

    # Verify attach_managed_policy_to_permission_set was called
    mock_sso_admin.attach_managed_policy_to_permission_set.assert_called()

    # Verify no policies were added to the result
    assert len(result["AttachedPolicies"]) == 0

    # Verify the console output includes warning for conflict
    mock_console.print.assert_any_call(
        "[yellow]Policy arn:aws:iam::aws:policy/AdministratorAccess is already attached to this permission set.[/yellow]"
    )


@patch("src.awsideman.commands.permission_set.resolve_permission_set_identifier")
@patch("src.awsideman.commands.permission_set.validate_aws_managed_policy_arn")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_update_permission_set_skip_invalid_policy(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_validate_policy_arn,
    mock_resolve_identifier,
    mock_aws_client,
    sample_permission_set_response,
    sample_managed_policies_response,
):
    """Test update_permission_set skips invalid policy ARNs."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )
    mock_resolve_identifier.return_value = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    )

    # Mock policy validation - pass initial validation, then fail during attachment
    mock_validate_policy_arn.side_effect = [
        True,
        True,
        True,
        False,
    ]  # 2 for initial validation, 2 for attachment

    # Mock the attach_managed_policy_to_permission_set API response
    mock_sso_admin.attach_managed_policy_to_permission_set.return_value = {}

    # Mock the describe_permission_set API response
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response

    # Mock the list_managed_policies_in_permission_set API response
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = (
        sample_managed_policies_response
    )

    # Call the function with one valid and one invalid policy
    managed_policies = ["arn:aws:iam::aws:policy/PowerUserAccess", "invalid-policy-arn"]
    result = update_permission_set(
        identifier="TestPermissionSet",
        description=None,
        session_duration=None,
        relay_state=None,
        add_managed_policy=managed_policies,
        remove_managed_policy=None,
        profile=None,
    )

    # Verify policy validation was called for both policies (twice each - validation and attachment)
    assert mock_validate_policy_arn.call_count == 4

    # Verify attach_managed_policy_to_permission_set was called only once (for valid policy)
    mock_sso_admin.attach_managed_policy_to_permission_set.assert_called_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        PermissionSetArn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        ManagedPolicyArn="arn:aws:iam::aws:policy/PowerUserAccess",
    )

    # Verify only the valid policy is in the result
    assert len(result["AttachedPolicies"]) == 1
    assert result["AttachedPolicies"][0]["Name"] == "PowerUserAccess"

    # Verify the console output includes warning for invalid policy
    mock_console.print.assert_any_call(
        "[yellow]Skipping invalid policy ARN: invalid-policy-arn[/yellow]"
    )


@patch("src.awsideman.commands.permission_set.resolve_permission_set_identifier")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_update_permission_set_describe_failure_after_update(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_resolve_identifier,
    mock_aws_client,
):
    """Test update_permission_set when describe fails after update."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )
    mock_resolve_identifier.return_value = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    )

    # Mock the update_permission_set API response
    mock_sso_admin.update_permission_set.return_value = {}

    # Mock the describe_permission_set API error
    error_response = {
        "Error": {
            "Code": "AccessDeniedException",
            "Message": "User is not authorized to perform this action",
        }
    }
    mock_sso_admin.describe_permission_set.side_effect = ClientError(
        error_response, "DescribePermissionSet"
    )

    # Call the function
    result = update_permission_set(
        identifier="TestPermissionSet",
        description="Updated description",
        session_duration=None,
        relay_state=None,
        add_managed_policy=None,
        remove_managed_policy=None,
        profile=None,
    )

    # Verify the function called the APIs correctly
    mock_sso_admin.update_permission_set.assert_called()
    mock_sso_admin.describe_permission_set.assert_called()

    # Verify the function still returns the basic data
    assert (
        result["PermissionSetArn"]
        == "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    )
    assert result["AttachedPolicies"] == []
    assert result["DetachedPolicies"] == []

    # Verify the console output includes warning
    mock_console.print.assert_any_call(
        "[yellow]Warning: Could not retrieve full permission set details after update.[/yellow]"
    )
    mock_console.print.assert_any_call(
        "[yellow]The permission set was updated but the updated details could not be displayed.[/yellow]"
    )


# Validation and Error Handling Tests


def test_update_permission_set_no_parameters():
    """Test update_permission_set with no update parameters provided."""
    with pytest.raises(typer.Exit):
        update_permission_set(
            identifier="TestPermissionSet",
            description=None,
            session_duration=None,
            relay_state=None,
            add_managed_policy=None,
            remove_managed_policy=None,
            profile=None,
        )


@patch("src.awsideman.commands.permission_set.validate_permission_set_description")
def test_update_permission_set_invalid_description(mock_validate_description):
    """Test update_permission_set with invalid description validation."""
    # Mock description validation failure
    mock_validate_description.return_value = False

    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        update_permission_set(
            identifier="TestPermissionSet",
            description="x" * 701,  # Too long
            session_duration=None,
            relay_state=None,
            add_managed_policy=None,
            remove_managed_policy=None,
            profile=None,
        )

    # Verify validate_permission_set_description was called
    mock_validate_description.assert_called_with("x" * 701)


@patch("src.awsideman.commands.permission_set.validate_aws_managed_policy_arn")
def test_update_permission_set_invalid_add_policy_arn(mock_validate_policy_arn):
    """Test update_permission_set with invalid add policy ARN validation."""
    # Mock policy validation failure
    mock_validate_policy_arn.return_value = False

    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        update_permission_set(
            identifier="TestPermissionSet",
            description=None,
            session_duration=None,
            relay_state=None,
            add_managed_policy=["invalid-arn"],
            remove_managed_policy=None,
            profile=None,
        )

    # Verify validate_aws_managed_policy_arn was called
    mock_validate_policy_arn.assert_called_with("invalid-arn")


@patch("src.awsideman.commands.permission_set.validate_aws_managed_policy_arn")
def test_update_permission_set_invalid_remove_policy_arn(mock_validate_policy_arn):
    """Test update_permission_set with invalid remove policy ARN validation."""
    # Mock policy validation failure
    mock_validate_policy_arn.return_value = False

    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        update_permission_set(
            identifier="TestPermissionSet",
            description=None,
            session_duration=None,
            relay_state=None,
            add_managed_policy=None,
            remove_managed_policy=["invalid-arn"],
            profile=None,
        )

    # Verify validate_aws_managed_policy_arn was called
    mock_validate_policy_arn.assert_called_with("invalid-arn")


@patch("src.awsideman.commands.permission_set.validate_profile")
def test_update_permission_set_profile_validation_failure(mock_validate_profile):
    """Test update_permission_set with profile validation failure."""
    # Mock profile validation failure
    mock_validate_profile.side_effect = typer.Exit(1)

    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        update_permission_set(
            identifier="TestPermissionSet",
            description="Updated description",
            session_duration=None,
            relay_state=None,
            add_managed_policy=None,
            remove_managed_policy=None,
            profile="non-existent-profile",
        )

    # Verify validate_profile was called with the correct parameter
    mock_validate_profile.assert_called_with("non-existent-profile")


@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
def test_update_permission_set_sso_instance_validation_failure(
    mock_validate_sso_instance, mock_validate_profile
):
    """Test update_permission_set with SSO instance validation failure."""
    # Setup mocks
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.side_effect = typer.Exit(1)

    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        update_permission_set(
            identifier="TestPermissionSet",
            description="Updated description",
            session_duration=None,
            relay_state=None,
            add_managed_policy=None,
            remove_managed_policy=None,
            profile=None,
        )

    # Verify validate_sso_instance was called
    mock_validate_sso_instance.assert_called_with({"region": "us-east-1"})


# Error Handling Tests


@patch("src.awsideman.commands.permission_set.resolve_permission_set_identifier")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_update_permission_set_resource_not_found_exception(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_resolve_identifier,
    mock_aws_client,
):
    """Test update_permission_set with ResourceNotFoundException."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )
    mock_resolve_identifier.return_value = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    )

    # Mock the update_permission_set API error
    error_response = {
        "Error": {"Code": "ResourceNotFoundException", "Message": "Permission set not found"}
    }
    mock_sso_admin.update_permission_set.side_effect = ClientError(
        error_response, "UpdatePermissionSet"
    )

    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        update_permission_set(
            identifier="NonExistentPermissionSet",
            description="Updated description",
            session_duration=None,
            relay_state=None,
            add_managed_policy=None,
            remove_managed_policy=None,
            profile=None,
        )

    # Verify the function called the API correctly
    mock_sso_admin.update_permission_set.assert_called()

    # Verify the console output includes appropriate error message
    mock_console.print.assert_any_call(
        "[red]Error: Permission set 'NonExistentPermissionSet' not found.[/red]"
    )
    mock_console.print.assert_any_call(
        "[yellow]Check the permission set name or ARN and try again.[/yellow]"
    )
    mock_console.print.assert_any_call(
        "[yellow]Use 'awsideman permission-set list' to see all available permission sets.[/yellow]"
    )


@patch("src.awsideman.commands.permission_set.resolve_permission_set_identifier")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_update_permission_set_access_denied_exception(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_resolve_identifier,
    mock_aws_client,
):
    """Test update_permission_set with AccessDeniedException."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )
    mock_resolve_identifier.return_value = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    )

    # Mock the update_permission_set API error
    error_response = {
        "Error": {
            "Code": "AccessDeniedException",
            "Message": "User is not authorized to perform this action",
        }
    }
    mock_sso_admin.update_permission_set.side_effect = ClientError(
        error_response, "UpdatePermissionSet"
    )

    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        update_permission_set(
            identifier="TestPermissionSet",
            description="Updated description",
            session_duration=None,
            relay_state=None,
            add_managed_policy=None,
            remove_managed_policy=None,
            profile=None,
        )

    # Verify the function called the API correctly
    mock_sso_admin.update_permission_set.assert_called()

    # Verify the console output includes appropriate error message
    mock_console.print.assert_any_call(
        "[red]Error: AccessDeniedException - User is not authorized to perform this action[/red]"
    )
    mock_console.print.assert_any_call(
        "[yellow]This could be due to insufficient permissions or an issue with the AWS Identity Center service.[/yellow]"
    )


@patch("src.awsideman.commands.permission_set.resolve_permission_set_identifier")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_update_permission_set_validation_exception(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_resolve_identifier,
    mock_aws_client,
):
    """Test update_permission_set with ValidationException."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )
    mock_resolve_identifier.return_value = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    )

    # Mock the update_permission_set API error
    error_response = {
        "Error": {"Code": "ValidationException", "Message": "Invalid session duration format"}
    }
    mock_sso_admin.update_permission_set.side_effect = ClientError(
        error_response, "UpdatePermissionSet"
    )

    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        update_permission_set(
            identifier="TestPermissionSet",
            description=None,
            session_duration="InvalidFormat",
            relay_state=None,
            add_managed_policy=None,
            remove_managed_policy=None,
            profile=None,
        )

    # Verify the function called the API correctly
    mock_sso_admin.update_permission_set.assert_called()

    # Verify the console output includes appropriate error message
    mock_console.print.assert_any_call(
        "[red]Error: ValidationException - Invalid session duration format[/red]"
    )


@patch("src.awsideman.commands.permission_set.resolve_permission_set_identifier")
@patch("src.awsideman.commands.permission_set.validate_aws_managed_policy_arn")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_update_permission_set_policy_attachment_access_denied(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_validate_policy_arn,
    mock_resolve_identifier,
    mock_aws_client,
    sample_permission_set_response,
    sample_managed_policies_response,
):
    """Test update_permission_set with AccessDeniedException during policy attachment."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_policy_arn.return_value = True
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )
    mock_resolve_identifier.return_value = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    )

    # Mock the attach_managed_policy_to_permission_set API error
    error_response = {
        "Error": {
            "Code": "AccessDeniedException",
            "Message": "User is not authorized to attach policies",
        }
    }
    mock_sso_admin.attach_managed_policy_to_permission_set.side_effect = ClientError(
        error_response, "AttachManagedPolicyToPermissionSet"
    )

    # Mock the describe_permission_set API response
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response

    # Mock the list_managed_policies_in_permission_set API response
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = (
        sample_managed_policies_response
    )

    # Call the function with managed policy to add
    result = update_permission_set(
        identifier="TestPermissionSet",
        description=None,
        session_duration=None,
        relay_state=None,
        add_managed_policy=["arn:aws:iam::aws:policy/PowerUserAccess"],
        remove_managed_policy=None,
        profile=None,
    )

    # Verify attach_managed_policy_to_permission_set was called
    mock_sso_admin.attach_managed_policy_to_permission_set.assert_called()

    # Verify no policies were added to the result
    assert len(result["AttachedPolicies"]) == 0

    # Verify the console output includes warning for access denied
    mock_console.print.assert_any_call(
        "[yellow]Warning: Failed to attach policy arn:aws:iam::aws:policy/PowerUserAccess: AccessDeniedException - User is not authorized to attach policies[/yellow]"
    )
    mock_console.print.assert_any_call(
        "[yellow]The permission set was updated but not all policies were attached.[/yellow]"
    )


@patch("src.awsideman.commands.permission_set.resolve_permission_set_identifier")
@patch("src.awsideman.commands.permission_set.validate_aws_managed_policy_arn")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_update_permission_set_policy_detachment_access_denied(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_validate_policy_arn,
    mock_resolve_identifier,
    mock_aws_client,
    sample_permission_set_response,
    sample_managed_policies_response,
):
    """Test update_permission_set with AccessDeniedException during policy detachment."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_policy_arn.return_value = True
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )
    mock_resolve_identifier.return_value = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    )

    # Mock the detach_managed_policy_from_permission_set API error
    error_response = {
        "Error": {
            "Code": "AccessDeniedException",
            "Message": "User is not authorized to detach policies",
        }
    }
    mock_sso_admin.detach_managed_policy_from_permission_set.side_effect = ClientError(
        error_response, "DetachManagedPolicyFromPermissionSet"
    )

    # Mock the describe_permission_set API response
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response

    # Mock the list_managed_policies_in_permission_set API response
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = (
        sample_managed_policies_response
    )

    # Call the function with managed policy to remove
    result = update_permission_set(
        identifier="TestPermissionSet",
        description=None,
        session_duration=None,
        relay_state=None,
        add_managed_policy=None,
        remove_managed_policy=["arn:aws:iam::aws:policy/AdministratorAccess"],
        profile=None,
    )

    # Verify detach_managed_policy_from_permission_set was called
    mock_sso_admin.detach_managed_policy_from_permission_set.assert_called()

    # Verify no policies were removed from the result
    assert len(result["DetachedPolicies"]) == 0

    # Verify the console output includes warning for access denied
    mock_console.print.assert_any_call(
        "[yellow]Warning: Failed to detach policy arn:aws:iam::aws:policy/AdministratorAccess: AccessDeniedException - User is not authorized to detach policies[/yellow]"
    )
    mock_console.print.assert_any_call(
        "[yellow]The permission set was updated but not all policies were detached.[/yellow]"
    )


@patch("src.awsideman.commands.permission_set.resolve_permission_set_identifier")
@patch("src.awsideman.commands.permission_set.validate_aws_managed_policy_arn")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_update_permission_set_policy_attachment_invalid_policy_exception(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_validate_policy_arn,
    mock_resolve_identifier,
    mock_aws_client,
    sample_permission_set_response,
    sample_managed_policies_response,
):
    """Test update_permission_set with ValidationException for invalid policy during attachment."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_policy_arn.return_value = True
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )
    mock_resolve_identifier.return_value = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    )

    # Mock the attach_managed_policy_to_permission_set API error
    error_response = {
        "Error": {"Code": "ValidationException", "Message": "Invalid policy ARN format"}
    }
    mock_sso_admin.attach_managed_policy_to_permission_set.side_effect = ClientError(
        error_response, "AttachManagedPolicyToPermissionSet"
    )

    # Mock the describe_permission_set API response
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response

    # Mock the list_managed_policies_in_permission_set API response
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = (
        sample_managed_policies_response
    )

    # Call the function with managed policy to add
    result = update_permission_set(
        identifier="TestPermissionSet",
        description=None,
        session_duration=None,
        relay_state=None,
        add_managed_policy=["arn:aws:iam::aws:policy/InvalidPolicy"],
        remove_managed_policy=None,
        profile=None,
    )

    # Verify attach_managed_policy_to_permission_set was called
    mock_sso_admin.attach_managed_policy_to_permission_set.assert_called()

    # Verify no policies were added to the result
    assert len(result["AttachedPolicies"]) == 0

    # Verify the console output includes warning for validation error
    mock_console.print.assert_any_call(
        "[yellow]Warning: Failed to attach policy arn:aws:iam::aws:policy/InvalidPolicy: ValidationException - Invalid policy ARN format[/yellow]"
    )


@patch("src.awsideman.commands.permission_set.resolve_permission_set_identifier")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.handle_network_error")
@patch("src.awsideman.commands.permission_set.console")
def test_update_permission_set_network_error(
    mock_console,
    mock_handle_network_error,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_resolve_identifier,
    mock_aws_client,
):
    """Test update_permission_set with network connectivity error."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )
    mock_resolve_identifier.return_value = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    )

    # Mock the update_permission_set API network error
    mock_sso_admin.update_permission_set.side_effect = EndpointConnectionError(
        endpoint_url="https://sso.us-east-1.amazonaws.com"
    )

    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        update_permission_set(
            identifier="TestPermissionSet",
            description="Updated description",
            session_duration=None,
            relay_state=None,
            add_managed_policy=None,
            remove_managed_policy=None,
            profile=None,
        )

    # Verify the function called the API correctly (with retries)
    assert mock_sso_admin.update_permission_set.call_count >= 1

    # Verify handle_network_error was called
    mock_handle_network_error.assert_called()


@patch("src.awsideman.commands.permission_set.resolve_permission_set_identifier")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.handle_aws_error")
@patch("src.awsideman.commands.permission_set.console")
def test_update_permission_set_generic_client_error(
    mock_console,
    mock_handle_aws_error,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_resolve_identifier,
    mock_aws_client,
):
    """Test update_permission_set with generic AWS client error."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )
    mock_resolve_identifier.return_value = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    )

    # Mock the update_permission_set API error
    error_response = {"Error": {"Code": "InternalServerError", "Message": "Internal server error"}}
    mock_sso_admin.update_permission_set.side_effect = ClientError(
        error_response, "UpdatePermissionSet"
    )

    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        update_permission_set(
            identifier="TestPermissionSet",
            description="Updated description",
            session_duration=None,
            relay_state=None,
            add_managed_policy=None,
            remove_managed_policy=None,
            profile=None,
        )

    # Verify the function called the API correctly
    mock_sso_admin.update_permission_set.assert_called()

    # Verify the console output includes appropriate error message
    mock_console.print.assert_any_call(
        "[red]Error: InternalServerError - Internal server error[/red]"
    )
    mock_console.print.assert_any_call(
        "[yellow]This could be due to insufficient permissions or an issue with the AWS Identity Center service.[/yellow]"
    )


@patch("src.awsideman.commands.permission_set.resolve_permission_set_identifier")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_update_permission_set_unexpected_exception(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_resolve_identifier,
    mock_aws_client,
):
    """Test update_permission_set with unexpected exception."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = (
        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
        "d-1234567890",
    )
    mock_resolve_identifier.return_value = (
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    )

    # Mock the update_permission_set API unexpected error
    mock_sso_admin.update_permission_set.side_effect = ValueError("Unexpected error")

    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        update_permission_set(
            identifier="TestPermissionSet",
            description="Updated description",
            session_duration=None,
            relay_state=None,
            add_managed_policy=None,
            remove_managed_policy=None,
            profile=None,
        )

    # Verify the function called the API correctly
    mock_sso_admin.update_permission_set.assert_called()

    # Verify the console output includes appropriate error message
    mock_console.print.assert_any_call("[red]Error: Unexpected error[/red]")
    mock_console.print.assert_any_call(
        "[yellow]This is an unexpected error. Please report this issue if it persists.[/yellow]"
    )


@patch("src.awsideman.commands.permission_set.resolve_permission_set_identifier")
def test_update_permission_set_identifier_resolution_failure(mock_resolve_identifier):
    """Test update_permission_set with identifier resolution failure."""
    # Mock identifier resolution failure
    mock_resolve_identifier.side_effect = typer.Exit(1)

    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        update_permission_set(
            identifier="NonExistentPermissionSet",
            description="Updated description",
            session_duration=None,
            relay_state=None,
            add_managed_policy=None,
            remove_managed_policy=None,
            profile=None,
        )

    # Verify resolve_permission_set_identifier was called
    mock_resolve_identifier.assert_called()
