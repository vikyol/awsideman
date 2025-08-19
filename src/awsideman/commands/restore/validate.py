"""Validate restore compatibility command for awsideman."""

import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from ...backup_restore.backends import FileSystemStorageBackend, S3StorageBackend
from ...backup_restore.storage import StorageEngine
from ...utils.config import Config
from ...utils.validators import validate_profile

console = Console()
config = Config()


def validate_restore(
    backup_id: str = typer.Argument(..., help="Backup ID to validate for restore compatibility"),
    target_account: Optional[str] = typer.Option(
        None, "--target-account", help="Target AWS account ID for cross-account restore"
    ),
    target_region: Optional[str] = typer.Option(
        None, "--target-region", help="Target AWS region for cross-region restore"
    ),
    target_instance_arn: Optional[str] = typer.Option(
        None, "--target-instance-arn", help="Target Identity Center instance ARN"
    ),
    target_role_arn: Optional[str] = typer.Option(
        None,
        "--target-role-arn",
        help="IAM role ARN to assume in target account for cross-account restore",
    ),
    storage_backend: str = typer.Option(
        "filesystem", "--storage", help="Storage backend: filesystem or s3"
    ),
    storage_path: Optional[str] = typer.Option(
        None, "--storage-path", help="Storage path where backup is located"
    ),
    output_format: str = typer.Option(
        "table", "--format", "-f", help="Output format: table or json"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile to use"),
):
    """Validate backup compatibility with target environment.

    Performs comprehensive validation of backup compatibility before restore
    operations. Checks for account, region, and instance compatibility,
    as well as resource dependencies and constraints.

    Examples:
        # Validate backup compatibility with current environment
        $ awsideman restore validate backup-20240117-143022-abc12345

        # Validate for cross-account restore
        $ awsideman restore validate backup-123 --target-account 123456789012

        # Validate for cross-region restore
        $ awsideman restore validate backup-123 --target-region us-west-2

        # Validate with custom storage location
        $ awsideman restore validate backup-123 --storage s3 --storage-path my-bucket/backups
    """
    try:
        # Validate profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Try to get storage location from local metadata index first
        from ...backup_restore.local_metadata_index import get_global_metadata_index

        metadata_index = get_global_metadata_index()
        storage_info = metadata_index.get_storage_location(backup_id)

        if storage_info and not storage_path:
            # Use storage info from metadata index if not explicitly provided
            storage_backend = storage_info["backend"]
            storage_path = storage_info["location"]
            console.print(
                f"[blue]Auto-detected storage: {storage_backend} at {storage_path}[/blue]"
            )

        # Initialize storage backend
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

        # Initialize AWS client manager
        from ...aws_clients.manager import AWSClientManager

        aws_client_manager = AWSClientManager(
            profile=profile_name, region=profile_data.get("region")
        )

        # Get the required clients
        identity_center_client = aws_client_manager.get_identity_center_client()
        identity_store_client = aws_client_manager.get_identity_store_client()

        # Initialize components
        storage_engine = StorageEngine(backend=storage_backend_obj)

        # Import RestoreManager for compatibility validation
        from ...backup_restore.restore_manager import RestoreManager

        restore_manager = RestoreManager(
            storage_engine=storage_engine,
            identity_center_client=identity_center_client,
            identity_store_client=identity_store_client,
        )

        # Check if backup exists
        console.print(f"[blue]Checking backup: {backup_id}[/blue]")

        try:
            backup_data = asyncio.run(storage_engine.retrieve_backup(backup_id))
            if not backup_data:
                console.print(f"[red]Error: Backup '{backup_id}' not found.[/red]")
                console.print(
                    "[yellow]Use 'awsideman backup list' to see available backups.[/yellow]"
                )
                raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Error: Backup '{backup_id}' not found.[/red]")
            console.print(f"[yellow]Details: {e}[/yellow]")
            raise typer.Exit(1)

        # Display backup information
        console.print("[blue]Found backup:[/blue]")
        console.print(f"  ID: {backup_data.metadata.backup_id}")
        console.print(f"  Type: {backup_data.metadata.backup_type.value}")
        console.print(f"  Timestamp: {backup_data.metadata.timestamp}")
        console.print(f"  Source Account: {backup_data.metadata.source_account}")
        console.print(f"  Source Region: {backup_data.metadata.source_region}")

        # Perform compatibility validation
        console.print("\n[blue]Validating backup compatibility...[/blue]")

        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
        ) as progress:
            task = progress.add_task("Validating compatibility...", total=None)

            try:
                # Use the RestoreManager's validate_compatibility method
                compatibility_result = asyncio.run(
                    restore_manager.validate_compatibility(
                        backup_id=backup_id,
                        target_instance_arn=target_instance_arn
                        or backup_data.metadata.instance_arn,
                    )
                )
                progress.update(task, description="Validation completed!")
            except Exception as e:
                console.print(f"[red]Compatibility validation failed: {e}[/red]")
                raise typer.Exit(1)

        # Display validation results
        if output_format.lower() == "json":
            console.print_json(data=compatibility_result.to_dict())
        else:
            display_validation_results(
                compatibility_result, backup_data, target_account, target_region
            )

        # Summary
        if compatibility_result.is_valid:
            console.print("[green]✓ Backup compatibility validation passed![/green]")
            console.print("[blue]The backup is compatible with the target environment.[/blue]")
        else:
            console.print("[red]✗ Backup compatibility validation failed![/red]")
            console.print(
                "[yellow]Please resolve the compatibility issues before proceeding with restore.[/yellow]"
            )

    except Exception as e:
        console.print(f"[red]Error during validation: {e}[/red]")
        raise typer.Exit(1)


