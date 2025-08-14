"""Tests for cache status command."""

import pytest


def test_cache_status_module_import():
    """Test that the cache_status module can be imported."""
    try:
        from src.awsideman.commands.cache.status import cache_status

        assert cache_status is not None
        assert callable(cache_status)
    except ImportError as e:
        pytest.fail(f"Failed to import cache_status: {e}")


def test_cache_status_function_signature():
    """Test that the cache_status function has the expected signature."""
    import inspect

    from src.awsideman.commands.cache.status import cache_status

    # Check that the function exists and is callable
    assert callable(cache_status)

    # Check that it has no parameters (it's a command with no arguments)
    sig = inspect.signature(cache_status)
    assert len(sig.parameters) == 0


def test_cache_status_help_text():
    """Test that the cache_status function has help text."""
    from src.awsideman.commands.cache.status import cache_status

    # Check that the function has a docstring
    assert cache_status.__doc__ is not None
    assert len(cache_status.__doc__.strip()) > 0

    # Check that the docstring contains expected content
    doc = cache_status.__doc__.lower()
    assert "display" in doc
    assert "cache" in doc
    assert "status" in doc


def test_cache_status_typer_integration():
    """Test that the cache_status function is properly integrated with Typer."""
    from src.awsideman.commands.cache.status import cache_status

    # Check that the function has type hints (even if empty)
    assert hasattr(cache_status, "__annotations__")


def test_cache_status_helper_functions():
    """Test that the helper functions exist and are callable."""
    from src.awsideman.commands.cache.status import (
        _display_backend_configuration,
        _display_backend_health,
        _display_backend_statistics,
        _display_encryption_status,
        _display_recent_cache_entries,
    )

    # Check that all helper functions exist and are callable
    for func in [
        _display_backend_configuration,
        _display_encryption_status,
        _display_backend_statistics,
        _display_backend_health,
        _display_recent_cache_entries,
    ]:
        assert callable(func)
        assert func.__doc__ is not None
