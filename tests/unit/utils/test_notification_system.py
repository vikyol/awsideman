"""Tests for notification system."""

import logging
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
import pytest

from src.awsideman.utils.monitoring_config import (
    EmailNotificationConfig,
    LogNotificationConfig,
    MonitoringConfig,
    ThresholdLevel,
    WebhookNotificationConfig,
)
from src.awsideman.utils.notification_system import EmailNotificationError, NotificationSystem
from src.awsideman.utils.status_models import (
    HealthStatus,
    ProvisioningStatus,
    StatusLevel,
    StatusReport,
    SummaryStatistics,
)


class TestNotificationSystem:
    """Test NotificationSystem class."""

    def setup_method(self):
        """Setup test method."""
        self.monitoring_config = MonitoringConfig(
            enabled=True,
            email_notifications=EmailNotificationConfig(
                smtp_server="smtp.example.com",
                username="user@example.com",
                password="password",
                from_address="alerts@example.com",
                to_addresses=["admin@example.com"],
            ),
            webhook_notifications=WebhookNotificationConfig(
                url="https://hooks.example.com/webhook"
            ),
            log_notifications=LogNotificationConfig(log_level="WARNING", enabled=True),
        )

        self.notification_system = NotificationSystem(self.monitoring_config)

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
                timestamp=datetime.now(),
                status=StatusLevel.HEALTHY,
                message="Provisioning operations running normally",
                active_operations=[],
                failed_operations=[],
                pending_count=0,
                estimated_completion=None,
            ),
            orphaned_assignment_status=[],
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

    def test_notification_system_creation(self):
        """Test creating notification system."""
        assert self.notification_system.monitoring_config == self.monitoring_config

    def test_prepare_notification_data(self):
        """Test preparing notification data."""
        data = self.notification_system._prepare_notification_data(
            self.status_report, ThresholdLevel.WARNING, "Test alert message"
        )

        assert data["threshold_level"] == "warning"
        assert data["message"] == "Test alert message"
        assert "timestamp" in data
        assert "status_report" in data

        status_data = data["status_report"]
        assert status_data["overall_health"] == "Warning"
        assert status_data["health_message"] == "System experiencing issues"
        assert status_data["provisioning_active"] == 0
        assert status_data["provisioning_failed"] == 0
        assert status_data["orphaned_assignments"] == 0
        assert status_data["sync_issues"] == 0
        assert status_data["total_users"] == 100
        assert status_data["total_groups"] == 10
        assert status_data["total_permission_sets"] == 5

    @pytest.mark.asyncio
    async def test_send_alert_disabled(self):
        """Test sending alert when monitoring is disabled."""
        self.monitoring_config.enabled = False

        # Should not raise any exceptions
        await self.notification_system.send_alert(
            self.status_report, ThresholdLevel.WARNING, "Test message"
        )

    @pytest.mark.asyncio
    @patch("src.awsideman.utils.notification_system.NotificationSystem._send_email_notification")
    @patch("src.awsideman.utils.notification_system.NotificationSystem._send_webhook_notification")
    @patch("src.awsideman.utils.notification_system.NotificationSystem._send_log_notification")
    async def test_send_alert_all_enabled(self, mock_log, mock_webhook, mock_email):
        """Test sending alert with all notification types enabled."""
        mock_email.return_value = None
        mock_webhook.return_value = None
        mock_log.return_value = None

        await self.notification_system.send_alert(
            self.status_report, ThresholdLevel.WARNING, "Test message"
        )

        mock_email.assert_called_once()
        mock_webhook.assert_called_once()
        mock_log.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.awsideman.utils.notification_system.NotificationSystem._send_email_notification")
    async def test_send_alert_with_exception(self, mock_email):
        """Test sending alert when notification fails."""
        mock_email.side_effect = EmailNotificationError("SMTP error")

        # Should not raise exception, but log error
        await self.notification_system.send_alert(
            self.status_report, ThresholdLevel.WARNING, "Test message"
        )

    @pytest.mark.asyncio
    @patch("smtplib.SMTP")
    async def test_send_email_notification(self, mock_smtp_class):
        """Test sending email notification."""
        mock_smtp = Mock()
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp

        notification_data = self.notification_system._prepare_notification_data(
            self.status_report, ThresholdLevel.WARNING, "Test message"
        )

        await self.notification_system._send_email_notification(notification_data)

        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once_with("user@example.com", "password")
        mock_smtp.send_message.assert_called_once()

    @pytest.mark.asyncio
    @patch("smtplib.SMTP")
    async def test_send_email_notification_disabled(self, mock_smtp_class):
        """Test sending email notification when disabled."""
        self.monitoring_config.email_notifications.enabled = False

        notification_data = self.notification_system._prepare_notification_data(
            self.status_report, ThresholdLevel.WARNING, "Test message"
        )

        await self.notification_system._send_email_notification(notification_data)

        mock_smtp_class.assert_not_called()

    @pytest.mark.asyncio
    @patch("smtplib.SMTP")
    async def test_send_email_notification_error(self, mock_smtp_class):
        """Test email notification error handling."""
        mock_smtp_class.side_effect = Exception("SMTP connection failed")

        notification_data = self.notification_system._prepare_notification_data(
            self.status_report, ThresholdLevel.WARNING, "Test message"
        )

        with pytest.raises(EmailNotificationError):
            await self.notification_system._send_email_notification(notification_data)

    def test_create_email_body(self):
        """Test creating email body."""
        notification_data = self.notification_system._prepare_notification_data(
            self.status_report, ThresholdLevel.WARNING, "Test message"
        )

        body = self.notification_system._create_email_body(notification_data)

        assert "AWS Identity Center Alert: WARNING" in body
        assert "Test message" in body
        assert "WARNING" in body  # Overall health status
        assert "System experiencing issues" in body
        assert "100" in body  # Total users
        assert "10" in body  # Total groups
        assert "5" in body  # Total permission sets
        assert "<html>" in body
        assert "</html>" in body

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.request")
    async def test_send_webhook_notification(self, mock_request):
        """Test sending webhook notification."""
        mock_response = Mock()
        mock_response.status = 200
        mock_request.return_value.__aenter__.return_value = mock_response

        notification_data = self.notification_system._prepare_notification_data(
            self.status_report, ThresholdLevel.WARNING, "Test message"
        )

        await self.notification_system._send_webhook_notification(notification_data)

        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args[1]["method"] == "POST"
        assert call_args[1]["url"] == "https://hooks.example.com/webhook"
        assert "json" in call_args[1]

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.request")
    async def test_send_webhook_notification_disabled(self, mock_request):
        """Test sending webhook notification when disabled."""
        self.monitoring_config.webhook_notifications.enabled = False

        notification_data = self.notification_system._prepare_notification_data(
            self.status_report, ThresholdLevel.WARNING, "Test message"
        )

        await self.notification_system._send_webhook_notification(notification_data)

        mock_request.assert_not_called()

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.request")
    async def test_send_webhook_notification_custom_payload(self, mock_request):
        """Test webhook notification with custom payload template."""
        self.monitoring_config.webhook_notifications.payload_template = (
            '{{"alert": "{message}", "level": "{threshold_level}"}}'
        )

        mock_response = Mock()
        mock_response.status = 200
        mock_request.return_value.__aenter__.return_value = mock_response

        notification_data = self.notification_system._prepare_notification_data(
            self.status_report, ThresholdLevel.WARNING, "Test message"
        )

        await self.notification_system._send_webhook_notification(notification_data)

        call_args = mock_request.call_args
        payload = call_args[1]["json"]
        assert payload["alert"] == "Test message"
        assert payload["level"] == "warning"

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.request")
    async def test_send_webhook_with_retry(self, mock_request):
        """Test webhook retry logic."""
        # First two attempts fail, third succeeds
        mock_response_fail = Mock()
        mock_response_fail.status = 500
        mock_response_fail.text.return_value = "Internal Server Error"

        mock_response_success = Mock()
        mock_response_success.status = 200

        mock_request.return_value.__aenter__.side_effect = [
            mock_response_fail,
            mock_response_fail,
            mock_response_success,
        ]

        webhook_config = self.monitoring_config.webhook_notifications
        webhook_config.retry_attempts = 3
        webhook_config.retry_delay_seconds = 0.1  # Fast retry for testing

        payload = {"test": "data"}

        await self.notification_system._send_webhook_with_retry(webhook_config, payload)

        assert mock_request.call_count == 3

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.request")
    async def test_send_webhook_with_retry_all_fail(self, mock_request):
        """Test webhook retry when all attempts fail."""
        mock_response = Mock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal Server Error")
        mock_request.return_value.__aenter__.return_value = mock_response

        webhook_config = self.monitoring_config.webhook_notifications
        webhook_config.retry_attempts = 2
        webhook_config.retry_delay_seconds = 0.1

        payload = {"test": "data"}

        with pytest.raises(aiohttp.ClientResponseError):
            await self.notification_system._send_webhook_with_retry(webhook_config, payload)

        assert mock_request.call_count == 2

    @pytest.mark.asyncio
    async def test_send_log_notification(self):
        """Test sending log notification."""
        notification_data = self.notification_system._prepare_notification_data(
            self.status_report, ThresholdLevel.WARNING, "Test message"
        )

        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger

            await self.notification_system._send_log_notification(notification_data)

            mock_logger.log.assert_called_once()
            call_args = mock_logger.log.call_args
            assert call_args[0][0] == logging.WARNING  # Log level
            assert "Test message" in call_args[0][1]  # Log message

    @pytest.mark.asyncio
    async def test_send_log_notification_disabled(self):
        """Test sending log notification when disabled."""
        self.monitoring_config.log_notifications.enabled = False

        notification_data = self.notification_system._prepare_notification_data(
            self.status_report, ThresholdLevel.WARNING, "Test message"
        )

        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger

            await self.notification_system._send_log_notification(notification_data)

            mock_logger.log.assert_not_called()

    def test_create_log_message(self):
        """Test creating log message."""
        notification_data = self.notification_system._prepare_notification_data(
            self.status_report, ThresholdLevel.WARNING, "Test message"
        )

        message = self.notification_system._create_log_message(notification_data)

        assert "AWS Identity Center Alert [WARNING]" in message
        assert "Test message" in message
        assert "Health: Warning" in message
        assert "Users: 100" in message
        assert "Groups: 10" in message
        assert "Permission Sets: 5" in message

    @pytest.mark.asyncio
    @patch("src.awsideman.utils.notification_system.NotificationSystem._send_email_notification")
    @patch("src.awsideman.utils.notification_system.NotificationSystem._send_webhook_notification")
    @patch("src.awsideman.utils.notification_system.NotificationSystem._send_log_notification")
    async def test_test_notifications_all_success(self, mock_log, mock_webhook, mock_email):
        """Test testing all notification methods successfully."""
        mock_email.return_value = None
        mock_webhook.return_value = None
        mock_log.return_value = None

        results = await self.notification_system.test_notifications()

        assert results["email"] is True
        assert results["webhook"] is True
        assert results["log"] is True

        mock_email.assert_called_once()
        mock_webhook.assert_called_once()
        mock_log.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.awsideman.utils.notification_system.NotificationSystem._send_email_notification")
    @patch("src.awsideman.utils.notification_system.NotificationSystem._send_webhook_notification")
    async def test_test_notifications_partial_failure(self, mock_webhook, mock_email):
        """Test testing notifications with partial failure."""
        mock_email.side_effect = EmailNotificationError("SMTP error")
        mock_webhook.return_value = None

        results = await self.notification_system.test_notifications()

        assert results["email"] is False
        assert results["webhook"] is True

    @pytest.mark.asyncio
    async def test_test_notifications_disabled_methods(self):
        """Test testing notifications with disabled methods."""
        # Disable email and webhook
        self.monitoring_config.email_notifications.enabled = False
        self.monitoring_config.webhook_notifications.enabled = False

        results = await self.notification_system.test_notifications()

        # Only log should be tested
        assert "log" in results
        assert "email" not in results
        assert "webhook" not in results


if __name__ == "__main__":
    pytest.main([__file__])
