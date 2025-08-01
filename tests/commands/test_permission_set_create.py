"""Tests for permission set create command."""
import pytest
from unittest.mock import MagicMock, patch, call
from botocore.exceptions import ClientError, EndpointConnectionError
from requests.exceptions import ConnectionError
import typer
from typer.testing import CliRunner
from datetime import datetime

from src.awsideman.commands.permission_set import create_permission_set


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
            "LastModifiedDate": datetime(2023, 1, 2, 0, 0, 0)
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


@patch("src.awsideman.commands.permission_set.validate_permission_set_name")
@patch("src.awsideman.commands.permission_set.validate_permission_set_description")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_create_permission_set_successful_basic(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_validate_description,
    mock_validate_name,
    mock_aws_client,
    sample_create_response,
    sample_permission_set_response
):
    """Test successful create_permission_set operation with basic parameters."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_name.return_value = True
    mock_validate_description.return_value = True
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the create_permission_set API response
    mock_sso_admin.create_permission_set.return_value = sample_create_response
    
    # Mock the describe_permission_set API response
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response
    
    # Call the function directly with explicit parameters
    result = create_permission_set(
        name="TestPermissionSet",
        description="Test permission set description",
        session_duration="PT1H",
        relay_state=None,
        managed_policy=None,
        profile=None
    )
    
    # Verify input validation was called
    mock_validate_name.assert_called_once_with("TestPermissionSet")
    mock_validate_description.assert_called_once_with("Test permission set description")
    
    # Verify the function called the APIs correctly
    mock_sso_admin.create_permission_set.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        Name="TestPermissionSet",
        Description="Test permission set description",
        SessionDuration="PT1H"
    )
    
    # Verify describe_permission_set was called to get details
    mock_sso_admin.describe_permission_set.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        PermissionSetArn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    )
    
    # Verify the function returned the correct data
    assert result["PermissionSetArn"] == "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    assert result["Name"] == "TestPermissionSet"
    assert result["Description"] == "Test permission set description"
    assert result["SessionDuration"] == "PT1H"
    assert result["AttachedManagedPolicies"] == []
    
    # Verify the console output
    mock_console.print.assert_any_call("[blue]Creating permission set 'TestPermissionSet'...[/blue]")
    mock_console.print.assert_any_call("[green]Permission set 'TestPermissionSet' created successfully.[/green]")


@patch("src.awsideman.commands.permission_set.validate_permission_set_name")
@patch("src.awsideman.commands.permission_set.validate_permission_set_description")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_create_permission_set_successful_with_all_parameters(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_validate_description,
    mock_validate_name,
    mock_aws_client,
    sample_create_response,
    sample_permission_set_response
):
    """Test successful create_permission_set operation with all parameters."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_name.return_value = True
    mock_validate_description.return_value = True
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the create_permission_set API response
    mock_sso_admin.create_permission_set.return_value = sample_create_response
    
    # Mock the describe_permission_set API response
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response
    
    # Call the function with all parameters
    result = create_permission_set(
        name="TestPermissionSet",
        description="Test permission set description",
        session_duration="PT4H",
        relay_state="https://console.aws.amazon.com/",
        managed_policy=None,
        profile="test-profile"
    )
    
    # Verify input validation was called
    mock_validate_name.assert_called_once_with("TestPermissionSet")
    mock_validate_description.assert_called_once_with("Test permission set description")
    
    # Verify profile validation was called with the correct profile
    mock_validate_profile.assert_called_once_with("test-profile")
    
    # Verify the function called the APIs correctly
    mock_sso_admin.create_permission_set.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        Name="TestPermissionSet",
        Description="Test permission set description",
        SessionDuration="PT4H",
        RelayState="https://console.aws.amazon.com/"
    )
    
    # Verify the function returned the correct data
    assert result["PermissionSetArn"] == "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    assert result["Name"] == "TestPermissionSet"
    assert result["Description"] == "Test permission set description"
    assert result["SessionDuration"] == "PT4H"
    assert result["RelayState"] == "https://console.aws.amazon.com/"
    assert result["AttachedManagedPolicies"] == []


