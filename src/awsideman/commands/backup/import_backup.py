"""Import backup command for awsideman."""

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from ...backup_restore.backends import FileSystemStorageBackend, S3StorageBackend
from ...backup_restore.export_import import ExportImportManager
from ...backup_restore.models import ExportFormat, ImportSource
from ...backup_restore.storage import StorageEngine
from ...utils.config import Config
from ...utils.validators import validate_profile

console = Console()
config = Config()


def import_backup(
    source: str = typer.Argument(..., help="Source file, directory, or URL to import from"),
    format: str = typer.Option(
        "auto", "--format", "-f", help="Import format: auto, json, yaml, csv, or awsideman"
    ),
    storage_backend: str = typer.Option(
        "filesystem", "--storage", help="Storage backend for imported backup: filesystem or s3"
    ),
    storage_path: Optional[str] = typer.Option(
        None, "--storage-path", help="Storage path (directory for filesystem, bucket/prefix for s3)"
    ),
    validate_only: bool = typer.Option(
        False, "--validate-only", help="Only validate the import data without importing"
    ),
    overwrite: bool = typer.Option(
        False, "--overwrite", help="Overwrite existing backup if it exists"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile to use"),
):
    """Import backup data from external sources.

    Imports backup data from various formats and sources for restoration
    or migration purposes. Supports multiple input formats and storage backends.

    Examples:
        # Import from JSON file
        $ awsideman backup import ./backup-data.json

        # Import from YAML file with specific format
        $ awsideman backup import ./backup-data.yaml --format yaml

        # Import from S3 with custom storage
        $ awsideman backup import s3://my-bucket/backups/backup-123 --storage s3 --storage-path my-bucket/imports

        # Validate import data without importing
        $ awsideman backup import ./backup-data.json --validate-only

        # Import with overwrite option
        $ awsideman backup import ./backup-data.json --overwrite
    """
    try:
        # Validate profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Determine source type and location
        source_type, source_location = _parse_source(source)

        # Initialize storage backend for import destination
        if storage_backend.lower() == "filesystem":
            storage_path = storage_path or config.get("backup.storage.filesystem.path", "./backups")
            storage_backend_obj = FileSystemStorageBackend(base_path=storage_path)
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

            storage_backend_obj = S3StorageBackend(**s3_config)
        else:
            console.print(f"[red]Error: Unsupported storage backend '{storage_backend}'.[/red]")
            console.print("[yellow]Supported backends: filesystem, s3[/yellow]")
            raise typer.Exit(1)

        # Initialize components
        storage_engine = StorageEngine(backend=storage_backend_obj)
        import_manager = ExportImportManager(storage_engine=storage_engine)

        # Create import source and format
        import_source = ImportSource(source_type=source_type, location=source_location)

        # Auto-detect format if not specified
        if format.lower() == "auto":
            detected_format = _detect_format(source_location)
            if detected_format:
                format = detected_format
                console.print(f"[blue]Auto-detected format: {format}[/blue]")
            else:
                console.print("[yellow]Could not auto-detect format, defaulting to JSON[/yellow]")
                format = "json"

        import_format = ExportFormat(
            format_type=format.lower(),
            compression=None,  # Will be auto-detected
            encryption=False,  # Will be auto-detected
        )

        # Validate import data first
        console.print(f"[blue]Validating import data from {source}...[/blue]")

        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
        ) as progress:
            task = progress.add_task("Validating import data...", total=None)

            try:
                validation_result = asyncio.run(
                    import_manager.validate_import_format(
                        source=import_source, format_config=import_format
                    )
                )
                progress.update(task, description="Validation completed!")
            except Exception as e:
                console.print(f"[red]Validation failed: {e}[/red]")
                raise typer.Exit(1)

        if not validation_result.is_valid:
            console.print("[red]Import validation failed![/red]")
            console.print("[yellow]Please fix the issues before importing.[/yellow]")

            if validation_result.errors:
                console.print("\n[bold red]Validation Errors:[/bold red]")
                for error in validation_result.errors:
                    console.print(f"[red]• {error}[/red]")

            if validation_result.warnings:
                console.print("\n[bold yellow]Warnings:[/bold yellow]")
                for warning in validation_result.warnings:
                    console.print(f"[yellow]• {warning}[/yellow]")

            raise typer.Exit(1)

        console.print("[green]✓ Import validation passed![/green]")

        # If only validation was requested, stop here
        if validate_only:
            console.print(
                "[blue]Validation completed successfully. Use --import to perform the actual import.[/blue]"
            )
            return

        # Perform the import
        console.print(f"[blue]Importing backup data from {source}...[/blue]")

        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
        ) as progress:
            task = progress.add_task("Importing backup data...", total=None)

            try:
                backup_id = asyncio.run(
                    import_manager.import_backup(source=import_source, format_config=import_format)
                )
                progress.update(task, description="Import completed!")
            except Exception as e:
                console.print(f"[red]Import failed: {e}[/red]")
                raise typer.Exit(1)

        # Display import results
        console.print("[green]✓ Backup imported successfully![/green]")
        console.print(f"[blue]Backup ID: {backup_id}[/blue]")
        console.print(f"[blue]Storage location: {storage_path}[/blue]")

    except Exception as e:
        console.print(f"[red]Error importing backup: {e}[/red]")
        raise typer.Exit(1)


def _parse_source(source: str) -> tuple[str, str]:
    """Parse source string to determine type and location."""
    if source.startswith("s3://"):
        return "s3", source
    elif source.startswith("http://") or source.startswith("https://"):
        return "url", source
    else:
        # Assume filesystem
        path = Path(source)
        if path.exists():
            if path.is_file():
                return "filesystem", str(path.absolute())
            elif path.is_dir():
                return "filesystem", str(path.absolute())
            else:
                raise typer.BadParameter(f"Source path '{source}' is not accessible")
        else:
            raise typer.BadParameter(f"Source path '{source}' does not exist")


def _detect_format(source_location: str) -> Optional[str]:
    """Auto-detect file format based on extension or content."""
    path = Path(source_location)

    # Check file extension
    if path.suffix.lower() in [".json"]:
        return "json"
    elif path.suffix.lower() in [".yaml", ".yml"]:
        return "yaml"
    elif path.suffix.lower() in [".csv"]:
        return "csv"
    elif path.suffix.lower() in [".backup", ".bak"]:
        return "awsideman"

    # For S3 URLs, try to extract extension from the key
    if source_location.startswith("s3://"):
        s3_path = source_location.split("/")[-1]
        if "." in s3_path:
            ext = s3_path.split(".")[-1].lower()
            if ext in ["json", "yaml", "yml", "csv", "backup", "bak"]:
                return ext

    return None
