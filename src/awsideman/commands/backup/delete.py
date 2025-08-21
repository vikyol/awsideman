"""Delete backup command for awsideman."""

import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.prompt import Confirm

from ...backup_restore.backends import FileSystemStorageBackend, S3StorageBackend
from ...backup_restore.local_metadata_index import get_global_metadata_index
from ...backup_restore.storage import StorageEngine
from ...utils.config import Config
from ...utils.validators import validate_profile

console = Console()
config = Config()


def delete_backup(
    backup_id: str = typer.Argument(..., help="Backup ID to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile to use"),
):
    """Delete a backup with confirmation.

    Removes a backup from storage after confirmation. This operation cannot
    be undone, so use with caution. The command will automatically determine
    the storage location using the local metadata index.

    Examples:
        # Delete a backup with confirmation
        $ awsideman backup delete backup-20240117-143022-abc12345

        # Delete without confirmation prompt
        $ awsideman backup delete backup-123 --force

        # Delete using specific AWS profile
        $ awsideman backup delete backup-123 --profile my-profile
    """
    try:
        # Get the global metadata index
        metadata_index = get_global_metadata_index()

        # Check if backup exists in local index
        console.print(f"[blue]Checking backup: {backup_id}[/blue]")

        backup_metadata = metadata_index.get_backup_metadata(backup_id)
        if not backup_metadata:
            console.print(f"[red]Error: Backup '{backup_id}' not found in local index.[/red]")
            console.print(
                "[yellow]Try using 'awsideman backup list --sync' to update the local index.[/yellow]"
            )
            raise typer.Exit(1)

        # Get storage location information
        storage_info = metadata_index.get_storage_location(backup_id)
        if not storage_info:
            console.print(f"[red]Error: Storage location not found for backup '{backup_id}'.[/red]")
            raise typer.Exit(1)

        storage_backend_type = storage_info.get("backend")
        storage_location = storage_info.get("location")

        if not storage_backend_type or not storage_location:
            console.print(
                f"[red]Error: Incomplete storage information for backup '{backup_id}'.[/red]"
            )
            raise typer.Exit(1)

        console.print(f"[blue]Found backup in {storage_backend_type.upper()} storage[/blue]")

        # Validate profile if needed for S3
        profile_name = None
        profile_data = None
        if storage_backend_type.lower() == "s3":
            profile_name, profile_data = validate_profile(profile)

        # Initialize storage backend based on metadata
        if storage_backend_type.lower() == "filesystem":
            backend_instance = FileSystemStorageBackend(base_path=storage_location)
        elif storage_backend_type.lower() == "s3":
            # Parse bucket and prefix from storage location
            if "/" in storage_location:
                bucket_name, prefix = storage_location.split("/", 1)
            else:
                bucket_name, prefix = storage_location, ""

            s3_config = {"bucket_name": bucket_name, "prefix": prefix}
            if profile_name:
                s3_config["profile_name"] = profile_name
            if profile_data and "region" in profile_data:
                s3_config["region_name"] = profile_data["region"]

            backend_instance = S3StorageBackend(**s3_config)
        else:
            console.print(
                f"[red]Error: Unsupported storage backend '{storage_backend_type}'.[/red]"
            )
            raise typer.Exit(1)

        # Initialize storage engine
        storage_engine = StorageEngine(backend=backend_instance)

        # Verify backup still exists in storage
        try:
            stored_metadata = asyncio.run(storage_engine.get_backup_metadata(backup_id))
            if not stored_metadata:
                console.print(f"[red]Error: Backup '{backup_id}' not found in storage.[/red]")
                console.print(
                    "[yellow]The backup may have been deleted from storage but not from the local index.[/yellow]"
                )
                # Remove from local index
                metadata_index.remove_backup_metadata(backup_id)
                console.print("[blue]Removed orphaned entry from local index.[/blue]")
                raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Error: Failed to verify backup in storage: {e}[/red]")
            raise typer.Exit(1)

        # Display backup information
        console.print("[blue]Found backup:[/blue]")
        console.print(f"  ID: {backup_metadata.backup_id}")
        console.print(f"  Timestamp: {backup_metadata.timestamp}")
        console.print(f"  Type: {backup_metadata.backup_type.value}")
        if backup_metadata.backup_type.value == "incremental" and backup_metadata.size_bytes == 0:
            console.print("  Size: No changes since last backup")
        elif backup_metadata.size_bytes and backup_metadata.size_bytes > 0:
            console.print(f"  Size: {backup_metadata.size_bytes / 1024 / 1024:.2f} MB")
        # Don't display size if it can't be calculated
        console.print(f"  Version: {backup_metadata.version}")
        console.print(f"  Storage: {storage_backend_type.upper()}")
        console.print(f"  Location: {storage_location}")

        # Confirmation prompt
        if not force:
            console.print("\n[yellow]Warning: This operation cannot be undone![/yellow]")
            if not Confirm.ask(f"Are you sure you want to delete backup '{backup_id}'?"):
                console.print("[blue]Operation cancelled.[/blue]")
                return
        else:
            console.print("[yellow]Force flag used - skipping confirmation.[/yellow]")

        # Delete the backup
        console.print(f"[blue]Deleting backup '{backup_id}'...[/blue]")

        try:
            success = asyncio.run(storage_engine.delete_backup(backup_id))

            if success:
                console.print(f"[green]✓ Backup '{backup_id}' deleted successfully![/green]")

                # Remove from local metadata index
                metadata_index.remove_backup_metadata(backup_id)
                console.print("[blue]Removed backup from local metadata index.[/blue]")
            else:
                console.print(f"[red]✗ Failed to delete backup '{backup_id}'.[/red]")
                raise typer.Exit(1)

        except Exception as e:
            console.print(f"[red]Error deleting backup: {e}[/red]")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
