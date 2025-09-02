"""Cleanup orphaned assignments command implementation."""

import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Optional

import typer
from botocore.exceptions import ClientError
from rich.console import Console
from rich.live import Live
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from ...aws_clients.manager import AWSClientManager
from ...utils.orphaned_assignment_detector import OrphanedAssignmentDetector
from .helpers import validate_aws_credentials, validate_profile, validate_sso_instance

console = Console()


def _get_cache_file_path(profile_name: str) -> str:
    """Get the cache file path for orphaned assignment detection results."""
    cache_dir = os.path.join(tempfile.gettempdir(), "awsideman", "orphaned_cleanup")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"{profile_name}_orphaned_assignments.json")


def _save_detection_results(profile_name: str, result) -> str:
    """Save detection results to cache file."""
    cache_file = _get_cache_file_path(profile_name)

    # Convert result to serializable format
    cache_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "profile": profile_name,
        "orphaned_assignments": [],
    }

    if hasattr(result, "orphaned_assignments") and result.orphaned_assignments:
        for assignment in result.orphaned_assignments:
            cache_data["orphaned_assignments"].append(
                {
                    "assignment_id": assignment.assignment_id,
                    "permission_set_arn": assignment.permission_set_arn,
                    "permission_set_name": assignment.permission_set_name,
                    "account_id": assignment.account_id,
                    "account_name": assignment.account_name,
                    "principal_id": assignment.principal_id,
                    "principal_name": assignment.principal_name,
                    "principal_type": assignment.principal_type.value,
                    "error_message": assignment.error_message,
                    "created_date": (
                        assignment.created_date.isoformat() if assignment.created_date else None
                    ),
                    "last_accessed": (
                        assignment.last_accessed.isoformat() if assignment.last_accessed else None
                    ),
                }
            )

    with open(cache_file, "w") as f:
        json.dump(cache_data, f, indent=2)

    return cache_file


def _load_detection_results(profile_name: str):
    """Load detection results from cache file."""
    cache_file = _get_cache_file_path(profile_name)

    if not os.path.exists(cache_file):
        return None

    try:
        with open(cache_file, "r") as f:
            cache_data = json.load(f)

        # Check if cache is recent (within 1 hour)
        cache_time = datetime.fromisoformat(cache_data["timestamp"].replace("Z", "+00:00"))
        if (datetime.now(timezone.utc) - cache_time).total_seconds() > 3600:  # 1 hour
            console.print("[yellow]⚠ Cache is older than 1 hour, will re-run detection[/yellow]")
            return None

        # Reconstruct the result object
        from ...utils.status_models import (
            OrphanedAssignment,
            OrphanedAssignmentStatus,
            PrincipalType,
            StatusLevel,
        )

        orphaned_assignments = []
        for assignment_data in cache_data["orphaned_assignments"]:
            assignment = OrphanedAssignment(
                assignment_id=assignment_data["assignment_id"],
                permission_set_arn=assignment_data["permission_set_arn"],
                permission_set_name=assignment_data["permission_set_name"],
                account_id=assignment_data["account_id"],
                account_name=assignment_data["account_name"],
                principal_id=assignment_data["principal_id"],
                principal_name=assignment_data["principal_name"],
                principal_type=PrincipalType(assignment_data["principal_type"]),
                error_message=assignment_data["error_message"],
                created_date=(
                    datetime.fromisoformat(assignment_data["created_date"].replace("Z", "+00:00"))
                    if assignment_data["created_date"]
                    else None
                ),
                last_accessed=(
                    datetime.fromisoformat(assignment_data["last_accessed"].replace("Z", "+00:00"))
                    if assignment_data["last_accessed"]
                    else None
                ),
            )
            orphaned_assignments.append(assignment)

        # Create a mock result object
        result = OrphanedAssignmentStatus(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.WARNING if orphaned_assignments else StatusLevel.HEALTHY,
            message=f"Found {len(orphaned_assignments)} orphaned assignments (from cache)",
            orphaned_assignments=orphaned_assignments,
            cleanup_available=True,
        )

        return result

    except Exception as e:
        console.print(f"[yellow]⚠ Error loading cache: {str(e)}, will re-run detection[/yellow]")
        return None


def _clear_cache(profile_name: str):
    """Clear the cache file."""
    cache_file = _get_cache_file_path(profile_name)
    if os.path.exists(cache_file):
        os.remove(cache_file)


