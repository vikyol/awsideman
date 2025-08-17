"""
Demonstration of comprehensive error handling and recovery capabilities.

This example shows how the enhanced backup and restore managers handle
various error scenarios with retry logic, partial recovery, and rollback.
"""

import asyncio
import logging
from datetime import datetime

from src.awsideman.backup_restore.enhanced_backup_manager import EnhancedBackupManager
from src.awsideman.backup_restore.error_handling import (
    ErrorAnalyzer,
    RetryConfig,
    create_error_handling_system,
)
from src.awsideman.backup_restore.models import BackupOptions, BackupType, GroupData, UserData

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MockCollector:
    """Mock collector that simulates various error scenarios."""

    def __init__(self, scenario: str = "success"):
        self.scenario = scenario
        self.call_count = 0

    async def validate_connection(self):
        """Simulate connection validation with different scenarios."""
        self.call_count += 1

        if self.scenario == "transient_network":
            if self.call_count <= 2:
                raise ConnectionError("Temporary network issue")
        elif self.scenario == "auth_error":
            from botocore.exceptions import ClientError

            error_response = {
                "Error": {"Code": "AccessDenied", "Message": "User is not authorized"}
            }
            raise ClientError(error_response, "ListUsers")
        elif self.scenario == "throttling":
            if self.call_count <= 1:
                from botocore.exceptions import ClientError

                error_response = {"Error": {"Code": "Throttling", "Message": "Rate exceeded"}}
                raise ClientError(error_response, "ListUsers")

        # Return successful validation
        from src.awsideman.backup_restore.models import ValidationResult

        return ValidationResult(is_valid=True, errors=[], warnings=[])

    async def collect_users(self, options):
        """Simulate user collection."""
        if self.scenario == "partial_failure" and self.call_count > 3:
            raise Exception("Failed to collect users")

        return [
            UserData(user_id="user1", user_name="alice"),
            UserData(user_id="user2", user_name="bob"),
        ]

    async def collect_groups(self, options):
        """Simulate group collection."""
        return [GroupData(group_id="group1", display_name="Administrators")]

    async def collect_permission_sets(self, options):
        """Simulate permission set collection."""
        if self.scenario == "partial_failure":
            raise Exception("Permission set service unavailable")
        return []

    async def collect_assignments(self, options):
        """Simulate assignment collection."""
        return []


class MockStorageEngine:
    """Mock storage engine for demonstration."""

    def __init__(self, scenario: str = "success"):
        self.scenario = scenario
        self.stored_backups = {}

    async def store_backup(self, backup_data):
        """Simulate backup storage."""
        if self.scenario == "storage_failure":
            raise Exception("Storage service unavailable")

        backup_id = f"backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        self.stored_backups[backup_id] = backup_data
        return backup_id

    async def retrieve_backup(self, backup_id):
        """Simulate backup retrieval."""
        return self.stored_backups.get(backup_id)

    async def verify_integrity(self, backup_id):
        """Simulate integrity verification."""
        from src.awsideman.backup_restore.models import ValidationResult

        return ValidationResult(is_valid=True, errors=[], warnings=[])


class MockValidator:
    """Mock validator for demonstration."""

    async def validate_backup_data(self, backup_data):
        """Simulate backup data validation."""
        from src.awsideman.backup_restore.models import ValidationResult

        return ValidationResult(is_valid=True, errors=[], warnings=[])


async def demonstrate_successful_backup_with_retry():
    """Demonstrate successful backup after transient network issues."""
    print("\n=== Demonstrating Successful Backup with Retry ===")

    # Create mock components with transient network issues
    collector = MockCollector(scenario="transient_network")
    storage_engine = MockStorageEngine()
    validator = MockValidator()

    # Create enhanced backup manager with fast retry for demo
    retry_config = RetryConfig(max_retries=3, base_delay=0.1, max_delay=1.0)

    manager = EnhancedBackupManager(
        collector=collector,
        storage_engine=storage_engine,
        validator=validator,
        retry_config=retry_config,
        instance_arn="arn:aws:sso:::instance/demo-instance",
        source_account="123456789012",
        source_region="us-east-1",
    )

    # Execute backup
    options = BackupOptions(backup_type=BackupType.FULL)
    result = await manager.create_backup(options)

    print(f"Backup Result: {result.success}")
    print(f"Message: {result.message}")
    print(f"Backup ID: {result.backup_id}")
    print(f"Connection validation attempts: {collector.call_count}")

    return result


async def demonstrate_backup_with_partial_recovery():
    """Demonstrate backup with partial recovery when some resources fail."""
    print("\n=== Demonstrating Backup with Partial Recovery ===")

    # Create mock components with partial failure
    collector = MockCollector(scenario="partial_failure")
    storage_engine = MockStorageEngine()
    validator = MockValidator()

    # Create enhanced backup manager
    retry_config = RetryConfig(max_retries=2, base_delay=0.1)

    manager = EnhancedBackupManager(
        collector=collector,
        storage_engine=storage_engine,
        validator=validator,
        retry_config=retry_config,
        instance_arn="arn:aws:sso:::instance/demo-instance",
        source_account="123456789012",
        source_region="us-east-1",
    )

    # Execute backup
    options = BackupOptions(backup_type=BackupType.FULL)
    result = await manager.create_backup(options)

    print(f"Backup Result: {result.success}")
    print(f"Message: {result.message}")
    if result.warnings:
        print(f"Warnings: {result.warnings}")
    if result.errors:
        print(f"Errors: {result.errors[:3]}...")  # Show first 3 errors

    return result


