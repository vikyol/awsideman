"""Backup diff command for awsideman."""

import asyncio
import logging
from typing import Optional

import typer
from botocore.exceptions import NoCredentialsError, TokenRetrievalError
from rich.console import Console

from ...backup_restore.backends import FileSystemStorageBackend, S3StorageBackend
from ...backup_restore.backup_diff_manager import BackupDiffManager
from ...backup_restore.collector import IdentityCenterCollector
from ...backup_restore.local_metadata_index import get_global_metadata_index
from ...backup_restore.storage import StorageEngine
from ...commands.common import validate_profile_with_cache
from ...utils.config import Config

console = Console(force_terminal=True, no_color=False)
config = Config()
logger = logging.getLogger(__name__)


def diff_backups(
    source: str = typer.Argument(
        ..., help="Source backup specification (date like '7d', '2025-01-15', or backup ID)"
    ),
    target: Optional[str] = typer.Argument(
        None,
        help="Target backup specification (defaults to current state). Use date like '1d', '2025-01-20', or backup ID",
    ),
    output_format: str = typer.Option(
        "console",
        "--format",
        "-f",
        help="Output format: console, json, csv, or html",
    ),
    output_file: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path (if not specified, prints to console)",
    ),
    storage_backend: Optional[str] = typer.Option(
        None,
        "--storage",
        help="Storage backend: filesystem or s3 (overrides config default)",
    ),
    storage_path: Optional[str] = typer.Option(
        None,
        "--storage-path",
        help="Storage path (directory for filesystem, bucket/prefix for s3)",
    ),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile to use"),
):
    """Compare two backups and show differences."""
    try:
        # Validate profile and get configuration
        profile_name, profile_config, aws_client = validate_profile_with_cache(profile)

        # Initialize storage backend
        default_backend = config.get("backup.storage.default_backend", "filesystem")

        if storage_backend == "s3" or (not storage_backend and default_backend == "s3"):
            # Use configured S3 settings if no storage_path provided
            if not storage_path:
                bucket_name = config.get("backup.storage.s3.bucket")
                prefix = config.get("backup.storage.s3.prefix", "backups")
                region_name = config.get("backup.storage.s3.region")

                if not bucket_name:
                    console.print(
                        "[red]Error: S3 storage requires --storage-path (bucket/prefix) or configured bucket[/red]"
                    )
                    raise typer.Exit(1)
            else:
                bucket_name, prefix = (
                    storage_path.split("/", 1) if "/" in storage_path else (storage_path, "")
                )
                region_name = profile_config.get("region")

            backend = S3StorageBackend(
                bucket_name=bucket_name,
                prefix=prefix,
                profile_name=profile_name,
                region_name=region_name,
            )
            console.print(f"[blue]Using S3 storage: {bucket_name}/{prefix}[/blue]")
        else:
            backend = FileSystemStorageBackend(
                base_path=storage_path or config.get("backup.storage.filesystem.path", "./backups"),
                create_dirs=True,
            )
            console.print(f"[blue]Using filesystem storage: {backend.base_path}[/blue]")

        # Initialize storage engine
        storage_engine = StorageEngine(backend=backend)

        # Get metadata index
        metadata_index = get_global_metadata_index()

        # Initialize collector for current state comparison
        # Get SSO instance information from profile configuration
        instance_arn = profile_config.get("sso_instance_arn")
        identity_store_id = profile_config.get("identity_store_id")

        if not instance_arn or not identity_store_id:
            console.print("[red]Error: No SSO instance configured for this profile.[/red]")
            console.print("[yellow]For security reasons, auto-detection is disabled.[/yellow]")
            console.print(
                "Use 'awsideman sso set <instance_arn> <identity_store_id>' to configure an SSO instance."
            )
            console.print("You can find available SSO instances with 'awsideman sso list'.")
            raise typer.Exit(1)

        console.print(f"[blue]Using configured SSO instance: {instance_arn}[/blue]")

        collector = IdentityCenterCollector(client_manager=aws_client, instance_arn=instance_arn)

        # Initialize backup diff manager
        diff_manager = BackupDiffManager(
            storage_engine=storage_engine,
            metadata_index=metadata_index,
            collector=collector,
        )

        # Run the comparison
        asyncio.run(
            diff_manager.compare_backups(
                source_spec=source,
                target_spec=target,
                output_format=output_format,
                output_file=output_file,
            )
        )

    except typer.Exit:
        # Re-raise typer.Exit without modification
        raise
    except (NoCredentialsError, TokenRetrievalError) as e:
        if isinstance(e, NoCredentialsError):
            console.print("[red]❌ Error: No AWS credentials found.[/red]")
            console.print("\n[yellow]To fix this issue:[/yellow]")
            console.print("1. Configure AWS credentials: [cyan]aws configure[/cyan]")
            console.print("2. Or use a profile: [cyan]--profile your-profile[/cyan]")
        else:
            console.print("[red]❌ Error: AWS SSO authentication failed.[/red]")
            console.print("\n[yellow]To fix this issue:[/yellow]")
            console.print(
                "1. Refresh your SSO login: [cyan]aws sso login --profile your-profile[/cyan]"
            )
            console.print("2. Or use a different profile: [cyan]--profile other-profile[/cyan]")
        logger.exception("Authentication error in backup diff command")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        console.print("[yellow]Please report this issue with the full error details[/yellow]")
        logger.exception("Unexpected error in backup diff command")
        raise typer.Exit(1)


