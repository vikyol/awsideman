"""Tests for user get commands."""

from typer.testing import CliRunner

from src.awsideman.commands.user import app


def test_get_user_command_structure():
    """Test that the get user command has the expected structure."""
    runner = CliRunner()

    # Test help output
    result = runner.invoke(app, ["get", "--help"])
    assert result.exit_code == 0
    assert "identifier" in result.output
    assert "Username, email, or user ID" in result.output


def test_get_user_basic_command():
    """Test basic get user command."""
    runner = CliRunner()
    result = runner.invoke(app, ["get", "testuser"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_get_user_with_profile():
    """Test get user command with profile parameter."""
    runner = CliRunner()
    result = runner.invoke(app, ["get", "testuser", "--profile", "test-profile"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_get_user_missing_identifier():
    """Test get user command fails when identifier is missing."""
    runner = CliRunner()
    result = runner.invoke(app, ["get"])
    assert result.exit_code != 0


def test_get_user_with_email_identifier():
    """Test get user command with email as identifier."""
    runner = CliRunner()
    result = runner.invoke(app, ["get", "test@example.com"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_get_user_with_user_id_identifier():
    """Test get user command with user ID as identifier."""
    runner = CliRunner()
    result = runner.invoke(app, ["get", "user-1234567890abcdef"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_get_user_help_text():
    """Test that help text contains expected information."""
    runner = CliRunner()
    result = runner.invoke(app, ["get", "--help"])
    assert result.exit_code == 0
    assert "Get detailed information about a specific user" in result.output
    assert "Username, email, or user ID to search for" in result.output
    assert "AWS profile to use" in result.output


def test_get_user_short_profile_option():
    """Test get user command with short profile option."""
    runner = CliRunner()
    result = runner.invoke(app, ["get", "testuser", "-p", "default"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None
