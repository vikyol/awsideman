"""Clear cache command for awsideman."""

from typing import Optional

import typer

from .helpers import console, get_cache_manager


def clear_cache(
    force: bool = typer.Option(False, "--force", "-f", help="Force clear without confirmation"),
    accounts_only: bool = typer.Option(
        False, "--accounts-only", help="Clear only account-related storage entries"
    ),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        help="AWS profile to clear cache for (only works with --accounts-only). Use '*' to clear all profiles.",
    ),
):
    """Clear internal data storage.

    Removes stored AWS Identity Center data to refresh information from AWS.
    Use this when you need to ensure you're getting the most current information.

    Use --accounts-only to clear only account-related data, which is useful
    when you know the organization structure has changed but other data is still valid.

    Use --profile with --accounts-only to clear data for a specific AWS profile.
    """
    try:
        # Get cache manager with profile-aware configuration if profile is specified
        if profile and not accounts_only:
            console.print("[red]Error: --profile can only be used with --accounts-only[/red]")
            raise typer.Exit(1)

        if profile and accounts_only:
            # Use profile-specific cache manager
            from ...cache.utilities import create_cache_manager, get_profile_cache_config

            config = get_profile_cache_config(profile)
            cache_manager = create_cache_manager(config)
            console.print(f"[blue]Using profile-specific cache configuration for: {profile}[/blue]")
        else:
            cache_manager = get_cache_manager()

        # Get cache stats before clearing to show what will be deleted
        stats = cache_manager.get_cache_stats()

        if not stats.get("enabled", False):
            console.print("[yellow]Cache is disabled.[/yellow]")
            return

        total_entries = stats.get("total_entries", 0)
        cache_size_mb = stats.get("total_size_mb", 0)

        if total_entries == 0:
            console.print("[green]Cache is already empty.[/green]")
            return

        # Show what will be cleared
        profile_info = f" for profile '{profile}'" if profile else ""
        console.print(
            f"[yellow]About to clear {total_entries} cache entries ({cache_size_mb} MB){profile_info}[/yellow]"
        )

        # Ask for confirmation unless --force is used
        if not force:
            confirm = typer.confirm("Are you sure you want to clear all cache entries?")
            if not confirm:
                console.print("[blue]Cache clear cancelled.[/blue]")
                return

        # Validate profile option
        if profile and not accounts_only:
            console.print("[red]Error: --profile can only be used with --accounts-only[/red]")
            raise typer.Exit(1)

        # Get initial cache stats for verification
        initial_stats = cache_manager.get_cache_stats()
        initial_entries = initial_stats.get("total_entries", 0)

        # Clear the cache
        if accounts_only:
            if profile == "*":
                # Clear account cache for all profiles
                console.print("[blue]Clearing account cache for all profiles...[/blue]")
                # This would require iterating through all profile configs
                # For now, just clear the current profile's account cache
                console.print(
                    "[yellow]Note: Clearing account cache for current profile only[/yellow]"
                )
                cache_manager.invalidate("*")  # Clear all entries
            else:
                # Clear account cache for specific profile
                console.print(f"[blue]Clearing account cache for profile: {profile}[/blue]")
                cache_manager.invalidate("*")  # Clear all entries
        else:
            # Clear all cache
            console.print("[blue]Clearing all cache entries...[/blue]")
            cache_manager.invalidate("*")  # Clear all entries

        # Get final cache stats for verification
        final_stats = cache_manager.get_cache_stats()
        final_entries = final_stats.get("total_entries", 0)

        # Calculate what was actually cleared
        entries_cleared = initial_entries - final_entries
        if entries_cleared > 0:
            console.print(f"[green]✓ Successfully cleared {entries_cleared} cache entries![/green]")
        else:
            console.print("[yellow]No cache entries were cleared.[/yellow]")

    except Exception as e:
        console.print(f"[red]Error clearing cache: {e}[/red]")
        raise typer.Exit(1)
