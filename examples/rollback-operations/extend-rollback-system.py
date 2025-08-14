#!/usr/bin/env python3
"""
Example: Extending the Rollback System

This example demonstrates how to extend the rollback system with:
1. Custom validation rules
2. Custom storage backends
3. Custom notification systems
4. Custom rollback actions

Run this example to see how to integrate custom functionality
with the rollback system.
"""

import logging
import smtplib
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from email.mime.text import MimeText
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

# Import rollback system components
from awsideman.rollback import (
    OperationLogger,
    OperationRecord,
    RollbackPlan,
    RollbackProcessor,
    RollbackResult,
    RollbackValidation,
)
from awsideman.rollback.exceptions import RollbackError
from awsideman.rollback.storage import OperationStore


# 1. Custom Validation Rules
class ValidationRule(ABC):
    """Base class for custom validation rules."""

    @abstractmethod
    def validate(self, operation: OperationRecord) -> List[str]:
        """Return list of validation errors."""
        pass


class BusinessHoursValidationRule(ValidationRule):
    """Validation rule that restricts rollbacks to business hours."""

    def __init__(self, start_hour: int = 9, end_hour: int = 17):
        self.start_hour = start_hour
        self.end_hour = end_hour

    def validate(self, operation: OperationRecord) -> List[str]:
        errors = []
        current_hour = datetime.now().hour

        if not (self.start_hour <= current_hour <= self.end_hour):
            errors.append(
                f"Rollbacks are only allowed during business hours "
                f"({self.start_hour}:00 - {self.end_hour}:00)"
            )

        return errors


class HighPrivilegeValidationRule(ValidationRule):
    """Validation rule for high-privilege permission sets."""

    def __init__(self, high_privilege_keywords: List[str] = None):
        self.high_privilege_keywords = high_privilege_keywords or [
            "Admin",
            "Full",
            "Root",
            "PowerUser",
        ]

    def validate(self, operation: OperationRecord) -> List[str]:
        errors = []

        # Check if permission set is high privilege
        is_high_privilege = any(
            keyword.lower() in operation.permission_set_name.lower()
            for keyword in self.high_privilege_keywords
        )

        if is_high_privilege:
            # Check if operation has approval metadata
            approval = operation.metadata.get("approval")
            if not approval:
                errors.append(
                    f"High-privilege rollbacks require approval metadata. "
                    f"Permission set: {operation.permission_set_name}"
                )
            elif not approval.get("approved_by"):
                errors.append("High-privilege rollbacks require approval from a manager")

        return errors


class ComplianceValidationRule(ValidationRule):
    """Validation rule for compliance requirements."""

    def validate(self, operation: OperationRecord) -> List[str]:
        errors = []

        # Check if operation has required compliance metadata
        required_fields = ["business_justification", "change_ticket"]

        for field in required_fields:
            if field not in operation.metadata:
                errors.append(f"Missing required compliance field: {field}")

        # Check if rollback is within compliance window (e.g., 30 days)
        operation_age = datetime.now(timezone.utc) - operation.timestamp
        if operation_age.days > 30:
            errors.append(
                f"Operation is {operation_age.days} days old. "
                "Rollbacks older than 30 days require compliance review."
            )

        return errors


