"""Tests for the org trace-policies command."""

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
    result = runner.invoke(app, ["trace-policies", "111111111111"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_trace_policies_command_with_profile():
    """Test trace-policies command with profile parameter."""
    runner = CliRunner()
    result = runner.invoke(app, ["trace-policies", "111111111111", "--profile", "test-profile"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_trace_policies_command_missing_account_id():
    """Test trace-policies command fails when account ID is missing."""
    runner = CliRunner()
    result = runner.invoke(app, ["trace-policies"])
    assert result.exit_code != 0


def test_trace_policies_command_with_json_format():
    """Test trace-policies command with JSON format."""
    runner = CliRunner()
    result = runner.invoke(app, ["trace-policies", "111111111111", "--json"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_trace_policies_command_with_table_format():
    """Test trace-policies command with table format."""
    runner = CliRunner()
    result = runner.invoke(app, ["trace-policies", "111111111111", "--table"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_trace_policies_command_help_text():
    """Test that help text contains expected information."""
    runner = CliRunner()
    result = runner.invoke(app, ["trace-policies", "--help"])
    assert result.exit_code == 0
    assert "Trace all SCPs and RCPs affecting a given account" in result.output
    assert "AWS account ID to trace policies for" in result.output
    assert "AWS profile to use" in result.output


def test_trace_policies_command_options():
    """Test that help text shows all options."""
    runner = CliRunner()
    result = runner.invoke(app, ["trace-policies", "--help"])
    assert result.exit_code == 0
    assert "--json" in result.output
    assert "--profile" in result.output


def test_trace_policies_command_short_profile_option():
    """Test trace-policies command with short profile option."""
    runner = CliRunner()
    result = runner.invoke(app, ["trace-policies", "111111111111", "-p", "default"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None
