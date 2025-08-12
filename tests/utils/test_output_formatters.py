"""Tests for output formatters for AWS Identity Center status monitoring."""
import csv
import json
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from src.awsideman.utils.output_formatters import (
    CSVFormatter,
    JSONFormatter,
    OutputFormatError,
    OutputFormatterFactory,
    TableFormatter,
    detect_and_format,
    format_status_report,
)
from src.awsideman.utils.status_models import (
    FormattedOutput,
    HealthStatus,
    OrphanedAssignment,
    OrphanedAssignmentStatus,
    OutputFormat,
    PrincipalType,
    ProvisioningOperation,
    ProvisioningOperationStatus,
    ProvisioningStatus,
    ResourceInspectionStatus,
    ResourceStatus,
    ResourceType,
    StatusLevel,
    StatusReport,
    SummaryStatistics,
    SyncMonitorStatus,
    SyncProviderType,
    SyncStatus,
)


class TestOutputFormatterFactory:
    """Test cases for OutputFormatterFactory."""

    def test_create_formatter_json(self):
        """Test creating JSON formatter."""
        formatter = OutputFormatterFactory.create_formatter(OutputFormat.JSON)
        assert isinstance(formatter, JSONFormatter)
        assert formatter.format_type == OutputFormat.JSON

    def test_create_formatter_csv(self):
        """Test creating CSV formatter."""
        formatter = OutputFormatterFactory.create_formatter(OutputFormat.CSV)
        assert isinstance(formatter, CSVFormatter)
        assert formatter.format_type == OutputFormat.CSV

    def test_create_formatter_table(self):
        """Test creating table formatter."""
        formatter = OutputFormatterFactory.create_formatter(OutputFormat.TABLE)
        assert isinstance(formatter, TableFormatter)
        assert formatter.format_type == OutputFormat.TABLE

    def test_create_formatter_unsupported(self):
        """Test creating formatter with unsupported format."""
        with pytest.raises(OutputFormatError, match="Unsupported output format"):
            # Create a mock format that doesn't exist
            OutputFormatterFactory.create_formatter("unsupported")

    def test_get_supported_formats(self):
        """Test getting supported formats."""
        formats = OutputFormatterFactory.get_supported_formats()
        assert OutputFormat.JSON in formats
        assert OutputFormat.CSV in formats
        assert OutputFormat.TABLE in formats
        assert len(formats) == 3

    def test_detect_format_valid(self):
        """Test format detection with valid inputs."""
        assert OutputFormatterFactory.detect_format("json") == OutputFormat.JSON
        assert OutputFormatterFactory.detect_format("JSON") == OutputFormat.JSON
        assert OutputFormatterFactory.detect_format("csv") == OutputFormat.CSV
        assert OutputFormatterFactory.detect_format("CSV") == OutputFormat.CSV
        assert OutputFormatterFactory.detect_format("table") == OutputFormat.TABLE
        assert OutputFormatterFactory.detect_format("TABLE") == OutputFormat.TABLE
        assert OutputFormatterFactory.detect_format("txt") == OutputFormat.TABLE
        assert OutputFormatterFactory.detect_format("text") == OutputFormat.TABLE

    def test_detect_format_invalid(self):
        """Test format detection with invalid inputs."""
        with pytest.raises(OutputFormatError, match="Invalid output format"):
            OutputFormatterFactory.detect_format("invalid")

        with pytest.raises(OutputFormatError, match="Invalid output format"):
            OutputFormatterFactory.detect_format("xml")

    def test_validate_format(self):
        """Test format validation."""
        assert OutputFormatterFactory.validate_format(OutputFormat.JSON) is True
        assert OutputFormatterFactory.validate_format(OutputFormat.CSV) is True
        assert OutputFormatterFactory.validate_format(OutputFormat.TABLE) is True


