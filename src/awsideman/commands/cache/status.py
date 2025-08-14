"""Cache status command for awsideman."""

import typer

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
        encryption_provider = cache_manager.get_encryption_provider()
        if encryption_provider:
            console.print("[green]Encryption:[/green] Enabled")
            console.print(f"[green]Provider:[/green] {type(encryption_provider).__name__}")

            # Display key information if available
            if hasattr(encryption_provider, "get_key_info"):
                key_info = encryption_provider.get_key_info()
                if key_info:
                    console.print(f"[green]Key Info:[/green] {key_info}")
        else:
            console.print("[yellow]Encryption:[/yellow] Disabled")
    except Exception as e:
        console.print(f"[yellow]Encryption Status:[/yellow] Unable to retrieve ({e})")


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
            if health.get("healthy", False):
                console.print("[green]Backend Health:[/green] Healthy")
            else:
                console.print("[red]Backend Health:[/red] Unhealthy")
                if "error" in health:
                    console.print(f"[red]Error:[/red] {health['error']}")
        else:
            console.print("[yellow]Backend Health:[/yellow] Unable to check")
    except Exception as e:
        console.print(f"[yellow]Backend Health:[/yellow] Unable to check ({e})")


def _display_recent_cache_entries(cache_manager) -> None:
    """Display recent cache entries with expiration times."""
    try:
        console.print("\n[bold blue]Recent Cache Entries[/bold blue]")
        console.print("-" * 30)

        # Get recent entries (limit to first 10)
        entries = cache_manager.get_recent_entries(limit=10)
        if entries:
            for entry in entries:
                key = entry.get("key", "Unknown")
                ttl = entry.get("ttl", "Unknown")
                size = entry.get("size", "Unknown")
                console.print(f"[green]{key}[/green] - TTL: {ttl}, Size: {size}")
        else:
            console.print("[yellow]No recent entries available[/yellow]")
    except Exception as e:
        console.print(f"[yellow]Recent Entries:[/yellow] Unable to retrieve ({e})")


def cache_status():
    """Display cache status and statistics.

    Shows information about the current cache including:
    - Backend type and configuration
    - Encryption status and key information
    - Number of cached entries and total cache size
    - Backend-specific statistics and health status
    - Recent cache entries with expiration times
    """
    try:
        cache_manager = get_cache_manager()
        stats = cache_manager.get_cache_stats()

        # Handle error case
        if "error" in stats:
            console.print(f"[red]Error getting cache status: {stats['error']}[/red]")
            return

        # Display cache status header
        console.print("\n[bold blue]Cache Status[/bold blue]")
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

        # Display backend-specific statistics and health status
        _display_backend_statistics(cache_manager)

        # Display legacy cache information for backward compatibility
        if hasattr(cache_manager, "path_manager") and cache_manager.path_manager:
            console.print(f"[green]Cache Directory:[/green] {stats['cache_directory']}")

        console.print(f"[green]Total Entries:[/green] {stats['total_entries']}")
        console.print(f"[green]Valid Entries:[/green] {stats['valid_entries']}")
        console.print(f"[green]Expired Entries:[/green] {stats['expired_entries']}")
        console.print(
            f"[green]Total Size:[/green] {stats['total_size_mb']} MB ({stats['total_size_bytes']} bytes)"
        )

        # Display cache size management information
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

        # Display recent cache entries if any exist
        if stats["total_entries"] > 0:
            _display_recent_cache_entries(cache_manager)
        else:
            console.print("\n[yellow]No cache entries found.[/yellow]")

    except Exception as e:
        console.print(f"[red]Error displaying cache status: {e}[/red]")
        raise typer.Exit(1)
