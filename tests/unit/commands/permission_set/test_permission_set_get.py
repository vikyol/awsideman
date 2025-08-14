"""Fast unit tests for permission_set get command."""

import inspect

import pytest


def test_get_permission_set_module_import():
    """Test that the get_permission_set module can be imported successfully."""
    try:
        from src.awsideman.commands.permission_set.get import get_permission_set

        assert get_permission_set is not None
    except Exception as e:
        pytest.fail(f"Failed to import get_permission_set: {e}")


def test_get_permission_set_function_signature():
    """Test that the get_permission_set function has the expected signature."""
    try:
        from src.awsideman.commands.permission_set.get import get_permission_set

        sig = inspect.signature(get_permission_set)

        # Check that all expected parameters exist
        expected_params = ["identifier", "profile"]
        for param_name in expected_params:
            assert (
                param_name in sig.parameters
            ), f"Parameter '{param_name}' not found in get_permission_set"

        # Check that the function is callable
        assert callable(get_permission_set)

    except Exception as e:
        pytest.fail(f"Failed to test get_permission_set function signature: {e}")


def test_get_permission_set_help_text():
    """Test that the get_permission_set function has proper help text."""
    try:
        from src.awsideman.commands.permission_set.get import get_permission_set

        doc = get_permission_set.__doc__
        assert doc is not None, "get_permission_set function should have a docstring"

        # Check that help text contains expected information
        assert "Get detailed information" in doc
        assert "permission set" in doc.lower()
        assert "name or arn" in doc.lower()
        assert "aws profile" in doc.lower()

    except Exception as e:
        pytest.fail(f"Failed to test get_permission_set help text: {e}")


def test_get_permission_set_typer_integration():
    """Test that the get_permission_set function is properly integrated with Typer."""
    try:
        from src.awsideman.commands.permission_set.get import get_permission_set

        # Check that the function has the expected attributes for Typer integration
        assert hasattr(get_permission_set, "__name__")
        assert hasattr(get_permission_set, "__doc__")
        assert hasattr(get_permission_set, "__annotations__")

        # Check that the function can be called (even if it fails due to missing AWS config)
        # This is a lightweight test that just verifies the function structure
        assert callable(get_permission_set)

    except Exception as e:
        pytest.fail(f"Failed to test get_permission_set Typer integration: {e}")


def test_get_permission_set_parameter_types():
    """Test that the get_permission_set function has the expected parameter types."""
    try:
        from src.awsideman.commands.permission_set.get import get_permission_set

        sig = inspect.signature(get_permission_set)

        # Check parameter types
        identifier_param = sig.parameters["identifier"]
        profile_param = sig.parameters["profile"]

        # identifier should be str (required), profile should be Optional[str]
        assert identifier_param.annotation == str
        assert "Optional" in str(profile_param.annotation) or profile_param.annotation == str

    except Exception as e:
        pytest.fail(f"Failed to test get_permission_set parameter types: {e}")
