"""Cache management commands for awsideman."""
import typer
import json
import time
import subprocess
import sys
import shlex
from typing import Optional
from rich.console import Console
from rich.table import Table
from datetime import datetime, timedelta

from ..cache.manager import CacheManager
from ..utils.models import CacheEntry

app = typer.Typer(help="Manage cache for AWS Identity Center operations. Clear cache, view status, and warm cache for better performance.")
console = Console()


@app.command("clear")
def clear_cache(
    force: bool = typer.Option(False, "--force", "-f", help="Force clear without confirmation"),
):
    """Clear all cached data.
    
    Removes all cached AWS Identity Center data to force fresh API calls.
    Use this when you need to ensure you're getting the most up-to-date information.
    """
    try:
        cache_manager = CacheManager()
        
        # Get cache stats before clearing to show what will be deleted
        stats = cache_manager.get_cache_stats()
        
        if not stats.get('enabled', False):
            console.print("[yellow]Cache is disabled.[/yellow]")
            return
        
        total_entries = stats.get('total_entries', 0)
        cache_size_mb = stats.get('total_size_mb', 0)
        
        if total_entries == 0:
            console.print("[green]Cache is already empty.[/green]")
            return
        
        # Show what will be cleared
        console.print(f"[yellow]About to clear {total_entries} cache entries ({cache_size_mb} MB)[/yellow]")
        
        # Ask for confirmation unless --force is used
        if not force:
            confirm = typer.confirm("Are you sure you want to clear all cache entries?")
            if not confirm:
                console.print("[blue]Cache clear cancelled.[/blue]")
                return
        
        # Clear the cache
        cache_manager.invalidate()  # Clear all entries
        
        console.print(f"[green]Successfully cleared {total_entries} cache entries ({cache_size_mb} MB)[/green]")
        
    except Exception as e:
        console.print(f"[red]Error clearing cache: {e}[/red]")
        raise typer.Exit(1)


@app.command("status")
def cache_status():
    """Display cache status and statistics.
    
    Shows information about the current cache including:
    - Number of cached entries
    - Total cache size
    - Cache configuration settings
    - Recent cache entries with expiration times
    """
    try:
        cache_manager = CacheManager()
        stats = cache_manager.get_cache_stats()
        
        # Handle error case
        if 'error' in stats:
            console.print(f"[red]Error getting cache status: {stats['error']}[/red]")
            return
        
        # Display cache status header
        console.print("\n[bold blue]Cache Status[/bold blue]")
        console.print("=" * 50)
        
        # Display basic statistics
        console.print(f"[green]Cache Enabled:[/green] {'Yes' if stats['enabled'] else 'No'}")
        
        if not stats['enabled']:
            console.print("[yellow]Cache is disabled. No statistics available.[/yellow]")
            return
        
        console.print(f"[green]Cache Directory:[/green] {stats['cache_directory']}")
        console.print(f"[green]Total Entries:[/green] {stats['total_entries']}")
        console.print(f"[green]Valid Entries:[/green] {stats['valid_entries']}")
        console.print(f"[green]Expired Entries:[/green] {stats['expired_entries']}")
        console.print(f"[green]Total Size:[/green] {stats['total_size_mb']} MB ({stats['total_size_bytes']} bytes)")
        
        # Display cache size management information
        try:
            size_info = cache_manager.get_cache_size_info()
            usage_pct = size_info.get('usage_percentage', 0)
            
            if size_info.get('is_over_limit', False):
                console.print(f"[red]Cache Usage:[/red] {usage_pct}% (OVER LIMIT)")
                console.print(f"[red]Over Limit By:[/red] {size_info.get('bytes_over_limit', 0)} bytes")
            elif usage_pct > 80:
                console.print(f"[yellow]Cache Usage:[/yellow] {usage_pct}% (HIGH)")
            else:
                console.print(f"[green]Cache Usage:[/green] {usage_pct}%")
            
            console.print(f"[green]Available Space:[/green] {size_info.get('available_space_mb', 0)} MB")
        except Exception as e:
            console.print(f"[yellow]Cache Usage:[/yellow] Unable to calculate ({e})")
        
        # Display configuration settings
        console.print("\n[bold blue]Configuration Settings[/bold blue]")
        console.print("-" * 30)
        console.print(f"[green]Default TTL:[/green] {stats['default_ttl']} seconds ({stats['default_ttl'] // 60} minutes)")
        console.print(f"[green]Max Cache Size:[/green] {stats['max_size_mb']} MB")
        
        # Display recent cache entries if any exist
        if stats['total_entries'] > 0:
            _display_recent_cache_entries(cache_manager)
        else:
            console.print("\n[yellow]No cache entries found.[/yellow]")
            
    except Exception as e:
        console.print(f"[red]Error displaying cache status: {e}[/red]")
        raise typer.Exit(1)


