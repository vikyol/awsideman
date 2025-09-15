"""Status check command implementation."""

import asyncio
from typing import Any, Optional

import typer
from botocore.exceptions import ClientError
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text

from ...aws_clients.manager import AWSClientManager
from ...utils.output_formatters import (
    CSVFormatter,
    JSONFormatter,
    OutputFormatError,
    TableFormatter,
)
from ...utils.status_infrastructure import StatusCheckConfig
from ...utils.status_models import OutputFormat, StatusLevel
from ...utils.status_orchestrator import StatusOrchestrator
from .helpers import (
    validate_aws_credentials,
    validate_output_format,
    validate_profile,
    validate_sso_instance,
    validate_status_type,
)

console = Console()


def check_status(
    output_format: Optional[str] = typer.Option(
        None, "--format", "-f", help="Output format: json, csv, table (default: table)"
    ),
    status_type: Optional[str] = typer.Option(
        None,
        "--type",
        "-t",
        help="Specific status type to check: health, provisioning, orphaned, sync, resource, summary",
    ),
    timeout: Optional[int] = typer.Option(
        30,
        "--timeout",
        help="Timeout for status checks in seconds (default: 30, use 300+ for large organizations)",
    ),
    parallel: bool = typer.Option(
        True, "--parallel/--sequential", help="Run checks in parallel (default: parallel)"
    ),
    quick_scan: bool = typer.Option(
        True,
        "--quick-scan/--full-scan",
        help="Use quick scan for orphaned assignments (default: quick scan)",
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="AWS profile to use (uses default profile if not specified)"
    ),
) -> None:
    """Check AWS Identity Center status and health.

    Performs comprehensive status monitoring including:
    - Overall health and connectivity
    - Active provisioning operations
    - Orphaned permission set assignments
    - External identity provider synchronization
    - Summary statistics

    Use --type to check specific status components or omit for comprehensive check.
    Output can be formatted as JSON, CSV, or human-readable table.
    """
    try:
        # Validate inputs
        output_fmt = validate_output_format(output_format)
        check_type = validate_status_type(status_type)

        # Validate the profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Validate the SSO instance and get instance ARN and identity store ID
        instance_arn, identity_store_id = validate_sso_instance(profile_data)

        # Initialize the AWS client manager with the profile and region
        region = profile_data.get("region")
        aws_client = AWSClientManager(profile=profile_name, region=region)

        # Validate AWS credentials before proceeding with status checks
        validate_aws_credentials(aws_client)

        # Clear cache before orphaned assignment detection to ensure fresh data
        # This prevents false negatives when groups/users have been deleted but cache still shows them as existing
        if (check_type == "orphaned" or check_type is None) and aws_client.is_caching_enabled():
            console.print(
                "[dim]Clearing cache to ensure fresh data for orphaned assignment detection...[/dim]"
            )
            cache_cleared = aws_client.clear_cache()
            if cache_cleared:
                console.print("[dim]✓ Cache cleared successfully[/dim]")
            else:
                console.print(
                    "[yellow]⚠ Warning: Could not clear cache, results may be stale[/yellow]"
                )

        # Create status check configuration optimized for large organizations
        # Use more conservative settings to avoid rate limiting
        status_config = StatusCheckConfig(
            timeout_seconds=timeout or 30,
            enable_parallel_checks=parallel,
            max_concurrent_checks=2 if parallel else 1,  # Reduced concurrency
            retry_attempts=3,
            retry_delay_seconds=2.0,  # Increased delay
            api_call_delay_seconds=0.2,  # Delay between API calls
            batch_size=5,  # Smaller batches
            batch_delay_seconds=1.0,  # Delay between batches
            max_retry_delay_seconds=15.0,  # Longer max delay
        )

        # Initialize the status orchestrator
        orchestrator = StatusOrchestrator(aws_client, status_config)

        # Enable quick scan for orphaned assignments to avoid long waits
        # For status checks, we only need to know IF there are orphaned assignments
        if quick_scan:
            orchestrator.enable_quick_scan(max_orphaned_to_find=1)

        # Show progress indicator for long-running operations
        if check_type == "orphaned":
            # Use live progress display for orphaned assignment detection
            progress_text = Text("Detecting orphaned assignments...", style="blue")

            def update_progress(message: str) -> None:
                """Update the progress display with new message."""
                progress_text.plain = message

            # Set the progress callback for orphaned assignment detection
            orchestrator.set_orphaned_progress_callback(update_progress)

            with Live(progress_text, console=console, refresh_per_second=2):
                result = asyncio.run(orchestrator.get_specific_status(check_type))

            # Format and display specific result
            _display_specific_status_result(result, output_fmt, check_type)
        else:
            # Use regular progress display for other status checks
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True,
            ) as progress:
                if check_type:
                    task = progress.add_task(f"Checking {check_type} status...", total=None)
                    # Run specific status check
                    result = asyncio.run(orchestrator.get_specific_status(check_type))
                    progress.remove_task(task)

                    # Format and display specific result
                    _display_specific_status_result(result, output_fmt, check_type)
                else:
                    task = progress.add_task("Performing comprehensive status check...", total=None)
                    # Run comprehensive status check
                    status_report = asyncio.run(orchestrator.get_comprehensive_status())
                    progress.remove_task(task)

                    # Format and display comprehensive result
                    _display_comprehensive_status_report(status_report, output_fmt)

    except ClientError as e:
        # Handle AWS API errors
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))
        console.print(f"[red]AWS Error ({error_code}): {error_message}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        # Handle other unexpected errors
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


def _display_comprehensive_status_report(status_report: Any, output_fmt: OutputFormat) -> None:
    """Display comprehensive status report in the specified format."""
    try:
        # Select appropriate formatter
        formatter: JSONFormatter | CSVFormatter | TableFormatter
        if output_fmt == OutputFormat.JSON:
            formatter = JSONFormatter()
        elif output_fmt == OutputFormat.CSV:
            formatter = CSVFormatter()
        else:
            formatter = TableFormatter()

        # Format the output
        formatted_output = formatter.format(status_report)

        # Display the formatted content
        console.print(formatted_output.content)

        # Show metadata for non-table formats
        if output_fmt != OutputFormat.TABLE:
            console.print(f"\n[dim]Output format: {formatted_output.format_type.value}[/dim]")
            console.print(
                f"[dim]Size: {formatted_output.metadata.get('size_bytes', 0)} bytes[/dim]"
            )

    except OutputFormatError as e:
        console.print(f"[red]Error formatting output: {str(e)}[/red]")
        raise typer.Exit(1)


def _display_specific_status_result(result: Any, output_fmt: OutputFormat, check_type: str) -> None:
    """Display specific status check result."""
    if output_fmt == OutputFormat.JSON:
        # Convert result to JSON
        import json
        from dataclasses import asdict

        try:
            result_dict = asdict(result)
            # Handle datetime serialization
            for key, value in result_dict.items():
                if hasattr(value, "isoformat"):
                    result_dict[key] = value.isoformat()

            console.print(json.dumps(result_dict, indent=2, default=str))
        except Exception as e:
            console.print(f"[red]Error formatting JSON: {str(e)}[/red]")
            raise typer.Exit(1)

    elif output_fmt == OutputFormat.CSV:
        # Simple CSV output for specific results
        console.print("Component,Status,Message,Timestamp")
        timestamp = result.timestamp.isoformat() if result.timestamp else "N/A"
        console.print(f"{check_type},{result.status.value},{result.message},{timestamp}")

    else:
        # Table format (default)
        _display_specific_status_table(result, check_type)


def _display_specific_status_table(result: Any, check_type: str) -> None:
    """Display specific status result as a table."""
    # Create status indicator
    status_indicators = {
        StatusLevel.HEALTHY: "✅",
        StatusLevel.WARNING: "⚠️ ",
        StatusLevel.CRITICAL: "❌",
        StatusLevel.CONNECTION_FAILED: "🔌",
    }
    indicator = status_indicators.get(result.status, "❓")

    # Create panel with status information
    lines = []
    lines.append(f"Status: {indicator} {result.status.value}")
    lines.append(f"Message: {result.message}")

    if result.timestamp:
        lines.append(f"Timestamp: {result.timestamp.isoformat()}")

    # Add component-specific details
    if hasattr(result, "details") and result.details:
        lines.append("\nDetails:")
        for key, value in result.details.items():
            lines.append(f"  {key.replace('_', ' ').title()}: {value}")

    # Add errors if present
    if hasattr(result, "errors") and result.errors:
        lines.append("\nErrors:")
        for error in result.errors:
            lines.append(f"  • {error}")

    # Create panel
    panel = Panel(
        "\n".join(lines),
        title=f"[bold blue]{check_type.title()} Status[/bold blue]",
        border_style="blue",
    )

    console.print(panel)