async def demonstrate_non_retryable_error():
    """Demonstrate handling of non-retryable authorization errors."""
    print("\n=== Demonstrating Non-Retryable Authorization Error ===")

    # Create mock components with authorization error
    collector = MockCollector(scenario="auth_error")
    storage_engine = MockStorageEngine()
    validator = MockValidator()

    # Create enhanced backup manager
    retry_config = RetryConfig(max_retries=3, base_delay=0.1)

    manager = EnhancedBackupManager(
        collector=collector,
        storage_engine=storage_engine,
        validator=validator,
        retry_config=retry_config,
        instance_arn="arn:aws:sso:::instance/demo-instance",
        source_account="123456789012",
        source_region="us-east-1",
    )

    # Execute backup
    options = BackupOptions(backup_type=BackupType.FULL)
    result = await manager.create_backup(options)

    print(f"Backup Result: {result.success}")
    print(f"Message: {result.message}")
    print(f"Connection validation attempts: {collector.call_count}")
    print("Error suggestions:")
    for error in result.errors[:5]:  # Show first 5 errors/suggestions
        print(f"  - {error}")

    return result


async def demonstrate_error_analysis():
    """Demonstrate error analysis and categorization."""
    print("\n=== Demonstrating Error Analysis ===")

    # Create error analyzer
    analyzer = ErrorAnalyzer()

    # Analyze different types of errors
    errors_to_analyze = [
        # Throttling error
        {
            "exception": Exception("Throttling: Rate exceeded"),
            "context": {"operation": "collect_users"},
        },
        # Network error
        {
            "exception": ConnectionError("Connection timeout"),
            "context": {"operation": "validate_connection"},
        },
        # Validation error
        {
            "exception": ValueError("Invalid parameter value"),
            "context": {"operation": "create_backup"},
        },
    ]

    for i, error_data in enumerate(errors_to_analyze, 1):
        print(f"\nError {i} Analysis:")
        error_info = analyzer.analyze_error(error_data["exception"], error_data["context"])

        print(f"  Category: {error_info.category.value}")
        print(f"  Severity: {error_info.severity.value}")
        print(f"  Recoverable: {error_info.recoverable}")
        print(f"  Suggested Actions: {error_info.suggested_actions[:2]}")
        print(f"  Remediation Steps: {error_info.remediation_steps[:2]}")


async def demonstrate_comprehensive_error_handling():
    """Demonstrate the complete error handling system."""
    print("\n=== Demonstrating Comprehensive Error Handling System ===")

    # Create complete error handling system
    error_system = create_error_handling_system()

    print("Error Handling System Components:")
    for component_name, component in error_system.items():
        print(f"  - {component_name}: {type(component).__name__}")

    # Demonstrate error reporting
    from src.awsideman.backup_restore.error_handling import ErrorCategory, ErrorInfo, ErrorSeverity

    sample_errors = [
        ErrorInfo(
            category=ErrorCategory.RATE_LIMITING,
            severity=ErrorSeverity.MEDIUM,
            message="API rate limit exceeded",
            suggested_actions=["Implement exponential backoff", "Reduce request rate"],
            remediation_steps=["Wait for rate limit reset", "Use batch operations"],
        ),
        ErrorInfo(
            category=ErrorCategory.AUTHORIZATION,
            severity=ErrorSeverity.HIGH,
            message="Access denied to Identity Center",
            suggested_actions=["Check IAM permissions", "Verify role trust policy"],
            remediation_steps=["Update IAM policy", "Configure cross-account access"],
        ),
    ]

    # Generate error report
    error_report = error_system["error_reporter"].generate_error_report(
        sample_errors, {"operation_type": "backup", "operation_id": "demo-123"}
    )

    print("\nError Report Summary:")
    print(f"  Total Errors: {error_report['summary']['total_errors']}")
    print(f"  Categories: {error_report['summary']['categories']}")
    print(f"  Immediate Actions: {error_report['remediation']['immediate_actions'][:3]}")
    print(f"  Next Steps: {error_report['next_steps'][:3]}")


async def main():
    """Run all demonstrations."""
    print("AWS Identity Manager - Error Handling and Recovery Demonstration")
    print("=" * 70)

    try:
        # Run demonstrations
        await demonstrate_successful_backup_with_retry()
        await demonstrate_backup_with_partial_recovery()
        await demonstrate_non_retryable_error()
        await demonstrate_error_analysis()
        await demonstrate_comprehensive_error_handling()

        print("\n" + "=" * 70)
        print("All demonstrations completed successfully!")

    except Exception as e:
        logger.error(f"Demonstration failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
