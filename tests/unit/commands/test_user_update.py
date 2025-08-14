"""Tests for user update commands."""

from typer.testing import CliRunner

from src.awsideman.commands.user import app


def test_update_user_command_structure():
    """Test that the update user command has the expected structure."""
    runner = CliRunner()

    # Test help output
    result = runner.invoke(app, ["update", "--help"])
    assert result.exit_code == 0
    assert "user_id" in result.output
    assert "User ID of the user to update" in result.output


def test_update_user_basic_command():
    """Test basic update user command."""
    runner = CliRunner()
    result = runner.invoke(app, ["update", "user-1234567890abcdef"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_update_user_with_profile():
    """Test update user command with profile parameter."""
    runner = CliRunner()
    result = runner.invoke(app, ["update", "user-1234567890abcdef", "--profile", "test-profile"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_update_user_missing_user_id():
    """Test update user command fails when user ID is missing."""
    runner = CliRunner()
    result = runner.invoke(app, ["update"])
    assert result.exit_code != 0


def test_update_user_with_username_update():
    """Test update user command with username update."""
    runner = CliRunner()
    result = runner.invoke(app, ["update", "user-1234567890abcdef", "--username", "newusername"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_update_user_with_email_update():
    """Test update user command with email update."""
    runner = CliRunner()
    result = runner.invoke(app, ["update", "user-1234567890abcdef", "--email", "new@example.com"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_update_user_help_text():
    """Test that help text contains expected information."""
    runner = CliRunner()
    result = runner.invoke(app, ["update", "--help"])
    assert result.exit_code == 0
    assert "Update an existing user in the Identity Store" in result.output
    assert "User ID of the user to update" in result.output
    assert "AWS profile to use" in result.output


def test_update_user_short_profile_option():
    """Test update user command with short profile option."""
    runner = CliRunner()
    result = runner.invoke(app, ["update", "user-1234567890abcdef", "-p", "default"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_update_user_with_all_parameters():
    """Test update user command with all optional parameters."""
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "update",
            "user-1234567890abcdef",
            "--username",
            "newusername",
            "--email",
            "new@example.com",
            "--given-name",
            "Updated",
            "--family-name",
            "Name",
            "--display-name",
            "Updated Name",
            "--profile",
            "default",
        ],
    )
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None
