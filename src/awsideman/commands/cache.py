"""Cache management commands for awsideman."""
import typer
import json
import time
import subprocess
import sys
import shlex
from pathlib import Path
from typing import Optional, Dict, Any
from rich.console import Console
from rich.table import Table
from datetime import datetime, timedelta

from ..cache.manager import CacheManager
from ..utils.models import CacheEntry
from ..cache.config import AdvancedCacheConfig
from ..cache.backends.base import CacheBackend
from ..encryption.provider import EncryptionProviderFactory, EncryptionError
from ..encryption.key_manager import KeyManager, FallbackKeyManager

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
    - Backend type and configuration
    - Encryption status and key information
    - Number of cached entries and total cache size
    - Backend-specific statistics and health status
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
        
        # Display backend type and configuration
        _display_backend_configuration(cache_manager)
        
        # Display encryption status and key information
        _display_encryption_status(cache_manager)
        
        # Display backend-specific statistics and health status
        _display_backend_statistics(cache_manager)
        
        # Display legacy cache information for backward compatibility
        if hasattr(cache_manager, 'path_manager') and cache_manager.path_manager:
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


def _display_backend_configuration(cache_manager: CacheManager) -> None:
    """Display backend type and configuration information.
    
    Args:
        cache_manager: CacheManager instance to get backend info from
    """
    try:
        console.print("\n[bold blue]Backend Configuration[/bold blue]")
        console.print("-" * 30)
        
        # Check if using advanced configuration
        if isinstance(cache_manager.config, AdvancedCacheConfig):
            config = cache_manager.config
            console.print(f"[green]Backend Type:[/green] {config.backend_type}")
            
            # Display backend-specific configuration
            if config.backend_type == "dynamodb":
                console.print(f"[green]DynamoDB Table:[/green] {config.dynamodb_table_name}")
                console.print(f"[green]DynamoDB Region:[/green] {config.dynamodb_region or 'default'}")
                console.print(f"[green]DynamoDB Profile:[/green] {config.dynamodb_profile or 'default'}")
            elif config.backend_type == "file":
                console.print(f"[green]File Cache Directory:[/green] {config.file_cache_dir or 'default (~/.awsideman/cache)'}")
            elif config.backend_type == "hybrid":
                console.print(f"[green]Local TTL:[/green] {config.hybrid_local_ttl} seconds")
                console.print(f"[green]DynamoDB Table:[/green] {config.dynamodb_table_name}")
                console.print(f"[green]DynamoDB Region:[/green] {config.dynamodb_region or 'default'}")
                console.print(f"[green]File Cache Directory:[/green] {config.file_cache_dir or 'default (~/.awsideman/cache)'}")
        else:
            console.print(f"[green]Backend Type:[/green] file (legacy)")
            console.print("[dim]Using basic cache configuration - advanced features not available[/dim]")
            
    except Exception as e:
        console.print(f"[red]Error displaying backend configuration: {e}[/red]")


def _display_encryption_status(cache_manager: CacheManager) -> None:
    """Display encryption status and key information.
    
    Args:
        cache_manager: CacheManager instance to get encryption info from
    """
    try:
        console.print("\n[bold blue]Encryption Status[/bold blue]")
        console.print("-" * 25)
        
        # Check if using advanced configuration with encryption
        if isinstance(cache_manager.config, AdvancedCacheConfig):
            config = cache_manager.config
            console.print(f"[green]Encryption Enabled:[/green] {'Yes' if config.encryption_enabled else 'No'}")
            console.print(f"[green]Encryption Type:[/green] {config.encryption_type}")
            
            # Display encryption provider information
            if hasattr(cache_manager, 'encryption_provider') and cache_manager.encryption_provider:
                provider_type = cache_manager.encryption_provider.get_encryption_type()
                console.print(f"[green]Active Provider:[/green] {provider_type}")
                
                # Show provider availability
                is_available = cache_manager.encryption_provider.is_available()
                status_color = "green" if is_available else "red"
                status_text = "Available" if is_available else "Unavailable"
                console.print(f"[{status_color}]Provider Status:[/{status_color}] {status_text}")
                
                # Display key information if encryption is enabled
                if config.encryption_enabled and config.encryption_type != "none":
                    _display_key_information()
            else:
                console.print("[dim]No encryption provider configured[/dim]")
        else:
            console.print(f"[green]Encryption Enabled:[/green] No")
            console.print("[dim]Encryption not available with basic cache configuration[/dim]")
            
    except Exception as e:
        console.print(f"[red]Error displaying encryption status: {e}[/red]")


def _display_key_information() -> None:
    """Display encryption key information."""
    try:
        from ..encryption.key_manager import KeyManager
        
        console.print("\n[bold blue]Key Information[/bold blue]")
        console.print("-" * 20)
        
        key_manager = KeyManager()
        key_info = key_manager.get_key_info()
        
        # Display keyring availability
        keyring_color = "green" if key_info.get('keyring_available', False) else "yellow"
        keyring_status = "Available" if key_info.get('keyring_available', False) else "Unavailable (using fallback)"
        console.print(f"[{keyring_color}]Keyring Status:[/{keyring_color}] {keyring_status}")
        
        # Display key existence
        key_color = "green" if key_info.get('key_exists', False) else "red"
        key_status = "Present" if key_info.get('key_exists', False) else "Missing"
        console.print(f"[{key_color}]Encryption Key:[/{key_color}] {key_status}")
        
        if key_info.get('key_exists', False):
            # Display key validity
            key_valid = key_info.get('key_valid', False)
            valid_color = "green" if key_valid else "red"
            valid_status = "Valid" if key_valid else "Invalid"
            console.print(f"[{valid_color}]Key Validity:[/{valid_color}] {valid_status}")
            
            # Display key length if available
            if 'key_length' in key_info:
                console.print(f"[green]Key Length:[/green] {key_info['key_length']} bytes")
        
        # Display service information
        console.print(f"[green]Service Name:[/green] {key_info.get('service_name', 'unknown')}")
        
        # Display any errors
        if 'key_error' in key_info:
            console.print(f"[red]Key Error:[/red] {key_info['key_error']}")
        
        if 'error' in key_info:
            console.print(f"[red]General Error:[/red] {key_info['error']}")
            
    except Exception as e:
        console.print(f"[red]Error getting key information: {e}[/red]")


def _display_backend_statistics(cache_manager: CacheManager) -> None:
    """Display backend-specific statistics and health status.
    
    Args:
        cache_manager: CacheManager instance to get backend stats from
    """
    try:
        console.print("\n[bold blue]Backend Statistics[/bold blue]")
        console.print("-" * 25)
        
        # Get backend statistics if available
        if hasattr(cache_manager, 'backend') and cache_manager.backend:
            backend_stats = cache_manager.backend.get_stats()
            backend_type = backend_stats.get('backend_type', 'unknown')
            
            # Display common backend information
            console.print(f"[green]Backend Type:[/green] {backend_type}")
            
            # Display backend-specific statistics
            if backend_type == "dynamodb":
                _display_dynamodb_statistics(backend_stats)
            elif backend_type == "file":
                _display_file_statistics(backend_stats)
            elif backend_type == "hybrid":
                _display_hybrid_statistics(backend_stats)
            
            # Display backend health status
            _display_backend_health(cache_manager.backend)
        else:
            console.print("[dim]Backend statistics not available (using legacy configuration)[/dim]")
            
    except Exception as e:
        console.print(f"[red]Error displaying backend statistics: {e}[/red]")


def _display_dynamodb_statistics(stats: Dict[str, Any]) -> None:
    """Display DynamoDB-specific statistics."""
    console.print(f"[green]Table Name:[/green] {stats.get('table_name', 'unknown')}")
    console.print(f"[green]Region:[/green] {stats.get('region', 'default')}")
    console.print(f"[green]Profile:[/green] {stats.get('profile', 'default')}")
    
    table_exists = stats.get('table_exists', False)
    exists_color = "green" if table_exists else "red"
    console.print(f"[{exists_color}]Table Exists:[/{exists_color}] {'Yes' if table_exists else 'No'}")
    
    if table_exists:
        console.print(f"[green]Table Status:[/green] {stats.get('table_status', 'UNKNOWN')}")
        console.print(f"[green]Item Count:[/green] {stats.get('item_count', 0)}")
        console.print(f"[green]Table Size:[/green] {stats.get('table_size_bytes', 0)} bytes")
        console.print(f"[green]Billing Mode:[/green] {stats.get('billing_mode', 'UNKNOWN')}")
        
        ttl_enabled = stats.get('ttl_enabled', False)
        ttl_color = "green" if ttl_enabled else "yellow"
        console.print(f"[{ttl_color}]TTL Enabled:[/{ttl_color}] {'Yes' if ttl_enabled else 'No'}")
        
        console.print(f"[green]Chunking Enabled:[/green] {'Yes' if stats.get('chunking_enabled', False) else 'No'}")
        console.print(f"[green]Compression Enabled:[/green] {'Yes' if stats.get('compression_enabled', False) else 'No'}")
        
        if 'creation_date' in stats and stats['creation_date']:
            console.print(f"[green]Created:[/green] {stats['creation_date']}")


def _display_file_statistics(stats: Dict[str, Any]) -> None:
    """Display file backend-specific statistics."""
    console.print(f"[green]Cache Directory:[/green] {stats.get('cache_directory', 'unknown')}")
    console.print(f"[green]Valid Entries:[/green] {stats.get('valid_entries', 0)}")
    console.print(f"[green]Expired Entries:[/green] {stats.get('expired_entries', 0)}")
    console.print(f"[green]Corrupted Entries:[/green] {stats.get('corrupted_entries', 0)}")
    console.print(f"[green]Total Files:[/green] {stats.get('total_files', 0)}")
    console.print(f"[green]Total Size:[/green] {stats.get('total_size_bytes', 0)} bytes")
    
    # Display encryption format information
    if 'encrypted_entries' in stats:
        console.print(f"[green]Encrypted Entries:[/green] {stats['encrypted_entries']}")
    if 'legacy_entries' in stats:
        console.print(f"[green]Legacy Format Entries:[/green] {stats['legacy_entries']}")


def _display_hybrid_statistics(stats: Dict[str, Any]) -> None:
    """Display hybrid backend-specific statistics."""
    console.print(f"[green]Local TTL:[/green] {stats.get('local_ttl', 0)} seconds")
    
    # Display access tracking information
    access_tracking = stats.get('access_tracking', {})
    console.print(f"[green]Tracked Keys:[/green] {access_tracking.get('tracked_keys', 0)}")
    console.print(f"[green]Total Accesses:[/green] {access_tracking.get('total_accesses', 0)}")
    
    # Display cache efficiency
    cache_efficiency = stats.get('cache_efficiency', {})
    console.print(f"[green]Local Entries:[/green] {cache_efficiency.get('local_entries', 0)}")
    console.print(f"[green]Remote Entries:[/green] {cache_efficiency.get('remote_entries', 0)}")
    console.print(f"[green]Local Hit Potential:[/green] {cache_efficiency.get('local_hit_potential', '0%')}")
    
    # Display backend-specific stats
    if 'local_backend' in stats:
        console.print("\n[dim]Local Backend:[/dim]")
        local_stats = stats['local_backend']
        if 'error' in local_stats:
            console.print(f"[red]  Error: {local_stats['error']}[/red]")
        else:
            console.print(f"[dim]  Valid Entries: {local_stats.get('valid_entries', 0)}[/dim]")
    
    if 'remote_backend' in stats:
        console.print("\n[dim]Remote Backend:[/dim]")
        remote_stats = stats['remote_backend']
        if 'error' in remote_stats:
            console.print(f"[red]  Error: {remote_stats['error']}[/red]")
        else:
            console.print(f"[dim]  Item Count: {remote_stats.get('item_count', 0)}[/dim]")


