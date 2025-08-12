"""Status monitoring commands for awsideman."""
import asyncio
from typing import Optional

import typer
from botocore.exceptions import ClientError
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from ..aws_clients.manager import AWSClientManager
from ..utils.config import Config
from ..utils.monitoring_config import MonitoringConfig, MonitoringConfigManager
from ..utils.notification_system import NotificationSystem
from ..utils.orphaned_assignment_detector import OrphanedAssignmentDetector
from ..utils.output_formatters import CSVFormatter, JSONFormatter, OutputFormatError, TableFormatter
from ..utils.resource_inspector import ResourceInspector
from ..utils.status_infrastructure import StatusCheckConfig
from ..utils.status_models import OutputFormat, StatusLevel
from ..utils.status_orchestrator import StatusOrchestrator

app = typer.Typer(
    help="Monitor AWS Identity Center status and health. Check overall system health, provisioning operations, orphaned assignments, and sync status."
)
console = Console()
config = Config()


def validate_profile(profile_name: Optional[str] = None) -> tuple[str, dict]:
    """
    Validate the profile and return profile name and data.

    This function checks if the specified profile exists or uses the default profile.
    It handles cases where no profile is specified and no default profile is set,
    or when the specified profile does not exist.

    Args:
        profile_name: AWS profile name to use

    Returns:
        Tuple of (profile_name, profile_data)

    Raises:
        typer.Exit: If profile validation fails with a clear error message
    """
    # Use the provided profile name or fall back to the default profile
    profile_name = profile_name or config.get("default_profile")

    # Check if a profile name is available
    if not profile_name:
        console.print("[red]Error: No profile specified and no default profile set.[/red]")
        console.print(
            "Use --profile option or set a default profile with 'awsideman profile set-default'."
        )
        raise typer.Exit(1)

    # Get all profiles and check if the specified profile exists
    profiles = config.get("profiles", {})
    if profile_name not in profiles:
        console.print(f"[red]Error: Profile '{profile_name}' does not exist.[/red]")
        console.print("Use 'awsideman profile add' to create a new profile.")
        raise typer.Exit(1)

    # Return the profile name and profile data
    return profile_name, profiles[profile_name]


def validate_sso_instance(profile_data: dict) -> tuple[str, str]:
    """
    Validate the SSO instance configuration and return instance ARN and identity store ID.

    This function checks if the specified profile has an SSO instance configured.
    It handles cases where no SSO instance is configured for the profile and provides
    helpful guidance on how to configure an SSO instance.

    Args:
        profile_data: Profile data dictionary containing configuration

    Returns:
        Tuple of (instance_arn, identity_store_id)

    Raises:
        typer.Exit: If SSO instance validation fails with a clear error message and guidance
    """
    # Get the SSO instance ARN and identity store ID from the profile data
    instance_arn = profile_data.get("sso_instance_arn")
    identity_store_id = profile_data.get("identity_store_id")

    # Check if both the instance ARN and identity store ID are available
    if not instance_arn or not identity_store_id:
        console.print("[red]Error: No SSO instance configured for this profile.[/red]")
        console.print(
            "Use 'awsideman sso set <instance_arn> <identity_store_id>' to configure an SSO instance."
        )
        console.print("You can find available SSO instances with 'awsideman sso list'.")
        raise typer.Exit(1)

    # Return the instance ARN and identity store ID
    return instance_arn, identity_store_id


def validate_output_format(format_str: Optional[str]) -> OutputFormat:
    """
    Validate and convert output format string to OutputFormat enum.

    Args:
        format_str: Output format string ('json', 'csv', 'table', or None)

    Returns:
        OutputFormat: Validated output format enum

    Raises:
        typer.Exit: If format is invalid
    """
    if format_str is None:
        return OutputFormat.TABLE

    format_str = format_str.lower()
    format_mapping = {
        "json": OutputFormat.JSON,
        "csv": OutputFormat.CSV,
        "table": OutputFormat.TABLE,
    }

    if format_str not in format_mapping:
        console.print(f"[red]Error: Invalid output format '{format_str}'.[/red]")
        console.print("Valid formats: json, csv, table")
        raise typer.Exit(1)

    return format_mapping[format_str]


