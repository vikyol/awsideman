"""Reporting components for bulk operations.

This module provides classes for generating summary and detailed reports
for bulk assignment operations, with Rich formatting for console output.

Classes:
    ReportGenerator: Generates formatted reports for bulk operation results
"""

import time
from pathlib import Path
from typing import Optional

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .batch import BulkOperationResults


class ReportGenerator:
    """Generates summary and detailed reports for bulk operations."""

    def __init__(self, console: Console):
        """Initialize report generator.

        Args:
            console: Rich console for output
        """
        self.console = console

    def generate_summary_report(self, results: BulkOperationResults, operation: str):
        """Generate and display summary report.

        Args:
            results: Bulk operation results
            operation: Operation type ('assign' or 'revoke')
        """
        # Create summary statistics
        total = results.total_processed
        successful = results.success_count
        failed = results.failure_count
        skipped = results.skip_count
        success_rate = results.success_rate

        # Format duration
        duration_str = self._format_duration(results.duration)

        # Create summary table
        summary_table = Table(show_header=False, box=None, padding=(0, 1))
        summary_table.add_column("Metric", style="bold cyan")
        summary_table.add_column("Value", style="bold")

        summary_table.add_row("Operation", operation.title())
        summary_table.add_row("Total Processed", str(total))
        summary_table.add_row("Successful", f"[green]{successful}[/green]")
        summary_table.add_row("Failed", f"[red]{failed}[/red]")
        summary_table.add_row("Skipped", f"[yellow]{skipped}[/yellow]")
        summary_table.add_row("Success Rate", f"{success_rate:.1f}%")
        summary_table.add_row("Duration", duration_str)

        # Create status breakdown
        status_panels = []

        if successful > 0:
            success_panel = Panel(
                f"[bold green]{successful}[/bold green]\nSuccessful", style="green", width=15
            )
            status_panels.append(success_panel)

        if failed > 0:
            failed_panel = Panel(f"[bold red]{failed}[/bold red]\nFailed", style="red", width=15)
            status_panels.append(failed_panel)

        if skipped > 0:
            skipped_panel = Panel(
                f"[bold yellow]{skipped}[/bold yellow]\nSkipped", style="yellow", width=15
            )
            status_panels.append(skipped_panel)

        # Display summary
        self.console.print()
        self.console.print(
            Panel(
                summary_table,
                title=f"[bold]Bulk {operation.title()} Summary[/bold]",
                border_style="blue",
            )
        )

        if status_panels:
            self.console.print()
            self.console.print(Columns(status_panels, equal=True, expand=True))

        # Show timing information if available
        if results.start_time and results.end_time:
            start_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(results.start_time))
            end_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(results.end_time))

            timing_table = Table(show_header=False, box=None, padding=(0, 1))
            timing_table.add_column("Metric", style="dim")
            timing_table.add_column("Value", style="dim")

            timing_table.add_row("Started", start_time_str)
            timing_table.add_row("Completed", end_time_str)

            self.console.print()
            self.console.print(
                Panel(timing_table, title="[dim]Timing Information[/dim]", border_style="dim")
            )

    def generate_detailed_report(
        self,
        results: BulkOperationResults,
        output_file: Optional[Path] = None,
        show_successful: bool = True,
        show_failed: bool = True,
        show_skipped: bool = True,
    ):
        """Generate detailed report with individual assignment results.

        Args:
            results: Bulk operation results
            output_file: Optional file path to save detailed report
            show_successful: Whether to show successful assignments
            show_failed: Whether to show failed assignments
            show_skipped: Whether to show skipped assignments
        """
        # Collect results to display
        results_to_show = []

        if show_successful and results.successful:
            results_to_show.extend([("Successful", result) for result in results.successful])

        if show_failed and results.failed:
            results_to_show.extend([("Failed", result) for result in results.failed])

        if show_skipped and results.skipped:
            results_to_show.extend([("Skipped", result) for result in results.skipped])

        if not results_to_show:
            self.console.print("[dim]No detailed results to display[/dim]")
            return

        # Create detailed table
        detailed_table = Table(
            title=f"Detailed {results.operation_type.title()} Results",
            show_header=True,
            header_style="bold magenta",
        )

        detailed_table.add_column("Status", style="bold", width=10)
        detailed_table.add_column("Principal", style="cyan", width=20)
        detailed_table.add_column("Permission Set", style="blue", width=25)
        detailed_table.add_column("Account", style="green", width=20)
        detailed_table.add_column("Type", width=8)
        detailed_table.add_column("Time (s)", justify="right", width=8)
        detailed_table.add_column("Error", style="red", width=40)

        # Add rows for each result
        for status_category, result in results_to_show:
            # Determine status style
            if result.status == "success":
                status_style = "[green]✓[/green]"
            elif result.status == "failed":
                status_style = "[red]✗[/red]"
            else:
                status_style = "[yellow]⚠[/yellow]"

            # Format processing time
            time_str = f"{result.processing_time:.2f}" if result.processing_time else "N/A"

            # Truncate error message if too long
            error_msg = result.error_message or ""
            if len(error_msg) > 37:
                error_msg = error_msg[:180] + "..."

            detailed_table.add_row(
                status_style,
                result.principal_name or "N/A",
                result.permission_set_name or "N/A",
                result.account_name or "N/A",
                result.principal_type or "USER",
                time_str,
                error_msg,
            )

        # Display detailed table
        self.console.print()
        self.console.print(detailed_table)

        # Save to file if requested
        if output_file:
            self._save_detailed_report_to_file(results, output_file)

    def generate_error_summary(self, results: BulkOperationResults):
        """Generate summary of errors encountered during processing.

        Args:
            results: Bulk operation results
        """
        if not results.failed:
            self.console.print("[green]No errors encountered![/green]")
            return

        # Group errors by type
        error_groups = {}
        for result in results.failed:
            error_msg = result.error_message or "Unknown error"
            # Extract error type (first part before colon or full message if no colon)
            error_type = error_msg.split(":")[0].strip()

            if error_type not in error_groups:
                error_groups[error_type] = []
            error_groups[error_type].append(result)

        # Create error summary table
        error_table = Table(title="Error Summary", show_header=True, header_style="bold red")

        error_table.add_column("Error Type", style="red", width=30)
        error_table.add_column("Count", justify="right", width=8)
        error_table.add_column("Examples", style="dim", width=50)

        for error_type, error_results in error_groups.items():
            count = len(error_results)

            # Get up to 3 examples
            examples = []
            for result in error_results[:3]:
                example = f"{result.principal_name} → {result.permission_set_name}"
                examples.append(example)

            if len(error_results) > 3:
                examples.append(f"... and {len(error_results) - 3} more")

            examples_str = "; ".join(examples)

            error_table.add_row(error_type, str(count), examples_str)

        self.console.print()
        self.console.print(error_table)

    def generate_performance_report(self, results: BulkOperationResults):
        """Generate performance metrics report.

        Args:
            results: Bulk operation results
        """
        if results.duration <= 0:
            self.console.print("[dim]No performance data available[/dim]")
            return

        # Calculate performance metrics
        total_assignments = results.total_processed
        throughput = total_assignments / results.duration if results.duration > 0 else 0

        # Calculate average processing time per assignment
        all_results = results.get_all_results()
        processing_times = [
            r.processing_time for r in all_results if r.processing_time and r.processing_time > 0
        ]

        avg_processing_time = (
            sum(processing_times) / len(processing_times) if processing_times else 0
        )
        min_processing_time = min(processing_times) if processing_times else 0
        max_processing_time = max(processing_times) if processing_times else 0

        # Create performance table
        perf_table = Table(show_header=False, box=None, padding=(0, 1))
        perf_table.add_column("Metric", style="bold cyan")
        perf_table.add_column("Value", style="bold")

        perf_table.add_row("Total Duration", self._format_duration(results.duration))
        perf_table.add_row("Throughput", f"{throughput:.2f} assignments/sec")
        perf_table.add_row("Batch Size", str(results.batch_size))

        if processing_times:
            perf_table.add_row("Avg Processing Time", f"{avg_processing_time:.3f}s")
            perf_table.add_row("Min Processing Time", f"{min_processing_time:.3f}s")
            perf_table.add_row("Max Processing Time", f"{max_processing_time:.3f}s")

        self.console.print()
        self.console.print(
            Panel(perf_table, title="[bold]Performance Metrics[/bold]", border_style="cyan")
        )

    def _format_duration(self, seconds: float) -> str:
        """Format duration in seconds to human-readable string.

        Args:
            seconds: Duration in seconds

        Returns:
            Formatted duration string
        """
        if seconds < 0:
            return "N/A"

        if seconds < 1:
            return f"{seconds*1000:.0f}ms"
        elif seconds < 60:
            return f"{seconds:.2f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            remaining_seconds = seconds % 60
            return f"{minutes}m {remaining_seconds:.1f}s"
        else:
            hours = int(seconds // 3600)
            remaining_minutes = int((seconds % 3600) // 60)
            remaining_seconds = seconds % 60
            return f"{hours}h {remaining_minutes}m {remaining_seconds:.1f}s"

    def _save_detailed_report_to_file(self, results: BulkOperationResults, output_file: Path):
        """Save detailed report to a file.

        Args:
            results: Bulk operation results
            output_file: Path to save the report
        """
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                # Write header
                f.write(f"Bulk {results.operation_type.title()} Detailed Report\n")
                f.write("=" * 50 + "\n\n")

                # Write summary
                f.write(f"Total Processed: {results.total_processed}\n")
                f.write(f"Successful: {results.success_count}\n")
                f.write(f"Failed: {results.failure_count}\n")
                f.write(f"Skipped: {results.skip_count}\n")
                f.write(f"Success Rate: {results.success_rate:.1f}%\n")
                f.write(f"Duration: {self._format_duration(results.duration)}\n\n")

                # Write detailed results
                all_results = results.get_all_results()
                for i, result in enumerate(all_results, 1):
                    f.write(f"{i}. {result.status.upper()}: ")
                    f.write(
                        f"{result.principal_name} -> {result.permission_set_name} @ {result.account_name}"
                    )

                    if result.principal_type:
                        f.write(f" ({result.principal_type})")

                    if result.processing_time:
                        f.write(f" [{result.processing_time:.3f}s]")

                    if result.error_message:
                        f.write(f"\n   Error: {result.error_message}")

                    f.write("\n")

            self.console.print(f"[green]Detailed report saved to: {output_file}[/green]")

        except Exception as e:
            self.console.print(f"[red]Failed to save detailed report: {str(e)}[/red]")
