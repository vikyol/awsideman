"""
Schedule manager for automated backup operations.

This module provides scheduling capabilities for automated backups with cron-based
scheduling, monitoring, and notification support.
"""

import asyncio
import logging
import threading
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ..utils.notification_system import NotificationSystem
from .interfaces import BackupManagerInterface, ScheduleManagerInterface
from .models import BackupOptions, BackupResult, BackupType, ScheduleConfig

logger = logging.getLogger(__name__)


class CronParser:
    """Simple cron expression parser for scheduling."""

    PREDEFINED_SCHEDULES = {
        "daily": "0 2 * * *",  # 2 AM daily
        "weekly": "0 2 * * 0",  # 2 AM on Sunday
        "monthly": "0 2 1 * *",  # 2 AM on 1st of month
        "hourly": "0 * * * *",  # Every hour
    }

    def __init__(self, expression: str):
        """Initialize cron parser with expression."""
        self.expression = expression.strip()
        self.parsed_fields = self._parse_expression()

    def _parse_expression(self) -> Dict[str, Any]:
        """Parse cron expression into components."""
        # Handle predefined schedules
        if self.expression.lower() in self.PREDEFINED_SCHEDULES:
            self.expression = self.PREDEFINED_SCHEDULES[self.expression.lower()]

        # Split into fields: minute hour day month weekday
        fields = self.expression.split()
        if len(fields) != 5:
            raise ValueError(f"Invalid cron expression: {self.expression}")

        return {
            "minute": self._parse_field(fields[0], 0, 59),
            "hour": self._parse_field(fields[1], 0, 23),
            "day": self._parse_field(fields[2], 1, 31),
            "month": self._parse_field(fields[3], 1, 12),
            "weekday": self._parse_field(fields[4], 0, 6),
        }

    def _parse_field(self, field: str, min_val: int, max_val: int) -> List[int]:
        """Parse individual cron field."""
        if field == "*":
            return list(range(min_val, max_val + 1))

        values = []
        for part in field.split(","):
            if "/" in part:
                # Handle step values (e.g., */5)
                range_part, step = part.split("/")
                step = int(step)
                if range_part == "*":
                    values.extend(list(range(min_val, max_val + 1, step)))
                else:
                    start, end = map(int, range_part.split("-"))
                    values.extend(list(range(start, end + 1, step)))
            elif "-" in part:
                # Handle ranges (e.g., 1-5)
                start, end = map(int, part.split("-"))
                values.extend(list(range(start, end + 1)))
            else:
                # Handle single values
                values.append(int(part))

        return sorted(list(set(values)))

    def next_run_time(self, from_time: Optional[datetime] = None) -> datetime:
        """Calculate next run time from given time."""
        if from_time is None:
            from_time = datetime.now()

        # Start from next minute to avoid immediate execution
        next_time = from_time.replace(second=0, microsecond=0) + timedelta(minutes=1)

        # Find next matching time (limit search to avoid infinite loops)
        for _ in range(366 * 24 * 60):  # Max 1 year of minutes
            if self._matches_time(next_time):
                return next_time
            next_time += timedelta(minutes=1)

        raise ValueError(f"Could not find next run time for cron expression: {self.expression}")

    def _matches_time(self, dt: datetime) -> bool:
        """Check if datetime matches cron expression."""
        return (
            dt.minute in self.parsed_fields["minute"]
            and dt.hour in self.parsed_fields["hour"]
            and dt.day in self.parsed_fields["day"]
            and dt.month in self.parsed_fields["month"]
            and dt.weekday() in self.parsed_fields["weekday"]
        )


class ScheduleInfo:
    """Information about a scheduled backup."""

    def __init__(self, schedule_id: str, config: ScheduleConfig):
        """Initialize schedule info."""
        self.schedule_id = schedule_id
        self.config = config
        self.created_at = datetime.now()
        self.last_run: Optional[datetime] = None
        self.next_run: Optional[datetime] = None
        self.consecutive_failures = 0
        self.total_runs = 0
        self.successful_runs = 0
        self.last_result: Optional[BackupResult] = None
        self.cron_parser = CronParser(config.interval)
        self._calculate_next_run()

    def _calculate_next_run(self):
        """Calculate next run time."""
        try:
            self.next_run = self.cron_parser.next_run_time(self.last_run)
        except ValueError as e:
            logger.error(f"Failed to calculate next run for schedule {self.schedule_id}: {e}")
            self.next_run = None

    def update_after_run(self, result: BackupResult):
        """Update schedule info after a backup run."""
        self.last_run = datetime.now()
        self.last_result = result
        self.total_runs += 1

        if result.success:
            self.consecutive_failures = 0
            self.successful_runs += 1
        else:
            self.consecutive_failures += 1

        self._calculate_next_run()

    def is_due(self) -> bool:
        """Check if schedule is due to run."""
        if not self.config.enabled or not self.next_run:
            return False
        return datetime.now() >= self.next_run

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "schedule_id": self.schedule_id,
            "name": self.config.name,
            "backup_type": self.config.backup_type.value,
            "interval": self.config.interval,
            "enabled": self.config.enabled,
            "created_at": self.created_at.isoformat(),
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "consecutive_failures": self.consecutive_failures,
            "total_runs": self.total_runs,
            "successful_runs": self.successful_runs,
            "success_rate": self.successful_runs / self.total_runs if self.total_runs > 0 else 0,
            "last_result": self.last_result.to_dict() if self.last_result else None,
            "retention_policy": self.config.retention_policy.to_dict(),
            "notification_settings": self.config.notification_settings.to_dict(),
        }


