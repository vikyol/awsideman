"""List backups command for awsideman."""

from datetime import datetime, timedelta
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ...backup_restore.backends import FileSystemStorageBackend
from ...backup_restore.local_metadata_index import get_global_metadata_index
from ...utils.config import Config
from ...utils.validators import validate_profile

console = Console()
config = Config()


def list_backups(
    days: Optional[int] = typer.Option(None, "--days", "-d", help="Show backups from last N days"),
    backup_type: Optional[str] = typer.Option(
        None, "--type", "-t", help="Filter by backup type: full or incremental"
    ),
    storage_backend: Optional[str] = typer.Option(
        None, "--backend", "-b", help="Filter by storage backend: filesystem or s3"
    ),
    output_format: str = typer.Option(
        "table", "--format", "-f", help="Output format: table or json"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile to use"),
    sync: bool = typer.Option(
        False, "--sync", help="Sync local index with storage backends before listing"
    ),
):
    """List all backups from local metadata index regardless of storage backend.

    This command provides a unified view of all backups stored across different
    storage backends (filesystem and S3) by using a local metadata index.

    Examples:
        # List all backups
        $ awsideman backup list

        # List backups from last 7 days
        $ awsideman backup list --days 7

        # List only S3 backups
        $ awsideman backup list --backend s3

        # Sync and list all backups
        $ awsideman backup list --sync
    """
    try:
        # Get the global metadata index
        metadata_index = get_global_metadata_index()

        # Sync with storage backends if requested
        if sync:
            console.print("[blue]Syncing local metadata index with storage backends...[/blue]")

            # Sync with filesystem backend
            try:
                filesystem_path = config.get("backup.storage.filesystem.path", "./backups")
                filesystem_backend = FileSystemStorageBackend(base_path=filesystem_path)
                metadata_index.sync_with_storage_backend(filesystem_backend, filesystem_path)
            except Exception as e:
                console.print(
                    f"[yellow]Warning: Failed to sync with filesystem backend: {e}[/yellow]"
                )

            # Sync with S3 backends (this would require profile info)
            if profile:
                try:
                    profile_name, profile_data = validate_profile(profile)
                    # Note: S3 sync would require knowing bucket names
                    # This could be enhanced with a config file listing S3 locations
                    console.print("[blue]S3 sync would require bucket configuration[/blue]")
                except Exception as e:
                    console.print(
                        f"[yellow]Warning: Failed to validate profile for S3 sync: {e}[/yellow]"
                    )

        # Create filters
        filters = {}

        if days:
            filters["since_date"] = datetime.now() - timedelta(days=days)

        if backup_type:
            if backup_type.lower() not in ["full", "incremental"]:
                console.print(f"[red]Error: Invalid backup type '{backup_type}'.[/red]")
                console.print("[yellow]Valid types: full, incremental[/yellow]")
                raise typer.Exit(1)
            filters["backup_type"] = backup_type

        if storage_backend:
            if storage_backend.lower() not in ["filesystem", "s3"]:
                console.print(f"[red]Error: Invalid storage backend '{storage_backend}'.[/red]")
                console.print("[yellow]Valid backends: filesystem, s3[/yellow]")
                raise typer.Exit(1)
            filters["storage_backend"] = storage_backend

        # Get backups from local index
        console.print("[blue]Retrieving backup list from local metadata index...[/blue]")
        backups = metadata_index.list_backups(filters=filters)

        if not backups:
            console.print("[yellow]No backups found matching the specified criteria.[/yellow]")

            # Show index stats
            stats = metadata_index.get_index_stats()
            if "total_backups" in stats and stats["total_backups"] > 0:
                console.print(
                    f"[blue]Local index contains {stats['total_backups']} backups total.[/blue]"
                )
                console.print("[blue]Try using --sync to update the local index.[/blue]")
            return

        # Display results
        if output_format.lower() == "json":
            backup_data = []
            for backup in backups:
                backup_dict = backup.to_dict()
                # Add storage location info
                storage_info = metadata_index.get_storage_location(backup.backup_id)
                if storage_info:
                    backup_dict["storage_info"] = storage_info
                backup_data.append(backup_dict)
            console.print_json(data=backup_data)
        else:
            display_unified_backup_list(backups, metadata_index)

        console.print(f"[green]Found {len(backups)} backup(s)[/green]")

        # Show index stats
        stats = metadata_index.get_index_stats()
        if "total_backups" in stats:
            console.print(f"[blue]Total backups in local index: {stats['total_backups']}[/blue]")
            if "by_backend" in stats:
                backend_info = ", ".join([f"{k}: {v}" for k, v in stats["by_backend"].items()])
                console.print(f"[blue]By backend: {backend_info}[/blue]")

    except Exception as e:
        console.print(f"[red]Error listing backups: {e}[/red]")
        raise typer.Exit(1)


def display_unified_backup_list(backups, metadata_index):
    """Display unified backup list in a formatted table."""
    table = Table(title="All Available Backups (Unified View)")
    table.add_column("Backup ID", style="cyan", no_wrap=True)
    table.add_column("Timestamp", style="white")
    table.add_column("Type", style="green")
    table.add_column("Size", style="blue")
    table.add_column("Resources", style="magenta")
    table.add_column("Storage", style="yellow")
    table.add_column("Location", style="white")

    for backup in backups:
        # Format size - only show when it can be calculated
        if backup.backup_type.value == "incremental" and backup.size_bytes == 0:
            size_str = "No changes since last backup"
        elif backup.size_bytes and backup.size_bytes > 0:
            size_str = f"{backup.size_bytes / 1024 / 1024:.2f} MB"
        else:
            size_str = ""  # Don't show size if it can't be calculated

        # Format timestamp
        timestamp_str = (
            backup.timestamp.strftime("%Y-%m-%d %H:%M") if backup.timestamp else "Unknown"
        )

        # Format resources count
        total_resources = sum(backup.resource_counts.values()) if backup.resource_counts else 0
        resources_str = f"{total_resources} items" if total_resources > 0 else "Unknown"

        # Get storage information
        storage_info = metadata_index.get_storage_location(backup.backup_id)
        storage_backend = storage_info.get("backend", "unknown") if storage_info else "unknown"
        storage_location = storage_info.get("location", "unknown") if storage_info else "unknown"

        # Truncate long storage locations for display
        if len(storage_location) > 30:
            storage_location = storage_location[:27] + "..."

        table.add_row(
            backup.backup_id,
            timestamp_str,
            backup.backup_type.value,
            size_str,
            resources_str,
            storage_backend.upper(),
            storage_location,
        )

    console.print(table)
