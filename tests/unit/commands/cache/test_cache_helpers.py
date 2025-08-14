"""Tests for cache helpers module."""

import pytest


def test_cache_helpers_module_import():
    """Test that the cache helpers module can be imported."""
    try:
        from src.awsideman.commands.cache.helpers import (
            console,
            create_cache_table,
            format_cache_stats,
            format_file_size,
            get_account_cache_optimizer,
            get_cache_manager,
            safe_json_loads,
            validate_cache_config,
        )

        assert console is not None
        assert callable(format_cache_stats)
        assert callable(create_cache_table)
        assert callable(validate_cache_config)
        assert callable(get_cache_manager)
        assert callable(get_account_cache_optimizer)
        assert callable(format_file_size)
        assert callable(safe_json_loads)
    except ImportError as e:
        pytest.fail(f"Failed to import cache helpers: {e}")


def test_cache_helpers_console_instance():
    """Test that the console instance is properly configured."""
    from src.awsideman.commands.cache.helpers import console

    # Check that console is a rich Console instance
    assert hasattr(console, "print")
    assert callable(console.print)


def test_cache_helpers_format_cache_stats():
    """Test that the format_cache_stats function works correctly."""
    from src.awsideman.commands.cache.helpers import format_cache_stats

    # Test with enabled cache
    stats_enabled = {"enabled": True, "total_entries": 100, "total_size_mb": 5.5, "hit_rate": 85.2}
    result = format_cache_stats(stats_enabled)
    assert "100 entries" in result
    assert "5.50 MB" in result
    assert "85.2%" in result

    # Test with disabled cache
    stats_disabled = {"enabled": False}
    result = format_cache_stats(stats_disabled)
    assert result == "Cache is disabled"


def test_cache_helpers_create_cache_table():
    """Test that the create_cache_table function works correctly."""
    from src.awsideman.commands.cache.helpers import create_cache_table

    table = create_cache_table()
    assert table is not None
    assert hasattr(table, "add_column")
    assert hasattr(table, "add_row")


def test_cache_helpers_format_file_size():
    """Test that the format_file_size function works correctly."""
    from src.awsideman.commands.cache.helpers import format_file_size

    # Test various sizes
    assert "1.00 KB" in format_file_size(1024)
    assert "1.00 MB" in format_file_size(1024 * 1024)
    assert "1.00 GB" in format_file_size(1024 * 1024 * 1024)


def test_cache_helpers_safe_json_loads():
    """Test that the safe_json_loads function works correctly."""
    from src.awsideman.commands.cache.helpers import safe_json_loads

    # Test valid JSON
    valid_json = '{"key": "value", "number": 42}'
    result = safe_json_loads(valid_json)
    assert result == {"key": "value", "number": 42}

    # Test invalid JSON
    invalid_json = '{"key": "value", "number": 42'  # Missing closing brace
    result = safe_json_loads(invalid_json)
    assert result is None

    # Test non-string input
    result = safe_json_loads(123)
    assert result is None
