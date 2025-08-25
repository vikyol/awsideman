"""Cache status command for awsideman."""

import json
from typing import Optional

import typer

from ..common import (
    advanced_cache_option,
    extract_standard_params,
    profile_option,
    region_option,
    verbose_option,
)
from .helpers import console, get_cache_manager


def _display_backend_configuration(cache_manager, actual_config=None) -> None:
    """Display backend configuration information."""
    try:
        # If we have actual configuration, use it for display
        if actual_config:
            backend_type = actual_config.backend_type
            console.print(f"[green]Backend Type:[/green] {backend_type}")

            # Display backend-specific configuration based on actual config
            if backend_type == "dynamodb":
                console.print(
                    f"[green]DynamoDB Table:[/green] {actual_config.dynamodb_table_name or 'Not configured'}"
                )
                console.print(
                    f"[green]DynamoDB Region:[/green] {actual_config.dynamodb_region or 'Not configured'}"
                )
                if actual_config.dynamodb_profile:
                    console.print(
                        f"[green]DynamoDB Profile:[/green] {actual_config.dynamodb_profile}"
                    )
            elif backend_type == "file":
                if actual_config.file_cache_dir:
                    console.print(
                        f"[green]File Cache Directory:[/green] {actual_config.file_cache_dir}"
                    )
            elif backend_type == "hybrid":
                console.print(
                    f"[green]Hybrid Local TTL:[/green] {actual_config.hybrid_local_ttl} seconds"
                )
                if actual_config.dynamodb_table_name:
                    console.print(
                        f"[green]DynamoDB Table:[/green] {actual_config.dynamodb_table_name}"
                    )
                if actual_config.file_cache_dir:
                    console.print(
                        f"[green]File Cache Directory:[/green] {actual_config.file_cache_dir}"
                    )
        else:
            # Fall back to cache manager backend detection
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
        # Check encryption status directly from backend
        encryption_enabled = False
        encryption_type = "none"

        if hasattr(cache_manager, "get_backend") and cache_manager.get_backend():
            backend = cache_manager.get_backend()
            if hasattr(backend, "get_stats"):
                try:
                    backend_stats = backend.get_stats()
                    if backend_stats.get("total_entries", 0) > 0:
                        # Sample a few files to check encryption status
                        if hasattr(backend, "path_manager"):
                            cache_files = backend.path_manager.list_cache_files()
                            for cache_file in cache_files[:3]:  # Check first 3 files
                                try:
                                    with open(cache_file, "rb") as f:
                                        file_content = f.read()
                                    if len(file_content) >= 4:
                                        metadata_length = int.from_bytes(
                                            file_content[:4], byteorder="big"
                                        )
                                        if metadata_length > 0 and metadata_length < len(
                                            file_content
                                        ):
                                            metadata_json = file_content[4 : 4 + metadata_length]
                                            metadata = json.loads(metadata_json.decode("utf-8"))
                                            if metadata.get("encrypted", False):
                                                encryption_enabled = True
                                                encryption_type = "aes"
                                                break
                                except Exception:
                                    continue
                except Exception:
                    pass

        # Fallback to config if backend check fails
        if not encryption_enabled and hasattr(cache_manager, "config") and cache_manager.config:
            config = cache_manager.config
            encryption_enabled = getattr(config, "encryption_enabled", False)
            encryption_type = getattr(config, "encryption_type", "none")

        console.print(
            f"[green]Encryption:[/green] {'Enabled' if encryption_enabled else 'Disabled'}"
        )
        if encryption_enabled:
            console.print(f"[green]Encryption Type:[/green] {encryption_type}")
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
                total_entries = size_info.get("total_entries", 0)
                max_entries = size_info.get("max_entries", 1000)

                # Calculate actual usage percentage based on entries
                if max_entries > 0:
                    actual_usage_pct = (total_entries / max_entries) * 100
                else:
                    actual_usage_pct = 0

                if size_info.get("is_over_limit", False):
                    console.print(f"[red]Storage Usage:[/red] {actual_usage_pct:.1f}% (OVER LIMIT)")
                    console.print(
                        f"[red]Over Limit By:[/red] {size_info.get('bytes_over_limit', 0)} bytes"
                    )
                elif actual_usage_pct > 80:
                    console.print(f"[yellow]Storage Usage:[/yellow] {actual_usage_pct:.1f}% (HIGH)")
                else:
                    console.print(f"[green]Storage Usage:[/green] {actual_usage_pct:.1f}%")

                console.print(
                    f"[green]Available Space:[/green] {size_info.get('available_space_mb', 0)} MB"
                )
            except Exception as e:
                console.print(f"[yellow]Storage Usage:[/yellow] Unable to calculate ({e})")

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
    """Display recent storage entries with expiration times."""
    try:
        console.print("\n[bold blue]Recent Storage Entries[/bold blue]")

        # Get recent entries (limit to first 10)
        entries = cache_manager.get_recent_entries(limit=10)

        if entries:
            # Create a table for better organization
            from rich.table import Table

            from ...cache.key_builder import CacheKeyBuilder

            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Operation", style="cyan", ratio=1)
            table.add_column("Resource", style="magenta", ratio=1)
            table.add_column("TTL", style="yellow", ratio=1)
            table.add_column("Age", style="blue", ratio=1)
            table.add_column("Size", style="green", ratio=1)
            table.add_column("Key", style="dim", ratio=3)

            for entry in entries:
                key = entry.get("key", "Unknown")
                ttl = entry.get("ttl", "Unknown")
                age = entry.get("age", "Unknown")
                size = entry.get("size", "Unknown")

                # Parse the cache key to extract operation and resource type
                try:
                    # First try the standard CacheKeyBuilder format
                    if ":" in key:
                        parsed_key = CacheKeyBuilder.parse_key(key)
                        operation = parsed_key.get("operation") or "Unknown"
                        resource_type = parsed_key.get("resource_type") or "Unknown"
                    else:
                        # Parse the actual cache key format (e.g., "list_organizational_units_for_parent_6765104b06d831b4")
                        operation = "Unknown"
                        resource_type = "Unknown"

                        # Try to extract meaningful information from the key
                        if key.startswith("list_"):
                            operation = "list"
                            # Extract resource type from the key
                            if "organizational_units" in key:
                                resource_type = "organizational_units"
                            elif "accounts" in key:
                                resource_type = "accounts"
                            elif "roots" in key:
                                resource_type = "roots"
                            elif "users" in key:
                                resource_type = "users"
                            elif "groups" in key:
                                resource_type = "groups"
                            elif "permission_sets" in key:
                                resource_type = "permission_sets"
                            elif "assignments" in key:
                                resource_type = "assignments"
                            else:
                                resource_type = "other"
                        elif key.startswith("describe_"):
                            operation = "describe"
                            # Extract resource type from the key
                            if "user" in key:
                                resource_type = "user"
                            elif "group" in key:
                                resource_type = "group"
                            elif "permission_set" in key:
                                resource_type = "permission_set"
                            elif "account" in key:
                                resource_type = "account"
                            else:
                                resource_type = "other"
                        elif key.startswith("get_"):
                            operation = "get"
                            resource_type = "other"
                        else:
                            # Try to guess from the key content
                            if "user" in key:
                                resource_type = "user"
                            elif "group" in key:
                                resource_type = "group"
                            elif "permission" in key:
                                resource_type = "permission_set"
                            elif "account" in key:
                                resource_type = "account"
                            elif "organizational" in key:
                                resource_type = "organizational_units"
                            else:
                                resource_type = "other"

                            # Try to guess operation
                            if "list" in key:
                                operation = "list"
                            elif "describe" in key:
                                operation = "describe"
                            elif "get" in key:
                                operation = "get"
                            else:
                                operation = "other"
                except Exception:
                    operation = "Unknown"
                    resource_type = "Unknown"

                # Truncate long keys for display
                display_key = key[:50] + "..." if len(key) > 50 else key

                # Color code based on expiration status
                if entry.get("is_expired", False):
                    row_style = "red"
                else:
                    row_style = "green"

                table.add_row(
                    operation, resource_type, ttl, age, size, display_key, style=row_style
                )

            console.print(table)
        else:
            console.print("[yellow]No recent entries available[/yellow]")
    except Exception as e:
        console.print(f"[yellow]Recent Entries:[/yellow] Unable to retrieve ({e})")


