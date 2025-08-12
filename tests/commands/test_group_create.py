"""Tests for group commands."""
from typer.testing import CliRunner

from src.awsideman.commands.group import app


def test_group_command_structure():
    """Test that the group commands have the expected structure."""
    runner = CliRunner()

    # Test help output
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Manage groups in AWS Identity Center" in result.output


def test_group_list_command():
    """Test group list command."""
    runner = CliRunner()
    result = runner.invoke(app, ["list", "--help"])
    assert result.exit_code == 0
    assert "List all groups" in result.output


def test_group_list_members_command():
    """Test group list-members command."""
    runner = CliRunner()
    result = runner.invoke(app, ["list-members", "--help"])
    assert result.exit_code == 0
    assert "List all members" in result.output


def test_group_add_member_command():
    """Test group add-member command."""
    runner = CliRunner()
    result = runner.invoke(app, ["add-member", "--help"])
    assert result.exit_code == 0
    assert "Add a user to a group" in result.output


def test_group_remove_member_command():
    """Test group remove-member command."""
    runner = CliRunner()
    result = runner.invoke(app, ["remove-member", "--help"])
    assert result.exit_code == 0
    assert "Remove a user from a group" in result.output


def test_group_delete_command():
    """Test group delete command."""
    runner = CliRunner()
    result = runner.invoke(app, ["delete", "--help"])
    assert result.exit_code == 0
    assert "Delete a group" in result.output


def test_group_help_text():
    """Test that help text contains expected information."""
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Create, list, update, and delete groups" in result.output
    assert "add-member" in result.output
    assert "list-members" in result.output
    assert "remove-member" in result.output
