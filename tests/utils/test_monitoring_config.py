"""Tests for monitoring configuration."""
import os
from unittest.mock import Mock, patch

import pytest

from src.awsideman.utils.config import Config
from src.awsideman.utils.monitoring_config import (
    EmailNotificationConfig,
    LogNotificationConfig,
    MonitoringConfig,
    MonitoringConfigManager,
    MonitoringThreshold,
    NotificationType,
    ScheduleConfig,
    ThresholdLevel,
    WebhookNotificationConfig,
)
from src.awsideman.utils.status_models import StatusLevel


class TestMonitoringThreshold:
    """Test MonitoringThreshold class."""

    def test_monitoring_threshold_creation(self):
        """Test creating a monitoring threshold."""
        threshold = MonitoringThreshold(
            level=ThresholdLevel.WARNING,
            status_levels=[StatusLevel.WARNING],
            orphaned_assignment_count=5,
            provisioning_failure_count=3,
            sync_delay_hours=24,
        )

        assert threshold.level == ThresholdLevel.WARNING
        assert threshold.status_levels == [StatusLevel.WARNING]
        assert threshold.orphaned_assignment_count == 5
        assert threshold.provisioning_failure_count == 3
        assert threshold.sync_delay_hours == 24
        assert threshold.enabled is True

    def test_monitoring_threshold_defaults(self):
        """Test monitoring threshold with defaults."""
        threshold = MonitoringThreshold(level=ThresholdLevel.CRITICAL)

        assert threshold.level == ThresholdLevel.CRITICAL
        assert threshold.status_levels == [StatusLevel.WARNING]
        assert threshold.orphaned_assignment_count is None
        assert threshold.provisioning_failure_count is None
        assert threshold.sync_delay_hours is None
        assert threshold.enabled is True


class TestEmailNotificationConfig:
    """Test EmailNotificationConfig class."""

    def test_email_config_creation(self):
        """Test creating email notification config."""
        config = EmailNotificationConfig(
            smtp_server="smtp.example.com",
            smtp_port=587,
            username="user@example.com",
            password="password",
            from_address="alerts@example.com",
            to_addresses=["admin@example.com", "ops@example.com"],
        )

        assert config.smtp_server == "smtp.example.com"
        assert config.smtp_port == 587
        assert config.username == "user@example.com"
        assert config.password == "password"
        assert config.from_address == "alerts@example.com"
        assert config.to_addresses == ["admin@example.com", "ops@example.com"]
        assert config.use_tls is True
        assert config.enabled is True

    def test_email_config_defaults(self):
        """Test email config with defaults."""
        config = EmailNotificationConfig(
            smtp_server="smtp.example.com",
            username="user@example.com",
            password="password",
            from_address="alerts@example.com",
        )

        assert config.smtp_port == 587
        assert config.to_addresses == []
        assert config.use_tls is True
        assert config.subject_template == "AWS Identity Center Alert: {level} - {message}"
        assert config.enabled is True


class TestWebhookNotificationConfig:
    """Test WebhookNotificationConfig class."""

    def test_webhook_config_creation(self):
        """Test creating webhook notification config."""
        config = WebhookNotificationConfig(
            url="https://hooks.slack.com/webhook",
            method="POST",
            headers={"Content-Type": "application/json"},
            timeout_seconds=30,
        )

        assert config.url == "https://hooks.slack.com/webhook"
        assert config.method == "POST"
        assert config.headers == {"Content-Type": "application/json"}
        assert config.timeout_seconds == 30
        assert config.retry_attempts == 3
        assert config.enabled is True

    def test_webhook_config_defaults(self):
        """Test webhook config with defaults."""
        config = WebhookNotificationConfig(url="https://example.com/webhook")

        assert config.method == "POST"
        assert config.headers == {}
        assert config.timeout_seconds == 30
        assert config.retry_attempts == 3
        assert config.retry_delay_seconds == 1.0
        assert config.payload_template is None
        assert config.enabled is True


class TestLogNotificationConfig:
    """Test LogNotificationConfig class."""

    def test_log_config_creation(self):
        """Test creating log notification config."""
        config = LogNotificationConfig(
            log_level="ERROR",
            log_format="%(asctime)s - %(message)s",
            log_file="/var/log/awsideman.log",
        )

        assert config.log_level == "ERROR"
        assert config.log_format == "%(asctime)s - %(message)s"
        assert config.log_file == "/var/log/awsideman.log"
        assert config.enabled is True

    def test_log_config_defaults(self):
        """Test log config with defaults."""
        config = LogNotificationConfig()

        assert config.log_level == "WARNING"
        assert config.log_format == "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        assert config.log_file is None
        assert config.enabled is True


