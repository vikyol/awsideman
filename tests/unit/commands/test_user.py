"""Simplified tests for user module structure."""

import pytest


def test_user_module_import():
    """Test that the user module can be imported."""
    try:
        from src.awsideman.commands.user import app

        assert app is not None
        assert hasattr(app, "command")
    except ImportError as e:
        pytest.fail(f"Failed to import user module: {e}")


def test_user_app_commands():
    """Test that the user app has the expected commands."""
    from src.awsideman.commands.user import app

    # Get all registered commands
    commands = [cmd.name for cmd in app.registered_commands]

    # Check that all expected commands are present
    expected_commands = ["list", "get", "create", "update", "delete"]
    for cmd in expected_commands:
        assert cmd in commands, f"Command '{cmd}' not found in user app"


def test_user_module_structure():
    """Test that the user module structure is correct."""
    try:
        # Test that all submodules can be imported
        from src.awsideman.commands.user import create, delete, get, helpers, list, update

        # Check that main functions exist
        assert hasattr(list, "list_users")
        assert hasattr(get, "get_user")
        assert hasattr(create, "create_user")
        assert hasattr(update, "update_user")
        assert hasattr(delete, "delete_user")
        assert hasattr(helpers, "console")
        assert hasattr(helpers, "config")

    except ImportError as e:
        pytest.fail(f"Failed to import user submodules: {e}")


def test_user_commands_help_text():
    """Test that all user commands have help text."""
    from src.awsideman.commands.user import create, delete, get, list, update

    # Check that all commands have docstrings
    assert list.list_users.__doc__ is not None
    assert get.get_user.__doc__ is not None
    assert create.create_user.__doc__ is not None
    assert update.update_user.__doc__ is not None
    assert delete.delete_user.__doc__ is not None

    # Check that docstrings contain expected content
    assert "list" in list.list_users.__doc__.lower()
    assert "get" in get.get_user.__doc__.lower()
    assert "create" in create.create_user.__doc__.lower()
    assert "update" in update.update_user.__doc__.lower()
    assert "delete" in delete.delete_user.__doc__.lower()


def test_user_helpers_functions():
    """Test that user helpers module has expected functions."""
    from src.awsideman.commands.user.helpers import (
        format_user_for_display,
        get_single_key,
        validate_email_format,
        validate_profile,
        validate_sso_instance,
        validate_username_format,
    )

    # Check that all helper functions exist and are callable
    assert callable(get_single_key)
    assert callable(validate_profile)
    assert callable(validate_sso_instance)
    assert callable(format_user_for_display)
    assert callable(validate_email_format)
    assert callable(validate_username_format)

    # Check that they have docstrings
    assert get_single_key.__doc__ is not None
    assert validate_profile.__doc__ is not None
    assert validate_sso_instance.__doc__ is not None
    assert format_user_for_display.__doc__ is not None
    assert validate_email_format.__doc__ is not None
    assert validate_username_format.__doc__ is not None
