"""Tests for backup config command."""

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from src.awsideman.commands.backup.config import app


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_config():
    with patch("awsideman.commands.backup.config.config") as mock:
        mock.get.return_value = {
            "storage": {
                "default_backend": "filesystem",
                "filesystem": {"path": "~/.awsideman/backups"},
                "s3": {"bucket": None, "prefix": "backups"},
            },
            "encryption": {"enabled": True, "type": "aes256"},
            "compression": {"enabled": True, "type": "gzip"},
            "defaults": {
                "backup_type": "full",
                "include_inactive_users": False,
                "resource_types": "all",
            },
            "retention": {
                "keep_daily": 7,
                "keep_weekly": 4,
                "keep_monthly": 12,
                "auto_cleanup": True,
            },
        }
        yield mock


def test_show_backup_config_table(runner, mock_config):
    """Test showing backup config in table format."""
    result = runner.invoke(app, ["show"])
    assert result.exit_code == 0
    assert "Backup Configuration" in result.output
    assert "filesystem" in result.output
    assert "aes256" in result.output


def test_show_backup_config_json(runner, mock_config):
    """Test showing backup config in JSON format."""
    result = runner.invoke(app, ["show", "--format", "json"])
    assert result.exit_code == 0
    assert '"storage"' in result.output
    assert '"default_backend"' in result.output


def test_show_backup_config_yaml(runner, mock_config):
    """Test showing backup config in YAML format."""
    result = runner.invoke(app, ["show", "--format", "yaml"])
    assert result.exit_code == 0
    assert "storage:" in result.output
    assert "default_backend:" in result.output


def test_set_backup_config(runner, mock_config):
    """Test setting backup config values."""
    result = runner.invoke(app, ["set", "storage.default_backend", "s3"])
    assert result.exit_code == 0
    assert "✓ Set storage.default_backend = s3" in result.output
    mock_config.set.assert_called_once()


def test_get_backup_config(runner, mock_config):
    """Test getting backup config values."""
    result = runner.invoke(app, ["get", "storage.default_backend"])
    assert result.exit_code == 0
    assert "storage.default_backend: filesystem" in result.output


def test_reset_backup_config_section(runner, mock_config):
    """Test resetting a specific backup config section."""
    with patch("typer.confirm") as mock_confirm:
        mock_confirm.return_value = True
        result = runner.invoke(app, ["reset", "--section", "storage"])
        assert result.exit_code == 0
        assert "✓ Reset 'storage' section to defaults" in result.output


def test_reset_backup_config_all(runner, mock_config):
    """Test resetting all backup config."""
    with patch("typer.confirm") as mock_confirm:
        mock_confirm.return_value = True
        result = runner.invoke(app, ["reset"])
        assert result.exit_code == 0
        assert "✓ Reset all backup configuration to defaults" in result.output


def test_test_backup_config_valid(runner, mock_config):
    """Test backup config validation with valid config."""
    result = runner.invoke(app, ["test"])
    assert result.exit_code == 0
    assert "✓ All backup configuration is valid!" in result.output


def test_test_backup_config_s3_no_bucket(runner):
    """Test backup config validation with S3 backend but no bucket."""
    with patch("awsideman.commands.backup.config.config") as mock:
        mock.get.return_value = {
            "storage": {"default_backend": "s3", "s3": {"bucket": None}},
            "encryption": {"enabled": True, "type": "aes256"},
            "compression": {"enabled": True, "type": "gzip"},
        }
        result = runner.invoke(app, ["test"])
        assert result.exit_code == 1
        assert "S3 backend selected but no bucket configured" in result.output


def test_test_backup_config_encryption_disabled(runner):
    """Test backup config validation with encryption disabled."""
    with patch("awsideman.commands.backup.config.config") as mock:
        mock.get.return_value = {
            "storage": {"default_backend": "filesystem"},
            "encryption": {"enabled": False},
            "compression": {"enabled": True, "type": "gzip"},
        }
        result = runner.invoke(app, ["test"])
        assert result.exit_code == 0
        assert "Encryption is disabled (not recommended for production)" in result.output
