"""Tests for permission set list command."""
import pytest
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError, ConnectionError
import typer
from datetime import datetime

from src.awsideman.commands.permission_set import _list_permission_sets_internal as list_permission_sets


@pytest.fixture
def mock_aws_client():
    """Create a mock AWS client."""
    mock = MagicMock()
    # Mock SSO Admin client
    mock_sso_admin = MagicMock()
    mock.get_client.return_value = mock_sso_admin
    return mock, mock_sso_admin


@pytest.fixture
def sample_permission_sets():
    """Sample permission set ARNs for testing."""
    return [
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-abcdef1234567890"
    ]


@pytest.fixture
def sample_permission_set_details():
    """Sample permission set details for testing."""
    return [
        {
            "Name": "AdminAccess",
            "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            "Description": "Provides admin access to AWS resources",
            "SessionDuration": "PT8H",
            "RelayState": "https://console.aws.amazon.com/",
            "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
            "LastModifiedDate": datetime(2023, 1, 2, 0, 0, 0)
        },
        {
            "Name": "ReadOnlyAccess",
            "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-abcdef1234567890",
            "Description": "Provides read-only access to AWS resources",
            "SessionDuration": "PT4H",
            "RelayState": "",
            "CreatedDate": datetime(2023, 1, 3, 0, 0, 0),
            "LastModifiedDate": datetime(2023, 1, 4, 0, 0, 0)
        }
    ]


@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
@patch("src.awsideman.commands.permission_set.get_single_key")
def test_list_permission_sets_successful(
    mock_get_single_key,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_permission_sets,
    sample_permission_set_details
):
    """Test successful list_permission_sets operation."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the list_permission_sets API response
    mock_sso_admin.list_permission_sets.return_value = {
        "PermissionSets": sample_permission_sets,
        "NextToken": None
    }
    
    # Mock the describe_permission_set API responses
    mock_sso_admin.describe_permission_set.side_effect = [
        {"PermissionSet": sample_permission_set_details[0]},
        {"PermissionSet": sample_permission_set_details[1]}
    ]
    
    # Call the function
    result, next_token = list_permission_sets()
    
    # Verify the function called the APIs correctly
    mock_sso_admin.list_permission_sets.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef"
    )
    
    # Verify describe_permission_set was called for each permission set
    assert mock_sso_admin.describe_permission_set.call_count == 2
    mock_sso_admin.describe_permission_set.assert_any_call(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        PermissionSetArn=sample_permission_sets[0]
    )
    mock_sso_admin.describe_permission_set.assert_any_call(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        PermissionSetArn=sample_permission_sets[1]
    )
    
    # Verify the function returned the correct data
    assert len(result) == 2
    assert result[0]["Name"] == "AdminAccess"
    assert result[1]["Name"] == "ReadOnlyAccess"
    assert next_token is None
    
    # Verify the console output
    mock_console.print.assert_any_call("[green]Found 2 permission sets.[/green]")


@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
@patch("src.awsideman.commands.permission_set.get_single_key")
def test_list_permission_sets_with_filter(
    mock_get_single_key,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_permission_sets,
    sample_permission_set_details
):
    """Test list_permission_sets with filter."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the list_permission_sets API response
    mock_sso_admin.list_permission_sets.return_value = {
        "PermissionSets": sample_permission_sets,
        "NextToken": None
    }
    
    # Mock the describe_permission_set API responses
    mock_sso_admin.describe_permission_set.side_effect = [
        {"PermissionSet": sample_permission_set_details[0]},
        {"PermissionSet": sample_permission_set_details[1]}
    ]
    
    # Call the function with filter
    result, next_token = list_permission_sets(filter="name=Admin")
    
    # Verify the function called the APIs correctly
    mock_sso_admin.list_permission_sets.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef"
    )
    
    # Verify describe_permission_set was called for each permission set
    assert mock_sso_admin.describe_permission_set.call_count == 2
    
    # Verify the function returned the filtered data (only AdminAccess)
    assert len(result) == 1
    assert result[0]["Name"] == "AdminAccess"
    assert next_token is None
    
    # Verify the console output for filtering
    mock_console.print.assert_any_call("[green]Found 2 permission sets.[/green]")
    mock_console.print.assert_any_call("[green]Filtered to 1 permission sets matching 'name=Admin'.[/green]")


