"""Warm cache command for awsideman."""

import shlex
import subprocess
from typing import Optional

import typer

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
        command_parts = shlex.split(command)
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

        # Build the full awsideman command (caching is now enabled by default)
        full_command = ["awsideman"]

        # Add the command group first
        full_command.append(command_parts[0])

        # Add profile option if specified (after the command group)
        if profile:
            full_command.extend(["--profile", profile])

        # Add region option if specified (after the command group)
        if region:
            full_command.extend(["--region", region])

        # Add the rest of the command arguments
        if len(command_parts) > 1:
            full_command.extend(command_parts[1:])

        # Execute the command to warm the cache
        console.print("[dim]Executing command to populate cache...[/dim]")
        console.print(f"[dim]Full command: {' '.join(full_command)}[/dim]")

        try:
            # Run the command with output suppressed
            result = subprocess.run(
                full_command, capture_output=True, text=True, timeout=300  # 5 minute timeout
            )

            if result.returncode != 0:
                console.print(f"[red]Error executing command: {result.stderr}[/red]")
                raise typer.Exit(1)

        except subprocess.TimeoutExpired:
            console.print("[red]Error: Command timed out after 5 minutes[/red]")
            raise typer.Exit(1)
        except FileNotFoundError:
            console.print(
                "[red]Error: Could not find awsideman executable. Make sure it's installed and in PATH.[/red]"
            )
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
