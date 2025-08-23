"""Cache status command for awsideman."""

from typing import Optional

import typer

from ..common import (
    cache_option,
    extract_standard_params,
    profile_option,
    region_option,
    verbose_option,
)
from .helpers import console, get_cache_manager


def _display_backend_configuration(cache_manager) -> None:
    """Display backend configuration information."""
    try:
        backend = cache_manager.get_backend()
        if backend:
            backend_type = type(backend).__name__
            console.print(f"[green]Backend Type:[/green] {backend_type}")

            # Display backend-specific configuration
            if hasattr(backend, "get_config"):
                config = backend.get_config()
                if config:
                    console.print(f"[green]Backend Config:[/green] {config}")
        else:
            console.print("[yellow]Backend Type:[/yellow] Not configured")
    except Exception as e:
        console.print(f"[yellow]Backend Config:[/yellow] Unable to retrieve ({e})")


def _display_encryption_status(cache_manager) -> None:
    """Display encryption status and key information."""
    try:
        # Get encryption information from cache manager
        if hasattr(cache_manager, "config") and cache_manager.config:
            config = cache_manager.config
            encryption_enabled = getattr(config, "encryption_enabled", False)
            encryption_type = getattr(config, "encryption_type", "none")

            console.print(
                f"[green]Encryption:[/green] {'Enabled' if encryption_enabled else 'Disabled'}"
            )
            if encryption_enabled:
                console.print(f"[green]Encryption Type:[/green] {encryption_type}")
        else:
            console.print("[yellow]Encryption:[/yellow] Unable to retrieve")
    except Exception as e:
        console.print(f"[yellow]Encryption:[/yellow] Unable to retrieve ({e})")


def _display_cache_statistics(stats: dict, cache_manager=None) -> None:
    """Display cache statistics."""
    try:
        # Display backend-specific statistics and health status
        if stats.get("backend_type") == "file":
            # File backend specific fields
            console.print(f"[green]Valid Entries:[/green] {stats.get('valid_entries', 0)}")
            console.print(f"[green]Expired Entries:[/green] {stats.get('expired_entries', 0)}")
            console.print(f"[green]Corrupted Entries:[/green] {stats.get('corrupted_entries', 0)}")
        elif stats.get("backend_type") == "dynamodb":
            # DynamoDB backend specific fields
            if "item_count" in stats:
                console.print(f"[green]Table Items:[/green] {stats['item_count']}")
            if "table_status" in stats:
                console.print(f"[green]Table Status:[/green] {stats['table_status']}")
            if "ttl_enabled" in stats:
                console.print(
                    f"[green]TTL Enabled:[/green] {'Yes' if stats['ttl_enabled'] else 'No'}"
                )

        # Display total size if available
        if "total_size_mb" in stats and "total_size_bytes" in stats:
            console.print(
                f"[green]Total Size:[/green] {stats['total_size_mb']} MB ({stats['total_size_bytes']} bytes)"
            )

        # Display cache size management information
        if cache_manager and hasattr(cache_manager, "get_cache_size_info"):
            try:
                size_info = cache_manager.get_cache_size_info()
                usage_pct = size_info.get("usage_percentage", 0)

                if size_info.get("is_over_limit", False):
                    console.print(f"[red]Cache Usage:[/red] {usage_pct}% (OVER LIMIT)")
                    console.print(
                        f"[red]Over Limit By:[/red] {size_info.get('bytes_over_limit', 0)} bytes"
                    )
                elif usage_pct > 80:
                    console.print(f"[yellow]Cache Usage:[/yellow] {usage_pct}% (HIGH)")
                else:
                    console.print(f"[green]Cache Usage:[/green] {usage_pct}%")

                console.print(
                    f"[green]Available Space:[/green] {size_info.get('available_space_mb', 0)} MB"
                )
            except Exception as e:
                console.print(f"[yellow]Cache Usage:[/yellow] Unable to calculate ({e})")

        # Display configuration settings
        console.print("\n[bold blue]Configuration Settings[/bold blue]")
        console.print("-" * 30)
        console.print(
            f"[green]Default TTL:[/green] {stats['default_ttl']} seconds ({stats['default_ttl'] // 60} minutes)"
        )
        console.print(f"[green]Max Cache Size:[/green] {stats['max_size_mb']} MB")

        # Display total entries
        console.print(f"[green]Total Entries:[/green] {stats['total_entries']}")

    except Exception as e:
        console.print(f"[yellow]Cache Statistics:[/yellow] Unable to retrieve ({e})")


def _display_backend_statistics(cache_manager) -> None:
    """Display backend-specific statistics and health status."""
    try:
        backend = cache_manager.get_backend()
        if backend:
            # Display backend health
            _display_backend_health(backend)

            # Display backend-specific stats
            if hasattr(backend, "get_statistics"):
                stats = backend.get_statistics()
                if stats:
                    console.print("\n[bold blue]Backend Statistics[/bold blue]")
                    console.print("-" * 25)
                    for key, value in stats.items():
                        console.print(f"[green]{key}:[/green] {value}")
    except Exception as e:
        console.print(f"[yellow]Backend Statistics:[/yellow] Unable to retrieve ({e})")


