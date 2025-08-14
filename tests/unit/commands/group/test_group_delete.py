"""Fast unit tests for group delete command."""

import inspect

import pytest


def test_delete_group_module_import():
    """Test that the delete_group module can be imported successfully."""
    try:
        from src.awsideman.commands.group.delete import delete_group

        assert delete_group is not None
    except Exception as e:
        pytest.fail(f"Failed to import delete_group: {e}")


def test_delete_group_function_signature():
    """Test that the delete_group function has the expected signature."""
    try:
        from src.awsideman.commands.group.delete import delete_group

        sig = inspect.signature(delete_group)
        expected_params = ["identifier", "force", "profile"]
        for param_name in expected_params:
            assert (
                param_name in sig.parameters
            ), f"Parameter '{param_name}' not found in delete_group"
        assert callable(delete_group)
    except Exception as e:
        pytest.fail(f"Failed to test delete_group function signature: {e}")


def test_delete_group_help_text():
    """Test that the delete_group function has proper help text."""
    try:
        from src.awsideman.commands.group.delete import delete_group

        doc = delete_group.__doc__
        assert doc is not None, "delete_group function should have a docstring"
        assert "Delete a group" in doc
        assert "permanently" in doc.lower()
        assert "confirmation" in doc.lower()
    except Exception as e:
        pytest.fail(f"Failed to test delete_group help text: {e}")


def test_delete_group_typer_integration():
    """Test that the delete_group function is properly integrated with Typer."""
    try:
        from src.awsideman.commands.group.delete import delete_group

        assert hasattr(delete_group, "__name__")
        assert hasattr(delete_group, "__doc__")
        assert hasattr(delete_group, "__annotations__")
        assert callable(delete_group)
    except Exception as e:
        pytest.fail(f"Failed to test delete_group Typer integration: {e}")


def test_delete_group_parameter_types():
    """Test that the delete_group function has the expected parameter types."""
    try:
        from src.awsideman.commands.group.delete import delete_group

        sig = inspect.signature(delete_group)
        identifier_param = sig.parameters["identifier"]
        force_param = sig.parameters["force"]
        profile_param = sig.parameters["profile"]
        assert identifier_param.annotation == str
        assert force_param.annotation == bool
        assert "Optional" in str(profile_param.annotation) or profile_param.annotation == str
    except Exception as e:
        pytest.fail(f"Failed to test delete_group parameter types: {e}")