class TestScheduleConfig:
    """Test ScheduleConfig class."""

    def test_schedule_config_creation(self):
        """Test creating schedule config."""
        config = ScheduleConfig(
            enabled=True,
            interval_minutes=30,
            cron_expression="0 */30 * * * *",
            max_concurrent_checks=5,
            timeout_seconds=600,
        )

        assert config.enabled is True
        assert config.interval_minutes == 30
        assert config.cron_expression == "0 */30 * * * *"
        assert config.max_concurrent_checks == 5
        assert config.timeout_seconds == 600
        assert config.retry_on_failure is True

    def test_schedule_config_defaults(self):
        """Test schedule config with defaults."""
        config = ScheduleConfig()

        assert config.enabled is False
        assert config.interval_minutes == 60
        assert config.cron_expression is None
        assert config.max_concurrent_checks == 3
        assert config.timeout_seconds == 300
        assert config.retry_on_failure is True
        assert config.retry_attempts == 2
        assert config.retry_delay_seconds == 30.0


class TestMonitoringConfig:
    """Test MonitoringConfig class."""

    def test_monitoring_config_creation(self):
        """Test creating monitoring config."""
        email_config = EmailNotificationConfig(
            smtp_server="smtp.example.com",
            username="user@example.com",
            password="password",
            from_address="alerts@example.com",
        )

        config = MonitoringConfig(
            enabled=True,
            email_notifications=email_config,
            profiles=["default", "prod"],
            status_types=["health", "provisioning"],
        )

        assert config.enabled is True
        assert config.email_notifications == email_config
        assert config.profiles == ["default", "prod"]
        assert config.status_types == ["health", "provisioning"]
        assert len(config.thresholds) == 2  # Default thresholds

    def test_monitoring_config_defaults(self):
        """Test monitoring config with defaults."""
        config = MonitoringConfig()

        assert config.enabled is False
        assert config.email_notifications is None
        assert config.webhook_notifications is None
        assert config.log_notifications is None
        assert config.schedule is None
        assert config.profiles == []
        assert config.status_types == ["health", "provisioning", "orphaned", "sync"]
        assert len(config.thresholds) == 2  # Default thresholds

    def test_default_thresholds(self):
        """Test default threshold creation."""
        config = MonitoringConfig()

        assert "warning" in config.thresholds
        assert "critical" in config.thresholds

        warning = config.thresholds["warning"]
        assert warning.level == ThresholdLevel.WARNING
        assert warning.status_levels == [StatusLevel.WARNING]
        assert warning.orphaned_assignment_count == 5
        assert warning.provisioning_failure_count == 3
        assert warning.sync_delay_hours == 24

        critical = config.thresholds["critical"]
        assert critical.level == ThresholdLevel.CRITICAL
        assert critical.status_levels == [StatusLevel.CRITICAL, StatusLevel.CONNECTION_FAILED]
        assert critical.orphaned_assignment_count == 20
        assert critical.provisioning_failure_count == 10
        assert critical.sync_delay_hours == 72


