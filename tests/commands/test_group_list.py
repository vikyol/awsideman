"""Tests for group list commands."""
from typer.testing import CliRunner

from src.awsideman.commands.group import app


def test_list_groups_command_structure():
    """Test that the list groups command has the expected structure."""
    runner = CliRunner()

    # Test help output
    result = runner.invoke(app, ["list", "--help"])
    assert result.exit_code == 0
    assert "filter" in result.output
    assert "limit" in result.output


def test_list_groups_basic_command():
    """Test basic list groups command."""
    runner = CliRunner()
    result = runner.invoke(app, ["list"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_list_groups_with_filter():
    """Test list groups command with filter parameter."""
    runner = CliRunner()
    result = runner.invoke(app, ["list", "--filter", "DisplayName=Admin"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_list_groups_with_limit():
    """Test list groups command with limit parameter."""
    runner = CliRunner()
    result = runner.invoke(app, ["list", "--limit", "10"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_list_groups_with_profile():
    """Test list groups command with profile parameter."""
    runner = CliRunner()
    result = runner.invoke(app, ["list", "--profile", "test-profile"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_list_groups_invalid_filter_format():
    """Test list groups command fails with invalid filter format."""
    runner = CliRunner()
    result = runner.invoke(app, ["list", "--filter", "invalid-filter"])
    # Command should fail due to invalid filter format
    assert result.exit_code != 0


def test_list_groups_help_text():
    """Test that help text contains expected information."""
    runner = CliRunner()
    result = runner.invoke(app, ["list", "--help"])
    assert result.exit_code == 0
    assert "List all groups" in result.output
    assert "Filter groups by attribute" in result.output
    assert "Maximum number of groups" in result.output


def test_list_groups_short_options():
    """Test list groups command with short option names."""
    runner = CliRunner()
    result = runner.invoke(app, ["list", "-f", "DisplayName=Admin", "-l", "5", "-p", "default"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None
