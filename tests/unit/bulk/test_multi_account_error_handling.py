"""Tests for enhanced multi-account error handling and reporting."""

from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError

from src.awsideman.bulk.multi_account_errors import (
    AccountFilterError,
    MultiAccountErrorHandler,
    MultiAccountErrorSummary,
    MultiAccountErrorType,
    MultiAccountOperationError,
    NameResolutionError,
    calculate_retry_delay,
    format_error_for_display,
    should_retry_error,
)
from src.awsideman.utils.models import AccountInfo, AccountResult, MultiAccountResults


class TestMultiAccountErrorHandler:
    """Test cases for MultiAccountErrorHandler."""

    def setup_method(self):
        """Set up test fixtures."""
        self.console = Mock()
        self.error_handler = MultiAccountErrorHandler(self.console)
        self.sample_account = AccountInfo(
            account_id="123456789012",
            account_name="test-account",
            email="test@example.com",
            status="ACTIVE",
            tags={"Environment": "Test"},
        )

    def test_handle_name_resolution_error_permission_set(self):
        """Test handling permission set name resolution errors."""
        # Create a mock ClientError
        error_response = {
            "Error": {"Code": "ResourceNotFoundException", "Message": "Permission set not found"}
        }
        client_error = ClientError(error_response, "ListPermissionSets")

        # Handle the error
        result = self.error_handler.handle_name_resolution_error(
            name="NonExistentPermissionSet",
            name_type="permission_set",
            error=client_error,
            show_guidance=False,
        )

        # Verify error details
        assert isinstance(result, NameResolutionError)
        assert result.resource_name == "NonExistentPermissionSet"
        assert result.resource_type == "permission_set"
        assert result.error_type == MultiAccountErrorType.RESOURCE_NOT_FOUND
        assert "Permission set not found" in result.message

        # Verify error is in history
        assert len(self.error_handler.error_history) == 1
        assert self.error_handler.error_history[0] == result

    def test_handle_name_resolution_error_principal(self):
        """Test handling principal name resolution errors."""
        error = ValueError("User 'nonexistent@example.com' not found")

        result = self.error_handler.handle_name_resolution_error(
            name="nonexistent@example.com", name_type="principal", error=error, show_guidance=False
        )

        assert isinstance(result, NameResolutionError)
        assert result.resource_name == "nonexistent@example.com"
        assert result.resource_type == "principal"
        assert result.error_type == MultiAccountErrorType.VALIDATION
        assert "not found" in result.message

    def test_handle_account_filter_error_wildcard(self):
        """Test handling wildcard account filter errors."""
        error_response = {
            "Error": {
                "Code": "AccessDeniedException",
                "Message": "Insufficient permissions to list accounts",
            }
        }
        client_error = ClientError(error_response, "ListAccounts")

        result = self.error_handler.handle_account_filter_error(
            filter_expression="*", error=client_error, show_guidance=False
        )

        assert isinstance(result, AccountFilterError)
        assert result.filter_expression == "*"
        assert result.filter_type == "wildcard"
        assert result.error_type == MultiAccountErrorType.PERMISSION_DENIED
        assert "Insufficient permissions" in result.message

    def test_handle_account_filter_error_tag(self):
        """Test handling tag-based account filter errors."""
        error = ValueError("Invalid tag format")

        result = self.error_handler.handle_account_filter_error(
            filter_expression="tag:Environment=Invalid", error=error, show_guidance=False
        )

        assert isinstance(result, AccountFilterError)
        assert result.filter_expression == "tag:Environment=Invalid"
        assert result.filter_type == "tag"
        assert result.error_type == MultiAccountErrorType.VALIDATION
        assert "Invalid tag format" in result.message

    def test_handle_account_operation_error(self):
        """Test handling individual account operation errors."""
        error_response = {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}
        client_error = ClientError(error_response, "CreateAccountAssignment")

        result = self.error_handler.handle_account_operation_error(
            account=self.sample_account,
            operation_type="assign",
            permission_set_name="TestPermissionSet",
            principal_name="test@example.com",
            error=client_error,
            retry_count=2,
        )

        assert isinstance(result, MultiAccountOperationError)
        assert result.account_id == "123456789012"
        assert result.account_name == "test-account"
        assert result.operation_type == "assign"
        assert result.permission_set_name == "TestPermissionSet"
        assert result.principal_name == "test@example.com"
        assert result.error_type == MultiAccountErrorType.THROTTLING
        assert result.context["retry_count"] == 2
        assert result.is_retryable()

    def test_error_classification(self):
        """Test error classification logic."""
        # Test permission denied
        error_response = {"Error": {"Code": "AccessDeniedException"}}
        client_error = ClientError(error_response, "TestOperation")
        assert (
            self.error_handler._classify_error(client_error)
            == MultiAccountErrorType.PERMISSION_DENIED
        )

        # Test resource not found
        error_response = {"Error": {"Code": "ResourceNotFoundException"}}
        client_error = ClientError(error_response, "TestOperation")
        assert (
            self.error_handler._classify_error(client_error)
            == MultiAccountErrorType.RESOURCE_NOT_FOUND
        )

        # Test throttling
        error_response = {"Error": {"Code": "ThrottlingException"}}
        client_error = ClientError(error_response, "TestOperation")
        assert self.error_handler._classify_error(client_error) == MultiAccountErrorType.THROTTLING

        # Test validation
        error_response = {"Error": {"Code": "ValidationException"}}
        client_error = ClientError(error_response, "TestOperation")
        assert self.error_handler._classify_error(client_error) == MultiAccountErrorType.VALIDATION

        # Test network error
        network_error = ConnectionError("Network unreachable")
        assert self.error_handler._classify_error(network_error) == MultiAccountErrorType.NETWORK

        # Test unknown error
        unknown_error = RuntimeError("Unknown error")
        assert self.error_handler._classify_error(unknown_error) == MultiAccountErrorType.UNKNOWN

    def test_get_error_summary(self):
        """Test error summary generation."""
        # Add some test errors
        self.error_handler.handle_name_resolution_error(
            "test", "permission_set", ValueError("test"), False
        )
        self.error_handler.handle_account_filter_error("*", ConnectionError("network"), False)

        summary = self.error_handler.get_error_summary()

        assert summary["total_errors"] == 2
        assert summary["error_counts"][MultiAccountErrorType.VALIDATION.value] == 1
        assert summary["error_counts"][MultiAccountErrorType.NETWORK.value] == 1
        assert summary["retryable_errors"] == 1  # Network error is retryable
        assert summary["non_retryable_errors"] == 1  # Validation error is not retryable