class TestMonitoringConfigManager:
    """Test MonitoringConfigManager class."""

    def setup_method(self):
        """Setup test method."""
        self.mock_config = Mock(spec=Config)
        self.config_manager = MonitoringConfigManager(self.mock_config)

    def test_get_monitoring_config_empty(self):
        """Test getting monitoring config with empty config."""
        self.mock_config.get.return_value = {}

        config = self.config_manager.get_monitoring_config()

        assert isinstance(config, MonitoringConfig)
        assert config.enabled is False
        assert len(config.thresholds) == 2

    def test_get_monitoring_config_with_data(self):
        """Test getting monitoring config with existing data."""
        config_data = {
            "enabled": True,
            "profiles": ["default"],
            "status_types": ["health", "provisioning"],
            "thresholds": {
                "warning": {
                    "level": "warning",
                    "status_levels": ["WARNING"],
                    "orphaned_assignment_count": 10,
                    "enabled": True,
                }
            },
            "email_notifications": {
                "smtp_server": "smtp.example.com",
                "username": "user@example.com",
                "password": "password",
                "from_address": "alerts@example.com",
                "to_addresses": ["admin@example.com"],
                "enabled": True,
            },
        }

        self.mock_config.get.return_value = config_data

        config = self.config_manager.get_monitoring_config()

        assert config.enabled is True
        assert config.profiles == ["default"]
        assert config.status_types == ["health", "provisioning"]
        assert "warning" in config.thresholds
        assert config.thresholds["warning"].orphaned_assignment_count == 10
        assert config.email_notifications is not None
        assert config.email_notifications.smtp_server == "smtp.example.com"

    @patch.dict(
        os.environ,
        {
            "AWSIDEMAN_MONITORING_ENABLED": "true",
            "AWSIDEMAN_EMAIL_NOTIFICATIONS_ENABLED": "false",
            "AWSIDEMAN_EMAIL_SMTP_SERVER": "smtp.override.com",
        },
    )
    def test_environment_overrides(self):
        """Test environment variable overrides."""
        config_data = {
            "enabled": False,
            "email_notifications": {"smtp_server": "smtp.example.com", "enabled": True},
        }

        self.mock_config.get.return_value = config_data

        config = self.config_manager.get_monitoring_config()

        assert config.enabled is True  # Overridden by env var
        assert config.email_notifications.enabled is False  # Overridden by env var
        assert (
            config.email_notifications.smtp_server == "smtp.override.com"
        )  # Overridden by env var

    def test_save_monitoring_config(self):
        """Test saving monitoring config."""
        config = MonitoringConfig(enabled=True, profiles=["default"])

        self.config_manager.save_monitoring_config(config)

        self.mock_config.set.assert_called_once()
        args = self.mock_config.set.call_args[0]
        assert args[0] == "monitoring"
        assert args[1]["enabled"] is True
        assert args[1]["profiles"] == ["default"]

    def test_validate_config_valid(self):
        """Test validating a valid config."""
        config = MonitoringConfig(
            enabled=True,
            email_notifications=EmailNotificationConfig(
                smtp_server="smtp.example.com",
                username="user@example.com",
                password="password",
                from_address="alerts@example.com",
                to_addresses=["admin@example.com"],
            ),
        )

        self.mock_config.get.return_value = {"default": {}}

        errors = self.config_manager.validate_config(config)

        assert errors == []

    def test_validate_config_disabled(self):
        """Test validating disabled config."""
        config = MonitoringConfig(enabled=False)

        errors = self.config_manager.validate_config(config)

        assert errors == []

    def test_validate_config_email_errors(self):
        """Test validating config with email errors."""
        config = MonitoringConfig(
            enabled=True,
            email_notifications=EmailNotificationConfig(
                smtp_server="",  # Missing
                username="",  # Missing
                password="password",
                from_address="",  # Missing
                to_addresses=[],  # Empty
            ),
        )

        errors = self.config_manager.validate_config(config)

        assert len(errors) == 4
        assert any("smtp_server not configured" in error for error in errors)
        assert any("username not configured" in error for error in errors)
        assert any("from_address not configured" in error for error in errors)
        assert any("to_addresses not configured" in error for error in errors)

    def test_validate_config_webhook_errors(self):
        """Test validating config with webhook errors."""
        config = MonitoringConfig(
            enabled=True, webhook_notifications=WebhookNotificationConfig(url="")  # Missing URL
        )

        errors = self.config_manager.validate_config(config)

        assert len(errors) == 1
        assert "url not configured" in errors[0]

    def test_validate_config_profile_errors(self):
        """Test validating config with profile errors."""
        config = MonitoringConfig(enabled=True, profiles=["nonexistent"])

        self.mock_config.get.return_value = {"default": {}}  # Only 'default' profile exists

        errors = self.config_manager.validate_config(config)

        assert len(errors) == 1
        assert "Profile 'nonexistent' specified" in errors[0]

    def test_validate_config_threshold_errors(self):
        """Test validating config with threshold errors."""
        config = MonitoringConfig(
            enabled=True,
            thresholds={
                "warning": MonitoringThreshold(
                    level=ThresholdLevel.WARNING,
                    status_levels=[],  # Empty status levels
                    enabled=True,
                )
            },
        )

        errors = self.config_manager.validate_config(config)

        assert len(errors) == 1
        assert "no status_levels configured" in errors[0]

    def test_get_env_bool(self):
        """Test getting boolean from environment variable."""
        # Test true values
        with patch.dict(os.environ, {"TEST_VAR": "true"}):
            assert self.config_manager._get_env_bool("TEST_VAR", False) is True

        with patch.dict(os.environ, {"TEST_VAR": "1"}):
            assert self.config_manager._get_env_bool("TEST_VAR", False) is True

        with patch.dict(os.environ, {"TEST_VAR": "yes"}):
            assert self.config_manager._get_env_bool("TEST_VAR", False) is True

        # Test false values
        with patch.dict(os.environ, {"TEST_VAR": "false"}):
            assert self.config_manager._get_env_bool("TEST_VAR", True) is False

        with patch.dict(os.environ, {"TEST_VAR": "0"}):
            assert self.config_manager._get_env_bool("TEST_VAR", True) is False

        # Test default
        assert self.config_manager._get_env_bool("NONEXISTENT_VAR", True) is True

    def test_get_env_int(self):
        """Test getting integer from environment variable."""
        # Test valid integer
        with patch.dict(os.environ, {"TEST_VAR": "42"}):
            assert self.config_manager._get_env_int("TEST_VAR", 0) == 42

        # Test invalid integer
        with patch.dict(os.environ, {"TEST_VAR": "not_a_number"}):
            assert self.config_manager._get_env_int("TEST_VAR", 100) == 100

        # Test default
        assert self.config_manager._get_env_int("NONEXISTENT_VAR", 50) == 50

    def test_convert_enums_to_strings(self):
        """Test converting enums to strings."""
        data = {
            "level": ThresholdLevel.WARNING,
            "status_levels": [StatusLevel.WARNING, StatusLevel.CRITICAL],
            "nested": {"type": NotificationType.EMAIL},
            "list": [ThresholdLevel.CRITICAL, "string", 42],
        }

        result = self.config_manager._convert_enums_to_strings(data)

        assert result["level"] == "warning"
        assert result["status_levels"] == ["WARNING", "CRITICAL"]
        assert result["nested"]["type"] == "email"
        assert result["list"] == ["critical", "string", 42]


if __name__ == "__main__":
    pytest.main([__file__])
