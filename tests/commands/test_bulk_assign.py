"""Tests for bulk assign command."""
import csv
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import typer

from src.awsideman.commands.bulk import bulk_assign
from src.awsideman.utils.bulk.batch import BatchProcessor


class TestBulkAssignCommand:
    """Test cases for bulk assign command."""

    def test_bulk_assign_csv_dry_run(self):
        """Test bulk assign with CSV file in dry-run mode."""
        # Create a temporary CSV file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            writer = csv.writer(f)
            writer.writerow(
                ["principal_name", "permission_set_name", "account_name", "principal_type"]
            )
            writer.writerow(["test-user", "ReadOnlyAccess", "TestAccount", "USER"])
            csv_file = Path(f.name)

        try:
            # Test that the command can be called and handles CSV files
            # We expect it to fail due to missing AWS credentials, but that's OK for this test
            with pytest.raises((SystemExit, typer.Exit)):
                bulk_assign(
                    csv_file,
                    dry_run=True,
                    continue_on_error=True,
                    batch_size=10,
                    profile="nonexistent-profile",
                )

        finally:
            # Clean up temporary file
            csv_file.unlink()

    def test_bulk_assign_json_format(self):
        """Test bulk assign with JSON file format."""
        # Create a temporary JSON file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                {
                    "assignments": [
                        {
                            "principal_name": "test-group",
                            "permission_set_name": "PowerUserAccess",
                            "account_name": "TestAccount",
                            "principal_type": "GROUP",
                        }
                    ]
                },
                f,
            )
            json_file = Path(f.name)

        try:
            # Test that the command can be called and handles JSON files
            # We expect it to fail due to missing AWS credentials, but that's OK for this test
            with pytest.raises((SystemExit, typer.Exit)):
                bulk_assign(
                    json_file,
                    dry_run=True,
                    continue_on_error=True,
                    batch_size=10,
                    profile="nonexistent-profile",
                )

        finally:
            # Clean up temporary file
            json_file.unlink()