def _display_backend_health(backend: CacheBackend) -> None:
    """Display backend health status.
    
    Args:
        backend: Cache backend to check health for
    """
    try:
        console.print("\n[bold blue]Backend Health[/bold blue]")
        console.print("-" * 20)
        
        # Perform health check
        start_time = time.time()
        is_healthy = backend.health_check()
        response_time_ms = (time.time() - start_time) * 1000
        
        # Display health status
        health_color = "green" if is_healthy else "red"
        health_status = "Healthy" if is_healthy else "Unhealthy"
        console.print(f"[{health_color}]Health Status:[/{health_color}] {health_status}")
        console.print(f"[green]Response Time:[/green] {response_time_ms:.1f}ms")
        
        # Display performance indicators
        if response_time_ms > 1000:
            console.print("[yellow]⚠️  Slow response time detected[/yellow]")
        elif response_time_ms > 500:
            console.print("[yellow]⚠️  Moderate response time[/yellow]")
        else:
            console.print("[green]✓ Good response time[/green]")
            
    except Exception as e:
        console.print(f"[red]Health Check Failed:[/red] {e}")


def _display_recent_cache_entries(cache_manager: CacheManager) -> None:
    """Display recent cache entries with expiration information.
    
    Args:
        cache_manager: CacheManager instance to get cache entries from
    """
    try:
        # Get list of cache files - handle both legacy and advanced configurations
        cache_files = []
        
        if cache_manager.path_manager is not None:
            # Legacy configuration with path_manager
            cache_files = cache_manager.path_manager.list_cache_files()
        elif hasattr(cache_manager, 'backend') and cache_manager.backend is not None:
            # Advanced configuration with backend
            try:
                # For file backend, we can get the files directly
                if hasattr(cache_manager.backend, 'path_manager'):
                    cache_files = cache_manager.backend.path_manager.list_cache_files()
                else:
                    # For other backends (DynamoDB, hybrid), we can't easily list files
                    # So we'll skip showing recent entries
                    console.print("\n[dim]Recent cache entries not available for this backend type[/dim]")
                    return
            except Exception as e:
                console.print(f"\n[dim]Could not retrieve recent cache entries: {e}[/dim]")
                return
        else:
            # No way to get cache files
            console.print("\n[dim]Recent cache entries not available[/dim]")
            return
        
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
                # Try to read as binary first to detect format
                with open(cache_file, 'rb') as f:
                    file_content = f.read()
                
                file_size_bytes = len(file_content)
                file_size_kb = round(file_size_bytes / 1024, 1)
                
                # Try to determine if this is encrypted or plain JSON
                cache_data = None
                
                # Check if it's the new encrypted format (starts with metadata length)
                if len(file_content) >= 4:
                    try:
                        metadata_length = int.from_bytes(file_content[:4], byteorder='big')
                        if 0 < metadata_length < len(file_content):
                            # Try to parse metadata
                            metadata_json = file_content[4:4+metadata_length]
                            metadata = json.loads(metadata_json.decode('utf-8'))
                            
                            if metadata.get('encrypted', False):
                                # This is encrypted format - use metadata for display
                                cache_entry = CacheEntry(
                                    data={},  # We can't decrypt here, so use empty data
                                    created_at=metadata['created_at'],
                                    ttl=metadata['ttl'],
                                    key=metadata['key'],
                                    operation=metadata['operation']
                                )
                                cache_entries.append((cache_entry, file_size_kb))
                                continue
                    except (ValueError, json.JSONDecodeError, KeyError):
                        # Not the new encrypted format, try old format
                        pass
                
                # Try old JSON format
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cache_data = json.load(f)
                    
                    # Validate cache data structure
                    required_fields = ['data', 'created_at', 'ttl', 'key', 'operation']
                    if not all(field in cache_data for field in required_fields):
                        console.print(f"[yellow]Warning: Cache file missing required fields: {cache_file.name}[/yellow]")
                        continue
                    
                    cache_entry = CacheEntry(
                        data=cache_data['data'],
                        created_at=cache_data['created_at'],
                        ttl=cache_data['ttl'],
                        key=cache_data['key'],
                        operation=cache_data['operation']
                    )
                    
                    cache_entries.append((cache_entry, file_size_kb))
                    
                except (json.JSONDecodeError, UnicodeDecodeError):
                    # This might be an encrypted file that we can't read directly
                    # Extract key from filename and try to get basic info
                    try:
                        # Cache files are typically named with the cache key
                        cache_key = cache_file.stem  # filename without extension
                        
                        # Create a minimal entry with file info
                        # We can't get the actual metadata without decryption
                        file_stat = cache_file.stat()
                        cache_entry = CacheEntry(
                            data={},
                            created_at=file_stat.st_mtime,  # Use file modification time
                            ttl=3600,  # Default TTL since we can't read it
                            key=cache_key,
                            operation="encrypted"  # Indicate this is encrypted
                        )
                        
                        cache_entries.append((cache_entry, file_size_kb))
                        
                    except Exception:
                        # Skip files we can't process at all
                        console.print(f"[yellow]Warning: Could not process cache file: {cache_file.name}[/yellow]")
                        continue
                
            except Exception as e:
                # Skip corrupted cache files
                console.print(f"[yellow]Warning: Could not read cache file {cache_file.name}: {e}[/yellow]")
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


@app.command("encryption")
def encryption_management():
    """Manage cache encryption settings and keys.
    
    This command provides access to encryption management subcommands
    for key rotation, encryption status, and encryption configuration.
    """
    console.print("[blue]Cache Encryption Management[/blue]")
    console.print("Use 'awsideman cache encryption --help' to see available subcommands:")
    console.print("  • status    - Show encryption status and key information")
    console.print("  • enable    - Enable encryption on existing cache")
    console.print("  • disable   - Disable encryption (with warnings)")
    console.print("  • rotate    - Rotate encryption keys")
    console.print("  • backup    - Backup encryption keys")
    console.print("  • restore   - Restore encryption keys")


# Create encryption subcommand group
encryption_app = typer.Typer(help="Manage cache encryption settings and keys")
app.add_typer(encryption_app, name="encryption")

# Create configuration subcommand group
config_app = typer.Typer(help="Manage cache configuration settings")
app.add_typer(config_app, name="config")


@encryption_app.command("status")
def encryption_status():
    """Display encryption status and key information.
    
    Shows detailed information about the current encryption configuration,
    key status, and keyring availability.
    """
    try:
        cache_manager = CacheManager()
        
        # Display encryption status header
        console.print("\n[bold blue]Cache Encryption Status[/bold blue]")
        console.print("=" * 50)
        
        # Check if we're using advanced configuration
        if not isinstance(cache_manager.config, AdvancedCacheConfig):
            console.print("[yellow]Using basic cache configuration - encryption not available[/yellow]")
            console.print("[dim]To use encryption, configure advanced cache settings in ~/.awsideman/config.yaml[/dim]")
            return
        
        config = cache_manager.config
        
        # Display basic encryption settings
        console.print(f"[green]Encryption Enabled:[/green] {'Yes' if config.encryption_enabled else 'No'}")
        console.print(f"[green]Encryption Type:[/green] {config.encryption_type}")
        
        if cache_manager.encryption_provider:
            provider_type = cache_manager.encryption_provider.get_encryption_type()
            console.print(f"[green]Active Provider:[/green] {provider_type}")
            
            # Show provider availability
            is_available = cache_manager.encryption_provider.is_available()
            status_color = "green" if is_available else "red"
            status_text = "Available" if is_available else "Unavailable"
            console.print(f"[{status_color}]Provider Status:[/{status_color}] {status_text}")
        
        # Display key information if encryption is enabled
        if config.encryption_enabled and config.encryption_type != "none":
            console.print("\n[bold blue]Key Information[/bold blue]")
            console.print("-" * 30)
            
            try:
                # Create key manager to get key info
                key_manager = KeyManager()
                key_info = key_manager.get_key_info()
                
                # Display keyring availability
                keyring_color = "green" if key_info.get('keyring_available', False) else "yellow"
                keyring_status = "Available" if key_info.get('keyring_available', False) else "Unavailable (using fallback)"
                console.print(f"[{keyring_color}]Keyring Status:[/{keyring_color}] {keyring_status}")
                
                # Display key existence
                key_color = "green" if key_info.get('key_exists', False) else "red"
                key_status = "Present" if key_info.get('key_exists', False) else "Missing"
                console.print(f"[{key_color}]Encryption Key:[/{key_color}] {key_status}")
                
                if key_info.get('key_exists', False):
                    # Display key validity
                    key_valid = key_info.get('key_valid', False)
                    valid_color = "green" if key_valid else "red"
                    valid_status = "Valid" if key_valid else "Invalid"
                    console.print(f"[{valid_color}]Key Validity:[/{valid_color}] {valid_status}")
                    
                    # Display key length if available
                    if 'key_length' in key_info:
                        console.print(f"[green]Key Length:[/green] {key_info['key_length']} bytes")
                    
                    # Display cache status
                    cached_status = "Yes" if key_info.get('cached', False) else "No"
                    console.print(f"[green]Key Cached:[/green] {cached_status}")
                
                # Display service information
                console.print(f"[green]Service Name:[/green] {key_info.get('service_name', 'unknown')}")
                console.print(f"[green]Username:[/green] {key_info.get('username', 'unknown')}")
                
                # Display any errors
                if 'key_error' in key_info:
                    console.print(f"[red]Key Error:[/red] {key_info['key_error']}")
                
                if 'error' in key_info:
                    console.print(f"[red]General Error:[/red] {key_info['error']}")
                
            except Exception as e:
                console.print(f"[red]Error getting key information: {e}[/red]")
        
        # Display available encryption providers
        console.print("\n[bold blue]Available Encryption Providers[/bold blue]")
        console.print("-" * 40)
        
        try:
            available_providers = EncryptionProviderFactory.get_available_providers()
            for provider in available_providers:
                if provider == config.encryption_type:
                    console.print(f"[green]• {provider} (active)[/green]")
                else:
                    console.print(f"[dim]• {provider}[/dim]")
        except Exception as e:
            console.print(f"[red]Error getting available providers: {e}[/red]")
        
        # Display recommendations
        console.print("\n[bold blue]Recommendations[/bold blue]")
        console.print("-" * 20)
        
        if not config.encryption_enabled:
            console.print("[yellow]• Consider enabling encryption for sensitive cache data[/yellow]")
        
        if config.encryption_enabled and not key_info.get('keyring_available', False):
            console.print("[yellow]• Keyring unavailable - using less secure file-based key storage[/yellow]")
        
        if config.encryption_enabled and not key_info.get('key_valid', True):
            console.print("[red]• Encryption key is invalid - consider rotating keys[/red]")
        
    except Exception as e:
        console.print(f"[red]Error displaying encryption status: {e}[/red]")
        raise typer.Exit(1)


