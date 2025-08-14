"""Tests for bulk operations reporting components."""

import time
from pathlib import Path
from unittest.mock import Mock, mock_open, patch

import pytest
from rich.console import Console

from src.awsideman.bulk.batch import AssignmentResult, BulkOperationResults
from src.awsideman.bulk.reporting import ReportGenerator


class TestReportGenerator:
    """Test cases for ReportGenerator class."""

    @pytest.fixture
    def mock_console(self):
        """Create a mock console for testing."""
        return Mock(spec=Console)

    @pytest.fixture
    def report_generator(self, mock_console):
        """Create a ReportGenerator instance for testing."""
        return ReportGenerator(mock_console)

    @pytest.fixture
    def sample_results(self):
        """Create sample bulk operation results for testing."""
        start_time = time.time()
        end_time = start_time + 10.5

        successful_result = AssignmentResult(
            principal_name="john.doe",
            permission_set_name="ReadOnlyAccess",
            account_name="Production",
            principal_type="USER",
            status="success",
            principal_id="user-123",
            permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-456",
            account_id="123456789012",
            processing_time=0.5,
            timestamp=start_time,
        )

        failed_result = AssignmentResult(
            principal_name="jane.smith",
            permission_set_name="AdminAccess",
            account_name="Development",
            principal_type="USER",
            status="failed",
            error_message="Permission denied: Insufficient privileges",
            processing_time=0.3,
            timestamp=start_time + 1,
        )

        skipped_result = AssignmentResult(
            principal_name="test.user",
            permission_set_name="TestAccess",
            account_name="Staging",
            principal_type="USER",
            status="skipped",
            error_message="Assignment already exists",
            processing_time=0.1,
            timestamp=start_time + 2,
        )

        results = BulkOperationResults(
            total_processed=3,
            operation_type="assign",
            duration=10.5,
            batch_size=10,
            continue_on_error=True,
            start_time=start_time,
            end_time=end_time,
        )

        results.successful = [successful_result]
        results.failed = [failed_result]
        results.skipped = [skipped_result]

        return results

    def test_init(self, mock_console):
        """Test ReportGenerator initialization."""
        generator = ReportGenerator(mock_console)
        assert generator.console == mock_console

    def test_generate_summary_report(self, report_generator, mock_console, sample_results):
        """Test summary report generation."""
        report_generator.generate_summary_report(sample_results, "assign")

        # Verify console.print was called multiple times for different sections
        # Should be called for: empty line, summary panel, empty line, status panels, empty line, timing panel
        assert mock_console.print.call_count >= 3

    def test_generate_detailed_report_all_types(
        self, report_generator, mock_console, sample_results
    ):
        """Test detailed report generation with all result types."""
        report_generator.generate_detailed_report(
            sample_results, show_successful=True, show_failed=True, show_skipped=True
        )

        # Verify console.print was called for the detailed table
        assert mock_console.print.call_count >= 2

    def test_generate_detailed_report_successful_only(
        self, report_generator, mock_console, sample_results
    ):
        """Test detailed report generation with successful results only."""
        report_generator.generate_detailed_report(
            sample_results, show_successful=True, show_failed=False, show_skipped=False
        )

        # Should still generate a report with successful results
        assert mock_console.print.call_count >= 2

    def test_generate_detailed_report_no_results(self, report_generator, mock_console):
        """Test detailed report generation with no results to show."""
        empty_results = BulkOperationResults(
            total_processed=0, operation_type="assign", duration=0.0
        )

        report_generator.generate_detailed_report(
            empty_results, show_successful=False, show_failed=False, show_skipped=False
        )

        # Should print a message about no results
        mock_console.print.assert_called_once()
        call_args = mock_console.print.call_args[0][0]
        assert "No detailed results to display" in str(call_args)

    def test_generate_error_summary_with_errors(
        self, report_generator, mock_console, sample_results
    ):
        """Test error summary generation with errors present."""
        report_generator.generate_error_summary(sample_results)

        # Should generate error summary table
        assert mock_console.print.call_count >= 2

    def test_generate_error_summary_no_errors(self, report_generator, mock_console):
        """Test error summary generation with no errors."""
        no_error_results = BulkOperationResults(
            total_processed=1, operation_type="assign", duration=1.0
        )

        successful_result = AssignmentResult(
            principal_name="john.doe",
            permission_set_name="ReadOnlyAccess",
            account_name="Production",
            principal_type="USER",
            status="success",
        )
        no_error_results.successful = [successful_result]

        report_generator.generate_error_summary(no_error_results)

        # Should print success message
        mock_console.print.assert_called_once()
        call_args = mock_console.print.call_args[0][0]
        assert "No errors encountered" in str(call_args)

    def test_generate_performance_report(self, report_generator, mock_console, sample_results):
        """Test performance report generation."""
        report_generator.generate_performance_report(sample_results)

        # Should generate performance metrics
        assert mock_console.print.call_count >= 2

    def test_generate_performance_report_no_data(self, report_generator, mock_console):
        """Test performance report generation with no performance data."""
        no_perf_results = BulkOperationResults(
            total_processed=0, operation_type="assign", duration=0.0
        )

        report_generator.generate_performance_report(no_perf_results)

        # Should print message about no data
        mock_console.print.assert_called_once()
        call_args = mock_console.print.call_args[0][0]
        assert "No performance data available" in str(call_args)

    def test_format_duration_milliseconds(self, report_generator):
        """Test duration formatting for milliseconds."""
        result = report_generator._format_duration(0.5)
        assert result == "500ms"

    def test_format_duration_seconds(self, report_generator):
        """Test duration formatting for seconds."""
        result = report_generator._format_duration(5.25)
        assert result == "5.25s"

    def test_format_duration_minutes(self, report_generator):
        """Test duration formatting for minutes."""
        result = report_generator._format_duration(125.5)
        assert result == "2m 5.5s"

    def test_format_duration_hours(self, report_generator):
        """Test duration formatting for hours."""
        result = report_generator._format_duration(7325.0)
        assert result == "2h 2m 5.0s"

    def test_format_duration_negative(self, report_generator):
        """Test duration formatting for negative values."""
        result = report_generator._format_duration(-1.0)
        assert result == "N/A"

    @patch("builtins.open", new_callable=mock_open)
    def test_save_detailed_report_to_file_success(
        self, mock_file, report_generator, mock_console, sample_results
    ):
        """Test saving detailed report to file successfully."""
        output_file = Path("/tmp/test_report.txt")

        report_generator._save_detailed_report_to_file(sample_results, output_file)

        # Verify file was opened for writing
        mock_file.assert_called_once_with(output_file, "w", encoding="utf-8")

        # Verify content was written
        handle = mock_file()
        assert handle.write.call_count > 0

        # Verify success message was printed
        mock_console.print.assert_called_once()
        call_args = mock_console.print.call_args[0][0]
        assert "Detailed report saved to" in str(call_args)

    @patch("builtins.open", side_effect=IOError("Permission denied"))
    def test_save_detailed_report_to_file_error(
        self, mock_file, report_generator, mock_console, sample_results
    ):
        """Test saving detailed report to file with error."""
        output_file = Path("/tmp/test_report.txt")

        report_generator._save_detailed_report_to_file(sample_results, output_file)

        # Verify error message was printed
        mock_console.print.assert_called_once()
        call_args = mock_console.print.call_args[0][0]
        assert "Failed to save detailed report" in str(call_args)

    def test_generate_detailed_report_with_file_output(
        self, report_generator, mock_console, sample_results
    ):
        """Test detailed report generation with file output."""
        with patch.object(report_generator, "_save_detailed_report_to_file") as mock_save:
            output_file = Path("/tmp/test_report.txt")

            report_generator.generate_detailed_report(sample_results, output_file=output_file)

            # Verify file save was called
            mock_save.assert_called_once_with(sample_results, output_file)

    def test_bulk_operation_results_properties(self, sample_results):
        """Test BulkOperationResults properties and methods."""
        # Test property calculations
        assert sample_results.success_count == 1
        assert sample_results.failure_count == 1
        assert sample_results.skip_count == 1
        assert sample_results.success_rate == pytest.approx(33.33, rel=1e-2)

        # Test get_all_results method
        all_results = sample_results.get_all_results()
        assert len(all_results) == 3
        assert all_results[0].status == "success"
        assert all_results[1].status == "failed"
        assert all_results[2].status == "skipped"

    def test_bulk_operation_results_add_result(self):
        """Test adding results to BulkOperationResults."""
        results = BulkOperationResults(total_processed=0, operation_type="assign", duration=0.0)

        # Test adding successful result
        success_result = AssignmentResult(
            principal_name="test",
            permission_set_name="test",
            account_name="test",
            principal_type="USER",
            status="success",
        )
        results.add_result(success_result)
        assert len(results.successful) == 1

        # Test adding failed result
        failed_result = AssignmentResult(
            principal_name="test",
            permission_set_name="test",
            account_name="test",
            principal_type="USER",
            status="failed",
        )
        results.add_result(failed_result)
        assert len(results.failed) == 1

        # Test adding skipped result
        skipped_result = AssignmentResult(
            principal_name="test",
            permission_set_name="test",
            account_name="test",
            principal_type="USER",
            status="skipped",
        )
        results.add_result(skipped_result)
        assert len(results.skipped) == 1

        # Test invalid status
        with pytest.raises(ValueError, match="Invalid status"):
            invalid_result = AssignmentResult(
                principal_name="test",
                permission_set_name="test",
                account_name="test",
                principal_type="USER",
                status="invalid",
            )
            results.add_result(invalid_result)

    def test_assignment_result_post_init(self):
        """Test AssignmentResult __post_init__ method."""
        # Test with timestamp provided
        custom_timestamp = time.time()
        result = AssignmentResult(
            principal_name="test",
            permission_set_name="test",
            account_name="test",
            principal_type="USER",
            status="success",
            timestamp=custom_timestamp,
        )
        assert result.timestamp == custom_timestamp

        # Test with no timestamp (should be set automatically)
        result_no_timestamp = AssignmentResult(
            principal_name="test",
            permission_set_name="test",
            account_name="test",
            principal_type="USER",
            status="success",
        )
        assert result_no_timestamp.timestamp is not None
        assert isinstance(result_no_timestamp.timestamp, float)