@patch("src.awsideman.commands.permission_set.validate_permission_set_name")
@patch("src.awsideman.commands.permission_set.validate_permission_set_description")
@patch("src.awsideman.commands.permission_set.validate_aws_managed_policy_arn")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_create_permission_set_with_managed_policies(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_validate_policy_arn,
    mock_validate_description,
    mock_validate_name,
    mock_aws_client,
    sample_create_response,
    sample_permission_set_response
):
    """Test successful create_permission_set operation with managed policies."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_name.return_value = True
    mock_validate_description.return_value = True
    mock_validate_policy_arn.return_value = True
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the create_permission_set API response
    mock_sso_admin.create_permission_set.return_value = sample_create_response
    
    # Mock the describe_permission_set API response
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response
    
    # Mock the attach_managed_policy_to_permission_set API response
    mock_sso_admin.attach_managed_policy_to_permission_set.return_value = {}
    
    # Call the function with managed policies
    managed_policies = [
        "arn:aws:iam::aws:policy/AdministratorAccess",
        "arn:aws:iam::aws:policy/ReadOnlyAccess"
    ]
    result = create_permission_set(
        name="TestPermissionSet",
        description="Test permission set description",
        session_duration="PT1H",
        relay_state=None,
        managed_policy=managed_policies,
        profile=None
    )
    
    # Verify input validation was called for each policy (twice - once in validation, once in attachment)
    assert mock_validate_policy_arn.call_count == 4
    mock_validate_policy_arn.assert_any_call("arn:aws:iam::aws:policy/AdministratorAccess")
    mock_validate_policy_arn.assert_any_call("arn:aws:iam::aws:policy/ReadOnlyAccess")
    
    # Verify the function called the APIs correctly
    mock_sso_admin.create_permission_set.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        Name="TestPermissionSet",
        Description="Test permission set description",
        SessionDuration="PT1H"
    )
    
    # Verify attach_managed_policy_to_permission_set was called for each policy
    assert mock_sso_admin.attach_managed_policy_to_permission_set.call_count == 2
    mock_sso_admin.attach_managed_policy_to_permission_set.assert_any_call(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        PermissionSetArn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        ManagedPolicyArn="arn:aws:iam::aws:policy/AdministratorAccess"
    )
    mock_sso_admin.attach_managed_policy_to_permission_set.assert_any_call(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        PermissionSetArn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        ManagedPolicyArn="arn:aws:iam::aws:policy/ReadOnlyAccess"
    )
    
    # Verify the function returned the correct data with attached policies
    assert result["AttachedManagedPolicies"] == [
        {"Name": "AdministratorAccess", "Arn": "arn:aws:iam::aws:policy/AdministratorAccess"},
        {"Name": "ReadOnlyAccess", "Arn": "arn:aws:iam::aws:policy/ReadOnlyAccess"}
    ]
    
    # Verify the console output
    mock_console.print.assert_any_call("[blue]Attaching 2 managed policies...[/blue]")
    mock_console.print.assert_any_call("[green]Attached policy: AdministratorAccess[/green]")
    mock_console.print.assert_any_call("[green]Attached policy: ReadOnlyAccess[/green]")


@patch("src.awsideman.commands.permission_set.validate_permission_set_name")
@patch("src.awsideman.commands.permission_set.validate_permission_set_description")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_create_permission_set_minimal_parameters(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_validate_description,
    mock_validate_name,
    mock_aws_client,
    sample_create_response,
    sample_permission_set_response
):
    """Test successful create_permission_set operation with minimal parameters."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_name.return_value = True
    mock_validate_description.return_value = True
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the create_permission_set API response
    mock_sso_admin.create_permission_set.return_value = sample_create_response
    
    # Mock the describe_permission_set API response
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response
    
    # Call the function with only required parameters
    result = create_permission_set(
        name="TestPermissionSet",
        description=None,
        session_duration="PT1H",
        relay_state=None,
        managed_policy=None,
        profile=None
    )
    
    # Verify input validation was called
    mock_validate_name.assert_called_once_with("TestPermissionSet")
    # Description validation is not called when description is None
    mock_validate_description.assert_not_called()
    
    # Verify the function called the APIs correctly with minimal parameters
    mock_sso_admin.create_permission_set.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        Name="TestPermissionSet",
        SessionDuration="PT1H"
    )
    
    # Verify the function returned the correct data
    assert result["Name"] == "TestPermissionSet"
    assert result["Description"] is None
    assert result["SessionDuration"] == "PT1H"
    assert result["RelayState"] is None
    assert result["AttachedManagedPolicies"] == []


