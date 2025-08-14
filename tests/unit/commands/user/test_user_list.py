"""Tests for user list command."""

import pytest


def test_list_users_module_import():
    """Test that the list_users module can be imported."""
    try:
        from src.awsideman.commands.user.list import list_users

        assert list_users is not None
        assert callable(list_users)
    except ImportError as e:
        pytest.fail(f"Failed to import list_users: {e}")


def test_list_users_function_signature():
    """Test that the list_users function has the expected signature."""
    import inspect

    from src.awsideman.commands.user.list import list_users

    # Check that the function exists and is callable
    assert callable(list_users)

    # Check that it has the expected parameters
    sig = inspect.signature(list_users)
    expected_params = {"filter", "limit", "next_token", "profile"}

    actual_params = set(sig.parameters.keys())
    assert expected_params.issubset(
        actual_params
    ), f"Missing parameters: {expected_params - actual_params}"


def test_list_users_help_text():
    """Test that the list_users function has help text."""
    from src.awsideman.commands.user.list import list_users

    # Check that the function has a docstring
    assert list_users.__doc__ is not None
    assert len(list_users.__doc__.strip()) > 0

    # Check that the docstring contains expected content
    doc = list_users.__doc__.lower()
    assert "list" in doc
    assert "users" in doc
    assert "identity store" in doc


def test_list_users_typer_integration():
    """Test that the list_users function is properly integrated with Typer."""
    from src.awsideman.commands.user.list import list_users

    # Check that the function has the expected type hints
    assert hasattr(list_users, "__annotations__")

    annotations = list_users.__annotations__
    assert "filter" in annotations
    assert "limit" in annotations
    assert "next_token" in annotations
    assert "profile" in annotations


def test_list_users_parameter_types():
    """Test that the list_users function has correct parameter types."""
    import inspect

    from src.awsideman.commands.user.list import list_users

    sig = inspect.signature(list_users)

    # Check that filter is optional string
    filter_param = sig.parameters["filter"]
    assert filter_param.annotation == str or "Optional" in str(filter_param.annotation)

    # Check that limit is optional int
    limit_param = sig.parameters["limit"]
    assert limit_param.annotation == int or "Optional" in str(limit_param.annotation)

    # Check that next_token is optional string
    next_token_param = sig.parameters["next_token"]
    assert next_token_param.annotation == str or "Optional" in str(next_token_param.annotation)

    # Check that profile is optional string
    profile_param = sig.parameters["profile"]
    assert profile_param.annotation == str or "Optional" in str(profile_param.annotation)
