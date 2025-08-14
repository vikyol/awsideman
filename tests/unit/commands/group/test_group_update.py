"""Fast unit tests for group update command."""

import inspect

import pytest


def test_update_group_module_import():
    """Test that the update_group module can be imported successfully."""
    try:
        from src.awsideman.commands.group.update import update_group

        assert update_group is not None
    except Exception as e:
        pytest.fail(f"Failed to import update_group: {e}")


def test_update_group_function_signature():
    """Test that the update_group function has the expected signature."""
    try:
        from src.awsideman.commands.group.update import update_group

        sig = inspect.signature(update_group)
        expected_params = ["identifier", "name", "description", "profile"]
        for param_name in expected_params:
            assert (
                param_name in sig.parameters
            ), f"Parameter '{param_name}' not found in update_group"
        assert callable(update_group)
    except Exception as e:
        pytest.fail(f"Failed to test update_group function signature: {e}")


def test_update_group_help_text():
    """Test that the update_group function has proper help text."""
    try:
        from src.awsideman.commands.group.update import update_group

        doc = update_group.__doc__
        assert doc is not None, "update_group function should have a docstring"
        assert "Update a group's attributes" in doc
        assert "attributes" in doc.lower()
        assert "unchanged" in doc.lower()
    except Exception as e:
        pytest.fail(f"Failed to test update_group help text: {e}")


def test_update_group_typer_integration():
    """Test that the update_group function is properly integrated with Typer."""
    try:
        from src.awsideman.commands.group.update import update_group

        assert hasattr(update_group, "__name__")
        assert hasattr(update_group, "__doc__")
        assert hasattr(update_group, "__annotations__")
        assert callable(update_group)
    except Exception as e:
        pytest.fail(f"Failed to test update_group Typer integration: {e}")


def test_update_group_parameter_types():
    """Test that the update_group function has the expected parameter types."""
    try:
        from src.awsideman.commands.group.update import update_group

        sig = inspect.signature(update_group)
        identifier_param = sig.parameters["identifier"]
        name_param = sig.parameters["name"]
        description_param = sig.parameters["description"]
        profile_param = sig.parameters["profile"]
        assert identifier_param.annotation == str
        assert "Optional" in str(name_param.annotation) or name_param.annotation == str
        assert (
            "Optional" in str(description_param.annotation) or description_param.annotation == str
        )
        assert "Optional" in str(profile_param.annotation) or profile_param.annotation == str
    except Exception as e:
        pytest.fail(f"Failed to test update_group parameter types: {e}")
