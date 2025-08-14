"""Tests for assignment assign command."""

import pytest


def test_assign_permission_set_module_import():
    """Test that the assign_permission_set module can be imported."""
    try:
        from src.awsideman.commands.assignment.assign import assign_permission_set

        assert assign_permission_set is not None
        assert callable(assign_permission_set)
    except ImportError as e:
        pytest.fail(f"Failed to import assign_permission_set: {e}")


def test_assign_single_account_module_import():
    """Test that the assign_single_account module can be imported."""
    try:
        from src.awsideman.commands.assignment.assign import assign_single_account

        assert assign_single_account is not None
        assert callable(assign_single_account)
    except ImportError as e:
        pytest.fail(f"Failed to import assign_single_account: {e}")


def test_assign_multi_account_advanced_module_import():
    """Test that the assign_multi_account_advanced module can be imported."""
    try:
        from src.awsideman.commands.assignment.assign import assign_multi_account_advanced

        assert assign_multi_account_advanced is not None
        assert callable(assign_multi_account_advanced)
    except ImportError as e:
        pytest.fail(f"Failed to import assign_multi_account_advanced: {e}")


def test_assign_multi_account_explicit_module_import():
    """Test that the assign_multi_account_explicit module can be imported."""
    try:
        from src.awsideman.commands.assignment.assign import assign_multi_account_explicit

        assert assign_multi_account_explicit is not None
        assert callable(assign_multi_account_explicit)
    except ImportError as e:
        pytest.fail(f"Failed to import assign_multi_account_explicit: {e}")


def test_assign_permission_set_function_signature():
    """Test that the assign_permission_set function has the expected signature."""
    import inspect

    from src.awsideman.commands.assignment.assign import assign_permission_set

    # Check that the function exists and is callable
    assert callable(assign_permission_set)

    # Check that it has the expected parameters
    sig = inspect.signature(assign_permission_set)
    expected_params = {
        "permission_set_name",
        "principal_name",
        "account_id",
        "principal_type",
        "profile",
    }

    actual_params = set(sig.parameters.keys())
    assert expected_params.issubset(
        actual_params
    ), f"Missing parameters: {expected_params - actual_params}"


def test_assign_single_account_function_signature():
    """Test that the assign_single_account function has the expected signature."""
    import inspect

    from src.awsideman.commands.assignment.assign import assign_single_account

    # Check that the function exists and is callable
    assert callable(assign_single_account)

    # Check that it has the expected parameters
    sig = inspect.signature(assign_single_account)
    expected_params = {
        "permission_set_name",
        "principal_name",
        "account_id",
        "principal_type",
        "profile",
    }

    actual_params = set(sig.parameters.keys())
    assert expected_params.issubset(
        actual_params
    ), f"Missing parameters: {expected_params - actual_params}"


def test_assign_multi_account_advanced_function_signature():
    """Test that the assign_multi_account_advanced function has the expected signature."""
    import inspect

    from src.awsideman.commands.assignment.assign import assign_multi_account_advanced

    # Check that the function exists and is callable
    assert callable(assign_multi_account_advanced)

    # Check that it has the expected parameters
    sig = inspect.signature(assign_multi_account_advanced)
    expected_params = {
        "permission_set_name",
        "principal_name",
        "ou_filter",
        "account_pattern",
        "principal_type",
        "dry_run",
        "batch_size",
        "continue_on_error",
        "profile",
    }

    actual_params = set(sig.parameters.keys())
    assert expected_params.issubset(
        actual_params
    ), f"Missing parameters: {expected_params - actual_params}"


def test_assign_multi_account_explicit_function_signature():
    """Test that the assign_multi_account_explicit function has the expected signature."""
    import inspect

    from src.awsideman.commands.assignment.assign import assign_multi_account_explicit

    # Check that the function exists and is callable
    assert callable(assign_multi_account_explicit)

    # Check that it has the expected parameters
    sig = inspect.signature(assign_multi_account_explicit)
    expected_params = {
        "permission_set_name",
        "principal_name",
        "account_list",
        "principal_type",
        "dry_run",
        "batch_size",
        "continue_on_error",
        "profile",
    }

    actual_params = set(sig.parameters.keys())
    assert expected_params.issubset(
        actual_params
    ), f"Missing parameters: {expected_params - actual_params}"


def test_assign_functions_help_text():
    """Test that the assign functions have help text."""
    from src.awsideman.commands.assignment.assign import (
        assign_multi_account_advanced,
        assign_multi_account_explicit,
        assign_permission_set,
        assign_single_account,
    )

    # Check that all functions have docstrings
    for func in [
        assign_permission_set,
        assign_single_account,
        assign_multi_account_advanced,
        assign_multi_account_explicit,
    ]:
        assert func.__doc__ is not None
        assert len(func.__doc__.strip()) > 0

        # Check that the docstring contains expected content
        doc = func.__doc__.lower()
        assert "assign" in doc
        assert "permission set" in doc


def test_assign_functions_typer_integration():
    """Test that the assign functions are properly integrated with Typer."""
    from src.awsideman.commands.assignment.assign import (
        assign_multi_account_advanced,
        assign_multi_account_explicit,
        assign_permission_set,
        assign_single_account,
    )

    # Check that all functions have type hints
    for func in [
        assign_permission_set,
        assign_single_account,
        assign_multi_account_advanced,
        assign_multi_account_explicit,
    ]:
        assert hasattr(func, "__annotations__")
        assert len(func.__annotations__) > 0
