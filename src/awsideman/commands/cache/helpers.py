"""Shared utilities for cache management commands."""

from typing import Any, Dict, Optional

from rich.console import Console
from rich.table import Table

from ...cache.config import AdvancedCacheConfig
from ...cache.manager import CacheManager
from ...utils.account_cache_optimizer import AccountCacheOptimizer

# Shared console instance
console = Console()


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
