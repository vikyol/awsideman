"""Validate backup command for awsideman."""

import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from ...backup_restore.backends import FileSystemStorageBackend, S3StorageBackend
from ...backup_restore.storage import StorageEngine
from ...backup_restore.validation import BackupValidator
from ...utils.config import Config
from ...utils.validators import validate_profile

console = Console()
config = Config()


def validate_backup(
    backup_id: str = typer.Argument(..., help="Backup ID to validate"),
    storage_backend: str = typer.Option(
        "filesystem", "--storage", help="Storage backend: filesystem or s3"
    ),
    storage_path: Optional[str] = typer.Option(
        None, "--storage-path", help="Storage path (directory for filesystem, bucket/prefix for s3)"
    ),
    check_integrity: bool = typer.Option(
        True, "--check-integrity/--no-check-integrity", help="Perform integrity checks"
    ),
    check_completeness: bool = typer.Option(
        True, "--check-completeness/--no-check-completeness", help="Check backup completeness"
    ),
    check_consistency: bool = typer.Option(
        True, "--check-consistency/--no-check-consistency", help="Check data consistency"
    ),
    output_format: str = typer.Option(
        "table", "--format", "-f", help="Output format: table or json"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile to use"),
):
    """Validate backup integrity and completeness.

    Performs comprehensive validation of a backup including integrity checks,
    completeness verification, and data consistency validation. This command
    helps ensure that backups are reliable and can be restored successfully.

    Examples:
        # Validate a backup with default checks
        $ awsideman backup validate backup-20240117-143022-abc12345

        # Validate with specific storage backend
        $ awsideman backup validate backup-123 --storage s3 --storage-path my-bucket/backups

        # Validate with selective checks
        $ awsideman backup validate backup-123 --no-check-consistency

        # Output validation results in JSON
        $ awsideman backup validate backup-123 --format json

        # Validate backup from custom filesystem path
        $ awsideman backup validate backup-123 --storage filesystem --storage-path /custom/backups
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
            # Configure S3 backend with profile support
            s3_config = {"bucket_name": bucket_name, "prefix": prefix}

            # Use profile name for SSO and named profiles
            if profile_name:
                s3_config["profile_name"] = profile_name

            # Add region from profile data if available
            if profile_data and "region" in profile_data:
                s3_config["region_name"] = profile_data["region"]

            storage_backend = S3StorageBackend(**s3_config)
        else:
            console.print(f"[red]Error: Unsupported storage backend '{storage_backend}'.[/red]")
            console.print("[yellow]Supported backends: filesystem, s3[/yellow]")
            raise typer.Exit(1)

        # Initialize components
        storage_engine = StorageEngine(backend=storage_backend)
        validator = BackupValidator()

        # Check if backup exists
        console.print(f"[blue]Validating backup: {backup_id}[/blue]")

        try:
            backup_metadata = asyncio.run(storage_engine.get_backup_metadata(backup_id))
        except Exception as e:
            console.print(f"[red]Error: Backup '{backup_id}' not found.[/red]")
            console.print(f"[yellow]Details: {e}[/yellow]")
            raise typer.Exit(1)

        if not backup_metadata:
            console.print(f"[red]Error: Backup '{backup_id}' not found.[/red]")
            raise typer.Exit(1)

        # Retrieve backup data for validation
        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
        ) as progress:
            task = progress.add_task("Retrieving backup data...", total=None)
            backup_data = asyncio.run(storage_engine.retrieve_backup(backup_id))
            progress.remove_task(task)

            if not backup_data:
                console.print(f"[red]Error: Could not retrieve backup data for '{backup_id}'[/red]")
                raise typer.Exit(1)

            # Validate backup data
            task = progress.add_task("Validating backup...", total=None)
            validation_result = asyncio.run(validator.validate_backup_data(backup_data))
            progress.update(task, description="Validation completed!")

        # Display results
        if output_format.lower() == "json":
            console.print_json(data=validation_result.to_dict())
        else:
            display_validation_results(validation_result, backup_metadata)

        # Summary
        if validation_result.is_valid:
            console.print("[green]✓ Backup validation completed successfully![/green]")
        else:
            console.print("[red]✗ Backup validation failed![/red]")
            console.print("[yellow]Please review the validation results above.[/yellow]")

    except Exception as e:
        console.print(f"[red]Error validating backup: {e}[/red]")
        raise typer.Exit(1)


def display_validation_results(validation_result, backup_metadata):
    """Display validation results in a formatted table."""
    # Main validation summary
    summary_table = Table(title="Backup Validation Summary")
    summary_table.add_column("Property", style="cyan")
    summary_table.add_column("Value", style="white")

    summary_table.add_row("Backup ID", backup_metadata.backup_id)
    summary_table.add_row("Timestamp", str(backup_metadata.timestamp))
    summary_table.add_row("Type", backup_metadata.backup_type.value)
    summary_table.add_row(
        "Overall Status",
        "[green]Valid[/green]" if validation_result.is_valid else "[red]Invalid[/red]",
    )
    summary_table.add_row(
        "Validation Status",
        ("[green]Passed[/green]" if validation_result.is_valid else "[red]Failed[/red]"),
    )
    summary_table.add_row("Errors", str(len(validation_result.errors)))
    summary_table.add_row("Warnings", str(len(validation_result.warnings)))

    console.print(summary_table)

    # Error and warning details
    if validation_result.errors:
        console.print("\n[bold red]Errors:[/bold red]")
        for error in validation_result.errors:
            console.print(f"  • {error}")

    if validation_result.warnings:
        console.print("\n[bold yellow]Warnings:[/bold yellow]")
        for warning in validation_result.warnings:
            console.print(f"  • {warning}")

    # Additional details if available
    if validation_result.details:
        console.print("\n[bold cyan]Validation Details:[/bold cyan]")
        details_table = Table()
        details_table.add_column("Property", style="cyan")
        details_table.add_column("Value", style="white")

        for key, value in validation_result.details.items():
            details_table.add_row(key.replace("_", " ").title(), str(value))

        console.print(details_table)

    # Resource count details from backup metadata
    if backup_metadata.resource_counts:
        console.print("\n[bold cyan]Resource Counts:[/bold cyan]")
        resource_table = Table()
        resource_table.add_column("Resource Type", style="cyan")
        resource_table.add_column("Count", style="white")

        for resource_type, count in backup_metadata.resource_counts.items():
            resource_table.add_row(resource_type.replace("_", " ").title(), str(count))

        console.print(resource_table)