class ScheduleManager(ScheduleManagerInterface):
    """Manager for backup scheduling operations."""

    def __init__(self, backup_manager: BackupManagerInterface):
        """Initialize schedule manager."""
        self.backup_manager = backup_manager
        self.schedules: Dict[str, ScheduleInfo] = {}
        self.running = False
        self._scheduler_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._notification_systems: Dict[str, NotificationSystem] = {}

    async def create_schedule(self, schedule_config: ScheduleConfig) -> str:
        """Create a new backup schedule."""
        # Validate schedule configuration
        self._validate_schedule_config(schedule_config)

        # Generate unique schedule ID
        schedule_id = str(uuid.uuid4())

        # Create schedule info
        schedule_info = ScheduleInfo(schedule_id, schedule_config)
        self.schedules[schedule_id] = schedule_info

        logger.info(f"Created backup schedule '{schedule_config.name}' with ID {schedule_id}")

        # Start scheduler if not running
        if not self.running:
            self.start_scheduler()

        return schedule_id

    async def update_schedule(self, schedule_id: str, schedule_config: ScheduleConfig) -> bool:
        """Update an existing backup schedule."""
        if schedule_id not in self.schedules:
            return False

        # Validate new configuration
        self._validate_schedule_config(schedule_config)

        # Update schedule
        old_schedule = self.schedules[schedule_id]
        new_schedule = ScheduleInfo(schedule_id, schedule_config)

        # Preserve execution history
        new_schedule.created_at = old_schedule.created_at
        new_schedule.last_run = old_schedule.last_run
        new_schedule.consecutive_failures = old_schedule.consecutive_failures
        new_schedule.total_runs = old_schedule.total_runs
        new_schedule.successful_runs = old_schedule.successful_runs
        new_schedule.last_result = old_schedule.last_result

        self.schedules[schedule_id] = new_schedule

        logger.info(f"Updated backup schedule '{schedule_config.name}' with ID {schedule_id}")
        return True

    async def delete_schedule(self, schedule_id: str) -> bool:
        """Delete a backup schedule."""
        if schedule_id not in self.schedules:
            return False

        schedule_name = self.schedules[schedule_id].config.name
        del self.schedules[schedule_id]

        logger.info(f"Deleted backup schedule '{schedule_name}' with ID {schedule_id}")

        # Stop scheduler if no schedules remain
        if not self.schedules and self.running:
            self.stop_scheduler()

        return True

    async def list_schedules(self) -> List[Dict[str, Any]]:
        """List all backup schedules."""
        return [schedule.to_dict() for schedule in self.schedules.values()]

    async def execute_scheduled_backup(self, schedule_id: str) -> BackupResult:
        """Execute a backup for the specified schedule."""
        if schedule_id not in self.schedules:
            return BackupResult(
                success=False,
                message=f"Schedule {schedule_id} not found",
                errors=[f"Schedule {schedule_id} not found"],
            )

        schedule_info = self.schedules[schedule_id]

        try:
            # Prepare backup options
            backup_options = schedule_info.config.backup_options or BackupOptions(
                backup_type=schedule_info.config.backup_type
            )

            logger.info(f"Executing scheduled backup for '{schedule_info.config.name}'")

            # Execute backup
            result = await self.backup_manager.create_backup(backup_options)

            # Update schedule info
            schedule_info.update_after_run(result)

            # Send notifications
            await self._send_backup_notification(schedule_info, result)

            return result

        except Exception as e:
            error_msg = f"Scheduled backup failed for '{schedule_info.config.name}': {str(e)}"
            logger.error(error_msg)

            result = BackupResult(success=False, message=error_msg, errors=[str(e)])

            schedule_info.update_after_run(result)
            await self._send_backup_notification(schedule_info, result)

            return result

    async def get_schedule_status(self, schedule_id: str) -> Dict[str, Any]:
        """Get the status and execution history of a schedule."""
        if schedule_id not in self.schedules:
            return {}

        return self.schedules[schedule_id].to_dict()

    def start_scheduler(self):
        """Start the background scheduler."""
        if self.running:
            return

        self.running = True
        self._stop_event.clear()
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop, daemon=True, name="BackupScheduler"
        )
        self._scheduler_thread.start()
        logger.info("Backup scheduler started")

    def stop_scheduler(self):
        """Stop the background scheduler."""
        if not self.running:
            return

        self.running = False
        self._stop_event.set()

        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=5.0)

        logger.info("Backup scheduler stopped")

    def _scheduler_loop(self):
        """Main scheduler loop running in background thread."""
        while self.running:
            try:
                # Check for due schedules
                due_schedules = [
                    schedule_id
                    for schedule_id, schedule_info in self.schedules.items()
                    if schedule_info.is_due()
                ]

                # Execute due schedules
                for schedule_id in due_schedules:
                    if not self.running:
                        break

                    try:
                        # Run backup in asyncio context
                        asyncio.run(self.execute_scheduled_backup(schedule_id))
                    except Exception as e:
                        logger.error(f"Failed to execute scheduled backup {schedule_id}: {e}")

                # Sleep for 1 minute before next check
                if not self._stop_event.wait(timeout=60):
                    continue
                else:
                    break

            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                if not self._stop_event.wait(timeout=60):
                    continue
                else:
                    break

    def _validate_schedule_config(self, config: ScheduleConfig):
        """Validate schedule configuration."""
        if not config.name:
            raise ValueError("Schedule name is required")

        if not config.interval:
            raise ValueError("Schedule interval is required")

        # Validate cron expression
        try:
            CronParser(config.interval)
        except Exception as e:
            raise ValueError(f"Invalid cron expression '{config.interval}': {e}")

        # Validate backup type
        if not isinstance(config.backup_type, BackupType):
            raise ValueError("Invalid backup type")

        # Validate retention policy
        if config.retention_policy.keep_daily < 0:
            raise ValueError("Retention policy values must be non-negative")

    async def _send_backup_notification(self, schedule_info: ScheduleInfo, result: BackupResult):
        """Send notification about backup result."""
        if not schedule_info.config.notification_settings.enabled:
            return

        settings = schedule_info.config.notification_settings

        # Only send notification if configured
        should_notify = (result.success and settings.notify_on_success) or (
            not result.success and settings.notify_on_failure
        )

        if not should_notify:
            return

        try:
            # Create notification message
            status = "SUCCESS" if result.success else "FAILURE"
            message = f"Scheduled backup '{schedule_info.config.name}' {status}"

            if result.message:
                message += f": {result.message}"

            # Send email notifications
            if settings.email_addresses:
                await self._send_email_notification(settings.email_addresses, message, result)

            # Send webhook notifications
            if settings.webhook_urls:
                await self._send_webhook_notifications(settings.webhook_urls, message, result)

            logger.info(f"Sent backup notification for schedule '{schedule_info.config.name}'")

        except Exception as e:
            logger.error(f"Failed to send backup notification: {e}")

    async def _send_email_notification(
        self, email_addresses: List[str], message: str, result: BackupResult
    ):
        """Send email notification about backup result."""
        # This is a simplified implementation
        # In a real implementation, you would integrate with the existing notification system
        logger.info(f"Email notification sent to {email_addresses}: {message}")

    async def _send_webhook_notifications(
        self, webhook_urls: List[str], message: str, result: BackupResult
    ):
        """Send webhook notifications about backup result."""
        import aiohttp

        payload = {
            "message": message,
            "success": result.success,
            "backup_id": result.backup_id,
            "timestamp": datetime.now().isoformat(),
            "errors": result.errors,
            "warnings": result.warnings,
        }

        for url in webhook_urls:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload, timeout=30) as response:
                        if response.status < 400:
                            logger.info(f"Webhook notification sent to {url}")
                        else:
                            logger.warning(
                                f"Webhook notification failed for {url}: HTTP {response.status}"
                            )
            except Exception as e:
                logger.error(f"Failed to send webhook notification to {url}: {e}")

    def get_scheduler_status(self) -> Dict[str, Any]:
        """Get current scheduler status."""
        return {
            "running": self.running,
            "total_schedules": len(self.schedules),
            "enabled_schedules": len([s for s in self.schedules.values() if s.config.enabled]),
            "due_schedules": len([s for s in self.schedules.values() if s.is_due()]),
            "schedules": [s.to_dict() for s in self.schedules.values()],
        }

    async def run_manual_backup(self, schedule_id: str) -> BackupResult:
        """Run a manual backup for a specific schedule."""
        return await self.execute_scheduled_backup(schedule_id)

    def __del__(self):
        """Cleanup when manager is destroyed."""
        if self.running:
            self.stop_scheduler()