@pytest.fixture
def sample_status_report():
    """Create a sample status report for testing."""
    timestamp = datetime(2024, 1, 15, 10, 30, 0)

    # Health status
    health_status = HealthStatus(
        timestamp=timestamp,
        status=StatusLevel.HEALTHY,
        message="Identity Center is healthy",
        service_available=True,
        connectivity_status="Connected",
        response_time_ms=150.5,
        last_successful_check=timestamp - timedelta(minutes=5),
    )

    # Provisioning operations
    active_op = ProvisioningOperation(
        operation_id="op-123",
        operation_type="CREATE_USER",
        status=ProvisioningOperationStatus.IN_PROGRESS,
        target_id="user-456",
        target_type="USER",
        created_date=timestamp - timedelta(minutes=10),
        estimated_completion=timestamp + timedelta(minutes=5),
    )

    failed_op = ProvisioningOperation(
        operation_id="op-789",
        operation_type="UPDATE_GROUP",
        status=ProvisioningOperationStatus.FAILED,
        target_id="group-101",
        target_type="GROUP",
        created_date=timestamp - timedelta(hours=1),
        failure_reason="Permission denied",
    )

    provisioning_status = ProvisioningStatus(
        timestamp=timestamp,
        status=StatusLevel.WARNING,
        message="Some operations have failed",
        active_operations=[active_op],
        failed_operations=[failed_op],
        pending_count=2,
        estimated_completion=timestamp + timedelta(minutes=5),
    )

    # Orphaned assignments
    orphaned_assignment = OrphanedAssignment(
        assignment_id="assign-123",
        permission_set_arn="arn:aws:sso:::permissionSet/ps-123",
        permission_set_name="ReadOnlyAccess",
        account_id="123456789012",
        account_name="Production",
        principal_id="user-deleted",
        principal_type=PrincipalType.USER,
        principal_name=None,
        error_message="User not found in identity store",
        created_date=timestamp - timedelta(days=30),
        last_accessed=timestamp - timedelta(days=5),
    )

    orphaned_status = OrphanedAssignmentStatus(
        timestamp=timestamp,
        status=StatusLevel.WARNING,
        message="Found orphaned assignments",
        orphaned_assignments=[orphaned_assignment],
        cleanup_available=True,
        last_cleanup=timestamp - timedelta(days=7),
    )

    # Sync status - use current time to ensure it's not overdue
    current_time = datetime.utcnow()
    sync_provider = SyncStatus(
        provider_name="Active Directory",
        provider_type=SyncProviderType.ACTIVE_DIRECTORY,
        last_sync_time=current_time - timedelta(minutes=30),  # Recent sync to be healthy
        sync_status="SUCCESS",
        next_sync_time=current_time + timedelta(hours=22),
        sync_duration_minutes=15.5,
        objects_synced=1250,
    )

    sync_status = SyncMonitorStatus(
        timestamp=timestamp,
        status=StatusLevel.HEALTHY,
        message="All providers synchronized",
        sync_providers=[sync_provider],
        providers_configured=1,
        providers_healthy=1,
        providers_with_errors=0,
    )

    # Summary statistics
    summary_stats = SummaryStatistics(
        total_users=500,
        total_groups=25,
        total_permission_sets=15,
        total_assignments=1200,
        active_accounts=8,
        last_updated=timestamp,
        user_creation_dates={"user-1": timestamp - timedelta(days=100)},
        group_creation_dates={"group-1": timestamp - timedelta(days=50)},
        permission_set_creation_dates={"ps-1": timestamp - timedelta(days=200)},
    )

    # Resource inspection
    resource_status = ResourceStatus(
        resource_id="user-123",
        resource_name="john.doe@example.com",
        resource_type=ResourceType.USER,
        exists=True,
        status=StatusLevel.HEALTHY,
        last_updated=timestamp - timedelta(days=1),
        configuration={"email": "john.doe@example.com", "enabled": True},
        health_details={"last_login": timestamp - timedelta(hours=6)},
    )

    resource_inspection = ResourceInspectionStatus(
        timestamp=timestamp,
        status=StatusLevel.HEALTHY,
        message="Resource found and healthy",
        target_resource=resource_status,
        similar_resources=["jane.doe@example.com", "john.smith@example.com"],
        inspection_type=ResourceType.USER,
    )

    return StatusReport(
        timestamp=timestamp,
        overall_health=health_status,
        provisioning_status=provisioning_status,
        orphaned_assignment_status=orphaned_status,
        sync_status=sync_status,
        summary_statistics=summary_stats,
        resource_inspections=[resource_inspection],
        check_duration_seconds=2.5,
    )