@patch("src.awsideman.commands.permission_set.validate_permission_set_name")
@patch("src.awsideman.commands.permission_set.validate_permission_set_description")
@patch("src.awsideman.commands.permission_set.validate_aws_managed_policy_arn")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_create_permission_set_policy_attachment_partial_failure(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_validate_policy_arn,
    mock_validate_description,
    mock_validate_name,
    mock_aws_client,
    sample_create_response,
    sample_permission_set_response
):
    """Test create_permission_set with partial policy attachment failure."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_name.return_value = True
    mock_validate_description.return_value = True
    mock_validate_policy_arn.return_value = True
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the create_permission_set API response
    mock_sso_admin.create_permission_set.return_value = sample_create_response
    
    # Mock the describe_permission_set API response
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response
    
    # Mock the attach_managed_policy_to_permission_set API response with one failure
    error_response = {
        "Error": {
            "Code": "ResourceNotFoundException",
            "Message": "Policy not found"
        }
    }
    mock_sso_admin.attach_managed_policy_to_permission_set.side_effect = [
        {},  # First policy succeeds
        ClientError(error_response, "AttachManagedPolicyToPermissionSet")  # Second policy fails
    ]
    
    # Call the function with managed policies
    managed_policies = [
        "arn:aws:iam::aws:policy/AdministratorAccess",
        "arn:aws:iam::aws:policy/NonExistentPolicy"
    ]
    result = create_permission_set(
        name="TestPermissionSet",
        description=None,
        session_duration="PT1H",
        relay_state=None,
        managed_policy=managed_policies,
        profile=None
    )
    
    # Verify the function called the APIs correctly
    mock_sso_admin.create_permission_set.assert_called_once()
    
    # Verify attach_managed_policy_to_permission_set was called for each policy
    assert mock_sso_admin.attach_managed_policy_to_permission_set.call_count == 2
    
    # Verify only the successful policy is in the result
    assert len(result["AttachedManagedPolicies"]) == 1
    assert result["AttachedManagedPolicies"][0]["Name"] == "AdministratorAccess"
    
    # Verify the console output includes warning for failed policy
    mock_console.print.assert_any_call("[green]Attached policy: AdministratorAccess[/green]")
    mock_console.print.assert_any_call(
        "[yellow]Warning: Failed to attach policy arn:aws:iam::aws:policy/NonExistentPolicy: ResourceNotFoundException - Policy not found[/yellow]"
    )
    mock_console.print.assert_any_call(
        "[yellow]The permission set was created but not all policies were attached.[/yellow]"
    )


@patch("src.awsideman.commands.permission_set.validate_permission_set_name")
@patch("src.awsideman.commands.permission_set.validate_permission_set_description")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_create_permission_set_describe_failure_after_creation(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_validate_description,
    mock_validate_name,
    mock_aws_client,
    sample_create_response
):
    """Test create_permission_set when describe fails after creation."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_name.return_value = True
    mock_validate_description.return_value = True
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the create_permission_set API response
    mock_sso_admin.create_permission_set.return_value = sample_create_response
    
    # Mock the describe_permission_set API error
    error_response = {
        "Error": {
            "Code": "AccessDeniedException",
            "Message": "User is not authorized to perform this action"
        }
    }
    mock_sso_admin.describe_permission_set.side_effect = ClientError(error_response, "DescribePermissionSet")
    
    # Call the function
    result = create_permission_set(
        name="TestPermissionSet",
        description=None,
        session_duration="PT1H",
        relay_state=None,
        managed_policy=None,
        profile=None
    )
    
    # Verify the function called the APIs correctly
    mock_sso_admin.create_permission_set.assert_called_once()
    mock_sso_admin.describe_permission_set.assert_called_once()
    
    # Verify the function still returns the basic data
    assert result["PermissionSetArn"] == "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
    assert result["Name"] == "TestPermissionSet"
    
    # Verify the console output includes warning
    mock_console.print.assert_any_call(
        "[yellow]Warning: Could not retrieve full permission set details after creation.[/yellow]"
    )