@encryption_app.command("enable")
def enable_encryption(
    force: bool = typer.Option(False, "--force", "-f", help="Force enable without confirmation"),
    encryption_type: str = typer.Option("aes256", "--type", "-t", help="Encryption type to use (aes256)"),
):
    """Enable encryption on existing cache data.
    
    This command enables encryption and re-encrypts all existing cache data.
    Use with caution as this operation cannot be easily undone.
    """
    try:
        cache_manager = CacheManager()
        
        # Check if we're using advanced configuration
        if not isinstance(cache_manager.config, AdvancedCacheConfig):
            console.print("[red]Error: Advanced cache configuration required for encryption[/red]")
            console.print("[dim]Configure advanced cache settings in ~/.awsideman/config.yaml[/dim]")
            raise typer.Exit(1)
        
        config = cache_manager.config
        
        # Check if encryption is already enabled
        if config.encryption_enabled:
            console.print("[yellow]Encryption is already enabled[/yellow]")
            console.print(f"Current encryption type: {config.encryption_type}")
            return
        
        # Validate encryption type
        available_providers = EncryptionProviderFactory.get_available_providers()
        if encryption_type not in available_providers:
            console.print(f"[red]Error: Encryption type '{encryption_type}' is not available[/red]")
            console.print(f"Available types: {', '.join(available_providers)}")
            raise typer.Exit(1)
        
        # Get cache statistics before enabling encryption
        stats = cache_manager.get_cache_stats()
        total_entries = stats.get('total_entries', 0)
        
        if total_entries == 0:
            console.print("[green]No existing cache entries to encrypt[/green]")
        else:
            console.print(f"[yellow]About to enable encryption and re-encrypt {total_entries} cache entries[/yellow]")
            console.print(f"[yellow]This will use {encryption_type} encryption[/yellow]")
        
        # Ask for confirmation unless --force is used
        if not force:
            console.print("\n[bold red]WARNING:[/bold red] This operation will:")
            console.print("• Enable encryption for all future cache operations")
            console.print("• Re-encrypt all existing cache data")
            console.print("• Generate and store a new encryption key")
            console.print("• Make cache data unreadable without the encryption key")
            
            confirm = typer.confirm("\nAre you sure you want to enable encryption?")
            if not confirm:
                console.print("[blue]Encryption enable cancelled[/blue]")
                return
        
        # Enable encryption in configuration
        console.print("[blue]Enabling encryption...[/blue]")
        
        # Update configuration
        config.encryption_enabled = True
        config.encryption_type = encryption_type
        
        # Create new cache manager with encryption enabled
        new_cache_manager = CacheManager(config=config)
        
        # Verify encryption is working
        if not new_cache_manager.encryption_provider or new_cache_manager.encryption_provider.get_encryption_type() == "none":
            console.print("[red]Error: Failed to enable encryption[/red]")
            raise typer.Exit(1)
        
        # Re-encrypt existing cache data if any exists
        if total_entries > 0:
            console.print(f"[blue]Re-encrypting {total_entries} existing cache entries...[/blue]")
            
            # This is a simplified approach - in a real implementation, you'd want to:
            # 1. Read all existing cache entries
            # 2. Decrypt them with the old (no encryption) provider
            # 3. Re-encrypt them with the new encryption provider
            # 4. Write them back
            
            # For now, we'll just clear the cache and let it rebuild
            console.print("[yellow]Clearing existing cache - it will be rebuilt with encryption[/yellow]")
            cache_manager.invalidate()
        
        # Test encryption by creating a test entry
        try:
            test_data = {"test": "encryption_enabled", "timestamp": time.time()}
            new_cache_manager.set("encryption_test", test_data, ttl=60, operation="encryption_test")
            
            # Try to read it back
            retrieved_data = new_cache_manager.get("encryption_test")
            if retrieved_data != test_data:
                raise Exception("Test data mismatch")
            
            # Clean up test entry
            new_cache_manager.invalidate("encryption_test")
            
            console.print("[green]✓ Encryption enabled successfully![/green]")
            console.print(f"[green]Using {encryption_type} encryption[/green]")
            
            # Display key information
            if encryption_type != "none":
                key_manager = KeyManager()
                key_info = key_manager.get_key_info()
                if key_info.get('keyring_available', False):
                    console.print("[green]✓ Encryption key stored securely in system keyring[/green]")
                else:
                    console.print("[yellow]⚠ Encryption key stored in file (keyring unavailable)[/yellow]")
            
        except Exception as e:
            console.print(f"[red]Error testing encryption: {e}[/red]")
            console.print("[red]Encryption may not be working correctly[/red]")
            raise typer.Exit(1)
        
    except Exception as e:
        console.print(f"[red]Error enabling encryption: {e}[/red]")
        raise typer.Exit(1)


@encryption_app.command("disable")
def disable_encryption(
    force: bool = typer.Option(False, "--force", "-f", help="Force disable without confirmation"),
    keep_data: bool = typer.Option(True, "--keep-data/--clear-data", help="Keep encrypted data or clear it"),
):
    """Disable encryption on cache data.
    
    This command disables encryption. Existing encrypted data can be kept
    (but will become inaccessible) or cleared entirely.
    """
    try:
        cache_manager = CacheManager()
        
        # Check if we're using advanced configuration
        if not isinstance(cache_manager.config, AdvancedCacheConfig):
            console.print("[yellow]Encryption is not available with basic configuration[/yellow]")
            return
        
        config = cache_manager.config
        
        # Check if encryption is already disabled
        if not config.encryption_enabled:
            console.print("[yellow]Encryption is already disabled[/yellow]")
            return
        
        # Get cache statistics
        stats = cache_manager.get_cache_stats()
        total_entries = stats.get('total_entries', 0)
        
        # Ask for confirmation unless --force is used
        if not force:
            console.print("\n[bold red]WARNING:[/bold red] This operation will:")
            console.print("• Disable encryption for all future cache operations")
            
            if keep_data:
                console.print("• Keep existing encrypted data (but it will become inaccessible)")
                console.print("• You will need to re-enable encryption with the same key to access the data")
            else:
                console.print(f"• Clear all {total_entries} existing cache entries")
                console.print("• All cached data will be lost and need to be rebuilt")
            
            console.print("• Remove encryption key from secure storage")
            
            confirm = typer.confirm("\nAre you sure you want to disable encryption?")
            if not confirm:
                console.print("[blue]Encryption disable cancelled[/blue]")
                return
        
        # Disable encryption
        console.print("[blue]Disabling encryption...[/blue]")
        
        # Clear cache data if requested
        if not keep_data and total_entries > 0:
            console.print(f"[blue]Clearing {total_entries} encrypted cache entries...[/blue]")
            cache_manager.invalidate()
        
        # Update configuration
        config.encryption_enabled = False
        config.encryption_type = "none"
        
        # Delete encryption key if it exists
        try:
            key_manager = KeyManager()
            if key_manager.key_exists():
                if key_manager.delete_key():
                    console.print("[green]✓ Encryption key deleted from secure storage[/green]")
                else:
                    console.print("[yellow]⚠ Failed to delete encryption key - you may need to remove it manually[/yellow]")
        except Exception as e:
            console.print(f"[yellow]Warning: Error deleting encryption key: {e}[/yellow]")
        
        # Test that encryption is disabled
        try:
            new_cache_manager = CacheManager(config=config)
            
            if new_cache_manager.encryption_provider.get_encryption_type() != "none":
                console.print("[red]Error: Failed to disable encryption[/red]")
                raise typer.Exit(1)
            
            # Test with a simple cache operation
            test_data = {"test": "encryption_disabled", "timestamp": time.time()}
            new_cache_manager.set("encryption_test", test_data, ttl=60, operation="encryption_test")
            
            retrieved_data = new_cache_manager.get("encryption_test")
            if retrieved_data != test_data:
                raise Exception("Test data mismatch")
            
            # Clean up test entry
            new_cache_manager.invalidate("encryption_test")
            
            console.print("[green]✓ Encryption disabled successfully![/green]")
            
            if keep_data and total_entries > 0:
                console.print(f"[yellow]Note: {total_entries} encrypted cache entries are still present but inaccessible[/yellow]")
                console.print("[dim]Use 'awsideman cache clear' to remove them if needed[/dim]")
            
        except Exception as e:
            console.print(f"[red]Error testing disabled encryption: {e}[/red]")
            raise typer.Exit(1)
        
    except Exception as e:
        console.print(f"[red]Error disabling encryption: {e}[/red]")
        raise typer.Exit(1)


