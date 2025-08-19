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
            backend_instance = FileSystemStorageBackend(base_path=storage_path)
        elif storage_backend.lower() == "s3":
            if not storage_path:
                console.print("[red]Error: S3 storage requires --storage-path parameter.[/red]")
                console.print("[yellow]Format: bucket-name/prefix[/yellow]")
                raise typer.Exit(1)

            bucket_name, prefix = (
                storage_path.split("/", 1) if "/" in storage_path else (storage_path, "")
            )
            # Configure S3 backend with profile support
            s3_config = {"bucket_name": bucket_name, "prefix": prefix}

            # Use profile name for SSO and named profiles
            if profile_name:
                s3_config["profile_name"] = profile_name

            # Add region from profile data if available
            if profile_data and "region" in profile_data:
                s3_config["region_name"] = profile_data["region"]

            backend_instance = S3StorageBackend(**s3_config)
        else:
            console.print(f"[red]Error: Unsupported storage backend '{storage_backend}'.[/red]")
            console.print("[yellow]Supported backends: filesystem, s3[/yellow]")
            raise typer.Exit(1)

        # Initialize managers
        storage_engine = StorageEngine(backend=backend_instance)

        # Create AWS client manager for the collector
        from ...aws_clients.manager import AWSClientManager

        aws_client = AWSClientManager(profile=profile_name, region=profile_data.get("region"))

        # Get SSO instance information for the collector
        try:
            sso_client = aws_client.get_identity_center_client()
            instances = sso_client.list_instances()
            console.print(f"[blue]Found {len(instances.get('Instances', []))} SSO instances[/blue]")

            if not instances.get("Instances"):
                console.print("[red]Error: No SSO instances found. Cannot create backup.[/red]")
                raise typer.Exit(1)

            instance_arn = instances["Instances"][0]["InstanceArn"]
            console.print(f"[blue]Using SSO instance: {instance_arn}[/blue]")

            collector = IdentityCenterCollector(
                client_manager=aws_client, instance_arn=instance_arn
            )
        except Exception as e:
            console.print(f"[red]Error getting SSO instance: {e}[/red]")
            raise typer.Exit(1)

        # Get the current AWS account ID
        try:
            sts_client = aws_client.get_client("sts")
            account_info = sts_client.get_caller_identity()
            source_account = account_info.get("Account", "")
            console.print(f"[blue]Using AWS account: {source_account}[/blue]")
        except Exception as e:
            console.print(f"[yellow]Warning: Could not determine AWS account ID: {e}[/yellow]")
            source_account = "unknown"

        # Create backup manager with required collector, storage_engine, and instance_arn
        backup_manager = BackupManager(
            collector=collector,
            storage_engine=storage_engine,
            instance_arn=instance_arn,
            source_account=source_account,
            source_region=profile_data.get("region", ""),
        )

        # Start backup process
        console.print(f"[blue]Starting {backup_type} backup...[/blue]")

        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
        ) as progress:
            task = progress.add_task("Creating backup...", total=None)

            # Execute backup
            backup_result = asyncio.run(backup_manager.create_backup(options=backup_options))

            progress.update(task, description="Backup completed successfully!")

        # Store metadata in local index for unified access
        if backup_result.success and backup_result.backup_id:
            try:
                from ...backup_restore.local_metadata_index import get_global_metadata_index

                metadata_index = get_global_metadata_index()

                # Get the created backup metadata
                backup_metadata = asyncio.run(
                    backup_manager.get_backup_metadata(backup_result.backup_id)
                )
                if backup_metadata:
                    # Determine storage backend and location
                    backend_type = "filesystem" if storage_backend.lower() == "filesystem" else "s3"
                    backend_location = storage_path or (
                        "./backups" if backend_type == "filesystem" else ""
                    )

                    # Add storage info to metadata
                    backup_metadata.storage_backend = backend_type
                    backup_metadata.storage_location = backend_location

                    # Store in local index
                    metadata_index.add_backup_metadata(
                        backup_result.backup_id, backup_metadata, backend_type, backend_location
                    )
                    console.print("[blue]Backup metadata added to local index[/blue]")
            except Exception as e:
                console.print(f"[yellow]Warning: Failed to add backup to local index: {e}[/yellow]")

        # Display results
        if output_format.lower() == "json":
            console.print_json(data=backup_result.to_dict())
        else:
            display_backup_results(backup_result)

        if backup_result.success:
            if backup_result.backup_id:
                # Backup was actually created
                console.print("[green]Backup completed successfully![/green]")
                console.print(f"[blue]Backup ID: {backup_result.backup_id}[/blue]")
                if backup_result.metadata and hasattr(backup_result.metadata, "size_bytes"):
                    if (
                        backup_result.metadata.backup_type.value == "incremental"
                        and backup_result.metadata.size_bytes == 0
                    ):
                        console.print("[blue]Status: No changes detected since last backup[/blue]")
                    elif backup_result.metadata.size_bytes > 0:
                        console.print(
                            f"[blue]Size: {backup_result.metadata.size_bytes / 1024 / 1024:.2f} MB[/blue]"
                        )
                    else:
                        console.print("[blue]Size: Unknown[/blue]")
            else:
                # Backup was skipped (no changes)
                console.print("[blue]No changes detected since last backup[/blue]")
                console.print("[green]Incremental backup skipped successfully![/green]")
                if backup_result.warnings:
                    for warning in backup_result.warnings:
                        console.print(f"[yellow]Note: {warning}[/yellow]")
        else:
            console.print("[red]Backup failed![/red]")
            if backup_result.errors:
                for error in backup_result.errors:
                    console.print(f"[red]Error: {error}[/red]")

    except Exception as e:
        console.print(f"[red]Error creating backup: {e}[/red]")
        raise typer.Exit(1)


def display_backup_results(backup_result):
    """Display backup results in a formatted table."""
    if not backup_result.backup_id:
        # No backup was created (e.g., incremental with no changes)
        console.print("[blue]No backup created - no changes detected[/blue]")
        return

    table = Table(title="Backup Results")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Backup ID", str(backup_result.backup_id or "N/A"))

    if backup_result.metadata and hasattr(backup_result.metadata, "timestamp"):
        table.add_row("Timestamp", str(backup_result.metadata.timestamp))
    else:
        table.add_row("Timestamp", "N/A")

    if backup_result.metadata and hasattr(backup_result.metadata, "backup_type"):
        table.add_row("Type", str(backup_result.metadata.backup_type.value))
    else:
        table.add_row("Type", "N/A")

    table.add_row("Status", "Success" if backup_result.success else "Failed")

    if backup_result.metadata and hasattr(backup_result.metadata, "size_bytes"):
        if (
            backup_result.metadata.backup_type.value == "incremental"
            and backup_result.metadata.size_bytes == 0
        ):
            table.add_row("Size", "No changes since last backup")
        elif backup_result.metadata.size_bytes > 0:
            table.add_row("Size", f"{backup_result.metadata.size_bytes / 1024 / 1024:.2f} MB")
        else:
            table.add_row("Size", "Unknown")
    else:
        table.add_row("Size", "N/A")

    if backup_result.metadata and hasattr(backup_result.metadata, "resource_counts"):
        table.add_row("Resources", str(backup_result.metadata.resource_counts))
    else:
        table.add_row("Resources", "N/A")

    if backup_result.duration:
        table.add_row("Duration", f"{backup_result.duration.total_seconds():.2f} seconds")
    else:
        table.add_row("Duration", "N/A")

    console.print(table)
