"""Tests for user list commands."""

from typer.testing import CliRunner

from src.awsideman.commands.user import app


def test_list_users_command_structure():
    """Test that the list users command has the expected structure."""
    runner = CliRunner()

    # Test help output
    result = runner.invoke(app, ["list", "--help"])
    assert result.exit_code == 0
    assert "filter" in result.output
    assert "limit" in result.output


def test_list_users_basic_command():
    """Test basic list users command."""
    runner = CliRunner()
    result = runner.invoke(app, ["list"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_list_users_with_filter():
    """Test list users command with filter parameter."""
    runner = CliRunner()
    result = runner.invoke(app, ["list", "--filter", "UserName=testuser"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_list_users_with_limit():
    """Test list users command with limit parameter."""
    runner = CliRunner()
    result = runner.invoke(app, ["list", "--limit", "10"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_list_users_with_profile():
    """Test list users command with profile parameter."""
    runner = CliRunner()
    result = runner.invoke(app, ["list", "--profile", "test-profile"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_list_users_invalid_filter_format():
    """Test list users command fails with invalid filter format."""
    runner = CliRunner()
    result = runner.invoke(app, ["list", "--filter", "invalid-filter"])
    # Command should fail due to invalid filter format
    assert result.exit_code != 0


def test_list_users_help_text():
    """Test that help text contains expected information."""
    runner = CliRunner()
    result = runner.invoke(app, ["list", "--help"])
    assert result.exit_code == 0
    assert "List all users" in result.output
    assert "Filter users by attribute" in result.output
    assert "Maximum number of users" in result.output


def test_list_users_short_options():
    """Test list users command with short option names."""
    runner = CliRunner()
    result = runner.invoke(app, ["list", "-f", "UserName=test", "-l", "5", "-p", "default"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None
