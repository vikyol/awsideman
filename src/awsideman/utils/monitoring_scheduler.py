"""Scheduler for automated monitoring checks."""

import asyncio
import logging
import signal
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ..aws_clients.manager import AWSClientManager
from ..utils.config import Config
from .monitoring_config import MonitoringConfig, ThresholdLevel
from .notification_system import NotificationSystem
from .status_models import StatusLevel, StatusReport
from .status_orchestrator import StatusOrchestrator

logger = logging.getLogger(__name__)


@dataclass
class ScheduledCheck:
    """Represents a scheduled monitoring check."""

    profile_name: str
    next_run: datetime
    last_run: Optional[datetime] = None
    consecutive_failures: int = 0
    enabled: bool = True


class MonitoringScheduler:
    """Handles scheduled execution of monitoring checks."""

    def __init__(self, monitoring_config: MonitoringConfig, config: Optional[Config] = None):
        """Initialize the monitoring scheduler."""
        self.monitoring_config = monitoring_config
        self.config = config or Config()
        self.notification_system = NotificationSystem(monitoring_config)
        self.scheduled_checks: Dict[str, ScheduledCheck] = {}
        self.running = False
        self._shutdown_event = asyncio.Event()
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""

        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            self.stop()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def start(self):
        """Start the monitoring scheduler."""
        if not self.monitoring_config.enabled or not self.monitoring_config.schedule:
            logger.warning("Monitoring or scheduling is disabled")
            return

        if not self.monitoring_config.schedule.enabled:
            logger.warning("Schedule is disabled in monitoring configuration")
            return

        logger.info("Starting monitoring scheduler...")
        self.running = True
        self._initialize_scheduled_checks()

        # Run the scheduler
        asyncio.run(self._run_scheduler())

    def stop(self):
        """Stop the monitoring scheduler."""
        logger.info("Stopping monitoring scheduler...")
        self.running = False
        self._shutdown_event.set()

    def _initialize_scheduled_checks(self):
        """Initialize scheduled checks for configured profiles."""
        profiles = self.monitoring_config.profiles
        if not profiles:
            # Use all available profiles if none specified
            profiles = list(self.config.get("profiles", {}).keys())

        now = datetime.now()

        for profile_name in profiles:
            # Stagger initial runs to avoid overwhelming the system
            stagger_minutes = len(self.scheduled_checks) * 2
            next_run = now + timedelta(minutes=stagger_minutes)

            self.scheduled_checks[profile_name] = ScheduledCheck(
                profile_name=profile_name, next_run=next_run
            )

        logger.info(f"Initialized {len(self.scheduled_checks)} scheduled checks")

    async def _run_scheduler(self):
        """Main scheduler loop."""
        logger.info("Monitoring scheduler started")

        while self.running:
            try:
                # Check for due monitoring checks
                due_checks = self._get_due_checks()

                if due_checks:
                    # Limit concurrent checks
                    max_concurrent = self.monitoring_config.schedule.max_concurrent_checks
                    semaphore = asyncio.Semaphore(max_concurrent)

                    # Execute due checks concurrently
                    tasks = [
                        self._execute_scheduled_check(check, semaphore) for check in due_checks
                    ]

                    await asyncio.gather(*tasks, return_exceptions=True)

                # Wait before next iteration or until shutdown
                try:
                    await asyncio.wait_for(self._shutdown_event.wait(), timeout=60)
                    break  # Shutdown requested
                except asyncio.TimeoutError:
                    continue  # Continue normal operation

            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                await asyncio.sleep(60)  # Wait before retrying

        logger.info("Monitoring scheduler stopped")

    def _get_due_checks(self) -> List[ScheduledCheck]:
        """Get list of checks that are due to run."""
        now = datetime.now()
        due_checks = []

        for check in self.scheduled_checks.values():
            if check.enabled and check.next_run <= now:
                due_checks.append(check)

        return due_checks

    async def _execute_scheduled_check(self, check: ScheduledCheck, semaphore: asyncio.Semaphore):
        """Execute a scheduled monitoring check."""
        async with semaphore:
            try:
                logger.info(f"Executing scheduled check for profile: {check.profile_name}")

                # Get profile configuration
                profiles = self.config.get("profiles", {})
                if check.profile_name not in profiles:
                    logger.error(f"Profile '{check.profile_name}' not found")
                    self._schedule_next_run(check)
                    return

                profile_data = profiles[check.profile_name]

                # Validate SSO instance configuration
                instance_arn = profile_data.get("sso_instance_arn")
                identity_store_id = profile_data.get("identity_store_id")

                if not instance_arn or not identity_store_id:
                    logger.error(f"Profile '{check.profile_name}' missing SSO configuration")
                    self._schedule_next_run(check)
                    return

                # Initialize AWS client
                region = profile_data.get("region")
                aws_client = AWSClientManager(profile=check.profile_name, region=region)

                # Create status orchestrator with timeout
                from ..utils.status_infrastructure import StatusCheckConfig

                status_config = StatusCheckConfig(
                    timeout_seconds=self.monitoring_config.schedule.timeout_seconds,
                    enable_parallel_checks=True,
                    max_concurrent_checks=3,
                    retry_attempts=1,
                    retry_delay_seconds=5.0,
                )

                orchestrator = StatusOrchestrator(aws_client, status_config)

                # Execute status check with timeout
                status_report = await asyncio.wait_for(
                    orchestrator.get_comprehensive_status(),
                    timeout=self.monitoring_config.schedule.timeout_seconds,
                )

                # Evaluate thresholds and send alerts
                await self._evaluate_and_alert(status_report, check.profile_name)

                # Update check status
                check.last_run = datetime.now()
                check.consecutive_failures = 0

                logger.info(
                    f"Scheduled check completed successfully for profile: {check.profile_name}"
                )

            except asyncio.TimeoutError:
                logger.error(f"Scheduled check timed out for profile: {check.profile_name}")
                self._handle_check_failure(check, "Check timed out")

            except Exception as e:
                logger.error(f"Scheduled check failed for profile {check.profile_name}: {e}")
                self._handle_check_failure(check, str(e))

            finally:
                self._schedule_next_run(check)

    def _handle_check_failure(self, check: ScheduledCheck, error_message: str):
        """Handle failure of a scheduled check."""
        check.consecutive_failures += 1

        # Disable check if too many consecutive failures
        if check.consecutive_failures >= 5:
            logger.warning(
                f"Disabling check for profile {check.profile_name} after {check.consecutive_failures} consecutive failures"
            )
            check.enabled = False

        # Send failure notification if retry is disabled or max attempts reached
        if (
            not self.monitoring_config.schedule.retry_on_failure
            or check.consecutive_failures >= self.monitoring_config.schedule.retry_attempts
        ):
            asyncio.create_task(self._send_failure_notification(check.profile_name, error_message))

    async def _send_failure_notification(self, profile_name: str, error_message: str):
        """Send notification about check failure."""
        try:
            # Create minimal status report for failure notification
            from ..utils.status_models import HealthStatus

            health_status = HealthStatus(
                status=StatusLevel.CRITICAL,
                message=f"Monitoring check failed: {error_message}",
                details={"profile": profile_name, "error": error_message},
                timestamp=datetime.now(),
                errors=[error_message],
            )

            status_report = StatusReport(
                timestamp=datetime.now(),
                overall_health=health_status,
                provisioning_status=None,
                orphaned_assignment_status=[],
                sync_status=[],
                summary_statistics=None,
            )

            await self.notification_system.send_alert(
                status_report=status_report,
                threshold_level=ThresholdLevel.CRITICAL,
                message=f"Monitoring check failed for profile '{profile_name}': {error_message}",
            )

        except Exception as e:
            logger.error(f"Failed to send failure notification: {e}")

    def _schedule_next_run(self, check: ScheduledCheck):
        """Schedule the next run for a check."""
        if not check.enabled:
            return

        interval = timedelta(minutes=self.monitoring_config.schedule.interval_minutes)

        # Add extra delay for failed checks
        if check.consecutive_failures > 0:
            delay_multiplier = min(check.consecutive_failures, 5)  # Cap at 5x delay
            interval = interval * delay_multiplier

        check.next_run = datetime.now() + interval

        logger.debug(f"Next run for profile {check.profile_name} scheduled at {check.next_run}")

    async def _evaluate_and_alert(self, status_report: StatusReport, profile_name: str):
        """Evaluate status report against thresholds and send alerts."""
        try:
            alerts_sent = []

            # Check each threshold
            for threshold_name, threshold in self.monitoring_config.thresholds.items():
                if not threshold.enabled:
                    continue

                alert_triggered = False
                alert_reasons = []

                # Check overall health status
                if (
                    status_report.overall_health
                    and status_report.overall_health.status in threshold.status_levels
                ):
                    alert_triggered = True
                    alert_reasons.append(
                        f"Health status: {status_report.overall_health.status.value}"
                    )

                # Check orphaned assignments count
                if (
                    threshold.orphaned_assignment_count is not None
                    and len(status_report.orphaned_assignment_status)
                    >= threshold.orphaned_assignment_count
                ):
                    alert_triggered = True
                    alert_reasons.append(
                        f"Orphaned assignments: {len(status_report.orphaned_assignment_status)}"
                    )

                # Check provisioning failures
                if (
                    threshold.provisioning_failure_count is not None
                    and status_report.provisioning_status
                    and len(status_report.provisioning_status.failed_operations)
                    >= threshold.provisioning_failure_count
                ):
                    alert_triggered = True
                    alert_reasons.append(
                        f"Provisioning failures: {len(status_report.provisioning_status.failed_operations)}"
                    )

                # Check sync delays
                if threshold.sync_delay_hours is not None and status_report.sync_status:
                    now = datetime.now()
                    for sync_status in status_report.sync_status:
                        if (
                            sync_status.last_sync_time
                            and (now - sync_status.last_sync_time).total_seconds() / 3600
                            >= threshold.sync_delay_hours
                        ):
                            alert_triggered = True
                            alert_reasons.append(f"Sync delay: {sync_status.provider_name}")

                # Send alert if threshold triggered
                if alert_triggered:
                    message = f"Profile '{profile_name}' triggered {threshold.level.value} threshold: {', '.join(alert_reasons)}"

                    await self.notification_system.send_alert(
                        status_report=status_report,
                        threshold_level=threshold.level,
                        message=message,
                    )

                    alerts_sent.append(threshold_name)
                    logger.info(
                        f"Alert sent for profile {profile_name}, threshold: {threshold_name}"
                    )

            if not alerts_sent:
                logger.debug(f"No alerts triggered for profile {profile_name}")

        except Exception as e:
            logger.error(f"Error evaluating thresholds for profile {profile_name}: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get current scheduler status."""
        return {
            "running": self.running,
            "enabled": self.monitoring_config.enabled and self.monitoring_config.schedule.enabled,
            "scheduled_checks": {
                name: {
                    "profile_name": check.profile_name,
                    "next_run": check.next_run.isoformat(),
                    "last_run": check.last_run.isoformat() if check.last_run else None,
                    "consecutive_failures": check.consecutive_failures,
                    "enabled": check.enabled,
                }
                for name, check in self.scheduled_checks.items()
            },
            "configuration": {
                "interval_minutes": self.monitoring_config.schedule.interval_minutes,
                "max_concurrent_checks": self.monitoring_config.schedule.max_concurrent_checks,
                "timeout_seconds": self.monitoring_config.schedule.timeout_seconds,
                "retry_on_failure": self.monitoring_config.schedule.retry_on_failure,
            },
        }

    async def run_manual_check(self, profile_name: str) -> Dict[str, Any]:
        """Run a manual monitoring check for a specific profile."""
        if profile_name not in self.scheduled_checks:
            raise ValueError(f"Profile '{profile_name}' not configured for monitoring")

        check = self.scheduled_checks[profile_name]
        semaphore = asyncio.Semaphore(1)

        try:
            await self._execute_scheduled_check(check, semaphore)
            return {
                "success": True,
                "message": f"Manual check completed for profile '{profile_name}'",
                "last_run": check.last_run.isoformat() if check.last_run else None,
                "consecutive_failures": check.consecutive_failures,
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Manual check failed for profile '{profile_name}': {e}",
                "error": str(e),
            }


def main():
    """Main entry point for running the monitoring scheduler as a standalone service."""
    import argparse

    parser = argparse.ArgumentParser(description="AWS Identity Center Monitoring Scheduler")
    parser.add_argument("--config-file", help="Path to configuration file")
    parser.add_argument(
        "--log-level", default="INFO", help="Log level (DEBUG, INFO, WARNING, ERROR)"
    )
    parser.add_argument("--log-file", help="Path to log file")

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(args.log_file) if args.log_file else logging.StreamHandler(),
        ],
    )

    try:
        # Load configuration
        config = Config()

        # Load monitoring configuration
        from .monitoring_config import MonitoringConfigManager

        config_manager = MonitoringConfigManager(config)
        monitoring_config = config_manager.get_monitoring_config()

        # Validate configuration
        errors = config_manager.validate_config(monitoring_config)
        if errors:
            logger.error("Configuration validation failed:")
            for error in errors:
                logger.error(f"  - {error}")
            sys.exit(1)

        # Create and start scheduler
        scheduler = MonitoringScheduler(monitoring_config, config)
        scheduler.start()

    except KeyboardInterrupt:
        logger.info("Scheduler interrupted by user")
    except Exception as e:
        logger.error(f"Scheduler failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