class TestJSONFormatter:
    """Test cases for JSONFormatter."""

    def test_format_complete_report(self, sample_status_report):
        """Test formatting a complete status report as JSON."""
        formatter = JSONFormatter()
        result = formatter.format(sample_status_report)

        assert isinstance(result, FormattedOutput)
        assert result.format_type == OutputFormat.JSON
        assert result.metadata["content_type"] == "application/json"
        assert result.metadata["encoding"] == "utf-8"
        assert "size_bytes" in result.metadata
        assert result.metadata["structure_version"] == "1.0"

        # Verify JSON is valid
        data = json.loads(result.content)
        assert "timestamp" in data
        assert "overall_status" in data
        assert "health" in data
        assert "provisioning" in data
        assert "orphaned_assignments" in data
        assert "sync" in data
        assert "summary_statistics" in data
        assert "resource_inspections" in data
        assert "component_statuses" in data

    def test_format_json_structure(self, sample_status_report):
        """Test JSON structure and data integrity."""
        formatter = JSONFormatter()
        result = formatter.format(sample_status_report)
        data = json.loads(result.content)

        # Check overall status
        assert data["overall_status"]["level"] == "Warning"
        assert data["overall_status"]["has_issues"] is True
        assert data["overall_status"]["issue_count"] > 0

        # Check health status
        health = data["health"]
        assert health["status"] == "Healthy"
        assert health["service_available"] is True
        assert health["response_time_ms"] == 150.5

        # Check provisioning status
        provisioning = data["provisioning"]
        assert provisioning["status"] == "Warning"
        assert len(provisioning["active_operations"]) == 1
        assert len(provisioning["failed_operations"]) == 1
        assert provisioning["total_operations"] == 2

        # Check orphaned assignments
        orphaned = data["orphaned_assignments"]
        assert orphaned["orphaned_count"] == 1
        assert len(orphaned["orphaned_assignments"]) == 1
        assert orphaned["orphaned_assignments"][0]["principal_type"] == "USER"

        # Check sync status
        sync = data["sync"]
        assert sync["providers_configured"] == 1
        assert sync["providers_healthy"] == 1
        assert len(sync["sync_providers"]) == 1

        # Check summary statistics
        stats = data["summary_statistics"]
        assert stats["total_users"] == 500
        assert stats["total_groups"] == 25
        assert stats["total_permission_sets"] == 15
        assert stats["total_assignments"] == 1200
        assert stats["active_accounts"] == 8

    def test_format_minimal_report(self):
        """Test formatting a minimal status report."""
        timestamp = datetime(2024, 1, 15, 10, 30, 0)

        health_status = HealthStatus(
            timestamp=timestamp,
            status=StatusLevel.HEALTHY,
            message="Healthy",
            service_available=True,
            connectivity_status="Connected",
        )

        provisioning_status = ProvisioningStatus(
            timestamp=timestamp,
            status=StatusLevel.HEALTHY,
            message="No operations",
            pending_count=0,
        )

        orphaned_status = OrphanedAssignmentStatus(
            timestamp=timestamp,
            status=StatusLevel.HEALTHY,
            message="No orphaned assignments",
            cleanup_available=True,
        )

        sync_status = SyncMonitorStatus(
            timestamp=timestamp,
            status=StatusLevel.HEALTHY,
            message="No providers configured",
            providers_configured=0,
            providers_healthy=0,
            providers_with_errors=0,
        )

        summary_stats = SummaryStatistics(
            total_users=0,
            total_groups=0,
            total_permission_sets=0,
            total_assignments=0,
            active_accounts=0,
            last_updated=timestamp,
        )

        minimal_report = StatusReport(
            timestamp=timestamp,
            overall_health=health_status,
            provisioning_status=provisioning_status,
            orphaned_assignment_status=orphaned_status,
            sync_status=sync_status,
            summary_statistics=summary_stats,
            check_duration_seconds=0.5,
        )

        formatter = JSONFormatter()
        result = formatter.format(minimal_report)

        assert isinstance(result, FormattedOutput)
        data = json.loads(result.content)
        assert data["overall_status"]["level"] == "Healthy"
        assert data["overall_status"]["has_issues"] is False
        assert data["summary_statistics"]["total_users"] == 0

    def test_format_error_handling(self):
        """Test JSON formatter error handling."""
        formatter = JSONFormatter()

        # Test with invalid data that might cause serialization issues
        with pytest.raises(OutputFormatError, match="Failed to format JSON output"):
            # Create a mock report that will cause serialization issues
            mock_report = Mock()
            mock_report.timestamp = "invalid_datetime"  # This should cause issues
            formatter.format(mock_report)


