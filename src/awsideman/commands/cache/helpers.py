"""Shared utilities for cache management commands."""

import logging
from typing import Any, Dict, Optional

from rich.console import Console
from rich.table import Table

from ...cache.config import AdvancedCacheConfig
from ...cache.manager import CacheManager
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

    # Add validation logic as needed
    return True


def get_cache_manager() -> CacheManager:
    """Get a configured cache manager instance."""
    try:
        # Try to load advanced cache configuration from config file
        from ...cache.config import AdvancedCacheConfig
        from ...utils.config import Config
        
        config = Config()
        cache_config_data = config.get_cache_config()
        
        # Check if we have advanced cache configuration
        all_config_data = config.get_all()
        if "cache" in all_config_data and isinstance(all_config_data["cache"], dict):
            cache_section = all_config_data["cache"]
            
            # If we have advanced settings, use AdvancedCacheConfig
            if any(key in cache_section for key in [
                "backend_type", "encryption_enabled", "encryption_type", 
                "dynamodb_table_name", "dynamodb_region", "dynamodb_profile"
            ]):
                logger.debug("Loading advanced cache configuration")
                advanced_config = AdvancedCacheConfig.from_config_file()
                return CacheManager(config=advanced_config)
        
        # Fall back to basic configuration
        logger.debug("Using basic cache configuration")
        return CacheManager()
        
    except Exception as e:
        logger.warning(f"Failed to load advanced cache configuration, using defaults: {e}")
        return CacheManager()


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