def display_diff_results(diff_result):
    """Display diff results in a human-readable console format with improved formatting."""

    # Display summary
    console.print("\n[bold blue]Backup Comparison Summary[/bold blue]")
    console.print(f"Source: {diff_result.source_backup_id} ({diff_result.source_timestamp})")
    console.print(f"Target: {diff_result.target_backup_id} ({diff_result.target_timestamp})")
    console.print(f"Total Changes: {diff_result.summary.total_changes}")

    if not diff_result.has_changes:
        console.print("\n[green]No changes found between the specified backups.[/green]")
        return

    # Create name mappings for better display
    name_mappings = create_name_mappings(diff_result)

    # Display changes by resource type with improved formatting
    resource_diffs = [
        ("Users", diff_result.user_diff),
        ("Groups", diff_result.group_diff),
        ("Permission Sets", diff_result.permission_set_diff),
    ]

    for resource_name, resource_diff in resource_diffs:
        if resource_diff.total_changes > 0:
            console.print(f"\n[bold cyan]{resource_name} Changes[/bold cyan]")
            console.print("-" * (len(resource_name) + 10))

            # Created resources - Green with + prefix
            if resource_diff.created:
                console.print(f"[green]Created ({len(resource_diff.created)}):[/green]")
                for change in resource_diff.created:
                    display_name = get_display_name(change, name_mappings)
                    console.print(f"  [green]+[/green] {display_name}")

            # Deleted resources - Red with - prefix
            if resource_diff.deleted:
                console.print(f"[red]Deleted ({len(resource_diff.deleted)}):[/red]")
                for change in resource_diff.deleted:
                    display_name = get_display_name(change, name_mappings)
                    console.print(f"  [red]-[/red] {display_name}")

            # Modified resources - Yellow with ~ prefix
            if resource_diff.modified:
                console.print(f"[yellow]Modified ({len(resource_diff.modified)}):[/yellow]")
                for change in resource_diff.modified:
                    display_name = get_display_name(change, name_mappings)
                    console.print(f"  [yellow]~[/yellow] {display_name}")

    # Display accounts section
    display_accounts_section(diff_result, name_mappings)

    # Display detailed changes for assignments with improved formatting
    if diff_result.assignment_diff.total_changes > 0:
        console.print("\n[bold yellow]Detailed Assignment Changes[/bold yellow]")
        display_detailed_assignments(diff_result.assignment_diff, name_mappings)


