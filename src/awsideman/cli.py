#!/usr/bin/env python3
"""
awsideman - AWS Identity Center Manager

A CLI tool for managing AWS Identity Center operations.
"""
from typing import Optional

import typer
from rich.console import Console

try:
    from awsideman import __version__

    from .commands import (
        access_review,
        assignment,
        bulk,
        cache,
        clone,
        config,
        copy,
        group,
        org,
        permission_set,
        profile,
        rollback,
        sso,
        templates,
        user,
    )
    from .commands.backup import app as backup_app
    from .commands.restore import app as restore_app
except ImportError:
    # Handle direct script execution
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from awsideman import __version__
    from awsideman.commands import (
        access_review,
        assignment,
        bulk,
        cache,
        clone,
        config,
        copy,
        group,
        org,
        permission_set,
        profile,
        rollback,
        sso,
        templates,
        user,
    )
    from awsideman.commands.backup import app as backup_app
    from awsideman.commands.restore import app as restore_app

app = typer.Typer(
    help="AWS Identity Center Manager - A CLI tool for managing AWS Identity Center operations including users, groups, and permission sets.",
    add_completion=True,
    no_args_is_help=True,
)
console = Console()

# Add subcommands
app.add_typer(config.app, name="config")
app.add_typer(profile.app, name="profile")
app.add_typer(sso.app, name="sso")
app.add_typer(user.app, name="user")
app.add_typer(group.app, name="group")
app.add_typer(permission_set.app, name="permission-set")
app.add_typer(copy.app, name="copy")
app.add_typer(clone.app, name="clone")
app.add_typer(assignment.app, name="assignment")
app.add_typer(org.app, name="org")
app.add_typer(cache.app, name="cache")
app.add_typer(bulk.app, name="bulk")
# Note: status command is handled specially below to support --profile option
app.add_typer(access_review.app, name="access-review")
app.add_typer(templates.app, name="templates")
app.add_typer(rollback.app, name="rollback")
app.add_typer(backup_app, name="backup")
app.add_typer(restore_app, name="restore")


# Add version command
@app.command()
def version():
    """Show the application version and exit."""
    console.print(f"awsideman version: {__version__}")
    raise typer.Exit()


@app.command()
def info(
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use"),
):
    """Display comprehensive information about the current AWS Identity Center configuration."""
    try:
        from .aws_clients.manager import AWSClientManager
        from .utils.validators import validate_profile, validate_sso_instance

        console.print("[bold blue]AWS Identity Center Information[/bold blue]\n")

        # Validate profile
        try:
            profile_name, profile_data = validate_profile(profile)
            console.print(f"[green]✓[/green] Active Profile: [bold]{profile_name}[/bold]")

            # Show profile details
            region = profile_data.get("region", "Not set")
            console.print(f"[green]✓[/green] Region: {region}")

        except Exception as e:
            console.print(f"[red]✗[/red] Profile Configuration: {str(e)}")
            return

        # Validate SSO instance (with auto-detection)
        try:
            instance_arn, identity_store_id = validate_sso_instance(profile_data, profile_name)
            console.print("[green]✓[/green] SSO Instance: Configured")
            console.print(f"    Instance ARN: {instance_arn}")
            console.print(f"    Identity Store ID: {identity_store_id}")

            # Show custom display name if available
            custom_name = profile_data.get("sso_display_name") or profile_data.get(
                "sso_instance_name"
            )
            if custom_name:
                console.print(f"    Display Name: {custom_name}")

        except Exception as e:
            console.print("[red]✗[/red] SSO Instance: Not configured")
            console.print(f"    Error: {str(e)}")
            return

        # Try to get additional information from AWS
        try:
            aws_client = AWSClientManager(profile=profile_name, region=region)

            # Test connectivity and get instance details
            console.print("\n[bold blue]AWS Connectivity Status[/bold blue]")
            sso_client = aws_client.get_identity_center_client()
            identitystore_client = aws_client.get_identity_store_client()

            # Get instance information
            instances_response = sso_client.list_instances()
            instances = instances_response.get("Instances", [])

            current_instance = None
            for instance in instances:
                if instance["InstanceArn"] == instance_arn:
                    current_instance = instance
                    break

            if current_instance:
                console.print("[green]✓[/green] Instance Status: Active")
                console.print(f"    Name: {current_instance.get('Name', 'N/A')}")
                console.print(f"    Status: {current_instance.get('Status', 'N/A')}")
                created_date = current_instance.get("CreatedDate")
                if created_date:
                    if hasattr(created_date, "strftime"):
                        console.print(f"    Created: {created_date.strftime('%Y-%m-%d %H:%M:%S')}")
                    else:
                        console.print(f"    Created: {created_date}")
            else:
                console.print("[yellow]⚠[/yellow] Instance Status: Not found in current region")

            # Get basic statistics
            console.print("\n[bold blue]Resource Summary[/bold blue]")

            try:
                # Count users
                users_response = identitystore_client.list_users(
                    IdentityStoreId=identity_store_id, MaxResults=1
                )
                user_count = "Available" if users_response.get("Users") else "None visible"
                console.print(f"[blue]ℹ[/blue] Users: {user_count}")
            except Exception:
                console.print("[yellow]⚠[/yellow] Users: Access check failed")

            try:
                # Count groups
                groups_response = identitystore_client.list_groups(
                    IdentityStoreId=identity_store_id, MaxResults=1
                )
                group_count = "Available" if groups_response.get("Groups") else "None visible"
                console.print(f"[blue]ℹ[/blue] Groups: {group_count}")
            except Exception:
                console.print("[yellow]⚠[/yellow] Groups: Access check failed")

            try:
                # Count permission sets
                ps_response = sso_client.list_permission_sets(
                    InstanceArn=instance_arn, MaxResults=1
                )
                ps_count = "Available" if ps_response.get("PermissionSets") else "None visible"
                console.print(f"[blue]ℹ[/blue] Permission Sets: {ps_count}")
            except Exception:
                console.print("[yellow]⚠[/yellow] Permission Sets: Access check failed")

            # Check Organizations access
            try:
                orgs_client = aws_client.get_raw_organizations_client()
                orgs_response = orgs_client.list_accounts(MaxResults=1)
                accounts_count = "Available" if orgs_response.get("Accounts") else "None visible"
                console.print(f"[blue]ℹ[/blue] AWS Organizations: {accounts_count}")
            except Exception:
                console.print("[yellow]⚠[/yellow] AWS Organizations: Access check failed")

        except Exception as e:
            console.print("\n[red]✗[/red] AWS Connectivity: Failed")
            console.print(f"    Error: {str(e)}")

        # Show helpful commands
        console.print("\n[bold blue]Helpful Commands[/bold blue]")
        console.print(f"• List users: [cyan]awsideman user list --profile {profile_name}[/cyan]")
        console.print(f"• List groups: [cyan]awsideman group list --profile {profile_name}[/cyan]")
        console.print(
            f"• List permission sets: [cyan]awsideman permission-set list --profile {profile_name}[/cyan]"
        )
        console.print(
            f"• View assignments: [cyan]awsideman assignment list --profile {profile_name}[/cyan]"
        )
        console.print(
            f"• Check status: [cyan]awsideman status check --profile {profile_name}[/cyan]"
        )

    except Exception as e:
        console.print(f"[red]Error getting AWS Identity Center information: {str(e)}[/red]")
        raise typer.Exit(1)