@patch("src.awsideman.commands.permission_set.validate_permission_set_name")
@patch("src.awsideman.commands.permission_set.validate_permission_set_description")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_create_permission_set_no_arn_in_response(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_validate_description,
    mock_validate_name,
    mock_aws_client
):
    """Test create_permission_set when no ARN is returned in response."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_name.return_value = True
    mock_validate_description.return_value = True
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the create_permission_set API response without ARN
    mock_sso_admin.create_permission_set.return_value = {"PermissionSet": {}}
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        create_permission_set(
            name="TestPermissionSet",
            description=None,
            session_duration="PT1H",
            relay_state=None,
            managed_policy=None,
            profile=None
        )
    
    # Verify the function called the API correctly
    mock_sso_admin.create_permission_set.assert_called_once()
    
    # Verify the console output includes error
    mock_console.print.assert_any_call(
        "[red]Error: Failed to create permission set. No ARN returned.[/red]"
    )


@patch("src.awsideman.commands.permission_set.validate_permission_set_name")
@patch("src.awsideman.commands.permission_set.validate_permission_set_description")
@patch("src.awsideman.commands.permission_set.validate_aws_managed_policy_arn")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_create_permission_set_skip_invalid_policy(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_validate_policy_arn,
    mock_validate_description,
    mock_validate_name,
    mock_aws_client,
    sample_create_response,
    sample_permission_set_response
):
    """Test create_permission_set skips invalid policy ARNs."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_name.return_value = True
    mock_validate_description.return_value = True
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock policy validation - pass initial validation, then fail during attachment
    mock_validate_policy_arn.side_effect = [True, True, True, False]  # 2 for initial validation, 2 for attachment
    
    # Mock the create_permission_set API response
    mock_sso_admin.create_permission_set.return_value = sample_create_response
    
    # Mock the describe_permission_set API response
    mock_sso_admin.describe_permission_set.return_value = sample_permission_set_response
    
    # Mock the attach_managed_policy_to_permission_set API response
    mock_sso_admin.attach_managed_policy_to_permission_set.return_value = {}
    
    # Call the function with one valid and one invalid policy
    managed_policies = [
        "arn:aws:iam::aws:policy/AdministratorAccess",
        "invalid-policy-arn"
    ]
    result = create_permission_set(
        name="TestPermissionSet",
        description=None,
        session_duration="PT1H",
        relay_state=None,
        managed_policy=managed_policies,
        profile=None
    )
    
    # Verify policy validation was called for both policies (twice each - validation and attachment)
    assert mock_validate_policy_arn.call_count == 4
    
    # Verify attach_managed_policy_to_permission_set was called only once (for valid policy)
    mock_sso_admin.attach_managed_policy_to_permission_set.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        PermissionSetArn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        ManagedPolicyArn="arn:aws:iam::aws:policy/AdministratorAccess"
    )
    
    # Verify only the valid policy is in the result
    assert len(result["AttachedManagedPolicies"]) == 1
    assert result["AttachedManagedPolicies"][0]["Name"] == "AdministratorAccess"
    
    # Verify the console output includes warning for invalid policy
    mock_console.print.assert_any_call("[yellow]Skipping invalid policy ARN: invalid-policy-arn[/yellow]")


# Validation and Error Handling Tests

