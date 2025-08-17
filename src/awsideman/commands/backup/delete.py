"""Delete backup command for awsideman."""

from typing import Optional

import typer
from rich.console import Console
from rich.prompt import Confirm

from ...backup_restore.backends import FileSystemStorageBackend, S3StorageBackend
from ...backup_restore.storage import StorageEngine
from ...utils.config import Config
from ...utils.validators import validate_profile

console = Console()
config = Config()


def delete_backup(
    backup_id: str = typer.Argument(..., help="Backup ID to delete"),
    storage_backend: str = typer.Option(
        "filesystem", "--storage", help="Storage backend: filesystem or s3"
    ),
    storage_path: Optional[str] = typer.Option(
        None, "--storage-path", help="Storage path (directory for filesystem, bucket/prefix for s3)"
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile to use"),
):
    """Delete a backup with confirmation.

    Removes a backup from storage after confirmation. This operation cannot
    be undone, so use with caution. The command will prompt for confirmation
    unless the --force flag is used.

    Examples:
        # Delete a backup with confirmation
        $ awsideman backup delete backup-20240117-143022-abc12345

        # Delete without confirmation prompt
        $ awsideman backup delete backup-123 --force

        # Delete from S3 storage
        $ awsideman backup delete backup-123 --storage s3 --storage-path my-bucket/backups

        # Delete from custom filesystem path
        $ awsideman backup delete backup-123 --storage filesystem --storage-path /custom/backups
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

        # Initialize storage engine
        storage_engine = StorageEngine(backend=storage_backend)

        # Check if backup exists and get metadata
        console.print(f"[blue]Checking backup: {backup_id}[/blue]")

        try:
            backup_metadata = storage_engine.get_backup_metadata(backup_id)
        except Exception as e:
            console.print(f"[red]Error: Backup '{backup_id}' not found.[/red]")
            console.print(f"[yellow]Details: {e}[/yellow]")
            raise typer.Exit(1)

        # Display backup information
        console.print("[blue]Found backup:[/blue]")
        console.print(f"  ID: {backup_metadata.backup_id}")
        console.print(f"  Timestamp: {backup_metadata.timestamp}")
        console.print(f"  Type: {backup_metadata.backup_type.value}")
        console.print(
            f"  Size: {backup_metadata.size_bytes / 1024 / 1024:.2f} MB"
            if backup_metadata.size_bytes
            else "  Size: Unknown"
        )
        console.print(f"  Storage: {backup_metadata.storage_location or 'Default'}")

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
            success = storage_engine.delete_backup(backup_id)

            if success:
                console.print(f"[green]✓ Backup '{backup_id}' deleted successfully![/green]")
            else:
                console.print(f"[red]✗ Failed to delete backup '{backup_id}'.[/red]")
                raise typer.Exit(1)

        except Exception as e:
            console.print(f"[red]Error deleting backup: {e}[/red]")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
