"""Warm cache command for awsideman."""

import sys
from typing import Optional

import typer
from typer.testing import CliRunner

from .helpers import console, get_cache_manager


def warm_cache(
    command: str = typer.Argument(..., help="Command to warm up (e.g., 'user list', 'group list')"),
    profile: Optional[str] = typer.Option(
        None, "--profile", help="AWS profile to use for cache warming"
    ),
    region: Optional[str] = typer.Option(
        None, "--region", help="AWS region to use for cache warming"
    ),
):
    """Warm up the cache by pre-executing a command.

    Executes the specified command to populate the cache, improving performance
    for subsequent identical commands. The command output is not displayed.

    Examples:
        awsideman cache warm "user list"
        awsideman cache warm "group list --limit 50"
        awsideman cache warm "org tree" --profile production
        awsideman cache warm "user list" --profile dev --region us-west-2
    """
    try:
        cache_manager = get_cache_manager()

        if not cache_manager.config.enabled:
            console.print("[yellow]Cache is disabled. Cannot warm cache.[/yellow]")
            return

        # Get cache stats before warming
        stats_before = cache_manager.get_cache_stats()
        entries_before = stats_before.get("total_entries", 0)

        # Show which profile/region is being used
        profile_info = ""
        if profile:
            profile_info += f" (profile: {profile}"
            if region:
                profile_info += f", region: {region}"
            profile_info += ")"
        elif region:
            profile_info = f" (region: {region})"

        console.print(f"[blue]Warming cache for command: {command}{profile_info}[/blue]")

        # Parse and validate the command
        command_parts = command.split()
        if not command_parts:
            console.print("[red]Error: Empty command provided[/red]")
            raise typer.Exit(1)

        # Validate that the command doesn't start with 'cache' to prevent recursion
        if command_parts[0] == "cache":
            console.print("[red]Error: Cannot warm cache commands (would cause recursion)[/red]")
            raise typer.Exit(1)

        # Validate that it's a known command group
        valid_commands = ["user", "group", "permission-set", "assignment", "org", "profile", "sso"]
        if command_parts[0] not in valid_commands:
            console.print(
                f"[red]Error: Unknown command '{command_parts[0]}'. Valid commands: {', '.join(valid_commands)}[/red]"
            )
            raise typer.Exit(1)

        # Execute the command to warm the cache
        console.print("[dim]Executing command to populate cache...[/dim]")
        console.print(f"[dim]Full command: awsideman {' '.join(command_parts)}[/dim]")

        try:
            # Execute the command using Typer's CliRunner
            _execute_command_with_cli_runner(command_parts, profile, region)

        except Exception as e:
            console.print(f"[red]Error executing command: {e}[/red]")
            raise typer.Exit(1)

        # Get cache stats after warming
        stats_after = cache_manager.get_cache_stats()
        entries_after = stats_after.get("total_entries", 0)

        # Calculate the difference
        new_entries = entries_after - entries_before

        if new_entries > 0:
            console.print(
                f"[green]✓ Cache warmed successfully! Added {new_entries} new cache entries.[/green]"
            )
        elif new_entries == 0:
            console.print(
                "[yellow]Cache was already warm for this command (no new entries added).[/yellow]"
            )
        else:
            # This shouldn't happen unless cache was cleared during execution
            console.print("[yellow]Cache state changed during warm-up.[/yellow]")

        console.print(f"[dim]Total cache entries: {entries_after}[/dim]")

    except Exception as e:
        console.print(f"[red]Error warming cache: {e}[/red]")
        raise typer.Exit(1)


def _execute_command_with_cli_runner(command_parts: list, profile: Optional[str], region: Optional[str]) -> None:
    """Execute a command using Typer's CliRunner."""
    command_group = command_parts[0]
    subcommand = command_parts[1] if len(command_parts) > 1 else None
    
    # Build the command arguments for CliRunner
    runner_args = [command_group]
    if subcommand:
        runner_args.append(subcommand)
    
    # Add profile and region options if specified
    if profile:
        runner_args.extend(["--profile", profile])
    if region:
        runner_args.extend(["--region", region])
    
    # Add any additional arguments from the original command
    if len(command_parts) > 2:
        runner_args.extend(command_parts[2:])
    
    try:
        # Import the appropriate app based on command group
        if command_group == "user":
            from ..user import app as user_app
            app = user_app
        elif command_group == "group":
            from ..group import app as group_app
            app = group_app
        elif command_group == "permission-set":
            from ..permission_set import app as permission_set_app
            app = permission_set_app
        elif command_group == "assignment":
            from ..assignment import app as assignment_app
            app = assignment_app
        elif command_group == "org":
            from ..org import app as org_app
            app = org_app
        elif command_group == "profile":
            from ..profile import app as profile_app
            app = profile_app
        elif command_group == "sso":
            from ..sso import app as sso_app
            app = sso_app
        else:
            raise ValueError(f"Unsupported command group: {command_group}")
        
        # Execute the command using CliRunner
        runner = CliRunner()
        result = runner.invoke(app, runner_args[1:])  # Skip the command group name
        
        if result.exit_code != 0:
            raise RuntimeError(f"Command failed with exit code {result.exit_code}: {result.stdout}")
            
    except ImportError as e:
        raise RuntimeError(f"Failed to import command module for {command_group}: {e}")
    except Exception as e:
        raise RuntimeError(f"Failed to execute command: {e}")
