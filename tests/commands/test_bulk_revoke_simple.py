"""Simple tests for bulk revoke operation logic."""
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError

from src.awsideman.utils.bulk.batch import BatchProcessor


class TestBulkRevokeOperationLogic:
    """Test cases for bulk revoke operation logic."""

    def test_execute_revoke_operation_success(self):
        """Test successful revoke operation."""
        # Create mock AWS client manager
        mock_aws_client = Mock()
        mock_sso_admin_client = Mock()
        mock_aws_client.get_identity_center_client.return_value = mock_sso_admin_client
        mock_aws_client.get_identity_store_client.return_value = Mock()

        # Setup successful delete response
        mock_sso_admin_client.list_account_assignments.return_value = {
            "AccountAssignments": [
                {
                    "AccountId": "123456789012",
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/test/ReadOnlyAccess",
                    "PrincipalId": "test-user-id",
                    "PrincipalType": "USER",
                }
            ]
        }

        mock_sso_admin_client.delete_account_assignment.return_value = {
            "AccountAssignmentDeletionStatus": {
                "Status": "SUCCEEDED",
                "RequestId": "test-request-id",
            }
        }

        # Create batch processor
        batch_processor = BatchProcessor(mock_aws_client, batch_size=1)

        # Execute revoke operation
        result = batch_processor._execute_revoke_operation(
            principal_id="test-user-id",
            permission_set_arn="arn:aws:sso:::permissionSet/test/ReadOnlyAccess",
            account_id="123456789012",
            principal_type="USER",
            instance_arn="arn:aws:sso:::instance/test",
        )

        # Verify result
        assert result["status"] == "success"
        assert result["message"] == "Assignment revoked successfully"
        assert result["retry_count"] == 0
        assert result["request_id"] == "test-request-id"

        # Verify API calls
        mock_sso_admin_client.list_account_assignments.assert_called_once_with(
            InstanceArn="arn:aws:sso:::instance/test",
            AccountId="123456789012",
            PermissionSetArn="arn:aws:sso:::permissionSet/test/ReadOnlyAccess",
        )
        mock_sso_admin_client.delete_account_assignment.assert_called_once()

    def test_execute_revoke_operation_assignment_not_found(self):
        """Test revoke operation when assignment doesn't exist."""
        # Create mock AWS client manager
        mock_aws_client = Mock()
        mock_sso_admin_client = Mock()
        mock_aws_client.get_identity_center_client.return_value = mock_sso_admin_client
        mock_aws_client.get_identity_store_client.return_value = Mock()

        # Setup empty list response (assignment doesn't exist)
        mock_sso_admin_client.list_account_assignments.return_value = {"AccountAssignments": []}

        # Create batch processor
        batch_processor = BatchProcessor(mock_aws_client, batch_size=1)

        # Execute revoke operation
        result = batch_processor._execute_revoke_operation(
            principal_id="test-user-id",
            permission_set_arn="arn:aws:sso:::permissionSet/test/ReadOnlyAccess",
            account_id="123456789012",
            principal_type="USER",
            instance_arn="arn:aws:sso:::instance/test",
        )

        # Verify result - should be skipped if assignment doesn't exist
        assert result["status"] == "skipped"
        assert result["message"] == "Assignment does not exist (already revoked)"
        assert result["retry_count"] == 0

        # Verify only list was called, not delete
        mock_sso_admin_client.list_account_assignments.assert_called_once_with(
            InstanceArn="arn:aws:sso:::instance/test",
            AccountId="123456789012",
            PermissionSetArn="arn:aws:sso:::permissionSet/test/ReadOnlyAccess",
        )
        mock_sso_admin_client.delete_account_assignment.assert_not_called()

    def test_execute_revoke_operation_in_progress(self):
        """Test revoke operation with IN_PROGRESS status."""
        # Create mock AWS client manager
        mock_aws_client = Mock()
        mock_sso_admin_client = Mock()
        mock_aws_client.get_identity_center_client.return_value = mock_sso_admin_client
        mock_aws_client.get_identity_store_client.return_value = Mock()

        # Setup existing assignment
        mock_sso_admin_client.list_account_assignments.return_value = {
            "AccountAssignments": [
                {
                    "AccountId": "123456789012",
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/test/ReadOnlyAccess",
                    "PrincipalId": "test-user-id",
                    "PrincipalType": "USER",
                }
            ]
        }

        # Setup IN_PROGRESS delete response
        mock_sso_admin_client.delete_account_assignment.return_value = {
            "AccountAssignmentDeletionStatus": {
                "Status": "IN_PROGRESS",
                "RequestId": "test-request-id",
            }
        }

        # Create batch processor
        batch_processor = BatchProcessor(mock_aws_client, batch_size=1)

        # Execute revoke operation
        result = batch_processor._execute_revoke_operation(
            principal_id="test-user-id",
            permission_set_arn="arn:aws:sso:::permissionSet/test/ReadOnlyAccess",
            account_id="123456789012",
            principal_type="USER",
            instance_arn="arn:aws:sso:::instance/test",
        )

        # Verify result - IN_PROGRESS should be considered success
        assert result["status"] == "success"
        assert result["message"] == "Assignment revocation in progress"
        assert result["retry_count"] == 0
        assert result["request_id"] == "test-request-id"

    def test_execute_revoke_operation_access_denied(self):
        """Test revoke operation with access denied error."""
        # Create mock AWS client manager
        mock_aws_client = Mock()
        mock_sso_admin_client = Mock()
        mock_aws_client.get_identity_center_client.return_value = mock_sso_admin_client
        mock_aws_client.get_identity_store_client.return_value = Mock()

        # Setup existing assignment
        mock_sso_admin_client.list_account_assignments.return_value = {
            "AccountAssignments": [
                {
                    "AccountId": "123456789012",
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/test/ReadOnlyAccess",
                    "PrincipalId": "test-user-id",
                    "PrincipalType": "USER",
                }
            ]
        }

        # Setup access denied error
        error_response = {
            "Error": {
                "Code": "AccessDeniedException",
                "Message": "User is not authorized to perform this action",
            }
        }
        mock_sso_admin_client.delete_account_assignment.side_effect = ClientError(
            error_response, "DeleteAccountAssignment"
        )

        # Create batch processor
        batch_processor = BatchProcessor(mock_aws_client, batch_size=1)

        # Execute revoke operation - should raise exception
        with pytest.raises(ClientError) as exc_info:
            batch_processor._execute_revoke_operation(
                principal_id="test-user-id",
                permission_set_arn="arn:aws:sso:::permissionSet/test/ReadOnlyAccess",
                account_id="123456789012",
                principal_type="USER",
                instance_arn="arn:aws:sso:::instance/test",
            )

        # Verify error code
        assert exc_info.value.response["Error"]["Code"] == "AccessDeniedException"

    def test_execute_revoke_operation_supports_both_user_and_group(self):
        """Test that revoke operation supports both USER and GROUP principal types."""
        # Create mock AWS client manager
        mock_aws_client = Mock()
        mock_sso_admin_client = Mock()
        mock_aws_client.get_identity_center_client.return_value = mock_sso_admin_client
        mock_aws_client.get_identity_store_client.return_value = Mock()

        # Setup successful responses for both calls - include both user and group assignments
        mock_sso_admin_client.list_account_assignments.return_value = {
            "AccountAssignments": [
                {
                    "AccountId": "123456789012",
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/test/ReadOnlyAccess",
                    "PrincipalId": "test-user-id",
                    "PrincipalType": "USER",
                },
                {
                    "AccountId": "123456789012",
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/test/ReadOnlyAccess",
                    "PrincipalId": "test-group-id",
                    "PrincipalType": "GROUP",
                },
            ]
        }

        mock_sso_admin_client.delete_account_assignment.return_value = {
            "AccountAssignmentDeletionStatus": {
                "Status": "SUCCEEDED",
                "RequestId": "test-request-id",
            }
        }

        # Create batch processor
        batch_processor = BatchProcessor(mock_aws_client, batch_size=1)

        # Test USER principal type
        result_user = batch_processor._execute_revoke_operation(
            principal_id="test-user-id",
            permission_set_arn="arn:aws:sso:::permissionSet/test/ReadOnlyAccess",
            account_id="123456789012",
            principal_type="USER",
            instance_arn="arn:aws:sso:::instance/test",
        )

        assert result_user["status"] == "success"

        # Test GROUP principal type
        result_group = batch_processor._execute_revoke_operation(
            principal_id="test-group-id",
            permission_set_arn="arn:aws:sso:::permissionSet/test/ReadOnlyAccess",
            account_id="123456789012",
            principal_type="GROUP",
            instance_arn="arn:aws:sso:::instance/test",
        )

        assert result_group["status"] == "success"

        # Verify both calls were made with correct principal types
        assert mock_sso_admin_client.delete_account_assignment.call_count == 2

        # Check the calls were made with correct parameters
        calls = mock_sso_admin_client.delete_account_assignment.call_args_list

        # First call should be for USER
        user_call = calls[0][1]  # kwargs
        assert user_call["PrincipalType"] == "USER"
        assert user_call["PrincipalId"] == "test-user-id"

        # Second call should be for GROUP
        group_call = calls[1][1]  # kwargs
        assert group_call["PrincipalType"] == "GROUP"
        assert group_call["PrincipalId"] == "test-group-id"

    def test_execute_revoke_operation_filters_assignments_correctly(self):
        """Test that revoke operation correctly filters assignments when multiple exist."""
        # Create mock AWS client manager
        mock_aws_client = Mock()
        mock_sso_admin_client = Mock()
        mock_aws_client.get_identity_center_client.return_value = mock_sso_admin_client
        mock_aws_client.get_identity_store_client.return_value = Mock()

        # Setup response with multiple assignments, but only one matches our principal
        mock_sso_admin_client.list_account_assignments.return_value = {
            "AccountAssignments": [
                {
                    "AccountId": "123456789012",
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/test/ReadOnlyAccess",
                    "PrincipalId": "other-user-id",
                    "PrincipalType": "USER",
                },
                {
                    "AccountId": "123456789012",
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/test/ReadOnlyAccess",
                    "PrincipalId": "test-user-id",
                    "PrincipalType": "USER",
                },
                {
                    "AccountId": "123456789012",
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/test/ReadOnlyAccess",
                    "PrincipalId": "test-group-id",
                    "PrincipalType": "GROUP",
                },
            ]
        }

        mock_sso_admin_client.delete_account_assignment.return_value = {
            "AccountAssignmentDeletionStatus": {
                "Status": "SUCCEEDED",
                "RequestId": "test-request-id",
            }
        }

        # Create batch processor
        batch_processor = BatchProcessor(mock_aws_client, batch_size=1)

        # Execute revoke operation for specific user
        result = batch_processor._execute_revoke_operation(
            principal_id="test-user-id",
            permission_set_arn="arn:aws:sso:::permissionSet/test/ReadOnlyAccess",
            account_id="123456789012",
            principal_type="USER",
            instance_arn="arn:aws:sso:::instance/test",
        )

        # Verify result - should succeed because matching assignment was found
        assert result["status"] == "success"
        assert result["message"] == "Assignment revoked successfully"

        # Verify delete was called (because matching assignment was found)
        mock_sso_admin_client.delete_account_assignment.assert_called_once()

    def test_execute_revoke_operation_no_matching_assignment(self):
        """Test that revoke operation handles case where no matching assignment exists."""
        # Create mock AWS client manager
        mock_aws_client = Mock()
        mock_sso_admin_client = Mock()
        mock_aws_client.get_identity_center_client.return_value = mock_sso_admin_client
        mock_aws_client.get_identity_store_client.return_value = Mock()

        # Setup response with assignments, but none match our principal
        mock_sso_admin_client.list_account_assignments.return_value = {
            "AccountAssignments": [
                {
                    "AccountId": "123456789012",
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/test/ReadOnlyAccess",
                    "PrincipalId": "other-user-id",
                    "PrincipalType": "USER",
                },
                {
                    "AccountId": "123456789012",
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/test/ReadOnlyAccess",
                    "PrincipalId": "another-group-id",
                    "PrincipalType": "GROUP",
                },
            ]
        }

        # Create batch processor
        batch_processor = BatchProcessor(mock_aws_client, batch_size=1)

        # Execute revoke operation for user that doesn't have assignment
        result = batch_processor._execute_revoke_operation(
            principal_id="test-user-id",
            permission_set_arn="arn:aws:sso:::permissionSet/test/ReadOnlyAccess",
            account_id="123456789012",
            principal_type="USER",
            instance_arn="arn:aws:sso:::instance/test",
        )

        # Verify result - should be skipped because assignment doesn't exist (already revoked)
        assert result["status"] == "skipped"
        assert result["message"] == "Assignment does not exist (already revoked)"

        # Verify delete was NOT called (because no matching assignment was found)
        mock_sso_admin_client.delete_account_assignment.assert_not_called()
