"""Tests for assignment get command."""

import pytest


def test_get_assignment_module_import():
    """Test that the get_assignment module can be imported."""
    try:
        from src.awsideman.commands.assignment.get import get_assignment

        assert get_assignment is not None
        assert callable(get_assignment)
    except ImportError as e:
        pytest.fail(f"Failed to import get_assignment: {e}")


def test_get_assignment_function_signature():
    """Test that the get_assignment function has the expected signature."""
    import inspect

    from src.awsideman.commands.assignment.get import get_assignment

    # Check that the function exists and is callable
    assert callable(get_assignment)

    # Check that it has the expected parameters
    sig = inspect.signature(get_assignment)
    expected_params = {"permission_set_arn", "principal_id", "account_id", "profile"}

    actual_params = set(sig.parameters.keys())
    assert expected_params.issubset(
        actual_params
    ), f"Missing parameters: {expected_params - actual_params}"


def test_get_assignment_help_text():
    """Test that the get_assignment function has help text."""
    from src.awsideman.commands.assignment.get import get_assignment

    # Check that the function has a docstring
    assert get_assignment.__doc__ is not None
    assert len(get_assignment.__doc__.strip()) > 0

    # Check that the docstring contains expected content
    doc = get_assignment.__doc__.lower()
    assert "get" in doc
    assert "assignment" in doc
    assert "permission set" in doc


def test_get_assignment_typer_integration():
    """Test that the get_assignment function is properly integrated with Typer."""
    from src.awsideman.commands.assignment.get import get_assignment

    # Check that the function has the expected type hints
    assert hasattr(get_assignment, "__annotations__")

    annotations = get_assignment.__annotations__
    assert "permission_set_arn" in annotations
    assert "principal_id" in annotations
    assert "account_id" in annotations
    assert "profile" in annotations


def test_get_assignment_parameter_types():
    """Test that the get_assignment function has correct parameter types."""
    import inspect

    from src.awsideman.commands.assignment.get import get_assignment

    sig = inspect.signature(get_assignment)

    # Check that permission_set_arn is a string
    assert sig.parameters["permission_set_arn"].annotation == str

    # Check that principal_id is a string
    assert sig.parameters["principal_id"].annotation == str

    # Check that account_id is a string
    assert sig.parameters["account_id"].annotation == str

    # Check that profile is optional string
    profile_param = sig.parameters["profile"]
    assert profile_param.annotation == str or "Optional" in str(profile_param.annotation)