@app.command("warm")
def warm_cache(
    command: str = typer.Argument(..., help="Command to warm up (e.g., 'user list', 'group list')"),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile to use for cache warming"),
    region: Optional[str] = typer.Option(None, "--region", help="AWS region to use for cache warming"),
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
        cache_manager = CacheManager()
        
        if not cache_manager.config.enabled:
            console.print("[yellow]Cache is disabled. Cannot warm cache.[/yellow]")
            return
        
        # Get cache stats before warming
        stats_before = cache_manager.get_cache_stats()
        entries_before = stats_before.get('total_entries', 0)
        
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
            console.print(f"[red]Error: Unknown command '{command_parts[0]}'. Valid commands: {', '.join(valid_commands)}[/red]")
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
                full_command,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                console.print(f"[red]Error executing command: {result.stderr}[/red]")
                raise typer.Exit(1)
            
        except subprocess.TimeoutExpired:
            console.print("[red]Error: Command timed out after 5 minutes[/red]")
            raise typer.Exit(1)
        except FileNotFoundError:
            console.print("[red]Error: Could not find awsideman executable. Make sure it's installed and in PATH.[/red]")
            raise typer.Exit(1)
        
        # Get cache stats after warming
        stats_after = cache_manager.get_cache_stats()
        entries_after = stats_after.get('total_entries', 0)
        
        # Calculate the difference
        new_entries = entries_after - entries_before
        
        if new_entries > 0:
            console.print(f"[green]✓ Cache warmed successfully! Added {new_entries} new cache entries.[/green]")
        elif new_entries == 0:
            console.print("[yellow]Cache was already warm for this command (no new entries added).[/yellow]")
        else:
            # This shouldn't happen unless cache was cleared during execution
            console.print("[yellow]Cache state changed during warm-up.[/yellow]")
        
        console.print(f"[dim]Total cache entries: {entries_after}[/dim]")
        
    except Exception as e:
        console.print(f"[red]Error warming cache: {e}[/red]")
        raise typer.Exit(1)


def _display_recent_cache_entries(cache_manager: CacheManager) -> None:
    """Display recent cache entries with expiration information.
    
    Args:
        cache_manager: CacheManager instance to get cache entries from
    """
    try:
        # Get list of cache files
        cache_files = cache_manager.path_manager.list_cache_files()
        
        if not cache_files:
            return
        
        console.print("\n[bold blue]Recent Cache Entries[/bold blue]")
        console.print("-" * 30)
        
        # Create table for cache entries
        table = Table()
        table.add_column("Operation", style="cyan", no_wrap=True)
        table.add_column("Age", style="green")
        table.add_column("TTL Remaining", style="yellow")
        table.add_column("Status", style="magenta")
        table.add_column("Size", style="blue")
        
        # Load and sort cache entries by creation time (most recent first)
        cache_entries = []
        current_time = time.time()
        
        for cache_file in cache_files:
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                
                cache_entry = CacheEntry(
                    data=cache_data['data'],
                    created_at=cache_data['created_at'],
                    ttl=cache_data['ttl'],
                    key=cache_data['key'],
                    operation=cache_data['operation']
                )
                
                # Calculate file size
                file_size_bytes = cache_file.stat().st_size
                file_size_kb = round(file_size_bytes / 1024, 1)
                
                cache_entries.append((cache_entry, file_size_kb))
                
            except Exception as e:
                # Skip corrupted cache files
                console.print(f"[red]Warning: Corrupted cache file {cache_file.name}: {e}[/red]")
                continue
        
        # Sort by creation time (most recent first)
        cache_entries.sort(key=lambda x: x[0].created_at, reverse=True)
        
        # Display up to 10 most recent entries
        for cache_entry, file_size_kb in cache_entries[:10]:
            # Calculate age and remaining TTL
            age_seconds = cache_entry.age_seconds(current_time)
            remaining_ttl = cache_entry.remaining_ttl(current_time)
            
            # Format age
            if age_seconds < 60:
                age_str = f"{int(age_seconds)}s"
            elif age_seconds < 3600:
                age_str = f"{int(age_seconds // 60)}m {int(age_seconds % 60)}s"
            else:
                hours = int(age_seconds // 3600)
                minutes = int((age_seconds % 3600) // 60)
                age_str = f"{hours}h {minutes}m"
            
            # Format remaining TTL
            if remaining_ttl <= 0:
                ttl_str = "Expired"
                status = "🔴 Expired"
            elif remaining_ttl < 60:
                ttl_str = f"{int(remaining_ttl)}s"
                status = "🟢 Valid"
            elif remaining_ttl < 3600:
                ttl_str = f"{int(remaining_ttl // 60)}m"
                status = "🟢 Valid"
            else:
                hours = int(remaining_ttl // 3600)
                minutes = int((remaining_ttl % 3600) // 60)
                ttl_str = f"{hours}h {minutes}m"
                status = "🟢 Valid"
            
            # Format file size
            if file_size_kb < 1:
                size_str = f"{int(file_size_kb * 1024)}B"
            else:
                size_str = f"{file_size_kb}KB"
            
            # Truncate operation name if too long
            operation_display = cache_entry.operation
            if len(operation_display) > 20:
                operation_display = operation_display[:17] + "..."
            
            table.add_row(
                operation_display,
                age_str,
                ttl_str,
                status,
                size_str
            )
        
        console.print(table)
        
        # Show summary if there are more entries
        total_entries = len(cache_entries)
        if total_entries > 10:
            console.print(f"\n[dim]Showing 10 most recent entries out of {total_entries} total entries.[/dim]")
        
    except Exception as e:
        console.print(f"[red]Error displaying cache entries: {e}[/red]")