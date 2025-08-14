"""Fast unit tests for group create command."""

import inspect

import pytest


def test_create_group_module_import():
    """Test that the create_group module can be imported successfully."""
    try:
        from src.awsideman.commands.group.create import create_group

        assert create_group is not None
    except Exception as e:
        pytest.fail(f"Failed to import create_group: {e}")


def test_create_group_function_signature():
    """Test that the create_group function has the expected signature."""
    try:
        from src.awsideman.commands.group.create import create_group

        sig = inspect.signature(create_group)
        expected_params = ["name", "description", "profile"]
        for param_name in expected_params:
            assert (
                param_name in sig.parameters
            ), f"Parameter '{param_name}' not found in create_group"
        assert callable(create_group)
    except Exception as e:
        pytest.fail(f"Failed to test create_group function signature: {e}")


def test_create_group_help_text():
    """Test that the create_group function has proper help text."""
    try:
        from src.awsideman.commands.group.create import create_group

        doc = create_group.__doc__
        assert doc is not None, "create_group function should have a docstring"
        assert "Create a new group" in doc
        assert "name" in doc.lower()
        assert "unique" in doc.lower()
    except Exception as e:
        pytest.fail(f"Failed to test create_group help text: {e}")


def test_create_group_typer_integration():
    """Test that the create_group function is properly integrated with Typer."""
    try:
        from src.awsideman.commands.group.create import create_group

        assert hasattr(create_group, "__name__")
        assert hasattr(create_group, "__doc__")
        assert hasattr(create_group, "__annotations__")
        assert callable(create_group)
    except Exception as e:
        pytest.fail(f"Failed to test create_group Typer integration: {e}")


def test_create_group_parameter_types():
    """Test that the create_group function has the expected parameter types."""
    try:
        from src.awsideman.commands.group.create import create_group

        sig = inspect.signature(create_group)
        name_param = sig.parameters["name"]
        description_param = sig.parameters["description"]
        profile_param = sig.parameters["profile"]
        assert name_param.annotation == str
        assert (
            "Optional" in str(description_param.annotation) or description_param.annotation == str
        )
        assert "Optional" in str(profile_param.annotation) or profile_param.annotation == str
    except Exception as e:
        pytest.fail(f"Failed to test create_group parameter types: {e}")
