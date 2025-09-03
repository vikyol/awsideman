"""Cache cleanup command for awsideman."""

from typing import Optional

import typer

from ..common import advanced_cache_option, extract_standard_params, profile_option, region_option
from .helpers import console, get_cache_manager

app = typer.Typer(help="Clean up expired cache files and optimize cache storage.")


@app.command("expired")
def cleanup_expired(
    profile: Optional[str] = profile_option(),
    region: Optional[str] = region_option(),
    no_cache: bool = advanced_cache_option(),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
    force: bool = typer.Option(False, "--force", "-f", help="Force cleanup without confirmation"),
):
    """Clean up expired cache files from the filesystem.

    This command removes expired cache files to free up disk space and improve
    cache performance. It's safe to run and will only remove files that have
    exceeded their TTL (Time To Live).

    Examples:
        awsideman cache cleanup expired
        awsideman cache cleanup expired --profile production
        awsideman cache cleanup expired --force
        awsideman cache cleanup expired --verbose
    """
    try:
        # Extract and process standard command parameters
        profile_param, region_param, enable_caching = extract_standard_params(
            profile, region, no_cache
        )

        # Get cache manager with profile-aware configuration
        if profile_param:
            from ...cache.utilities import create_cache_manager, get_profile_cache_config

            config = get_profile_cache_config(profile_param)
            cache_manager = create_cache_manager(config, profile=profile_param)
            console.print(
                f"[blue]Using profile-specific cache configuration for: {profile_param}[/blue]"
            )
        else:
            cache_manager = get_cache_manager()

        if not cache_manager.config.enabled:
            console.print("[yellow]Cache is disabled. Nothing to clean up.[/yellow]")
            return

        # Show cache information if verbose
        if verbose:
            stats_before = cache_manager.get_cache_stats()
            console.print("[blue]Cache stats before cleanup:[/blue]")
            console.print(f"  Backend: {stats_before.get('backend_type', 'unknown')}")
            console.print(f"  Total entries: {stats_before.get('total_entries', 0)}")
            console.print(f"  Total size: {stats_before.get('total_size_mb', 0):.2f} MB")

        # Confirm cleanup unless forced
        if not force:
            console.print(
                "[yellow]This will remove expired cache files from the filesystem.[/yellow]"
            )
            console.print("[dim]Only files that have exceeded their TTL will be removed.[/dim]")

            try:
                confirm = typer.confirm("Do you want to continue?")
                if not confirm:
                    console.print("[blue]Cleanup cancelled.[/blue]")
                    return
            except typer.Abort:
                console.print("[blue]Cleanup cancelled.[/blue]")
                return

        console.print("[blue]Starting cache cleanup...[/blue]")

        # Clean up expired files
        removed_files = cache_manager.cleanup_expired_files()

        if removed_files > 0:
            console.print(f"[green]✓ Cleaned up {removed_files} expired cache files[/green]")
        else:
            console.print("[blue]No expired cache files found.[/blue]")

        # Show cache information after cleanup if verbose
        if verbose:
            stats_after = cache_manager.get_cache_stats()
            console.print("[blue]Cache stats after cleanup:[/blue]")
            console.print(f"  Backend: {stats_after.get('backend_type', 'unknown')}")
            console.print(f"  Total entries: {stats_after.get('total_entries', 0)}")
            console.print(f"  Total size: {stats_after.get('total_size_mb', 0):.2f} MB")

            if removed_files > 0:
                entries_before = stats_before.get("total_entries", 0)
                entries_after = stats_after.get("total_entries", 0)
                size_before = stats_before.get("total_size_mb", 0)
                size_after = stats_after.get("total_size_mb", 0)

                console.print("[green]Improvement:[/green]")
                console.print(f"  Entries removed: {entries_before - entries_after}")
                console.print(f"  Space freed: {size_before - size_after:.2f} MB")

    except Exception as e:
        console.print(f"[red]Error during cache cleanup: {str(e)}[/red]")
        if verbose:
            import traceback

            console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(1)


@app.command("all")
def cleanup_all(
    profile: Optional[str] = profile_option(),
    region: Optional[str] = region_option(),
    no_cache: bool = advanced_cache_option(),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
    force: bool = typer.Option(False, "--force", "-f", help="Force cleanup without confirmation"),
):
    """Clean up all cache files (both expired and valid).

    WARNING: This will remove ALL cache files, including valid ones.
    This will force a complete cache rebuild on next use.

    Examples:
        awsideman cache cleanup all --force
        awsideman cache cleanup all --profile production --force
    """
    try:
        # Extract and process standard command parameters
        profile_param, region_param, enable_caching = extract_standard_params(
            profile, region, no_cache
        )

        # Get cache manager with profile-aware configuration
        if profile_param:
            from ...cache.utilities import create_cache_manager, get_profile_cache_config

            config = get_profile_cache_config(profile_param)
            cache_manager = create_cache_manager(config, profile=profile_param)
            console.print(
                f"[blue]Using profile-specific cache configuration for: {profile_param}[/blue]"
            )
        else:
            cache_manager = get_cache_manager()

        if not cache_manager.config.enabled:
            console.print("[yellow]Cache is disabled. Nothing to clean up.[/yellow]")
            return

        # Show cache information if verbose
        if verbose:
            stats_before = cache_manager.get_cache_stats()
            console.print("[blue]Cache stats before cleanup:[/blue]")
            console.print(f"  Backend: {stats_before.get('backend_type', 'unknown')}")
            console.print(f"  Total entries: {stats_before.get('total_entries', 0)}")
            console.print(f"  Total size: {stats_before.get('total_size_mb', 0):.2f} MB")

        # Confirm cleanup unless forced
        if not force:
            console.print(
                "[red]WARNING: This will remove ALL cache files, including valid ones![/red]"
            )
            console.print("[yellow]This will force a complete cache rebuild on next use.[/yellow]")

            try:
                confirm = typer.confirm("Are you sure you want to continue?")
                if not confirm:
                    console.print("[blue]Cleanup cancelled.[/blue]")
                    return
            except typer.Abort:
                console.print("[blue]Cleanup cancelled.[/blue]")
                return

        console.print("[blue]Starting complete cache cleanup...[/blue]")

        # Clear all cache
        cache_manager.clear()

        console.print("[green]✓ Cleared all cache files[/green]")
        console.print("[yellow]Cache will be rebuilt on next use.[/yellow]")

    except Exception as e:
        console.print(f"[red]Error during cache cleanup: {str(e)}[/red]")
        if verbose:
            import traceback

            console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(1)
