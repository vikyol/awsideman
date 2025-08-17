"""
Unit tests for backup schedule notification functionality.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.awsideman.backup_restore.models import (
    BackupResult,
    BackupType,
    NotificationSettings,
    RetentionPolicy,
    ScheduleConfig,
)
from src.awsideman.backup_restore.schedule_manager import ScheduleInfo, ScheduleManager


class TestScheduleNotifications:
    """Test notification functionality in schedule manager."""

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
    def notification_config(self):
        """Create notification configuration."""
        return NotificationSettings(
            enabled=True,
            email_addresses=["admin@example.com", "backup@example.com"],
            webhook_urls=["http://example.com/webhook", "http://backup.example.com/hook"],
            notify_on_success=True,
            notify_on_failure=True,
        )

    @pytest.fixture
    def schedule_config_with_notifications(self, notification_config):
        """Create schedule configuration with notifications."""
        return ScheduleConfig(
            name="test-schedule-notifications",
            backup_type=BackupType.FULL,
            interval="daily",
            retention_policy=RetentionPolicy(),
            notification_settings=notification_config,
        )

    @pytest.mark.asyncio
    async def test_notification_on_success(
        self, schedule_manager, schedule_config_with_notifications
    ):
        """Test notifications are sent on successful backup."""
        schedule_id = await schedule_manager.create_schedule(schedule_config_with_notifications)

        with (
            patch.object(schedule_manager, "_send_email_notification") as mock_email,
            patch.object(schedule_manager, "_send_webhook_notifications") as mock_webhook,
        ):

            # Execute successful backup
            result = await schedule_manager.execute_scheduled_backup(schedule_id)

            assert result.success is True

            # Verify notifications were sent
            mock_email.assert_called_once()
            mock_webhook.assert_called_once()

            # Check call arguments
            email_args = mock_email.call_args[0]
            webhook_args = mock_webhook.call_args[0]

            assert "admin@example.com" in email_args[0]
            assert "backup@example.com" in email_args[0]
            assert "SUCCESS" in email_args[1]

            assert "http://example.com/webhook" in webhook_args[0]
            assert "http://backup.example.com/hook" in webhook_args[0]
            assert "SUCCESS" in webhook_args[1]

    @pytest.mark.asyncio
    async def test_notification_on_failure(
        self, schedule_manager, schedule_config_with_notifications, mock_backup_manager
    ):
        """Test notifications are sent on backup failure."""
        # Configure backup manager to fail
        mock_backup_manager.create_backup.return_value = BackupResult(
            success=False, errors=["Backup operation failed", "Storage unavailable"]
        )

        schedule_id = await schedule_manager.create_schedule(schedule_config_with_notifications)

        with (
            patch.object(schedule_manager, "_send_email_notification") as mock_email,
            patch.object(schedule_manager, "_send_webhook_notifications") as mock_webhook,
        ):

            # Execute failed backup
            result = await schedule_manager.execute_scheduled_backup(schedule_id)

            assert result.success is False

            # Verify notifications were sent
            mock_email.assert_called_once()
            mock_webhook.assert_called_once()

            # Check call arguments contain failure information
            email_args = mock_email.call_args[0]
            webhook_args = mock_webhook.call_args[0]

            assert "FAILURE" in email_args[1]
            assert "FAILURE" in webhook_args[1]

    @pytest.mark.asyncio
    async def test_notification_disabled(self, schedule_manager):
        """Test no notifications are sent when disabled."""
        config = ScheduleConfig(
            name="test-no-notifications",
            backup_type=BackupType.FULL,
            interval="daily",
            retention_policy=RetentionPolicy(),
            notification_settings=NotificationSettings(enabled=False),
        )

        schedule_id = await schedule_manager.create_schedule(config)

        with (
            patch.object(schedule_manager, "_send_email_notification") as mock_email,
            patch.object(schedule_manager, "_send_webhook_notifications") as mock_webhook,
        ):

            # Execute backup
            await schedule_manager.execute_scheduled_backup(schedule_id)

            # Verify no notifications were sent
            mock_email.assert_not_called()
            mock_webhook.assert_not_called()

    @pytest.mark.asyncio
    async def test_notification_success_only(self, schedule_manager, mock_backup_manager):
        """Test notifications only on success when configured."""
        config = ScheduleConfig(
            name="test-success-only",
            backup_type=BackupType.FULL,
            interval="daily",
            retention_policy=RetentionPolicy(),
            notification_settings=NotificationSettings(
                enabled=True,
                notify_on_success=True,
                notify_on_failure=False,
                email_addresses=["admin@example.com"],
            ),
        )

        schedule_id = await schedule_manager.create_schedule(config)

        with patch.object(schedule_manager, "_send_email_notification") as mock_email:
            # Test successful backup - should notify
            result = await schedule_manager.execute_scheduled_backup(schedule_id)
            assert result.success is True
            mock_email.assert_called_once()

            # Reset mock
            mock_email.reset_mock()

            # Configure failure and test - should not notify
            mock_backup_manager.create_backup.return_value = BackupResult(
                success=False, errors=["Test failure"]
            )

            result = await schedule_manager.execute_scheduled_backup(schedule_id)
            assert result.success is False
            mock_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_notification_failure_only(self, schedule_manager, mock_backup_manager):
        """Test notifications only on failure when configured."""
        config = ScheduleConfig(
            name="test-failure-only",
            backup_type=BackupType.FULL,
            interval="daily",
            retention_policy=RetentionPolicy(),
            notification_settings=NotificationSettings(
                enabled=True,
                notify_on_success=False,
                notify_on_failure=True,
                email_addresses=["admin@example.com"],
            ),
        )

        schedule_id = await schedule_manager.create_schedule(config)

        with patch.object(schedule_manager, "_send_email_notification") as mock_email:
            # Test successful backup - should not notify
            result = await schedule_manager.execute_scheduled_backup(schedule_id)
            assert result.success is True
            mock_email.assert_not_called()

            # Configure failure and test - should notify
            mock_backup_manager.create_backup.return_value = BackupResult(
                success=False, errors=["Test failure"]
            )

            result = await schedule_manager.execute_scheduled_backup(schedule_id)
            assert result.success is False
            mock_email.assert_called_once()

    @pytest.mark.asyncio
    async def test_email_notification_content(self, schedule_manager):
        """Test email notification content and format."""
        result = BackupResult(
            success=True, backup_id="backup-123", message="Backup completed successfully"
        )

        email_addresses = ["admin@example.com", "backup@example.com"]
        message = "Scheduled backup 'test-schedule' SUCCESS: Backup completed successfully"

        # Mock the actual email sending to capture the call
        with patch("logging.Logger.info") as mock_logger:
            await schedule_manager._send_email_notification(email_addresses, message, result)

            # Verify logging was called with expected message
            mock_logger.assert_called_with(
                f"Email notification sent to {email_addresses}: {message}"
            )

    @pytest.mark.asyncio
    async def test_webhook_notification_payload(self, schedule_manager):
        """Test webhook notification payload structure."""
        result = BackupResult(
            success=True,
            backup_id="backup-123",
            message="Backup completed successfully",
            errors=[],
            warnings=["Minor warning"],
        )

        webhook_urls = ["http://example.com/webhook"]
        message = "Scheduled backup 'test-schedule' SUCCESS"

        with patch("aiohttp.ClientSession") as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 200

            # Properly mock the async context manager chain
            mock_session_instance = AsyncMock()
            mock_session.return_value = mock_session_instance
            mock_session_instance.__aenter__.return_value = mock_session_instance

            # Mock the post method to return the mock response
            mock_post_context = AsyncMock()
            mock_post_context.__aenter__.return_value = mock_response
            mock_session_instance.post.return_value = mock_post_context

            await schedule_manager._send_webhook_notifications(webhook_urls, message, result)

            # Verify session was created and post was called
            mock_session.assert_called_once()
            post_call = mock_session_instance.post
            post_call.assert_called_once()

            # Check the payload structure
            call_args = post_call.call_args
            payload = call_args[1]["json"]

            assert payload["message"] == message
            assert payload["success"] is True
            assert payload["backup_id"] == "backup-123"
            assert "timestamp" in payload
            assert payload["errors"] == []
            assert payload["warnings"] == ["Minor warning"]

    @pytest.mark.asyncio
    async def test_webhook_notification_failure_handling(self, schedule_manager):
        """Test webhook notification failure handling."""
        result = BackupResult(success=True, backup_id="backup-123")
        webhook_urls = ["http://invalid-url.example.com/webhook"]
        message = "Test message"

        with patch("aiohttp.ClientSession") as mock_session:
            # Simulate connection error
            mock_session_instance = AsyncMock()
            mock_session.return_value = mock_session_instance
            mock_session_instance.__aenter__.return_value = mock_session_instance
            mock_session_instance.post.side_effect = Exception("Connection failed")

            with patch("src.awsideman.backup_restore.schedule_manager.logger") as mock_logger:
                # Should not raise exception, but log error
                await schedule_manager._send_webhook_notifications(webhook_urls, message, result)

                # Verify error was logged
                mock_logger.error.assert_called()
                error_call = mock_logger.error.call_args[0][0]
                assert "Failed to send webhook notification" in error_call

    @pytest.mark.asyncio
    async def test_webhook_notification_http_error(self, schedule_manager):
        """Test webhook notification HTTP error handling."""
        result = BackupResult(success=True, backup_id="backup-123")
        webhook_urls = ["http://example.com/webhook"]
        message = "Test message"

        # Test that HTTP errors are handled gracefully without raising exceptions
        with patch("aiohttp.ClientSession") as mock_session:
            # Create a mock response with error status
            mock_response = MagicMock()
            mock_response.status = 500

            # Create async context manager mocks
            mock_session_ctx = AsyncMock()
            mock_post_ctx = AsyncMock()

            mock_session.return_value = mock_session_ctx
            mock_session_ctx.__aenter__.return_value.post.return_value = mock_post_ctx
            mock_post_ctx.__aenter__.return_value = mock_response

            # Should not raise exception even with HTTP error
            try:
                await schedule_manager._send_webhook_notifications(webhook_urls, message, result)
                # If we get here, the method handled the error gracefully
                assert True
            except Exception as e:
                pytest.fail(
                    f"Webhook notification should handle HTTP errors gracefully, but raised: {e}"
                )

    @pytest.mark.asyncio
    async def test_multiple_webhook_notifications(self, schedule_manager):
        """Test sending notifications to multiple webhooks."""
        result = BackupResult(success=True, backup_id="backup-123")
        webhook_urls = [
            "http://webhook1.example.com/hook",
            "http://webhook2.example.com/hook",
            "http://webhook3.example.com/hook",
        ]
        message = "Test message"

        with patch("aiohttp.ClientSession") as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 200

            # Properly mock the async context manager chain
            mock_session_instance = AsyncMock()
            mock_session.return_value = mock_session_instance
            mock_session_instance.__aenter__.return_value = mock_session_instance

            # Mock the post method to return the mock response
            mock_post_context = AsyncMock()
            mock_post_context.__aenter__.return_value = mock_response
            mock_session_instance.post.return_value = mock_post_context

            await schedule_manager._send_webhook_notifications(webhook_urls, message, result)

            # Verify all webhooks were called
            post_calls = mock_session_instance.post.call_args_list
            assert len(post_calls) == 3

            # Verify each URL was called
            called_urls = [call[0][0] for call in post_calls]
            for url in webhook_urls:
                assert url in called_urls

    @pytest.mark.asyncio
    async def test_notification_exception_handling(
        self, schedule_manager, schedule_config_with_notifications
    ):
        """Test notification exception handling doesn't break backup execution."""
        schedule_id = await schedule_manager.create_schedule(schedule_config_with_notifications)

        # Mock notification methods to raise exceptions
        with (
            patch.object(
                schedule_manager, "_send_email_notification", side_effect=Exception("Email failed")
            ),
            patch.object(
                schedule_manager,
                "_send_webhook_notifications",
                side_effect=Exception("Webhook failed"),
            ),
            patch("logging.Logger.error") as mock_logger,
        ):

            # Execute backup - should succeed despite notification failures
            result = await schedule_manager.execute_scheduled_backup(schedule_id)

            assert result.success is True

            # Verify errors were logged
            mock_logger.assert_called()
            error_calls = [call[0][0] for call in mock_logger.call_args_list]
            assert any("Failed to send backup notification" in call for call in error_calls)

    def test_notification_settings_validation(self):
        """Test notification settings validation in schedule config."""
        # Valid configuration
        valid_settings = NotificationSettings(
            enabled=True,
            email_addresses=["test@example.com"],
            webhook_urls=["http://example.com/webhook"],
            notify_on_success=True,
            notify_on_failure=True,
        )

        config = ScheduleConfig(
            name="test-schedule",
            backup_type=BackupType.FULL,
            interval="daily",
            retention_policy=RetentionPolicy(),
            notification_settings=valid_settings,
        )

        # Should not raise any exceptions
        assert config.notification_settings.enabled is True
        assert len(config.notification_settings.email_addresses) == 1
        assert len(config.notification_settings.webhook_urls) == 1

    @pytest.mark.asyncio
    async def test_schedule_info_notification_integration(self):
        """Test schedule info integration with notification settings."""
        notification_settings = NotificationSettings(
            enabled=True,
            email_addresses=["admin@example.com"],
            notify_on_success=True,
            notify_on_failure=False,
        )

        config = ScheduleConfig(
            name="test-integration",
            backup_type=BackupType.FULL,
            interval="daily",
            retention_policy=RetentionPolicy(),
            notification_settings=notification_settings,
        )

        schedule_info = ScheduleInfo("test-id", config)
        data = schedule_info.to_dict()

        # Verify notification settings are included in serialization
        assert "notification_settings" in data
        assert data["notification_settings"]["enabled"] is True
        assert data["notification_settings"]["email_addresses"] == ["admin@example.com"]
        assert data["notification_settings"]["notify_on_success"] is True
        assert data["notification_settings"]["notify_on_failure"] is False
