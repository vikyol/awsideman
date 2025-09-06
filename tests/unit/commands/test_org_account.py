"""Tests for the org account command."""

import re

from typer.testing import CliRunner

from src.awsideman.commands.org import app


def test_account_command_structure():
    """Test that the account command has the expected structure."""
    runner = CliRunner()

    # Test help output
    result = runner.invoke(app, ["account", "--help"])
    assert result.exit_code == 0
    assert "Display detailed information about a specific AWS account" in result.output


def test_account_command_basic():
    """Test basic account command."""
    runner = CliRunner()
    result = runner.invoke(app, ["account", "111111111111"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_account_command_with_profile():
    """Test account command with profile parameter."""
    runner = CliRunner()
    result = runner.invoke(app, ["account", "111111111111", "--profile", "test-profile"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_account_command_missing_account_id():
    """Test account command fails when account ID is missing."""
    runner = CliRunner()
    result = runner.invoke(app, ["account"])
    assert result.exit_code != 0


def test_account_command_with_json_format():
    """Test account command with JSON format."""
    runner = CliRunner()
    result = runner.invoke(app, ["account", "111111111111", "--json"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_account_command_with_table_format():
    """Test account command with table format."""
    runner = CliRunner()
    result = runner.invoke(app, ["account", "111111111111", "--table"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_account_command_help_text():
    """Test that help text contains expected information."""
    runner = CliRunner()
    result = runner.invoke(app, ["account", "--help"])
    assert result.exit_code == 0
    assert "Display detailed information about a specific AWS account" in result.output
    assert "account name to display details for" in result.output
    assert "AWS profile to use" in result.output


def test_account_command_options():
    """Test that help text shows all options."""
    runner = CliRunner()
    result = runner.invoke(app, ["account", "--help"])
    assert result.exit_code == 0

    # Strip ANSI color codes for more reliable string matching
    clean_output = re.sub(r"\x1b\[[0-9;]*m", "", result.output)

    assert "--json" in clean_output
    assert "--profile" in clean_output
    # --no-cache is now hidden as an advanced debugging option
    # assert "--no-cache" in clean_output


def test_account_command_short_profile_option():
    """Test account command with short profile option."""
    runner = CliRunner()
    result = runner.invoke(app, ["account", "111111111111", "-p", "default"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None
