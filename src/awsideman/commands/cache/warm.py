"""Warm cache command for awsideman."""

from typing import Optional

import typer
from typer.testing import CliRunner

from ..common import (
    advanced_cache_option,
    extract_standard_params,
    profile_option,
    region_option,
    show_cache_info,
)
from .helpers import console, get_cache_manager


def warm_cache(
    command: str = typer.Argument(..., help="Command to warm up (e.g., 'user list', 'group list')"),
    profile: Optional[str] = profile_option(),
    region: Optional[str] = region_option(),
    no_cache: bool = advanced_cache_option(),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
):
    """Pre-load data by executing a command.

    Executes the specified command to populate internal data storage, improving response times
    for subsequent identical commands. The command output is not displayed.

    Examples:
        awsideman cache warm "user list"
        awsideman cache warm "group list --limit 50"
        awsideman cache warm "org tree" --profile production
        awsideman cache warm "user list" --profile dev --region us-west-2
    """
    try:
        # Extract and process standard command parameters
        profile_param, region_param, enable_caching = extract_standard_params(
            profile, region, no_cache
        )

        # Show cache information if verbose
        show_cache_info(verbose)

        # Get cache manager with profile-aware configuration
        if profile_param:
            from ...cache.utilities import create_cache_manager, get_profile_cache_config

            config = get_profile_cache_config(profile_param)
            cache_manager = create_cache_manager(config)
            console.print(
                f"[blue]Using profile-specific cache configuration for: {profile_param}[/blue]"
            )
        else:
            cache_manager = get_cache_manager()

        if not cache_manager.config.enabled:
            console.print("[yellow]Cache is disabled. Cannot warm cache.[/yellow]")
            return

        # Get cache stats before warming
        stats_before = cache_manager.get_cache_stats()
        entries_before = stats_before.get("total_entries", 0)

        # Show which profile/region is being used
        profile_info = ""
        if profile_param:
            profile_info += f" (profile: {profile_param}"
            if region_param:
                profile_info += f", region: {region_param}"
            profile_info += ")"
        elif region_param:
            profile_info = f" (region: {region_param})"

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

        _execute_command_with_cli_runner(
            command_parts, profile_param, region_param, enable_caching, verbose
        )

        # Get cache stats after warming
        stats_after = cache_manager.get_cache_stats()
        entries_after = stats_after.get("total_entries", 0)

        # Report results
        new_entries = entries_after - entries_before

        # Since the command execution succeeded, assume the cache was populated
        # The cache stats comparison might not work due to process isolation
        if new_entries > 0:
            console.print(
                f"[green]✓ Cache warmed successfully! Added {new_entries} new cache entries.[/green]"
            )
        else:
            # Check if the cache actually has entries (more reliable than difference)
            if entries_after > 0:
                console.print(
                    f"[green]✓ Cache warmed successfully! Cache now has {entries_after} entries.[/green]"
                )
            else:
                console.print(
                    "[yellow]Cache warming completed, but no entries detected. This may be due to process isolation.[/yellow]"
                )

    except Exception as e:
        console.print(f"[red]Error warming cache: {e}[/red]")
        raise typer.Exit(1)


def _execute_command_with_cli_runner(
    command_parts: list,
    profile: Optional[str],
    region: Optional[str],
    enable_caching: bool,
    verbose: bool,
) -> None:
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

    # Add cache options for enhanced integration
    if not enable_caching:
        runner_args.append("--no-cache")
    if verbose:
        runner_args.append("--verbose")

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
