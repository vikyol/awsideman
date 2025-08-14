"""Tests for assignment revoke command."""

import pytest


def test_revoke_permission_set_module_import():
    """Test that the revoke_permission_set module can be imported."""
    try:
        from src.awsideman.commands.assignment.revoke import revoke_permission_set

        assert revoke_permission_set is not None
        assert callable(revoke_permission_set)
    except ImportError as e:
        pytest.fail(f"Failed to import revoke_permission_set: {e}")


def test_revoke_permission_set_function_signature():
    """Test that the revoke_permission_set function has the expected signature."""
    import inspect

    from src.awsideman.commands.assignment.revoke import revoke_permission_set

    # Check that the function exists and is callable
    assert callable(revoke_permission_set)

    # Check that it has the expected parameters
    sig = inspect.signature(revoke_permission_set)
    expected_params = {
        "permission_set_name",
        "principal_name",
        "account_id",
        "principal_type",
        "force",
        "profile",
    }

    actual_params = set(sig.parameters.keys())
    assert expected_params.issubset(
        actual_params
    ), f"Missing parameters: {expected_params - actual_params}"


def test_revoke_permission_set_help_text():
    """Test that the revoke_permission_set function has help text."""
    from src.awsideman.commands.assignment.revoke import revoke_permission_set

    # Check that the function has a docstring
    assert revoke_permission_set.__doc__ is not None
    assert len(revoke_permission_set.__doc__.strip()) > 0

    # Check that the docstring contains expected content
    doc = revoke_permission_set.__doc__.lower()
    assert "revoke" in doc
    assert "permission set" in doc
    assert "principal" in doc


def test_revoke_permission_set_typer_integration():
    """Test that the revoke_permission_set function is properly integrated with Typer."""
    from src.awsideman.commands.assignment.revoke import revoke_permission_set

    # Check that the function has the expected type hints
    assert hasattr(revoke_permission_set, "__annotations__")

    annotations = revoke_permission_set.__annotations__
    assert "permission_set_name" in annotations
    assert "principal_name" in annotations
    assert "account_id" in annotations
    assert "principal_type" in annotations
    assert "force" in annotations
    assert "profile" in annotations


def test_revoke_permission_set_parameter_types():
    """Test that the revoke_permission_set function has correct parameter types."""
    import inspect

    from src.awsideman.commands.assignment.revoke import revoke_permission_set

    sig = inspect.signature(revoke_permission_set)

    # Check that permission_set_name is a string
    assert sig.parameters["permission_set_name"].annotation == str

    # Check that principal_name is a string
    assert sig.parameters["principal_name"].annotation == str

    # Check that account_id is a string (or Optional[str])
    account_id_param = sig.parameters["account_id"]
    assert account_id_param.annotation == str or "Optional" in str(account_id_param.annotation)

    # Check that principal_type is optional string
    principal_type_param = sig.parameters["principal_type"]
    assert principal_type_param.annotation == str or "Optional" in str(
        principal_type_param.annotation
    )

    # Check that force is a boolean
    assert sig.parameters["force"].annotation == bool

    # Check that profile is optional string
    profile_param = sig.parameters["profile"]
    assert profile_param.annotation == str or "Optional" in str(profile_param.annotation)