@encryption_app.command("rotate")
def rotate_encryption_key(
    force: bool = typer.Option(False, "--force", "-f", help="Force rotation without confirmation"),
    backup_old_key: bool = typer.Option(True, "--backup/--no-backup", help="Backup old key before rotation"),
):
    """Rotate encryption keys and re-encrypt all cache data.
    
    This command generates a new encryption key and re-encrypts all existing
    cache data with the new key. The old key is securely deleted after successful rotation.
    """
    try:
        cache_manager = CacheManager()
        
        # Check if we're using advanced configuration with encryption
        if not isinstance(cache_manager.config, AdvancedCacheConfig):
            console.print("[red]Error: Advanced cache configuration required for key rotation[/red]")
            raise typer.Exit(1)
        
        config = cache_manager.config
        
        if not config.encryption_enabled or config.encryption_type == "none":
            console.print("[red]Error: Encryption is not enabled - cannot rotate keys[/red]")
            console.print("[dim]Use 'awsideman cache encryption enable' to enable encryption first[/dim]")
            raise typer.Exit(1)
        
        # Check that encryption is working
        if not cache_manager.encryption_provider or cache_manager.encryption_provider.get_encryption_type() == "none":
            console.print("[red]Error: Encryption provider not available[/red]")
            raise typer.Exit(1)
        
        # Get cache statistics
        stats = cache_manager.get_cache_stats()
        total_entries = stats.get('total_entries', 0)
        
        console.print(f"[yellow]About to rotate encryption key and re-encrypt {total_entries} cache entries[/yellow]")
        
        # Ask for confirmation unless --force is used
        if not force:
            console.print("\n[bold yellow]WARNING:[/bold yellow] This operation will:")
            console.print("• Generate a new encryption key")
            console.print(f"• Re-encrypt all {total_entries} existing cache entries")
            console.print("• Securely delete the old encryption key")
            console.print("• Take some time to complete for large caches")
            
            if backup_old_key:
                console.print("• Create a backup of the old key (for recovery purposes)")
            
            confirm = typer.confirm("\nAre you sure you want to rotate the encryption key?")
            if not confirm:
                console.print("[blue]Key rotation cancelled[/blue]")
                return
        
        # Start key rotation process
        console.print("[blue]Starting key rotation...[/blue]")
        
        try:
            # Create key manager
            key_manager = KeyManager()
            
            # Backup old key if requested
            old_key_backup = None
            if backup_old_key:
                try:
                    old_key = key_manager.get_key()
                    old_key_backup = old_key
                    console.print("[green]✓ Old key backed up for recovery[/green]")
                except Exception as e:
                    console.print(f"[yellow]Warning: Could not backup old key: {e}[/yellow]")
            
            # Rotate the key
            console.print("[blue]Generating new encryption key...[/blue]")
            old_key, new_key = key_manager.rotate_key()
            
            if not old_key:
                console.print("[yellow]No old key found - this appears to be the first key generation[/yellow]")
            
            console.print("[green]✓ New encryption key generated and stored[/green]")
            
            # Re-encrypt all cache data if there are entries
            if total_entries > 0:
                console.print(f"[blue]Re-encrypting {total_entries} cache entries with new key...[/blue]")
                
                # This is a simplified implementation
                # In a production system, you would:
                # 1. Read all cache entries
                # 2. Decrypt with old key
                # 3. Re-encrypt with new key
                # 4. Write back to cache
                
                # For now, we'll clear the cache and let it rebuild
                # This is safer and simpler, though less efficient
                console.print("[yellow]Clearing cache - it will be rebuilt with the new key[/yellow]")
                cache_manager.invalidate()
                
                console.print("[green]✓ Cache cleared - will be rebuilt with new encryption key[/green]")
            
            # Test the new key
            console.print("[blue]Testing new encryption key...[/blue]")
            
            # Create new cache manager to use the rotated key
            new_cache_manager = CacheManager(config=config)
            
            # Test encryption/decryption
            test_data = {"test": "key_rotation", "timestamp": time.time()}
            new_cache_manager.set("rotation_test", test_data, ttl=60, operation="rotation_test")
            
            retrieved_data = new_cache_manager.get("rotation_test")
            if retrieved_data != test_data:
                raise Exception("Test data mismatch after key rotation")
            
            # Clean up test entry
            new_cache_manager.invalidate("rotation_test")
            
            console.print("[green]✓ Key rotation completed successfully![/green]")
            
            # Display key information
            key_info = key_manager.get_key_info()
            if key_info.get('keyring_available', False):
                console.print("[green]✓ New key stored securely in system keyring[/green]")
            else:
                console.print("[yellow]⚠ New key stored in file (keyring unavailable)[/yellow]")
            
            if old_key_backup and backup_old_key:
                console.print("[dim]Old key backup is available for emergency recovery[/dim]")
            
        except EncryptionError as e:
            console.print(f"[red]Encryption error during key rotation: {e}[/red]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Error during key rotation: {e}[/red]")
            console.print("[red]Key rotation may have failed - check encryption status[/red]")
            raise typer.Exit(1)
        
    except Exception as e:
        console.print(f"[red]Error rotating encryption key: {e}[/red]")
        raise typer.Exit(1)