class TestCSVFormatter:
    """Test cases for CSVFormatter."""

    def test_format_complete_report(self, sample_status_report):
        """Test formatting a complete status report as CSV."""
        formatter = CSVFormatter()
        result = formatter.format(sample_status_report)

        assert isinstance(result, FormattedOutput)
        assert result.format_type == OutputFormat.CSV
        assert result.metadata["content_type"] == "text/csv"
        assert result.metadata["encoding"] == "utf-8"
        assert "size_bytes" in result.metadata
        assert "sections" in result.metadata

        # Verify CSV structure
        lines = result.content.strip().split("\n")
        assert len(lines) > 10  # Should have multiple sections

        # Check for section headers
        content = result.content
        assert "# Status Summary" in content
        assert "# Health Status" in content
        assert "# Provisioning Operations" in content
        assert "# Orphaned Assignments" in content
        assert "# Sync Providers" in content
        assert "# Summary Statistics" in content

    def test_csv_data_integrity(self, sample_status_report):
        """Test CSV data integrity and parsing."""
        formatter = CSVFormatter()
        result = formatter.format(sample_status_report)

        # Parse CSV content to verify structure
        lines = result.content.strip().split("\n")
        csv_reader = csv.reader(lines)
        rows = list(csv_reader)

        # Find and verify summary section
        summary_idx = None
        for i, row in enumerate(rows):
            if row and row[0] == "# Status Summary":
                summary_idx = i
                break

        assert summary_idx is not None
        assert rows[summary_idx + 1][0] == "Timestamp"  # Header row
        assert len(rows[summary_idx + 2]) == 5  # Data row with 5 columns

        # Verify timestamp format
        timestamp_value = rows[summary_idx + 2][0]
        assert "2024-01-15T10:30:00" in timestamp_value

    def test_format_minimal_report(self):
        """Test formatting a minimal status report as CSV."""
        timestamp = datetime(2024, 1, 15, 10, 30, 0)

        health_status = HealthStatus(
            timestamp=timestamp,
            status=StatusLevel.HEALTHY,
            message="Healthy",
            service_available=True,
            connectivity_status="Connected",
        )

        provisioning_status = ProvisioningStatus(
            timestamp=timestamp,
            status=StatusLevel.HEALTHY,
            message="No operations",
            pending_count=0,
        )

        orphaned_status = OrphanedAssignmentStatus(
            timestamp=timestamp,
            status=StatusLevel.HEALTHY,
            message="No orphaned assignments",
            cleanup_available=True,
        )

        sync_status = SyncMonitorStatus(
            timestamp=timestamp,
            status=StatusLevel.HEALTHY,
            message="No providers configured",
            providers_configured=0,
            providers_healthy=0,
            providers_with_errors=0,
        )

        summary_stats = SummaryStatistics(
            total_users=10,
            total_groups=2,
            total_permission_sets=3,
            total_assignments=25,
            active_accounts=2,
            last_updated=timestamp,
        )

        minimal_report = StatusReport(
            timestamp=timestamp,
            overall_health=health_status,
            provisioning_status=provisioning_status,
            orphaned_assignment_status=orphaned_status,
            sync_status=sync_status,
            summary_statistics=summary_stats,
            check_duration_seconds=0.5,
        )

        formatter = CSVFormatter()
        result = formatter.format(minimal_report)

        # Should only have basic sections (no provisioning, orphaned, sync)
        expected_sections = ["summary", "health", "statistics"]
        assert result.metadata["sections"] == expected_sections

        # Should not contain optional sections
        content = result.content
        assert "# Provisioning Operations" not in content
        assert "# Orphaned Assignments" not in content
        assert "# Sync Providers" not in content

    def test_csv_special_characters(self):
        """Test CSV handling of special characters and commas."""
        timestamp = datetime(2024, 1, 15, 10, 30, 0)

        # Create assignment with special characters
        orphaned_assignment = OrphanedAssignment(
            assignment_id="assign-123",
            permission_set_arn="arn:aws:sso:::permissionSet/ps-123",
            permission_set_name="Read,Write Access",  # Contains comma
            account_id="123456789012",
            account_name='Test "Production" Account',  # Contains quotes
            principal_id="user-deleted",
            principal_type=PrincipalType.USER,
            principal_name="John, Doe",  # Contains comma
            error_message='User not found: "special case"',  # Contains quotes
            created_date=timestamp - timedelta(days=30),
        )

        orphaned_status = OrphanedAssignmentStatus(
            timestamp=timestamp,
            status=StatusLevel.WARNING,
            message="Found orphaned assignments",
            orphaned_assignments=[orphaned_assignment],
            cleanup_available=True,
        )

        # Create minimal report with special characters
        health_status = HealthStatus(
            timestamp=timestamp,
            status=StatusLevel.HEALTHY,
            message="Healthy",
            service_available=True,
            connectivity_status="Connected",
        )

        provisioning_status = ProvisioningStatus(
            timestamp=timestamp,
            status=StatusLevel.HEALTHY,
            message="No operations",
            pending_count=0,
        )

        sync_status = SyncMonitorStatus(
            timestamp=timestamp,
            status=StatusLevel.HEALTHY,
            message="No providers configured",
            providers_configured=0,
            providers_healthy=0,
            providers_with_errors=0,
        )

        summary_stats = SummaryStatistics(
            total_users=0,
            total_groups=0,
            total_permission_sets=0,
            total_assignments=0,
            active_accounts=0,
            last_updated=timestamp,
        )

        report = StatusReport(
            timestamp=timestamp,
            overall_health=health_status,
            provisioning_status=provisioning_status,
            orphaned_assignment_status=orphaned_status,
            sync_status=sync_status,
            summary_statistics=summary_stats,
            check_duration_seconds=0.5,
        )

        formatter = CSVFormatter()
        result = formatter.format(report)

        # Verify CSV can be parsed despite special characters
        lines = result.content.strip().split("\n")
        csv_reader = csv.reader(lines)
        rows = list(csv_reader)

        # Should be able to parse without errors
        assert len(rows) > 0

        # Find orphaned assignments section and verify data
        orphaned_section_found = False
        for i, row in enumerate(rows):
            if row and row[0] == "# Orphaned Assignments":
                # Check data row (should be 2 rows after header)
                data_row = rows[i + 2]
                assert "Read,Write Access" in data_row[1]  # Permission set name
                assert "John, Doe" in data_row[6]  # Principal name
                orphaned_section_found = True
                break

        assert orphaned_section_found


