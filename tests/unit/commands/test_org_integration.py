"""Tests for org command integration."""

import re
from typer.testing import CliRunner

from src.awsideman.commands.org import app


def test_org_command_structure():
    """Test that the org commands have the expected structure."""
    runner = CliRunner()

    # Test help output
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Manage AWS Organizations" in result.output


def test_org_tree_command_integration():
    """Test org tree command integration."""
    runner = CliRunner()
    result = runner.invoke(app, ["tree", "--help"])
    assert result.exit_code == 0
    assert "Display the full AWS Organization hierarchy" in result.output


def test_org_search_command_integration():
    """Test org search command integration."""
    runner = CliRunner()
    result = runner.invoke(app, ["search", "--help"])
    assert result.exit_code == 0
    assert "Search for accounts by name or substring" in result.output


def test_org_account_command_integration():
    """Test org account command integration."""
    runner = CliRunner()
    result = runner.invoke(app, ["account", "--help"])
    assert result.exit_code == 0
    assert "Display detailed information about a specific AWS account" in result.output


def test_org_trace_policies_command_integration():
    """Test org trace-policies command integration."""
    runner = CliRunner()
    result = runner.invoke(app, ["trace-policies", "--help"])
    assert result.exit_code == 0
    assert "Trace all SCPs and RCPs affecting a given account" in result.output


def test_org_commands_help_text():
    """Test that help text contains expected information."""
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "organization structure" in result.output
    assert "tree" in result.output
    assert "search" in result.output
    assert "account" in result.output
    assert "trace-policies" in result.output


def test_org_commands_consistency():
    """Test that all org commands have consistent structure."""
    runner = CliRunner()

    # All commands should have help
    for command in ["tree", "search", "account", "trace-policies"]:
        result = runner.invoke(app, [command, "--help"])
        assert result.exit_code == 0
        assert "help" in result.output.lower()


def test_org_commands_profile_consistency():
    """Test that all org commands support profile option consistently."""
    runner = CliRunner()
    
    # Test that account command supports profile
    result = runner.invoke(app, ["account", "--help"])
    assert result.exit_code == 0
    
    # Strip ANSI color codes for more reliable string matching
    clean_output = re.sub(r'\x1b\[[0-9;]*m', '', result.output)
    assert "--profile" in clean_output