def validate_status_type(status_type: Optional[str]) -> Optional[str]:
    """
    Validate status type parameter.

    Args:
        status_type: Status type string

    Returns:
        str: Validated status type or None for comprehensive check

    Raises:
        typer.Exit: If status type is invalid
    """
    if status_type is None:
        return None

    valid_types = ["health", "provisioning", "orphaned", "sync", "resource", "summary"]
    if status_type not in valid_types:
        console.print(f"[red]Error: Invalid status type '{status_type}'.[/red]")
        console.print(f"Valid types: {', '.join(valid_types)}")
        raise typer.Exit(1)

    return status_type


@app.command("check")
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
        30, "--timeout", help="Timeout for status checks in seconds (default: 30)"
    ),
    parallel: bool = typer.Option(
        True, "--parallel/--sequential", help="Run checks in parallel (default: parallel)"
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="AWS profile to use (uses default profile if not specified)"
    ),
):
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

        # Create status check configuration
        status_config = StatusCheckConfig(
            timeout_seconds=timeout,
            enable_parallel_checks=parallel,
            max_concurrent_checks=5,
            retry_attempts=2,
            retry_delay_seconds=1.0,
        )

        # Initialize the status orchestrator
        orchestrator = StatusOrchestrator(aws_client, status_config)

        # Show progress indicator for long-running operations
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


@app.command("inspect")
def inspect_resource(
    resource_type: str = typer.Argument(
        ..., help="Resource type to inspect: user, group, permission-set"
    ),
    resource_id: str = typer.Argument(..., help="Resource identifier (ID, name, or ARN)"),
    output_format: Optional[str] = typer.Option(
        None, "--format", "-f", help="Output format: json, csv, table (default: table)"
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="AWS profile to use (uses default profile if not specified)"
    ),
):
    """Inspect detailed status of a specific resource.

    Provides detailed status information for individual users, groups, or permission sets.
    Shows resource health, configuration, and suggests similar resources if not found.

    Examples:
        awsideman status inspect user john.doe@example.com
        awsideman status inspect group Administrators
        awsideman status inspect permission-set ReadOnlyAccess
    """
    try:
        # Validate inputs
        output_fmt = validate_output_format(output_format)

        # Validate resource type
        valid_resource_types = ["user", "group", "permission-set"]
        if resource_type not in valid_resource_types:
            console.print(f"[red]Error: Invalid resource type '{resource_type}'.[/red]")
            console.print(f"Valid types: {', '.join(valid_resource_types)}")
            raise typer.Exit(1)

        # Validate the profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Validate the SSO instance and get instance ARN and identity store ID
        instance_arn, identity_store_id = validate_sso_instance(profile_data)

        # Initialize the AWS client manager with the profile and region
        region = profile_data.get("region")
        aws_client = AWSClientManager(profile=profile_name, region=region)

        # Initialize the resource inspector
        inspector = ResourceInspector(aws_client)

        # Show progress indicator
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task(f"Inspecting {resource_type} '{resource_id}'...", total=None)

            # Perform resource inspection based on type
            if resource_type == "user":
                result = asyncio.run(inspector.inspect_user(resource_id))
            elif resource_type == "group":
                result = asyncio.run(inspector.inspect_group(resource_id))
            elif resource_type == "permission-set":
                result = asyncio.run(inspector.inspect_permission_set(resource_id))

            progress.remove_task(task)

        # Format and display result
        _display_resource_inspection_result(result, output_fmt, resource_type, resource_id)

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


