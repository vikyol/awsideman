"""Tests for assignment helper functions."""

from unittest.mock import MagicMock, patch

import pytest
import typer
from botocore.exceptions import ClientError

from src.awsideman.commands.assignment import resolve_permission_set_info, resolve_principal_info


@pytest.fixture
def mock_sso_admin_client():
    """Create a mock SSO admin client."""
    return MagicMock()


@pytest.fixture
def mock_identity_store_client():
    """Create a mock identity store client."""
    return MagicMock()


@pytest.fixture
def sample_permission_set_response():
    """Sample permission set response for testing."""
    return {
        "PermissionSet": {
            "Name": "AdminAccess",
            "Description": "Full administrative access",
            "SessionDuration": "PT8H",
        }
    }


@pytest.fixture
def sample_user_response():
    """Sample user response for testing."""
    return {
        "UserName": "john.doe",
        "DisplayName": "John Doe",
        "Name": {"GivenName": "John", "FamilyName": "Doe"},
    }


@pytest.fixture
def sample_group_response():
    """Sample group response for testing."""
    return {"DisplayName": "Administrators"}


class TestResolvePermissionSetInfo:
    """Tests for resolve_permission_set_info function."""

    @patch("src.awsideman.commands.assignment.helpers.console")
    def test_resolve_permission_set_info_successful(
        self, mock_console, mock_sso_admin_client, sample_permission_set_response
    ):
        """Test successful resolve_permission_set_info operation."""
        # Setup mocks
        mock_sso_admin_client.describe_permission_set.return_value = sample_permission_set_response

        # Call the function
        result = resolve_permission_set_info(
            instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            sso_admin_client=mock_sso_admin_client,
        )

        # Verify the function called the API correctly
        mock_sso_admin_client.describe_permission_set.assert_called_once_with(
            InstanceArn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
            PermissionSetArn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        )

        # Verify the function returned the correct data
        assert (
            result["PermissionSetArn"]
            == "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
        )
        assert result["Name"] == "AdminAccess"
        assert result["Description"] == "Full administrative access"
        assert result["SessionDuration"] == "PT8H"

    @patch("src.awsideman.commands.assignment.helpers.console")
    def test_resolve_permission_set_info_minimal_response(
        self, mock_console, mock_sso_admin_client
    ):
        """Test resolve_permission_set_info with minimal response data."""
        # Setup mocks with minimal response
        minimal_response = {"PermissionSet": {"Name": "MinimalPermissionSet"}}
        mock_sso_admin_client.describe_permission_set.return_value = minimal_response

        # Call the function
        result = resolve_permission_set_info(
            instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            sso_admin_client=mock_sso_admin_client,
        )

        # Verify the function returned the correct data with defaults
        assert result["Name"] == "MinimalPermissionSet"
        assert result["Description"] is None
        assert result["SessionDuration"] == "PT1H"  # Default value

    @patch("src.awsideman.commands.assignment.helpers.console")
    def test_resolve_permission_set_info_not_found(self, mock_console, mock_sso_admin_client):
        """Test resolve_permission_set_info when permission set is not found."""
        # Setup mocks
        mock_sso_admin_client.exceptions.ResourceNotFoundException = type(
            "ResourceNotFoundException", (Exception,), {}
        )
        mock_sso_admin_client.describe_permission_set.side_effect = (
            mock_sso_admin_client.exceptions.ResourceNotFoundException()
        )

        # Call the function and expect exit
        with pytest.raises(typer.Exit):
            resolve_permission_set_info(
                instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
                sso_admin_client=mock_sso_admin_client,
            )

        # Verify the console output
        mock_console.print.assert_any_call(
            "[red]Error: Permission set with ARN 'arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef' not found.[/red]"
        )

    @patch("src.awsideman.commands.assignment.helpers.handle_aws_error")
    @patch("src.awsideman.commands.assignment.helpers.console")
    def test_resolve_permission_set_info_client_error(
        self, mock_console, mock_handle_aws_error, mock_sso_admin_client
    ):
        """Test resolve_permission_set_info with AWS client error."""
        # Setup mocks
        error_response = {
            "Error": {
                "Code": "AccessDeniedException",
                "Message": "User is not authorized to perform this action",
            }
        }
        mock_sso_admin_client.describe_permission_set.side_effect = ClientError(
            error_response, "DescribePermissionSet"
        )

        # Mock the exceptions attribute to avoid TypeError
        mock_sso_admin_client.exceptions.ResourceNotFoundException = type(
            "ResourceNotFoundException", (Exception,), {}
        )

        # Call the function
        resolve_permission_set_info(
            instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            sso_admin_client=mock_sso_admin_client,
        )

        # Verify the error handler was called
        mock_handle_aws_error.assert_called_once()

    @patch("src.awsideman.commands.assignment.helpers.console")
    def test_resolve_permission_set_info_generic_error(self, mock_console, mock_sso_admin_client):
        """Test resolve_permission_set_info with generic error."""
        # Setup mocks
        mock_sso_admin_client.describe_permission_set.side_effect = Exception("Generic error")

        # Mock the exceptions attribute to avoid TypeError
        mock_sso_admin_client.exceptions.ResourceNotFoundException = type(
            "ResourceNotFoundException", (Exception,), {}
        )

        # Call the function and expect exit
        with pytest.raises(typer.Exit):
            resolve_permission_set_info(
                instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
                sso_admin_client=mock_sso_admin_client,
            )

        # Verify the console output
        mock_console.print.assert_any_call("[red]Error: Generic error[/red]")


