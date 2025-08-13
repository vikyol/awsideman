"""Monitoring configuration for automated status checks."""

import logging
import os
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from rich.console import Console

from .config import Config
from .status_models import StatusLevel

console = Console()
logger = logging.getLogger(__name__)


class NotificationType(Enum):
    """Types of notifications supported."""

    EMAIL = "email"
    WEBHOOK = "webhook"
    LOG = "log"


class ThresholdLevel(Enum):
    """Threshold levels for monitoring alerts."""

    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class MonitoringThreshold:
    """Configuration for monitoring thresholds."""

    level: ThresholdLevel
    status_levels: List[StatusLevel] = field(default_factory=lambda: [StatusLevel.WARNING])
    orphaned_assignment_count: Optional[int] = None
    provisioning_failure_count: Optional[int] = None
    sync_delay_hours: Optional[int] = None
    enabled: bool = True


@dataclass
class EmailNotificationConfig:
    """Configuration for email notifications."""

    smtp_server: str
    username: str
    password: str
    from_address: str
    smtp_port: int = 587
    to_addresses: List[str] = field(default_factory=list)
    use_tls: bool = True
    subject_template: str = "AWS Identity Center Alert: {level} - {message}"
    enabled: bool = True


@dataclass
class WebhookNotificationConfig:
    """Configuration for webhook notifications."""

    url: str
    method: str = "POST"
    headers: Dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 30
    retry_attempts: int = 3
    retry_delay_seconds: float = 1.0
    payload_template: Optional[str] = None
    enabled: bool = True


@dataclass
class LogNotificationConfig:
    """Configuration for log notifications."""

    log_level: str = "WARNING"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_file: Optional[str] = None
    enabled: bool = True


@dataclass
class ScheduleConfig:
    """Configuration for scheduled monitoring."""

    enabled: bool = False
    interval_minutes: int = 60
    cron_expression: Optional[str] = None
    max_concurrent_checks: int = 3
    timeout_seconds: int = 300
    retry_on_failure: bool = True
    retry_attempts: int = 2
    retry_delay_seconds: float = 30.0


@dataclass
class MonitoringConfig:
    """Complete monitoring configuration."""

    enabled: bool = False
    thresholds: Dict[str, MonitoringThreshold] = field(default_factory=dict)
    email_notifications: Optional[EmailNotificationConfig] = None
    webhook_notifications: Optional[WebhookNotificationConfig] = None
    log_notifications: Optional[LogNotificationConfig] = None
    schedule: Optional[ScheduleConfig] = None
    profiles: List[str] = field(default_factory=list)
    status_types: List[str] = field(
        default_factory=lambda: ["health", "provisioning", "orphaned", "sync"]
    )

    def __post_init__(self):
        """Initialize default thresholds if none provided."""
        if not self.thresholds:
            self.thresholds = self._get_default_thresholds()

    def _get_default_thresholds(self) -> Dict[str, MonitoringThreshold]:
        """Get default monitoring thresholds."""
        return {
            "warning": MonitoringThreshold(
                level=ThresholdLevel.WARNING,
                status_levels=[StatusLevel.WARNING],
                orphaned_assignment_count=5,
                provisioning_failure_count=3,
                sync_delay_hours=24,
            ),
            "critical": MonitoringThreshold(
                level=ThresholdLevel.CRITICAL,
                status_levels=[StatusLevel.CRITICAL, StatusLevel.CONNECTION_FAILED],
                orphaned_assignment_count=20,
                provisioning_failure_count=10,
                sync_delay_hours=72,
            ),
        }