# 2. Custom Storage Backend
class DynamoDBOperationStore(OperationStore):
    """DynamoDB-based storage backend for operation records."""

    def __init__(self, table_name: str, region_name: str = "us-east-1"):
        self.table_name = table_name
        self.region_name = region_name
        self.dynamodb = boto3.resource("dynamodb", region_name=region_name)
        self.table = self.dynamodb.Table(table_name)

    def save_operation(self, operation: OperationRecord) -> None:
        """Save operation to DynamoDB."""
        try:
            item = self._operation_to_item(operation)
            self.table.put_item(Item=item)
        except ClientError as e:
            raise RollbackError(f"Failed to save operation to DynamoDB: {e}")

    def load_operations(self, filters: Optional[Dict] = None) -> List[OperationRecord]:
        """Load operations from DynamoDB with optional filtering."""
        try:
            if filters:
                # Build filter expression
                filter_expression = self._build_filter_expression(filters)
                response = self.table.scan(FilterExpression=filter_expression)
            else:
                response = self.table.scan()

            operations = []
            for item in response["Items"]:
                operations.append(self._item_to_operation(item))

            return operations
        except ClientError as e:
            raise RollbackError(f"Failed to load operations from DynamoDB: {e}")

    def update_operation(self, operation_id: str, updates: Dict[str, Any]) -> None:
        """Update operation in DynamoDB."""
        try:
            update_expression = "SET "
            expression_values = {}

            for key, value in updates.items():
                update_expression += f"{key} = :{key}, "
                expression_values[f":{key}"] = value

            update_expression = update_expression.rstrip(", ")

            self.table.update_item(
                Key={"operation_id": operation_id},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values,
            )
        except ClientError as e:
            raise RollbackError(f"Failed to update operation in DynamoDB: {e}")

    def delete_operation(self, operation_id: str) -> None:
        """Delete operation from DynamoDB."""
        try:
            self.table.delete_item(Key={"operation_id": operation_id})
        except ClientError as e:
            raise RollbackError(f"Failed to delete operation from DynamoDB: {e}")

    def _operation_to_item(self, operation: OperationRecord) -> Dict[str, Any]:
        """Convert OperationRecord to DynamoDB item."""
        item = operation.to_dict()
        # Convert datetime to ISO string for DynamoDB
        item["timestamp"] = operation.timestamp.isoformat()
        return item

    def _item_to_operation(self, item: Dict[str, Any]) -> OperationRecord:
        """Convert DynamoDB item to OperationRecord."""
        # Convert ISO string back to datetime
        item["timestamp"] = datetime.fromisoformat(item["timestamp"])
        return OperationRecord.from_dict(item)

    def _build_filter_expression(self, filters: Dict[str, Any]):
        """Build DynamoDB filter expression from filters."""
        # Simplified implementation - in practice, you'd use boto3's Attr
        # This is just for demonstration
        from boto3.dynamodb.conditions import Attr

        conditions = []

        if "operation_type" in filters:
            conditions.append(Attr("operation_type").eq(filters["operation_type"]))

        if "principal_name" in filters:
            conditions.append(Attr("principal_name").contains(filters["principal_name"]))

        if "rolled_back" in filters:
            conditions.append(Attr("rolled_back").eq(filters["rolled_back"]))

        # Combine conditions with AND
        if conditions:
            filter_expr = conditions[0]
            for condition in conditions[1:]:
                filter_expr = filter_expr & condition
            return filter_expr

        return None


# 3. Custom Notification System
class NotificationSystem(ABC):
    """Base class for notification systems."""

    @abstractmethod
    def send_rollback_notification(
        self, operation: OperationRecord, result: RollbackResult
    ) -> None:
        """Send notification about rollback operation."""
        pass


class EmailNotificationSystem(NotificationSystem):
    """Email-based notification system."""

    def __init__(self, smtp_server: str, smtp_port: int, username: str, password: str):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password

    def send_rollback_notification(
        self, operation: OperationRecord, result: RollbackResult
    ) -> None:
        """Send email notification about rollback."""
        try:
            # Determine recipients
            recipients = self._get_notification_recipients(operation)

            # Create email content
            subject = f"Rollback {'Completed' if result.success else 'Failed'}: {operation.permission_set_name}"
            body = self._create_email_body(operation, result)

            # Send email
            msg = MimeText(body)
            msg["Subject"] = subject
            msg["From"] = self.username
            msg["To"] = ", ".join(recipients)

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)

            logging.info(f"Rollback notification sent to {recipients}")

        except Exception as e:
            logging.error(f"Failed to send rollback notification: {e}")

    def _get_notification_recipients(self, operation: OperationRecord) -> List[str]:
        """Determine who should receive notifications."""
        recipients = []

        # Add operation performer
        if "user" in operation.metadata:
            recipients.append(operation.metadata["user"])

        # Add security team for high-privilege operations
        if any(
            keyword in operation.permission_set_name.lower()
            for keyword in ["admin", "full", "root"]
        ):
            recipients.append("security-team@company.com")

        # Add compliance team for production accounts
        if any("prod" in name.lower() for name in operation.account_names):
            recipients.append("compliance@company.com")

        return recipients

    def _create_email_body(self, operation: OperationRecord, result: RollbackResult) -> str:
        """Create email body content."""
        status = "COMPLETED" if result.success else "FAILED"

        body = f"""
Rollback Operation {status}

Operation Details:
- Operation ID: {operation.operation_id}
- Original Operation: {operation.operation_type}
- Principal: {operation.principal_name} ({operation.principal_type})
- Permission Set: {operation.permission_set_name}
- Accounts: {', '.join(operation.account_names)}
- Original Timestamp: {operation.timestamp}

Rollback Results:
- Status: {status}
- Rollback Operation ID: {result.rollback_operation_id or 'N/A'}
- Successful Actions: {result.successful_actions}
- Failed Actions: {result.failed_actions}
- Duration: {result.duration:.2f} seconds
"""

        if not result.success and result.error_message:
            body += f"\nError Message: {result.error_message}"

        if result.action_results:
            body += "\n\nDetailed Results:\n"
            for action_result in result.action_results:
                body += f"- {action_result}\n"

        body += f"\nTimestamp: {datetime.now()}\n"

        return body


