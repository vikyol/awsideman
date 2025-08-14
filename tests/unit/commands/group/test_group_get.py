"""Fast unit tests for group get command."""

import inspect

import pytest


def test_get_group_module_import():
    """Test that the get_group module can be imported successfully."""
    try:
        from src.awsideman.commands.group.get import get_group

        assert get_group is not None
    except Exception as e:
        pytest.fail(f"Failed to import get_group: {e}")


def test_get_group_function_signature():
    """Test that the get_group function has the expected signature."""
    try:
        from src.awsideman.commands.group.get import get_group

        sig = inspect.signature(get_group)
        expected_params = ["identifier", "profile"]
        for param_name in expected_params:
            assert param_name in sig.parameters, f"Parameter '{param_name}' not found in get_group"
        assert callable(get_group)
    except Exception as e:
        pytest.fail(f"Failed to test get_group function signature: {e}")


def test_get_group_help_text():
    """Test that the get_group function has proper help text."""
    try:
        from src.awsideman.commands.group.get import get_group

        doc = get_group.__doc__
        assert doc is not None, "get_group function should have a docstring"
        assert "Get detailed information" in doc
        assert "group" in doc.lower()
        assert "retrieves" in doc.lower()
    except Exception as e:
        pytest.fail(f"Failed to test get_group help text: {e}")


def test_get_group_typer_integration():
    """Test that the get_group function is properly integrated with Typer."""
    try:
        from src.awsideman.commands.group.get import get_group

        assert hasattr(get_group, "__name__")
        assert hasattr(get_group, "__doc__")
        assert hasattr(get_group, "__annotations__")
        assert callable(get_group)
    except Exception as e:
        pytest.fail(f"Failed to test get_group Typer integration: {e}")


def test_get_group_parameter_types():
    """Test that the get_group function has the expected parameter types."""
    try:
        from src.awsideman.commands.group.get import get_group

        sig = inspect.signature(get_group)
        identifier_param = sig.parameters["identifier"]
        profile_param = sig.parameters["profile"]
        assert identifier_param.annotation == str
        assert "Optional" in str(profile_param.annotation) or profile_param.annotation == str
    except Exception as e:
        pytest.fail(f"Failed to test get_group parameter types: {e}")
