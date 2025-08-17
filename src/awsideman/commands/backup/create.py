"""Create backup command for awsideman."""

import asyncio
from datetime import datetime
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from ...backup_restore.backends import FileSystemStorageBackend, S3StorageBackend
from ...backup_restore.collector import IdentityCenterCollector
from ...backup_restore.manager import BackupManager
from ...backup_restore.models import BackupOptions, BackupType, ResourceType
from ...backup_restore.storage import StorageEngine
from ...utils.config import Config
from ...utils.validators import validate_profile

console = Console()
config = Config()


def create_backup(
    backup_type: str = typer.Option(
        "full", "--type", "-t", help="Backup type: full or incremental"
    ),
    resources: Optional[str] = typer.Option(
        None,
        "--resources",
        "-r",
        help="Comma-separated list of resources to backup (users,groups,permission_sets,assignments,all)",
    ),
    since: Optional[str] = typer.Option(
        None,
        "--since",
        "-s",
        help="For incremental backups: start date (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)",
    ),
    storage_backend: str = typer.Option(
        "filesystem", "--storage", help="Storage backend: filesystem or s3"
    ),
    storage_path: Optional[str] = typer.Option(
        None, "--storage-path", help="Storage path (directory for filesystem, bucket/prefix for s3)"
    ),
    no_encryption: bool = typer.Option(False, "--no-encryption", help="Disable backup encryption"),
    no_compression: bool = typer.Option(
        False, "--no-compression", help="Disable backup compression"
    ),
    include_inactive: bool = typer.Option(
        False, "--include-inactive", help="Include inactive users in backup"
    ),
    output_format: str = typer.Option(
        "table", "--format", "-f", help="Output format: table or json"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile to use"),
):
    """Create a new backup of AWS Identity Center configuration.

    Creates a comprehensive backup of AWS Identity Center resources including
    users, groups, permission sets, and assignments. Supports both full and
    incremental backup modes with configurable storage backends and encryption.

    Examples:
        # Create a full backup
        $ awsideman backup create

        # Create an incremental backup
        $ awsideman backup create --type incremental --since 2024-01-01

        # Create backup with specific resources
        $ awsideman backup create --resources users,groups

        # Create backup with custom storage
        $ awsideman backup create --storage s3 --storage-path my-bucket/backups

        # Create unencrypted backup (not recommended for production)
        $ awsideman backup create --no-encryption
    """
    try:
        # Validate input parameters
        if backup_type.lower() not in ["full", "incremental"]:
            console.print(f"[red]Error: Invalid backup type '{backup_type}'.[/red]")
            console.print("[yellow]Backup type must be either 'full' or 'incremental'.[/yellow]")
            raise typer.Exit(1)

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

        # Parse since date for incremental backups
        since_date = None
        if backup_type.lower() == "incremental":
            if not since:
                console.print("[red]Error: Incremental backup requires --since parameter.[/red]")
                raise typer.Exit(1)

            try:
                # Try different date formats
                for fmt in ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S"]:
                    try:
                        since_date = datetime.strptime(since, fmt)
                        break
                    except ValueError:
                        continue

                if not since_date:
                    console.print(f"[red]Error: Invalid date format '{since}'.[/red]")
                    console.print("[yellow]Use format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS[/yellow]")
                    raise typer.Exit(1)
            except Exception as e:
                console.print(f"[red]Error parsing date: {e}[/red]")
                raise typer.Exit(1)

        # Validate profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Initialize backup components
        console.print("[blue]Initializing backup components...[/blue]")

        # Create backup options
        backup_options = BackupOptions(
            backup_type=(
                BackupType.FULL if backup_type.lower() == "full" else BackupType.INCREMENTAL
            ),
            resource_types=resource_types if resource_types else [ResourceType.ALL],
            since=since_date,
            include_inactive_users=include_inactive,
            encryption_enabled=not no_encryption,
            compression_enabled=not no_compression,
        )

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

        # Initialize managers
        storage_engine = StorageEngine(backend=storage_backend)
        backup_manager = BackupManager(storage_engine=storage_engine)
        collector = IdentityCenterCollector(profile=profile_name, region=profile_data.get("region"))

        # Start backup process
        console.print(f"[blue]Starting {backup_type} backup...[/blue]")

        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
        ) as progress:
            task = progress.add_task("Creating backup...", total=None)

            # Execute backup
            backup_result = asyncio.run(
                backup_manager.create_backup(collector=collector, options=backup_options)
            )

            progress.update(task, description="Backup completed successfully!")

        # Display results
        if output_format.lower() == "json":
            console.print_json(data=backup_result.to_dict())
        else:
            display_backup_results(backup_result)

        console.print("[green]Backup completed successfully![/green]")
        console.print(f"[blue]Backup ID: {backup_result.backup_id}[/blue]")
        console.print(f"[blue]Storage location: {backup_result.storage_location}[/blue]")

    except Exception as e:
        console.print(f"[red]Error creating backup: {e}[/red]")
        raise typer.Exit(1)


def display_backup_results(backup_result):
    """Display backup results in a formatted table."""
    table = Table(title="Backup Results")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Backup ID", backup_result.backup_id)
    table.add_row("Timestamp", str(backup_result.timestamp))
    table.add_row("Type", backup_result.backup_type.value)
    table.add_row("Status", backup_result.status.value)
    table.add_row("Storage Location", backup_result.storage_location)
    table.add_row("Size", f"{backup_result.size_bytes / 1024 / 1024:.2f} MB")
    table.add_row("Resources", str(backup_result.resource_counts))

    console.print(table)