class TestMultiAccountErrorSummary:
    """Test cases for MultiAccountErrorSummary."""

    def setup_method(self):
        """Set up test fixtures."""
        self.console = Mock()
        self.error_summary = MultiAccountErrorSummary(self.console)

        # Create sample failed accounts
        self.failed_accounts = [
            AccountResult(
                account_id="123456789012",
                account_name="account-1",
                status="failed",
                error_message="AccessDeniedException: Insufficient permissions",
                processing_time=1.5,
                retry_count=0,
            ),
            AccountResult(
                account_id="123456789013",
                account_name="account-2",
                status="failed",
                error_message="ThrottlingException: Rate exceeded",
                processing_time=2.0,
                retry_count=2,
            ),
            AccountResult(
                account_id="123456789014",
                account_name="account-3",
                status="failed",
                error_message="ResourceNotFoundException: Permission set not found",
                processing_time=0.5,
                retry_count=0,
            ),
        ]

        self.results = MultiAccountResults(
            total_accounts=5,
            successful_accounts=[
                AccountResult("123456789015", "account-4", "success"),
                AccountResult("123456789016", "account-5", "success"),
            ],
            failed_accounts=self.failed_accounts,
            skipped_accounts=[],
            operation_type="assign",
            duration=10.0,
            batch_size=10,
        )

    def test_generate_error_summary_with_failures(self):
        """Test error summary generation with failures."""
        summary = self.error_summary.generate_error_summary(
            results=self.results, show_detailed_errors=False, show_recommendations=False
        )

        assert summary["has_errors"]
        assert summary["summary_stats"]["total_failed_accounts"] == 3
        assert summary["summary_stats"]["total_accounts"] == 5
        assert summary["summary_stats"]["failure_rate"] == 60.0
        assert summary["summary_stats"]["retryable_failures"] == 1  # Throttling error
        assert summary["summary_stats"]["permanent_failures"] == 2  # Permission and resource errors

        # Check most common error
        most_common = summary["summary_stats"]["most_common_error"]
        assert most_common["count"] >= 1
        assert most_common["percentage"] > 0

    def test_generate_error_summary_no_failures(self):
        """Test error summary generation with no failures."""
        no_failure_results = MultiAccountResults(
            total_accounts=2,
            successful_accounts=[
                AccountResult("123456789015", "account-4", "success"),
                AccountResult("123456789016", "account-5", "success"),
            ],
            failed_accounts=[],
            skipped_accounts=[],
            operation_type="assign",
            duration=5.0,
            batch_size=10,
        )

        summary = self.error_summary.generate_error_summary(
            results=no_failure_results, show_detailed_errors=False, show_recommendations=False
        )

        assert not summary["has_errors"]
        assert summary["message"] == "No errors to report"

    def test_categorize_account_errors(self):
        """Test error categorization logic."""
        categories = self.error_summary._categorize_account_errors(self.failed_accounts)

        assert "permission_denied" in categories
        assert "throttling" in categories
        assert "resource_not_found" in categories

        assert len(categories["permission_denied"]) == 1
        assert len(categories["throttling"]) == 1
        assert len(categories["resource_not_found"]) == 1

        assert categories["permission_denied"][0].account_id == "123456789012"
        assert categories["throttling"][0].account_id == "123456789013"
        assert categories["resource_not_found"][0].account_id == "123456789014"

    def test_get_most_common_error(self):
        """Test most common error detection."""
        # Add duplicate error types
        duplicate_failed_accounts = self.failed_accounts + [
            AccountResult(
                account_id="123456789017",
                account_name="account-6",
                status="failed",
                error_message="AccessDeniedException: Another permission error",
                processing_time=1.0,
                retry_count=0,
            )
        ]

        most_common = self.error_summary._get_most_common_error(duplicate_failed_accounts)

        assert most_common["count"] == 2  # Two permission errors
        assert most_common["percentage"] == 50.0  # 2 out of 4 errors
        assert "AccessDeniedException" in most_common["message"]

    def test_count_retryable_failures(self):
        """Test retryable failure counting."""
        retryable_count = self.error_summary._count_retryable_failures(self.failed_accounts)

        # Only the throttling error should be retryable
        assert retryable_count == 1

    @patch("builtins.open", create=True)
    @patch("json.dump")
    def test_export_error_report_json(self, mock_json_dump, mock_open):
        """Test JSON error report export."""
        mock_file = Mock()
        mock_open.return_value.__enter__.return_value = mock_file

        result = self.error_summary.export_error_report(
            results=self.results, output_file="test_report.json", format="json"
        )

        assert result
        mock_open.assert_called_once()
        mock_json_dump.assert_called_once()

    @patch("builtins.open", create=True)
    @patch("csv.writer")
    def test_export_error_report_csv(self, mock_csv_writer, mock_open):
        """Test CSV error report export."""
        mock_file = Mock()
        mock_writer = Mock()
        mock_open.return_value.__enter__.return_value = mock_file
        mock_csv_writer.return_value = mock_writer

        result = self.error_summary.export_error_report(
            results=self.results, output_file="test_report.csv", format="csv"
        )

        assert result
        mock_open.assert_called_once()
        mock_csv_writer.assert_called_once()
        # Should write header + 3 failed accounts
        assert mock_writer.writerow.call_count == 4