@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
@patch("src.awsideman.commands.permission_set.get_single_key")
def test_list_permission_sets_with_pagination(
    mock_get_single_key,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_permission_sets,
    sample_permission_set_details
):
    """Test list_permission_sets with pagination."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the list_permission_sets API response with pagination
    mock_sso_admin.list_permission_sets.return_value = {
        "PermissionSets": [sample_permission_sets[0]],
        "NextToken": "next-page-token"
    }
    
    # Mock the describe_permission_set API response
    mock_sso_admin.describe_permission_set.return_value = {
        "PermissionSet": sample_permission_set_details[0]
    }
    
    # Mock user pressing a key other than Enter to stop pagination
    mock_get_single_key.return_value = "q"
    
    # Call the function
    result, next_token = list_permission_sets()
    
    # Verify the function called the APIs correctly
    mock_sso_admin.list_permission_sets.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef"
    )
    
    # Verify describe_permission_set was called for the permission set
    mock_sso_admin.describe_permission_set.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        PermissionSetArn=sample_permission_sets[0]
    )
    
    # Verify the function returned the correct data
    assert len(result) == 1
    assert result[0]["Name"] == "AdminAccess"
    assert next_token == "next-page-token"
    
    # Verify the console output for pagination
    mock_console.print.assert_any_call("[green]Found 1 permission sets (more results available).[/green]")
    mock_console.print.assert_any_call("\n[blue]Press ENTER to see the next page, or any other key to exit...[/blue]")
    mock_console.print.assert_any_call("\n[yellow]Pagination stopped.[/yellow]")


@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
@patch("src.awsideman.commands.permission_set.get_single_key")
def test_list_permission_sets_with_next_token(
    mock_get_single_key,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_permission_sets,
    sample_permission_set_details
):
    """Test list_permission_sets with next_token parameter."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the list_permission_sets API response
    mock_sso_admin.list_permission_sets.return_value = {
        "PermissionSets": [sample_permission_sets[1]],
        "NextToken": None
    }
    
    # Mock the describe_permission_set API response
    mock_sso_admin.describe_permission_set.return_value = {
        "PermissionSet": sample_permission_set_details[1]
    }
    
    # Call the function with next_token
    result, next_token = list_permission_sets(next_token="provided-token")
    
    # Verify the function called the APIs correctly
    mock_sso_admin.list_permission_sets.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        NextToken="provided-token"
    )
    
    # Verify describe_permission_set was called for the permission set
    mock_sso_admin.describe_permission_set.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        PermissionSetArn=sample_permission_sets[1]
    )
    
    # Verify the function returned the correct data
    assert len(result) == 1
    assert result[0]["Name"] == "ReadOnlyAccess"
    assert next_token is None


@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_list_permission_sets_with_limit(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_permission_sets,
    sample_permission_set_details
):
    """Test list_permission_sets with limit."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the list_permission_sets API response
    mock_sso_admin.list_permission_sets.return_value = {
        "PermissionSets": [sample_permission_sets[0]],
        "NextToken": None
    }
    
    # Mock the describe_permission_set API response
    mock_sso_admin.describe_permission_set.return_value = {
        "PermissionSet": sample_permission_set_details[0]
    }
    
    # Call the function with limit
    result, next_token = list_permission_sets(limit=1)
    
    # Verify the function called the APIs correctly
    mock_sso_admin.list_permission_sets.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        MaxResults=1
    )
    
    # Verify describe_permission_set was called for the permission set
    mock_sso_admin.describe_permission_set.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        PermissionSetArn=sample_permission_sets[0]
    )
    
    # Verify the function returned the correct data
    assert len(result) == 1
    assert result[0]["Name"] == "AdminAccess"
    assert next_token is None
    
    # Verify the console output
    mock_console.print.assert_any_call("[green]Found 1 permission sets (showing up to 1 results).[/green]")


@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_list_permission_sets_empty_result(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client
):
    """Test list_permission_sets with empty result."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the list_permission_sets API response with empty result
    mock_sso_admin.list_permission_sets.return_value = {
        "PermissionSets": [],
        "NextToken": None
    }
    
    # Call the function
    result, next_token = list_permission_sets()
    
    # Verify the function called the API correctly
    mock_sso_admin.list_permission_sets.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef"
    )
    
    # Verify the function returned the correct data
    assert result == []
    assert next_token is None
    
    # Verify the console output
    mock_console.print.assert_any_call("[yellow]No permission sets found.[/yellow]")


@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_list_permission_sets_invalid_filter_format(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client
):
    """Test list_permission_sets with invalid filter format."""
    # Setup mocks
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Call the function with invalid filter format
    with pytest.raises(typer.Exit):
        list_permission_sets(filter="invalid-filter")
    
    # Verify the console output
    mock_console.print.assert_any_call("[red]Error: Filter must be in the format 'attribute=value'[/red]")


