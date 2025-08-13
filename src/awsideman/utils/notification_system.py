"""Notification system for monitoring alerts."""

import asyncio
import json
import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict

import aiohttp
from rich.console import Console

from .monitoring_config import (
    EmailNotificationConfig,
    MonitoringConfig,
    ThresholdLevel,
    WebhookNotificationConfig,
)
from .status_models import StatusLevel, StatusReport

console = Console()
logger = logging.getLogger(__name__)


class NotificationError(Exception):
    """Base exception for notification errors."""

    pass


class EmailNotificationError(NotificationError):
    """Exception for email notification errors."""

    pass


class WebhookNotificationError(NotificationError):
    """Exception for webhook notification errors."""

    pass


class NotificationSystem:
    """Handles sending notifications for monitoring alerts."""

    def __init__(self, monitoring_config: MonitoringConfig):
        """Initialize the notification system."""
        self.monitoring_config = monitoring_config
        self._setup_logging()

    def _setup_logging(self):
        """Setup logging configuration for notifications."""
        if (
            self.monitoring_config.log_notifications is not None
            and self.monitoring_config.log_notifications.enabled
        ):
            log_config = self.monitoring_config.log_notifications

            # Configure logger
            notification_logger = logging.getLogger("awsideman.notifications")
            notification_logger.setLevel(getattr(logging, log_config.log_level.upper()))

            # Create formatter
            formatter = logging.Formatter(log_config.log_format)

            # Add file handler if log file specified
            if log_config.log_file:
                file_handler = logging.FileHandler(log_config.log_file)
                file_handler.setFormatter(formatter)
                notification_logger.addHandler(file_handler)

            # Add console handler
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            notification_logger.addHandler(console_handler)

    async def send_alert(
        self, status_report: StatusReport, threshold_level: ThresholdLevel, message: str
    ):
        """Send alert notifications based on configuration."""
        if not self.monitoring_config.enabled:
            return

        # Prepare notification data
        notification_data = self._prepare_notification_data(status_report, threshold_level, message)

        # Send notifications concurrently
        tasks = []

        if (
            self.monitoring_config.email_notifications
            and self.monitoring_config.email_notifications.enabled
        ):
            tasks.append(self._send_email_notification(notification_data))

        if (
            self.monitoring_config.webhook_notifications
            and self.monitoring_config.webhook_notifications.enabled
        ):
            tasks.append(self._send_webhook_notification(notification_data))

        if (
            self.monitoring_config.log_notifications
            and self.monitoring_config.log_notifications.enabled
        ):
            tasks.append(self._send_log_notification(notification_data))

        # Execute all notification tasks
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Log any notification failures
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Notification task {i} failed: {result}")

    def _prepare_notification_data(
        self, status_report: StatusReport, threshold_level: ThresholdLevel, message: str
    ) -> Dict[str, Any]:
        """Prepare notification data from status report."""
        return {
            "timestamp": datetime.now().isoformat(),
            "threshold_level": threshold_level.value,
            "message": message,
            "status_report": {
                "overall_health": (
                    status_report.overall_health.status.value
                    if status_report.overall_health
                    else "unknown"
                ),
                "health_message": (
                    status_report.overall_health.message if status_report.overall_health else ""
                ),
                "provisioning_active": (
                    len(status_report.provisioning_status.active_operations)
                    if status_report.provisioning_status
                    and hasattr(status_report.provisioning_status, "active_operations")
                    else 0
                ),
                "provisioning_failed": (
                    len(status_report.provisioning_status.failed_operations)
                    if status_report.provisioning_status
                    and hasattr(status_report.provisioning_status, "failed_operations")
                    else 0
                ),
                "orphaned_assignments": (
                    len(status_report.orphaned_assignment_status.orphaned_assignments)
                    if status_report.orphaned_assignment_status
                    and hasattr(status_report.orphaned_assignment_status, "orphaned_assignments")
                    else 0
                ),
                "sync_issues": (
                    len([s for s in status_report.sync_status if s.status != StatusLevel.HEALTHY])
                    if status_report.sync_status and hasattr(status_report.sync_status, "__iter__")
                    else 0
                ),
                "total_users": (
                    status_report.summary_statistics.total_users
                    if status_report.summary_statistics
                    and hasattr(status_report.summary_statistics, "total_users")
                    else 0
                ),
                "total_groups": (
                    status_report.summary_statistics.total_groups
                    if status_report.summary_statistics
                    and hasattr(status_report.summary_statistics, "total_groups")
                    else 0
                ),
                "total_permission_sets": (
                    status_report.summary_statistics.total_permission_sets
                    if status_report.summary_statistics
                    and hasattr(status_report.summary_statistics, "total_permission_sets")
                    else 0
                ),
                "report_timestamp": (
                    status_report.timestamp.isoformat() if status_report.timestamp else ""
                ),
            },
        }

    async def _send_email_notification(self, notification_data: Dict[str, Any]):
        """Send email notification."""
        try:
            email_config = self.monitoring_config.email_notifications
            if not email_config or not email_config.enabled:
                return

            # Create email message
            msg = MIMEMultipart()
            msg["From"] = email_config.from_address

            # Ensure to_addresses is a list and not None
            to_addresses = email_config.to_addresses or []
            if not to_addresses:
                raise EmailNotificationError(
                    "No recipient addresses configured for email notifications"
                )

            msg["To"] = ", ".join(to_addresses)
            msg["Subject"] = email_config.subject_template.format(
                level=notification_data["threshold_level"].upper(),
                message=notification_data["message"],
            )

            # Create email body
            body = self._create_email_body(notification_data)
            msg.attach(MIMEText(body, "html"))

            # Send email
            await self._send_email_smtp(email_config, msg)

            logger.info(
                f"Email notification sent successfully to {len(email_config.to_addresses)} recipients"
            )

        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")
            raise EmailNotificationError(f"Email notification failed: {e}")

    async def _send_email_smtp(self, email_config: EmailNotificationConfig, msg: MIMEMultipart):
        """Send email using SMTP."""

        def send_email():
            with smtplib.SMTP(email_config.smtp_server, email_config.smtp_port) as server:
                if email_config.use_tls:
                    server.starttls()
                server.login(email_config.username, email_config.password)
                server.send_message(msg)

        # Run SMTP operation in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, send_email)

    def _create_email_body(self, notification_data: Dict[str, Any]) -> str:
        """Create HTML email body from notification data."""
        status_report = notification_data.get("status_report", {})

        # Determine alert color based on threshold level
        alert_colors = {"warning": "#FFA500", "critical": "#FF0000"}
        alert_color = alert_colors.get(
            notification_data.get("threshold_level", "warning"), "#FFA500"
        )

        html_body = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .alert-header {{ background-color: {alert_color}; color: white; padding: 15px; border-radius: 5px; }}
                .status-section {{ margin: 15px 0; padding: 10px; border-left: 3px solid #ccc; }}
                .status-good {{ border-left-color: #28a745; }}
                .status-warning {{ border-left-color: #ffc107; }}
                .status-critical {{ border-left-color: #dc3545; }}
                .metric {{ display: inline-block; margin: 10px 15px 10px 0; }}
                .metric-value {{ font-weight: bold; font-size: 1.2em; }}
                .timestamp {{ color: #666; font-size: 0.9em; }}
            </style>
        </head>
        <body>
            <div class="alert-header">
                <h2>AWS Identity Center Alert: {notification_data['threshold_level'].upper()}</h2>
                <p>{notification_data['message']}</p>
            </div>

            <div class="status-section">
                <h3>Overall Health Status</h3>
                <p><strong>Status:</strong> {status_report['overall_health']}</p>
                <p><strong>Message:</strong> {status_report['health_message']}</p>
            </div>

            <div class="status-section">
                <h3>Key Metrics</h3>
                <div class="metric">
                    <div class="metric-value">{status_report['provisioning_active']}</div>
                    <div>Active Provisioning</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{status_report['provisioning_failed']}</div>
                    <div>Failed Provisioning</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{status_report['orphaned_assignments']}</div>
                    <div>Orphaned Assignments</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{status_report['sync_issues']}</div>
                    <div>Sync Issues</div>
                </div>
            </div>

            <div class="status-section">
                <h3>Resource Summary</h3>
                <div class="metric">
                    <div class="metric-value">{status_report['total_users']}</div>
                    <div>Total Users</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{status_report['total_groups']}</div>
                    <div>Total Groups</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{status_report['total_permission_sets']}</div>
                    <div>Permission Sets</div>
                </div>
            </div>

            <div class="timestamp">
                <p><strong>Alert Generated:</strong> {notification_data['timestamp']}</p>
                <p><strong>Status Report Time:</strong> {status_report['report_timestamp']}</p>
            </div>
        </body>
        </html>
        """

        return html_body

    async def _send_webhook_notification(self, notification_data: Dict[str, Any]):
        """Send webhook notification."""
        try:
            webhook_config = self.monitoring_config.webhook_notifications
            if not webhook_config or not webhook_config.enabled:
                return

            # Prepare payload
            if webhook_config.payload_template:
                # Use custom payload template - flatten data for template formatting
                template_data = {**notification_data, **notification_data.get("status_report", {})}
                try:
                    payload_str = webhook_config.payload_template.format(**template_data)
                    payload = json.loads(payload_str)
                except (KeyError, json.JSONDecodeError):
                    # If template formatting fails, use a simple message payload
                    payload = {
                        "message": notification_data.get("message", "No message"),
                        "level": notification_data.get("threshold_level", "unknown"),
                    }
            else:
                # Use default payload structure
                payload = {
                    "alert_type": "aws_identity_center_monitoring",
                    "level": notification_data.get("threshold_level", "unknown"),
                    "message": notification_data.get("message", "No message"),
                    "timestamp": notification_data.get("timestamp", "unknown"),
                    "status_summary": notification_data.get("status_report", {}),
                }

            # Send webhook with retry logic
            await self._send_webhook_with_retry(webhook_config, payload)

            logger.info(f"Webhook notification sent successfully to {webhook_config.url}")

        except Exception as e:
            logger.error(f"Failed to send webhook notification: {e}")
            raise WebhookNotificationError(f"Webhook notification failed: {e}")

    async def _send_webhook_with_retry(
        self, webhook_config: WebhookNotificationConfig, payload: Dict[str, Any]
    ):
        """Send webhook with retry logic."""
        last_exception = None

        for attempt in range(webhook_config.retry_attempts):
            try:
                timeout = aiohttp.ClientTimeout(total=webhook_config.timeout_seconds)

                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.request(
                        method=webhook_config.method,
                        url=webhook_config.url,
                        json=payload,
                        headers=webhook_config.headers,
                    ) as response:
                        if response.status < 400:
                            return  # Success
                        else:
                            raise aiohttp.ClientResponseError(
                                request_info=response.request_info,
                                history=response.history,
                                status=response.status,
                                message=f"HTTP {response.status}: {await response.text()}",
                            )

            except Exception as e:
                last_exception = e
                if attempt < webhook_config.retry_attempts - 1:
                    await asyncio.sleep(webhook_config.retry_delay_seconds)
                    logger.warning(f"Webhook attempt {attempt + 1} failed, retrying: {e}")
                else:
                    logger.error(f"All webhook attempts failed: {e}")

        if last_exception:
            raise last_exception

    async def _send_log_notification(self, notification_data: Dict[str, Any]):
        """Send log notification."""
        try:
            log_config = self.monitoring_config.log_notifications
            if not log_config or not log_config.enabled:
                return

            # Get logger for notifications
            notification_logger = logging.getLogger("awsideman.notifications")

            # Create log message
            log_message = self._create_log_message(notification_data)

            # Log at appropriate level
            log_level = getattr(logging, log_config.log_level.upper())
            notification_logger.log(log_level, log_message)

        except Exception as e:
            logger.error(f"Failed to send log notification: {e}")
            # Don't raise exception for log notifications to avoid infinite loops

    def _create_log_message(self, notification_data: Dict[str, Any]) -> str:
        """Create structured log message from notification data."""
        status_report = notification_data.get("status_report", {})

        return (
            f"AWS Identity Center Alert [{notification_data.get('threshold_level', 'unknown').upper()}]: "
            f"{notification_data.get('message', 'No message')} | "
            f"Health: {status_report.get('overall_health', 'unknown')} | "
            f"Provisioning Active: {status_report.get('provisioning_active', 0)} | "
            f"Provisioning Failed: {status_report.get('provisioning_failed', 0)} | "
            f"Orphaned Assignments: {status_report.get('orphaned_assignments', 0)} | "
            f"Sync Issues: {status_report.get('sync_issues', 0)} | "
            f"Users: {status_report.get('total_users', 0)} | "
            f"Groups: {status_report.get('total_groups', 0)} | "
            f"Permission Sets: {status_report.get('total_permission_sets', 0)}"
        )

    async def test_notifications(self) -> Dict[str, bool]:
        """Test all configured notification methods."""
        results = {}

        # Create test notification data
        test_data = {
            "timestamp": datetime.now().isoformat(),
            "threshold_level": "warning",
            "message": "Test notification from AWS Identity Center monitoring",
            "status_report": {
                "overall_health": "healthy",
                "health_message": "All systems operational",
                "provisioning_active": 0,
                "provisioning_failed": 0,
                "orphaned_assignments": 0,
                "sync_issues": 0,
                "total_users": 100,
                "total_groups": 10,
                "total_permission_sets": 5,
                "report_timestamp": datetime.now().isoformat(),
            },
        }

        # Test email notifications
        if (
            self.monitoring_config.email_notifications
            and self.monitoring_config.email_notifications.enabled
        ):
            try:
                await self._send_email_notification(test_data)
                results["email"] = True
            except Exception as e:
                logger.error(f"Email notification test failed: {e}")
                results["email"] = False

        # Test webhook notifications
        if (
            self.monitoring_config.webhook_notifications
            and self.monitoring_config.webhook_notifications.enabled
        ):
            try:
                await self._send_webhook_notification(test_data)
                results["webhook"] = True
            except Exception as e:
                logger.error(f"Webhook notification test failed: {e}")
                results["webhook"] = False

        # Test log notifications
        if (
            self.monitoring_config.log_notifications
            and self.monitoring_config.log_notifications.enabled
        ):
            try:
                await self._send_log_notification(test_data)
                results["log"] = True
            except Exception as e:
                logger.error(f"Log notification test failed: {e}")
                results["log"] = False

        return results