def create_name_mappings(diff_result):
    """Create mappings from IDs to names for better display."""
    mappings = {"users": {}, "groups": {}, "permission_sets": {}, "accounts": {}}

    # Extract user mappings from changes
    for change in (
        diff_result.user_diff.created
        + diff_result.user_diff.deleted
        + diff_result.user_diff.modified
    ):
        if change.after_value:
            user_data = change.after_value
            user_id = user_data.get("user_id")
            user_name = user_data.get("user_name")
            display_name = user_data.get("display_name")
            email = user_data.get("email")

            if user_id:
                # Prefer display_name, then user_name, then email
                name = display_name or user_name or email or user_id
                mappings["users"][user_id] = name
        elif change.before_value:
            user_data = change.before_value
            user_id = user_data.get("user_id")
            user_name = user_data.get("user_name")
            display_name = user_data.get("display_name")
            email = user_data.get("email")

            if user_id:
                name = display_name or user_name or email or user_id
                mappings["users"][user_id] = name

    # Extract group mappings from changes
    for change in (
        diff_result.group_diff.created
        + diff_result.group_diff.deleted
        + diff_result.group_diff.modified
    ):
        if change.after_value:
            group_data = change.after_value
            group_id = group_data.get("group_id")
            display_name = group_data.get("display_name")

            if group_id:
                name = display_name or group_id
                mappings["groups"][group_id] = name
        elif change.before_value:
            group_data = change.before_value
            group_id = group_data.get("group_id")
            display_name = group_data.get("display_name")

            if group_id:
                name = display_name or group_id
                mappings["groups"][group_id] = name

    # Extract permission set mappings from changes
    for change in (
        diff_result.permission_set_diff.created
        + diff_result.permission_set_diff.deleted
        + diff_result.permission_set_diff.modified
    ):
        if change.after_value:
            ps_data = change.after_value
            ps_arn = ps_data.get("permission_set_arn")
            name = ps_data.get("name")

            if ps_arn:
                mappings["permission_sets"][ps_arn] = name or ps_arn.split("/")[-1]
        elif change.before_value:
            ps_data = change.before_value
            ps_arn = ps_data.get("permission_set_arn")
            name = ps_data.get("name")

            if ps_arn:
                mappings["permission_sets"][ps_arn] = name or ps_arn.split("/")[-1]

    # Also extract user and group mappings from assignment changes
    # This is needed because users/groups might not be in the changes but are referenced in assignments
    for change in (
        diff_result.assignment_diff.created
        + diff_result.assignment_diff.deleted
        + diff_result.assignment_diff.modified
    ):
        assignment_info = parse_assignment_info(change)
        if assignment_info:
            principal_type = assignment_info.get("principal_type")
            principal_id = assignment_info.get("principal_id")

            if principal_type == "USER" and principal_id and principal_id not in mappings["users"]:
                # For users not in changes, we'll use the ID as fallback
                mappings["users"][principal_id] = principal_id
            elif (
                principal_type == "GROUP"
                and principal_id
                and principal_id not in mappings["groups"]
            ):
                # For groups not in changes, we'll use the ID as fallback
                mappings["groups"][principal_id] = principal_id

    return mappings


def get_display_name(change, name_mappings):
    """Get a user-friendly display name for a change."""
    resource_type = change.resource_type

    if resource_type == "users":
        user_id = change.resource_id
        return name_mappings["users"].get(user_id, change.resource_name or user_id)
    elif resource_type == "groups":
        group_id = change.resource_id
        return name_mappings["groups"].get(group_id, change.resource_name or group_id)
    elif resource_type == "permission_sets":
        ps_arn = change.resource_id
        return name_mappings["permission_sets"].get(
            ps_arn, change.resource_name or ps_arn.split("/")[-1]
        )
    else:
        return change.resource_name or change.resource_id


def display_accounts_section(diff_result, name_mappings):
    """Display accounts section showing new/removed accounts based on assignments."""
    # Extract unique accounts from assignment changes
    source_accounts = set()
    target_accounts = set()

    # Get accounts from deleted assignments (source)
    for change in diff_result.assignment_diff.deleted:
        assignment_info = parse_assignment_info(change)
        if assignment_info and assignment_info.get("account_id"):
            source_accounts.add(assignment_info["account_id"])

    # Get accounts from created assignments (target)
    for change in diff_result.assignment_diff.created:
        assignment_info = parse_assignment_info(change)
        if assignment_info and assignment_info.get("account_id"):
            target_accounts.add(assignment_info["account_id"])

    # Calculate differences
    new_accounts = target_accounts - source_accounts
    removed_accounts = source_accounts - target_accounts

    if new_accounts or removed_accounts:
        console.print("\n[bold cyan]Accounts Changes[/bold cyan]")
        console.print("-" * 18)

        # New accounts
        if new_accounts:
            console.print(f"[green]New Accounts ({len(new_accounts)}):[/green]")
            for account_id in sorted(new_accounts):
                # Try to get account name from AWS Organizations if available
                account_name = get_account_name(account_id)
                display_text = f"{account_name} ({account_id})" if account_name else account_id
                console.print(f"  [green]+[/green] {display_text}")

        # Removed accounts
        if removed_accounts:
            console.print(f"[red]Removed Accounts ({len(removed_accounts)}):[/red]")
            for account_id in sorted(removed_accounts):
                account_name = get_account_name(account_id)
                display_text = f"{account_name} ({account_id})" if account_name else account_id
                console.print(f"  [red]-[/red] {display_text}")


def get_account_name(account_id):
    """Get account name from AWS Organizations if available."""
    # For now, return None as we don't have direct access to Organizations API
    # This could be enhanced in the future to fetch account names
    return None


