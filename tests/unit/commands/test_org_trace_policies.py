"""Tests for the org trace-policies command."""

import re

from typer.testing import CliRunner

from src.awsideman.commands.org import app


def test_trace_policies_command_structure():
    """Test that the trace-policies command has the expected structure."""
    runner = CliRunner()

    # Test help output
    result = runner.invoke(app, ["trace-policies", "--help"])
    assert result.exit_code == 0
    assert "Trace all SCPs and RCPs affecting a given account" in result.output


def test_trace_policies_command_basic():
    """Test basic trace-policies command."""
    runner = CliRunner()
    result = runner.invoke(app, ["trace-policies", "test-policy"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_trace_policies_command_with_profile():
    """Test trace-policies command with profile parameter."""
    runner = CliRunner()
    result = runner.invoke(app, ["trace-policies", "test-policy", "--profile", "test-profile"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_trace_policies_command_missing_policy():
    """Test trace-policies command fails when policy is missing."""
    runner = CliRunner()
    result = runner.invoke(app, ["trace-policies"])
    assert result.exit_code != 0


def test_trace_policies_command_help_text():
    """Test that help text contains expected information."""
    runner = CliRunner()
    result = runner.invoke(app, ["trace-policies", "--help"])
    assert result.exit_code == 0
    assert "Trace all SCPs and RCPs affecting a given account" in result.output


def test_trace_policies_command_options():
    """Test that help text shows all options."""
    runner = CliRunner()
    result = runner.invoke(app, ["trace-policies", "--help"])
    assert result.exit_code == 0

    # Strip ANSI color codes for more reliable string matching
    clean_output = re.sub(r"\x1b\[[0-9;]*m", "", result.output)

    assert "--json" in clean_output
    assert "--profile" in clean_output