class TestResolvePrincipalInfo:
    """Tests for resolve_principal_info function."""

    @patch("src.awsideman.commands.assignment.helpers.console")
    def test_resolve_principal_info_user_successful(
        self, mock_console, mock_identity_store_client, sample_user_response
    ):
        """Test successful resolve_principal_info operation for USER."""
        # Setup mocks
        mock_identity_store_client.describe_user.return_value = sample_user_response

        # Call the function
        result = resolve_principal_info(
            identity_store_id="d-1234567890",
            principal_id="user-1234567890abcdef",
            principal_type="USER",
            identity_store_client=mock_identity_store_client,
        )

        # Verify the function called the API correctly
        mock_identity_store_client.describe_user.assert_called_once_with(
            IdentityStoreId="d-1234567890", UserId="user-1234567890abcdef"
        )

        # Verify the function returned the correct data
        assert result["PrincipalId"] == "user-1234567890abcdef"
        assert result["PrincipalType"] == "USER"
        assert result["PrincipalName"] == "john.doe"
        assert result["DisplayName"] == "John Doe"

    @patch("src.awsideman.commands.assignment.console")
    def test_resolve_principal_info_user_no_display_name(
        self, mock_console, mock_identity_store_client
    ):
        """Test resolve_principal_info for USER without display name."""
        # Setup mocks with user response without display name
        user_response = {
            "UserName": "jane.smith",
            "Name": {"GivenName": "Jane", "FamilyName": "Smith"},
        }
        mock_identity_store_client.describe_user.return_value = user_response

        # Call the function
        result = resolve_principal_info(
            identity_store_id="d-1234567890",
            principal_id="user-1234567890abcdef",
            principal_type="USER",
            identity_store_client=mock_identity_store_client,
        )

        # Verify the function constructed display name from name components
        assert result["PrincipalName"] == "jane.smith"
        assert result["DisplayName"] == "Jane Smith"

    @patch("src.awsideman.commands.assignment.console")
    def test_resolve_principal_info_user_minimal_info(
        self, mock_console, mock_identity_store_client
    ):
        """Test resolve_principal_info for USER with minimal information."""
        # Setup mocks with minimal user response
        user_response = {"UserName": "minimal.user"}
        mock_identity_store_client.describe_user.return_value = user_response

        # Call the function
        result = resolve_principal_info(
            identity_store_id="d-1234567890",
            principal_id="user-1234567890abcdef",
            principal_type="USER",
            identity_store_client=mock_identity_store_client,
        )

        # Verify the function used username as display name
        assert result["PrincipalName"] == "minimal.user"
        assert result["DisplayName"] == "minimal.user"

    @patch("src.awsideman.commands.assignment.helpers.console")
    def test_resolve_principal_info_group_successful(
        self, mock_console, mock_identity_store_client, sample_group_response
    ):
        """Test successful resolve_principal_info operation for GROUP."""
        # Setup mocks
        mock_identity_store_client.describe_group.return_value = sample_group_response

        # Call the function
        result = resolve_principal_info(
            identity_store_id="d-1234567890",
            principal_id="group-1234567890abcdef",
            principal_type="GROUP",
            identity_store_client=mock_identity_store_client,
        )

        # Verify the function called the API correctly
        mock_identity_store_client.describe_group.assert_called_once_with(
            IdentityStoreId="d-1234567890", GroupId="group-1234567890abcdef"
        )

        # Verify the function returned the correct data
        assert result["PrincipalId"] == "group-1234567890abcdef"
        assert result["PrincipalType"] == "GROUP"
        assert result["PrincipalName"] == "Administrators"
        assert result["DisplayName"] == "Administrators"

    @patch("src.awsideman.commands.assignment.helpers.console")
    def test_resolve_principal_info_user_not_found(self, mock_console, mock_identity_store_client):
        """Test resolve_principal_info when user is not found."""
        # Setup mocks
        mock_identity_store_client.exceptions.ResourceNotFoundException = type(
            "ResourceNotFoundException", (Exception,), {}
        )
        mock_identity_store_client.describe_user.side_effect = (
            mock_identity_store_client.exceptions.ResourceNotFoundException()
        )

        # Call the function and expect exit
        with pytest.raises(typer.Exit):
            resolve_principal_info(
                identity_store_id="d-1234567890",
                principal_id="user-1234567890abcdef",
                principal_type="USER",
                identity_store_client=mock_identity_store_client,
            )

        # Verify the console output
        mock_console.print.assert_any_call(
            "[red]Error: User with ID 'user-1234567890abcdef' not found.[/red]"
        )

    @patch("src.awsideman.commands.assignment.helpers.console")
    def test_resolve_principal_info_group_not_found(self, mock_console, mock_identity_store_client):
        """Test resolve_principal_info when group is not found."""
        # Setup mocks
        mock_identity_store_client.exceptions.ResourceNotFoundException = type(
            "ResourceNotFoundException", (Exception,), {}
        )
        mock_identity_store_client.describe_group.side_effect = (
            mock_identity_store_client.exceptions.ResourceNotFoundException()
        )

        # Call the function and expect exit
        with pytest.raises(typer.Exit):
            resolve_principal_info(
                identity_store_id="d-1234567890",
                principal_id="group-1234567890abcdef",
                principal_type="GROUP",
                identity_store_client=mock_identity_store_client,
            )

        # Verify the console output
        mock_console.print.assert_any_call(
            "[red]Error: Group with ID 'group-1234567890abcdef' not found.[/red]"
        )

    @patch("src.awsideman.commands.assignment.helpers.console")
    def test_resolve_principal_info_invalid_principal_type(
        self, mock_console, mock_identity_store_client
    ):
        """Test resolve_principal_info with invalid principal type."""
        # Call the function with invalid principal type and expect exit
        with pytest.raises(typer.Exit):
            resolve_principal_info(
                identity_store_id="d-1234567890",
                principal_id="principal-1234567890abcdef",
                principal_type="INVALID",
                identity_store_client=mock_identity_store_client,
            )

        # Verify the console output
        mock_console.print.assert_any_call("[red]Error: Invalid principal type 'INVALID'.[/red]")
        mock_console.print.assert_any_call(
            "[yellow]Principal type must be either 'USER' or 'GROUP'.[/yellow]"
        )

    @patch("src.awsideman.commands.assignment.helpers.handle_aws_error")
    @patch("src.awsideman.commands.assignment.helpers.console")
    def test_resolve_principal_info_user_client_error(
        self, mock_console, mock_handle_aws_error, mock_identity_store_client
    ):
        """Test resolve_principal_info with AWS client error for user."""
        # Setup mocks
        error_response = {
            "Error": {
                "Code": "AccessDeniedException",
                "Message": "User is not authorized to perform this action",
            }
        }
        mock_identity_store_client.describe_user.side_effect = ClientError(
            error_response, "DescribeUser"
        )

        # Mock the exceptions attribute to avoid TypeError
        mock_identity_store_client.exceptions.ResourceNotFoundException = type(
            "ResourceNotFoundException", (Exception,), {}
        )

        # Call the function
        resolve_principal_info(
            identity_store_id="d-1234567890",
            principal_id="user-1234567890abcdef",
            principal_type="USER",
            identity_store_client=mock_identity_store_client,
        )

        # Verify the error handler was called with correct operation
        mock_handle_aws_error.assert_called_once()
        args, kwargs = mock_handle_aws_error.call_args
        assert args[1] == "DescribeUser"

    @patch("src.awsideman.commands.assignment.helpers.handle_aws_error")
    @patch("src.awsideman.commands.assignment.helpers.console")
    def test_resolve_principal_info_group_client_error(
        self, mock_console, mock_handle_aws_error, mock_identity_store_client
    ):
        """Test resolve_principal_info with AWS client error for group."""
        # Setup mocks
        error_response = {
            "Error": {
                "Code": "AccessDeniedException",
                "Message": "User is not authorized to perform this action",
            }
        }
        mock_identity_store_client.describe_group.side_effect = ClientError(
            error_response, "DescribeGroup"
        )

        # Mock the exceptions attribute to avoid TypeError
        mock_identity_store_client.exceptions.ResourceNotFoundException = type(
            "ResourceNotFoundException", (Exception,), {}
        )

        # Call the function
        resolve_principal_info(
            identity_store_id="d-1234567890",
            principal_id="group-1234567890abcdef",
            principal_type="GROUP",
            identity_store_client=mock_identity_store_client,
        )

        # Verify the error handler was called with correct operation
        mock_handle_aws_error.assert_called_once()
        args, kwargs = mock_handle_aws_error.call_args
        assert args[1] == "DescribeGroup"

    @patch("src.awsideman.commands.assignment.helpers.console")
    def test_resolve_principal_info_generic_error(self, mock_console, mock_identity_store_client):
        """Test resolve_principal_info with generic error."""
        # Setup mocks
        mock_identity_store_client.describe_user.side_effect = Exception("Generic error")

        # Mock the exceptions attribute to avoid TypeError
        mock_identity_store_client.exceptions.ResourceNotFoundException = type(
            "ResourceNotFoundException", (Exception,), {}
        )

        # Call the function and expect exit
        with pytest.raises(typer.Exit):
            resolve_principal_info(
                identity_store_id="d-1234567890",
                principal_id="user-1234567890abcdef",
                principal_type="USER",
                identity_store_client=mock_identity_store_client,
            )

        # Verify the console output
        mock_console.print.assert_any_call("[red]Error: Generic error[/red]")

    @patch("src.awsideman.commands.assignment.console")
    def test_resolve_principal_info_case_insensitive_principal_type(
        self, mock_console, mock_identity_store_client, sample_user_response
    ):
        """Test resolve_principal_info with lowercase principal type."""
        # Setup mocks
        mock_identity_store_client.describe_user.return_value = sample_user_response

        # Call the function with lowercase principal type
        result = resolve_principal_info(
            identity_store_id="d-1234567890",
            principal_id="user-1234567890abcdef",
            principal_type="user",
            identity_store_client=mock_identity_store_client,
        )

        # Verify the function handled case insensitive principal type
        assert result["PrincipalType"] == "user"
        mock_identity_store_client.describe_user.assert_called_once()
