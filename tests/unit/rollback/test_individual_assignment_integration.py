"""Integration tests for individual assignment operation logging."""

import shutil
import tempfile
from unittest.mock import Mock, patch

from src.awsideman.commands.assignment import _log_individual_operation
from src.awsideman.rollback.logger import OperationLogger


class TestIndividualAssignmentLogging:
    """Tests for individual assignment operation logging integration."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir)

    @patch("src.awsideman.commands.assignment.OperationLogger")
    def test_log_individual_assign_operation(self, mock_logger_class):
        """Test logging of individual assign operation."""
        # Mock the operation logger
        mock_logger = Mock()
        mock_logger.log_operation.return_value = "test-operation-id"
        mock_logger_class.return_value = mock_logger

        # Call the logging function
        _log_individual_operation(
            operation_type="assign",
            principal_id="user-123",
            principal_type="USER",
            principal_name="john.doe",
            permission_set_arn="arn:aws:sso:::permissionSet/ps-123",
            permission_set_name="ReadOnlyAccess",
            account_id="123456789012",
            success=True,
            request_id="req-123",
        )

        # Verify logger was called correctly
        mock_logger.log_operation.assert_called_once()
        call_args = mock_logger.log_operation.call_args

        assert call_args[1]["operation_type"] == "assign"
        assert call_args[1]["principal_id"] == "user-123"
        assert call_args[1]["principal_type"] == "USER"
        assert call_args[1]["principal_name"] == "john.doe"
        assert call_args[1]["permission_set_arn"] == "arn:aws:sso:::permissionSet/ps-123"
        assert call_args[1]["permission_set_name"] == "ReadOnlyAccess"
        assert call_args[1]["account_ids"] == ["123456789012"]
        assert call_args[1]["account_names"] == ["123456789012"]
        assert len(call_args[1]["results"]) == 1
        assert call_args[1]["results"][0]["account_id"] == "123456789012"
        assert call_args[1]["results"][0]["success"] is True
        assert call_args[1]["metadata"]["source"] == "individual_assignment"
        assert call_args[1]["metadata"]["request_id"] == "req-123"

    @patch("src.awsideman.commands.assignment.OperationLogger")
    def test_log_individual_revoke_operation(self, mock_logger_class):
        """Test logging of individual revoke operation."""
        # Mock the operation logger
        mock_logger = Mock()
        mock_logger.log_operation.return_value = "test-revoke-id"
        mock_logger_class.return_value = mock_logger

        # Call the logging function
        _log_individual_operation(
            operation_type="revoke",
            principal_id="group-456",
            principal_type="GROUP",
            principal_name="developers",
            permission_set_arn="arn:aws:sso:::permissionSet/ps-456",
            permission_set_name="DeveloperAccess",
            account_id="123456789013",
            success=True,
            request_id="req-456",
        )

        # Verify logger was called correctly
        mock_logger.log_operation.assert_called_once()
        call_args = mock_logger.log_operation.call_args

        assert call_args[1]["operation_type"] == "revoke"
        assert call_args[1]["principal_id"] == "group-456"
        assert call_args[1]["principal_type"] == "GROUP"
        assert call_args[1]["principal_name"] == "developers"
        assert call_args[1]["permission_set_name"] == "DeveloperAccess"
        assert call_args[1]["account_ids"] == ["123456789013"]

    @patch("src.awsideman.commands.assignment.OperationLogger")
    def test_log_failed_operation(self, mock_logger_class):
        """Test logging of failed operation."""
        # Mock the operation logger
        mock_logger = Mock()
        mock_logger.log_operation.return_value = "test-failed-id"
        mock_logger_class.return_value = mock_logger

        # Call the logging function with failure
        _log_individual_operation(
            operation_type="assign",
            principal_id="user-789",
            principal_type="USER",
            principal_name="test.user",
            permission_set_arn="arn:aws:sso:::permissionSet/ps-789",
            permission_set_name="TestAccess",
            account_id="123456789014",
            success=False,
            error="Permission denied",
            request_id="req-789",
        )

        # Verify logger was called correctly
        mock_logger.log_operation.assert_called_once()
        call_args = mock_logger.log_operation.call_args

        assert call_args[1]["results"][0]["success"] is False
        assert call_args[1]["results"][0]["error"] == "Permission denied"

    @patch("src.awsideman.commands.assignment.OperationLogger")
    @patch("src.awsideman.commands.assignment.console")
    def test_logging_failure_does_not_break_operation(self, mock_console, mock_logger_class):
        """Test that logging failures don't break the assignment operation."""
        # Mock the operation logger to raise an exception
        mock_logger = Mock()
        mock_logger.log_operation.side_effect = Exception("Logging failed")
        mock_logger_class.return_value = mock_logger

        # This should not raise an exception
        _log_individual_operation(
            operation_type="assign",
            principal_id="user-test",
            principal_type="USER",
            principal_name="test.user",
            permission_set_arn="arn:aws:sso:::permissionSet/ps-test",
            permission_set_name="TestAccess",
            account_id="123456789999",
            success=True,
            request_id="req-test",
        )

        # Verify warning was printed
        mock_console.print.assert_called()
        warning_call = mock_console.print.call_args_list[-1]
        assert "Warning: Failed to log operation" in str(warning_call)

    def test_log_individual_operation_with_real_logger(self):
        """Test logging with real OperationLogger instance."""
        # Create real operation logger with temp directory
        with patch("src.awsideman.commands.assignment.OperationLogger") as mock_logger_class:
            real_logger = OperationLogger(self.temp_dir)
            mock_logger_class.return_value = real_logger

            # Call the logging function
            _log_individual_operation(
                operation_type="assign",
                principal_id="user-real",
                principal_type="USER",
                principal_name="real.user",
                permission_set_arn="arn:aws:sso:::permissionSet/ps-real",
                permission_set_name="RealAccess",
                account_id="123456789015",
                success=True,
                request_id="req-real",
            )

            # Verify operation was logged
            operations = real_logger.get_operations()
            assert len(operations) == 1

            operation = operations[0]
            assert operation.operation_type.value == "assign"
            assert operation.principal_name == "real.user"
            assert operation.permission_set_name == "RealAccess"
            assert operation.account_ids == ["123456789015"]
            assert operation.metadata["source"] == "individual_assignment"
            assert operation.metadata["request_id"] == "req-real"

    @patch("src.awsideman.commands.assignment.OperationLogger")
    @patch("src.awsideman.commands.assignment.console")
    def test_log_operation_success_message(self, mock_console, mock_logger_class):
        """Test that successful logging produces appropriate console output."""
        # Mock the operation logger
        mock_logger = Mock()
        mock_logger.log_operation.return_value = "success-operation-id"
        mock_logger_class.return_value = mock_logger

        # Call the logging function
        _log_individual_operation(
            operation_type="assign",
            principal_id="user-success",
            principal_type="USER",
            principal_name="success.user",
            permission_set_arn="arn:aws:sso:::permissionSet/ps-success",
            permission_set_name="SuccessAccess",
            account_id="123456789016",
            success=True,
            request_id="req-success",
        )

        # Verify success message was printed
        mock_console.print.assert_called()
        success_call = mock_console.print.call_args_list[-1]
        assert "Logged assign operation: success-operation-id" in str(success_call)

    def test_log_operation_without_request_id(self):
        """Test logging operation without request ID."""
        with patch("src.awsideman.commands.assignment.OperationLogger") as mock_logger_class:
            mock_logger = Mock()
            mock_logger.log_operation.return_value = "no-request-id"
            mock_logger_class.return_value = mock_logger

            # Call the logging function without request_id
            _log_individual_operation(
                operation_type="revoke",
                principal_id="user-no-req",
                principal_type="USER",
                principal_name="no.request.user",
                permission_set_arn="arn:aws:sso:::permissionSet/ps-no-req",
                permission_set_name="NoRequestAccess",
                account_id="123456789017",
                success=True,
                request_id=None,
            )

            # Verify logger was called with None request_id
            call_args = mock_logger.log_operation.call_args
            assert call_args[1]["metadata"]["request_id"] is None
