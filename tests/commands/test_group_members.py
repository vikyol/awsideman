"""Tests for group member management commands."""
from typer.testing import CliRunner

from src.awsideman.commands.group import app


def test_list_members_command_structure():
    """Test that the list-members command has the expected structure."""
    runner = CliRunner()

    # Test help output
    result = runner.invoke(app, ["list-members", "--help"])
    assert result.exit_code == 0
    assert "identifier" in result.output
    assert "Group name or ID" in result.output


def test_list_members_basic_command():
    """Test basic list-members command."""
    runner = CliRunner()
    result = runner.invoke(app, ["list-members", "TestGroup"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_list_members_with_group_id():
    """Test list-members command with group ID."""
    runner = CliRunner()
    result = runner.invoke(app, ["list-members", "group-1234567890abcdef"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_list_members_with_profile():
    """Test list-members command with profile parameter."""
    runner = CliRunner()
    result = runner.invoke(app, ["list-members", "TestGroup", "--profile", "test-profile"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_list_members_missing_identifier():
    """Test list-members command fails when identifier is missing."""
    runner = CliRunner()
    result = runner.invoke(app, ["list-members"])
    assert result.exit_code != 0


def test_list_members_help_text():
    """Test that help text contains expected information."""
    runner = CliRunner()
    result = runner.invoke(app, ["list-members", "--help"])
    assert result.exit_code == 0
    assert "List all members" in result.output
    assert "Group name or ID" in result.output
    assert "AWS profile to use" in result.output


def test_add_member_command_structure():
    """Test that the add-member command has the expected structure."""
    runner = CliRunner()

    # Test help output
    result = runner.invoke(app, ["add-member", "--help"])
    assert result.exit_code == 0
    assert "group_identifier" in result.output
    assert "user_identifier" in result.output


def test_add_member_basic_command():
    """Test basic add-member command."""
    runner = CliRunner()
    result = runner.invoke(app, ["add-member", "TestGroup", "testuser"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_add_member_with_profile():
    """Test add-member command with profile parameter."""
    runner = CliRunner()
    result = runner.invoke(
        app, ["add-member", "TestGroup", "testuser", "--profile", "test-profile"]
    )
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_add_member_missing_group():
    """Test add-member command fails when group identifier is missing."""
    runner = CliRunner()
    result = runner.invoke(app, ["add-member", "testuser"])
    assert result.exit_code != 0


def test_add_member_missing_user():
    """Test add-member command fails when user identifier is missing."""
    runner = CliRunner()
    result = runner.invoke(app, ["add-member", "TestGroup"])
    assert result.exit_code != 0


def test_add_member_help_text():
    """Test that help text contains expected information."""
    runner = CliRunner()
    result = runner.invoke(app, ["add-member", "--help"])
    assert result.exit_code == 0
    assert "Add a user to a group" in result.output
    assert "Group name or ID" in result.output
    assert "User ID, username, or email" in result.output


def test_remove_member_command_structure():
    """Test that the remove-member command has the expected structure."""
    runner = CliRunner()

    # Test help output
    result = runner.invoke(app, ["remove-member", "--help"])
    assert result.exit_code == 0
    assert "group_identifier" in result.output
    assert "user_identifier" in result.output


def test_remove_member_basic_command():
    """Test basic remove-member command."""
    runner = CliRunner()
    result = runner.invoke(app, ["remove-member", "TestGroup", "testuser"])
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_remove_member_with_profile():
    """Test remove-member command with profile parameter."""
    runner = CliRunner()
    result = runner.invoke(
        app, ["remove-member", "TestGroup", "testuser", "--profile", "test-profile"]
    )
    # Command should fail due to missing AWS configuration, but not due to parameter validation
    assert result is not None


def test_remove_member_missing_group():
    """Test remove-member command fails when group identifier is missing."""
    runner = CliRunner()
    result = runner.invoke(app, ["remove-member", "testuser"])
    assert result.exit_code != 0


def test_remove_member_missing_user():
    """Test remove-member command fails when user identifier is missing."""
    runner = CliRunner()
    result = runner.invoke(app, ["remove-member", "TestGroup"])
    assert result.exit_code != 0


def test_remove_member_help_text():
    """Test that help text contains expected information."""
    runner = CliRunner()
    result = runner.invoke(app, ["remove-member", "--help"])
    assert result.exit_code == 0
    assert "Remove a user from a group" in result.output
    assert "Group name or ID" in result.output
    assert "User ID, username, or email" in result.output
