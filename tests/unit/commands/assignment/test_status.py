"""Tests for assignment status command."""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import typer
from botocore.exceptions import ClientError

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "src"))

from awsideman.commands.assignment.status import check_assignment_status  # noqa: E402


class TestAssignmentStatusCommand:
    """Test cases for assignment status command."""

    @patch("awsideman.commands.assignment.status.validate_profile")
    @patch("awsideman.commands.assignment.status.validate_sso_instance")
    @patch("awsideman.commands.assignment.status.AWSClientManager")
    def test_check_assignment_status_success_creation(
        self, mock_aws_client_manager, mock_validate_sso, mock_validate_profile
    ):
        """Test successful status check for assignment creation."""
        # Setup mocks
        mock_validate_profile.return_value = ("test-profile", {})
        mock_validate_sso.return_value = ("instance-arn", "identity-store-id")

        mock_aws_client = Mock()
        mock_aws_client_manager.return_value = mock_aws_client

        mock_sso_admin_client = Mock()
        mock_aws_client.get_sso_admin_client.return_value = mock_sso_admin_client

        # Mock successful creation status response
        mock_sso_admin_client.describe_account_assignment_creation_status.return_value = {
            "AccountAssignmentCreationStatus": {
                "Status": "SUCCEEDED",
                "RequestId": "test-request-id",
                "CreatedDate": "2024-01-01T00:00:00Z",
                "AccountAssignment": {
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/test",
                    "PrincipalId": "user-123",
                    "PrincipalType": "USER",
                    "AccountId": "123456789012",
                },
            }
        }

        # Test the function - should not raise SystemExit for success cases
        check_assignment_status("test-request-id")

        # Verify the API was called correctly
        mock_sso_admin_client.describe_account_assignment_creation_status.assert_called_once_with(
            InstanceArn="instance-arn",
            AccountAssignmentCreationRequestId="test-request-id",
        )

    @patch("awsideman.commands.assignment.status.validate_profile")
    @patch("awsideman.commands.assignment.status.validate_sso_instance")
    @patch("awsideman.commands.assignment.status.AWSClientManager")
    def test_check_assignment_status_success_deletion(
        self, mock_aws_client_manager, mock_validate_sso, mock_validate_profile
    ):
        """Test successful status check for assignment deletion."""
        # Setup mocks
        mock_validate_profile.return_value = ("test-profile", {})
        mock_validate_sso.return_value = ("instance-arn", "identity-store-id")

        mock_aws_client = Mock()
        mock_aws_client_manager.return_value = mock_aws_client

        mock_sso_admin_client = Mock()
        mock_aws_client.get_sso_admin_client.return_value = mock_sso_admin_client

        # Mock creation status not found, deletion status found
        mock_sso_admin_client.describe_account_assignment_creation_status.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException"}},
            "DescribeAccountAssignmentCreationStatus",
        )

        mock_sso_admin_client.describe_account_assignment_deletion_status.return_value = {
            "AccountAssignmentDeletionStatus": {
                "Status": "IN_PROGRESS",
                "RequestId": "test-request-id",
                "CreatedDate": "2024-01-01T00:00:00Z",
                "AccountAssignment": {
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/test",
                    "PrincipalId": "user-123",
                    "PrincipalType": "USER",
                    "AccountId": "123456789012",
                },
            }
        }

        # Test the function - should not raise SystemExit for success cases
        check_assignment_status("test-request-id")

        # Verify both APIs were called
        mock_sso_admin_client.describe_account_assignment_creation_status.assert_called_once()
        mock_sso_admin_client.describe_account_assignment_deletion_status.assert_called_once_with(
            InstanceArn="instance-arn",
            AccountAssignmentDeletionRequestId="test-request-id",
        )

    @patch("awsideman.commands.assignment.status.validate_profile")
    @patch("awsideman.commands.assignment.status.validate_sso_instance")
    @patch("awsideman.commands.assignment.status.AWSClientManager")
    def test_check_assignment_status_not_found(
        self, mock_aws_client_manager, mock_validate_sso, mock_validate_profile
    ):
        """Test status check when request ID is not found."""
        # Setup mocks
        mock_validate_profile.return_value = ("test-profile", {})
        mock_validate_sso.return_value = ("instance-arn", "identity-store-id")

        mock_aws_client = Mock()
        mock_aws_client_manager.return_value = mock_aws_client

        mock_sso_admin_client = Mock()
        mock_aws_client.get_sso_admin_client.return_value = mock_sso_admin_client

        # Mock both creation and deletion status not found
        mock_sso_admin_client.describe_account_assignment_creation_status.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException"}},
            "DescribeAccountAssignmentCreationStatus",
        )
        mock_sso_admin_client.describe_account_assignment_deletion_status.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException"}},
            "DescribeAccountAssignmentDeletionStatus",
        )

        # Test the function - should raise typer.Exit for error cases
        with pytest.raises(typer.Exit) as exc_info:
            check_assignment_status("test-request-id")

        # Should exit with code 1 (error)
        assert exc_info.value.exit_code == 1

    @patch("awsideman.commands.assignment.status.validate_profile")
    @patch("awsideman.commands.assignment.status.validate_sso_instance")
    @patch("awsideman.commands.assignment.status.AWSClientManager")
    def test_check_assignment_status_failed(
        self, mock_aws_client_manager, mock_validate_sso, mock_validate_profile
    ):
        """Test status check for failed assignment."""
        # Setup mocks
        mock_validate_profile.return_value = ("test-profile", {})
        mock_validate_sso.return_value = ("instance-arn", "identity-store-id")

        mock_aws_client = Mock()
        mock_aws_client_manager.return_value = mock_aws_client

        mock_sso_admin_client = Mock()
        mock_aws_client.get_sso_admin_client.return_value = mock_sso_admin_client

        # Mock failed creation status response
        mock_sso_admin_client.describe_account_assignment_creation_status.return_value = {
            "AccountAssignmentCreationStatus": {
                "Status": "FAILED",
                "RequestId": "test-request-id",
                "CreatedDate": "2024-01-01T00:00:00Z",
                "FailureReason": "Permission denied",
                "AccountAssignment": {
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/test",
                    "PrincipalId": "user-123",
                    "PrincipalType": "USER",
                    "AccountId": "123456789012",
                },
            }
        }

        # Test the function - should not raise SystemExit for status display
        check_assignment_status("test-request-id")

    @patch("awsideman.commands.assignment.status.validate_profile")
    @patch("awsideman.commands.assignment.status.validate_sso_instance")
    def test_check_assignment_status_empty_request_id(
        self, mock_validate_sso, mock_validate_profile
    ):
        """Test status check with empty request ID."""
        # Setup mocks to avoid validation issues
        mock_validate_profile.return_value = ("test-profile", {})
        mock_validate_sso.return_value = ("instance-arn", "identity-store-id")

        with pytest.raises(typer.Exit) as exc_info:
            check_assignment_status("")

        # Should exit with code 1 (error)
        assert exc_info.value.exit_code == 1