def cache_status(
    profile: Optional[str] = profile_option(),
    region: Optional[str] = region_option(),
    no_cache: bool = advanced_cache_option(),
    verbose: bool = verbose_option(),
):
    """Display internal data storage status and statistics.

    Shows information about the current data storage including:
    - Storage backend type and configuration
    - Encryption status and key information
    - Number of stored entries and total storage size
    - Backend-specific statistics and health status
    - Recent entries with expiration times
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
            # Try to get profile-specific cache manager for current profile
            try:
                from ...cache.utilities import get_profile_cache_config
                from ...utils.config import Config

                # Get current profile from config
                config = Config()
                config_data = config.get_all()
                current_profile = config_data.get("default_profile")

                if current_profile:
                    # Use profile-specific cache configuration
                    profile_config = get_profile_cache_config(current_profile)
                    cache_manager = create_cache_manager(profile_config)
                    console.print(
                        f"[dim]Using cache configuration for profile: {current_profile}[/dim]"
                    )
                else:
                    # Fall back to default cache manager
                    cache_manager = get_cache_manager()
            except Exception as e:
                console.print(f"[dim]Could not get profile-specific cache config: {e}[/dim]")
                # Fall back to default cache manager
                cache_manager = get_cache_manager()

        # Get the actual configuration for display purposes
        actual_config = None
        if profile_param:
            from ...cache.utilities import get_profile_cache_config

            actual_config = get_profile_cache_config(profile_param)
        else:
            try:
                from ...cache.utilities import get_profile_cache_config
                from ...utils.config import Config

                config = Config()
                config_data = config.get_all()
                current_profile = config_data.get("default_profile")

                if current_profile:
                    actual_config = get_profile_cache_config(current_profile)
            except Exception:
                pass

        # Show cache information if verbose (using the same cache manager)
        if verbose:
            # Get cache stats from the same cache manager for consistency
            verbose_stats = cache_manager.get_cache_stats()
            if verbose_stats.get("enabled", False):
                backend_type = verbose_stats.get("backend_type", "unknown")
                total_entries = verbose_stats.get("total_entries", 0)
                console.print(
                    f"[blue]Storage: {backend_type} backend, " f"{total_entries} entries[/blue]"
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
        _display_backend_configuration(cache_manager, actual_config)

        # Display encryption status and key information
        _display_encryption_status(cache_manager)

        # Display cache statistics
        _display_cache_statistics(stats, cache_manager)

        # Display configuration settings if we have actual config
        if actual_config:
            console.print("\n[bold blue]Configuration Settings[/bold blue]")
            console.print("-" * 40)
            console.print(
                f"[green]Default TTL:[/green] {actual_config.default_ttl} seconds ({actual_config.default_ttl // 60} minutes)"
            )
            console.print(f"[green]Max Cache Size:[/green] {actual_config.max_size_mb} MB")
            console.print(
                f"[green]Encryption:[/green] {'Enabled' if actual_config.encryption_enabled else 'Disabled'}"
            )
            if actual_config.encryption_enabled:
                console.print(f"[green]Encryption Type:[/green] {actual_config.encryption_type}")
        else:
            # Fall back to cache manager stats
            console.print("\n[bold blue]Configuration Settings[/bold blue]")
            console.print("-" * 40)
            console.print(
                f"[green]Default TTL:[/green] {stats.get('default_ttl', 'Unknown')} seconds"
            )
            console.print(
                f"[green]Max Cache Size:[/green] {stats.get('max_size_mb', 'Unknown')} MB"
            )

        # Display recent storage entries
        _display_recent_cache_entries(cache_manager)

    except Exception as e:
        console.print(f"[red]Error getting cache status: {e}[/red]")
        raise typer.Exit(1)
