"""Tests for bulk assign command."""
import csv
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.awsideman.commands.bulk import bulk_assign
from src.awsideman.utils.bulk import BatchProcessor


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
            # Mock the dependencies
            with patch("awsideman.commands.bulk.validate_profile") as mock_validate_profile, patch(
                "awsideman.commands.bulk.validate_sso_instance"
            ) as mock_validate_sso, patch("awsideman.commands.bulk.console"):
                # Setup mocks
                mock_validate_profile.return_value = ("test-profile", {"sso_start_url": "test"})
                mock_validate_sso.return_value = ("test-instance-arn", "test-identity-store-id")

                # Mock the file processing and resolution
                with patch(
                    "awsideman.utils.bulk.processors.FileFormatDetector.get_processor"
                ) as mock_processor, patch(
                    "awsideman.utils.bulk.resolver.ResourceResolver"
                ) as mock_resolver, patch(
                    "awsideman.utils.bulk.preview.PreviewGenerator"
                ) as mock_preview:
                    # Setup processor mock
                    mock_proc_instance = Mock()
                    mock_proc_instance.validate_format.return_value = []
                    mock_proc_instance.parse_assignments.return_value = [
                        {
                            "principal_name": "test-user",
                            "permission_set_name": "ReadOnlyAccess",
                            "account_name": "TestAccount",
                            "principal_type": "USER",
                        }
                    ]
                    mock_processor.return_value = mock_proc_instance

                    # Setup resolver mock
                    mock_resolver_instance = Mock()
                    mock_resolver_instance.resolve_assignment.return_value = {
                        "principal_name": "test-user",
                        "permission_set_name": "ReadOnlyAccess",
                        "account_name": "TestAccount",
                        "principal_type": "USER",
                        "principal_id": "test-user-id",
                        "permission_set_arn": "test-ps-arn",
                        "account_id": "123456789012",
                        "resolution_success": True,
                        "resolution_errors": [],
                    }
                    mock_resolver.return_value = mock_resolver_instance

                    # Setup preview mock
                    mock_preview_instance = Mock()
                    mock_preview_instance.generate_preview_report.return_value = Mock(
                        total_assignments=1, successful_resolutions=1, failed_resolutions=0
                    )
                    mock_preview.return_value = mock_preview_instance

                    # Test dry-run mode (should exit early)
                    with pytest.raises(SystemExit) as exc_info:
                        bulk_assign(
                            csv_file,
                            dry_run=True,
                            continue_on_error=True,
                            batch_size=10,
                            profile=None,
                        )

                    # Verify dry-run completed successfully
                    assert exc_info.value.code == 0

                    # Verify preview was generated
                    mock_preview_instance.generate_preview_report.assert_called_once()
                    mock_preview_instance.display_dry_run_message.assert_called_once()

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
            # Mock the dependencies
            with patch("awsideman.commands.bulk.validate_profile") as mock_validate_profile, patch(
                "awsideman.commands.bulk.validate_sso_instance"
            ) as mock_validate_sso, patch("awsideman.commands.bulk.console"):
                # Setup mocks
                mock_validate_profile.return_value = ("test-profile", {"sso_start_url": "test"})
                mock_validate_sso.return_value = ("test-instance-arn", "test-identity-store-id")

                # Mock the file processing
                with patch(
                    "awsideman.utils.bulk.processors.FileFormatDetector.get_processor"
                ) as mock_processor:
                    # Setup processor mock
                    mock_proc_instance = Mock()
                    mock_proc_instance.validate_format.return_value = []
                    mock_proc_instance.parse_assignments.return_value = [
                        {
                            "principal_name": "test-group",
                            "permission_set_name": "PowerUserAccess",
                            "account_name": "TestAccount",
                            "principal_type": "GROUP",
                        }
                    ]
                    mock_processor.return_value = mock_proc_instance

                    # Test that JSON format is detected and processed
                    with patch(
                        "awsideman.utils.bulk.processors.FileFormatDetector.detect_format"
                    ) as mock_detect:
                        mock_detect.return_value = "json"

                        # This will fail at resolution step, but that's expected for this test
                        with pytest.raises(SystemExit):
                            bulk_assign(
                                json_file,
                                dry_run=True,
                                continue_on_error=True,
                                batch_size=10,
                                profile=None,
                            )

                        # Verify JSON format was detected
                        mock_detect.assert_called_once_with(json_file)

        finally:
            # Clean up temporary file
            json_file.unlink()


class TestAssignmentOperationLogic:
    """Test cases for assignment operation logic in BatchProcessor."""

    @patch("awsideman.utils.bulk.batch.console")
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

    @patch("awsideman.utils.bulk.batch.console")
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

        # Verify result
        assert result["status"] == "success"
        assert result["message"] == "Assignment already exists"
        assert result["retry_count"] == 0

        # Verify only list API was called, not create
        mock_sso_admin_client.list_account_assignments.assert_called_once()
        mock_sso_admin_client.create_account_assignment.assert_not_called()

    @patch("awsideman.utils.bulk.batch.console")
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

        # Verify result
        assert result["status"] == "success"
        assert result["message"] == "Assignment revoked successfully"
        assert result["retry_count"] == 0
        assert result["request_id"] == "test-request-id"

        # Verify API calls
        mock_sso_admin_client.list_account_assignments.assert_called_once()
        mock_sso_admin_client.delete_account_assignment.assert_called_once()

    @patch("awsideman.utils.bulk.batch.console")
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

        # Verify result
        assert result["status"] == "success"
        assert result["message"] == "Assignment does not exist (already revoked)"
        assert result["retry_count"] == 0

        # Verify only list API was called, not delete
        mock_sso_admin_client.list_account_assignments.assert_called_once()
        mock_sso_admin_client.delete_account_assignment.assert_not_called()