@patch("src.awsideman.commands.permission_set.validate_permission_set_name")
def test_create_permission_set_invalid_name(mock_validate_name):
    """Test create_permission_set with invalid name validation."""
    # Mock name validation failure
    mock_validate_name.return_value = False
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        create_permission_set(
            name="",
            description=None,
            session_duration="PT1H",
            relay_state=None,
            managed_policy=None,
            profile=None
        )
    
    # Verify validate_permission_set_name was called
    mock_validate_name.assert_called_once_with("")


@patch("src.awsideman.commands.permission_set.validate_permission_set_name")
@patch("src.awsideman.commands.permission_set.validate_permission_set_description")
def test_create_permission_set_invalid_description(mock_validate_description, mock_validate_name):
    """Test create_permission_set with invalid description validation."""
    # Setup mocks
    mock_validate_name.return_value = True
    mock_validate_description.return_value = False
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        create_permission_set(
            name="TestPermissionSet",
            description="x" * 701,  # Too long
            session_duration="PT1H",
            relay_state=None,
            managed_policy=None,
            profile=None
        )
    
    # Verify validation was called
    mock_validate_name.assert_called_once_with("TestPermissionSet")
    mock_validate_description.assert_called_once_with("x" * 701)


@patch("src.awsideman.commands.permission_set.validate_permission_set_name")
@patch("src.awsideman.commands.permission_set.validate_permission_set_description")
@patch("src.awsideman.commands.permission_set.validate_aws_managed_policy_arn")
def test_create_permission_set_invalid_policy_arn(
    mock_validate_policy_arn,
    mock_validate_description,
    mock_validate_name
):
    """Test create_permission_set with invalid policy ARN validation."""
    # Setup mocks
    mock_validate_name.return_value = True
    mock_validate_description.return_value = True
    mock_validate_policy_arn.return_value = False
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        create_permission_set(
            name="TestPermissionSet",
            description=None,
            session_duration="PT1H",
            relay_state=None,
            managed_policy=["invalid-arn"],
            profile=None
        )
    
    # Verify validation was called
    mock_validate_name.assert_called_once_with("TestPermissionSet")
    # Description validation is not called when description is None
    mock_validate_description.assert_not_called()
    mock_validate_policy_arn.assert_called_once_with("invalid-arn")


@patch("src.awsideman.commands.permission_set.validate_permission_set_name")
@patch("src.awsideman.commands.permission_set.validate_permission_set_description")
@patch("src.awsideman.commands.permission_set.validate_profile")
def test_create_permission_set_profile_validation_failure(
    mock_validate_profile,
    mock_validate_description,
    mock_validate_name
):
    """Test create_permission_set with profile validation failure."""
    # Setup mocks
    mock_validate_name.return_value = True
    mock_validate_description.return_value = True
    mock_validate_profile.side_effect = typer.Exit(1)
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        create_permission_set(
            name="TestPermissionSet",
            description=None,
            session_duration="PT1H",
            relay_state=None,
            managed_policy=None,
            profile="non-existent-profile"
        )
    
    # Verify validate_profile was called with the correct parameter
    mock_validate_profile.assert_called_once_with("non-existent-profile")


@patch("src.awsideman.commands.permission_set.validate_permission_set_name")
@patch("src.awsideman.commands.permission_set.validate_permission_set_description")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
def test_create_permission_set_sso_instance_validation_failure(
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_validate_description,
    mock_validate_name
):
    """Test create_permission_set with SSO instance validation failure."""
    # Setup mocks
    mock_validate_name.return_value = True
    mock_validate_description.return_value = True
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.side_effect = typer.Exit(1)
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        create_permission_set(
            name="TestPermissionSet",
            description=None,
            session_duration="PT1H",
            relay_state=None,
            managed_policy=None,
            profile=None
        )
    
    # Verify validate_sso_instance was called with the correct parameter
    mock_validate_sso_instance.assert_called_once_with({"region": "us-east-1"})


