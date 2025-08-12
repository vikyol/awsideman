"""Integration tests for monitoring system."""
import asyncio
import os
import tempfile
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.awsideman.utils.config import Config
from src.awsideman.utils.monitoring_config import (
    EmailNotificationConfig,
    LogNotificationConfig,
    MonitoringConfig,
    MonitoringConfigManager,
    MonitoringThreshold,
    ScheduleConfig,
    ThresholdLevel,
)
from src.awsideman.utils.monitoring_scheduler import MonitoringScheduler
from src.awsideman.utils.notification_system import NotificationSystem
from src.awsideman.utils.status_models import (
    HealthStatus,
    ProvisioningStatus,
    StatusLevel,
    StatusReport,
    SummaryStatistics,
)


class TestMonitoringIntegration:
    """Integration tests for the complete monitoring system."""

    def setup_method(self):
        """Setup test method."""
        # Create temporary config directory
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = os.path.join(self.temp_dir, "config.yaml")

        # Mock config to use temporary directory
        self.mock_config = Mock(spec=Config)
        self.mock_config.get_config_file_path.return_value = self.config_file

        # Create test status report
        self.status_report = StatusReport(
            timestamp=datetime.now(),
            overall_health=HealthStatus(
                status=StatusLevel.WARNING,
                message="System experiencing issues",
                details={"connection_count": 5},
                timestamp=datetime.now(),
                errors=[],
            ),
            provisioning_status=ProvisioningStatus(
                active_operations=[],
                failed_operations=[],
                pending_count=0,
                estimated_completion=None,
            ),
            orphaned_assignments=[Mock() for _ in range(6)],  # 6 orphaned assignments
            sync_status=[],
            summary_statistics=SummaryStatistics(
                total_users=100,
                total_groups=10,
                total_permission_sets=5,
                total_assignments=200,
                active_accounts=3,
                last_updated=datetime.now(),
            ),
        )

    def teardown_method(self):
        """Cleanup test method."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_config_manager_integration(self):
        """Test configuration manager integration."""
        # Setup config data
        config_data = {
            "monitoring": {
                "enabled": True,
                "profiles": ["default"],
                "thresholds": {
                    "warning": {
                        "level": "warning",
                        "status_levels": ["WARNING"],
                        "orphaned_assignment_count": 5,
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
                "log_notifications": {"enabled": True, "log_level": "WARNING"},
            }
        }

        self.mock_config.get.return_value = config_data.get("monitoring", {})

        # Test configuration loading
        config_manager = MonitoringConfigManager(self.mock_config)
        monitoring_config = config_manager.get_monitoring_config()

        assert monitoring_config.enabled is True
        assert monitoring_config.profiles == ["default"]
        assert "warning" in monitoring_config.thresholds
        assert monitoring_config.email_notifications is not None
        assert monitoring_config.log_notifications is not None

        # Test validation
        errors = config_manager.validate_config(monitoring_config)
        assert len(errors) == 0

        # Test saving
        monitoring_config.profiles = ["default", "prod"]
        config_manager.save_monitoring_config(monitoring_config)

        self.mock_config.set.assert_called_once()
        saved_data = self.mock_config.set.call_args[0][1]
        assert saved_data["profiles"] == ["default", "prod"]

    @pytest.mark.asyncio
    async def test_notification_system_integration(self):
        """Test notification system integration."""
        # Create monitoring config with log notifications only (for testing)
        monitoring_config = MonitoringConfig(
            enabled=True, log_notifications=LogNotificationConfig(enabled=True, log_level="WARNING")
        )

        # Create notification system
        notification_system = NotificationSystem(monitoring_config)

        # Test sending alert
        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger

            await notification_system.send_alert(
                status_report=self.status_report,
                threshold_level=ThresholdLevel.WARNING,
                message="Integration test alert",
            )

            # Verify log notification was sent
            mock_logger.log.assert_called_once()
            call_args = mock_logger.log.call_args
            assert "Integration test alert" in call_args[0][1]
            assert "Health: WARNING" in call_args[0][1]
            assert "Orphaned assignments: 6" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_scheduler_integration(self):
        """Test scheduler integration."""
        # Create monitoring config with schedule
        monitoring_config = MonitoringConfig(
            enabled=True,
            profiles=["default"],
            schedule=ScheduleConfig(
                enabled=True, interval_minutes=60, max_concurrent_checks=1, timeout_seconds=30
            ),
            log_notifications=LogNotificationConfig(enabled=True),
        )

        # Mock config with profile data
        self.mock_config.get.return_value = {
            "default": {
                "sso_instance_arn": "arn:aws:sso:::instance/ins-123",
                "identity_store_id": "d-123",
                "region": "us-east-1",
            }
        }

        # Create scheduler
        scheduler = MonitoringScheduler(monitoring_config, self.mock_config)

        # Test initialization
        scheduler._initialize_scheduled_checks()
        assert len(scheduler.scheduled_checks) == 1
        assert "default" in scheduler.scheduled_checks

        # Test manual check execution
        with patch(
            "src.awsideman.utils.monitoring_scheduler.StatusOrchestrator"
        ) as mock_orchestrator:
            with patch("src.awsideman.utils.monitoring_scheduler.AWSClientManager"):
                mock_orchestrator_instance = Mock()
                mock_orchestrator_instance.get_comprehensive_status = AsyncMock(
                    return_value=self.status_report
                )
                mock_orchestrator.return_value = mock_orchestrator_instance

                with patch.object(scheduler.notification_system, "send_alert") as mock_send_alert:
                    mock_send_alert.return_value = None

                    result = await scheduler.run_manual_check("default")

                    assert result["success"] is True
                    mock_send_alert.assert_called()  # Should trigger alert due to orphaned assignments

    @pytest.mark.asyncio
    async def test_end_to_end_monitoring_workflow(self):
        """Test complete end-to-end monitoring workflow."""
        # 1. Setup configuration
        config_data = {
            "monitoring": {
                "enabled": True,
                "profiles": ["default"],
                "thresholds": {
                    "warning": {
                        "level": "warning",
                        "status_levels": ["WARNING"],
                        "orphaned_assignment_count": 3,  # Lower threshold for testing
                        "enabled": True,
                    }
                },
                "log_notifications": {"enabled": True, "log_level": "WARNING"},
            }
        }

        self.mock_config.get.side_effect = lambda key, default=None: {
            "monitoring": config_data.get("monitoring", {}),
            "profiles": {
                "default": {
                    "sso_instance_arn": "arn:aws:sso:::instance/ins-123",
                    "identity_store_id": "d-123",
                    "region": "us-east-1",
                }
            },
        }.get(key, default)

        # 2. Load and validate configuration
        config_manager = MonitoringConfigManager(self.mock_config)
        monitoring_config = config_manager.get_monitoring_config()

        errors = config_manager.validate_config(monitoring_config)
        assert len(errors) == 0

        # 3. Create notification system
        notification_system = NotificationSystem(monitoring_config)

        # 4. Test notification
        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger

            await notification_system.send_alert(
                status_report=self.status_report,
                threshold_level=ThresholdLevel.WARNING,
                message="End-to-end test alert",
            )

            # Verify notification was sent
            mock_logger.log.assert_called_once()
            log_message = mock_logger.log.call_args[0][1]
            assert "End-to-end test alert" in log_message
            assert "WARNING" in log_message

        # 5. Create and test scheduler
        scheduler = MonitoringScheduler(monitoring_config, self.mock_config)
        scheduler._initialize_scheduled_checks()

        # 6. Simulate scheduled check execution
        with patch(
            "src.awsideman.utils.monitoring_scheduler.StatusOrchestrator"
        ) as mock_orchestrator:
            with patch("src.awsideman.utils.monitoring_scheduler.AWSClientManager"):
                mock_orchestrator_instance = Mock()
                mock_orchestrator_instance.get_comprehensive_status = AsyncMock(
                    return_value=self.status_report
                )
                mock_orchestrator.return_value = mock_orchestrator_instance

                with patch.object(scheduler.notification_system, "send_alert") as mock_send_alert:
                    mock_send_alert.return_value = None

                    # Execute check
                    check = scheduler.scheduled_checks["default"]
                    semaphore = asyncio.Semaphore(1)

                    await scheduler._execute_scheduled_check(check, semaphore)

                    # Verify alert was triggered
                    mock_send_alert.assert_called_once()
                    call_args = mock_send_alert.call_args
                    assert call_args[1]["threshold_level"] == ThresholdLevel.WARNING
                    assert "Orphaned assignments: 6" in call_args[1]["message"]

    @pytest.mark.asyncio
    async def test_multiple_threshold_evaluation(self):
        """Test evaluation of multiple thresholds."""
        # Create config with multiple thresholds
        monitoring_config = MonitoringConfig(
            enabled=True,
            thresholds={
                "warning": MonitoringThreshold(
                    level=ThresholdLevel.WARNING,
                    status_levels=[StatusLevel.WARNING],
                    orphaned_assignment_count=3,
                ),
                "critical": MonitoringThreshold(
                    level=ThresholdLevel.CRITICAL,
                    status_levels=[StatusLevel.CRITICAL],
                    orphaned_assignment_count=10,
                ),
            },
            log_notifications=LogNotificationConfig(enabled=True),
        )

        # Create scheduler
        scheduler = MonitoringScheduler(monitoring_config, self.mock_config)

        # Test with status that triggers warning but not critical
        status_report_warning = StatusReport(
            timestamp=datetime.now(),
            overall_health=HealthStatus(
                status=StatusLevel.WARNING,
                message="Warning level issue",
                details={},
                timestamp=datetime.now(),
                errors=[],
            ),
            provisioning_status=None,
            orphaned_assignments=[
                Mock() for _ in range(5)
            ],  # 5 orphaned (warning threshold: 3, critical: 10)
            sync_status=[],
            summary_statistics=None,
        )

        with patch.object(scheduler.notification_system, "send_alert") as mock_send_alert:
            mock_send_alert.return_value = None

            await scheduler._evaluate_and_alert(status_report_warning, "test_profile")

            # Should trigger warning threshold only
            assert mock_send_alert.call_count == 1
            call_args = mock_send_alert.call_args
            assert call_args[1]["threshold_level"] == ThresholdLevel.WARNING

    def test_configuration_validation_integration(self):
        """Test comprehensive configuration validation."""
        # Test valid configuration
        valid_config = MonitoringConfig(
            enabled=True,
            profiles=["default"],
            email_notifications=EmailNotificationConfig(
                smtp_server="smtp.example.com",
                username="user@example.com",
                password="password",
                from_address="alerts@example.com",
                to_addresses=["admin@example.com"],
            ),
        )

        self.mock_config.get.return_value = {"default": {}}

        config_manager = MonitoringConfigManager(self.mock_config)
        errors = config_manager.validate_config(valid_config)
        assert len(errors) == 0

        # Test invalid configuration
        invalid_config = MonitoringConfig(
            enabled=True,
            profiles=["nonexistent"],
            email_notifications=EmailNotificationConfig(
                smtp_server="",  # Missing
                username="",  # Missing
                password="password",
                from_address="",  # Missing
                to_addresses=[],  # Empty
            ),
        )

        errors = config_manager.validate_config(invalid_config)
        assert len(errors) > 0

        # Check specific error types
        error_messages = " ".join(errors)
        assert "smtp_server not configured" in error_messages
        assert "username not configured" in error_messages
        assert "from_address not configured" in error_messages
        assert "to_addresses not configured" in error_messages
        assert "Profile 'nonexistent'" in error_messages


if __name__ == "__main__":
    pytest.main([__file__])