class MonitoringConfigManager:
    """Manages monitoring configuration with validation and defaults."""

    def __init__(self, config: Optional[Config] = None):
        """Initialize the monitoring configuration manager."""
        self.config = config or Config()
        self._monitoring_config: Optional[MonitoringConfig] = None

    def get_monitoring_config(self) -> MonitoringConfig:
        """Get monitoring configuration with environment variable overrides."""
        if self._monitoring_config is None:
            self._monitoring_config = self._load_monitoring_config()
        return self._monitoring_config

    def _load_monitoring_config(self) -> MonitoringConfig:
        """Load monitoring configuration from config file and environment variables."""
        # Start with config file values
        config_data = self.config.get("monitoring", {})

        # Create monitoring config from file data
        monitoring_config = self._create_monitoring_config_from_dict(config_data)

        # Override with environment variables
        monitoring_config = self._apply_environment_overrides(monitoring_config)

        return monitoring_config

    def _create_monitoring_config_from_dict(self, config_data: Dict[str, Any]) -> MonitoringConfig:
        """Create MonitoringConfig from dictionary data."""
        # Extract main configuration
        enabled = config_data.get("enabled", False)
        profiles = config_data.get("profiles", [])
        status_types = config_data.get(
            "status_types", ["health", "provisioning", "orphaned", "sync"]
        )

        # Extract thresholds
        thresholds = {}
        threshold_data = config_data.get("thresholds", {})
        for name, threshold_config in threshold_data.items():
            thresholds[name] = MonitoringThreshold(
                level=ThresholdLevel(threshold_config.get("level", "warning")),
                status_levels=[
                    StatusLevel(level)
                    for level in threshold_config.get("status_levels", ["WARNING"])
                ],
                orphaned_assignment_count=threshold_config.get("orphaned_assignment_count"),
                provisioning_failure_count=threshold_config.get("provisioning_failure_count"),
                sync_delay_hours=threshold_config.get("sync_delay_hours"),
                enabled=threshold_config.get("enabled", True),
            )

        # Extract notification configurations
        email_config = None
        if "email_notifications" in config_data and config_data["email_notifications"] is not None:
            email_data = config_data["email_notifications"]
            email_config = EmailNotificationConfig(
                smtp_server=email_data.get("smtp_server", ""),
                smtp_port=email_data.get("smtp_port", 587),
                username=email_data.get("username", ""),
                password=email_data.get("password", ""),
                from_address=email_data.get("from_address", ""),
                to_addresses=email_data.get("to_addresses") or [],
                use_tls=email_data.get("use_tls", True),
                subject_template=email_data.get(
                    "subject_template", "AWS Identity Center Alert: {level} - {message}"
                ),
                enabled=email_data.get("enabled", True),
            )

        webhook_config = None
        if (
            "webhook_notifications" in config_data
            and config_data["webhook_notifications"] is not None
        ):
            webhook_data = config_data["webhook_notifications"]
            webhook_config = WebhookNotificationConfig(
                url=webhook_data.get("url", ""),
                method=webhook_data.get("method", "POST"),
                headers=webhook_data.get("headers", {}),
                timeout_seconds=webhook_data.get("timeout_seconds", 30),
                retry_attempts=webhook_data.get("retry_attempts", 3),
                retry_delay_seconds=webhook_data.get("retry_delay_seconds", 1.0),
                payload_template=webhook_data.get("payload_template"),
                enabled=webhook_data.get("enabled", True),
            )

        log_config = None
        if "log_notifications" in config_data and config_data["log_notifications"] is not None:
            log_data = config_data["log_notifications"]
            log_config = LogNotificationConfig(
                log_level=log_data.get("log_level", "WARNING"),
                log_format=log_data.get(
                    "log_format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                ),
                log_file=log_data.get("log_file"),
                enabled=log_data.get("enabled", True),
            )

        # Extract schedule configuration
        schedule_config = None
        if "schedule" in config_data and config_data["schedule"] is not None:
            schedule_data = config_data["schedule"]
            schedule_config = ScheduleConfig(
                enabled=schedule_data.get("enabled", False),
                interval_minutes=schedule_data.get("interval_minutes", 60),
                cron_expression=schedule_data.get("cron_expression"),
                max_concurrent_checks=schedule_data.get("max_concurrent_checks", 3),
                timeout_seconds=schedule_data.get("timeout_seconds", 300),
                retry_on_failure=schedule_data.get("retry_on_failure", True),
                retry_attempts=schedule_data.get("retry_attempts", 2),
                retry_delay_seconds=schedule_data.get("retry_delay_seconds", 30.0),
            )

        return MonitoringConfig(
            enabled=enabled,
            thresholds=thresholds,
            email_notifications=email_config,
            webhook_notifications=webhook_config,
            log_notifications=log_config,
            schedule=schedule_config,
            profiles=profiles,
            status_types=status_types,
        )

    def _apply_environment_overrides(self, config: MonitoringConfig) -> MonitoringConfig:
        """Apply environment variable overrides to monitoring configuration."""
        # Override main settings
        config.enabled = self._get_env_bool("AWSIDEMAN_MONITORING_ENABLED", config.enabled)

        # Override email settings
        if config.email_notifications:
            config.email_notifications.enabled = self._get_env_bool(
                "AWSIDEMAN_EMAIL_NOTIFICATIONS_ENABLED", config.email_notifications.enabled
            )
            config.email_notifications.smtp_server = os.environ.get(
                "AWSIDEMAN_EMAIL_SMTP_SERVER", config.email_notifications.smtp_server
            )
            config.email_notifications.username = os.environ.get(
                "AWSIDEMAN_EMAIL_USERNAME", config.email_notifications.username
            )
            config.email_notifications.password = os.environ.get(
                "AWSIDEMAN_EMAIL_PASSWORD", config.email_notifications.password
            )

        # Override webhook settings
        if config.webhook_notifications:
            config.webhook_notifications.enabled = self._get_env_bool(
                "AWSIDEMAN_WEBHOOK_NOTIFICATIONS_ENABLED", config.webhook_notifications.enabled
            )
            config.webhook_notifications.url = os.environ.get(
                "AWSIDEMAN_WEBHOOK_URL", config.webhook_notifications.url
            )

        # Override schedule settings
        if config.schedule:
            config.schedule.enabled = self._get_env_bool(
                "AWSIDEMAN_SCHEDULE_ENABLED", config.schedule.enabled
            )
            config.schedule.interval_minutes = self._get_env_int(
                "AWSIDEMAN_SCHEDULE_INTERVAL_MINUTES", config.schedule.interval_minutes
            )

        return config

    def save_monitoring_config(self, monitoring_config: MonitoringConfig):
        """Save monitoring configuration to config file."""
        # Convert to dictionary
        config_dict = asdict(monitoring_config)

        # Convert enums to strings
        config_dict = self._convert_enums_to_strings(config_dict)

        # Save to config
        self.config.set("monitoring", config_dict)
        self._monitoring_config = monitoring_config

    def _convert_enums_to_strings(self, data: Any) -> Any:
        """Recursively convert enum values to strings."""
        if isinstance(data, dict):
            return {key: self._convert_enums_to_strings(value) for key, value in data.items()}
        elif isinstance(data, list):
            return [self._convert_enums_to_strings(item) for item in data]
        elif isinstance(data, Enum):
            return data.value
        else:
            return data

    def validate_config(self, monitoring_config: MonitoringConfig) -> List[str]:
        """Validate monitoring configuration and return list of errors."""
        errors = []

        if not monitoring_config.enabled:
            return errors  # No validation needed if monitoring is disabled

        # Validate email configuration
        if monitoring_config.email_notifications and monitoring_config.email_notifications.enabled:
            email_config = monitoring_config.email_notifications
            if not email_config.smtp_server:
                errors.append("Email notifications enabled but smtp_server not configured")
            if not email_config.username:
                errors.append("Email notifications enabled but username not configured")
            if not email_config.password:
                errors.append("Email notifications enabled but password not configured")
            if not email_config.from_address:
                errors.append("Email notifications enabled but from_address not configured")
            if not email_config.to_addresses:
                errors.append("Email notifications enabled but to_addresses not configured")

        # Validate webhook configuration
        if (
            monitoring_config.webhook_notifications
            and monitoring_config.webhook_notifications.enabled
        ):
            webhook_config = monitoring_config.webhook_notifications
            if not webhook_config.url:
                errors.append("Webhook notifications enabled but url not configured")

        # Validate profiles
        if monitoring_config.profiles:
            available_profiles = self.config.get("profiles", {})
            for profile in monitoring_config.profiles:
                if profile not in available_profiles:
                    errors.append(
                        f"Profile '{profile}' specified in monitoring config but not found in profiles"
                    )

        # Validate thresholds
        for name, threshold in monitoring_config.thresholds.items():
            if threshold.enabled:
                if not threshold.status_levels:
                    errors.append(f"Threshold '{name}' enabled but no status_levels configured")

        return errors

    def _get_env_bool(self, env_var: str, default: bool) -> bool:
        """Get boolean value from environment variable."""
        value = os.environ.get(env_var)
        if value is None:
            return default
        return value.lower() in ("true", "1", "yes", "on")

    def _get_env_int(self, env_var: str, default: int) -> int:
        """Get integer value from environment variable."""
        value = os.environ.get(env_var)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            logger.warning(
                f"Invalid integer value for {env_var}: {value}. Using default: {default}"
            )
            return default
