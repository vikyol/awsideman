"""Restore backup command for awsideman."""

import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

from ...backup_restore.backends import FileSystemStorageBackend, S3StorageBackend
from ...backup_restore.models import ConflictStrategy, ResourceType, RestoreOptions
from ...backup_restore.restore_manager import RestoreManager
from ...backup_restore.storage import StorageEngine
from ...backup_restore.validation import BackupValidator
from ...utils.config import Config
from ...utils.validators import validate_profile

console = Console()
config = Config()


def restore_backup(
    backup_id: str = typer.Argument(..., help="Backup ID to restore from"),
    resources: Optional[str] = typer.Option(
        None,
        "--resources",
        "-r",
        help="Comma-separated list of resources to restore (users,groups,permission_sets,assignments,all)",
    ),
    conflict_strategy: str = typer.Option(
        "prompt",
        "--conflict-strategy",
        "-c",
        help="Conflict resolution strategy: overwrite, skip, prompt, merge",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without applying them"),
    target_account: Optional[str] = typer.Option(
        None, "--target-account", help="Target AWS account ID for cross-account restore"
    ),
    target_region: Optional[str] = typer.Option(
        None, "--target-region", help="Target AWS region for cross-region restore"
    ),
    target_instance_arn: Optional[str] = typer.Option(
        None, "--target-instance-arn", help="Target Identity Center instance ARN"
    ),
    storage_backend: str = typer.Option(
        "filesystem", "--storage", help="Storage backend: filesystem or s3"
    ),
    storage_path: Optional[str] = typer.Option(
        None, "--storage-path", help="Storage path where backup is located"
    ),
    skip_validation: bool = typer.Option(
        False, "--skip-validation", help="Skip compatibility validation before restore"
    ),
    output_format: str = typer.Option(
        "table", "--format", "-f", help="Output format: table or json"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile to use"),
):
    """Restore AWS Identity Center configuration from a backup.

    Restores AWS Identity Center resources (users, groups, permission sets,
    assignments) from a backup. Supports selective restore, conflict resolution,
    and cross-account/region operations.

    Examples:
        # Restore all resources from a backup
        $ awsideman restore backup-20240117-143022-abc12345

        # Dry-run restore to preview changes
        $ awsideman restore backup-123 --dry-run

        # Restore only users and groups
        $ awsideman restore backup-123 --resources users,groups

        # Restore with conflict resolution strategy
        $ awsideman restore backup-123 --conflict-strategy overwrite

        # Cross-account restore
        $ awsideman restore backup-123 --target-account 123456789012 --target-region us-west-2
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

        # Validate conflict strategy
        if conflict_strategy.lower() not in ["overwrite", "skip", "prompt", "merge"]:
            console.print(f"[red]Error: Invalid conflict strategy '{conflict_strategy}'.[/red]")
            console.print("[yellow]Valid strategies: overwrite, skip, prompt, merge[/yellow]")
            raise typer.Exit(1)

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
            storage_backend_obj = S3StorageBackend(bucket_name=bucket_name, prefix=prefix)
        else:
            console.print(f"[red]Error: Unsupported storage backend '{storage_backend}'.[/red]")
            console.print("[yellow]Supported backends: filesystem, s3[/yellow]")
            raise typer.Exit(1)

        # Initialize components
        storage_engine = StorageEngine(backend=storage_backend_obj)
        restore_manager = RestoreManager(storage_engine=storage_engine)
        validator = BackupValidator(storage_engine=storage_engine)

        # Check if backup exists
        console.print(f"[blue]Checking backup: {backup_id}[/blue]")

        try:
            storage_engine.retrieve_backup(backup_id)
        except Exception as e:
            console.print(f"[red]Error: Backup '{backup_id}' not found.[/red]")
            console.print(f"[yellow]Details: {e}[/yellow]")
            raise typer.Exit(1)

        # Validate backup compatibility if not skipped
        if not skip_validation:
            console.print("[blue]Validating backup compatibility...[/blue]")

            try:
                compatibility_result = asyncio.run(
                    validator.validate_compatibility(
                        backup_id=backup_id,
                        target_account=target_account,
                        target_region=target_region,
                        target_instance_arn=target_instance_arn,
                    )
                )

                if not compatibility_result.is_compatible:
                    console.print("[red]Backup compatibility validation failed![/red]")
                    console.print("[yellow]Use --skip-validation to proceed anyway.[/yellow]")

                    if compatibility_result.issues:
                        console.print("\n[bold red]Compatibility Issues:[/bold red]")
                        for issue in compatibility_result.issues:
                            console.print(f"[red]• {issue}[/red]")

                    raise typer.Exit(1)

                console.print("[green]✓ Backup compatibility validation passed![/green]")

            except Exception as e:
                console.print(f"[red]Compatibility validation failed: {e}[/red]")
                if not skip_validation:
                    raise typer.Exit(1)

        # Create restore options
        restore_options = RestoreOptions(
            target_resources=resource_types if resource_types else [ResourceType.ALL],
            conflict_strategy=ConflictStrategy(conflict_strategy.lower()),
            dry_run=dry_run,
            target_account=target_account,
            target_region=target_region,
            target_instance_arn=target_instance_arn,
            skip_validation=skip_validation,
        )

        # Perform restore operation
        if dry_run:
            console.print(f"[blue]Previewing restore from backup: {backup_id}[/blue]")
            operation_type = "Preview"
        else:
            console.print(f"[blue]Restoring from backup: {backup_id}[/blue]")
            operation_type = "Restore"

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(f"{operation_type} in progress...", total=None)

            try:
                restore_result = asyncio.run(
                    restore_manager.restore_backup(backup_id=backup_id, options=restore_options)
                )
                progress.update(task, description=f"{operation_type} completed!")
            except Exception as e:
                console.print(f"[red]{operation_type} failed: {e}[/red]")
                raise typer.Exit(1)

        # Display results
        if output_format.lower() == "json":
            console.print_json(data=restore_result.to_dict())
        else:
            display_restore_results(restore_result, dry_run)

        # Summary
        if dry_run:
            console.print("[green]✓ Restore preview completed successfully![/green]")
            console.print("[blue]Use --dry-run=false to perform the actual restore.[/blue]")
        else:
            console.print("[green]✓ Restore completed successfully![/green]")
            console.print(f"[blue]Restored {restore_result.changes_applied} resources.[/blue]")

    except Exception as e:
        console.print(f"[red]Error during restore: {e}[/red]")
        raise typer.Exit(1)


def display_restore_results(restore_result, dry_run: bool):
    """Display restore results in a formatted table."""
    operation_type = "Preview" if dry_run else "Restore"

    # Main results summary
    summary_table = Table(title=f"{operation_type} Results Summary")
    summary_table.add_column("Property", style="cyan")
    summary_table.add_column("Value", style="white")

    summary_table.add_row("Operation Type", operation_type)
    summary_table.add_row(
        "Status", "[green]Success[/green]" if restore_result.success else "[red]Failed[/red]"
    )
    summary_table.add_row("Changes Applied", str(restore_result.changes_applied))
    summary_table.add_row(
        "Duration", str(restore_result.duration) if restore_result.duration else "N/A"
    )

    console.print(summary_table)

    # Detailed changes
    if restore_result.changes_applied > 0:
        console.print("\n[bold cyan]Detailed Changes:[/bold cyan]")
        changes_table = Table()
        changes_table.add_column("Resource Type", style="cyan")
        changes_table.add_column("Action", style="green")
        changes_table.add_column("Count", style="white")
        changes_table.add_column("Details", style="white")

        # This would be populated with actual change details from the restore result
        # For now, showing a placeholder
        changes_table.add_row("Users", "Created/Updated", "N/A", "User accounts restored")
        changes_table.add_row("Groups", "Created/Updated", "N/A", "Group memberships restored")
        changes_table.add_row("Permission Sets", "Created/Updated", "N/A", "Permissions restored")
        changes_table.add_row(
            "Assignments", "Created/Updated", "N/A", "Access assignments restored"
        )

        console.print(changes_table)

    # Warnings and errors
    if restore_result.warnings:
        console.print("\n[bold yellow]Warnings:[/bold yellow]")
        for warning in restore_result.warnings:
            console.print(f"[yellow]• {warning}[/yellow]")

    if restore_result.errors:
        console.print("\n[bold red]Errors:[/bold red]")
        for error in restore_result.errors:
            console.print(f"[red]• {error}[/red]")
