"""Schedule management commands for backup operations.

This module provides CLI commands for creating, updating, deleting, and managing
backup schedules with cron-based scheduling and notification support.
"""

import asyncio
from typing import Dict, List, Optional

import typer
from rich.console import Console
from rich.table import Table

from ...backup_restore.backends import FileSystemStorageBackend, S3StorageBackend
from ...backup_restore.models import (
    BackupType,
    NotificationSettings,
    ResourceType,
    RetentionPolicy,
    ScheduleConfig,
)
from ...backup_restore.schedule_manager import ScheduleManager
from ...backup_restore.storage import StorageEngine
from ...utils.config import Config
from ...utils.validators import validate_profile

console = Console()
config = Config()


def create_schedule(
    name: str = typer.Option(..., "--name", "-n", help="Name for the backup schedule"),
    interval: str = typer.Option(
        "daily",
        "--interval",
        "-i",
        help="Schedule interval: daily, weekly, monthly, hourly, or cron expression",
    ),
    backup_type: str = typer.Option(
        "full", "--type", "-t", help="Backup type: full or incremental"
    ),
    resources: Optional[str] = typer.Option(
        None,
        "--resources",
        "-r",
        help="Comma-separated list of resources to backup (users,groups,permission_sets,assignments,all)",
    ),
    storage_backend: str = typer.Option(
        "filesystem", "--storage", help="Storage backend: filesystem or s3"
    ),
    storage_path: Optional[str] = typer.Option(
        None, "--storage-path", help="Storage path (directory for filesystem, bucket/prefix for s3)"
    ),
    keep_daily: int = typer.Option(7, "--keep-daily", help="Number of daily backups to retain"),
    keep_weekly: int = typer.Option(4, "--keep-weekly", help="Number of weekly backups to retain"),
    keep_monthly: int = typer.Option(
        12, "--keep-monthly", help="Number of monthly backups to retain"
    ),
    keep_yearly: int = typer.Option(3, "--keep-yearly", help="Number of yearly backups to retain"),
    notify_email: Optional[List[str]] = typer.Option(
        None,
        "--notify-email",
        help="Email addresses for notifications (can be used multiple times)",
    ),
    notify_webhook: Optional[List[str]] = typer.Option(
        None, "--notify-webhook", help="Webhook URLs for notifications (can be used multiple times)"
    ),
    enabled: bool = typer.Option(
        True, "--enabled/--disabled", help="Enable or disable the schedule"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile to use"),
):
    """Create a new backup schedule.

    Creates a new backup schedule with configurable intervals, retention policies,
    and notification settings. Schedules can be set to run automatically at specified
    intervals or use cron expressions for complex scheduling.

    Examples:
        # Create a daily backup schedule
        $ awsideman backup schedule create --name "daily-backup" --interval daily

        # Create a weekly backup with notifications
        $ awsideman backup schedule create --name "weekly-backup" --interval weekly --notify-email admin@company.com

        # Create a monthly backup with custom retention
        $ awsideman backup schedule create --name "monthly-backup" --interval monthly --keep-monthly 6

        # Create a cron-based schedule
        $ awsideman backup schedule create --name "custom-schedule" --interval "0 2 * * 0" --backup-type full
    """
    try:
        # Validate profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Parse resource types
        resource_types = []
        if resources:
            resource_list = [r.strip().lower() for r in resources.split(",")]
            for resource in resource_list:
                if resource == "all":
                    resource_types = [
                        ResourceType.USERS,
                        ResourceType.GROUPS,
                        ResourceType.PERMISSION_SETS,
                        ResourceType.ASSIGNMENTS,
                    ]
                    break
                elif resource == "users":
                    resource_types.append(ResourceType.USERS)
                elif resource == "groups":
                    resource_types.append(ResourceType.GROUPS)
                elif resource == "permission_sets":
                    resource_types.append(ResourceType.PERMISSION_SETS)
                elif resource == "assignments":
                    resource_types.append(ResourceType.ASSIGNMENTS)
                else:
                    console.print(f"[red]Error: Invalid resource type '{resource}'.[/red]")
                    console.print(
                        "[yellow]Valid resource types: users, groups, permission_sets, assignments, all[/yellow]"
                    )
                    raise typer.Exit(1)

        # Validate backup type
        if backup_type.lower() not in ["full", "incremental"]:
            console.print(f"[red]Error: Invalid backup type '{backup_type}'.[/red]")
            console.print("[yellow]Valid types: full, incremental[/yellow]")
            raise typer.Exit(1)

        # Initialize components
        storage_backend_obj = _initialize_storage_backend(
            storage_backend, storage_path, profile_name, profile_data
        )
        storage_engine = StorageEngine(backend=storage_backend_obj)
        schedule_manager = ScheduleManager(storage_engine=storage_engine)

        # Create schedule configuration
        schedule_config = ScheduleConfig(
            name=name,
            interval=interval,
            backup_type=(
                BackupType.FULL if backup_type.lower() == "full" else BackupType.INCREMENTAL
            ),
            resource_types=resource_types if resource_types else None,
            storage_backend=storage_backend,
            storage_path=storage_path,
            retention_policy=RetentionPolicy(
                keep_daily=keep_daily,
                keep_weekly=keep_weekly,
                keep_monthly=keep_monthly,
                keep_yearly=keep_yearly,
                auto_cleanup=True,
            ),
            notification_settings=NotificationSettings(
                email_addresses=notify_email or [], webhook_urls=notify_webhook or []
            ),
            enabled=enabled,
        )

        # Create the schedule
        console.print(f"[blue]Creating backup schedule '{name}'...[/blue]")
        schedule_id = asyncio.run(schedule_manager.create_schedule(schedule_config))

        console.print(f"[green]✓ Backup schedule '{name}' created successfully![/green]")
        console.print(f"[blue]Schedule ID: {schedule_id}[/blue]")

    except Exception as e:
        console.print(f"[red]Error creating schedule: {e}[/red]")
        raise typer.Exit(1)


def update_schedule(
    schedule_id: str = typer.Argument(..., help="Schedule ID to update"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="New name for the schedule"),
    interval: Optional[str] = typer.Option(None, "--interval", "-i", help="New schedule interval"),
    enabled: Optional[bool] = typer.Option(
        None, "--enabled/--disabled", help="Enable or disable the schedule"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile to use"),
):
    """Update an existing backup schedule.

    Updates the configuration of an existing backup schedule. Only specified
    parameters will be updated; others will remain unchanged.

    Examples:
        # Update schedule name
        $ awsideman backup schedule update schedule-123 --name "new-name"

        # Update schedule interval
        $ awsideman backup schedule update schedule-123 --interval weekly

        # Disable a schedule
        $ awsideman backup schedule update schedule-123 --disabled
    """
    try:
        # Validate profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Initialize components
        storage_engine = StorageEngine()
        schedule_manager = ScheduleManager(storage_engine=storage_engine)

        # Get current schedule
        console.print(f"[blue]Updating schedule: {schedule_id}[/blue]")

        try:
            current_schedule = asyncio.run(schedule_manager.get_schedule(schedule_id))
        except Exception as e:
            console.print(f"[red]Error: Schedule '{schedule_id}' not found.[/red]")
            console.print(f"[yellow]Details: {e}[/yellow]")
            raise typer.Exit(1)

        # Update configuration
        if name:
            current_schedule.name = name
        if interval:
            current_schedule.interval = interval
        if enabled is not None:
            current_schedule.enabled = enabled

        # Apply updates
        success = asyncio.run(schedule_manager.update_schedule(schedule_id, current_schedule))

        if success:
            console.print(f"[green]✓ Schedule '{schedule_id}' updated successfully![/green]")
        else:
            console.print(f"[red]✗ Failed to update schedule '{schedule_id}'.[/red]")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]Error updating schedule: {e}[/red]")
        raise typer.Exit(1)


def delete_schedule(
    schedule_id: str = typer.Argument(..., help="Schedule ID to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile to use"),
):
    """Delete a backup schedule.

    Removes a backup schedule and stops all future executions. This operation
    cannot be undone, so use with caution.

    Examples:
        # Delete a schedule with confirmation
        $ awsideman backup schedule delete schedule-123

        # Delete without confirmation
        $ awsideman backup schedule delete schedule-123 --force
    """
    try:
        # Validate profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Initialize components
        storage_engine = StorageEngine()
        schedule_manager = ScheduleManager(storage_engine=storage_engine)

        # Get schedule details
        console.print(f"[blue]Deleting schedule: {schedule_id}[/blue]")

        try:
            schedule = asyncio.run(schedule_manager.get_schedule(schedule_id))
        except Exception as e:
            console.print(f"[red]Error: Schedule '{schedule_id}' not found.[/red]")
            console.print(f"[yellow]Details: {e}[/yellow]")
            raise typer.Exit(1)

        # Display schedule information
        console.print("[blue]Found schedule:[/blue]")
        console.print(f"  ID: {schedule.schedule_id}")
        console.print(f"  Name: {schedule.name}")
        console.print(f"  Interval: {schedule.interval}")
        console.print(f"  Status: {'Enabled' if schedule.enabled else 'Disabled'}")

        # Confirmation prompt
        if not force:
            from rich.prompt import Confirm

            if not Confirm.ask(f"Are you sure you want to delete schedule '{schedule_id}'?"):
                console.print("[blue]Operation cancelled.[/blue]")
                return

        # Delete the schedule
        success = asyncio.run(schedule_manager.delete_schedule(schedule_id))

        if success:
            console.print(f"[green]✓ Schedule '{schedule_id}' deleted successfully![/green]")
        else:
            console.print(f"[red]✗ Failed to delete schedule '{schedule_id}'.[/red]")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]Error deleting schedule: {e}[/red]")
        raise typer.Exit(1)


