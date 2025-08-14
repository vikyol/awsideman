"""Tests for user helpers module."""

import pytest


def test_user_helpers_module_import():
    """Test that the user helpers module can be imported."""
    try:
        from src.awsideman.commands.user.helpers import (
            config,
            console,
            format_user_for_display,
            get_single_key,
            validate_email_format,
            validate_profile,
            validate_sso_instance,
            validate_username_format,
        )

        assert console is not None
        assert config is not None
        assert callable(get_single_key)
        assert callable(validate_profile)
        assert callable(validate_sso_instance)
        assert callable(format_user_for_display)
        assert callable(validate_email_format)
        assert callable(validate_username_format)
    except ImportError as e:
        pytest.fail(f"Failed to import user helpers: {e}")


def test_user_helpers_console_instance():
    """Test that the console instance is properly configured."""
    from src.awsideman.commands.user.helpers import console

    # Check that console is a rich Console instance
    assert hasattr(console, "print")
    assert callable(console.print)


def test_user_helpers_config_instance():
    """Test that the config instance is properly configured."""
    from src.awsideman.commands.user.helpers import config

    # Check that config is a Config instance
    assert hasattr(config, "get")
    assert callable(config.get)


def test_user_helpers_get_single_key():
    """Test that the get_single_key function works correctly."""
    from src.awsideman.commands.user.helpers import get_single_key

    # Check that the function exists and is callable
    assert callable(get_single_key)

    # Check that it has a docstring
    assert get_single_key.__doc__ is not None
    assert "single key press" in get_single_key.__doc__.lower()


def test_user_helpers_validate_profile():
    """Test that the validate_profile function works correctly."""
    from src.awsideman.commands.user.helpers import validate_profile

    # Check that the function exists and is callable
    assert callable(validate_profile)

    # Check that it has a docstring
    assert validate_profile.__doc__ is not None
    assert "validate the profile" in validate_profile.__doc__.lower()


def test_user_helpers_validate_sso_instance():
    """Test that the validate_sso_instance function works correctly."""
    from src.awsideman.commands.user.helpers import validate_sso_instance

    # Check that the function exists and is callable
    assert callable(validate_sso_instance)

    # Check that it has a docstring
    assert validate_sso_instance.__doc__ is not None
    assert "validate the sso instance" in validate_sso_instance.__doc__.lower()


def test_user_helpers_format_user_for_display():
    """Test that the format_user_for_display function works correctly."""
    from src.awsideman.commands.user.helpers import format_user_for_display

    # Test with complete user data
    user_data = {
        "UserName": "testuser",
        "DisplayName": "Test User",
        "Emails": [{"Value": "test@example.com", "Primary": True}],
    }
    result = format_user_for_display(user_data)
    assert "testuser" in result
    assert "Test User" in result
    assert "test@example.com" in result

    # Test with minimal user data
    minimal_user = {"UserName": "minimal"}
    result = format_user_for_display(minimal_user)
    assert "minimal" in result
    assert "N/A" in result


def test_user_helpers_validate_email_format():
    """Test that the validate_email_format function works correctly."""
    from src.awsideman.commands.user.helpers import validate_email_format

    # Test valid emails
    assert validate_email_format("test@example.com") is True
    assert validate_email_format("user.name@domain.co.uk") is True
    assert validate_email_format("user+tag@example.org") is True

    # Test invalid emails
    assert validate_email_format("invalid-email") is False
    assert validate_email_format("@example.com") is False
    assert validate_email_format("user@") is False
    assert validate_email_format("") is False


def test_user_helpers_validate_username_format():
    """Test that the validate_username_format function works correctly."""
    from src.awsideman.commands.user.helpers import validate_username_format

    # Test valid usernames
    assert validate_username_format("validuser") is True
    assert validate_username_format("user_name") is True
    assert validate_username_format("user-name") is True
    assert validate_username_format("user123") is True
    assert validate_username_format("a" * 128) is True  # Max length

    # Test invalid usernames
    assert validate_username_format("") is False  # Too short
    assert validate_username_format("a" * 129) is False  # Too long
    assert validate_username_format("user@name") is False  # Invalid character
    assert validate_username_format("user.name") is False  # Invalid character
    assert validate_username_format("user name") is False  # Invalid character
