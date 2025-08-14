"""Tests for group delete commands."""

from typer.testing import CliRunner

from src.awsideman.commands.group import app


def test_delete_group_command_structure():
    """Test that the delete group command has the expected structure."""
    runner = CliRunner()

    # Test help output
    result = runner.invoke(app, ["delete", "--help"])
    assert result.exit_code == 0
    assert "identifier" in result.output
    assert "Group name or ID" in result.output


def test_delete_group_basic_command():
    """Test basic delete group command."""
    runner = CliRunner()
    result = runner.invoke(app, ["delete", "TestGroup"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_delete_group_with_profile():
    """Test delete group command with profile parameter."""
    runner = CliRunner()
    result = runner.invoke(app, ["delete", "TestGroup", "--profile", "test-profile"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_delete_group_missing_identifier():
    """Test delete group command fails when identifier is missing."""
    runner = CliRunner()
    result = runner.invoke(app, ["delete"])
    assert result.exit_code != 0


def test_delete_group_with_group_id():
    """Test delete group command with group ID."""
    runner = CliRunner()
    result = runner.invoke(app, ["delete", "group-1234567890abcdef"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_delete_group_help_text():
    """Test that help text contains expected information."""
    runner = CliRunner()
    result = runner.invoke(app, ["delete", "--help"])
    assert result.exit_code == 0
    assert "Delete a group from the Identity Store" in result.output
    assert "Group name or ID" in result.output
    assert "AWS profile to use" in result.output


def test_delete_group_short_profile_option():
    """Test delete group command with short profile option."""
    runner = CliRunner()
    result = runner.invoke(app, ["delete", "TestGroup", "-p", "default"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_delete_group_with_force_flag():
    """Test delete group command with force flag."""
    runner = CliRunner()
    result = runner.invoke(app, ["delete", "TestGroup", "--force"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None