@patch("src.awsideman.commands.permission_set.validate_permission_set_name")
@patch("src.awsideman.commands.permission_set.validate_permission_set_description")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_create_permission_set_duplicate_name_error(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_validate_description,
    mock_validate_name,
    mock_aws_client
):
    """Test create_permission_set with duplicate name (ConflictException)."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_name.return_value = True
    mock_validate_description.return_value = True
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the create_permission_set API error for duplicate name
    error_response = {
        "Error": {
            "Code": "ConflictException",
            "Message": "Permission set with this name already exists"
        }
    }
    mock_sso_admin.create_permission_set.side_effect = ClientError(error_response, "CreatePermissionSet")
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        create_permission_set(
            name="ExistingPermissionSet",
            description=None,
            session_duration="PT1H",
            relay_state=None,
            managed_policy=None,
            profile=None
        )
    
    # Verify the function called the API correctly
    mock_sso_admin.create_permission_set.assert_called_once()
    
    # Verify the console output includes specific error message for duplicate name
    mock_console.print.assert_any_call("[red]Error: Permission set 'ExistingPermissionSet' already exists.[/red]")
    mock_console.print.assert_any_call(
        "[yellow]Use a different name or use 'awsideman permission-set update' to modify an existing permission set.[/yellow]"
    )


@patch("src.awsideman.commands.permission_set.validate_permission_set_name")
@patch("src.awsideman.commands.permission_set.validate_permission_set_description")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_create_permission_set_api_error(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_validate_description,
    mock_validate_name,
    mock_aws_client
):
    """Test create_permission_set with general API error."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_name.return_value = True
    mock_validate_description.return_value = True
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the create_permission_set API error
    error_response = {
        "Error": {
            "Code": "AccessDeniedException",
            "Message": "User is not authorized to perform this action"
        }
    }
    mock_sso_admin.create_permission_set.side_effect = ClientError(error_response, "CreatePermissionSet")
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        create_permission_set(
            name="TestPermissionSet",
            description=None,
            session_duration="PT1H",
            relay_state=None,
            managed_policy=None,
            profile=None
        )
    
    # Verify the function called the API correctly
    mock_sso_admin.create_permission_set.assert_called_once()
    
    # Verify the console output includes general error message
    mock_console.print.assert_any_call(
        "[red]Error: AccessDeniedException - User is not authorized to perform this action[/red]"
    )


@patch("src.awsideman.commands.permission_set.validate_permission_set_name")
@patch("src.awsideman.commands.permission_set.validate_permission_set_description")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_create_permission_set_network_error(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_validate_description,
    mock_validate_name,
    mock_aws_client
):
    """Test create_permission_set with network error."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_name.return_value = True
    mock_validate_description.return_value = True
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the create_permission_set API with network error
    mock_sso_admin.create_permission_set.side_effect = ConnectionError("Network error")
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        create_permission_set(
            name="TestPermissionSet",
            description=None,
            session_duration="PT1H",
            relay_state=None,
            managed_policy=None,
            profile=None
        )
    
    # Verify the function called the API correctly
    mock_sso_admin.create_permission_set.assert_called_once()


@patch("src.awsideman.commands.permission_set.validate_permission_set_name")
@patch("src.awsideman.commands.permission_set.validate_permission_set_description")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_create_permission_set_unexpected_error(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_validate_description,
    mock_validate_name,
    mock_aws_client
):
    """Test create_permission_set with unexpected error."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_name.return_value = True
    mock_validate_description.return_value = True
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the create_permission_set API with unexpected error
    mock_sso_admin.create_permission_set.side_effect = Exception("Unexpected error")
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        create_permission_set(
            name="TestPermissionSet",
            description=None,
            session_duration="PT1H",
            relay_state=None,
            managed_policy=None,
            profile=None
        )
    
    # Verify the function called the API correctly
    mock_sso_admin.create_permission_set.assert_called_once()
    
    # Verify the console output includes unexpected error message
    mock_console.print.assert_any_call("[red]Error: Unexpected error[/red]")
    mock_console.print.assert_any_call(
        "[yellow]This is an unexpected error. Please report this issue if it persists.[/yellow]"
    )