@app.command("cleanup")
def cleanup_orphaned(
    dry_run: bool = typer.Option(
        True,
        "--dry-run/--execute",
        help="Show what would be cleaned up without making changes (default: dry-run)",
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompts"),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="AWS profile to use (uses default profile if not specified)"
    ),
):
    """Clean up orphaned permission set assignments.

    Identifies and optionally removes permission set assignments for principals
    that no longer exist in the identity provider. Use --dry-run to preview
    changes before executing.

    Examples:
        awsideman status cleanup --dry-run    # Preview cleanup
        awsideman status cleanup --execute    # Perform cleanup with confirmation
        awsideman status cleanup --execute --force  # Perform cleanup without confirmation
    """
    try:
        # Validate the profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Validate the SSO instance and get instance ARN and identity store ID
        instance_arn, identity_store_id = validate_sso_instance(profile_data)

        # Initialize the AWS client manager with the profile and region
        region = profile_data.get("region")
        aws_client = AWSClientManager(profile=profile_name, region=region)

        # Initialize the orphaned assignment detector
        detector = OrphanedAssignmentDetector(aws_client)

        # Show progress indicator
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Detecting orphaned assignments...", total=None)

            # Detect orphaned assignments
            result = asyncio.run(detector.check_status())

            progress.remove_task(task)

        # Check if any orphaned assignments were found
        if not hasattr(result, "orphaned_assignments") or not result.orphaned_assignments:
            console.print("[green]✅ No orphaned assignments found.[/green]")
            return

        orphaned_count = len(result.orphaned_assignments)
        console.print(f"[yellow]Found {orphaned_count} orphaned assignments.[/yellow]")

        # Display orphaned assignments
        table = Table(title="Orphaned Assignments")
        table.add_column("Permission Set", style="cyan")
        table.add_column("Account", style="blue")
        table.add_column("Principal", style="magenta")
        table.add_column("Type", style="green")
        table.add_column("Age (days)", style="yellow")

        for assignment in result.orphaned_assignments:
            table.add_row(
                assignment.permission_set_name,
                assignment.account_name or assignment.account_id,
                assignment.principal_name or assignment.principal_id,
                assignment.principal_type.value,
                str(assignment.get_age_days()),
            )

        console.print(table)

        if dry_run:
            console.print("\n[blue]This is a dry run. Use --execute to perform the cleanup.[/blue]")
            return

        # Confirm cleanup unless --force is used
        if not force:
            console.print(
                f"\n[yellow]This will permanently remove {orphaned_count} orphaned assignments.[/yellow]"
            )
            confirm = typer.confirm("Are you sure you want to proceed?")
            if not confirm:
                console.print("[blue]Cleanup cancelled.[/blue]")
                return

        # Perform cleanup
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Cleaning up orphaned assignments...", total=None)

            cleanup_result = asyncio.run(
                detector.cleanup_orphaned_assignments(result.orphaned_assignments)
            )

            progress.remove_task(task)

        # Display cleanup results
        if cleanup_result and hasattr(cleanup_result, "cleaned_count"):
            console.print(
                f"[green]✅ Successfully cleaned up {cleanup_result.cleaned_count} orphaned assignments.[/green]"
            )

            if hasattr(cleanup_result, "failed_count") and cleanup_result.failed_count > 0:
                console.print(
                    f"[yellow]⚠️  Failed to clean up {cleanup_result.failed_count} assignments.[/yellow]"
                )

                if hasattr(cleanup_result, "errors") and cleanup_result.errors:
                    console.print("\nErrors encountered:")
                    for error in cleanup_result.errors[:5]:  # Show first 5 errors
                        console.print(f"  • {error}")
        else:
            console.print("[red]❌ Cleanup operation failed.[/red]")

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


def _display_comprehensive_status_report(status_report, output_fmt: OutputFormat) -> None:
    """Display comprehensive status report in the specified format."""
    try:
        # Select appropriate formatter
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


def _display_specific_status_result(result, output_fmt: OutputFormat, check_type: str) -> None:
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


def _display_specific_status_table(result, check_type: str) -> None:
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


