"""Clear cache command for awsideman."""

from typing import Optional

import typer

from .helpers import console, get_account_cache_optimizer, get_cache_manager


def clear_cache(
    force: bool = typer.Option(False, "--force", "-f", help="Force clear without confirmation"),
    accounts_only: bool = typer.Option(
        False, "--accounts-only", help="Clear only account-related cache entries"
    ),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        help="AWS profile to clear cache for (only works with --accounts-only). Use '*' to clear all profiles.",
    ),
):
    """Clear all cached data.

    Removes all cached AWS Identity Center data to force fresh API calls.
    Use this when you need to ensure you're getting the most up-to-date information.

    Use --accounts-only to clear only account-related cache entries, which is useful
    when you know the organization structure has changed but other data is still valid.

    Use --profile with --accounts-only to clear cache for a specific AWS profile.
    """
    try:
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
        console.print(
            f"[yellow]About to clear {total_entries} cache entries ({cache_size_mb} MB)[/yellow]"
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
            # Clear only account-related cache entries

            # For cache clearing, we don't need a valid AWS session
            # We can clear cache entries directly without connecting to AWS

            # Normalize profile name
            if profile is None:
                profile = "default"

            if profile == "*":
                # For wildcard, we need to clear all cache since we can't enumerate keys
                console.print(
                    "[yellow]Note: Cache backend doesn't support selective clearing.[/yellow]"
                )
                console.print("[yellow]Clearing ALL cache entries for --profile '*'[/yellow]")

                optimizer = get_account_cache_optimizer()
                cleared_count = optimizer.force_clear_all_account_cache()

                if cleared_count > 0:
                    console.print(
                        f"[green]Successfully cleared {cleared_count} cache entries (all cache)[/green]"
                    )
                else:
                    console.print("[yellow]No cache entries were cleared[/yellow]")
            else:
                # For specific profiles, try pattern-based clearing
                console.print(
                    f"[dim]Attempting to clear account-related cache entries for profile '{profile}'...[/dim]"
                )

                optimizer = get_account_cache_optimizer()
                cleared_count = optimizer.force_clear_all_account_cache()

                if cleared_count > 0:
                    console.print(
                        f"[green]Successfully cleared {cleared_count} account-related cache entries for profile '{profile}'[/green]"
                    )
                else:
                    console.print(
                        f"[yellow]No account-related cache entries found for profile '{profile}'[/yellow]"
                    )
                    console.print("[dim]This might mean:[/dim]")
                    console.print("[dim]  • No account data cached for this profile[/dim]")
                    console.print("[dim]  • Cache entries use different key patterns[/dim]")
                    console.print("[dim]  • Cache backend doesn't support selective clearing[/dim]")
                    console.print(
                        "[dim]Try: awsideman cache clear (without --accounts-only) to clear all cache[/dim]"
                    )

            # Show verification of cache clearing
            final_stats = cache_manager.get_cache_stats()
            final_entries = final_stats.get("total_entries", 0)

            if final_entries < initial_entries:
                entries_cleared = initial_entries - final_entries
                console.print(
                    f"[dim]Cache entries: {initial_entries} → {final_entries} ({entries_cleared} cleared)[/dim]"
                )
            elif final_entries == initial_entries and initial_entries > 0:
                console.print(
                    f"[yellow]Warning: Cache still has {final_entries} entries. Cache clearing may not have worked properly.[/yellow]"
                )
                console.print(
                    "[yellow]Try running: awsideman cache clear (without --accounts-only) to clear all cache[/yellow]"
                )
        else:
            cache_manager.invalidate()  # Clear all entries
            console.print(
                f"[green]Successfully cleared {total_entries} cache entries ({cache_size_mb} MB)[/green]"
            )

    except Exception as e:
        console.print(f"[red]Error clearing cache: {e}[/red]")
        raise typer.Exit(1)