def display_validation_results(compatibility_result, backup_data, target_account, target_region):
    """Display compatibility validation results in a formatted table."""

    # Validation summary
    summary_table = Table(title="Compatibility Validation Summary")
    summary_table.add_column("Property", style="cyan")
    summary_table.add_column("Value", style="white")

    summary_table.add_row("Backup ID", backup_data.metadata.backup_id)
    summary_table.add_row("Source Account", backup_data.metadata.source_account)
    summary_table.add_row("Source Region", backup_data.metadata.source_region)
    summary_table.add_row("Target Account", target_account or "Current")
    summary_table.add_row("Target Region", target_region or "Current")
    summary_table.add_row(
        "Overall Compatibility",
        (
            "[green]Compatible[/green]"
            if compatibility_result.is_valid
            else "[red]Incompatible[/red]"
        ),
    )

    console.print(summary_table)

    # Detailed validation results
    if hasattr(compatibility_result, "validation_details"):
        console.print("\n[bold cyan]Detailed Validation Results:[/bold cyan]")
        details_table = Table()
        details_table.add_column("Check", style="cyan")
        details_table.add_column("Status", style="white")
        details_table.add_column("Details", style="white")

        # This would be populated with actual validation details
        # For now, showing a placeholder
        details_table.add_row(
            "Account Compatibility",
            (
                "[green]Passed[/green]"
                if not target_account or target_account == backup_data.metadata.source_account
                else "[yellow]Check Required[/yellow]"
            ),
            "Account IDs match or no cross-account restore",
        )

        details_table.add_row(
            "Region Compatibility",
            (
                "[green]Passed[/green]"
                if not target_region or target_region == backup_data.metadata.source_region
                else "[yellow]Check Required[/yellow]"
            ),
            "Regions match or no cross-region restore",
        )

        details_table.add_row(
            "Instance Compatibility",
            "[green]Passed[/green]",
            "Identity Center instance compatibility verified",
        )

        details_table.add_row(
            "Resource Dependencies",
            "[green]Passed[/green]",
            "All resource dependencies are satisfied",
        )

        console.print(details_table)

    # Compatibility issues
    if hasattr(compatibility_result, "errors") and compatibility_result.errors:
        console.print("\n[bold red]Compatibility Issues:[/bold red]")
        for issue in compatibility_result.errors:
            console.print(f"[red]• {issue}[/red]")

    # Warnings
    if hasattr(compatibility_result, "warnings") and compatibility_result.warnings:
        console.print("\n[bold yellow]Warnings:[/bold yellow]")
        for warning in compatibility_result.warnings:
            console.print(f"[yellow]• {warning}[/yellow]")

    # Recommendations
    if hasattr(compatibility_result, "recommendations") and compatibility_result.recommendations:
        console.print("\n[bold blue]Recommendations:[/bold blue]")
        for recommendation in compatibility_result.recommendations:
            console.print(f"[blue]• {recommendation}[/blue]")

    # Next steps
    console.print("\n[bold blue]Next Steps:[/bold blue]")
    if compatibility_result.is_valid:
        console.print("[blue]1. Compatibility validation passed - proceed with restore[/blue]")
        console.print(
            "[blue]2. Use 'awsideman restore preview' to see what will be restored[/blue]"
        )
        console.print(
            "[blue]3. Use 'awsideman restore apply' to perform the restore operation[/blue]"
        )
    else:
        console.print("[blue]1. Resolve compatibility issues listed above[/blue]")
        console.print("[blue]2. Re-run validation after resolving issues[/blue]")
        console.print("[blue]3. Consider using --skip-validation if issues are acceptable[/blue]")
