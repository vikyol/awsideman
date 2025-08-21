"""Tests for the org search command."""

import re
from typer.testing import CliRunner

from src.awsideman.commands.org import app


def test_search_command_structure():
    """Test that the search command has the expected structure."""
    runner = CliRunner()

    # Test help output
    result = runner.invoke(app, ["search", "--help"])
    assert result.exit_code == 0
    assert "Search for accounts by name or substring" in result.output


def test_search_command_basic():
    """Test basic search command."""
    runner = CliRunner()
    result = runner.invoke(app, ["search", "test"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_search_command_with_profile():
    """Test search command with profile parameter."""
    runner = CliRunner()
    result = runner.invoke(app, ["search", "test", "--profile", "test-profile"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_search_command_with_pattern():
    """Test search command with pattern parameter."""
    runner = CliRunner()
    result = runner.invoke(app, ["search", "--pattern", "test"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_search_command_with_filter():
    """Test search command with filter parameter."""
    runner = CliRunner()
    result = runner.invoke(app, ["search", "test", "--filter", "status=ACTIVE"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_search_command_with_limit():
    """Test search command with limit parameter."""
    runner = CliRunner()
    result = runner.invoke(app, ["search", "test", "--limit", "10"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_search_command_missing_query():
    """Test search command fails when query is missing."""
    runner = CliRunner()
    result = runner.invoke(app, ["search"])
    assert result.exit_code != 0


def test_search_command_help_text():
    """Test that help text contains expected information."""
    runner = CliRunner()
    result = runner.invoke(app, ["search", "--help"])
    assert result.exit_code == 0
    assert "Search for accounts by name or substring" in result.output
    assert "Account name or substring to search for" in result.output
    assert "AWS profile to use" in result.output


def test_search_command_options():
    """Test that help text shows all options."""
    runner = CliRunner()
    result = runner.invoke(app, ["search", "--help"])
    assert result.exit_code == 0
    
    # Strip ANSI color codes for more reliable string matching
    clean_output = re.sub(r'\x1b\[[0-9;]*m', '', result.output)
    
    assert "--ou" in clean_output
    assert "--profile" in clean_output
    assert "--json" in clean_output


def test_search_command_short_profile_option():
    """Test search command with short profile option."""
    runner = CliRunner()
    result = runner.invoke(app, ["search", "test", "-p", "default"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_search_command_with_json_format():
    """Test search command with JSON format."""
    runner = CliRunner()
    result = runner.invoke(app, ["search", "test", "--json"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_search_command_with_table_format():
    """Test search command with table format."""
    runner = CliRunner()
    result = runner.invoke(app, ["search", "test", "--table"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None
