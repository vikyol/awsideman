"""Tests for user get command."""

import pytest


def test_get_user_module_import():
    """Test that the get_user module can be imported."""
    try:
        from src.awsideman.commands.user.get import get_user

        assert get_user is not None
        assert callable(get_user)
    except ImportError as e:
        pytest.fail(f"Failed to import get_user: {e}")


def test_get_user_function_signature():
    """Test that the get_user function has the expected signature."""
    import inspect

    from src.awsideman.commands.user.get import get_user

    # Check that the function exists and is callable
    assert callable(get_user)

    # Check that it has the expected parameters
    sig = inspect.signature(get_user)
    expected_params = {"identifier", "profile"}

    actual_params = set(sig.parameters.keys())
    assert expected_params.issubset(
        actual_params
    ), f"Missing parameters: {expected_params - actual_params}"


def test_get_user_help_text():
    """Test that the get_user function has help text."""
    from src.awsideman.commands.user.get import get_user

    # Check that the function has a docstring
    assert get_user.__doc__ is not None
    assert len(get_user.__doc__.strip()) > 0

    # Check that the docstring contains expected content
    doc = get_user.__doc__.lower()
    assert "get" in doc
    assert "user" in doc
    assert "information" in doc


def test_get_user_typer_integration():
    """Test that the get_user function is properly integrated with Typer."""
    from src.awsideman.commands.user.get import get_user

    # Check that the function has the expected type hints
    assert hasattr(get_user, "__annotations__")

    annotations = get_user.__annotations__
    assert "identifier" in annotations
    assert "profile" in annotations


def test_get_user_parameter_types():
    """Test that the get_user function has correct parameter types."""
    import inspect

    from src.awsideman.commands.user.get import get_user

    sig = inspect.signature(get_user)

    # Check that identifier is a string
    assert sig.parameters["identifier"].annotation == str

    # Check that profile is optional string
    profile_param = sig.parameters["profile"]
    assert profile_param.annotation == str or "Optional" in str(profile_param.annotation)
