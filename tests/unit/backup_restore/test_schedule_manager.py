"""
Unit tests for backup schedule manager.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from src.awsideman.backup_restore.models import (
    BackupResult,
    BackupType,
    NotificationSettings,
    RetentionPolicy,
    ScheduleConfig,
)
from src.awsideman.backup_restore.schedule_manager import CronParser, ScheduleInfo, ScheduleManager


class TestCronParser:
    """Test cron expression parsing."""

    def test_predefined_schedules(self):
        """Test predefined schedule expressions."""
        parser = CronParser("daily")
        assert parser.expression == "0 2 * * *"

        parser = CronParser("weekly")
        assert parser.expression == "0 2 * * 0"

        parser = CronParser("monthly")
        assert parser.expression == "0 2 1 * *"

        parser = CronParser("hourly")
        assert parser.expression == "0 * * * *"

    def test_basic_cron_parsing(self):
        """Test basic cron expression parsing."""
        parser = CronParser("0 2 * * *")
        fields = parser.parsed_fields

        assert fields["minute"] == [0]
        assert fields["hour"] == [2]
        assert fields["day"] == list(range(1, 32))
        assert fields["month"] == list(range(1, 13))
        assert fields["weekday"] == list(range(0, 7))

    def test_range_parsing(self):
        """Test range parsing in cron expressions."""
        parser = CronParser("0 9-17 * * 1-5")
        fields = parser.parsed_fields

        assert fields["minute"] == [0]
        assert fields["hour"] == list(range(9, 18))
        assert fields["weekday"] == list(range(1, 6))

    def test_step_parsing(self):
        """Test step parsing in cron expressions."""
        parser = CronParser("*/15 * * * *")
        fields = parser.parsed_fields

        assert fields["minute"] == [0, 15, 30, 45]

    def test_list_parsing(self):
        """Test comma-separated list parsing."""
        parser = CronParser("0,30 9,17 * * *")
        fields = parser.parsed_fields

        assert fields["minute"] == [0, 30]
        assert fields["hour"] == [9, 17]

    def test_invalid_expression(self):
        """Test invalid cron expression handling."""
        with pytest.raises(ValueError):
            CronParser("invalid")

        with pytest.raises(ValueError):
            CronParser("0 2 * *")  # Missing field

    def test_next_run_time(self):
        """Test next run time calculation."""
        parser = CronParser("0 2 * * *")  # Daily at 2 AM

        # Test from 1 AM - should be 2 AM same day
        from_time = datetime(2024, 1, 1, 1, 0, 0)
        next_run = parser.next_run_time(from_time)
        expected = datetime(2024, 1, 1, 2, 0, 0)
        assert next_run == expected

        # Test from 3 AM - should be 2 AM next day
        from_time = datetime(2024, 1, 1, 3, 0, 0)
        next_run = parser.next_run_time(from_time)
        expected = datetime(2024, 1, 2, 2, 0, 0)
        assert next_run == expected

    def test_matches_time(self):
        """Test time matching against cron expression."""
        parser = CronParser("0 2 * * *")

        # Should match 2 AM
        assert parser._matches_time(datetime(2024, 1, 1, 2, 0, 0))

        # Should not match other times
        assert not parser._matches_time(datetime(2024, 1, 1, 1, 0, 0))
        assert not parser._matches_time(datetime(2024, 1, 1, 2, 30, 0))


class TestScheduleInfo:
    """Test schedule information management."""

    def test_schedule_info_creation(self):
        """Test schedule info creation."""
        config = ScheduleConfig(
            name="test-schedule",
            backup_type=BackupType.FULL,
            interval="daily",
            retention_policy=RetentionPolicy(),
            notification_settings=NotificationSettings(),
        )

        schedule_info = ScheduleInfo("test-id", config)

        assert schedule_info.schedule_id == "test-id"
        assert schedule_info.config == config
        assert schedule_info.consecutive_failures == 0
        assert schedule_info.total_runs == 0
        assert schedule_info.successful_runs == 0
        assert schedule_info.next_run is not None

    def test_update_after_successful_run(self):
        """Test schedule update after successful backup."""
        config = ScheduleConfig(
            name="test-schedule",
            backup_type=BackupType.FULL,
            interval="daily",
            retention_policy=RetentionPolicy(),
            notification_settings=NotificationSettings(),
        )

        schedule_info = ScheduleInfo("test-id", config)
        result = BackupResult(success=True, backup_id="backup-123")

        schedule_info.update_after_run(result)

        assert schedule_info.consecutive_failures == 0
        assert schedule_info.total_runs == 1
        assert schedule_info.successful_runs == 1
        assert schedule_info.last_result == result
        assert schedule_info.last_run is not None

    def test_update_after_failed_run(self):
        """Test schedule update after failed backup."""
        config = ScheduleConfig(
            name="test-schedule",
            backup_type=BackupType.FULL,
            interval="daily",
            retention_policy=RetentionPolicy(),
            notification_settings=NotificationSettings(),
        )

        schedule_info = ScheduleInfo("test-id", config)
        result = BackupResult(success=False, errors=["Test error"])

        schedule_info.update_after_run(result)

        assert schedule_info.consecutive_failures == 1
        assert schedule_info.total_runs == 1
        assert schedule_info.successful_runs == 0
        assert schedule_info.last_result == result

    def test_is_due(self):
        """Test due time checking."""
        config = ScheduleConfig(
            name="test-schedule",
            backup_type=BackupType.FULL,
            interval="daily",
            retention_policy=RetentionPolicy(),
            notification_settings=NotificationSettings(),
        )

        schedule_info = ScheduleInfo("test-id", config)

        # Should not be due immediately after creation
        assert not schedule_info.is_due()

        # Simulate past due time
        schedule_info.next_run = datetime.now() - timedelta(minutes=1)
        assert schedule_info.is_due()

        # Disabled schedule should not be due
        schedule_info.config.enabled = False
        assert not schedule_info.is_due()

    def test_to_dict(self):
        """Test dictionary conversion."""
        config = ScheduleConfig(
            name="test-schedule",
            backup_type=BackupType.FULL,
            interval="daily",
            retention_policy=RetentionPolicy(),
            notification_settings=NotificationSettings(),
        )

        schedule_info = ScheduleInfo("test-id", config)
        data = schedule_info.to_dict()

        assert data["schedule_id"] == "test-id"
        assert data["name"] == "test-schedule"
        assert data["backup_type"] == "full"
        assert data["interval"] == "daily"
        assert data["enabled"] is True
        assert "created_at" in data
        assert "next_run" in data


class TestScheduleManager:
    """Test schedule manager functionality."""

    @pytest.fixture
    def mock_backup_manager(self):
        """Create mock backup manager."""
        manager = AsyncMock()
        manager.create_backup.return_value = BackupResult(
            success=True, backup_id="backup-123", message="Backup completed successfully"
        )
        return manager

    @pytest.fixture
    def schedule_manager(self, mock_backup_manager):
        """Create schedule manager with mock backup manager."""
        return ScheduleManager(mock_backup_manager)

    @pytest.fixture
    def sample_schedule_config(self):
        """Create sample schedule configuration."""
        return ScheduleConfig(
            name="test-schedule",
            backup_type=BackupType.FULL,
            interval="daily",
            retention_policy=RetentionPolicy(),
            notification_settings=NotificationSettings(),
        )

    @pytest.mark.asyncio
    async def test_create_schedule(self, schedule_manager, sample_schedule_config):
        """Test schedule creation."""
        schedule_id = await schedule_manager.create_schedule(sample_schedule_config)

        assert schedule_id is not None
        assert len(schedule_id) > 0
        assert schedule_id in schedule_manager.schedules

        schedule_info = schedule_manager.schedules[schedule_id]
        assert schedule_info.config.name == "test-schedule"
        assert schedule_info.config.backup_type == BackupType.FULL

    @pytest.mark.asyncio
    async def test_create_schedule_validation(self, schedule_manager):
        """Test schedule creation validation."""
        # Test empty name
        config = ScheduleConfig(
            name="",
            backup_type=BackupType.FULL,
            interval="daily",
            retention_policy=RetentionPolicy(),
            notification_settings=NotificationSettings(),
        )

        with pytest.raises(ValueError, match="Schedule name is required"):
            await schedule_manager.create_schedule(config)

        # Test invalid cron expression
        config = ScheduleConfig(
            name="test",
            backup_type=BackupType.FULL,
            interval="invalid-cron",
            retention_policy=RetentionPolicy(),
            notification_settings=NotificationSettings(),
        )

        with pytest.raises(ValueError, match="Invalid cron expression"):
            await schedule_manager.create_schedule(config)

    @pytest.mark.asyncio
    async def test_update_schedule(self, schedule_manager, sample_schedule_config):
        """Test schedule update."""
        # Create schedule
        schedule_id = await schedule_manager.create_schedule(sample_schedule_config)

        # Update schedule
        updated_config = ScheduleConfig(
            name="updated-schedule",
            backup_type=BackupType.INCREMENTAL,
            interval="weekly",
            retention_policy=RetentionPolicy(),
            notification_settings=NotificationSettings(),
        )

        result = await schedule_manager.update_schedule(schedule_id, updated_config)
        assert result is True

        # Verify update
        schedule_info = schedule_manager.schedules[schedule_id]
        assert schedule_info.config.name == "updated-schedule"
        assert schedule_info.config.backup_type == BackupType.INCREMENTAL
        assert schedule_info.config.interval == "weekly"

    @pytest.mark.asyncio
    async def test_update_nonexistent_schedule(self, schedule_manager, sample_schedule_config):
        """Test updating non-existent schedule."""
        result = await schedule_manager.update_schedule("nonexistent", sample_schedule_config)
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_schedule(self, schedule_manager, sample_schedule_config):
        """Test schedule deletion."""
        # Create schedule
        schedule_id = await schedule_manager.create_schedule(sample_schedule_config)
        assert schedule_id in schedule_manager.schedules

        # Delete schedule
        result = await schedule_manager.delete_schedule(schedule_id)
        assert result is True
        assert schedule_id not in schedule_manager.schedules

    @pytest.mark.asyncio
    async def test_delete_nonexistent_schedule(self, schedule_manager):
        """Test deleting non-existent schedule."""
        result = await schedule_manager.delete_schedule("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_list_schedules(self, schedule_manager, sample_schedule_config):
        """Test listing schedules."""
        # Initially empty
        schedules = await schedule_manager.list_schedules()
        assert len(schedules) == 0

        # Create schedule
        schedule_id = await schedule_manager.create_schedule(sample_schedule_config)

        # List schedules
        schedules = await schedule_manager.list_schedules()
        assert len(schedules) == 1
        assert schedules[0]["schedule_id"] == schedule_id
        assert schedules[0]["name"] == "test-schedule"

    @pytest.mark.asyncio
    async def test_execute_scheduled_backup(
        self, schedule_manager, sample_schedule_config, mock_backup_manager
    ):
        """Test executing scheduled backup."""
        # Create schedule
        schedule_id = await schedule_manager.create_schedule(sample_schedule_config)

        # Execute backup
        result = await schedule_manager.execute_scheduled_backup(schedule_id)

        assert result.success is True
        assert result.backup_id == "backup-123"

        # Verify backup manager was called
        mock_backup_manager.create_backup.assert_called_once()

        # Verify schedule info was updated
        schedule_info = schedule_manager.schedules[schedule_id]
        assert schedule_info.total_runs == 1
        assert schedule_info.successful_runs == 1
        assert schedule_info.consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_execute_scheduled_backup_failure(
        self, schedule_manager, sample_schedule_config, mock_backup_manager
    ):
        """Test executing scheduled backup with failure."""
        # Configure backup manager to fail
        mock_backup_manager.create_backup.return_value = BackupResult(
            success=False, errors=["Backup failed"]
        )

        # Create schedule
        schedule_id = await schedule_manager.create_schedule(sample_schedule_config)

        # Execute backup
        result = await schedule_manager.execute_scheduled_backup(schedule_id)

        assert result.success is False
        assert "Backup failed" in result.errors

        # Verify schedule info was updated
        schedule_info = schedule_manager.schedules[schedule_id]
        assert schedule_info.total_runs == 1
        assert schedule_info.successful_runs == 0
        assert schedule_info.consecutive_failures == 1

    @pytest.mark.asyncio
    async def test_execute_nonexistent_schedule(self, schedule_manager):
        """Test executing non-existent schedule."""
        result = await schedule_manager.execute_scheduled_backup("nonexistent")

        assert result.success is False
        assert "not found" in result.message

    @pytest.mark.asyncio
    async def test_get_schedule_status(self, schedule_manager, sample_schedule_config):
        """Test getting schedule status."""
        # Create schedule
        schedule_id = await schedule_manager.create_schedule(sample_schedule_config)

        # Get status
        status = await schedule_manager.get_schedule_status(schedule_id)

        assert status["schedule_id"] == schedule_id
        assert status["name"] == "test-schedule"
        assert status["total_runs"] == 0
        assert status["success_rate"] == 0

    @pytest.mark.asyncio
    async def test_get_nonexistent_schedule_status(self, schedule_manager):
        """Test getting status of non-existent schedule."""
        status = await schedule_manager.get_schedule_status("nonexistent")
        assert status == {}

    def test_scheduler_lifecycle(self, schedule_manager):
        """Test scheduler start/stop lifecycle."""
        # Initially not running
        assert not schedule_manager.running

        # Start scheduler
        schedule_manager.start_scheduler()
        assert schedule_manager.running

        # Stop scheduler
        schedule_manager.stop_scheduler()
        assert not schedule_manager.running

    def test_get_scheduler_status(self, schedule_manager, sample_schedule_config):
        """Test getting scheduler status."""
        status = schedule_manager.get_scheduler_status()

        assert "running" in status
        assert "total_schedules" in status
        assert "enabled_schedules" in status
        assert "due_schedules" in status
        assert "schedules" in status

    @pytest.mark.asyncio
    async def test_notification_sending(self, schedule_manager, mock_backup_manager):
        """Test notification sending after backup."""
        # Create schedule with notifications enabled
        config = ScheduleConfig(
            name="test-schedule",
            backup_type=BackupType.FULL,
            interval="daily",
            retention_policy=RetentionPolicy(),
            notification_settings=NotificationSettings(
                enabled=True,
                notify_on_success=True,
                notify_on_failure=True,
                email_addresses=["test@example.com"],
                webhook_urls=["http://example.com/webhook"],
            ),
        )

        schedule_id = await schedule_manager.create_schedule(config)

        # Mock notification methods
        with (
            patch.object(schedule_manager, "_send_email_notification") as mock_email,
            patch.object(schedule_manager, "_send_webhook_notifications") as mock_webhook,
        ):

            # Execute backup
            await schedule_manager.execute_scheduled_backup(schedule_id)

            # Verify notifications were sent
            mock_email.assert_called_once()
            mock_webhook.assert_called_once()

    @pytest.mark.asyncio
    async def test_webhook_notification_sending(self, schedule_manager):
        """Test webhook notification sending."""
        result = BackupResult(success=True, backup_id="test-123")

        with patch("aiohttp.ClientSession") as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)

            mock_post = AsyncMock()
            mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_session.return_value.__aenter__.return_value.post = mock_post

            await schedule_manager._send_webhook_notifications(
                ["http://example.com/webhook"], "Test message", result
            )

            # Verify session was used
            mock_session.assert_called_once()


class TestScheduleManagerIntegration:
    """Integration tests for schedule manager."""

    @pytest.mark.asyncio
    async def test_full_schedule_workflow(self):
        """Test complete schedule workflow."""
        # Create mock backup manager
        backup_manager = AsyncMock()
        backup_manager.create_backup.return_value = BackupResult(
            success=True, backup_id="backup-123"
        )

        # Create schedule manager
        schedule_manager = ScheduleManager(backup_manager)

        # Create schedule
        config = ScheduleConfig(
            name="integration-test",
            backup_type=BackupType.FULL,
            interval="daily",
            retention_policy=RetentionPolicy(keep_daily=7),
            notification_settings=NotificationSettings(enabled=False),
        )

        schedule_id = await schedule_manager.create_schedule(config)

        # Execute backup
        result = await schedule_manager.execute_scheduled_backup(schedule_id)
        assert result.success is True

        # Check status
        status = await schedule_manager.get_schedule_status(schedule_id)
        assert status["total_runs"] == 1
        assert status["successful_runs"] == 1

        # Update schedule
        config.name = "updated-integration-test"
        update_result = await schedule_manager.update_schedule(schedule_id, config)
        assert update_result is True

        # Verify update
        updated_status = await schedule_manager.get_schedule_status(schedule_id)
        assert updated_status["name"] == "updated-integration-test"

        # Delete schedule
        delete_result = await schedule_manager.delete_schedule(schedule_id)
        assert delete_result is True

        # Verify deletion
        final_status = await schedule_manager.get_schedule_status(schedule_id)
        assert final_status == {}