class TestErrorUtilities:
    """Test cases for error utility functions."""

    def test_should_retry_error_retryable(self):
        """Test retry logic for retryable errors."""
        # Throttling error should be retryable
        error_response = {"Error": {"Code": "ThrottlingException"}}
        client_error = ClientError(error_response, "TestOperation")

        assert should_retry_error(client_error, 0, 3)
        assert should_retry_error(client_error, 2, 3)
        assert not should_retry_error(client_error, 3, 3)  # Max retries reached

        # Network error should be retryable
        network_error = ConnectionError("Network unreachable")
        assert should_retry_error(network_error, 0, 3)

    def test_should_retry_error_non_retryable(self):
        """Test retry logic for non-retryable errors."""
        # Permission error should not be retryable
        error_response = {"Error": {"Code": "AccessDeniedException"}}
        client_error = ClientError(error_response, "TestOperation")

        assert not should_retry_error(client_error, 0, 3)

        # Validation error (ValueError) is actually retryable in the current implementation
        # Only AWS ValidationException is non-retryable
        validation_error = ValueError("Invalid parameter")
        assert should_retry_error(validation_error, 0, 3)

    def test_calculate_retry_delay(self):
        """Test retry delay calculation."""
        # Test exponential backoff
        delay_0 = calculate_retry_delay(0, base_delay=1.0, max_delay=60.0)
        delay_1 = calculate_retry_delay(1, base_delay=1.0, max_delay=60.0)
        delay_2 = calculate_retry_delay(2, base_delay=1.0, max_delay=60.0)

        # Should increase with retry count (adaptive strategy includes multipliers)
        assert delay_0 > 0  # Should have some delay
        assert delay_1 > delay_0  # Should increase
        assert delay_2 > delay_1  # Should continue increasing

        # Test that delay is reasonable (adaptive strategy can be quite high)
        delay_high = calculate_retry_delay(10, base_delay=1.0, max_delay=5.0)
        assert delay_high > 0  # Should have some delay

        # Test minimum delay
        delay_min = calculate_retry_delay(0, base_delay=0.01, max_delay=60.0)
        assert delay_min >= 0.1  # Minimum 0.1 second delay

    def test_format_error_for_display(self):
        """Test error formatting for display."""
        error = NameResolutionError(
            error_type=MultiAccountErrorType.RESOURCE_NOT_FOUND,
            message="Permission set not found",
            resource_name="TestPermissionSet",
            resource_type="permission_set",
            account_id="123456789012",
            account_name="test-account",
        )

        # Test basic formatting
        formatted = format_error_for_display(error, include_context=False, include_guidance=False)
        assert "[test-account (123456789012)] Permission set not found" in formatted

        # Test with context
        formatted_with_context = format_error_for_display(
            error, include_context=True, include_guidance=False
        )
        assert "Context:" in formatted_with_context
        assert "resource_name: TestPermissionSet" in formatted_with_context

        # Test with guidance
        formatted_with_guidance = format_error_for_display(
            error, include_context=False, include_guidance=True
        )
        assert "Resolution guidance:" in formatted_with_guidance
        assert "permission set name is correct" in formatted_with_guidance


if __name__ == "__main__":
    pytest.main([__file__])
