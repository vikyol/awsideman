"""
Integration tests for schedule manager with backup system.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from src.awsideman.backup_restore.manager import BackupManager
from src.awsideman.backup_restore.models import (
    BackupOptions,
    BackupResult,
    BackupType,
    NotificationSettings,
    RetentionPolicy,
    ScheduleConfig,
)
from src.awsideman.backup_restore.schedule_manager import ScheduleManager


class TestScheduleManagerIntegration:
    """Integration tests for schedule manager with backup system."""

    @pytest.fixture
    def mock_storage_engine(self):
        """Create mock storage engine."""
        storage = AsyncMock()
        storage.store_backup.return_value = "backup-123"
        return storage

    @pytest.fixture
    def mock_collector(self):
        """Create mock collector."""
        collector = AsyncMock()
        collector.collect_users.return_value = []
        collector.collect_groups.return_value = []
        collector.collect_permission_sets.return_value = []
        collector.collect_assignments.return_value = []
        return collector

    @pytest.fixture
    def backup_manager(self, mock_storage_engine, mock_collector):
        """Create backup manager with mocked dependencies."""
        manager = BackupManager(mock_storage_engine, mock_collector)
        # Set required instance ARN for testing
        manager.instance_arn = "arn:aws:sso:::instance/ssoins-1234567890abcdef"
        return manager

    @pytest.fixture
    def schedule_manager(self, backup_manager):
        """Create schedule manager with backup manager."""
        return ScheduleManager(backup_manager)

    @pytest.mark.asyncio
    async def test_schedule_manager_with_real_backup_manager(
        self, schedule_manager, backup_manager
    ):
        """Test schedule manager integration with backup manager."""
        # Create schedule configuration
        config = ScheduleConfig(
            name="integration-test-schedule",
            backup_type=BackupType.FULL,
            interval="daily",
            retention_policy=RetentionPolicy(keep_daily=7),
            notification_settings=NotificationSettings(enabled=False),
            backup_options=BackupOptions(
                backup_type=BackupType.FULL, encryption_enabled=True, compression_enabled=True
            ),
        )

        # Create schedule
        schedule_id = await schedule_manager.create_schedule(config)
        assert schedule_id is not None

        # Execute scheduled backup
        result = await schedule_manager.execute_scheduled_backup(schedule_id)

        # Verify backup was executed
        assert result.success is True
        assert result.backup_id is not None

        # Verify schedule was updated
        status = await schedule_manager.get_schedule_status(schedule_id)
        assert status["total_runs"] == 1
        assert status["successful_runs"] == 1
        assert status["consecutive_failures"] == 0

    @pytest.mark.asyncio
    async def test_schedule_manager_backup_failure_handling(self, schedule_manager):
        """Test schedule manager handling of backup failures."""
        # Create a backup manager that will fail
        failing_backup_manager = AsyncMock()
        failing_backup_manager.create_backup.return_value = BackupResult(
            success=False, errors=["Storage failure", "Connection timeout"]
        )

        # Create schedule manager with failing backup manager
        failing_schedule_manager = ScheduleManager(failing_backup_manager)

        # Create schedule
        config = ScheduleConfig(
            name="failure-test-schedule",
            backup_type=BackupType.FULL,
            interval="daily",
            retention_policy=RetentionPolicy(),
            notification_settings=NotificationSettings(enabled=False),
        )

        schedule_id = await failing_schedule_manager.create_schedule(config)

        # Execute scheduled backup - should handle failure gracefully
        result = await failing_schedule_manager.execute_scheduled_backup(schedule_id)

        # Verify failure was handled
        assert result.success is False
        assert len(result.errors) > 0

        # Verify schedule tracking
        status = await failing_schedule_manager.get_schedule_status(schedule_id)
        assert status["total_runs"] == 1
        assert status["successful_runs"] == 0
        assert status["consecutive_failures"] == 1

    @pytest.mark.asyncio
    async def test_multiple_schedules_execution(self, schedule_manager):
        """Test execution of multiple schedules."""
        schedules = []

        # Create multiple schedules
        for i in range(3):
            config = ScheduleConfig(
                name=f"test-schedule-{i}",
                backup_type=BackupType.FULL,
                interval="daily",
                retention_policy=RetentionPolicy(),
                notification_settings=NotificationSettings(enabled=False),
            )
            schedule_id = await schedule_manager.create_schedule(config)
            schedules.append(schedule_id)

        # Execute all schedules
        results = []
        for schedule_id in schedules:
            result = await schedule_manager.execute_scheduled_backup(schedule_id)
            results.append(result)

        # Verify all executions
        assert len(results) == 3
        for result in results:
            assert result.success is True

        # Verify scheduler status
        scheduler_status = schedule_manager.get_scheduler_status()
        assert scheduler_status["total_schedules"] == 3
        assert scheduler_status["enabled_schedules"] == 3

    @pytest.mark.asyncio
    async def test_schedule_with_incremental_backup(self, schedule_manager):
        """Test schedule with incremental backup type."""
        config = ScheduleConfig(
            name="incremental-schedule",
            backup_type=BackupType.INCREMENTAL,
            interval="hourly",
            retention_policy=RetentionPolicy(),
            notification_settings=NotificationSettings(enabled=False),
            backup_options=BackupOptions(
                backup_type=BackupType.INCREMENTAL, since=datetime.now() - timedelta(hours=1)
            ),
        )

        schedule_id = await schedule_manager.create_schedule(config)
        result = await schedule_manager.execute_scheduled_backup(schedule_id)

        assert result.success is True

        # Verify schedule configuration
        status = await schedule_manager.get_schedule_status(schedule_id)
        assert status["backup_type"] == "incremental"

    @pytest.mark.asyncio
    async def test_schedule_lifecycle_management(self, schedule_manager):
        """Test complete schedule lifecycle."""
        # Create schedule
        config = ScheduleConfig(
            name="lifecycle-test",
            backup_type=BackupType.FULL,
            interval="daily",
            retention_policy=RetentionPolicy(),
            notification_settings=NotificationSettings(enabled=False),
        )

        schedule_id = await schedule_manager.create_schedule(config)

        # Execute backup
        result1 = await schedule_manager.execute_scheduled_backup(schedule_id)
        assert result1.success is True

        # Update schedule
        config.name = "updated-lifecycle-test"
        config.backup_type = BackupType.INCREMENTAL
        update_result = await schedule_manager.update_schedule(schedule_id, config)
        assert update_result is True

        # Execute updated schedule
        result2 = await schedule_manager.execute_scheduled_backup(schedule_id)
        assert result2.success is True

        # Verify history is preserved
        status = await schedule_manager.get_schedule_status(schedule_id)
        assert status["name"] == "updated-lifecycle-test"
        assert status["backup_type"] == "incremental"
        assert status["total_runs"] == 2
        assert status["successful_runs"] == 2

        # Delete schedule
        delete_result = await schedule_manager.delete_schedule(schedule_id)
        assert delete_result is True

        # Verify deletion
        final_status = await schedule_manager.get_schedule_status(schedule_id)
        assert final_status == {}

    @pytest.mark.asyncio
    async def test_schedule_with_notifications(self, schedule_manager):
        """Test schedule with notification settings."""
        config = ScheduleConfig(
            name="notification-test",
            backup_type=BackupType.FULL,
            interval="daily",
            retention_policy=RetentionPolicy(),
            notification_settings=NotificationSettings(
                enabled=True,
                notify_on_success=True,
                notify_on_failure=True,
                email_addresses=["admin@example.com"],
                webhook_urls=["http://example.com/webhook"],
            ),
        )

        schedule_id = await schedule_manager.create_schedule(config)

        # Mock notification methods
        with (
            patch.object(schedule_manager, "_send_email_notification") as mock_email,
            patch.object(schedule_manager, "_send_webhook_notifications") as mock_webhook,
        ):

            result = await schedule_manager.execute_scheduled_backup(schedule_id)
            assert result.success is True

            # Verify notifications were attempted
            mock_email.assert_called_once()
            mock_webhook.assert_called_once()

    def test_scheduler_thread_management(self, schedule_manager):
        """Test scheduler thread lifecycle."""
        # Initially not running
        assert not schedule_manager.running
        assert schedule_manager._scheduler_thread is None

        # Start scheduler
        schedule_manager.start_scheduler()
        assert schedule_manager.running
        assert schedule_manager._scheduler_thread is not None
        assert schedule_manager._scheduler_thread.is_alive()

        # Stop scheduler
        schedule_manager.stop_scheduler()
        assert not schedule_manager.running

        # Thread should stop within timeout
        if schedule_manager._scheduler_thread:
            schedule_manager._scheduler_thread.join(timeout=1.0)
            assert not schedule_manager._scheduler_thread.is_alive()

    @pytest.mark.asyncio
    async def test_schedule_validation_integration(self, schedule_manager):
        """Test schedule validation with backup manager integration."""
        # Test invalid cron expression instead of backup type (since BackupType is an enum)
        with pytest.raises(ValueError, match="Invalid cron expression"):
            config = ScheduleConfig(
                name="invalid-test",
                backup_type=BackupType.FULL,
                interval="invalid-cron-expression",  # This should cause validation error
                retention_policy=RetentionPolicy(),
                notification_settings=NotificationSettings(),
            )
            await schedule_manager.create_schedule(config)

        # Test valid configuration
        valid_config = ScheduleConfig(
            name="valid-test",
            backup_type=BackupType.FULL,
            interval="daily",
            retention_policy=RetentionPolicy(),
            notification_settings=NotificationSettings(),
        )

        schedule_id = await schedule_manager.create_schedule(valid_config)
        assert schedule_id is not None

        # Verify schedule was created
        schedules = await schedule_manager.list_schedules()
        assert len(schedules) == 1
        assert schedules[0]["name"] == "valid-test"