class SlackNotificationSystem(NotificationSystem):
    """Slack-based notification system."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send_rollback_notification(
        self, operation: OperationRecord, result: RollbackResult
    ) -> None:
        """Send Slack notification about rollback."""
        try:
            import requests

            status_emoji = "✅" if result.success else "❌"
            status_text = "completed successfully" if result.success else "failed"

            message = {
                "text": f"{status_emoji} Rollback {status_text}",
                "attachments": [
                    {
                        "color": "good" if result.success else "danger",
                        "fields": [
                            {
                                "title": "Operation ID",
                                "value": operation.operation_id,
                                "short": True,
                            },
                            {
                                "title": "Principal",
                                "value": f"{operation.principal_name} ({operation.principal_type})",
                                "short": True,
                            },
                            {
                                "title": "Permission Set",
                                "value": operation.permission_set_name,
                                "short": True,
                            },
                            {
                                "title": "Accounts",
                                "value": ", ".join(operation.account_names),
                                "short": True,
                            },
                            {
                                "title": "Success Rate",
                                "value": f"{result.get_success_rate():.1f}%",
                                "short": True,
                            },
                            {
                                "title": "Duration",
                                "value": f"{result.duration:.2f}s",
                                "short": True,
                            },
                        ],
                    }
                ],
            }

            if not result.success and result.error_message:
                message["attachments"][0]["fields"].append(
                    {"title": "Error", "value": result.error_message, "short": False}
                )

            response = requests.post(self.webhook_url, json=message)
            response.raise_for_status()

            logging.info("Rollback notification sent to Slack")

        except Exception as e:
            logging.error(f"Failed to send Slack notification: {e}")


# 4. Extended Rollback Processor
class ExtendedRollbackProcessor(RollbackProcessor):
    """Extended rollback processor with custom validation and notifications."""

    def __init__(self, config=None):
        super().__init__(config)
        self.validation_rules: List[ValidationRule] = []
        self.notification_systems: List[NotificationSystem] = []

    def add_validation_rule(self, rule: ValidationRule) -> None:
        """Add a custom validation rule."""
        self.validation_rules.append(rule)

    def add_notification_system(self, system: NotificationSystem) -> None:
        """Add a notification system."""
        self.notification_systems.append(system)

    def validate_rollback(self, operation_id: str) -> RollbackValidation:
        """Enhanced validation with custom rules."""
        # Start with base validation
        validation = super().validate_rollback(operation_id)

        # Apply custom validation rules
        operation = self.logger.get_operation(operation_id)
        if operation:
            for rule in self.validation_rules:
                errors = rule.validate(operation)
                validation.errors.extend(errors)

        # Update validation status
        validation.is_valid = len(validation.errors) == 0

        return validation

    def execute_rollback(
        self, plan: RollbackPlan, dry_run: bool = False, batch_size: int = 10
    ) -> RollbackResult:
        """Enhanced rollback execution with notifications."""
        # Execute rollback
        result = super().execute_rollback(plan, dry_run, batch_size)

        # Send notifications if not a dry run
        if not dry_run:
            operation = self.logger.get_operation(plan.operation_id)
            if operation:
                for notification_system in self.notification_systems:
                    try:
                        notification_system.send_rollback_notification(operation, result)
                    except Exception as e:
                        logging.error(f"Notification failed: {e}")

        return result


# 5. Example Usage
def main():
    """Demonstrate extended rollback system functionality."""

    # Setup logging
    logging.basicConfig(level=logging.INFO)

    print("Extended Rollback System Example")
    print("=" * 40)

    # 1. Create extended processor with custom validation rules
    processor = ExtendedRollbackProcessor()

    # Add validation rules
    processor.add_validation_rule(BusinessHoursValidationRule(start_hour=9, end_hour=17))
    processor.add_validation_rule(HighPrivilegeValidationRule())
    processor.add_validation_rule(ComplianceValidationRule())

    # Add notification systems (configure with your actual credentials)
    # processor.add_notification_system(EmailNotificationSystem(
    #     smtp_server="smtp.company.com",
    #     smtp_port=587,
    #     username="notifications@company.com",
    #     password="password"
    # ))

    # processor.add_notification_system(SlackNotificationSystem(
    #     webhook_url="https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"
    # ))

    # 2. Create a sample operation for demonstration
    logger = OperationLogger()

    sample_operation_data = {
        "operation_type": "assign",
        "principal_id": "user-123456789",
        "principal_type": "USER",
        "principal_name": "john.doe",
        "permission_set_arn": "arn:aws:sso:::permissionSet/ins-123/ps-456",
        "permission_set_name": "AdminAccess",  # High privilege
        "account_ids": ["123456789012"],
        "account_names": ["Production"],
        "results": [{"account_id": "123456789012", "success": True}],
        "metadata": {
            "source": "cli",
            "user": "admin@company.com",
            "business_justification": "Emergency access for incident response",
            "change_ticket": "CHG-12345",
            "approval": {
                "approved_by": "manager@company.com",
                "approval_date": "2024-01-15T10:00:00Z",
            },
        },
    }

    operation_id = logger.log_operation(sample_operation_data)
    print(f"Sample operation logged: {operation_id}")

    # 3. Demonstrate custom validation
    print("\n3. Testing Custom Validation")
    print("-" * 30)

    validation = processor.validate_rollback(operation_id)
    print(f"Validation result: {'VALID' if validation.is_valid else 'INVALID'}")

    if validation.errors:
        print("Validation errors:")
        for error in validation.errors:
            print(f"  - {error}")

    if validation.warnings:
        print("Validation warnings:")
        for warning in validation.warnings:
            print(f"  - {warning}")

    # 4. Demonstrate custom storage backend (if DynamoDB table exists)
    print("\n4. Testing Custom Storage Backend")
    print("-" * 35)

    try:
        # Note: This requires a DynamoDB table named 'awsideman-operations'
        # Create the table first or comment out this section

        # custom_store = DynamoDBOperationStore("awsideman-operations")
        # custom_logger = OperationLogger()
        # custom_logger.storage = custom_store

        # # Test saving to DynamoDB
        # test_operation_id = custom_logger.log_operation(sample_operation_data)
        # print(f"Operation saved to DynamoDB: {test_operation_id}")

        # # Test loading from DynamoDB
        # loaded_ops = custom_logger.get_operations({"operation_type": "assign"})
        # print(f"Loaded {len(loaded_ops)} operations from DynamoDB")

        print("Custom storage backend test skipped (requires DynamoDB table)")

    except Exception as e:
        print(f"Custom storage backend test failed: {e}")

    # 5. Demonstrate rollback with notifications (dry run)
    print("\n5. Testing Rollback with Notifications")
    print("-" * 38)

    if validation.is_valid:
        try:
            plan = processor.generate_plan(operation_id)
            print(f"Generated rollback plan with {len(plan.actions)} actions")

            # Execute dry run
            result = processor.execute_rollback(plan, dry_run=True)
            print(f"Dry run result: {'SUCCESS' if result.success else 'FAILED'}")

            if result.success:
                print(f"Would perform {result.successful_actions} rollback actions")
            else:
                print(f"Dry run failed: {result.error_message}")

        except Exception as e:
            print(f"Rollback test failed: {e}")
    else:
        print("Skipping rollback test due to validation errors")

    print("\n" + "=" * 40)
    print("Extended Rollback System Example Complete")


if __name__ == "__main__":
    main()