def list_schedules(
    output_format: str = typer.Option(
        "table", "--format", "-f", help="Output format: table or json"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile to use"),
):
    """List all backup schedules.

    Displays all configured backup schedules with their current status and
    configuration details.

    Examples:
        # List all schedules
        $ awsideman backup schedule list

        # Output in JSON format
        $ awsideman backup schedule list --format json
    """
    try:
        # Validate profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Initialize components
        storage_engine = StorageEngine()
        schedule_manager = ScheduleManager(storage_engine=storage_engine)

        # Get schedules
        console.print("[blue]Retrieving backup schedules...[/blue]")
        schedules = asyncio.run(schedule_manager.list_schedules())

        if not schedules:
            console.print("[yellow]No backup schedules found.[/yellow]")
            return

        # Display results
        if output_format.lower() == "json":

            schedule_data = [schedule.to_dict() for schedule in schedules]
            console.print_json(data=schedule_data)
        else:
            display_schedule_list(schedules)

        console.print(f"[green]Found {len(schedules)} schedule(s)[/green]")

    except Exception as e:
        console.print(f"[red]Error listing schedules: {e}[/red]")
        raise typer.Exit(1)


def run_schedule(
    schedule_id: str = typer.Argument(..., help="Schedule ID to run"),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile to use"),
):
    """Manually run a scheduled backup.

    Executes a backup according to the specified schedule configuration.
    This is useful for testing schedules or running backups outside of
    the normal schedule.

    Examples:
        # Run a scheduled backup
        $ awsideman backup schedule run schedule-123
    """
    try:
        # Validate profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Initialize components
        storage_engine = StorageEngine()
        schedule_manager = ScheduleManager(storage_engine=storage_engine)

        # Run the schedule
        console.print(f"[blue]Running scheduled backup: {schedule_id}[/blue]")

        try:
            backup_result = asyncio.run(schedule_manager.execute_scheduled_backup(schedule_id))
            console.print("[green]✓ Scheduled backup completed successfully![/green]")
            console.print(f"[blue]Backup ID: {backup_result.backup_id}[/blue]")
        except Exception as e:
            console.print(f"[red]Error running scheduled backup: {e}[/red]")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


def get_schedule_status(
    schedule_id: str = typer.Argument(..., help="Schedule ID to check"),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile to use"),
):
    """Get detailed status of a specific schedule.

    Displays detailed information about a backup schedule including its
    configuration, last execution status, and next scheduled run.

    Examples:
        # Get schedule status
        $ awsideman backup schedule status schedule-123
    """
    try:
        # Validate profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Initialize components
        storage_engine = StorageEngine()
        schedule_manager = ScheduleManager(storage_engine=storage_engine)

        # Get schedule status
        console.print(f"[blue]Getting schedule status: {schedule_id}[/blue]")

        try:
            schedule_status = asyncio.run(schedule_manager.get_schedule_status(schedule_id))
            display_schedule_status(schedule_status)
        except Exception as e:
            console.print(f"[red]Error getting schedule status: {e}[/red]")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


def _initialize_storage_backend(
    storage_backend: str,
    storage_path: Optional[str],
    profile_name: Optional[str] = None,
    profile_data: Optional[Dict] = None,
):
    """Initialize storage backend based on configuration."""
    if storage_backend.lower() == "filesystem":
        storage_path = storage_path or config.get("backup.storage.filesystem.path", "./backups")
        return FileSystemStorageBackend(base_path=storage_path, profile=profile_name)
    elif storage_backend.lower() == "s3":
        if not storage_path:
            console.print("[red]Error: S3 storage requires --storage-path parameter.[/red]")
            console.print("[yellow]Format: bucket-name/prefix[/yellow]")
            raise typer.Exit(1)

        bucket_name, prefix = (
            storage_path.split("/", 1) if "/" in storage_path else (storage_path, "")
        )

        # Configure S3 backend with profile support
        s3_config = {"bucket_name": bucket_name, "prefix": prefix, "profile": profile_name}

        # Use profile name for SSO and named profiles
        if profile_name:
            s3_config["profile_name"] = profile_name

        # Add region from profile data if available
        if profile_data and "region" in profile_data:
            s3_config["region_name"] = profile_data["region"]

        return S3StorageBackend(**s3_config)
    else:
        console.print(f"[red]Error: Unsupported storage backend '{storage_backend}'.[/red]")
        console.print("[yellow]Supported backends: filesystem, s3[/yellow]")
        raise typer.Exit(1)


def display_schedule_list(schedules):
    """Display schedule list in a formatted table."""
    table = Table(title="Backup Schedules")
    table.add_column("Schedule ID", style="cyan", no_wrap=True)
    table.add_column("Name", style="white")
    table.add_column("Interval", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("Status", style="blue")
    table.add_column("Last Run", style="magenta")
    table.add_column("Next Run", style="white")

    for schedule in schedules:
        # Format status
        status_style = "[green]Enabled[/green]" if schedule.enabled else "[red]Disabled[/red]"

        # Format timestamps
        last_run = (
            schedule.last_execution.strftime("%Y-%m-%d %H:%M")
            if schedule.last_execution
            else "Never"
        )
        next_run = (
            schedule.next_execution.strftime("%Y-%m-%d %H:%M") if schedule.next_execution else "N/A"
        )

        table.add_row(
            schedule.schedule_id,
            schedule.name,
            schedule.interval,
            schedule.backup_type.value,
            status_style,
            last_run,
            next_run,
        )

    console.print(table)


def display_schedule_status(schedule_status):
    """Display schedule status in a formatted table."""
    table = Table(title="Schedule Status")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Schedule ID", schedule_status.schedule_id)
    table.add_row("Name", schedule_status.name)
    table.add_row("Interval", schedule_status.interval)
    table.add_row("Backup Type", schedule_status.backup_type.value)
    table.add_row(
        "Status", "[green]Enabled[/green]" if schedule_status.enabled else "[red]Disabled[/red]"
    )
    table.add_row(
        "Last Execution",
        str(schedule_status.last_execution) if schedule_status.last_execution else "Never",
    )
    table.add_row(
        "Next Execution",
        str(schedule_status.next_execution) if schedule_status.next_execution else "N/A",
    )
    table.add_row("Execution Count", str(schedule_status.execution_count))
    table.add_row("Success Count", str(schedule_status.success_count))
    table.add_row("Failure Count", str(schedule_status.failure_count))

    console.print(table)
