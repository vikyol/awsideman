"""List backups command for awsideman."""

from datetime import datetime, timedelta
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ...backup_restore.backends import FileSystemStorageBackend, S3StorageBackend
from ...backup_restore.storage import StorageEngine

# BackupFilters not yet implemented, using simple filtering for now
from ...utils.config import Config
from ...utils.validators import validate_profile

console = Console()
config = Config()


def list_backups(
    days: Optional[int] = typer.Option(None, "--days", "-d", help="Show backups from last N days"),
    backup_type: Optional[str] = typer.Option(
        None, "--type", "-t", help="Filter by backup type (full, incremental)"
    ),
    status: Optional[str] = typer.Option(
        None, "--status", "-s", help="Filter by backup status (completed, failed, in_progress)"
    ),
    storage_backend: str = typer.Option(
        "filesystem", "--storage", help="Storage backend: filesystem or s3"
    ),
    storage_path: Optional[str] = typer.Option(
        None, "--storage-path", help="Storage path (directory for filesystem, bucket/prefix for s3)"
    ),
    output_format: str = typer.Option(
        "table", "--format", "-f", help="Output format: table or json"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile to use"),
):
    """List available backups with filtering options.

    Displays a list of all available backups with optional filtering by date,
    type, status, and storage location. Supports both filesystem and S3 storage backends.

    Examples:
        # List all backups
        $ awsideman backup list

        # List backups from last 7 days
        $ awsideman backup list --days 7

        # List only full backups
        $ awsideman backup list --type full

        # List failed backups
        $ awsideman backup list --status failed

        # List backups from S3 storage
        $ awsideman backup list --storage s3 --storage-path my-bucket/backups

        # Output in JSON format
        $ awsideman backup list --format json
    """
    try:
        # Validate profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Initialize storage backend
        if storage_backend.lower() == "filesystem":
            storage_path = storage_path or config.get("backup.storage.filesystem.path", "./backups")
            storage_backend = FileSystemStorageBackend(base_path=storage_path)
        elif storage_backend.lower() == "s3":
            if not storage_path:
                console.print("[red]Error: S3 storage requires --storage-path parameter.[/red]")
                console.print("[yellow]Format: bucket-name/prefix[/yellow]")
                raise typer.Exit(1)

            bucket_name, prefix = (
                storage_path.split("/", 1) if "/" in storage_path else (storage_path, "")
            )
            storage_backend = S3StorageBackend(bucket_name=bucket_name, prefix=prefix)
        else:
            console.print(f"[red]Error: Unsupported storage backend '{storage_backend}'.[/red]")
            console.print("[yellow]Supported backends: filesystem, s3[/yellow]")
            raise typer.Exit(1)

        # Create filters (simplified for now)
        filters = {}

        if days:
            filters["since_date"] = datetime.now() - timedelta(days=days)

        if backup_type:
            if backup_type.lower() not in ["full", "incremental"]:
                console.print(f"[red]Error: Invalid backup type '{backup_type}'.[/red]")
                console.print("[yellow]Valid types: full, incremental[/yellow]")
                raise typer.Exit(1)
            filters["backup_type"] = backup_type

        if status:
            if status.lower() not in ["completed", "failed", "in_progress"]:
                console.print(f"[red]Error: Invalid status '{status}'.[/red]")
                console.print("[yellow]Valid statuses: completed, failed, in_progress[/yellow]")
                raise typer.Exit(1)
            filters["status"] = status

        # Initialize storage engine and list backups
        console.print("[blue]Retrieving backup list...[/blue]")
        storage_engine = StorageEngine(backend=storage_backend)

        backups = storage_engine.list_backups(filters=filters)

        if not backups:
            console.print("[yellow]No backups found matching the specified criteria.[/yellow]")
            return

        # Display results
        if output_format.lower() == "json":

            backup_data = [backup.to_dict() for backup in backups]
            console.print_json(data=backup_data)
        else:
            display_backup_list(backups)

        console.print(f"[green]Found {len(backups)} backup(s)[/green]")

    except Exception as e:
        console.print(f"[red]Error listing backups: {e}[/red]")
        raise typer.Exit(1)


def display_backup_list(backups):
    """Display backup list in a formatted table."""
    table = Table(title="Available Backups")
    table.add_column("Backup ID", style="cyan", no_wrap=True)
    table.add_column("Timestamp", style="white")
    table.add_column("Type", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Size", style="blue")
    table.add_column("Resources", style="magenta")
    table.add_column("Storage", style="white")

    for backup in backups:
        # Format size
        size_str = f"{backup.size_bytes / 1024 / 1024:.2f} MB" if backup.size_bytes else "Unknown"

        # Format timestamp
        timestamp_str = (
            backup.timestamp.strftime("%Y-%m-%d %H:%MM") if backup.timestamp else "Unknown"
        )

        # Format resources count
        resources_str = str(backup.resource_counts) if backup.resource_counts else "Unknown"

        # Determine status color
        status_style = {"completed": "green", "failed": "red", "in_progress": "yellow"}.get(
            backup.status.value, "white"
        )

        table.add_row(
            backup.backup_id,
            timestamp_str,
            backup.backup_type.value,
            f"[{status_style}]{backup.status.value}[/{status_style}]",
            size_str,
            resources_str,
            backup.storage_location or "Default",
        )

    console.print(table)