class TestTableFormatter:
    """Test cases for TableFormatter."""

    def test_format_complete_report(self, sample_status_report):
        """Test formatting a complete status report as table."""
        formatter = TableFormatter()
        result = formatter.format(sample_status_report)

        assert isinstance(result, FormattedOutput)
        assert result.format_type == OutputFormat.TABLE
        assert result.metadata["content_type"] == "text/plain"
        assert result.metadata["encoding"] == "utf-8"
        assert "size_bytes" in result.metadata
        assert "line_count" in result.metadata
        assert "sections" in result.metadata

        # Verify table structure
        content = result.content
        assert "AWS Identity Center Status Report" in content
        assert "=" * 80 in content
        assert "Overall Status:" in content
        assert "Component Status:" in content
        assert "Health Status:" in content
        assert "Summary Statistics:" in content

    def test_table_status_indicators(self, sample_status_report):
        """Test status indicators in table format."""
        formatter = TableFormatter()
        result = formatter.format(sample_status_report)

        content = result.content

        # Should contain status indicators
        assert "✅" in content  # Healthy indicator
        assert "⚠️" in content  # Warning indicator

        # Check specific status lines
        lines = content.split("\n")
        overall_status_line = None
        for line in lines:
            if "Overall Status:" in line:
                overall_status_line = line
                break

        assert overall_status_line is not None
        assert "Warning" in overall_status_line

    def test_table_sections(self, sample_status_report):
        """Test table sections and content."""
        formatter = TableFormatter()
        result = formatter.format(sample_status_report)

        content = result.content

        # Check for all expected sections
        assert "Health Status:" in content
        assert "Provisioning Operations:" in content
        assert "Orphaned Assignments:" in content
        assert "Synchronization Status:" in content
        assert "Summary Statistics:" in content
        assert "Resource Inspections:" in content

        # Check specific data points
        assert "Total Operations: 2" in content
        assert "Total Orphaned: 1" in content
        assert "Users: 500" in content
        assert "Groups: 25" in content

    def test_format_minimal_report(self):
        """Test formatting a minimal status report as table."""
        timestamp = datetime(2024, 1, 15, 10, 30, 0)

        health_status = HealthStatus(
            timestamp=timestamp,
            status=StatusLevel.HEALTHY,
            message="All systems healthy",
            service_available=True,
            connectivity_status="Connected",
            response_time_ms=100.0,
        )

        provisioning_status = ProvisioningStatus(
            timestamp=timestamp,
            status=StatusLevel.HEALTHY,
            message="No active operations",
            pending_count=0,
        )

        orphaned_status = OrphanedAssignmentStatus(
            timestamp=timestamp,
            status=StatusLevel.HEALTHY,
            message="No orphaned assignments found",
            cleanup_available=True,
        )

        sync_status = SyncMonitorStatus(
            timestamp=timestamp,
            status=StatusLevel.HEALTHY,
            message="No external providers configured",
            providers_configured=0,
            providers_healthy=0,
            providers_with_errors=0,
        )

        summary_stats = SummaryStatistics(
            total_users=100,
            total_groups=5,
            total_permission_sets=8,
            total_assignments=200,
            active_accounts=3,
            last_updated=timestamp,
        )

        minimal_report = StatusReport(
            timestamp=timestamp,
            overall_health=health_status,
            provisioning_status=provisioning_status,
            orphaned_assignment_status=orphaned_status,
            sync_status=sync_status,
            summary_statistics=summary_stats,
            check_duration_seconds=1.2,
        )

        formatter = TableFormatter()
        result = formatter.format(minimal_report)

        content = result.content

        # Should show healthy status
        assert "Overall Status: ✅ Healthy" in content
        assert "All systems healthy" in content

        # Should not show optional sections with no data
        assert "Recent Failed Operations:" not in content
        assert "Sample Orphaned Assignments:" not in content
        assert "Provider Details:" not in content

        # Should show basic statistics
        assert "Users: 100" in content
        assert "Groups: 5" in content
        assert "Permission Sets: 8" in content

    def test_table_formatting_edge_cases(self):
        """Test table formatting with edge cases."""
        timestamp = datetime(2024, 1, 15, 10, 30, 0)

        # Health status with connection failure
        health_status = HealthStatus(
            timestamp=timestamp,
            status=StatusLevel.CONNECTION_FAILED,
            message="Cannot connect to Identity Center",
            service_available=False,
            connectivity_status="Failed",
            errors=["Connection timeout", "Invalid credentials"],
        )

        provisioning_status = ProvisioningStatus(
            timestamp=timestamp,
            status=StatusLevel.CRITICAL,
            message="Multiple failures detected",
            pending_count=0,
        )

        orphaned_status = OrphanedAssignmentStatus(
            timestamp=timestamp,
            status=StatusLevel.HEALTHY,
            message="No orphaned assignments",
            cleanup_available=True,
        )

        sync_status = SyncMonitorStatus(
            timestamp=timestamp,
            status=StatusLevel.HEALTHY,
            message="No providers configured",
            providers_configured=0,
            providers_healthy=0,
            providers_with_errors=0,
        )

        summary_stats = SummaryStatistics(
            total_users=0,
            total_groups=0,
            total_permission_sets=0,
            total_assignments=0,
            active_accounts=0,
            last_updated=timestamp,
        )

        edge_case_report = StatusReport(
            timestamp=timestamp,
            overall_health=health_status,
            provisioning_status=provisioning_status,
            orphaned_assignment_status=orphaned_status,
            sync_status=sync_status,
            summary_statistics=summary_stats,
            check_duration_seconds=30.0,
        )

        formatter = TableFormatter()
        result = formatter.format(edge_case_report)

        content = result.content

        # Should show connection failed status
        assert "🔌" in content  # Connection failed indicator
        assert "Connection Failed" in content
        assert "Cannot connect to Identity Center" in content

        # Should show errors
        assert "Errors:" in content
        assert "Connection timeout" in content
        assert "Invalid credentials" in content


