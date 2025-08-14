"""Output formatters for AWS Identity Center status monitoring."""

import csv
import json
from datetime import datetime
from io import StringIO
from typing import Any, Dict, List, Optional

from .status_models import (
    FormattedOutput,
    HealthStatus,
    OrphanedAssignment,
    OrphanedAssignmentStatus,
    OutputFormat,
    ProvisioningOperation,
    ProvisioningStatus,
    ResourceInspectionStatus,
    StatusLevel,
    StatusReport,
    SummaryStatistics,
    SyncMonitorStatus,
    SyncStatus,
)


class OutputFormatError(Exception):
    """Exception raised for output formatting errors."""

    pass


class BaseFormatter:
    """Base class for all output formatters."""

    def __init__(self):
        self.format_type = None

    def format(self, status_report: StatusReport) -> FormattedOutput:
        """Format a status report. Must be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement format method")

    def _serialize_datetime(self, dt: Optional[datetime]) -> Optional[str]:
        """Serialize datetime to ISO format string."""
        if dt is None:
            return None
        return dt.isoformat()

    def _serialize_status_level(self, status: StatusLevel) -> str:
        """Serialize status level to string."""
        return status.value


class JSONFormatter(BaseFormatter):
    """Formatter for JSON output suitable for API consumption and monitoring systems."""

    def __init__(self):
        super().__init__()
        self.format_type = OutputFormat.JSON

    def format(self, status_report: StatusReport) -> FormattedOutput:
        """Format status report as structured JSON."""
        try:
            # Convert the status report to a dictionary with proper serialization
            data = self._serialize_status_report(status_report)

            # Format as JSON with proper indentation
            content = json.dumps(data, indent=2, default=str)

            metadata = {
                "content_type": "application/json",
                "encoding": "utf-8",
                "size_bytes": len(content.encode("utf-8")),
                "structure_version": "1.0",
            }

            return FormattedOutput(format_type=self.format_type, content=content, metadata=metadata)

        except Exception as e:
            raise OutputFormatError(f"Failed to format JSON output: {str(e)}")

    def _serialize_status_report(self, report: StatusReport) -> Dict[str, Any]:
        """Serialize status report to dictionary with proper type handling."""
        return {
            "timestamp": self._serialize_datetime(report.timestamp),
            "check_duration_seconds": report.check_duration_seconds,
            "overall_status": {
                "level": self._serialize_status_level(report.get_overall_status_level()),
                "summary": report.get_status_summary(),
                "has_issues": report.has_issues(),
                "issue_count": report.get_issue_count(),
            },
            "health": self._serialize_health_status(report.overall_health),
            "provisioning": self._serialize_provisioning_status(report.provisioning_status),
            "orphaned_assignments": self._serialize_orphaned_assignment_status(
                report.orphaned_assignment_status
            ),
            "sync": self._serialize_sync_status(report.sync_status),
            "summary_statistics": self._serialize_summary_statistics(report.summary_statistics),
            "resource_inspections": [
                self._serialize_resource_inspection(ri) for ri in report.resource_inspections
            ],
            "component_statuses": {
                k: self._serialize_status_level(v)
                for k, v in report.get_component_statuses().items()
            },
        }

    def _serialize_health_status(self, health: HealthStatus) -> Dict[str, Any]:
        """Serialize health status to dictionary."""
        return {
            "status": self._serialize_status_level(health.status),
            "message": health.message,
            "service_available": health.service_available,
            "connectivity_status": health.connectivity_status,
            "response_time_ms": health.response_time_ms,
            "last_successful_check": self._serialize_datetime(health.last_successful_check),
            "timestamp": self._serialize_datetime(health.timestamp),
            "details": health.details,
            "errors": health.errors,
        }

    def _serialize_provisioning_status(self, provisioning: ProvisioningStatus) -> Dict[str, Any]:
        """Serialize provisioning status to dictionary."""
        return {
            "status": self._serialize_status_level(provisioning.status),
            "message": provisioning.message,
            "pending_count": provisioning.pending_count,
            "estimated_completion": self._serialize_datetime(provisioning.estimated_completion),
            "active_operations": [
                self._serialize_provisioning_operation(op) for op in provisioning.active_operations
            ],
            "failed_operations": [
                self._serialize_provisioning_operation(op) for op in provisioning.failed_operations
            ],
            "completed_operations": [
                self._serialize_provisioning_operation(op)
                for op in provisioning.completed_operations
            ],
            "total_operations": provisioning.get_total_operations(),
            "failure_rate": provisioning.get_failure_rate(),
            "timestamp": self._serialize_datetime(provisioning.timestamp),
            "details": provisioning.details,
            "errors": provisioning.errors,
        }

    def _serialize_provisioning_operation(self, operation: ProvisioningOperation) -> Dict[str, Any]:
        """Serialize provisioning operation to dictionary."""
        return {
            "operation_id": operation.operation_id,
            "operation_type": operation.operation_type,
            "status": operation.status.value,
            "target_id": operation.target_id,
            "target_type": operation.target_type,
            "created_date": self._serialize_datetime(operation.created_date),
            "failure_reason": operation.failure_reason,
            "estimated_completion": self._serialize_datetime(operation.estimated_completion),
            "duration_minutes": operation.get_duration_minutes(),
        }

    def _serialize_orphaned_assignment_status(
        self, orphaned: OrphanedAssignmentStatus
    ) -> Dict[str, Any]:
        """Serialize orphaned assignment status to dictionary."""
        return {
            "status": self._serialize_status_level(orphaned.status),
            "message": orphaned.message,
            "orphaned_count": orphaned.get_orphaned_count(),
            "cleanup_available": orphaned.cleanup_available,
            "last_cleanup": self._serialize_datetime(orphaned.last_cleanup),
            "orphaned_assignments": [
                self._serialize_orphaned_assignment(assignment)
                for assignment in orphaned.orphaned_assignments
            ],
            "user_orphans_count": len(orphaned.get_user_orphans()),
            "group_orphans_count": len(orphaned.get_group_orphans()),
            "affected_accounts": orphaned.get_accounts_with_orphans(),
            "timestamp": self._serialize_datetime(orphaned.timestamp),
            "details": orphaned.details,
            "errors": orphaned.errors,
        }

    def _serialize_orphaned_assignment(self, assignment: OrphanedAssignment) -> Dict[str, Any]:
        """Serialize orphaned assignment to dictionary."""
        return {
            "assignment_id": assignment.assignment_id,
            "permission_set_arn": assignment.permission_set_arn,
            "permission_set_name": assignment.permission_set_name,
            "account_id": assignment.account_id,
            "account_name": assignment.account_name,
            "principal_id": assignment.principal_id,
            "principal_type": assignment.principal_type.value,
            "principal_name": assignment.principal_name,
            "error_message": assignment.error_message,
            "created_date": self._serialize_datetime(assignment.created_date),
            "last_accessed": self._serialize_datetime(assignment.last_accessed),
            "display_name": assignment.get_display_name(),
            "age_days": assignment.get_age_days(),
        }

    def _serialize_sync_status(self, sync: SyncMonitorStatus) -> Dict[str, Any]:
        """Serialize sync monitor status to dictionary."""
        return {
            "status": self._serialize_status_level(sync.status),
            "message": sync.message,
            "providers_configured": sync.providers_configured,
            "providers_healthy": sync.providers_healthy,
            "providers_with_errors": sync.providers_with_errors,
            "health_percentage": sync.get_health_percentage(),
            "sync_providers": [
                self._serialize_sync_provider(provider) for provider in sync.sync_providers
            ],
            "overdue_providers": [
                self._serialize_sync_provider(provider) for provider in sync.get_overdue_providers()
            ],
            "error_providers": [
                self._serialize_sync_provider(provider) for provider in sync.get_error_providers()
            ],
            "timestamp": self._serialize_datetime(sync.timestamp),
            "details": sync.details,
            "errors": sync.errors,
        }

    def _serialize_sync_provider(self, provider: SyncStatus) -> Dict[str, Any]:
        """Serialize sync provider status to dictionary."""
        return {
            "provider_name": provider.provider_name,
            "provider_type": provider.provider_type.value,
            "last_sync_time": self._serialize_datetime(provider.last_sync_time),
            "sync_status": provider.sync_status,
            "next_sync_time": self._serialize_datetime(provider.next_sync_time),
            "error_message": provider.error_message,
            "sync_duration_minutes": provider.sync_duration_minutes,
            "objects_synced": provider.objects_synced,
            "sync_age_hours": provider.get_sync_age_hours(),
            "is_overdue": provider.is_sync_overdue(),
            "is_healthy": provider.is_healthy(),
        }

    def _serialize_summary_statistics(self, stats: SummaryStatistics) -> Dict[str, Any]:
        """Serialize summary statistics to dictionary."""
        return {
            "total_users": stats.total_users,
            "total_groups": stats.total_groups,
            "total_permission_sets": stats.total_permission_sets,
            "total_assignments": stats.total_assignments,
            "active_accounts": stats.active_accounts,
            "total_principals": stats.get_total_principals(),
            "assignments_per_account": stats.get_assignments_per_account(),
            "assignments_per_permission_set": stats.get_assignments_per_permission_set(),
            "last_updated": self._serialize_datetime(stats.last_updated),
            "newest_user_date": self._serialize_datetime(stats.get_newest_user_date()),
            "oldest_user_date": self._serialize_datetime(stats.get_oldest_user_date()),
        }

    def _serialize_resource_inspection(
        self, inspection: ResourceInspectionStatus
    ) -> Dict[str, Any]:
        """Serialize resource inspection to dictionary."""
        result = {
            "status": self._serialize_status_level(inspection.status),
            "message": inspection.message,
            "inspection_type": (
                inspection.inspection_type.value if inspection.inspection_type else None
            ),
            "resource_found": inspection.resource_found(),
            "has_suggestions": inspection.has_suggestions(),
            "similar_resources": inspection.similar_resources,
            "resource_summary": inspection.get_resource_summary(),
            "timestamp": self._serialize_datetime(inspection.timestamp),
            "details": inspection.details,
            "errors": inspection.errors,
        }

        if inspection.target_resource:
            result["target_resource"] = {
                "resource_id": inspection.target_resource.resource_id,
                "resource_name": inspection.target_resource.resource_name,
                "resource_type": inspection.target_resource.resource_type.value,
                "exists": inspection.target_resource.exists,
                "status": self._serialize_status_level(inspection.target_resource.status),
                "last_updated": self._serialize_datetime(inspection.target_resource.last_updated),
                "configuration": inspection.target_resource.configuration,
                "health_details": inspection.target_resource.health_details,
                "error_message": inspection.target_resource.error_message,
                "display_name": inspection.target_resource.get_display_name(),
                "age_days": inspection.target_resource.get_age_days(),
            }

        return result


class CSVFormatter(BaseFormatter):
    """Formatter for CSV output suitable for spreadsheet analysis."""

    def __init__(self):
        super().__init__()
        self.format_type = OutputFormat.CSV

    def format(self, status_report: StatusReport) -> FormattedOutput:
        """Format status report as CSV data."""
        try:
            output = StringIO()

            # Write summary section
            self._write_summary_section(output, status_report)
            output.write("\n")

            # Write health status section
            self._write_health_section(output, status_report.overall_health)
            output.write("\n")

            # Write provisioning operations section
            if status_report.provisioning_status.get_total_operations() > 0:
                self._write_provisioning_section(output, status_report.provisioning_status)
                output.write("\n")

            # Write orphaned assignments section
            if status_report.orphaned_assignment_status.has_orphaned_assignments():
                self._write_orphaned_assignments_section(
                    output, status_report.orphaned_assignment_status
                )
                output.write("\n")

            # Write sync providers section
            if status_report.sync_status.has_providers_configured():
                self._write_sync_providers_section(output, status_report.sync_status)
                output.write("\n")

            # Write statistics section
            self._write_statistics_section(output, status_report.summary_statistics)

            content = output.getvalue()

            metadata = {
                "content_type": "text/csv",
                "encoding": "utf-8",
                "size_bytes": len(content.encode("utf-8")),
                "sections": self._get_csv_sections(status_report),
            }

            return FormattedOutput(format_type=self.format_type, content=content, metadata=metadata)

        except Exception as e:
            raise OutputFormatError(f"Failed to format CSV output: {str(e)}")

    def _write_summary_section(self, output: StringIO, report: StatusReport) -> None:
        """Write summary section to CSV."""
        writer = csv.writer(output)
        writer.writerow(["# Status Summary"])
        writer.writerow(["Timestamp", "Overall Status", "Summary", "Issues", "Check Duration (s)"])
        writer.writerow(
            [
                self._serialize_datetime(report.timestamp),
                self._serialize_status_level(report.get_overall_status_level()),
                report.get_status_summary(),
                report.get_issue_count(),
                report.check_duration_seconds,
            ]
        )

    def _write_health_section(self, output: StringIO, health: HealthStatus) -> None:
        """Write health status section to CSV."""
        writer = csv.writer(output)
        writer.writerow(["# Health Status"])
        writer.writerow(
            ["Status", "Message", "Service Available", "Connectivity", "Response Time (ms)"]
        )
        writer.writerow(
            [
                self._serialize_status_level(health.status),
                health.message,
                health.service_available,
                health.connectivity_status,
                health.response_time_ms or "N/A",
            ]
        )

    def _write_provisioning_section(
        self, output: StringIO, provisioning: ProvisioningStatus
    ) -> None:
        """Write provisioning operations section to CSV."""
        writer = csv.writer(output)
        writer.writerow(["# Provisioning Operations"])
        writer.writerow(
            [
                "Operation ID",
                "Type",
                "Status",
                "Target ID",
                "Target Type",
                "Created Date",
                "Duration (min)",
                "Failure Reason",
            ]
        )

        # Write all operations
        all_operations = (
            provisioning.active_operations
            + provisioning.failed_operations
            + provisioning.completed_operations
        )

        for op in all_operations:
            writer.writerow(
                [
                    op.operation_id,
                    op.operation_type,
                    op.status.value,
                    op.target_id,
                    op.target_type,
                    self._serialize_datetime(op.created_date),
                    op.get_duration_minutes() or "N/A",
                    op.failure_reason or "N/A",
                ]
            )

    def _write_orphaned_assignments_section(
        self, output: StringIO, orphaned: OrphanedAssignmentStatus
    ) -> None:
        """Write orphaned assignments section to CSV."""
        writer = csv.writer(output)
        writer.writerow(["# Orphaned Assignments"])
        writer.writerow(
            [
                "Assignment ID",
                "Permission Set",
                "Account ID",
                "Account Name",
                "Principal ID",
                "Principal Type",
                "Principal Name",
                "Age (days)",
                "Error Message",
            ]
        )

        for assignment in orphaned.orphaned_assignments:
            writer.writerow(
                [
                    assignment.assignment_id,
                    assignment.permission_set_name,
                    assignment.account_id,
                    assignment.account_name or "N/A",
                    assignment.principal_id,
                    assignment.principal_type.value,
                    assignment.principal_name or "Deleted",
                    assignment.get_age_days(),
                    assignment.error_message,
                ]
            )

    def _write_sync_providers_section(self, output: StringIO, sync: SyncMonitorStatus) -> None:
        """Write sync providers section to CSV."""
        writer = csv.writer(output)
        writer.writerow(["# Sync Providers"])
        writer.writerow(
            [
                "Provider Name",
                "Provider Type",
                "Status",
                "Last Sync",
                "Sync Age (hours)",
                "Objects Synced",
                "Error Message",
            ]
        )

        for provider in sync.sync_providers:
            writer.writerow(
                [
                    provider.provider_name,
                    provider.provider_type.value,
                    provider.sync_status,
                    self._serialize_datetime(provider.last_sync_time),
                    provider.get_sync_age_hours() or "N/A",
                    provider.objects_synced or "N/A",
                    provider.error_message or "N/A",
                ]
            )

    def _write_statistics_section(self, output: StringIO, stats: SummaryStatistics) -> None:
        """Write statistics section to CSV."""
        writer = csv.writer(output)
        writer.writerow(["# Summary Statistics"])
        writer.writerow(["Metric", "Value"])
        writer.writerow(["Total Users", stats.total_users])
        writer.writerow(["Total Groups", stats.total_groups])
        writer.writerow(["Total Permission Sets", stats.total_permission_sets])
        writer.writerow(["Total Assignments", stats.total_assignments])
        writer.writerow(["Active Accounts", stats.active_accounts])
        writer.writerow(["Assignments per Account", f"{stats.get_assignments_per_account():.2f}"])
        writer.writerow(
            ["Assignments per Permission Set", f"{stats.get_assignments_per_permission_set():.2f}"]
        )
        writer.writerow(["Last Updated", self._serialize_datetime(stats.last_updated)])

    def _get_csv_sections(self, report: StatusReport) -> List[str]:
        """Get list of sections included in CSV output."""
        sections = ["summary", "health", "statistics"]

        if report.provisioning_status.get_total_operations() > 0:
            sections.append("provisioning")

        if report.orphaned_assignment_status.has_orphaned_assignments():
            sections.append("orphaned_assignments")

        if report.sync_status.has_providers_configured():
            sections.append("sync_providers")

        return sections


class TableFormatter(BaseFormatter):
    """Formatter for human-readable table output as default display format."""

    def __init__(self):
        super().__init__()
        self.format_type = OutputFormat.TABLE

    def format(self, status_report: StatusReport) -> FormattedOutput:
        """Format status report as human-readable table."""
        try:
            lines = []

            # Header
            lines.append("=" * 80)
            lines.append("AWS Identity Center Status Report")
            lines.append("=" * 80)
            lines.append(f"Generated: {self._serialize_datetime(status_report.timestamp)}")
            lines.append(f"Check Duration: {status_report.check_duration_seconds:.2f}s")
            lines.append("")

            # Overall Status
            status_level = status_report.get_overall_status_level()
            status_indicator = self._get_status_indicator(status_level)
            lines.append(f"Overall Status: {status_indicator} {status_level.value}")
            lines.append(f"Summary: {status_report.get_status_summary()}")

            if status_report.has_issues():
                lines.append(f"Issues Found: {status_report.get_issue_count()}")

            lines.append("")

            # Component Status Summary
            lines.append("Component Status:")
            lines.append("-" * 40)
            for component, status in status_report.get_component_statuses().items():
                indicator = self._get_status_indicator(status)
                lines.append(
                    f"  {component.replace('_', ' ').title():<20} {indicator} {status.value}"
                )
            lines.append("")

            # Health Details
            self._add_health_section(lines, status_report.overall_health)

            # Provisioning Status
            if status_report.provisioning_status.get_total_operations() > 0:
                self._add_provisioning_section(lines, status_report.provisioning_status)

            # Orphaned Assignments
            if status_report.orphaned_assignment_status.has_orphaned_assignments():
                self._add_orphaned_assignments_section(
                    lines, status_report.orphaned_assignment_status
                )

            # Sync Status
            if status_report.sync_status.has_providers_configured():
                self._add_sync_section(lines, status_report.sync_status)

            # Summary Statistics
            self._add_statistics_section(lines, status_report.summary_statistics)

            # Resource Inspections
            if status_report.resource_inspections:
                self._add_resource_inspections_section(lines, status_report.resource_inspections)

            lines.append("=" * 80)

            content = "\n".join(lines)

            metadata = {
                "content_type": "text/plain",
                "encoding": "utf-8",
                "size_bytes": len(content.encode("utf-8")),
                "line_count": len(lines),
                "sections": self._get_table_sections(status_report),
            }

            return FormattedOutput(format_type=self.format_type, content=content, metadata=metadata)

        except Exception as e:
            raise OutputFormatError(f"Failed to format table output: {str(e)}")

    def _get_status_indicator(self, status: StatusLevel) -> str:
        """Get colored status indicator for terminal display."""
        indicators = {
            StatusLevel.HEALTHY: "✅",
            StatusLevel.WARNING: "⚠️ ",
            StatusLevel.CRITICAL: "❌",
            StatusLevel.CONNECTION_FAILED: "🔌",
        }
        return indicators.get(status, "❓")

    def _add_health_section(self, lines: List[str], health: HealthStatus) -> None:
        """Add health status section to table output."""
        lines.append("Health Status:")
        lines.append("-" * 40)
        lines.append(f"  Status: {self._get_status_indicator(health.status)} {health.status.value}")
        lines.append(f"  Message: {health.message}")
        lines.append(f"  Service Available: {'Yes' if health.service_available else 'No'}")
        lines.append(f"  Connectivity: {health.connectivity_status}")

        if health.response_time_ms is not None:
            lines.append(f"  Response Time: {health.response_time_ms:.2f}ms")

        if health.last_successful_check:
            lines.append(
                f"  Last Successful Check: {self._serialize_datetime(health.last_successful_check)}"
            )

        if health.errors:
            lines.append("  Errors:")
            for error in health.errors:
                lines.append(f"    • {error}")

        lines.append("")

    def _add_provisioning_section(self, lines: List[str], provisioning: ProvisioningStatus) -> None:
        """Add provisioning status section to table output."""
        lines.append("Provisioning Operations:")
        lines.append("-" * 40)
        lines.append(f"  Total Operations: {provisioning.get_total_operations()}")
        lines.append(f"  Active: {len(provisioning.active_operations)}")
        lines.append(f"  Failed: {len(provisioning.failed_operations)}")
        lines.append(f"  Completed: {len(provisioning.completed_operations)}")
        lines.append(f"  Failure Rate: {provisioning.get_failure_rate():.1f}%")

        if provisioning.pending_count > 0:
            lines.append(f"  Pending: {provisioning.pending_count}")

        if provisioning.estimated_completion:
            lines.append(
                f"  Estimated Completion: {self._serialize_datetime(provisioning.estimated_completion)}"
            )

        # Show recent failed operations
        if provisioning.failed_operations:
            lines.append("  Recent Failed Operations:")
            for op in provisioning.failed_operations[:5]:  # Show up to 5
                lines.append(
                    f"    • {op.operation_type} - {op.target_id}: {op.failure_reason or 'Unknown error'}"
                )

        lines.append("")

    def _add_orphaned_assignments_section(
        self, lines: List[str], orphaned: OrphanedAssignmentStatus
    ) -> None:
        """Add orphaned assignments section to table output."""
        lines.append("Orphaned Assignments:")
        lines.append("-" * 40)
        lines.append(f"  Total Orphaned: {orphaned.get_orphaned_count()}")
        lines.append(f"  User Assignments: {len(orphaned.get_user_orphans())}")
        lines.append(f"  Group Assignments: {len(orphaned.get_group_orphans())}")
        lines.append(f"  Affected Accounts: {len(orphaned.get_accounts_with_orphans())}")
        lines.append(f"  Cleanup Available: {'Yes' if orphaned.cleanup_available else 'No'}")

        if orphaned.last_cleanup:
            lines.append(f"  Last Cleanup: {self._serialize_datetime(orphaned.last_cleanup)}")

        # Show sample orphaned assignments
        if orphaned.orphaned_assignments:
            lines.append("  Sample Orphaned Assignments:")
            for assignment in orphaned.orphaned_assignments[:5]:  # Show up to 5
                lines.append(
                    f"    • {assignment.get_display_name()} (Age: {assignment.get_age_days()} days)"
                )

        lines.append("")

    def _add_sync_section(self, lines: List[str], sync: SyncMonitorStatus) -> None:
        """Add sync status section to table output."""
        lines.append("Synchronization Status:")
        lines.append("-" * 40)
        lines.append(f"  Providers Configured: {sync.providers_configured}")
        lines.append(f"  Providers Healthy: {sync.providers_healthy}")
        lines.append(f"  Providers with Errors: {sync.providers_with_errors}")
        lines.append(f"  Health Percentage: {sync.get_health_percentage():.1f}%")

        if sync.sync_providers:
            lines.append("  Provider Details:")
            for provider in sync.sync_providers:
                status_indicator = "✅" if provider.is_healthy() else "❌"
                lines.append(
                    f"    {status_indicator} {provider.provider_name} ({provider.provider_type.value})"
                )

                if provider.last_sync_time:
                    age_hours = provider.get_sync_age_hours()
                    lines.append(
                        f"      Last Sync: {self._serialize_datetime(provider.last_sync_time)} ({age_hours:.1f}h ago)"
                    )
                else:
                    lines.append("      Last Sync: Never")

                if provider.error_message:
                    lines.append(f"      Error: {provider.error_message}")

        lines.append("")

    def _add_statistics_section(self, lines: List[str], stats: SummaryStatistics) -> None:
        """Add summary statistics section to table output."""
        lines.append("Summary Statistics:")
        lines.append("-" * 40)
        lines.append(f"  Users: {stats.total_users:,}")
        lines.append(f"  Groups: {stats.total_groups:,}")
        lines.append(f"  Permission Sets: {stats.total_permission_sets:,}")
        lines.append(f"  Total Assignments: {stats.total_assignments:,}")
        lines.append(f"  Active Accounts: {stats.active_accounts:,}")
        lines.append(f"  Assignments per Account: {stats.get_assignments_per_account():.2f}")
        lines.append(
            f"  Assignments per Permission Set: {stats.get_assignments_per_permission_set():.2f}"
        )
        lines.append(f"  Last Updated: {self._serialize_datetime(stats.last_updated)}")

        if stats.get_newest_user_date():
            lines.append(f"  Newest User: {self._serialize_datetime(stats.get_newest_user_date())}")

        if stats.get_oldest_user_date():
            lines.append(f"  Oldest User: {self._serialize_datetime(stats.get_oldest_user_date())}")

        lines.append("")

    def _add_resource_inspections_section(
        self, lines: List[str], inspections: List[ResourceInspectionStatus]
    ) -> None:
        """Add resource inspections section to table output."""
        lines.append("Resource Inspections:")
        lines.append("-" * 40)

        for inspection in inspections:
            status_indicator = self._get_status_indicator(inspection.status)
            lines.append(f"  {status_indicator} {inspection.get_resource_summary()}")

            if inspection.target_resource:
                resource = inspection.target_resource
                lines.append(f"    Type: {resource.resource_type.value}")
                lines.append(f"    Status: {resource.status.value}")

                if resource.last_updated:
                    lines.append(
                        f"    Last Updated: {self._serialize_datetime(resource.last_updated)}"
                    )

                if resource.error_message:
                    lines.append(f"    Error: {resource.error_message}")

            if inspection.has_suggestions():
                lines.append(
                    f"    Similar Resources: {', '.join(inspection.similar_resources[:3])}"
                )
                if len(inspection.similar_resources) > 3:
                    lines.append(f"    ... and {len(inspection.similar_resources) - 3} more")

        lines.append("")

    def _get_table_sections(self, report: StatusReport) -> List[str]:
        """Get list of sections included in table output."""
        sections = ["header", "overall_status", "component_status", "health", "statistics"]

        if report.provisioning_status.get_total_operations() > 0:
            sections.append("provisioning")

        if report.orphaned_assignment_status.has_orphaned_assignments():
            sections.append("orphaned_assignments")

        if report.sync_status.has_providers_configured():
            sections.append("sync")

        if report.resource_inspections:
            sections.append("resource_inspections")

        return sections


class OutputFormatterFactory:
    """Factory class for creating output formatters."""

    _formatters = {
        OutputFormat.JSON: JSONFormatter,
        OutputFormat.CSV: CSVFormatter,
        OutputFormat.TABLE: TableFormatter,
    }

    @classmethod
    def create_formatter(cls, format_type: OutputFormat) -> BaseFormatter:
        """Create a formatter instance for the specified format type."""
        if format_type not in cls._formatters:
            raise OutputFormatError(f"Unsupported output format: {format_type}")

        formatter_class = cls._formatters[format_type]
        return formatter_class()

    @classmethod
    def get_supported_formats(cls) -> List[OutputFormat]:
        """Get list of supported output formats."""
        return list(cls._formatters.keys())

    @classmethod
    def detect_format(cls, format_string: str) -> OutputFormat:
        """Detect output format from string input with validation."""
        format_string = format_string.lower().strip()

        # Direct mapping
        format_mapping = {
            "json": OutputFormat.JSON,
            "csv": OutputFormat.CSV,
            "table": OutputFormat.TABLE,
            "txt": OutputFormat.TABLE,  # Alias for table
            "text": OutputFormat.TABLE,  # Alias for table
        }

        if format_string in format_mapping:
            return format_mapping[format_string]

        # Try to match by enum value
        try:
            return OutputFormat(format_string)
        except ValueError:
            pass

        raise OutputFormatError(
            f"Invalid output format '{format_string}'. "
            f"Supported formats: {', '.join([f.value for f in cls.get_supported_formats()])}"
        )

    @classmethod
    def validate_format(cls, format_type: OutputFormat) -> bool:
        """Validate that the format type is supported."""
        return format_type in cls._formatters


def format_status_report(status_report: StatusReport, format_type: OutputFormat) -> FormattedOutput:
    """
    Convenience function to format a status report.

    Args:
        status_report: The status report to format
        format_type: The desired output format

    Returns:
        FormattedOutput containing the formatted content

    Raises:
        OutputFormatError: If formatting fails or format is unsupported
    """
    formatter = OutputFormatterFactory.create_formatter(format_type)
    return formatter.format(status_report)


def detect_and_format(status_report: StatusReport, format_string: str) -> FormattedOutput:
    """
    Detect format from string and format status report.

    Args:
        status_report: The status report to format
        format_string: String representation of desired format

    Returns:
        FormattedOutput containing the formatted content

    Raises:
        OutputFormatError: If format detection or formatting fails
    """
    format_type = OutputFormatterFactory.detect_format(format_string)
    return format_status_report(status_report, format_type)
