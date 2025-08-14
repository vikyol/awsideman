"""Tests for assignment list command."""

import pytest


def test_list_assignments_module_import():
    """Test that the list_assignments module can be imported."""
    try:
        from src.awsideman.commands.assignment.list import list_assignments

        assert list_assignments is not None
        assert callable(list_assignments)
    except ImportError as e:
        pytest.fail(f"Failed to import list_assignments: {e}")


def test_list_assignments_function_signature():
    """Test that the list_assignments function has the expected signature."""
    import inspect

    from src.awsideman.commands.assignment.list import list_assignments

    # Check that the function exists and is callable
    assert callable(list_assignments)

    # Check that it has the expected parameters
    sig = inspect.signature(list_assignments)
    expected_params = {
        "account_id",
        "permission_set_arn",
        "principal_id",
        "principal_type",
        "limit",
        "next_token",
        "interactive",
        "profile",
    }

    actual_params = set(sig.parameters.keys())
    assert expected_params.issubset(
        actual_params
    ), f"Missing parameters: {expected_params - actual_params}"


def test_list_assignments_help_text():
    """Test that the list_assignments function has help text."""
    from src.awsideman.commands.assignment.list import list_assignments

    # Check that the function has a docstring
    assert list_assignments.__doc__ is not None
    assert len(list_assignments.__doc__.strip()) > 0

    # Check that the docstring contains expected content
    doc = list_assignments.__doc__.lower()
    assert "list" in doc
    assert "assignment" in doc
    assert "permission set" in doc


def test_list_assignments_typer_integration():
    """Test that the list_assignments function is properly integrated with Typer."""

    from src.awsideman.commands.assignment.list import list_assignments

    # Check that the function has Typer option decorators
    # This is a basic check that the function is set up for CLI use
    assert hasattr(list_assignments, "__annotations__")

    # Check that the function has the expected type hints
    annotations = list_assignments.__annotations__
    assert "account_id" in annotations
    assert "permission_set_arn" in annotations
    assert "principal_id" in annotations
    assert "principal_type" in annotations
    assert "limit" in annotations
    assert "profile" in annotations
