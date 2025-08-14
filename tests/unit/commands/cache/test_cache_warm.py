"""Tests for cache warm command."""

import pytest


def test_warm_cache_module_import():
    """Test that the warm_cache module can be imported."""
    try:
        from src.awsideman.commands.cache.warm import warm_cache

        assert warm_cache is not None
        assert callable(warm_cache)
    except ImportError as e:
        pytest.fail(f"Failed to import warm_cache: {e}")


def test_warm_cache_function_signature():
    """Test that the warm_cache function has the expected signature."""
    import inspect

    from src.awsideman.commands.cache.warm import warm_cache

    # Check that the function exists and is callable
    assert callable(warm_cache)

    # Check that it has the expected parameters
    sig = inspect.signature(warm_cache)
    expected_params = {"command", "profile", "region"}

    actual_params = set(sig.parameters.keys())
    assert expected_params.issubset(
        actual_params
    ), f"Missing parameters: {expected_params - actual_params}"


def test_warm_cache_help_text():
    """Test that the warm_cache function has help text."""
    from src.awsideman.commands.cache.warm import warm_cache

    # Check that the function has a docstring
    assert warm_cache.__doc__ is not None
    assert len(warm_cache.__doc__.strip()) > 0

    # Check that the docstring contains expected content
    doc = warm_cache.__doc__.lower()
    assert "warm" in doc
    assert "cache" in doc
    assert "command" in doc


def test_warm_cache_typer_integration():
    """Test that the warm_cache function is properly integrated with Typer."""
    from src.awsideman.commands.cache.warm import warm_cache

    # Check that the function has the expected type hints
    assert hasattr(warm_cache, "__annotations__")

    annotations = warm_cache.__annotations__
    assert "command" in annotations
    assert "profile" in annotations
    assert "region" in annotations


def test_warm_cache_parameter_types():
    """Test that the warm_cache function has correct parameter types."""
    import inspect

    from src.awsideman.commands.cache.warm import warm_cache

    sig = inspect.signature(warm_cache)

    # Check that command is a string
    assert sig.parameters["command"].annotation == str

    # Check that profile is optional string
    profile_param = sig.parameters["profile"]
    assert profile_param.annotation == str or "Optional" in str(profile_param.annotation)

    # Check that region is optional string
    region_param = sig.parameters["region"]
    assert region_param.annotation == str or "Optional" in str(region_param.annotation)