@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_list_permission_sets_api_error(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client
):
    """Test list_permission_sets with API error."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the list_permission_sets API error
    error_response = {
        "Error": {
            "Code": "AccessDeniedException",
            "Message": "User is not authorized to perform this action"
        }
    }
    mock_sso_admin.list_permission_sets.side_effect = ClientError(error_response, "ListPermissionSets")
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        list_permission_sets()
    
    # Verify the function called the API correctly
    mock_sso_admin.list_permission_sets.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef"
    )

@pat
ch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_list_permission_sets_profile_validation_failure(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile
):
    """Test list_permission_sets with profile validation failure."""
    # Mock profile validation failure
    mock_validate_profile.side_effect = typer.Exit(1)
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        list_permission_sets(profile="non-existent-profile")
    
    # Verify validate_profile was called with the correct parameter
    mock_validate_profile.assert_called_once_with("non-existent-profile")
    
    # Verify validate_sso_instance was not called
    mock_validate_sso_instance.assert_not_called()


@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_list_permission_sets_sso_instance_validation_failure(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile
):
    """Test list_permission_sets with SSO instance validation failure."""
    # Setup mocks
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    
    # Mock SSO instance validation failure
    mock_validate_sso_instance.side_effect = typer.Exit(1)
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        list_permission_sets()
    
    # Verify validate_profile was called
    mock_validate_profile.assert_called_once()
    
    # Verify validate_sso_instance was called with the correct parameter
    mock_validate_sso_instance.assert_called_once_with({"region": "us-east-1"})


@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_list_permission_sets_permission_set_details_error(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_permission_sets
):
    """Test list_permission_sets with error retrieving permission set details."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the list_permission_sets API response
    mock_sso_admin.list_permission_sets.return_value = {
        "PermissionSets": sample_permission_sets,
        "NextToken": None
    }
    
    # Mock the describe_permission_set API error for one permission set
    error_response = {
        "Error": {
            "Code": "AccessDeniedException",
            "Message": "User is not authorized to perform this action"
        }
    }
    mock_sso_admin.describe_permission_set.side_effect = ClientError(error_response, "DescribePermissionSet")
    
    # Call the function
    result, next_token = list_permission_sets()
    
    # Verify the function called the APIs correctly
    mock_sso_admin.list_permission_sets.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef"
    )
    
    # Verify describe_permission_set was called for the first permission set
    mock_sso_admin.describe_permission_set.assert_called_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        PermissionSetArn=sample_permission_sets[0]
    )
    
    # Verify the console output includes a warning
    mock_console.print.assert_any_call(
        f"[yellow]Warning: Could not retrieve details for permission set {sample_permission_sets[0]}: AccessDeniedException - User is not authorized to perform this action[/yellow]"
    )


@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
def test_list_permission_sets_network_error(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client
):
    """Test list_permission_sets with network error."""
    # Setup mocks
    mock_client, mock_sso_admin = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
    
    # Mock the list_permission_sets API with network error
    mock_sso_admin.list_permission_sets.side_effect = ConnectionError("Failed to connect to AWS")
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        list_permission_sets()
    
    # Verify the function called the API correctly
    mock_sso_admin.list_permission_sets.assert_called_once_with(
        InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef"
    )
    
    # Verify the console output includes a network error message
    mock_console.print.assert_any_call("[red]Network Error: Failed to connect to AWS[/red]")


@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
@patch("src.awsideman.commands.permission_set.validate_filter")
def test_list_permission_sets_invalid_filter_validation(
    mock_validate_filter,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile
):
    """Test list_permission_sets with invalid filter validation."""
    # Mock filter validation failure
    mock_validate_filter.return_value = False
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        list_permission_sets(filter="invalid=filter")
    
    # Verify validate_filter was called with the correct parameter
    mock_validate_filter.assert_called_once_with("invalid=filter")


@patch("src.awsideman.commands.permission_set.validate_profile")
@patch("src.awsideman.commands.permission_set.validate_sso_instance")
@patch("src.awsideman.commands.permission_set.AWSClientManager")
@patch("src.awsideman.commands.permission_set.console")
@patch("src.awsideman.commands.permission_set.validate_limit")
def test_list_permission_sets_invalid_limit_validation(
    mock_validate_limit,
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile
):
    """Test list_permission_sets with invalid limit validation."""
    # Mock limit validation failure
    mock_validate_limit.return_value = False
    
    # Call the function and expect exception
    with pytest.raises(typer.Exit):
        list_permission_sets(limit=-1)
    
    # Verify validate_limit was called with the correct parameter
    mock_validate_limit.assert_called_once_with(-1)