def cleanup_orphaned(
    dry_run: bool = typer.Option(
        True,
        "--dry-run/--execute",
        help="Show what would be cleaned up without making changes (default: dry-run)",
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompts"),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="AWS profile to use (uses default profile if not specified)"
    ),
    no_cache: bool = typer.Option(
        False, "--no-cache", help="Force fresh detection, ignore cached results"
    ),
):
    """Clean up orphaned permission set assignments.

    Identifies and optionally removes permission set assignments for principals
    that no longer exist in the identity provider. Detection results are cached
    for 1 hour to avoid re-running expensive detection when switching between
    dry-run and execute modes.

    Examples:
        awsideman status cleanup --dry-run    # Preview cleanup (caches results)
        awsideman status cleanup --execute    # Use cached results or run fresh detection
        awsideman status cleanup --execute --force  # Perform cleanup without confirmation
        awsideman status cleanup --no-cache   # Force fresh detection, ignore cache
    """
    try:
        # Validate the profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Validate the SSO instance and get instance ARN and identity store ID
        instance_arn, identity_store_id = validate_sso_instance(profile_data)

        # Initialize the AWS client manager with the profile and region
        region = profile_data.get("region")
        aws_client = AWSClientManager(profile=profile_name, region=region)

        # Validate AWS credentials before proceeding
        validate_aws_credentials(aws_client)

        # Try to load cached results first (unless --no-cache is specified)
        result = None
        if not no_cache:
            result = _load_detection_results(profile_name)
            if result:
                console.print("[green]✓ Using cached detection results[/green]")

        # If no cached results or --no-cache specified, run fresh detection
        if not result:
            # Clear AWS client cache before orphaned assignment detection to ensure fresh data
            # This prevents false negatives when groups/users have been deleted but cache still shows them as existing
            if aws_client.is_caching_enabled():
                console.print(
                    "[dim]Clearing AWS client cache to ensure fresh data for orphaned assignment detection...[/dim]"
                )
                cache_cleared = aws_client.clear_cache()
                if cache_cleared:
                    console.print("[dim]✓ AWS client cache cleared successfully[/dim]")
                else:
                    console.print(
                        "[yellow]⚠ Warning: Could not clear AWS client cache, results may be stale[/yellow]"
                    )

            # Show progress indicator with live updates
            progress_text = Text("Detecting orphaned assignments...", style="blue")

            def update_progress(message: str):
                """Update the progress display with new message."""
                progress_text.plain = message

            # Initialize the orphaned assignment detector with progress callback
            detector = OrphanedAssignmentDetector(aws_client, progress_callback=update_progress)

            with Live(progress_text, console=console, refresh_per_second=2):
                # Detect orphaned assignments
                result = asyncio.run(detector.check_status())

            # Save results to cache for potential reuse
            cache_file = _save_detection_results(profile_name, result)
            console.print(f"[dim]✓ Detection results cached to: {cache_file}[/dim]")

        # Check if any orphaned assignments were found
        if not hasattr(result, "orphaned_assignments") or not result.orphaned_assignments:
            console.print("[green]✅ No orphaned assignments found.[/green]")
            return

        orphaned_count = len(result.orphaned_assignments)
        console.print(f"[yellow]Found {orphaned_count} orphaned assignments.[/yellow]")

        # Display orphaned assignments
        table = Table(title="Orphaned Assignments")
        table.add_column("Permission Set", style="cyan")
        table.add_column("Account", style="blue")
        table.add_column("Principal", style="magenta")
        table.add_column("Type", style="green")
        table.add_column("Age (days)", style="yellow")

        for assignment in result.orphaned_assignments:
            table.add_row(
                assignment.permission_set_name,
                assignment.account_name or assignment.account_id,
                assignment.principal_name or assignment.principal_id,
                assignment.principal_type.value,
                str(assignment.get_age_days()),
            )

        console.print(table)

        if dry_run:
            console.print("\n[blue]This is a dry run. Use --execute to perform the cleanup.[/blue]")

            # Ask if user wants to proceed with cleanup
            if not force:
                console.print("\n[yellow]Would you like to proceed with the cleanup now?[/yellow]")
                proceed = typer.confirm("Execute cleanup for these orphaned assignments?")
                if proceed:
                    console.print("[blue]Proceeding with cleanup...[/blue]")
                    # Clear the cache since we're about to execute
                    _clear_cache(profile_name)
                    # Continue to cleanup section below
                else:
                    console.print(
                        "[blue]Cleanup cancelled. Results are cached for later use.[/blue]"
                    )
                    return
            else:
                console.print("[blue]Use --execute to perform the cleanup.[/blue]")
                return

        # Confirm cleanup unless --force is used
        if not force:
            console.print(
                f"\n[yellow]This will permanently remove {orphaned_count} orphaned assignments.[/yellow]"
            )
            confirm = typer.confirm("Are you sure you want to proceed?")
            if not confirm:
                console.print("[blue]Cleanup cancelled.[/blue]")
                return

        # Perform cleanup with progress tracking
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Cleaning up orphaned assignments...", total=orphaned_count)

            def progress_callback(current: int, total: int, status: str, assignment_name: str):
                """Update progress bar with cleanup progress."""
                if status == "success":
                    progress.update(
                        task,
                        completed=current,
                        description=f"Cleaning up orphaned assignments... ({current}/{total}) ✓ {assignment_name}",
                    )
                elif status == "failed":
                    progress.update(
                        task,
                        completed=current,
                        description=f"Cleaning up orphaned assignments... ({current}/{total}) ✗ {assignment_name}",
                    )
                else:
                    progress.update(
                        task,
                        completed=current,
                        description=f"Cleaning up orphaned assignments... ({current}/{total}) ⚠ {assignment_name}",
                    )

            cleanup_result = asyncio.run(
                detector.cleanup_orphaned_assignments(
                    result.orphaned_assignments, progress_callback
                )
            )

            progress.remove_task(task)

        # Display cleanup results
        if cleanup_result and hasattr(cleanup_result, "successful_cleanups"):
            console.print(
                f"[green]✅ Successfully cleaned up {cleanup_result.successful_cleanups} orphaned assignments.[/green]"
            )

            # Clear cache after successful cleanup
            _clear_cache(profile_name)
            console.print("[dim]✓ Cache cleared after successful cleanup[/dim]")

            if hasattr(cleanup_result, "failed_cleanups") and cleanup_result.failed_cleanups > 0:
                console.print(
                    f"[yellow]⚠️  Failed to clean up {cleanup_result.failed_cleanups} assignments.[/yellow]"
                )

                if hasattr(cleanup_result, "cleanup_errors") and cleanup_result.cleanup_errors:
                    console.print("\nErrors encountered:")
                    for error in cleanup_result.cleanup_errors[:5]:  # Show first 5 errors
                        console.print(f"  • {error}")
        else:
            console.print("[red]❌ Cleanup operation failed.[/red]")

    except ClientError as e:
        # Handle AWS API errors
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))
        console.print(f"[red]AWS Error ({error_code}): {error_message}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        # Handle other unexpected errors
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)
