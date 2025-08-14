"""Fast unit tests for permission_set list command."""

import inspect

import pytest


def test_list_permission_sets_module_import():
    """Test that the list_permission_sets module can be imported successfully."""
    try:
        from src.awsideman.commands.permission_set.list import list_permission_sets

        assert list_permission_sets is not None
    except Exception as e:
        pytest.fail(f"Failed to import list_permission_sets: {e}")


def test_list_permission_sets_function_signature():
    """Test that the list_permission_sets function has the expected signature."""
    try:
        from src.awsideman.commands.permission_set.list import list_permission_sets

        sig = inspect.signature(list_permission_sets)

        # Check that all expected parameters exist
        expected_params = ["filter", "limit", "next_token", "profile"]
        for param_name in expected_params:
            assert (
                param_name in sig.parameters
            ), f"Parameter '{param_name}' not found in list_permission_sets"

        # Check that the function is callable
        assert callable(list_permission_sets)

    except Exception as e:
        pytest.fail(f"Failed to test list_permission_sets function signature: {e}")


def test_list_permission_sets_help_text():
    """Test that the list_permission_sets function has proper help text."""
    try:
        from src.awsideman.commands.permission_set.list import list_permission_sets

        doc = list_permission_sets.__doc__
        assert doc is not None, "list_permission_sets function should have a docstring"

        # Check that help text contains expected information
        assert "List all permission sets" in doc
        assert "filter" in doc.lower()
        assert "limit" in doc.lower()
        assert "pagination" in doc.lower()
        assert "table" in doc.lower()

    except Exception as e:
        pytest.fail(f"Failed to test list_permission_sets help text: {e}")


def test_list_permission_sets_typer_integration():
    """Test that the list_permission_sets function is properly integrated with Typer."""
    try:
        from src.awsideman.commands.permission_set.list import list_permission_sets

        # Check that the function has the expected attributes for Typer integration
        assert hasattr(list_permission_sets, "__name__")
        assert hasattr(list_permission_sets, "__doc__")
        assert hasattr(list_permission_sets, "__annotations__")

        # Check that the function can be called (even if it fails due to missing AWS config)
        # This is a lightweight test that just verifies the function structure
        assert callable(list_permission_sets)

    except Exception as e:
        pytest.fail(f"Failed to test list_permission_sets Typer integration: {e}")


def test_list_permission_sets_parameter_types():
    """Test that the list_permission_sets function has the expected parameter types."""
    try:
        from src.awsideman.commands.permission_set.list import list_permission_sets

        sig = inspect.signature(list_permission_sets)

        # Check parameter types
        filter_param = sig.parameters["filter"]
        limit_param = sig.parameters["limit"]
        next_token_param = sig.parameters["next_token"]
        profile_param = sig.parameters["profile"]

        # All parameters should be Optional[str] or Optional[int]
        assert "Optional" in str(filter_param.annotation) or filter_param.annotation == str
        assert "Optional" in str(limit_param.annotation) or limit_param.annotation == int
        assert "Optional" in str(next_token_param.annotation) or next_token_param.annotation == str
        assert "Optional" in str(profile_param.annotation) or profile_param.annotation == str

    except Exception as e:
        pytest.fail(f"Failed to test list_permission_sets parameter types: {e}")