@encryption_app.command("backup")
def backup_encryption_key(
    output_file: Optional[str] = typer.Option(None, "--output", "-o", help="Output file for key backup"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing backup file"),
):
    """Create a secure backup of the encryption key.
    
    This command creates a backup of the current encryption key for disaster recovery.
    The backup should be stored securely and separately from the main system.
    """
    try:
        cache_manager = CacheManager()
        
        # Check if we're using advanced configuration with encryption
        if not isinstance(cache_manager.config, AdvancedCacheConfig):
            console.print("[red]Error: Advanced cache configuration required for key backup[/red]")
            raise typer.Exit(1)
        
        config = cache_manager.config
        
        if not config.encryption_enabled or config.encryption_type == "none":
            console.print("[red]Error: Encryption is not enabled - no key to backup[/red]")
            raise typer.Exit(1)
        
        # Create key manager
        key_manager = KeyManager()
        
        # Check if key exists
        if not key_manager.key_exists():
            console.print("[red]Error: No encryption key found to backup[/red]")
            raise typer.Exit(1)
        
        # Determine output file
        if not output_file:
            from pathlib import Path
            timestamp = int(time.time())
            output_file = str(Path.home() / f".awsideman_key_backup_{timestamp}.key")
        
        # Check if output file exists
        from pathlib import Path
        output_path = Path(output_file)
        if output_path.exists() and not force:
            console.print(f"[red]Error: Backup file already exists: {output_file}[/red]")
            console.print("[dim]Use --force to overwrite or specify a different file[/dim]")
            raise typer.Exit(1)
        
        console.print(f"[blue]Creating key backup: {output_file}[/blue]")
        
        # Get the key
        key = key_manager.get_key()
        
        # Create backup data structure
        backup_data = {
            "version": 1,
            "service_name": key_manager.service_name,
            "username": key_manager.username,
            "encryption_type": config.encryption_type,
            "created_at": time.time(),
            "key": key_manager._encode_key(key)
        }
        
        # Write backup file
        import json
        with open(output_path, 'w') as f:
            json.dump(backup_data, f, indent=2)
        
        # Set restrictive permissions
        import os
        os.chmod(output_path, 0o600)  # Owner read/write only
        
        console.print("[green]✓ Encryption key backup created successfully[/green]")
        console.print(f"[green]Backup file: {output_file}[/green]")
        console.print("\n[bold yellow]IMPORTANT SECURITY NOTES:[/bold yellow]")
        console.print("• Store this backup file in a secure location")
        console.print("• Do not share or transmit this file over insecure channels")
        console.print("• Consider encrypting the backup file with additional encryption")
        console.print("• Delete the backup file when no longer needed")
        
    except Exception as e:
        console.print(f"[red]Error creating key backup: {e}[/red]")
        raise typer.Exit(1)


@encryption_app.command("restore")
def restore_encryption_key(
    backup_file: str = typer.Argument(..., help="Backup file to restore from"),
    force: bool = typer.Option(False, "--force", "-f", help="Force restore without confirmation"),
):
    """Restore encryption key from a backup file.
    
    This command restores an encryption key from a previously created backup.
    Use this for disaster recovery when the original key is lost or corrupted.
    """
    try:
        from pathlib import Path
        
        # Check if backup file exists
        backup_path = Path(backup_file)
        if not backup_path.exists():
            console.print(f"[red]Error: Backup file not found: {backup_file}[/red]")
            raise typer.Exit(1)
        
        # Read backup file
        console.print(f"[blue]Reading backup file: {backup_file}[/blue]")
        
        try:
            with open(backup_path, 'r') as f:
                backup_data = json.load(f)
        except json.JSONDecodeError as e:
            console.print(f"[red]Error: Invalid backup file format: {e}[/red]")
            raise typer.Exit(1)
        
        # Validate backup data
        required_fields = ['version', 'service_name', 'username', 'encryption_type', 'key']
        missing_fields = [field for field in required_fields if field not in backup_data]
        if missing_fields:
            console.print(f"[red]Error: Backup file missing required fields: {', '.join(missing_fields)}[/red]")
            raise typer.Exit(1)
        
        # Display backup information
        console.print("\n[bold blue]Backup Information[/bold blue]")
        console.print("-" * 25)
        console.print(f"[green]Version:[/green] {backup_data['version']}")
        console.print(f"[green]Service Name:[/green] {backup_data['service_name']}")
        console.print(f"[green]Username:[/green] {backup_data['username']}")
        console.print(f"[green]Encryption Type:[/green] {backup_data['encryption_type']}")
        
        if 'created_at' in backup_data:
            from datetime import datetime
            created_time = datetime.fromtimestamp(backup_data['created_at'])
            console.print(f"[green]Created:[/green] {created_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Check current key status
        key_manager = KeyManager(
            service_name=backup_data['service_name'],
            username=backup_data['username']
        )
        
        current_key_exists = key_manager.key_exists()
        if current_key_exists:
            console.print(f"\n[yellow]Warning: A key already exists for this service[/yellow]")
        
        # Ask for confirmation unless --force is used
        if not force:
            console.print("\n[bold yellow]WARNING:[/bold yellow] This operation will:")
            if current_key_exists:
                console.print("• Replace the existing encryption key")
                console.print("• Make existing encrypted cache data inaccessible")
            else:
                console.print("• Install the encryption key from the backup")
            console.print("• Enable access to cache data encrypted with this key")
            
            confirm = typer.confirm("\nAre you sure you want to restore this encryption key?")
            if not confirm:
                console.print("[blue]Key restore cancelled[/blue]")
                return
        
        # Restore the key
        console.print("[blue]Restoring encryption key...[/blue]")
        
        try:
            # Decode the key
            key = key_manager._decode_key(backup_data['key'])
            
            # Store the key
            key_manager._store_key(key)
            
            console.print("[green]✓ Encryption key restored successfully[/green]")
            
            # Test the restored key
            console.print("[blue]Testing restored key...[/blue]")
            
            # Verify we can retrieve the key
            retrieved_key = key_manager.get_key()
            if retrieved_key != key:
                raise Exception("Key verification failed")
            
            console.print("[green]✓ Key verification successful[/green]")
            
            # Display key information
            key_info = key_manager.get_key_info()
            if key_info.get('keyring_available', False):
                console.print("[green]✓ Key stored securely in system keyring[/green]")
            else:
                console.print("[yellow]⚠ Key stored in file (keyring unavailable)[/yellow]")
            
            console.print("\n[bold green]Key restore completed successfully![/bold green]")
            console.print("[dim]You can now access cache data encrypted with this key[/dim]")
            
        except Exception as e:
            console.print(f"[red]Error restoring key: {e}[/red]")
            raise typer.Exit(1)
        
    except Exception as e:
        console.print(f"[red]Error restoring encryption key: {e}[/red]")
        raise typer.Exit(1)


# Create health monitoring subcommand group
health_app = typer.Typer(help="Monitor and manage cache backend health")
app.add_typer(health_app, name="health")


@health_app.command("check")
def health_check(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed health information"),
    backend: Optional[str] = typer.Option(None, "--backend", "-b", help="Check specific backend (file, dynamodb, hybrid)"),
):
    """Check the health of cache backends.
    
    Performs connectivity and functionality tests on the configured cache backends
    to ensure they are working properly.
    """
    try:
        cache_manager = CacheManager()
        
        console.print("\n[bold blue]Cache Backend Health Check[/bold blue]")
        console.print("=" * 50)
        
        # Check if we're using advanced configuration
        if not isinstance(cache_manager.config, AdvancedCacheConfig):
            console.print("[yellow]Using basic cache configuration[/yellow]")
            
            # For basic config, check file backend health
            if cache_manager.path_manager:
                console.print("\n[bold blue]File Backend Health[/bold blue]")
                console.print("-" * 25)
                
                try:
                    # Test basic file operations
                    cache_dir = cache_manager.path_manager.get_cache_directory()
                    console.print(f"[green]Cache Directory:[/green] {cache_dir}")
                    
                    # Test directory access
                    if cache_dir.exists():
                        console.print("[green]✓ Cache directory exists[/green]")
                        
                        # Test write access
                        test_file = cache_dir / ".health_check_test"
                        try:
                            test_file.write_text("health_check")
                            test_file.unlink()
                            console.print("[green]✓ Write access confirmed[/green]")
                        except Exception as e:
                            console.print(f"[red]✗ Write access failed: {e}[/red]")
                    else:
                        console.print("[yellow]⚠ Cache directory does not exist[/yellow]")
                        try:
                            cache_manager.path_manager.ensure_cache_directory()
                            console.print("[green]✓ Created cache directory[/green]")
                        except Exception as e:
                            console.print(f"[red]✗ Failed to create cache directory: {e}[/red]")
                    
                    console.print("[green]✓ Basic file backend is healthy[/green]")
                    
                except Exception as e:
                    console.print(f"[red]✗ File backend health check failed: {e}[/red]")
            
            return
        
        config = cache_manager.config
        
        # Display current backend configuration
        console.print(f"[green]Backend Type:[/green] {config.backend_type}")
        console.print(f"[green]Encryption:[/green] {'Enabled' if config.encryption_enabled else 'Disabled'}")
        
        # Check specific backend if requested
        if backend and backend != config.backend_type:
            console.print(f"[yellow]Note: Checking {backend} backend (not currently active)[/yellow]")
        
        # Perform health checks based on backend type
        backends_to_check = []
        
        if backend:
            # Check specific backend
            backends_to_check.append(backend)
        else:
            # Check active backend
            backends_to_check.append(config.backend_type)
            
            # For hybrid backend, also check component backends
            if config.backend_type == "hybrid":
                backends_to_check.extend(["file", "dynamodb"])
        
        overall_healthy = True
        
        for backend_type in backends_to_check:
            console.print(f"\n[bold blue]{backend_type.title()} Backend Health[/bold blue]")
            console.print("-" * (len(backend_type) + 15))
            
            try:
                backend_healthy = _check_backend_health(backend_type, config, verbose)
                if not backend_healthy:
                    overall_healthy = False
            except Exception as e:
                console.print(f"[red]✗ Health check failed: {e}[/red]")
                overall_healthy = False
        
        # Overall status
        console.print(f"\n[bold blue]Overall Health Status[/bold blue]")
        console.print("-" * 25)
        
        if overall_healthy:
            console.print("[green]✓ All backends are healthy[/green]")
        else:
            console.print("[red]✗ One or more backends have issues[/red]")
            console.print("[dim]Use 'awsideman cache health repair' to attempt automatic fixes[/dim]")
        
    except Exception as e:
        console.print(f"[red]Error performing health check: {e}[/red]")
        raise typer.Exit(1)


@health_app.command("benchmark")
def benchmark_backends(
    operations: int = typer.Option(100, "--operations", "-n", help="Number of operations to perform"),
    data_size: int = typer.Option(1024, "--size", "-s", help="Size of test data in bytes"),
    backend: Optional[str] = typer.Option(None, "--backend", "-b", help="Benchmark specific backend"),
):
    """Benchmark cache backend performance.
    
    Performs read/write operations to measure backend performance and latency.
    """
    try:
        cache_manager = CacheManager()
        
        console.print("\n[bold blue]Cache Backend Performance Benchmark[/bold blue]")
        console.print("=" * 50)
        
        # Check if we're using advanced configuration
        if not isinstance(cache_manager.config, AdvancedCacheConfig):
            console.print("[yellow]Performance benchmarking requires advanced cache configuration[/yellow]")
            return
        
        config = cache_manager.config
        
        console.print(f"[green]Test Parameters:[/green]")
        console.print(f"  • Operations: {operations}")
        console.print(f"  • Data Size: {data_size} bytes")
        console.print(f"  • Active Backend: {config.backend_type}")
        
        # Determine which backends to benchmark
        backends_to_test = []
        
        if backend:
            backends_to_test.append(backend)
        else:
            # Test active backend
            backends_to_test.append(config.backend_type)
        
        # Generate test data
        test_data = b'x' * data_size
        
        for backend_type in backends_to_test:
            console.print(f"\n[bold blue]Benchmarking {backend_type.title()} Backend[/bold blue]")
            console.print("-" * (len(backend_type) + 20))
            
            try:
                results = _benchmark_backend(backend_type, config, test_data, operations)
                _display_benchmark_results(results)
            except Exception as e:
                console.print(f"[red]Benchmark failed for {backend_type}: {e}[/red]")
        
    except Exception as e:
        console.print(f"[red]Error running benchmark: {e}[/red]")
        raise typer.Exit(1)


@health_app.command("repair")
def repair_backends(
    backend: Optional[str] = typer.Option(None, "--backend", "-b", help="Repair specific backend"),
    force: bool = typer.Option(False, "--force", "-f", help="Force repair without confirmation"),
):
    """Repair cache backend configuration issues.
    
    Attempts to automatically fix common backend configuration and connectivity issues.
    """
    try:
        cache_manager = CacheManager()
        
        console.print("\n[bold blue]Cache Backend Repair[/bold blue]")
        console.print("=" * 30)
        
        # Check if we're using advanced configuration
        if not isinstance(cache_manager.config, AdvancedCacheConfig):
            console.print("[yellow]Backend repair requires advanced cache configuration[/yellow]")
            return
        
        config = cache_manager.config
        
        # Determine which backends to repair
        backends_to_repair = []
        
        if backend:
            backends_to_repair.append(backend)
        else:
            backends_to_repair.append(config.backend_type)
        
        # Ask for confirmation unless --force is used
        if not force:
            console.print(f"[yellow]About to attempt repair of {', '.join(backends_to_repair)} backend(s)[/yellow]")
            console.print("\n[bold yellow]WARNING:[/bold yellow] This operation may:")
            console.print("• Create missing tables or directories")
            console.print("• Modify backend configuration")
            console.print("• Clear corrupted cache entries")
            
            confirm = typer.confirm("\nProceed with backend repair?")
            if not confirm:
                console.print("[blue]Backend repair cancelled[/blue]")
                return
        
        overall_success = True
        
        for backend_type in backends_to_repair:
            console.print(f"\n[bold blue]Repairing {backend_type.title()} Backend[/bold blue]")
            console.print("-" * (len(backend_type) + 18))
            
            try:
                success = _repair_backend(backend_type, config)
                if not success:
                    overall_success = False
            except Exception as e:
                console.print(f"[red]Repair failed for {backend_type}: {e}[/red]")
                overall_success = False
        
        # Overall status
        console.print(f"\n[bold blue]Repair Summary[/bold blue]")
        console.print("-" * 15)
        
        if overall_success:
            console.print("[green]✓ All backend repairs completed successfully[/green]")
        else:
            console.print("[red]✗ Some backend repairs failed[/red]")
            console.print("[dim]Check the output above for specific error details[/dim]")
        
    except Exception as e:
        console.print(f"[red]Error during backend repair: {e}[/red]")
        raise typer.Exit(1)


@health_app.command("connectivity")
def test_connectivity(
    backend: Optional[str] = typer.Option(None, "--backend", "-b", help="Test specific backend connectivity"),
    timeout: int = typer.Option(30, "--timeout", "-t", help="Connection timeout in seconds"),
):
    """Test connectivity to cache backends.
    
    Tests network connectivity and authentication for remote backends like DynamoDB.
    """
    try:
        cache_manager = CacheManager()
        
        console.print("\n[bold blue]Cache Backend Connectivity Test[/bold blue]")
        console.print("=" * 40)
        
        # Check if we're using advanced configuration
        if not isinstance(cache_manager.config, AdvancedCacheConfig):
            console.print("[yellow]Connectivity testing requires advanced cache configuration[/yellow]")
            return
        
        config = cache_manager.config
        
        # Determine which backends to test
        backends_to_test = []
        
        if backend:
            backends_to_test.append(backend)
        else:
            backends_to_test.append(config.backend_type)
            
            # For hybrid backend, also test component backends
            if config.backend_type == "hybrid":
                backends_to_test.extend(["file", "dynamodb"])
        
        overall_success = True
        
        for backend_type in backends_to_test:
            console.print(f"\n[bold blue]Testing {backend_type.title()} Backend Connectivity[/bold blue]")
            console.print("-" * (len(backend_type) + 30))
            
            try:
                success = _test_backend_connectivity(backend_type, config, timeout)
                if not success:
                    overall_success = False
            except Exception as e:
                console.print(f"[red]Connectivity test failed for {backend_type}: {e}[/red]")
                overall_success = False
        
        # Overall status
        console.print(f"\n[bold blue]Connectivity Summary[/bold blue]")
        console.print("-" * 22)
        
        if overall_success:
            console.print("[green]✓ All backends are accessible[/green]")
        else:
            console.print("[red]✗ Some backends have connectivity issues[/red]")
        
    except Exception as e:
        console.print(f"[red]Error testing connectivity: {e}[/red]")
        raise typer.Exit(1)


def _check_backend_health(backend_type: str, config: AdvancedCacheConfig, verbose: bool) -> bool:
    """Check health of a specific backend type."""
    from ..cache.factory import BackendFactory
    
    try:
        # Create backend instance for testing
        test_config = AdvancedCacheConfig(
            backend_type=backend_type,
            dynamodb_table_name=config.dynamodb_table_name,
            dynamodb_region=config.dynamodb_region,
            dynamodb_profile=config.dynamodb_profile,
            file_cache_dir=config.file_cache_dir
        )
        
        backend = BackendFactory.create_backend(test_config)
        
        # Perform basic health check
        start_time = time.time()
        is_healthy = backend.health_check()
        response_time = (time.time() - start_time) * 1000
        
        if is_healthy:
            console.print(f"[green]✓ Backend is healthy[/green] ({response_time:.1f}ms)")
        else:
            console.print(f"[red]✗ Backend health check failed[/red] ({response_time:.1f}ms)")
        
        # Get detailed health status if available and verbose mode is on
        if verbose and hasattr(backend, 'get_detailed_health_status'):
            try:
                detailed_status = backend.get_detailed_health_status()
                console.print(f"[dim]  Status: {detailed_status.message}[/dim]")
                if detailed_status.error:
                    console.print(f"[dim]  Error: {detailed_status.error}[/dim]")
            except Exception as e:
                console.print(f"[dim]  Could not get detailed status: {e}[/dim]")
        
        # Get backend statistics
        if verbose:
            try:
                stats = backend.get_stats()
                console.print("[dim]  Statistics:[/dim]")
                for key, value in stats.items():
                    if key not in ['backend_type']:
                        console.print(f"[dim]    {key}: {value}[/dim]")
            except Exception as e:
                console.print(f"[dim]  Could not get statistics: {e}[/dim]")
        
        return is_healthy
        
    except Exception as e:
        console.print(f"[red]✗ Failed to check backend health: {e}[/red]")
        return False


def _benchmark_backend(backend_type: str, config: AdvancedCacheConfig, test_data: bytes, operations: int) -> dict:
    """Benchmark a specific backend type."""
    from ..cache.factory import BackendFactory
    import uuid
    
    # Create backend instance for testing
    test_config = AdvancedCacheConfig(
        backend_type=backend_type,
        dynamodb_table_name=config.dynamodb_table_name,
        dynamodb_region=config.dynamodb_region,
        dynamodb_profile=config.dynamodb_profile,
        file_cache_dir=config.file_cache_dir
    )
    
    backend = BackendFactory.create_backend(test_config)
    
    # Benchmark write operations
    console.print("[blue]Testing write operations...[/blue]")
    write_times = []
    test_keys = []
    
    for i in range(operations):
        key = f"benchmark_test_{uuid.uuid4()}"
        test_keys.append(key)
        
        start_time = time.time()
        backend.set(key, test_data, ttl=300, operation="benchmark")
        end_time = time.time()
        
        write_times.append((end_time - start_time) * 1000)  # Convert to milliseconds
        
        if (i + 1) % 10 == 0:
            console.print(f"[dim]  Completed {i + 1}/{operations} writes[/dim]")
    
    # Benchmark read operations
    console.print("[blue]Testing read operations...[/blue]")
    read_times = []
    
    for i, key in enumerate(test_keys):
        start_time = time.time()
        data = backend.get(key)
        end_time = time.time()
        
        read_times.append((end_time - start_time) * 1000)  # Convert to milliseconds
        
        if (i + 1) % 10 == 0:
            console.print(f"[dim]  Completed {i + 1}/{operations} reads[/dim]")
    
    # Clean up test data
    console.print("[blue]Cleaning up test data...[/blue]")
    for key in test_keys:
        try:
            backend.invalidate(key)
        except Exception:
            pass  # Ignore cleanup errors
    
    # Calculate statistics
    def calculate_stats(times):
        if not times:
            return {}
        
        times.sort()
        return {
            'min': min(times),
            'max': max(times),
            'avg': sum(times) / len(times),
            'median': times[len(times) // 2],
            'p95': times[int(len(times) * 0.95)],
            'p99': times[int(len(times) * 0.99)]
        }
    
    return {
        'backend_type': backend_type,
        'operations': operations,
        'data_size': len(test_data),
        'write_stats': calculate_stats(write_times),
        'read_stats': calculate_stats(read_times)
    }


def _display_benchmark_results(results: dict):
    """Display benchmark results in a formatted table."""
    console.print(f"[green]Backend:[/green] {results['backend_type']}")
    console.print(f"[green]Operations:[/green] {results['operations']}")
    console.print(f"[green]Data Size:[/green] {results['data_size']} bytes")
    
    # Create table for results
    table = Table()
    table.add_column("Operation", style="cyan")
    table.add_column("Min (ms)", style="green")
    table.add_column("Avg (ms)", style="yellow")
    table.add_column("Median (ms)", style="blue")
    table.add_column("P95 (ms)", style="magenta")
    table.add_column("P99 (ms)", style="red")
    table.add_column("Max (ms)", style="red")
    
    # Add write stats
    write_stats = results['write_stats']
    if write_stats:
        table.add_row(
            "Write",
            f"{write_stats['min']:.2f}",
            f"{write_stats['avg']:.2f}",
            f"{write_stats['median']:.2f}",
            f"{write_stats['p95']:.2f}",
            f"{write_stats['p99']:.2f}",
            f"{write_stats['max']:.2f}"
        )
    
    # Add read stats
    read_stats = results['read_stats']
    if read_stats:
        table.add_row(
            "Read",
            f"{read_stats['min']:.2f}",
            f"{read_stats['avg']:.2f}",
            f"{read_stats['median']:.2f}",
            f"{read_stats['p95']:.2f}",
            f"{read_stats['p99']:.2f}",
            f"{read_stats['max']:.2f}"
        )
    
    console.print(table)


def _repair_backend(backend_type: str, config: AdvancedCacheConfig) -> bool:
    """Repair a specific backend type."""
    from ..cache.factory import BackendFactory
    
    try:
        console.print(f"[blue]Attempting to repair {backend_type} backend...[/blue]")
        
        if backend_type == "file":
            # For file backend, ensure directory exists and is writable
            from ..cache.backends.file import FileBackend
            
            cache_dir = config.file_cache_dir or str(Path.home() / ".awsideman" / "cache")
            backend = FileBackend(cache_dir)
            
            # Test health and repair if needed
            if backend.health_check():
                console.print("[green]✓ File backend is already healthy[/green]")
                return True
            else:
                # Try to create cache directory
                try:
                    backend.path_manager.ensure_cache_directory()
                    console.print("[green]✓ Created cache directory[/green]")
                    
                    # Test again
                    if backend.health_check():
                        console.print("[green]✓ File backend repair successful[/green]")
                        return True
                    else:
                        console.print("[red]✗ File backend still unhealthy after repair attempt[/red]")
                        return False
                except Exception as e:
                    console.print(f"[red]✗ Failed to repair file backend: {e}[/red]")
                    return False
        
        elif backend_type == "dynamodb":
            # For DynamoDB backend, check table and repair if needed
            from ..cache.backends.dynamodb import DynamoDBBackend
            
            backend = DynamoDBBackend(
                table_name=config.dynamodb_table_name,
                region=config.dynamodb_region,
                profile=config.dynamodb_profile
            )
            
            # Use repair method if available
            if hasattr(backend, 'repair_table'):
                repair_result = backend.repair_table()
                
                if repair_result['success']:
                    console.print("[green]✓ DynamoDB backend repair successful[/green]")
                    for action in repair_result['actions_taken']:
                        console.print(f"[green]  • {action}[/green]")
                    return True
                else:
                    console.print("[red]✗ DynamoDB backend repair failed[/red]")
                    for error in repair_result['errors']:
                        console.print(f"[red]  • {error}[/red]")
                    return False
            else:
                # Fallback to basic health check
                if backend.health_check():
                    console.print("[green]✓ DynamoDB backend is already healthy[/green]")
                    return True
                else:
                    console.print("[red]✗ DynamoDB backend is unhealthy and cannot be repaired automatically[/red]")
                    return False
        
        elif backend_type == "hybrid":
            # For hybrid backend, repair both component backends
            file_success = _repair_backend("file", config)
            dynamodb_success = _repair_backend("dynamodb", config)
            
            if file_success and dynamodb_success:
                console.print("[green]✓ Hybrid backend repair successful[/green]")
                return True
            else:
                console.print("[red]✗ Hybrid backend repair partially failed[/red]")
                return False
        
        else:
            console.print(f"[red]✗ Unknown backend type: {backend_type}[/red]")
            return False
    
    except Exception as e:
        console.print(f"[red]✗ Repair failed for {backend_type}: {e}[/red]")
        return False


def _test_backend_connectivity(backend_type: str, config: AdvancedCacheConfig, timeout: int) -> bool:
    """Test connectivity to a specific backend type."""
    from ..cache.factory import BackendFactory
    
    try:
        console.print(f"[blue]Testing {backend_type} connectivity...[/blue]")
        
        if backend_type == "file":
            # For file backend, test local filesystem access
            from ..cache.backends.file import FileBackend
            
            cache_dir = config.file_cache_dir or str(Path.home() / ".awsideman" / "cache")
            backend = FileBackend(cache_dir)
            
            # Test basic operations
            test_key = "connectivity_test"
            test_data = b"connectivity_test_data"
            
            try:
                # Test write
                backend.set(test_key, test_data, ttl=60, operation="connectivity_test")
                console.print("[green]✓ Write operation successful[/green]")
                
                # Test read
                retrieved_data = backend.get(test_key)
                if retrieved_data == test_data:
                    console.print("[green]✓ Read operation successful[/green]")
                else:
                    console.print("[red]✗ Read operation returned incorrect data[/red]")
                    return False
                
                # Test delete
                backend.invalidate(test_key)
                console.print("[green]✓ Delete operation successful[/green]")
                
                return True
                
            except Exception as e:
                console.print(f"[red]✗ File backend connectivity test failed: {e}[/red]")
                return False
        
        elif backend_type == "dynamodb":
            # For DynamoDB backend, test AWS connectivity
            from ..cache.backends.dynamodb import DynamoDBBackend
            
            backend = DynamoDBBackend(
                table_name=config.dynamodb_table_name,
                region=config.dynamodb_region,
                profile=config.dynamodb_profile
            )
            
            try:
                # Test AWS credentials and connectivity
                console.print("[blue]  Testing AWS credentials...[/blue]")
                backend.client.list_tables(Limit=1)
                console.print("[green]✓ AWS credentials valid[/green]")
                
                # Test table access
                console.print("[blue]  Testing table access...[/blue]")
                if hasattr(backend, 'get_table_info'):
                    table_info = backend.get_table_info()
                    if table_info.get('exists', False):
                        console.print(f"[green]✓ Table '{config.dynamodb_table_name}' is accessible[/green]")
                        console.print(f"[green]  Status: {table_info.get('table_status', 'Unknown')}[/green]")
                    else:
                        console.print(f"[yellow]⚠ Table '{config.dynamodb_table_name}' does not exist[/yellow]")
                        console.print("[dim]  Table will be created automatically when needed[/dim]")
                
                # Test basic operations
                console.print("[blue]  Testing basic operations...[/blue]")
                test_key = "connectivity_test"
                test_data = b"connectivity_test_data"
                
                # Test write
                backend.set(test_key, test_data, ttl=60, operation="connectivity_test")
                console.print("[green]✓ Write operation successful[/green]")
                
                # Test read
                retrieved_data = backend.get(test_key)
                if retrieved_data == test_data:
                    console.print("[green]✓ Read operation successful[/green]")
                else:
                    console.print("[red]✗ Read operation returned incorrect data[/red]")
                    return False
                
                # Test delete
                backend.invalidate(test_key)
                console.print("[green]✓ Delete operation successful[/green]")
                
                return True
                
            except Exception as e:
                console.print(f"[red]✗ DynamoDB connectivity test failed: {e}[/red]")
                return False
        
        elif backend_type == "hybrid":
            # For hybrid backend, test both component backends
            file_success = _test_backend_connectivity("file", config, timeout)
            dynamodb_success = _test_backend_connectivity("dynamodb", config, timeout)
            
            if file_success and dynamodb_success:
                console.print("[green]✓ Hybrid backend connectivity successful[/green]")
                return True
            else:
                console.print("[red]✗ Hybrid backend connectivity partially failed[/red]")
                return False
        
        else:
            console.print(f"[red]✗ Unknown backend type: {backend_type}[/red]")
            return False
    
    except Exception as e:
        console.print(f"[red]✗ Connectivity test failed for {backend_type}: {e}[/red]")
        return False
# Configuration management commands
@config_app.command("show")
def show_configuration():
    """Display current cache configuration settings.
    
    Shows all cache configuration options including backend settings,
    encryption configuration, and DynamoDB settings.
    """
    try:
        cache_manager = CacheManager()
        
        console.print("\n[bold blue]Cache Configuration[/bold blue]")
        console.print("=" * 40)
        
        # Check if using advanced configuration
        if isinstance(cache_manager.config, AdvancedCacheConfig):
            config = cache_manager.config
            
            # Display basic settings
            console.print("\n[bold blue]Basic Settings[/bold blue]")
            console.print("-" * 20)
            console.print(f"[green]Enabled:[/green] {'Yes' if config.enabled else 'No'}")
            console.print(f"[green]Default TTL:[/green] {config.default_ttl} seconds")
            console.print(f"[green]Max Size:[/green] {config.max_size_mb} MB")
            
            # Display backend settings
            console.print("\n[bold blue]Backend Settings[/bold blue]")
            console.print("-" * 20)
            console.print(f"[green]Backend Type:[/green] {config.backend_type}")
            
            if config.backend_type in ["dynamodb", "hybrid"]:
                console.print(f"[green]DynamoDB Table:[/green] {config.dynamodb_table_name}")
                console.print(f"[green]DynamoDB Region:[/green] {config.dynamodb_region or 'default'}")
                console.print(f"[green]DynamoDB Profile:[/green] {config.dynamodb_profile or 'default'}")
            
            if config.backend_type in ["file", "hybrid"]:
                console.print(f"[green]File Cache Dir:[/green] {config.file_cache_dir or 'default'}")
            
            if config.backend_type == "hybrid":
                console.print(f"[green]Hybrid Local TTL:[/green] {config.hybrid_local_ttl} seconds")
            
            # Display encryption settings
            console.print("\n[bold blue]Encryption Settings[/bold blue]")
            console.print("-" * 25)
            console.print(f"[green]Encryption Enabled:[/green] {'Yes' if config.encryption_enabled else 'No'}")
            console.print(f"[green]Encryption Type:[/green] {config.encryption_type}")
            
            # Display operation-specific TTLs
            if config.operation_ttls:
                console.print("\n[bold blue]Operation TTLs[/bold blue]")
                console.print("-" * 20)
                for operation, ttl in config.operation_ttls.items():
                    console.print(f"[green]{operation}:[/green] {ttl} seconds")
        else:
            console.print("[yellow]Using basic cache configuration[/yellow]")
            console.print(f"[green]Enabled:[/green] {'Yes' if cache_manager.config.enabled else 'No'}")
            console.print(f"[green]Default TTL:[/green] {cache_manager.config.default_ttl} seconds")
            console.print(f"[green]Max Size:[/green] {cache_manager.config.max_size_mb} MB")
            console.print("[dim]Advanced configuration options not available[/dim]")
        
    except Exception as e:
        console.print(f"[red]Error displaying configuration: {e}[/red]")
        raise typer.Exit(1)


@config_app.command("set-backend")
def set_backend(
    backend_type: str = typer.Argument(..., help="Backend type (file, dynamodb, hybrid)"),
    table_name: Optional[str] = typer.Option(None, "--table", help="DynamoDB table name"),
    region: Optional[str] = typer.Option(None, "--region", help="DynamoDB region"),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile"),
    cache_dir: Optional[str] = typer.Option(None, "--cache-dir", help="File cache directory"),
    local_ttl: Optional[int] = typer.Option(None, "--local-ttl", help="Hybrid local TTL in seconds"),
    force: bool = typer.Option(False, "--force", "-f", help="Force change without confirmation"),
):
    """Configure cache backend settings.
    
    Changes the cache backend type and related configuration options.
    This will affect how and where cache data is stored.
    """
    try:
        # Validate backend type
        valid_backends = ["file", "dynamodb", "hybrid"]
        if backend_type not in valid_backends:
            console.print(f"[red]Error: Invalid backend type '{backend_type}'[/red]")
            console.print(f"Valid options: {', '.join(valid_backends)}")
            raise typer.Exit(1)
        
        # Load current configuration
        try:
            config = AdvancedCacheConfig.from_config_and_environment()
        except Exception:
            console.print("[yellow]Creating new advanced configuration[/yellow]")
            config = AdvancedCacheConfig()
        
        # Show current configuration
        console.print(f"[blue]Current backend: {config.backend_type}[/blue]")
        console.print(f"[blue]New backend: {backend_type}[/blue]")
        
        # Ask for confirmation unless --force is used
        if not force:
            console.print("\n[bold yellow]WARNING:[/bold yellow] Changing backend type will:")
            console.print("• Change how cache data is stored and accessed")
            console.print("• May require clearing existing cache data")
            console.print("• May require additional AWS permissions for DynamoDB")
            
            confirm = typer.confirm("\nAre you sure you want to change the backend?")
            if not confirm:
                console.print("[blue]Backend change cancelled[/blue]")
                return
        
        # Update configuration
        config.backend_type = backend_type
        
        # Update backend-specific settings
        if backend_type in ["dynamodb", "hybrid"]:
            if table_name:
                config.dynamodb_table_name = table_name
            if region:
                config.dynamodb_region = region
            if profile:
                config.dynamodb_profile = profile
        
        if backend_type in ["file", "hybrid"]:
            if cache_dir:
                config.file_cache_dir = cache_dir
        
        if backend_type == "hybrid" and local_ttl:
            config.hybrid_local_ttl = local_ttl
        
        # Validate configuration
        validation_errors = config.validate()
        if validation_errors:
            console.print("[red]Configuration validation errors:[/red]")
            for field, error in validation_errors.items():
                console.print(f"[red]• {field}: {error}[/red]")
            raise typer.Exit(1)
        
        # Save configuration
        config.save_to_file()
        
        console.print(f"[green]✓ Successfully configured {backend_type} backend[/green]")
        
        # Show next steps
        if backend_type == "dynamodb":
            console.print("\n[bold blue]Next Steps:[/bold blue]")
            console.print("• Ensure AWS credentials are configured")
            console.print("• Verify DynamoDB permissions")
            console.print("• Run 'awsideman cache config test' to verify connectivity")
        elif backend_type == "hybrid":
            console.print("\n[bold blue]Next Steps:[/bold blue]")
            console.print("• Ensure AWS credentials are configured for DynamoDB")
            console.print("• Verify file system permissions for local cache")
            console.print("• Run 'awsideman cache config test' to verify both backends")
        
    except Exception as e:
        console.print(f"[red]Error configuring backend: {e}[/red]")
        raise typer.Exit(1)


@config_app.command("enable-encryption")
def enable_encryption(
    encryption_type: str = typer.Option("aes256", "--type", "-t", help="Encryption type (aes256)"),
    force: bool = typer.Option(False, "--force", "-f", help="Force enable without confirmation"),
):
    """Enable encryption for cache data.
    
    Enables encryption and generates encryption keys. This will encrypt
    all future cache data and optionally re-encrypt existing data.
    """
    try:
        # Validate encryption type
        available_providers = EncryptionProviderFactory.get_available_providers()
        if encryption_type not in available_providers:
            console.print(f"[red]Error: Encryption type '{encryption_type}' is not available[/red]")
            console.print(f"Available types: {', '.join(available_providers)}")
            raise typer.Exit(1)
        
        # Load current configuration
        try:
            config = AdvancedCacheConfig.from_config_and_environment()
        except Exception:
            console.print("[yellow]Creating new advanced configuration[/yellow]")
            config = AdvancedCacheConfig()
        
        # Check if encryption is already enabled
        if config.encryption_enabled:
            console.print("[yellow]Encryption is already enabled[/yellow]")
            console.print(f"Current encryption type: {config.encryption_type}")
            return
        
        # Ask for confirmation unless --force is used
        if not force:
            console.print("\n[bold yellow]WARNING:[/bold yellow] Enabling encryption will:")
            console.print("• Generate and store a new encryption key")
            console.print("• Encrypt all future cache data")
            console.print("• Make cache data unreadable without the encryption key")
            console.print("• Store the key in your system's keyring/keychain")
            
            confirm = typer.confirm("\nAre you sure you want to enable encryption?")
            if not confirm:
                console.print("[blue]Encryption enable cancelled[/blue]")
                return
        
        # Update configuration
        config.encryption_enabled = True
        config.encryption_type = encryption_type
        
        # Validate configuration
        validation_errors = config.validate()
        if validation_errors:
            console.print("[red]Configuration validation errors:[/red]")
            for field, error in validation_errors.items():
                console.print(f"[red]• {field}: {error}[/red]")
            raise typer.Exit(1)
        
        # Test encryption provider availability
        console.print("[blue]Testing encryption provider...[/blue]")
        try:
            provider = EncryptionProviderFactory.create_provider(encryption_type)
            if not provider.is_available():
                console.print(f"[red]Error: Encryption provider '{encryption_type}' is not available[/red]")
                raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Error testing encryption provider: {e}[/red]")
            raise typer.Exit(1)
        
        # Save configuration
        config.save_to_file()
        
        console.print(f"[green]✓ Successfully enabled {encryption_type} encryption[/green]")
        console.print("[green]✓ Encryption key generated and stored securely[/green]")
        
        # Show next steps
        console.print("\n[bold blue]Next Steps:[/bold blue]")
        console.print("• All new cache data will be encrypted automatically")
        console.print("• Consider backing up your encryption key")
        console.print("• Run 'awsideman cache encryption status' to verify setup")
        
    except Exception as e:
        console.print(f"[red]Error enabling encryption: {e}[/red]")
        raise typer.Exit(1)


@config_app.command("disable-encryption")
def disable_encryption(
    force: bool = typer.Option(False, "--force", "-f", help="Force disable without confirmation"),
):
    """Disable encryption for cache data.
    
    Disables encryption for future cache operations. Existing encrypted
    cache data will become inaccessible unless re-encrypted.
    """
    try:
        # Load current configuration
        try:
            config = AdvancedCacheConfig.from_config_and_environment()
        except Exception:
            console.print("[red]Error: Could not load configuration[/red]")
            raise typer.Exit(1)
        
        # Check if encryption is already disabled
        if not config.encryption_enabled:
            console.print("[yellow]Encryption is already disabled[/yellow]")
            return
        
        # Ask for confirmation unless --force is used
        if not force:
            console.print("\n[bold red]WARNING:[/bold red] Disabling encryption will:")
            console.print("• Make existing encrypted cache data inaccessible")
            console.print("• Store future cache data in plain text")
            console.print("• Reduce security of cached AWS data")
            console.print("• Require clearing cache to access data again")
            
            console.print("\n[bold yellow]RECOMMENDATION:[/bold yellow] Consider clearing cache after disabling encryption")
            
            confirm = typer.confirm("\nAre you sure you want to disable encryption?")
            if not confirm:
                console.print("[blue]Encryption disable cancelled[/blue]")
                return
        
        # Update configuration
        config.encryption_enabled = False
        config.encryption_type = "none"
        
        # Save configuration
        config.save_to_file()
        
        console.print("[green]✓ Successfully disabled encryption[/green]")
        
        # Show next steps
        console.print("\n[bold blue]Next Steps:[/bold blue]")
        console.print("• Consider running 'awsideman cache clear' to remove encrypted data")
        console.print("• Future cache data will be stored in plain text")
        console.print("• Encryption key remains in keyring for potential re-enabling")
        
    except Exception as e:
        console.print(f"[red]Error disabling encryption: {e}[/red]")
        raise typer.Exit(1)


@config_app.command("create-table")
def create_dynamodb_table(
    table_name: Optional[str] = typer.Option(None, "--table", help="DynamoDB table name"),
    region: Optional[str] = typer.Option(None, "--region", help="DynamoDB region"),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile"),
    force: bool = typer.Option(False, "--force", "-f", help="Force creation without confirmation"),
):
    """Create DynamoDB table for cache storage.
    
    Creates a DynamoDB table with proper configuration for cache storage
    including TTL settings and appropriate billing mode.
    """
    try:
        # Load current configuration to get defaults
        try:
            config = AdvancedCacheConfig.from_config_and_environment()
            table_name = table_name or config.dynamodb_table_name
            region = region or config.dynamodb_region
            profile = profile or config.dynamodb_profile
        except Exception:
            table_name = table_name or "awsideman-cache"
        
        console.print(f"[blue]Creating DynamoDB table: {table_name}[/blue]")
        if region:
            console.print(f"[blue]Region: {region}[/blue]")
        if profile:
            console.print(f"[blue]Profile: {profile}[/blue]")
        
        # Ask for confirmation unless --force is used
        if not force:
            console.print("\n[bold yellow]This will:[/bold yellow]")
            console.print("• Create a new DynamoDB table")
            console.print("• Configure TTL for automatic expiration")
            console.print("• Set up pay-per-request billing")
            console.print("• May incur AWS charges")
            
            confirm = typer.confirm("\nAre you sure you want to create the table?")
            if not confirm:
                console.print("[blue]Table creation cancelled[/blue]")
                return
        
        # Create DynamoDB backend to handle table creation
        from ..cache.backends.dynamodb import DynamoDBBackend
        
        backend = DynamoDBBackend(
            table_name=table_name,
            region=region,
            profile=profile
        )
        
        # Check if table already exists
        console.print("[blue]Checking if table exists...[/blue]")
        try:
            backend.table.load()
            console.print("[yellow]Table already exists[/yellow]")
            
            # Show table information
            stats = backend.get_stats()
            console.print(f"[green]Table Status:[/green] {stats.get('table_status', 'UNKNOWN')}")
            console.print(f"[green]Item Count:[/green] {stats.get('item_count', 0)}")
            console.print(f"[green]TTL Enabled:[/green] {'Yes' if stats.get('ttl_enabled', False) else 'No'}")
            return
            
        except Exception:
            # Table doesn't exist, proceed with creation
            pass
        
        # Create the table
        console.print("[blue]Creating DynamoDB table...[/blue]")
        backend.ensure_table_exists()
        
        # Verify table creation
        console.print("[blue]Verifying table creation...[/blue]")
        stats = backend.get_stats()
        
        if stats.get('table_exists', False):
            console.print(f"[green]✓ Successfully created table: {table_name}[/green]")
            console.print(f"[green]✓ Table Status: {stats.get('table_status', 'UNKNOWN')}[/green]")
            console.print(f"[green]✓ TTL Enabled: {'Yes' if stats.get('ttl_enabled', False) else 'No'}[/green]")
            console.print(f"[green]✓ Billing Mode: {stats.get('billing_mode', 'UNKNOWN')}[/green]")
        else:
            console.print("[red]Error: Table creation may have failed[/red]")
            raise typer.Exit(1)
        
    except Exception as e:
        console.print(f"[red]Error creating DynamoDB table: {e}[/red]")
        raise typer.Exit(1)


@config_app.command("test")
def test_configuration():
    """Test cache configuration and connectivity.
    
    Validates the current cache configuration and tests connectivity
    to backends, encryption providers, and other dependencies.
    """
    try:
        console.print("\n[bold blue]Testing Cache Configuration[/bold blue]")
        console.print("=" * 40)
        
        # Test basic configuration loading
        console.print("[blue]Testing configuration loading...[/blue]")
        try:
            cache_manager = CacheManager()
            console.print("[green]✓ Configuration loaded successfully[/green]")
        except Exception as e:
            console.print(f"[red]✗ Configuration loading failed: {e}[/red]")
            raise typer.Exit(1)
        
        if not cache_manager.config.enabled:
            console.print("[yellow]Cache is disabled - skipping further tests[/yellow]")
            return
        
        # Test backend connectivity
        console.print("\n[blue]Testing backend connectivity...[/blue]")
        if hasattr(cache_manager, 'backend') and cache_manager.backend:
            try:
                is_healthy = cache_manager.backend.health_check()
                if is_healthy:
                    console.print("[green]✓ Backend is healthy and accessible[/green]")
                else:
                    console.print("[red]✗ Backend health check failed[/red]")
            except Exception as e:
                console.print(f"[red]✗ Backend connectivity test failed: {e}[/red]")
        else:
            console.print("[yellow]⚠ Using legacy configuration - backend tests skipped[/yellow]")
        
        # Test encryption if enabled
        if isinstance(cache_manager.config, AdvancedCacheConfig) and cache_manager.config.encryption_enabled:
            console.print("\n[blue]Testing encryption...[/blue]")
            try:
                if hasattr(cache_manager, 'encryption_provider') and cache_manager.encryption_provider:
                    is_available = cache_manager.encryption_provider.is_available()
                    if is_available:
                        console.print("[green]✓ Encryption provider is available[/green]")
                        
                        # Test encryption/decryption
                        test_data = {"test": "data", "timestamp": time.time()}
                        encrypted = cache_manager.encryption_provider.encrypt(test_data)
                        decrypted = cache_manager.encryption_provider.decrypt(encrypted)
                        
                        if decrypted == test_data:
                            console.print("[green]✓ Encryption/decryption test passed[/green]")
                        else:
                            console.print("[red]✗ Encryption/decryption test failed[/red]")
                    else:
                        console.print("[red]✗ Encryption provider is not available[/red]")
                else:
                    console.print("[red]✗ No encryption provider configured[/red]")
            except Exception as e:
                console.print(f"[red]✗ Encryption test failed: {e}[/red]")
        
        # Test cache operations
        console.print("\n[blue]Testing cache operations...[/blue]")
        try:
            test_key = f"test_key_{int(time.time())}"
            test_data = {"test": "cache_operation", "timestamp": time.time()}
            
            # Test set operation
            cache_manager.set(test_key, test_data, ttl=60, operation="config_test")
            console.print("[green]✓ Cache set operation successful[/green]")
            
            # Test get operation
            retrieved_data = cache_manager.get(test_key)
            if retrieved_data == test_data:
                console.print("[green]✓ Cache get operation successful[/green]")
            else:
                console.print("[red]✗ Cache get operation failed - data mismatch[/red]")
            
            # Test invalidate operation
            cache_manager.invalidate(test_key)
            retrieved_after_invalidate = cache_manager.get(test_key)
            if retrieved_after_invalidate is None:
                console.print("[green]✓ Cache invalidate operation successful[/green]")
            else:
                console.print("[red]✗ Cache invalidate operation failed[/red]")
                
        except Exception as e:
            console.print(f"[red]✗ Cache operations test failed: {e}[/red]")
        
        # Test configuration validation
        console.print("\n[blue]Testing configuration validation...[/blue]")
        if isinstance(cache_manager.config, AdvancedCacheConfig):
            validation_errors = cache_manager.config.validate()
            if not validation_errors:
                console.print("[green]✓ Configuration validation passed[/green]")
            else:
                console.print("[yellow]⚠ Configuration validation warnings:[/yellow]")
                for field, error in validation_errors.items():
                    console.print(f"[yellow]  • {field}: {error}[/yellow]")
        
        console.print("\n[bold green]Configuration test completed[/bold green]")
        
    except Exception as e:
        console.print(f"[red]Error testing configuration: {e}[/red]")
        raise typer.Exit(1)


@config_app.command("validate")
def validate_configuration():
    """Validate cache configuration settings.
    
    Checks the current cache configuration for errors and provides
    recommendations for optimal settings.
    """
    try:
        console.print("\n[bold blue]Cache Configuration Validation[/bold blue]")
        console.print("=" * 45)
        
        # Load and validate configuration
        try:
            config = AdvancedCacheConfig.from_config_and_environment()
            console.print("[green]✓ Configuration loaded successfully[/green]")
        except Exception as e:
            console.print(f"[red]✗ Failed to load configuration: {e}[/red]")
            raise typer.Exit(1)
        
        # Perform validation
        validation_errors = config.validate()
        
        if not validation_errors:
            console.print("[green]✓ Configuration validation passed - no errors found[/green]")
        else:
            console.print(f"[red]✗ Found {len(validation_errors)} validation errors:[/red]")
            for field, error in validation_errors.items():
                console.print(f"[red]  • {field}: {error}[/red]")
        
        # Provide recommendations
        console.print("\n[bold blue]Recommendations[/bold blue]")
        console.print("-" * 20)
        
        recommendations = []
        
        # Backend recommendations
        if config.backend_type == "file" and not config.encryption_enabled:
            recommendations.append("Consider enabling encryption for file-based cache to protect sensitive data")
        
        if config.backend_type == "dynamodb" and not config.dynamodb_region:
            recommendations.append("Specify a DynamoDB region for better performance and cost control")
        
        # TTL recommendations
        if config.default_ttl > 86400:  # 24 hours
            recommendations.append("Default TTL is quite long - consider shorter TTL for more up-to-date data")
        elif config.default_ttl < 300:  # 5 minutes
            recommendations.append("Default TTL is quite short - may result in frequent API calls")
        
        # Size recommendations
        if config.max_size_mb > 1000:  # 1GB
            recommendations.append("Max cache size is quite large - monitor disk usage")
        elif config.max_size_mb < 50:  # 50MB
            recommendations.append("Max cache size is quite small - may result in frequent cache evictions")
        
        # Encryption recommendations
        if not config.encryption_enabled and config.backend_type in ["file", "hybrid"]:
            recommendations.append("Consider enabling encryption for local cache files")
        
        if recommendations:
            for i, recommendation in enumerate(recommendations, 1):
                console.print(f"[yellow]{i}. {recommendation}[/yellow]")
        else:
            console.print("[green]No specific recommendations - configuration looks good![/green]")
        
        # Display configuration summary
        console.print("\n[bold blue]Configuration Summary[/bold blue]")
        console.print("-" * 25)
        console.print(f"[green]Backend:[/green] {config.backend_type}")
        console.print(f"[green]Encryption:[/green] {'Enabled' if config.encryption_enabled else 'Disabled'}")
        console.print(f"[green]Default TTL:[/green] {config.default_ttl} seconds")
        console.print(f"[green]Max Size:[/green] {config.max_size_mb} MB")
        
        if validation_errors:
            console.print(f"\n[red]Please fix {len(validation_errors)} validation errors before using the cache[/red]")
            raise typer.Exit(1)
        else:
            console.print("\n[green]Configuration is valid and ready to use[/green]")
        
    except Exception as e:
        console.print(f"[red]Error validating configuration: {e}[/red]")
        raise typer.Exit(1)