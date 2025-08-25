"""Shared utilities for cache management commands."""

import logging
from typing import Any, Dict, Optional, Union

from rich.console import Console
from rich.table import Table

from ...aws_clients.manager import AWSClientManager
from ...cache.config import AdvancedCacheConfig
from ...cache.manager import CacheManager
from ...cache.utilities import (
    create_aws_client_manager,
    create_cache_manager,
    get_default_cache_config,
    get_optimal_cache_config_for_environment,
    validate_cache_configuration,
)
from ...utils.account_cache_optimizer import AccountCacheOptimizer

# Shared console instance
console = Console()
logger = logging.getLogger(__name__)


def format_cache_stats(stats: Dict[str, Any]) -> str:
    """Format cache statistics for display."""
    if not stats.get("enabled", False):
        return "Cache is disabled"

    total_entries = stats.get("total_entries", 0)
    total_size_mb = stats.get("total_size_mb", 0)
    hit_rate = stats.get("hit_rate", 0)

    return f"{total_entries} entries, {total_size_mb:.2f} MB, {hit_rate:.1f}% hit rate"


def create_cache_table() -> Table:
    """Create a rich table for displaying cache information."""
    table = Table(show_header=True, header_style="bold blue")
    table.add_column("Key", style="green")
    table.add_column("Value", style="cyan")
    table.add_column("Type", style="magenta")
    return table


def validate_cache_config(config: AdvancedCacheConfig) -> bool:
    """Validate cache configuration."""
    if not config:
        return False

    # Use the new validation utility
    validation_errors = validate_cache_configuration(config)
    if validation_errors:
        logger.warning(f"Cache configuration validation errors: {validation_errors}")
        return False

    return True


def get_cache_manager() -> CacheManager:
    """
    Get the unified cache manager singleton instance.

    This function now returns the CacheManager singleton,
    ensuring consistent cache behavior across all commands.
    """
    try:
        # Use the new utility function to get the singleton
        logger.debug("Getting unified cache manager singleton")
        cache_manager = create_cache_manager()

        logger.info("Successfully retrieved unified cache manager singleton")
        return cache_manager

    except Exception as e:
        logger.error(f"Failed to get unified cache manager: {e}")

        # Fall back to creating a new singleton instance
        logger.info("Falling back to direct CacheManager instantiation")
        return CacheManager()


def get_aws_client_manager_with_cache(
    profile: Optional[str] = None,
    region: Optional[str] = None,
    enable_caching: bool = True,
    cache_config: Optional[Union[AdvancedCacheConfig, Dict[str, Any]]] = None,
) -> "AWSClientManager":
    """
    Get an AWS client manager with proper cache integration.

    This function provides a standardized way to create AWS client managers
    with cache integration using the new utilities.

    Args:
        profile: AWS profile name to use
        region: AWS region to use
        enable_caching: Whether to enable caching
        cache_config: Optional cache configuration

    Returns:
        Configured AWSClientManager instance with cache integration
    """
    try:
        logger.debug("Creating AWS client manager with cache integration using enhanced utilities")
        client_manager = create_aws_client_manager(
            profile=profile,
            region=region,
            enable_caching=enable_caching,
            cache_config=cache_config,
            auto_configure_cache=True,
        )

        logger.info("Successfully created AWS client manager with cache integration")
        return client_manager

    except Exception as e:
        logger.error(f"Failed to create AWS client manager with cache integration: {e}")

        # Fall back to basic client manager without caching
        logger.info("Falling back to basic AWS client manager without caching")
        from ...aws_clients.manager import AWSClientManager

        return AWSClientManager(profile=profile, region=region, enable_caching=False)


def get_optimal_cache_config() -> AdvancedCacheConfig:
    """
    Get optimal cache configuration for the current environment.

    This function uses the new utility to analyze the environment
    and return the best cache configuration.
    """
    try:
        logger.debug("Getting optimal cache configuration for current environment")
        config = get_optimal_cache_config_for_environment()

        logger.info(
            f"Generated optimal cache config: backend={config.backend_type}, encryption={config.encryption_enabled}"
        )
        return config

    except Exception as e:
        logger.warning(f"Failed to get optimal cache config: {e}")
        return get_default_cache_config()


def get_account_cache_optimizer() -> AccountCacheOptimizer:
    """Get an account cache optimizer instance."""
    return AccountCacheOptimizer()


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"


def safe_json_loads(json_str: str) -> Optional[Dict[str, Any]]:
    """Safely parse JSON string, returning None on error."""
    try:
        import json

        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return None


def get_cache_config_summary(config: AdvancedCacheConfig) -> Dict[str, Any]:
    """
    Get a summary of cache configuration for display purposes.

    Args:
        config: Cache configuration to summarize

    Returns:
        Dictionary with configuration summary
    """
    summary = {
        "enabled": config.enabled,
        "backend_type": config.backend_type,
        "default_ttl": f"{config.default_ttl} seconds ({config.default_ttl // 60} minutes)",
        "max_size_mb": f"{config.max_size_mb} MB",
        "encryption_enabled": config.encryption_enabled,
        "encryption_type": config.encryption_type,
    }

    # Add backend-specific information
    if config.backend_type == "dynamodb":
        summary.update(
            {
                "dynamodb_table": config.dynamodb_table_name,
                "dynamodb_region": config.dynamodb_region or "default",
                "dynamodb_profile": config.dynamodb_profile or "default",
            }
        )
    elif config.backend_type == "file":
        summary.update({"file_cache_dir": config.file_cache_dir or "default"})
    elif config.backend_type == "hybrid":
        summary.update(
            {
                "hybrid_local_ttl": f"{config.hybrid_local_ttl} seconds",
                "dynamodb_table": config.dynamodb_table_name,
                "file_cache_dir": config.file_cache_dir or "default",
            }
        )

    return summary


def display_cache_config_summary(config: AdvancedCacheConfig) -> None:
    """
    Display a formatted summary of cache configuration.

    Args:
        config: Cache configuration to display
    """
    summary = get_cache_config_summary(config)

    table = create_cache_table()
    table.title = "Cache Configuration Summary"

    for key, value in summary.items():
        table.add_row(key.replace("_", " ").title(), str(value), type(value).__name__)

    console.print(table)