# Custom status command that accepts --profile option and delegates to subcommands
@app.command("status")
def status_command(
    subcommand: Optional[str] = typer.Argument(
        None, help="Status subcommand: check, inspect, cleanup, monitor"
    ),
    output_format: Optional[str] = typer.Option(
        None, "--format", "-f", help="Output format: json, csv, table (default: table)"
    ),
    status_type: Optional[str] = typer.Option(
        None,
        "--type",
        "-t",
        help="Specific status type to check: health, provisioning, orphaned, sync, resource, summary",
    ),
    timeout: Optional[int] = typer.Option(
        30,
        "--timeout",
        help="Timeout for status checks in seconds (default: 30, use 300+ for large organizations)",
    ),
    parallel: bool = typer.Option(
        True, "--parallel/--sequential", help="Run checks in parallel (default: parallel)"
    ),
    quick_scan: bool = typer.Option(
        True,
        "--quick-scan/--full-scan",
        help="Use quick scan for orphaned assignments (default: quick scan)",
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="AWS profile to use (uses default profile if not specified)"
    ),
    # Additional arguments for other subcommands
    resource_type: Optional[str] = typer.Argument(
        None, help="Resource type for inspect: user, group, permission-set"
    ),
    resource_id: Optional[str] = typer.Argument(None, help="Resource identifier for inspect"),
    dry_run: bool = typer.Option(
        True,
        "--dry-run/--execute",
        help="Show what would be cleaned up without making changes (for cleanup)",
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Skip confirmation prompts (for cleanup)"
    ),
    action: Optional[str] = typer.Argument(
        None, help="Action for monitor: show, enable, disable, test, schedule"
    ),
):
    """Check AWS Identity Center status and health.

    This is the main status command. If no subcommand is specified, it defaults to 'check'.
    For other status operations, use specific subcommands like 'inspect', 'cleanup', or 'monitor'.

    Examples:
        awsideman status --profile dev-account
        awsideman status check --profile dev-account
        awsideman status inspect user john.doe@example.com --profile dev-account
        awsideman status cleanup --dry-run --profile dev-account
        awsideman status monitor show --profile dev-account
    """
    # If no subcommand is specified, default to 'check'
    if subcommand is None:
        subcommand = "check"

    # Import the status subcommands
    from .commands.status.check import check_status
    from .commands.status.cleanup import cleanup_orphaned
    from .commands.status.inspect import inspect_resource
    from .commands.status.monitor import monitor_config

    # Route to the appropriate subcommand
    if subcommand == "check":
        check_status(
            output_format=output_format,
            status_type=status_type,
            timeout=timeout,
            parallel=parallel,
            quick_scan=quick_scan,
            profile=profile,
        )
    elif subcommand == "inspect":
        if not resource_type or not resource_id:
            console.print(
                "[red]Error: inspect subcommand requires resource_type and resource_id arguments.[/red]"
            )
            console.print("Usage: awsideman status inspect <resource_type> <resource_id> [options]")
            console.print(
                "Example: awsideman status inspect user john.doe@example.com --profile dev-account"
            )
            raise typer.Exit(1)
        inspect_resource(
            resource_type=resource_type,
            resource_id=resource_id,
            output_format=output_format,
            profile=profile,
        )
    elif subcommand == "cleanup":
        cleanup_orphaned(
            dry_run=dry_run,
            force=force,
            profile=profile,
        )
    elif subcommand == "monitor":
        if not action:
            console.print("[red]Error: monitor subcommand requires an action argument.[/red]")
            console.print("Usage: awsideman status monitor <action> [options]")
            console.print("Actions: show, enable, disable, test, schedule")
            raise typer.Exit(1)
        monitor_config(
            action=action,
            profile=profile,
        )
    else:
        console.print(f"[red]Error: Unknown subcommand '{subcommand}'.[/red]")
        console.print("Valid subcommands: check, inspect, cleanup, monitor")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