@patch("src.awsideman.commands.permission_set.validate_permission_set_name")
@patch("src.awsideman.commands.permission_set.validate_permission_set_description")
@patch("src.awsideman.commands.permission_set.validate_aws_managed_policy_arn")
def test_create_permission_set_multiple_invalid_policies(
    mock_validate_policy_arn,
    mock_validate_description,
    mock_validate_name
):
    """Test create_permission_set with multiple invalid policy ARNs."""
    # Setup mocks
    mock_validate_name.return_value = True
    mock_validate_description.return_value = True
    # First policy is invalid, should exit immediately
    mock_validate_policy_arn.return_value = False
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        create_permission_set(
            name="TestPermissionSet",
            description=None,
            session_duration="PT1H",
            relay_state=None,
            managed_policy=["invalid-arn-1", "invalid-arn-2"],
            profile=None
        )
    
    # Verify validation was called only for the first policy (exits on first failure)
    mock_validate_policy_arn.assert_called_once_with("invalid-arn-1")


@patch("src.awsideman.commands.permission_set.validate_permission_set_name")
@patch("src.awsideman.commands.permission_set.validate_permission_set_description")
@patch("src.awsideman.commands.permission_set.validate_aws_managed_policy_arn")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_create_permission_set_mixed_policy_validation(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_validate_policy_arn,
    mock_validate_description,
    mock_validate_name,
    mock_aws_client,
    sample_create_response,
    sample_permission_set_response
):
    """Test create_permission_set with mixed valid and invalid policies during validation."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_name.return_value = True
    mock_validate_description.return_value = True
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock policy validation - first valid, second invalid (should exit on second)
    mock_validate_policy_arn.side_effect = [True, False]
    
    # Call the function and expect exception on second invalid policy
    with pytest.raises(typer.Exit):
        create_permission_set(
            name="TestPermissionSet",
            description=None,
            session_duration="PT1H",
            relay_state=None,
            managed_policy=[
                "arn:aws:iam::aws:policy/AdministratorAccess",
                "invalid-arn"
            ],
            profile=None
        )
    
    # Verify validation was called for both policies
    assert mock_validate_policy_arn.call_count == 2
    mock_validate_policy_arn.assert_any_call("arn:aws:iam::aws:policy/AdministratorAccess")
    mock_validate_policy_arn.assert_any_call("invalid-arn")
    
    # Verify create_permission_set was not called due to validation failure
    mock_sso_admin.create_permission_set.assert_not_called()


@patch("src.awsideman.commands.permission_set.validate_permission_set_name")
@patch("src.awsideman.commands.permission_set.validate_permission_set_description")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_create_permission_set_empty_name_validation(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_validate_description,
    mock_validate_name
):
    """Test create_permission_set with empty name validation."""
    # Mock name validation failure for empty name
    mock_validate_name.return_value = False
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        create_permission_set(name="")
    
    # Verify validate_permission_set_name was called with empty string
    mock_validate_name.assert_called_once_with("")
    
    # Verify other validations were not called
    mock_validate_description.assert_not_called()
    mock_validate_profile.assert_not_called()
    mock_validate_sso_instance.assert_not_called()
    mock_aws_client_manager.assert_not_called()


@patch("src.awsideman.commands.permission_set.validate_permission_set_name")
@patch("src.awsideman.commands.permission_set.validate_permission_set_description")
@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_create_permission_set_long_name_validation(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_validate_description,
    mock_validate_name
):
    """Test create_permission_set with name too long validation."""
    # Mock name validation failure for long name
    mock_validate_name.return_value = False
    
    long_name = "a" * 33  # Exceeds 32 character limit
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        create_permission_set(
            name=long_name,
            description=None,
            session_duration="PT1H",
            relay_state=None,
            managed_policy=None,
            profile=None
        )
    
    # Verify validate_permission_set_name was called with long name
    mock_validate_name.assert_called_once_with(long_name)
    
    # Verify other validations were not called
    mock_validate_description.assert_not_called()
    mock_validate_profile.assert_not_called()
    mock_validate_sso_instance.assert_not_called()
    mock_aws_client_manager.assert_not_called()