class TestConvenienceFunctions:
    """Test cases for convenience functions."""

    def test_format_status_report(self, sample_status_report):
        """Test format_status_report convenience function."""
        # Test JSON format
        result = format_status_report(sample_status_report, OutputFormat.JSON)
        assert result.format_type == OutputFormat.JSON
        assert result.metadata["content_type"] == "application/json"

        # Test CSV format
        result = format_status_report(sample_status_report, OutputFormat.CSV)
        assert result.format_type == OutputFormat.CSV
        assert result.metadata["content_type"] == "text/csv"

        # Test table format
        result = format_status_report(sample_status_report, OutputFormat.TABLE)
        assert result.format_type == OutputFormat.TABLE
        assert result.metadata["content_type"] == "text/plain"

    def test_detect_and_format(self, sample_status_report):
        """Test detect_and_format convenience function."""
        # Test with various format strings
        result = detect_and_format(sample_status_report, "json")
        assert result.format_type == OutputFormat.JSON

        result = detect_and_format(sample_status_report, "CSV")
        assert result.format_type == OutputFormat.CSV

        result = detect_and_format(sample_status_report, "table")
        assert result.format_type == OutputFormat.TABLE

        result = detect_and_format(sample_status_report, "txt")
        assert result.format_type == OutputFormat.TABLE

    def test_detect_and_format_invalid(self, sample_status_report):
        """Test detect_and_format with invalid format string."""
        with pytest.raises(OutputFormatError, match="Invalid output format"):
            detect_and_format(sample_status_report, "invalid")


