"""Integration tests for status commands."""

import re
from typer.testing import CliRunner

from src.awsideman.commands.status import app


class TestCommandIntegration:
    """Test integration between status commands."""

    def test_check_command_help(self):
        """Test that check command help shows expected options."""
        runner = CliRunner()
        result = runner.invoke(app, ["check", "--help"])
        assert result.exit_code == 0
        
        # Strip ANSI color codes for more reliable string matching
        clean_output = re.sub(r'\x1b\[[0-9;]*m', '', result.stdout)
        
        assert "--format" in clean_output

    def test_cleanup_command_help(self):
        """Test that cleanup command help shows expected options."""
        runner = CliRunner()
        result = runner.invoke(app, ["cleanup", "--help"])
        assert result.exit_code == 0
        
        # Strip ANSI color codes for more reliable string matching
        clean_output = re.sub(r'\x1b\[[0-9;]*m', '', result.stdout)
        
        assert "--dry-run" in clean_output
