"""Simplified tests for cache module structure."""

import pytest


def test_cache_module_import():
    """Test that the cache module can be imported."""
    try:
        from src.awsideman.commands.cache import app

        assert app is not None
        assert hasattr(app, "command")
    except ImportError as e:
        pytest.fail(f"Failed to import cache module: {e}")


def test_cache_app_commands():
    """Test that the cache app has the expected commands."""
    from src.awsideman.commands.cache import app

    # Get all registered commands
    commands = [cmd.name for cmd in app.registered_commands]

    # Check that all expected commands are present
    expected_commands = ["clear", "status", "warm", "encryption", "accounts", "inspect"]
    for cmd in expected_commands:
        assert cmd in commands, f"Command '{cmd}' not found in cache app"


def test_cache_module_structure():
    """Test that the cache module structure is correct."""
    try:
        # Test that all submodules can be imported
        from src.awsideman.commands.cache import (
            accounts,
            clear,
            encryption,
            helpers,
            inspect,
            status,
            warm,
        )

        # Check that main functions exist
        assert hasattr(clear, "clear_cache")
        assert hasattr(status, "cache_status")
        assert hasattr(warm, "warm_cache")
        assert hasattr(encryption, "encryption_management")
        assert hasattr(accounts, "account_cache_status")
        assert hasattr(inspect, "inspect_cache")
        assert hasattr(helpers, "console")

    except ImportError as e:
        pytest.fail(f"Failed to import cache submodules: {e}")


def test_cache_commands_help_text():
    """Test that all cache commands have help text."""
    from src.awsideman.commands.cache import accounts, clear, encryption, inspect, status, warm

    # Check that all commands have docstrings
    assert clear.clear_cache.__doc__ is not None
    assert status.cache_status.__doc__ is not None
    assert warm.warm_cache.__doc__ is not None
    assert encryption.encryption_management.__doc__ is not None
    assert accounts.account_cache_status.__doc__ is not None
    assert inspect.inspect_cache.__doc__ is not None

    # Check that docstrings contain expected content
    assert "clear" in clear.clear_cache.__doc__.lower()
    assert "status" in status.cache_status.__doc__.lower()
    assert "warm" in warm.warm_cache.__doc__.lower()
    assert "encryption" in encryption.encryption_management.__doc__.lower()
    assert "account" in accounts.account_cache_status.__doc__.lower()
    assert "inspect" in inspect.inspect_cache.__doc__.lower()


def test_cache_helpers_functions():
    """Test that cache helpers module has expected functions."""
    from src.awsideman.commands.cache.helpers import (
        create_cache_table,
        format_cache_stats,
        format_file_size,
        get_account_cache_optimizer,
        get_cache_manager,
        safe_json_loads,
        validate_cache_config,
    )

    # Check that all helper functions exist and are callable
    assert callable(format_cache_stats)
    assert callable(create_cache_table)
    assert callable(validate_cache_config)
    assert callable(get_cache_manager)
    assert callable(get_account_cache_optimizer)
    assert callable(format_file_size)
    assert callable(safe_json_loads)

    # Check that they have docstrings
    assert format_cache_stats.__doc__ is not None
    assert create_cache_table.__doc__ is not None
    assert validate_cache_config.__doc__ is not None
    assert get_cache_manager.__doc__ is not None
    assert get_account_cache_optimizer.__doc__ is not None
    assert format_file_size.__doc__ is not None
    assert safe_json_loads.__doc__ is not None
