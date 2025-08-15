"""Tests for status monitor command functionality."""

from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from src.awsideman.commands.status import app


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_config():
    """Mock configuration with test profile."""
    with patch("src.awsideman.commands.status.monitor.Config") as mock_config_class:
        mock_config_instance = Mock()
        mock_config_class.return_value = mock_config_instance
        yield mock_config_instance


@pytest.fixture
def mock_monitoring_config_manager():
    """Mock monitoring configuration manager."""
    with patch("src.awsideman.commands.status.monitor.MonitoringConfigManager") as mock_manager:
        yield mock_manager


class TestMonitorConfigCommand:
    """Test the monitor config command."""

    def test_monitor_show_action(self, runner, mock_config, mock_monitoring_config_manager):
        """Test monitor show action."""
        # Setup mocks
        mock_manager_instance = Mock()
        mock_monitoring_config_manager.return_value = mock_manager_instance
        mock_monitoring_config = Mock()
        mock_monitoring_config.enabled = True
        mock_monitoring_config.profiles = ["test-profile"]
        mock_monitoring_config.status_types = ["health", "provisioning"]
        mock_monitoring_config.thresholds = {}
        mock_monitoring_config.email_notifications = None
        mock_monitoring_config.webhook_notifications = None
        mock_manager_instance.get_monitoring_config.return_value = mock_monitoring_config

        # Run command
        result = runner.invoke(app, ["monitor", "show"])

        # Verify success
        assert result.exit_code == 0
        mock_monitoring_config_manager.assert_called_once()

    def test_monitor_enable_action(self, runner, mock_config, mock_monitoring_config_manager):
        """Test monitor enable action."""
        # Setup mocks
        mock_manager_instance = Mock()
        mock_monitoring_config_manager.return_value = mock_manager_instance
        mock_monitoring_config = Mock()
        mock_manager_instance.get_monitoring_config.return_value = mock_monitoring_config

        # Run command
        result = runner.invoke(app, ["monitor", "enable"])

        # Verify success
        assert result.exit_code == 0
        mock_monitoring_config_manager.assert_called_once()

    def test_monitor_disable_action(self, runner, mock_config, mock_monitoring_config_manager):
        """Test monitor disable action."""
        # Setup mocks
        mock_manager_instance = Mock()
        mock_monitoring_config_manager.return_value = mock_manager_instance
        mock_monitoring_config = Mock()
        mock_manager_instance.get_monitoring_config.return_value = mock_monitoring_config

        # Run command
        result = runner.invoke(app, ["monitor", "disable"])

        # Verify success
        assert result.exit_code == 0
        mock_monitoring_config_manager.assert_called_once()

    def test_monitor_test_action(self, runner, mock_config, mock_monitoring_config_manager):
        """Test monitor test action."""
        # Setup mocks
        mock_manager_instance = Mock()
        mock_monitoring_config_manager.return_value = mock_manager_instance
        mock_monitoring_config = Mock()
        mock_monitoring_config.enabled = False  # Disabled to avoid complex notification testing
        mock_manager_instance.get_monitoring_config.return_value = mock_monitoring_config

        # Run command
        result = runner.invoke(app, ["monitor", "test"])

        # Verify that it exits with error code 1 because monitoring is disabled
        assert result.exit_code == 1
        assert "Monitoring is disabled" in result.stdout
        mock_monitoring_config_manager.assert_called_once()

    def test_monitor_schedule_action(self, runner, mock_config, mock_monitoring_config_manager):
        """Test monitor schedule action."""
        # Setup mocks
        mock_manager_instance = Mock()
        mock_monitoring_config_manager.return_value = mock_manager_instance
        mock_monitoring_config = Mock()
        mock_manager_instance.get_monitoring_config.return_value = mock_monitoring_config

        # Run command
        result = runner.invoke(app, ["monitor", "schedule"])

        # Verify success
        assert result.exit_code == 0
        mock_monitoring_config_manager.assert_called_once()

    def test_monitor_config_initialization_error(self, runner):
        """Test monitor config with initialization error."""
        with patch("src.awsideman.commands.status.monitor.Config") as mock_config_class:
            mock_config_class.side_effect = Exception("Config initialization failed")

            result = runner.invoke(app, ["monitor", "show"])
            assert result.exit_code == 1
            assert "Error initializing monitoring config" in result.stdout