def _display_resource_inspection_result(
    result, output_fmt: OutputFormat, resource_type: str, resource_id: str
) -> None:
    """Display resource inspection result."""
    if output_fmt == OutputFormat.JSON:
        # Convert result to JSON
        import json
        from dataclasses import asdict

        try:
            result_dict = asdict(result)
            console.print(json.dumps(result_dict, indent=2, default=str))
        except Exception as e:
            console.print(f"[red]Error formatting JSON: {str(e)}[/red]")
            raise typer.Exit(1)

    elif output_fmt == OutputFormat.CSV:
        # Simple CSV output for resource inspection
        console.print("Resource Type,Resource ID,Status,Found,Message")
        found = "Yes" if result.resource_found() else "No"
        console.print(
            f"{resource_type},{resource_id},{result.status.value},{found},{result.message}"
        )

    else:
        # Table format (default)
        _display_resource_inspection_table(result, resource_type, resource_id)


def _display_resource_inspection_table(result, resource_type: str, resource_id: str) -> None:
    """Display resource inspection result as a table."""
    # Create status indicator
    status_indicators = {
        StatusLevel.HEALTHY: "✅",
        StatusLevel.WARNING: "⚠️ ",
        StatusLevel.CRITICAL: "❌",
        StatusLevel.CONNECTION_FAILED: "🔌",
    }
    indicator = status_indicators.get(result.status, "❓")

    # Create panel with resource information
    lines = []
    lines.append(f"Resource Type: {resource_type}")
    lines.append(f"Resource ID: {resource_id}")
    lines.append(f"Status: {indicator} {result.status.value}")
    lines.append(f"Found: {'Yes' if result.resource_found() else 'No'}")
    lines.append(f"Message: {result.message}")

    if result.timestamp:
        lines.append(f"Inspected: {result.timestamp.isoformat()}")

    # Add resource details if found
    if hasattr(result, "target_resource") and result.target_resource:
        resource = result.target_resource
        lines.append("\nResource Details:")
        lines.append(f"  Name: {resource.resource_name or 'N/A'}")
        lines.append(f"  Status: {resource.status.value}")

        if resource.last_updated:
            lines.append(f"  Last Updated: {resource.last_updated.isoformat()}")

        if resource.configuration:
            lines.append("  Configuration:")
            for key, value in resource.configuration.items():
                lines.append(f"    {key}: {value}")

    # Add suggestions if resource not found
    if result.has_suggestions():
        lines.append("\nSimilar Resources:")
        for suggestion in result.similar_resources[:5]:  # Show up to 5 suggestions
            lines.append(f"  • {suggestion}")

    # Add errors if present
    if hasattr(result, "errors") and result.errors:
        lines.append("\nErrors:")
        for error in result.errors:
            lines.append(f"  • {error}")

    # Create panel
    panel = Panel(
        "\n".join(lines),
        title=f"[bold blue]Resource Inspection: {resource_type}[/bold blue]",
        border_style="blue",
    )

    console.print(panel)


@app.command("monitor")
def monitor_config(
    action: str = typer.Argument(
        ..., help="Action to perform: show, enable, disable, test, schedule"
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="AWS profile to use (uses default profile if not specified)"
    ),
):
    """Configure and manage automated monitoring.

    Actions:
        show     - Display current monitoring configuration
        enable   - Enable monitoring with default settings
        disable  - Disable monitoring
        test     - Test notification systems
        schedule - Show scheduler status

    Examples:
        awsideman status monitor show
        awsideman status monitor enable
        awsideman status monitor test
    """
    try:
        # Initialize configuration manager
        config_manager = MonitoringConfigManager(config)
        monitoring_config = config_manager.get_monitoring_config()

        if action == "show":
            _show_monitoring_config(monitoring_config)
        elif action == "enable":
            _enable_monitoring(config_manager, monitoring_config, profile)
        elif action == "disable":
            _disable_monitoring(config_manager, monitoring_config)
        elif action == "test":
            _test_notifications(monitoring_config)
        elif action == "schedule":
            _show_scheduler_status(monitoring_config)
        else:
            console.print(f"[red]Error: Unknown action '{action}'.[/red]")
            console.print("Valid actions: show, enable, disable, test, schedule")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