def _display_backend_health(backend) -> None:
    """Display backend health status."""
    try:
        if hasattr(backend, "health_check"):
            health = backend.health_check()
            if isinstance(health, dict):
                if health.get("healthy", False):
                    console.print("[green]Backend Health:[/green] Healthy")
                    if "message" in health:
                        console.print(f"[dim]Status:[/dim] {health['message']}")
                else:
                    console.print("[red]Backend Health:[/red] Unhealthy")
                    if "message" in health:
                        console.print(f"[red]Error:[/red] {health['message']}")
                    if "error" in health:
                        console.print(f"[red]Details:[/red] {health['error']}")
            else:
                # Fallback for boolean return values (legacy support)
                if health:
                    console.print("[green]Backend Health:[/green] Healthy")
                else:
                    console.print("[red]Backend Health:[/red] Unhealthy")
        else:
            console.print("[yellow]Backend Health:[/yellow] Unable to check")
    except Exception as e:
        console.print(f"[yellow]Backend Health:[/yellow] Unable to check ({e})")


def _display_recent_cache_entries(cache_manager) -> None:
    """Display recent cache entries with expiration times."""
    try:
        console.print("\n[bold blue]Recent Cache Entries[/bold blue]")

        # Get recent entries (limit to first 10)
        entries = cache_manager.get_recent_entries(limit=10)

        if entries:
            # Create a table for better organization
            from rich.table import Table

            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Operation", style="cyan", ratio=2)
            table.add_column("TTL", style="yellow", ratio=1)
            table.add_column("Age", style="blue", ratio=1)
            table.add_column("Size", style="green", ratio=1)
            table.add_column("Key", style="dim", ratio=3)

            for entry in entries:
                operation = entry.get("operation", "Unknown")
                ttl = entry.get("ttl", "Unknown")
                age = entry.get("age", "Unknown")
                size = entry.get("size", "Unknown")
                key = entry.get("key", "Unknown")

                # Truncate long keys for display
                display_key = key  # [:50] + "..." if len(key) > 50 else key

                # Color code based on expiration status
                if entry.get("is_expired", False):
                    row_style = "red"
                else:
                    row_style = "green"

                table.add_row(operation, ttl, age, size, display_key, style=row_style)

            console.print(table)
        else:
            console.print("[yellow]No recent entries available[/yellow]")
    except Exception as e:
        console.print(f"[yellow]Recent Entries:[/yellow] Unable to retrieve ({e})")


def cache_status(
    profile: Optional[str] = profile_option(),
    region: Optional[str] = region_option(),
    no_cache: bool = cache_option(),
    verbose: bool = verbose_option(),
):
    """Display cache status and statistics.

    Shows information about the current cache including:
    - Backend type and configuration
    - Encryption status and key information
    - Number of cached entries and total cache size
    - Backend-specific statistics and health status
    - Recent cache entries with expiration times
    """
    try:
        # Extract and process standard command parameters
        profile_param, region_param, enable_caching = extract_standard_params(
            profile, region, no_cache
        )

        # Get cache manager with profile-aware configuration
        if profile_param:
            # Create a cache manager with the specified profile
            from ...cache.utilities import create_cache_manager, get_profile_cache_config

            config = get_profile_cache_config(profile_param)
            cache_manager = create_cache_manager(config)
        else:
            cache_manager = get_cache_manager()

        # Show cache information if verbose (using the same cache manager)
        if verbose:
            # Get cache stats from the same cache manager for consistency
            verbose_stats = cache_manager.get_cache_stats()
            if verbose_stats.get("enabled", False):
                backend_type = verbose_stats.get("backend_type", "unknown")
                total_entries = verbose_stats.get("total_entries", 0)
                console.print(
                    f"[blue]Cache: {backend_type} backend, " f"{total_entries} entries[/blue]"
                )
            else:
                console.print("[blue]Cache: Disabled[/blue]")

        stats = cache_manager.get_cache_stats()

        # Handle error case
        if "error" in stats:
            console.print(f"[red]Error getting cache status: {stats['error']}[/red]")
            return

        # Display cache status header
        console.print("\n[bold blue]Cache Status[/bold blue]")
        if profile_param:
            console.print(f"[blue]Profile: {profile_param}[/blue]")
        console.print("=" * 50)

        # Display basic statistics
        console.print(f"[green]Cache Enabled:[/green] {'Yes' if stats['enabled'] else 'No'}")

        if not stats["enabled"]:
            console.print("[yellow]Cache is disabled. No statistics available.[/yellow]")
            return

        # Display backend type and configuration
        _display_backend_configuration(cache_manager)

        # Display encryption status and key information
        _display_encryption_status(cache_manager)

        # Display cache statistics
        _display_cache_statistics(stats, cache_manager)

        # Display recent cache entries
        _display_recent_cache_entries(cache_manager)

    except Exception as e:
        console.print(f"[red]Error getting cache status: {e}[/red]")
        raise typer.Exit(1)
