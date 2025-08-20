"""Cleanup orphaned assignments command implementation."""

import asyncio
from typing import Optional

import typer
from botocore.exceptions import ClientError
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from ...aws_clients.manager import AWSClientManager
from ...utils.orphaned_assignment_detector import OrphanedAssignmentDetector
from .helpers import validate_aws_credentials, validate_profile, validate_sso_instance

console = Console()


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
):
    """Clean up orphaned permission set assignments.

    Identifies and optionally removes permission set assignments for principals
    that no longer exist in the identity provider. Use --dry-run to preview
    changes before executing.

    Examples:
        awsideman status cleanup --dry-run    # Preview cleanup
        awsideman status cleanup --execute    # Perform cleanup with confirmation
        awsideman status cleanup --execute --force  # Perform cleanup without confirmation
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

        # Initialize the orphaned assignment detector
        detector = OrphanedAssignmentDetector(aws_client)

        # Show progress indicator
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Detecting orphaned assignments...", total=None)

            # Detect orphaned assignments
            result = asyncio.run(detector.check_status())

            progress.remove_task(task)

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

        # Perform cleanup
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Cleaning up orphaned assignments...", total=None)

            cleanup_result = asyncio.run(
                detector.cleanup_orphaned_assignments(result.orphaned_assignments)
            )

            progress.remove_task(task)

        # Display cleanup results
        if cleanup_result and hasattr(cleanup_result, "successful_cleanups"):
            console.print(
                f"[green]✅ Successfully cleaned up {cleanup_result.successful_cleanups} orphaned assignments.[/green]"
            )

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