def _show_monitoring_config(monitoring_config: MonitoringConfig):
    """Display current monitoring configuration."""
    # Main status
    status_color = "green" if monitoring_config.enabled else "red"
    console.print(
        f"[bold]Monitoring Status:[/bold] [{status_color}]{'Enabled' if monitoring_config.enabled else 'Disabled'}[/{status_color}]"
    )

    if not monitoring_config.enabled:
        console.print(
            "\n[yellow]Use 'awsideman status monitor enable' to enable monitoring.[/yellow]"
        )
        return

    # Profiles
    if monitoring_config.profiles:
        console.print(f"\n[bold]Monitored Profiles:[/bold] {', '.join(monitoring_config.profiles)}")
    else:
        console.print("\n[bold]Monitored Profiles:[/bold] [yellow]All configured profiles[/yellow]")

    # Status types
    console.print(f"[bold]Status Types:[/bold] {', '.join(monitoring_config.status_types)}")

    # Thresholds
    if monitoring_config.thresholds:
        console.print("\n[bold]Thresholds:[/bold]")
        for name, threshold in monitoring_config.thresholds.items():
            status = "✅" if threshold.enabled else "❌"
            console.print(f"  {status} {name.title()}: {threshold.level.value}")

            details = []
            if threshold.orphaned_assignment_count:
                details.append(f"Orphaned assignments ≥ {threshold.orphaned_assignment_count}")
            if threshold.provisioning_failure_count:
                details.append(f"Provisioning failures ≥ {threshold.provisioning_failure_count}")
            if threshold.sync_delay_hours:
                details.append(f"Sync delay ≥ {threshold.sync_delay_hours}h")

            if details:
                console.print(f"    Triggers: {', '.join(details)}")

    # Notifications
    console.print("\n[bold]Notifications:[/bold]")

    if monitoring_config.email_notifications:
        status = "✅" if monitoring_config.email_notifications.enabled else "❌"
        console.print(f"  {status} Email: {monitoring_config.email_notifications.smtp_server}")
        if (
            monitoring_config.email_notifications.enabled
            and monitoring_config.email_notifications.to_addresses
        ):
            console.print(
                f"    Recipients: {', '.join(monitoring_config.email_notifications.to_addresses)}"
            )

    if monitoring_config.webhook_notifications:
        status = "✅" if monitoring_config.webhook_notifications.enabled else "❌"
        console.print(f"  {status} Webhook: {monitoring_config.webhook_notifications.url}")

    if monitoring_config.log_notifications:
        status = "✅" if monitoring_config.log_notifications.enabled else "❌"
        log_dest = monitoring_config.log_notifications.log_file or "console"
        console.print(f"  {status} Log: {log_dest}")

    # Schedule
    if monitoring_config.schedule:
        console.print("\n[bold]Schedule:[/bold]")
        status = "✅" if monitoring_config.schedule.enabled else "❌"
        console.print(
            f"  {status} Automated checks: Every {monitoring_config.schedule.interval_minutes} minutes"
        )

        if monitoring_config.schedule.enabled:
            console.print(f"    Max concurrent: {monitoring_config.schedule.max_concurrent_checks}")
            console.print(f"    Timeout: {monitoring_config.schedule.timeout_seconds}s")
            console.print(
                f"    Retry on failure: {'Yes' if monitoring_config.schedule.retry_on_failure else 'No'}"
            )


def _enable_monitoring(
    config_manager: MonitoringConfigManager,
    monitoring_config: MonitoringConfig,
    profile: Optional[str],
):
    """Enable monitoring with default or specified configuration."""
    if monitoring_config.enabled:
        console.print("[yellow]Monitoring is already enabled.[/yellow]")
        return

    # Enable monitoring
    monitoring_config.enabled = True

    # Set profile if specified
    if profile:
        monitoring_config.profiles = [profile]

    # Enable basic log notifications by default
    if not monitoring_config.log_notifications:
        from ..utils.monitoring_config import LogNotificationConfig

        monitoring_config.log_notifications = LogNotificationConfig(enabled=True)

    # Save configuration
    config_manager.save_monitoring_config(monitoring_config)

    console.print("[green]✅ Monitoring enabled successfully![/green]")
    console.print("\n[blue]Next steps:[/blue]")
    console.print("1. Configure notifications: Edit ~/.awsideman/config.yaml")
    console.print("2. Test notifications: awsideman status monitor test")
    console.print("3. Enable scheduling: Set monitoring.schedule.enabled = true in config")
    console.print("4. View configuration: awsideman status monitor show")


