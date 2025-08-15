"""Tests for status command integration and edge cases."""

import pytest
from typer.testing import CliRunner

from src.awsideman.commands.status import app


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


class TestCommandIntegration:
    """Test command integration and edge cases."""

    def test_app_help(self, runner):
        """Test that the app help displays correctly."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Monitor AWS Identity Center status and health" in result.stdout
        assert "check" in result.stdout
        assert "inspect" in result.stdout
        assert "cleanup" in result.stdout

    def test_check_command_help(self, runner):
        """Test that the check command help displays correctly."""
        result = runner.invoke(app, ["check", "--help"])
        assert result.exit_code == 0
        assert "Check AWS Identity Center status and health" in result.stdout
        assert "--format" in result.stdout
        assert "--type" in result.stdout
        assert "--timeout" in result.stdout
        assert "--parallel" in result.stdout

    def test_inspect_command_help(self, runner):
        """Test that the inspect command help displays correctly."""
        result = runner.invoke(app, ["inspect", "--help"])
        assert result.exit_code == 0
        assert "Inspect detailed status of a specific resource" in result.stdout
        assert "resource_type" in result.stdout
        assert "resource_id" in result.stdout

    def test_cleanup_command_help(self, runner):
        """Test that the cleanup command help displays correctly."""
        result = runner.invoke(app, ["cleanup", "--help"])
        assert result.exit_code == 0
        assert "Clean up orphaned permission set assignments" in result.stdout
        assert "--dry-run" in result.stdout
        assert "--force" in result.stdout

    def test_monitor_command_help(self, runner):
        """Test that the monitor command help displays correctly."""
        result = runner.invoke(app, ["monitor", "--help"])
        assert result.exit_code == 0
        assert "Configure and manage automated monitoring" in result.stdout
        assert "action" in result.stdout
