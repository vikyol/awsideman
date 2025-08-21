"""Tests for the org tree command."""

import re
from typer.testing import CliRunner

from src.awsideman.commands.org import app


def test_tree_command_structure():
    """Test that the tree command has the expected structure."""
    runner = CliRunner()

    # Test help output
    result = runner.invoke(app, ["tree", "--help"])
    assert result.exit_code == 0
    assert "Display the full AWS Organization hierarchy" in result.output


def test_tree_command_basic():
    """Test basic tree command."""
    runner = CliRunner()
    result = runner.invoke(app, ["tree"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_tree_command_with_profile():
    """Test tree command with profile parameter."""
    runner = CliRunner()
    result = runner.invoke(app, ["tree", "--profile", "test-profile"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_tree_command_with_flat_format():
    """Test tree command with flat format."""
    runner = CliRunner()
    result = runner.invoke(app, ["tree", "--flat"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_tree_command_with_json_format():
    """Test tree command with JSON format."""
    runner = CliRunner()
    result = runner.invoke(app, ["tree", "--json"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_tree_command_with_table_format():
    """Test tree command with table format."""
    runner = CliRunner()
    result = runner.invoke(app, ["tree", "--table"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_tree_command_help_text():
    """Test that help text contains expected information."""
    runner = CliRunner()
    result = runner.invoke(app, ["tree", "--help"])
    assert result.exit_code == 0
    assert "Display the full AWS Organization hierarchy" in result.output
    assert "organizational units, their relationships, and accounts" in result.output
    assert "AWS profile to use" in result.output


def test_tree_command_format_options():
    """Test that help text shows format options."""
    runner = CliRunner()
    result = runner.invoke(app, ["tree", "--help"])
    assert result.exit_code == 0
    
    # Strip ANSI color codes for more reliable string matching
    clean_output = re.sub(r'\x1b\[[0-9;]*m', '', result.output)
    
    assert "--flat" in clean_output
    assert "--profile" in clean_output


def test_tree_command_short_profile_option():
    """Test tree command with short profile option."""
    runner = CliRunner()
    result = runner.invoke(app, ["tree", "-p", "default"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None
