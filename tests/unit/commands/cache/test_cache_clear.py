"""Tests for cache clear command."""

import pytest


def test_clear_cache_module_import():
    """Test that the clear_cache module can be imported."""
    try:
        from src.awsideman.commands.cache.clear import clear_cache

        assert clear_cache is not None
        assert callable(clear_cache)
    except ImportError as e:
        pytest.fail(f"Failed to import clear_cache: {e}")


def test_clear_cache_function_signature():
    """Test that the clear_cache function has the expected signature."""
    import inspect

    from src.awsideman.commands.cache.clear import clear_cache

    # Check that the function exists and is callable
    assert callable(clear_cache)

    # Check that it has the expected parameters
    sig = inspect.signature(clear_cache)
    expected_params = {"force", "accounts_only", "profile"}

    actual_params = set(sig.parameters.keys())
    assert expected_params.issubset(
        actual_params
    ), f"Missing parameters: {expected_params - actual_params}"


def test_clear_cache_help_text():
    """Test that the clear_cache function has help text."""
    from src.awsideman.commands.cache.clear import clear_cache

    # Check that the function has a docstring
    assert clear_cache.__doc__ is not None
    assert len(clear_cache.__doc__.strip()) > 0

    # Check that the docstring contains expected content
    doc = clear_cache.__doc__.lower()
    assert "clear" in doc
    assert "cache" in doc
    assert "data" in doc


def test_clear_cache_typer_integration():
    """Test that the clear_cache function is properly integrated with Typer."""
    from src.awsideman.commands.cache.clear import clear_cache

    # Check that the function has the expected type hints
    assert hasattr(clear_cache, "__annotations__")

    annotations = clear_cache.__annotations__
    assert "force" in annotations
    assert "accounts_only" in annotations
    assert "profile" in annotations


def test_clear_cache_parameter_types():
    """Test that the clear_cache function has correct parameter types."""
    import inspect

    from src.awsideman.commands.cache.clear import clear_cache

    sig = inspect.signature(clear_cache)

    # Check that force is a boolean
    assert sig.parameters["force"].annotation == bool

    # Check that accounts_only is a boolean
    assert sig.parameters["accounts_only"].annotation == bool

    # Check that profile is optional string
    profile_param = sig.parameters["profile"]
    assert profile_param.annotation == str or "Optional" in str(profile_param.annotation)