class TestDataIntegrity:
    """Test cases for data integrity across all formatters."""

    def test_datetime_serialization(self, sample_status_report):
        """Test datetime serialization consistency across formats."""
        timestamp_str = "2024-01-15T10:30:00"

        # JSON format
        json_result = format_status_report(sample_status_report, OutputFormat.JSON)
        json_data = json.loads(json_result.content)
        assert timestamp_str in json_data["timestamp"]

        # CSV format
        csv_result = format_status_report(sample_status_report, OutputFormat.CSV)
        assert timestamp_str in csv_result.content

        # Table format
        table_result = format_status_report(sample_status_report, OutputFormat.TABLE)
        assert timestamp_str in table_result.content

    def test_status_level_consistency(self, sample_status_report):
        """Test status level representation consistency."""
        # JSON format
        json_result = format_status_report(sample_status_report, OutputFormat.JSON)
        json_data = json.loads(json_result.content)
        assert json_data["overall_status"]["level"] == "Warning"
        assert json_data["health"]["status"] == "Healthy"

        # CSV format
        csv_result = format_status_report(sample_status_report, OutputFormat.CSV)
        assert "Warning" in csv_result.content
        assert "Healthy" in csv_result.content

        # Table format
        table_result = format_status_report(sample_status_report, OutputFormat.TABLE)
        assert "Warning" in table_result.content
        assert "Healthy" in table_result.content

    def test_numeric_data_consistency(self, sample_status_report):
        """Test numeric data consistency across formats."""
        # JSON format
        json_result = format_status_report(sample_status_report, OutputFormat.JSON)
        json_data = json.loads(json_result.content)
        assert json_data["summary_statistics"]["total_users"] == 500
        assert json_data["summary_statistics"]["total_groups"] == 25

        # CSV format
        csv_result = format_status_report(sample_status_report, OutputFormat.CSV)
        assert "500" in csv_result.content  # Total users
        assert "25" in csv_result.content  # Total groups

        # Table format
        table_result = format_status_report(sample_status_report, OutputFormat.TABLE)
        assert "Users: 500" in table_result.content
        assert "Groups: 25" in table_result.content

    def test_error_handling_consistency(self):
        """Test error handling consistency across formatters."""
        formatters = [JSONFormatter(), CSVFormatter(), TableFormatter()]

        for formatter in formatters:
            with pytest.raises(OutputFormatError):
                # Test with invalid input that should cause formatting errors
                mock_report = Mock()
                mock_report.timestamp = None  # This should cause issues
                formatter.format(mock_report)


