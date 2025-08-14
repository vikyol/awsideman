"""Preview functionality for bulk operations.

This module provides classes for generating and displaying assignment previews
before executing bulk operations. Includes user confirmation prompts and
detailed preview reports.

Classes:
    PreviewGenerator: Generates and displays assignment previews with user confirmation
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table
from rich.text import Text

from .resolver import ResourceResolver


@dataclass
class PreviewSummary:
    """Summary statistics for preview display."""

    total_assignments: int
    successful_resolutions: int
    failed_resolutions: int
    users: int
    groups: int
    unique_permission_sets: int
    unique_accounts: int


class PreviewGenerator:
    """Generates and displays assignment previews with user confirmation."""

    def __init__(self, console: Console):
        """Initialize the preview generator.

        Args:
            console: Rich console for output formatting
        """
        self.console = console

    def generate_preview_report(
        self, assignments: List[Dict[str, Any]], operation_type: str = "assign"
    ) -> PreviewSummary:
        """Generate and display a preview report showing resolved names and IDs.

        Args:
            assignments: List of assignment dictionaries with resolved data
            operation_type: Type of operation ('assign' or 'revoke')

        Returns:
            PreviewSummary with statistics about the assignments
        """
        # Calculate summary statistics
        summary = self._calculate_summary(assignments)

        # Display header
        self._display_header(operation_type, summary)

        # Display summary statistics
        self._display_summary_stats(summary)

        # Display detailed assignment table
        self._display_assignment_table(assignments, operation_type)

        # Display any resolution errors
        self._display_resolution_errors(assignments)

        return summary

    def _calculate_summary(self, assignments: List[Dict[str, Any]]) -> PreviewSummary:
        """Calculate summary statistics for the assignments.

        Args:
            assignments: List of assignment dictionaries

        Returns:
            PreviewSummary with calculated statistics
        """
        total_assignments = len(assignments)
        successful_resolutions = sum(1 for a in assignments if a.get("resolution_success", False))
        failed_resolutions = total_assignments - successful_resolutions

        users = sum(1 for a in assignments if a.get("principal_type", "").upper() == "USER")
        groups = sum(1 for a in assignments if a.get("principal_type", "").upper() == "GROUP")

        unique_permission_sets = len(
            set(
                a.get("permission_set_name", "")
                for a in assignments
                if a.get("permission_set_name")
            )
        )

        unique_accounts = len(
            set(a.get("account_name", "") for a in assignments if a.get("account_name"))
        )

        return PreviewSummary(
            total_assignments=total_assignments,
            successful_resolutions=successful_resolutions,
            failed_resolutions=failed_resolutions,
            users=users,
            groups=groups,
            unique_permission_sets=unique_permission_sets,
            unique_accounts=unique_accounts,
        )

    def _display_header(self, operation_type: str, summary: PreviewSummary):
        """Display the preview header.

        Args:
            operation_type: Type of operation ('assign' or 'revoke')
            summary: Preview summary statistics
        """
        operation_title = f"Bulk {operation_type.title()} Preview"

        # Create header text with color coding
        if summary.failed_resolutions > 0:
            status_color = "yellow"
            status_text = f"⚠️  {summary.failed_resolutions} resolution errors found"
        else:
            status_color = "green"
            status_text = "✅ All names resolved successfully"

        header_text = Text()
        header_text.append(f"{operation_title}\n", style="bold blue")
        header_text.append(status_text, style=f"bold {status_color}")

        panel = Panel(header_text, title="Preview Report", title_align="left", border_style="blue")

        self.console.print()
        self.console.print(panel)
        self.console.print()

    def _display_summary_stats(self, summary: PreviewSummary):
        """Display summary statistics table.

        Args:
            summary: Preview summary statistics
        """
        stats_table = Table(
            title="Summary Statistics", show_header=True, header_style="bold magenta"
        )
        stats_table.add_column("Metric", style="cyan", no_wrap=True)
        stats_table.add_column("Count", style="green", justify="right")

        stats_table.add_row("Total Assignments", str(summary.total_assignments))
        stats_table.add_row("Successful Resolutions", str(summary.successful_resolutions))

        if summary.failed_resolutions > 0:
            stats_table.add_row("Failed Resolutions", f"[red]{summary.failed_resolutions}[/red]")
        else:
            stats_table.add_row("Failed Resolutions", str(summary.failed_resolutions))

        stats_table.add_row("", "")  # Separator
        stats_table.add_row("Users", str(summary.users))
        stats_table.add_row("Groups", str(summary.groups))
        stats_table.add_row("Unique Permission Sets", str(summary.unique_permission_sets))
        stats_table.add_row("Unique Accounts", str(summary.unique_accounts))

        self.console.print(stats_table)
        self.console.print()

    def _display_assignment_table(self, assignments: List[Dict[str, Any]], operation_type: str):
        """Display detailed assignment table.

        Args:
            assignments: List of assignment dictionaries
            operation_type: Type of operation ('assign' or 'revoke')
        """
        # Create assignments table
        table = Table(
            title=f"Assignment Details ({operation_type.title()} Operation)",
            show_header=True,
            header_style="bold magenta",
            show_lines=True,
        )

        # Add columns
        table.add_column("#", style="dim", width=4, justify="right")
        table.add_column("Principal", style="cyan", min_width=15)
        table.add_column("Type", style="blue", width=6)
        table.add_column("Permission Set", style="green", min_width=15)
        table.add_column("Account", style="yellow", min_width=15)
        table.add_column("Status", style="white", width=10)

        # Add rows
        for idx, assignment in enumerate(assignments, 1):
            # Format principal information
            principal_name = assignment.get("principal_name", "N/A")
            principal_id = assignment.get("principal_id", "")
            if principal_id:
                principal_display = f"{principal_name}\n[dim]{principal_id}[/dim]"
            else:
                principal_display = f"{principal_name}\n[red]Not resolved[/red]"

            # Format principal type
            principal_type = assignment.get("principal_type", "USER")

            # Format permission set information
            ps_name = assignment.get("permission_set_name", "N/A")
            ps_arn = assignment.get("permission_set_arn", "")
            if ps_arn:
                # Extract permission set name from ARN for display
                ps_display = (
                    f"{ps_name}\n[dim]{ps_arn.split('/')[-1] if '/' in ps_arn else ps_arn}[/dim]"
                )
            else:
                ps_display = f"{ps_name}\n[red]Not resolved[/red]"

            # Format account information
            account_name = assignment.get("account_name", "N/A")
            account_id = assignment.get("account_id", "")
            if account_id:
                account_display = f"{account_name}\n[dim]{account_id}[/dim]"
            else:
                account_display = f"{account_name}\n[red]Not resolved[/red]"

            # Format status
            if assignment.get("resolution_success", False):
                status = "[green]✅ Ready[/green]"
            else:
                status = "[red]❌ Error[/red]"

            table.add_row(
                str(idx), principal_display, principal_type, ps_display, account_display, status
            )

        self.console.print(table)
        self.console.print()

    def _display_resolution_errors(self, assignments: List[Dict[str, Any]]):
        """Display resolution errors if any exist.

        Args:
            assignments: List of assignment dictionaries
        """
        # Collect all assignments with errors
        error_assignments = [
            a
            for a in assignments
            if not a.get("resolution_success", False) and a.get("resolution_errors")
        ]

        if not error_assignments:
            return

        # Create error table
        error_table = Table(
            title="Resolution Errors", show_header=True, header_style="bold red", border_style="red"
        )

        error_table.add_column("#", style="dim", width=4, justify="right")
        error_table.add_column("Assignment", style="cyan", min_width=20)
        error_table.add_column("Errors", style="red", min_width=30)

        for idx, assignment in enumerate(error_assignments, 1):
            # Format assignment identifier
            principal_name = assignment.get("principal_name", "N/A")
            ps_name = assignment.get("permission_set_name", "N/A")
            account_name = assignment.get("account_name", "N/A")
            assignment_id = f"{principal_name} → {ps_name} @ {account_name}"

            # Format errors
            errors = assignment.get("resolution_errors", [])
            error_text = "\n".join(f"• {error}" for error in errors)

            error_table.add_row(str(idx), assignment_id, error_text)

        self.console.print(error_table)
        self.console.print()

    def prompt_user_confirmation(
        self, operation_type: str, summary: PreviewSummary, force: bool = False
    ) -> bool:
        """Prompt user for confirmation after displaying preview.

        Args:
            operation_type: Type of operation ('assign' or 'revoke')
            summary: Preview summary statistics
            force: Skip confirmation if True

        Returns:
            True if user confirms to proceed, False to cancel
        """
        if force:
            self.console.print("[yellow]Force mode enabled - skipping confirmation[/yellow]")
            return True

        # Show warning if there are resolution errors
        if summary.failed_resolutions > 0:
            warning_panel = Panel(
                f"[red]⚠️  Warning: {summary.failed_resolutions} assignments have resolution errors and will be skipped.[/red]\n"
                f"Only {summary.successful_resolutions} out of {summary.total_assignments} assignments will be processed.",
                title="Resolution Errors Detected",
                border_style="red",
            )
            self.console.print(warning_panel)
            self.console.print()

        # Create confirmation message
        if summary.failed_resolutions > 0:
            confirm_message = (
                f"Do you want to proceed with {operation_type}ing "
                f"{summary.successful_resolutions} assignments?"
            )
        else:
            confirm_message = (
                f"Do you want to proceed with {operation_type}ing "
                f"{summary.total_assignments} assignments?"
            )

        # Special handling for revoke operations
        if operation_type.lower() == "revoke":
            self.console.print("[red]⚠️  This will REMOVE permission set assignments![/red]")
            self.console.print()

        # Prompt for confirmation
        try:
            return Confirm.ask(confirm_message, default=False)
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Operation cancelled by user[/yellow]")
            return False

    def display_cancellation_message(self, operation_type: str):
        """Display cancellation message when user chooses not to proceed.

        Args:
            operation_type: Type of operation ('assign' or 'revoke')
        """
        cancellation_panel = Panel(
            f"[yellow]Bulk {operation_type} operation cancelled by user.[/yellow]\n"
            "No changes have been made to your AWS Identity Center assignments.",
            title="Operation Cancelled",
            border_style="yellow",
        )
        self.console.print()
        self.console.print(cancellation_panel)

    def display_dry_run_message(self, operation_type: str, summary: PreviewSummary):
        """Display dry-run completion message.

        Args:
            operation_type: Type of operation ('assign' or 'revoke')
            summary: Preview summary statistics
        """
        if summary.failed_resolutions > 0:
            status_text = (
                f"[yellow]Dry-run completed with {summary.failed_resolutions} resolution errors.[/yellow]\n"
                f"Fix the errors above and run again to proceed with {summary.successful_resolutions} assignments."
            )
            border_style = "yellow"
        else:
            status_text = (
                f"[green]Dry-run completed successfully![/green]\n"
                f"All {summary.total_assignments} assignments are ready for {operation_type} operation.\n"
                f"Remove --dry-run flag to execute the actual {operation_type} operation."
            )
            border_style = "green"

        dry_run_panel = Panel(
            status_text,
            title=f"Dry-Run Complete - {operation_type.title()} Operation",
            border_style=border_style,
        )
        self.console.print()
        self.console.print(dry_run_panel)

    def generate_preview_for_file(
        self, file_path: Path, resolver: ResourceResolver, operation_type: str = "assign"
    ) -> tuple[List[Dict[str, Any]], PreviewSummary]:
        """Generate preview for assignments from a file.

        Args:
            file_path: Path to the input file
            resolver: ResourceResolver instance for name resolution
            operation_type: Type of operation ('assign' or 'revoke')

        Returns:
            Tuple of (resolved_assignments, preview_summary)

        Raises:
            ValueError: If file processing fails
            FileNotFoundError: If file doesn't exist
        """
        from .processors import FileFormatDetector

        # Get appropriate processor for the file
        processor = FileFormatDetector.get_processor(file_path)

        # Parse assignments from file
        assignments = processor.parse_assignments()

        # Resolve names to IDs/ARNs
        resolved_assignments = []
        for assignment in assignments:
            resolved_assignment = resolver.resolve_assignment(assignment)
            resolved_assignments.append(resolved_assignment)

        # Generate and display preview
        summary = self.generate_preview_report(resolved_assignments, operation_type)

        return resolved_assignments, summary

    def validate_assignments_for_operation(
        self, assignments: List[Dict[str, Any]], operation_type: str
    ) -> List[Dict[str, Any]]:
        """Validate assignments are suitable for the specified operation.

        Args:
            assignments: List of resolved assignment dictionaries
            operation_type: Type of operation ('assign' or 'revoke')

        Returns:
            List of assignments that are valid for the operation
        """
        valid_assignments = []

        for assignment in assignments:
            # Skip assignments with resolution errors
            if not assignment.get("resolution_success", False):
                continue

            # Check required fields are present
            required_fields = ["principal_id", "permission_set_arn", "account_id"]
            if all(assignment.get(field) for field in required_fields):
                valid_assignments.append(assignment)

        return valid_assignments

    def display_operation_summary(
        self,
        operation_type: str,
        total_requested: int,
        valid_assignments: int,
        skipped_assignments: int,
    ):
        """Display summary of what will be processed.

        Args:
            operation_type: Type of operation ('assign' or 'revoke')
            total_requested: Total number of assignments requested
            valid_assignments: Number of valid assignments to process
            skipped_assignments: Number of assignments to skip
        """
        if skipped_assignments > 0:
            summary_text = (
                f"[blue]Processing {valid_assignments} out of {total_requested} assignments[/blue]\n"
                f"[yellow]{skipped_assignments} assignments will be skipped due to resolution errors[/yellow]"
            )
            border_style = "yellow"
        else:
            summary_text = f"[green]Processing all {valid_assignments} assignments[/green]"
            border_style = "green"

        summary_panel = Panel(
            summary_text,
            title=f"Starting {operation_type.title()} Operation",
            border_style=border_style,
        )
        self.console.print()
        self.console.print(summary_panel)
        self.console.print()
