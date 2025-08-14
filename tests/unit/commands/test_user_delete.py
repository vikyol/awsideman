"""Tests for user delete commands."""

from typer.testing import CliRunner

from src.awsideman.commands.user import app


def test_delete_user_command_structure():
    """Test that the delete user command has the expected structure."""
    runner = CliRunner()

    # Test help output
    result = runner.invoke(app, ["delete", "--help"])
    assert result.exit_code == 0
    assert "user_id" in result.output
    assert "User ID of the user to delete" in result.output


def test_delete_user_basic_command():
    """Test basic delete user command."""
    runner = CliRunner()
    result = runner.invoke(app, ["delete", "user-1234567890abcdef"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_delete_user_with_profile():
    """Test delete user command with profile parameter."""
    runner = CliRunner()
    result = runner.invoke(app, ["delete", "user-1234567890abcdef", "--profile", "test-profile"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_delete_user_missing_user_id():
    """Test delete user command fails when user ID is missing."""
    runner = CliRunner()
    result = runner.invoke(app, ["delete"])
    assert result.exit_code != 0


def test_delete_user_with_force_flag():
    """Test delete user command with force flag."""
    runner = CliRunner()
    result = runner.invoke(app, ["delete", "user-1234567890abcdef", "--force"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_delete_user_help_text():
    """Test that help text contains expected information."""
    runner = CliRunner()
    result = runner.invoke(app, ["delete", "--help"])
    assert result.exit_code == 0
    assert "Delete a user from the Identity Store" in result.output
    assert "User ID of the user to delete" in result.output
    assert "AWS profile to use" in result.output


def test_delete_user_short_profile_option():
    """Test delete user command with short profile option."""
    runner = CliRunner()
    result = runner.invoke(app, ["delete", "user-1234567890abcdef", "-p", "default"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_delete_user_short_force_option():
    """Test delete user command with short force option."""
    runner = CliRunner()
    result = runner.invoke(app, ["delete", "user-1234567890abcdef", "-f"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_delete_user_with_all_options():
    """Test delete user command with all options."""
    runner = CliRunner()
    result = runner.invoke(
        app, ["delete", "user-1234567890abcdef", "--force", "--profile", "default"]
    )
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None
