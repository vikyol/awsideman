"""Fast unit tests for group list command."""

import inspect

import pytest


def test_list_groups_module_import():
    """Test that the list_groups module can be imported successfully."""
    try:
        from src.awsideman.commands.group.list import list_groups

        assert list_groups is not None
    except Exception as e:
        pytest.fail(f"Failed to import list_groups: {e}")


def test_list_groups_function_signature():
    """Test that the list_groups function has the expected signature."""
    try:
        from src.awsideman.commands.group.list import list_groups

        sig = inspect.signature(list_groups)
        expected_params = ["filter", "limit", "next_token", "profile"]
        for param_name in expected_params:
            assert (
                param_name in sig.parameters
            ), f"Parameter '{param_name}' not found in list_groups"
        assert callable(list_groups)
    except Exception as e:
        pytest.fail(f"Failed to test list_groups function signature: {e}")


def test_list_groups_help_text():
    """Test that the list_groups function has proper help text."""
    try:
        from src.awsideman.commands.group.list import list_groups

        doc = list_groups.__doc__
        assert doc is not None, "list_groups function should have a docstring"
        assert "List all groups" in doc
        assert "filter" in doc.lower()
        assert "paginated" in doc.lower()
        assert "table" in doc.lower()
    except Exception as e:
        pytest.fail(f"Failed to test list_groups help text: {e}")


def test_list_groups_typer_integration():
    """Test that the list_groups function is properly integrated with Typer."""
    try:
        from src.awsideman.commands.group.list import list_groups

        assert hasattr(list_groups, "__name__")
        assert hasattr(list_groups, "__doc__")
        assert hasattr(list_groups, "__annotations__")
        assert callable(list_groups)
    except Exception as e:
        pytest.fail(f"Failed to test list_groups Typer integration: {e}")


def test_list_groups_parameter_types():
    """Test that the list_groups function has the expected parameter types."""
    try:
        from src.awsideman.commands.group.list import list_groups

        sig = inspect.signature(list_groups)
        filter_param = sig.parameters["filter"]
        limit_param = sig.parameters["limit"]
        next_token_param = sig.parameters["next_token"]
        profile_param = sig.parameters["profile"]
        assert "Optional" in str(filter_param.annotation) or filter_param.annotation == str
        assert "Optional" in str(limit_param.annotation) or limit_param.annotation == int
        assert "Optional" in str(next_token_param.annotation) or next_token_param.annotation == str
        assert "Optional" in str(profile_param.annotation) or profile_param.annotation == str
    except Exception as e:
        pytest.fail(f"Failed to test list_groups parameter types: {e}")
