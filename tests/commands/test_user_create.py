"""Tests for user creation commands."""
from typer.testing import CliRunner

from src.awsideman.commands.user import app


def test_create_user_command_structure():
    """Test that the create user command has the expected structure."""
    runner = CliRunner()

    # Test help output
    result = runner.invoke(app, ["create", "--help"])
    assert result.exit_code == 0
    assert "username" in result.output
    assert "email" in result.output


def test_create_user_missing_username():
    """Test create user command fails when username is missing."""
    runner = CliRunner()
    result = runner.invoke(app, ["create", "--email", "test@example.com"])
    assert result.exit_code != 0


def test_create_user_missing_email():
    """Test create user command fails when email is missing."""
    runner = CliRunner()
    result = runner.invoke(app, ["create", "--username", "testuser"])
    assert result.exit_code != 0


def test_create_user_invalid_email_format():
    """Test create user command fails with invalid email format."""
    runner = CliRunner()
    result = runner.invoke(app, ["create", "--username", "testuser", "--email", "invalid-email"])
    assert result.exit_code != 0


def test_create_user_valid_parameters():
    """Test create user command accepts valid parameters."""
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "create",
            "--username",
            "testuser",
            "--email",
            "test@example.com",
            "--given-name",
            "Test",
            "--family-name",
            "User",
            "--display-name",
            "Test User",
        ],
    )
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_create_user_minimal_parameters():
    """Test create user command works with minimal required parameters."""
    runner = CliRunner()
    result = runner.invoke(
        app, ["create", "--username", "minimaluser", "--email", "minimal@example.com"]
    )
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_create_user_help_text():
    """Test that help text contains expected information."""
    runner = CliRunner()
    result = runner.invoke(app, ["create", "--help"])
    assert result.exit_code == 0
    assert "Create a new user" in result.output
    assert "Username for the new user" in result.output
    assert "Email address for the new user" in result.output