def parse_assignment_info(change):
    """Parse assignment information from change data."""
    try:
        # Try to get info from after_value (for created) or before_value (for deleted)
        value = change.after_value or change.before_value

        if value and isinstance(value, dict):
            return {
                "principal_type": value.get("principal_type", "UNKNOWN"),
                "principal_id": value.get("principal_id", "unknown"),
                "account_id": value.get("account_id", "unknown"),
                "permission_set_arn": value.get("permission_set_arn", "unknown"),
            }

        # Try to parse from resource_id if it's in a specific format
        # Format: account_id:permission_set_arn:principal_type:principal_id
        if change.resource_id and ":" in change.resource_id:
            parts = change.resource_id.split(":")
            if len(parts) >= 4:
                return {
                    "account_id": parts[0],
                    "permission_set_arn": parts[1],
                    "principal_type": parts[2],
                    "principal_id": parts[3],
                }

    except Exception:
        pass

    return None


def display_detailed_assignments(assignment_diff, name_mappings):
    """Display detailed assignment changes with better formatting."""

    def extract_permission_set_name(permission_set_arn):
        """Extract permission set name from ARN."""
        try:
            if permission_set_arn and "/" in permission_set_arn:
                return permission_set_arn.split("/")[-1]
        except Exception:
            pass
        return None

    # Created assignments
    if assignment_diff.created:
        console.print(f"\n[green]Created Assignments ({len(assignment_diff.created)}):[/green]")
        for change in assignment_diff.created:
            assignment_info = parse_assignment_info(change)
            if assignment_info:
                principal_type = assignment_info.get("principal_type", "UNKNOWN")
                principal_id = assignment_info.get("principal_id", "unknown")
                account_id = assignment_info.get("account_id", "unknown")
                permission_set_arn = assignment_info.get("permission_set_arn", "unknown")

                # Get principal name
                if principal_type == "USER":
                    principal_name = name_mappings["users"].get(principal_id, principal_id)
                    prefix = "[USER]"
                elif principal_type == "GROUP":
                    principal_name = name_mappings["groups"].get(principal_id, principal_id)
                    prefix = "[GROUP]"
                else:
                    principal_name = principal_id
                    prefix = f"[{principal_type}]"

                # Get permission set name
                permission_set_name = name_mappings["permission_sets"].get(
                    permission_set_arn, extract_permission_set_name(permission_set_arn)
                )
                permission_display = (
                    permission_set_name or permission_set_arn.split("/")[-1]
                    if "/" in permission_set_arn
                    else permission_set_arn
                )

                # Get account name
                account_name = get_account_name(account_id)
                account_display = f"{account_name} ({account_id})" if account_name else account_id

                console.print(
                    f"  [green]+[/green] {prefix} {principal_name} -> {permission_display} @ {account_display}"
                )
            else:
                display_name = change.resource_name or change.resource_id
                console.print(f"  [green]+[/green] {display_name}")

    # Deleted assignments
    if assignment_diff.deleted:
        console.print(f"\n[red]Deleted Assignments ({len(assignment_diff.deleted)}):[/red]")
        for change in assignment_diff.deleted:
            assignment_info = parse_assignment_info(change)
            if assignment_info:
                principal_type = assignment_info.get("principal_type", "UNKNOWN")
                principal_id = assignment_info.get("principal_id", "unknown")
                account_id = assignment_info.get("account_id", "unknown")
                permission_set_arn = assignment_info.get("permission_set_arn", "unknown")

                # Get principal name
                if principal_type == "USER":
                    principal_name = name_mappings["users"].get(principal_id, principal_id)
                    prefix = "[USER]"
                elif principal_type == "GROUP":
                    principal_name = name_mappings["groups"].get(principal_id, principal_id)
                    prefix = "[GROUP]"
                else:
                    principal_name = principal_id
                    prefix = f"[{principal_type}]"

                # Get permission set name
                permission_set_name = name_mappings["permission_sets"].get(
                    permission_set_arn, extract_permission_set_name(permission_set_arn)
                )
                permission_display = (
                    permission_set_name or permission_set_arn.split("/")[-1]
                    if "/" in permission_set_arn
                    else permission_set_arn
                )

                # Get account name
                account_name = get_account_name(account_id)
                account_display = f"{account_name} ({account_id})" if account_name else account_id

                console.print(
                    f"  [red]-[/red] {prefix} {principal_name} -> {permission_display} @ {account_display}"
                )
            else:
                display_name = change.resource_name or change.resource_id
                console.print(f"  [red]-[/red] {display_name}")
