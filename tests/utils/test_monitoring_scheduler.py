"""Tests for monitoring scheduler."""
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.awsideman.utils.config import Config
from src.awsideman.utils.monitoring_config import (
    MonitoringConfig,
    MonitoringThreshold,
    ScheduleConfig,
    ThresholdLevel,
)
from src.awsideman.utils.monitoring_scheduler import MonitoringScheduler, ScheduledCheck
from src.awsideman.utils.status_models import (
    HealthStatus,
    ProvisioningStatus,
    StatusLevel,
    StatusReport,
)


class TestScheduledCheck:
    """Test ScheduledCheck class."""

    def test_scheduled_check_creation(self):
        """Test creating a scheduled check."""
        next_run = datetime.now() + timedelta(minutes=30)
        check = ScheduledCheck(profile_name="default", next_run=next_run)

        assert check.profile_name == "default"
        assert check.next_run == next_run
        assert check.last_run is None
        assert check.consecutive_failures == 0
        assert check.enabled is True


class TestMonitoringScheduler:
    """Test MonitoringScheduler class."""

    def setup_method(self):
        """Setup test method."""
        self.monitoring_config = MonitoringConfig(
            enabled=True,
            profiles=["default", "prod"],
            schedule=ScheduleConfig(
                enabled=True,
                interval_minutes=60,
                max_concurrent_checks=2,
                timeout_seconds=300,
                retry_on_failure=True,
                retry_attempts=2,
            ),
            thresholds={
                "warning": MonitoringThreshold(
                    level=ThresholdLevel.WARNING,
                    status_levels=[StatusLevel.WARNING],
                    orphaned_assignment_count=5,
                )
            },
        )

        self.mock_config = Mock(spec=Config)
        self.mock_config.get.return_value = {
            "default": {
                "sso_instance_arn": "arn:aws:sso:::instance/ins-123",
                "identity_store_id": "d-123",
                "region": "us-east-1",
            },
            "prod": {
                "sso_instance_arn": "arn:aws:sso:::instance/ins-456",
                "identity_store_id": "d-456",
                "region": "us-west-2",
            },
        }

        self.scheduler = MonitoringScheduler(self.monitoring_config, self.mock_config)

    def test_scheduler_creation(self):
        """Test creating monitoring scheduler."""
        assert self.scheduler.monitoring_config == self.monitoring_config
        assert self.scheduler.config == self.mock_config
        assert self.scheduler.running is False
        assert len(self.scheduler.scheduled_checks) == 0

    def test_initialize_scheduled_checks(self):
        """Test initializing scheduled checks."""
        self.scheduler._initialize_scheduled_checks()

        assert len(self.scheduler.scheduled_checks) == 2
        assert "default" in self.scheduler.scheduled_checks
        assert "prod" in self.scheduler.scheduled_checks

        # Check staggered start times
        default_check = self.scheduler.scheduled_checks["default"]
        prod_check = self.scheduler.scheduled_checks["prod"]

        assert default_check.profile_name == "default"
        assert prod_check.profile_name == "prod"
        assert prod_check.next_run > default_check.next_run  # Staggered

    def test_initialize_scheduled_checks_no_profiles(self):
        """Test initializing checks when no profiles specified."""
        self.monitoring_config.profiles = []

        self.scheduler._initialize_scheduled_checks()

        assert len(self.scheduler.scheduled_checks) == 2  # Uses all available profiles
        assert "default" in self.scheduler.scheduled_checks
        assert "prod" in self.scheduler.scheduled_checks

    def test_get_due_checks(self):
        """Test getting due checks."""
        now = datetime.now()

        # Create checks with different next run times
        self.scheduler.scheduled_checks = {
            "due": ScheduledCheck("due", next_run=now - timedelta(minutes=5)),
            "not_due": ScheduledCheck("not_due", next_run=now + timedelta(minutes=5)),
            "disabled": ScheduledCheck(
                "disabled", next_run=now - timedelta(minutes=5), enabled=False
            ),
        }

        due_checks = self.scheduler._get_due_checks()

        assert len(due_checks) == 1
        assert due_checks[0].profile_name == "due"

    def test_schedule_next_run(self):
        """Test scheduling next run."""
        check = ScheduledCheck("test", next_run=datetime.now())
        original_time = check.next_run

        self.scheduler._schedule_next_run(check)

        # Should be scheduled 60 minutes later (interval_minutes)
        expected_time = original_time + timedelta(minutes=60)
        assert abs((check.next_run - expected_time).total_seconds()) < 60  # Within 1 minute

    def test_schedule_next_run_with_failures(self):
        """Test scheduling next run with consecutive failures."""
        check = ScheduledCheck("test", next_run=datetime.now(), consecutive_failures=2)
        original_time = check.next_run

        self.scheduler._schedule_next_run(check)

        # Should be scheduled with delay multiplier (2x)
        expected_time = original_time + timedelta(minutes=120)  # 60 * 2
        assert abs((check.next_run - expected_time).total_seconds()) < 60

    def test_schedule_next_run_disabled(self):
        """Test scheduling next run for disabled check."""
        check = ScheduledCheck("test", next_run=datetime.now(), enabled=False)
        original_time = check.next_run

        self.scheduler._schedule_next_run(check)

        # Should not change next_run for disabled checks
        assert check.next_run == original_time

    def test_handle_check_failure(self):
        """Test handling check failure."""
        check = ScheduledCheck("test", next_run=datetime.now())

        self.scheduler._handle_check_failure(check, "Test error")

        assert check.consecutive_failures == 1
        assert check.enabled is True  # Should still be enabled

    def test_handle_check_failure_disable_after_max(self):
        """Test disabling check after max consecutive failures."""
        check = ScheduledCheck("test", next_run=datetime.now(), consecutive_failures=4)

        self.scheduler._handle_check_failure(check, "Test error")

        assert check.consecutive_failures == 5
        assert check.enabled is False  # Should be disabled

    @pytest.mark.asyncio
    @patch("src.awsideman.utils.monitoring_scheduler.StatusOrchestrator")
    @patch("src.awsideman.utils.monitoring_scheduler.AWSClientManager")
    async def test_execute_scheduled_check_success(self, mock_aws_client, mock_orchestrator):
        """Test successful execution of scheduled check."""
        # Setup mocks
        mock_status_report = Mock(spec=StatusReport)
        mock_orchestrator_instance = Mock()
        mock_orchestrator_instance.get_comprehensive_status.return_value = mock_status_report
        mock_orchestrator.return_value = mock_orchestrator_instance

        # Create check
        check = ScheduledCheck("default", next_run=datetime.now())
        semaphore = asyncio.Semaphore(1)

        with patch.object(self.scheduler, "_evaluate_and_alert") as mock_evaluate:
            mock_evaluate.return_value = None

            await self.scheduler._execute_scheduled_check(check, semaphore)

        assert check.consecutive_failures == 0
        assert check.last_run is not None
        mock_evaluate.assert_called_once_with(mock_status_report, "default")

    @pytest.mark.asyncio
    async def test_execute_scheduled_check_missing_profile(self):
        """Test executing check for missing profile."""
        self.mock_config.get.return_value = {}  # No profiles

        check = ScheduledCheck("missing", next_run=datetime.now())
        semaphore = asyncio.Semaphore(1)

        await self.scheduler._execute_scheduled_check(check, semaphore)

        # Check should be rescheduled but not marked as failed
        assert check.consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_execute_scheduled_check_timeout(self):
        """Test executing check with timeout."""
        # Mock timeout
        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            check = ScheduledCheck("default", next_run=datetime.now())
            semaphore = asyncio.Semaphore(1)

            await self.scheduler._execute_scheduled_check(check, semaphore)

        assert check.consecutive_failures == 1

    @pytest.mark.asyncio
    @patch("src.awsideman.utils.monitoring_scheduler.NotificationSystem")
    async def test_send_failure_notification(self, mock_notification_system):
        """Test sending failure notification."""
        mock_system = Mock()
        mock_system.send_alert = AsyncMock()
        mock_notification_system.return_value = mock_system

        await self.scheduler._send_failure_notification("test_profile", "Test error")

        mock_system.send_alert.assert_called_once()
        call_args = mock_system.send_alert.call_args
        assert call_args[1]["threshold_level"] == ThresholdLevel.CRITICAL
        assert "test_profile" in call_args[1]["message"]
        assert "Test error" in call_args[1]["message"]

    @pytest.mark.asyncio
    async def test_evaluate_and_alert_no_triggers(self):
        """Test evaluating status with no alert triggers."""
        status_report = StatusReport(
            timestamp=datetime.now(),
            overall_health=HealthStatus(
                status=StatusLevel.HEALTHY,
                message="All good",
                details={},
                timestamp=datetime.now(),
                errors=[],
            ),
            provisioning_status=ProvisioningStatus(
                active_operations=[],
                failed_operations=[],
                pending_count=0,
                estimated_completion=None,
            ),
            orphaned_assignments=[],
            sync_status=[],
            summary_statistics=None,
        )

        with patch.object(self.scheduler.notification_system, "send_alert") as mock_send:
            await self.scheduler._evaluate_and_alert(status_report, "test_profile")

            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_evaluate_and_alert_health_trigger(self):
        """Test evaluating status with health status trigger."""
        status_report = StatusReport(
            timestamp=datetime.now(),
            overall_health=HealthStatus(
                status=StatusLevel.WARNING,  # Matches threshold
                message="System warning",
                details={},
                timestamp=datetime.now(),
                errors=[],
            ),
            provisioning_status=None,
            orphaned_assignments=[],
            sync_status=[],
            summary_statistics=None,
        )

        with patch.object(self.scheduler.notification_system, "send_alert") as mock_send:
            mock_send.return_value = None

            await self.scheduler._evaluate_and_alert(status_report, "test_profile")

            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert call_args[1]["threshold_level"] == ThresholdLevel.WARNING
            assert "Health status: WARNING" in call_args[1]["message"]

    @pytest.mark.asyncio
    async def test_evaluate_and_alert_orphaned_assignments_trigger(self):
        """Test evaluating status with orphaned assignments trigger."""
        # Create 6 orphaned assignments (threshold is 5)
        orphaned_assignments = [Mock() for _ in range(6)]

        status_report = StatusReport(
            timestamp=datetime.now(),
            overall_health=HealthStatus(
                status=StatusLevel.HEALTHY,
                message="All good",
                details={},
                timestamp=datetime.now(),
                errors=[],
            ),
            provisioning_status=None,
            orphaned_assignments=orphaned_assignments,
            sync_status=[],
            summary_statistics=None,
        )

        with patch.object(self.scheduler.notification_system, "send_alert") as mock_send:
            mock_send.return_value = None

            await self.scheduler._evaluate_and_alert(status_report, "test_profile")

            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert call_args[1]["threshold_level"] == ThresholdLevel.WARNING
            assert "Orphaned assignments: 6" in call_args[1]["message"]

    def test_get_status(self):
        """Test getting scheduler status."""
        # Initialize some checks
        self.scheduler._initialize_scheduled_checks()

        status = self.scheduler.get_status()

        assert status["running"] is False
        assert status["enabled"] is True
        assert len(status["scheduled_checks"]) == 2
        assert "configuration" in status

        config = status["configuration"]
        assert config["interval_minutes"] == 60
        assert config["max_concurrent_checks"] == 2
        assert config["timeout_seconds"] == 300
        assert config["retry_on_failure"] is True

    @pytest.mark.asyncio
    async def test_run_manual_check_success(self):
        """Test running manual check successfully."""
        self.scheduler._initialize_scheduled_checks()

        with patch.object(self.scheduler, "_execute_scheduled_check") as mock_execute:
            mock_execute.return_value = None

            result = await self.scheduler.run_manual_check("default")

            assert result["success"] is True
            assert "default" in result["message"]
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_manual_check_invalid_profile(self):
        """Test running manual check for invalid profile."""
        with pytest.raises(ValueError, match="not configured for monitoring"):
            await self.scheduler.run_manual_check("nonexistent")

    @pytest.mark.asyncio
    async def test_run_manual_check_failure(self):
        """Test running manual check with failure."""
        self.scheduler._initialize_scheduled_checks()

        with patch.object(self.scheduler, "_execute_scheduled_check") as mock_execute:
            mock_execute.side_effect = Exception("Test error")

            result = await self.scheduler.run_manual_check("default")

            assert result["success"] is False
            assert "Test error" in result["message"]
            assert "error" in result

    def test_scheduler_disabled_monitoring(self):
        """Test scheduler with disabled monitoring."""
        self.monitoring_config.enabled = False

        # Should not start
        with patch("asyncio.run") as mock_run:
            self.scheduler.start()
            mock_run.assert_not_called()

    def test_scheduler_disabled_schedule(self):
        """Test scheduler with disabled schedule."""
        self.monitoring_config.schedule.enabled = False

        # Should not start
        with patch("asyncio.run") as mock_run:
            self.scheduler.start()
            mock_run.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__])
