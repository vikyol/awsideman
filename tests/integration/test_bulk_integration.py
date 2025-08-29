"""Integration tests for bulk operation logging."""

import shutil
import tempfile
from unittest.mock import Mock, patch

from src.awsideman.aws_clients.manager import AWSClientManager
from src.awsideman.bulk.batch import AssignmentResult, BatchProcessor
from src.awsideman.rollback.logger import OperationLogger


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

        # Verify operation was logged by checking for the specific operation
        operations = self.batch_processor.operation_logger.get_operations()

        # Find the operation we just logged by checking the metadata
        logged_operation = None
        for op in operations:
            if (
                op.metadata
                and op.metadata.get("source") == "bulk_operation"
                and op.metadata.get("input_file") == "assignments.csv"
                and op.metadata.get("file_format") == "csv"
            ):
                logged_operation = op
                break

        assert logged_operation is not None, "Bulk operation was not logged"
        assert logged_operation.operation_type.value == "assign"
        assert logged_operation.principal_name == "john.doe"
        assert logged_operation.permission_set_name == "ReadOnlyAccess"
        assert len(logged_operation.account_ids) == 2
        assert "123456789012" in logged_operation.account_ids
        assert "123456789013" in logged_operation.account_ids

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

    @patch("src.awsideman.bulk.batch.console")
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