class TestFormattedOutputModel:
    """Test cases for FormattedOutput model."""

    def test_formatted_output_creation(self):
        """Test FormattedOutput model creation and methods."""
        timestamp = datetime(2024, 1, 15, 10, 30, 0)

        output = FormattedOutput(
            format_type=OutputFormat.JSON,
            content='{"test": "data"}',
            metadata={"size": 100},
            generated_at=timestamp,
        )

        assert output.format_type == OutputFormat.JSON
        assert output.content == '{"test": "data"}'
        assert output.metadata["size"] == 100
        assert output.generated_at == timestamp

        # Test methods
        assert output.get_content_length() == 16  # Correct length of '{"test": "data"}'
        assert output.is_json_format() is True
        assert output.is_csv_format() is False
        assert output.is_table_format() is False

    def test_formatted_output_format_detection(self):
        """Test format detection methods."""
        json_output = FormattedOutput(format_type=OutputFormat.JSON, content="{}", metadata={})

        csv_output = FormattedOutput(
            format_type=OutputFormat.CSV, content="header,value", metadata={}
        )

        table_output = FormattedOutput(
            format_type=OutputFormat.TABLE, content="Table content", metadata={}
        )

        # JSON format
        assert json_output.is_json_format() is True
        assert json_output.is_csv_format() is False
        assert json_output.is_table_format() is False

        # CSV format
        assert csv_output.is_json_format() is False
        assert csv_output.is_csv_format() is True
        assert csv_output.is_table_format() is False

        # Table format
        assert table_output.is_json_format() is False
        assert table_output.is_csv_format() is False
        assert table_output.is_table_format() is True