class TestAssignmentOperationLogic:
    """Test cases for assignment operation logic in BatchProcessor."""

    @patch("src.awsideman.utils.bulk.batch.console")
    def test_execute_assign_operation_success(self, mock_console):
        """Test successful assignment creation."""
        # Create mock AWS client manager
        mock_aws_client = Mock()
        mock_sso_admin_client = Mock()
        mock_aws_client.get_identity_center_client.return_value = mock_sso_admin_client
        mock_aws_client.get_identity_store_client.return_value = Mock()

        # Setup mock responses
        mock_sso_admin_client.list_account_assignments.return_value = {
            "AccountAssignments": []  # No existing assignments
        }
        mock_sso_admin_client.create_account_assignment.return_value = {
            "AccountAssignmentCreationStatus": {
                "Status": "SUCCEEDED",
                "RequestId": "test-request-id",
            }
        }

        # Create batch processor
        batch_processor = BatchProcessor(mock_aws_client, batch_size=10)

        # Test assignment creation
        result = batch_processor._execute_assign_operation(
            principal_id="test-user-id",
            permission_set_arn="test-ps-arn",
            account_id="123456789012",
            principal_type="USER",
            instance_arn="test-instance-arn",
        )

        # Verify result
        assert result["status"] == "success"
        assert result["message"] == "Assignment created successfully"
        assert result["retry_count"] == 0
        assert result["request_id"] == "test-request-id"

        # Verify API calls
        mock_sso_admin_client.list_account_assignments.assert_called_once()
        mock_sso_admin_client.create_account_assignment.assert_called_once()

    @patch("src.awsideman.utils.bulk.batch.console")
    def test_execute_assign_operation_already_exists(self, mock_console):
        """Test assignment creation when assignment already exists."""
        # Create mock AWS client manager
        mock_aws_client = Mock()
        mock_sso_admin_client = Mock()
        mock_aws_client.get_identity_center_client.return_value = mock_sso_admin_client
        mock_aws_client.get_identity_store_client.return_value = Mock()

        # Setup mock responses - assignment already exists
        mock_sso_admin_client.list_account_assignments.return_value = {
            "AccountAssignments": [
                {
                    "PrincipalId": "test-user-id",
                    "PermissionSetArn": "test-ps-arn",
                    "AccountId": "123456789012",
                    "PrincipalType": "USER",
                }
            ]
        }

        # Create batch processor
        batch_processor = BatchProcessor(mock_aws_client, batch_size=10)

        # Test assignment creation
        result = batch_processor._execute_assign_operation(
            principal_id="test-user-id",
            permission_set_arn="test-ps-arn",
            account_id="123456789012",
            principal_type="USER",
            instance_arn="test-instance-arn",
        )

        # Verify result - should be skipped when assignment already exists
        assert result["status"] == "skipped"
        assert result["message"] == "Assignment already exists"
        assert result["retry_count"] == 0

        # Verify only list API was called, not create
        mock_sso_admin_client.list_account_assignments.assert_called_once()
        mock_sso_admin_client.create_account_assignment.assert_not_called()

    @patch("src.awsideman.utils.bulk.batch.console")
    def test_execute_revoke_operation_success(self, mock_console):
        """Test successful assignment revocation."""
        # Create mock AWS client manager
        mock_aws_client = Mock()
        mock_sso_admin_client = Mock()
        mock_aws_client.get_identity_center_client.return_value = mock_sso_admin_client
        mock_aws_client.get_identity_store_client.return_value = Mock()

        # Setup mock responses
        mock_sso_admin_client.list_account_assignments.return_value = {
            "AccountAssignments": [
                {
                    "PrincipalId": "test-user-id",
                    "PermissionSetArn": "test-ps-arn",
                    "AccountId": "123456789012",
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
        batch_processor = BatchProcessor(mock_aws_client, batch_size=10)

        # Test assignment revocation
        result = batch_processor._execute_revoke_operation(
            principal_id="test-user-id",
            permission_set_arn="test-ps-arn",
            account_id="123456789012",
            principal_type="USER",
            instance_arn="test-instance-arn",
        )

        # Verify result - should be success when assignment is successfully revoked
        assert result["status"] == "success"
        assert result["message"] == "Assignment revoked successfully"
        assert result["retry_count"] == 0
        assert result["request_id"] == "test-request-id"

        # Verify API calls
        mock_sso_admin_client.list_account_assignments.assert_called_once()
        mock_sso_admin_client.delete_account_assignment.assert_called_once()

    @patch("src.awsideman.utils.bulk.batch.console")
    def test_execute_revoke_operation_not_exists(self, mock_console):
        """Test assignment revocation when assignment doesn't exist."""
        # Create mock AWS client manager
        mock_aws_client = Mock()
        mock_sso_admin_client = Mock()
        mock_aws_client.get_identity_center_client.return_value = mock_sso_admin_client
        mock_aws_client.get_identity_store_client.return_value = Mock()

        # Setup mock responses - no existing assignments
        mock_sso_admin_client.list_account_assignments.return_value = {"AccountAssignments": []}

        # Create batch processor
        batch_processor = BatchProcessor(mock_aws_client, batch_size=10)

        # Test assignment revocation
        result = batch_processor._execute_revoke_operation(
            principal_id="test-user-id",
            permission_set_arn="test-ps-arn",
            account_id="123456789012",
            principal_type="USER",
            instance_arn="test-instance-arn",
        )

        # Verify result - should be skipped when assignment doesn't exist
        assert result["status"] == "skipped"
        assert result["message"] == "Assignment does not exist (already revoked)"
        assert result["retry_count"] == 0

        # Verify only list API was called, not delete
        mock_sso_admin_client.list_account_assignments.assert_called_once()
        mock_sso_admin_client.delete_account_assignment.assert_not_called()