def _disable_monitoring(
    config_manager: MonitoringConfigManager, monitoring_config: MonitoringConfig
):
    """Disable monitoring."""
    if not monitoring_config.enabled:
        console.print("[yellow]Monitoring is already disabled.[/yellow]")
        return

    # Confirm disable
    confirm = typer.confirm("Are you sure you want to disable monitoring?")
    if not confirm:
        console.print("[blue]Monitoring disable cancelled.[/blue]")
        return

    # Disable monitoring
    monitoring_config.enabled = False
    config_manager.save_monitoring_config(monitoring_config)

    console.print("[green]✅ Monitoring disabled successfully.[/green]")


def _test_notifications(monitoring_config: MonitoringConfig):
    """Test notification systems."""
    if not monitoring_config.enabled:
        console.print("[red]Error: Monitoring is disabled. Enable monitoring first.[/red]")
        raise typer.Exit(1)

    # Check if any notifications are configured
    has_notifications = (
        (monitoring_config.email_notifications and monitoring_config.email_notifications.enabled)
        or (
            monitoring_config.webhook_notifications
            and monitoring_config.webhook_notifications.enabled
        )
        or (monitoring_config.log_notifications and monitoring_config.log_notifications.enabled)
    )

    if not has_notifications:
        console.print("[yellow]No notification methods are configured and enabled.[/yellow]")
        console.print("Configure notifications in ~/.awsideman/config.yaml")
        return

    console.print("[blue]Testing notification systems...[/blue]")

    # Test notifications
    notification_system = NotificationSystem(monitoring_config)

    with console.status("Sending test notifications..."):
        results = asyncio.run(notification_system.test_notifications())

    # Display results
    console.print("\n[bold]Test Results:[/bold]")

    for notification_type, success in results.items():
        status = "✅" if success else "❌"
        result = "Success" if success else "Failed"
        console.print(f"  {status} {notification_type.title()}: {result}")

    if all(results.values()):
        console.print("\n[green]All notification tests passed![/green]")
    else:
        console.print("\n[yellow]Some notification tests failed. Check logs for details.[/yellow]")


def _show_scheduler_status(monitoring_config: MonitoringConfig):
    """Show scheduler status."""
    if not monitoring_config.enabled:
        console.print("[red]Monitoring is disabled.[/red]")
        return

    if not monitoring_config.schedule or not monitoring_config.schedule.enabled:
        console.print("[yellow]Scheduled monitoring is disabled.[/yellow]")
        console.print("Enable scheduling in ~/.awsideman/config.yaml:")
        console.print("  monitoring:")
        console.print("    schedule:")
        console.print("      enabled: true")
        console.print("      interval_minutes: 60")
        return

    console.print("[bold]Scheduler Configuration:[/bold]")
    console.print("  Status: [green]Enabled[/green]")
    console.print(f"  Interval: {monitoring_config.schedule.interval_minutes} minutes")
    console.print(f"  Max concurrent checks: {monitoring_config.schedule.max_concurrent_checks}")
    console.print(f"  Timeout: {monitoring_config.schedule.timeout_seconds} seconds")
    console.print(
        f"  Retry on failure: {'Yes' if monitoring_config.schedule.retry_on_failure else 'No'}"
    )

    console.print("\n[blue]To run the scheduler as a service:[/blue]")
    console.print("  python -m awsideman.utils.monitoring_scheduler")

    console.print("\n[blue]To run a manual check:[/blue]")
    console.print("  awsideman status check --profile <profile_name>")
