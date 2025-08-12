"""Integration tests for bulk operation logging."""

import shutil
import tempfile
from unittest.mock import Mock, patch

from src.awsideman.aws_clients.manager import AWSClientManager
from src.awsideman.utils.bulk.batch import AssignmentResult, BatchProcessor
from src.awsideman.utils.rollback.logger import OperationLogger


class TestBulkOperationLogging:
    """Tests for bulk operation logging integration."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()

        # Mock AWS client manager
        self.mock_aws_client = Mock(spec=AWSClientManager)
        self.mock_sso_admin_client = Mock()
        self.mock_identity_store_client = Mock()

        self.mock_aws_client.get_identity_center_client.return_value = self.mock_sso_admin_client
        self.mock_aws_client.get_identity_store_client.return_value = (
            self.mock_identity_store_client
        )

        # Create batch processor
        self.batch_processor = BatchProcessor(self.mock_aws_client, batch_size=2)

        # Override the operation logger to use temp directory
        self.batch_processor.operation_logger = OperationLogger(self.temp_dir)

    def teardown_method(self):
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir)

    def test_log_bulk_assign_operations(self):
        """Test logging of successful bulk assign operations."""
        # Create successful assignment results
        successful_results = [
            AssignmentResult(
                principal_name="john.doe",
                permission_set_name="ReadOnlyAccess",
                account_name="Production",
                principal_type="USER",
                principal_id="user-123",
                permission_set_arn="arn:aws:sso:::permissionSet/ps-123",
                account_id="123456789012",
                status="success",
                processing_time=1.5,
            ),
            AssignmentResult(
                principal_name="john.doe",
                permission_set_name="ReadOnlyAccess",
                account_name="Staging",
                principal_type="USER",
                principal_id="user-123",
                permission_set_arn="arn:aws:sso:::permissionSet/ps-123",
                account_id="123456789013",
                status="success",
                processing_time=1.2,
            ),
        ]

        # Original assignments for metadata
        original_assignments = [
            {
                "principal_name": "john.doe",
                "permission_set_name": "ReadOnlyAccess",
                "account_name": "Production",
                "_input_file": "assignments.csv",
                "_file_format": "csv",
            },
            {
                "principal_name": "john.doe",
                "permission_set_name": "ReadOnlyAccess",
                "account_name": "Staging",
                "_input_file": "assignments.csv",
                "_file_format": "csv",
            },
        ]

        # Call the logging method
        self.batch_processor._log_bulk_operations(
            successful_results, "assign", original_assignments
        )

        # Verify operation was logged
        operations = self.batch_processor.operation_logger.get_operations()
        assert len(operations) == 1

        operation = operations[0]
        assert operation.operation_type.value == "assign"
        assert operation.principal_name == "john.doe"
        assert operation.permission_set_name == "ReadOnlyAccess"
        assert len(operation.account_ids) == 2
        assert "123456789012" in operation.account_ids
        assert "123456789013" in operation.account_ids
        assert operation.metadata["source"] == "bulk_operation"
        assert operation.metadata["input_file"] == "assignments.csv"
        assert operation.metadata["file_format"] == "csv"

    def test_log_bulk_revoke_operations(self):
        """Test logging of successful bulk revoke operations."""
        # Create successful assignment results
        successful_results = [
            AssignmentResult(
                principal_name="jane.doe",
                permission_set_name="DeveloperAccess",
                account_name="Development",
                principal_type="USER",
                principal_id="user-456",
                permission_set_arn="arn:aws:sso:::permissionSet/ps-456",
                account_id="123456789014",
                status="success",
                processing_time=0.8,
            )
        ]

        # Original assignments for metadata
        original_assignments = [
            {
                "principal_name": "jane.doe",
                "permission_set_name": "DeveloperAccess",
                "account_name": "Development",
                "_input_file": "revocations.json",
                "_file_format": "json",
            }
        ]

        # Call the logging method
        self.batch_processor._log_bulk_operations(
            successful_results, "revoke", original_assignments
        )

        # Verify operation was logged
        operations = self.batch_processor.operation_logger.get_operations()
        assert len(operations) == 1

        operation = operations[0]
        assert operation.operation_type.value == "revoke"
        assert operation.principal_name == "jane.doe"
        assert operation.permission_set_name == "DeveloperAccess"
        assert len(operation.account_ids) == 1
        assert operation.account_ids[0] == "123456789014"
        assert operation.metadata["source"] == "bulk_operation"
        assert operation.metadata["input_file"] == "revocations.json"

    def test_log_multiple_principals_operations(self):
        """Test logging operations for multiple principals."""
        # Create successful assignment results for different principals
        successful_results = [
            AssignmentResult(
                principal_name="john.doe",
                permission_set_name="ReadOnlyAccess",
                account_name="Production",
                principal_type="USER",
                principal_id="user-123",
                permission_set_arn="arn:aws:sso:::permissionSet/ps-123",
                account_id="123456789012",
                status="success",
                processing_time=1.0,
            ),
            AssignmentResult(
                principal_name="developers",
                permission_set_name="DeveloperAccess",
                account_name="Development",
                principal_type="GROUP",
                principal_id="group-456",
                permission_set_arn="arn:aws:sso:::permissionSet/ps-456",
                account_id="123456789014",
                status="success",
                processing_time=1.2,
            ),
        ]

        # Original assignments for metadata
        original_assignments = [
            {"principal_name": "john.doe", "permission_set_name": "ReadOnlyAccess"},
            {"principal_name": "developers", "permission_set_name": "DeveloperAccess"},
        ]

        # Call the logging method
        self.batch_processor._log_bulk_operations(
            successful_results, "assign", original_assignments
        )

        # Verify both operations were logged separately
        operations = self.batch_processor.operation_logger.get_operations()
        assert len(operations) == 2

        # Check that we have operations for both principals
        principal_names = [op.principal_name for op in operations]
        assert "john.doe" in principal_names
        assert "developers" in principal_names

    def test_extract_bulk_metadata(self):
        """Test extraction of metadata from original assignments."""
        original_assignments = [
            {"principal_name": "test.user", "_input_file": "test.csv", "_file_format": "csv"},
            {"principal_name": "another.user", "_input_file": "test.csv", "_file_format": "csv"},
        ]

        metadata = self.batch_processor._extract_bulk_metadata(original_assignments)

        assert metadata["source"] == "bulk_operation"
        assert metadata["batch_size"] == 2
        assert metadata["total_assignments"] == 2
        assert metadata["input_file"] == "test.csv"
        assert metadata["file_format"] == "csv"

    def test_extract_bulk_metadata_no_file_info(self):
        """Test metadata extraction when file info is not available."""
        original_assignments = [{"principal_name": "test.user"}, {"principal_name": "another.user"}]

        metadata = self.batch_processor._extract_bulk_metadata(original_assignments)

        assert metadata["source"] == "bulk_operation"
        assert metadata["batch_size"] == 2
        assert metadata["total_assignments"] == 2
        assert "input_file" not in metadata
        assert "file_format" not in metadata

    def test_logging_failure_does_not_break_operation(self):
        """Test that logging failures don't break the bulk operation."""
        # Mock the operation logger to raise an exception
        with patch.object(
            self.batch_processor.operation_logger,
            "log_operation",
            side_effect=Exception("Logging failed"),
        ):
            successful_results = [
                AssignmentResult(
                    principal_name="test.user",
                    permission_set_name="TestAccess",
                    account_name="Test",
                    principal_type="USER",
                    principal_id="user-test",
                    permission_set_arn="arn:aws:sso:::permissionSet/ps-test",
                    account_id="123456789999",
                    status="success",
                    processing_time=1.0,
                )
            ]

            original_assignments = [{"principal_name": "test.user"}]

            # This should not raise an exception
            self.batch_processor._log_bulk_operations(
                successful_results, "assign", original_assignments
            )

            # Verify no operations were logged due to the exception
            operations = self.batch_processor.operation_logger.get_operations()
            assert len(operations) == 0

    @patch("src.awsideman.utils.bulk.batch.console")
    def test_logging_with_console_output(self, mock_console):
        """Test that logging produces appropriate console output."""
        successful_results = [
            AssignmentResult(
                principal_name="test.user",
                permission_set_name="TestAccess",
                account_name="Test",
                principal_type="USER",
                principal_id="user-test",
                permission_set_arn="arn:aws:sso:::permissionSet/ps-test",
                account_id="123456789999",
                status="success",
                processing_time=1.0,
            )
        ]

        original_assignments = [{"principal_name": "test.user"}]

        # Call the logging method
        self.batch_processor._log_bulk_operations(
            successful_results, "assign", original_assignments
        )

        # Verify console output was called
        mock_console.print.assert_called()

        # Check that the logged operation ID was printed
        call_args = mock_console.print.call_args_list
        logged_message = str(call_args[-1])
        assert "Logged assign operation:" in logged_message
