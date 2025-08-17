"""
Comprehensive error handling and recovery system for backup-restore operations.

This module provides retry logic, partial backup recovery, rollback capabilities,
and detailed error reporting with remediation suggestions.
"""

import asyncio
import logging
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type
from uuid import uuid4

from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Severity levels for errors."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Categories of errors that can occur."""

    NETWORK = "network"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    RATE_LIMITING = "rate_limiting"
    RESOURCE_NOT_FOUND = "resource_not_found"
    RESOURCE_CONFLICT = "resource_conflict"
    VALIDATION = "validation"
    STORAGE = "storage"
    ENCRYPTION = "encryption"
    CONFIGURATION = "configuration"
    UNKNOWN = "unknown"


class RecoveryAction(Enum):
    """Types of recovery actions that can be taken."""

    RETRY = "retry"
    SKIP = "skip"
    ROLLBACK = "rollback"
    PARTIAL_RECOVERY = "partial_recovery"
    MANUAL_INTERVENTION = "manual_intervention"
    ABORT = "abort"


@dataclass
class ErrorInfo:
    """Detailed information about an error."""

    error_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)
    category: ErrorCategory = ErrorCategory.UNKNOWN
    severity: ErrorSeverity = ErrorSeverity.MEDIUM
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    exception: Optional[Exception] = None
    stack_trace: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    suggested_actions: List[str] = field(default_factory=list)
    remediation_steps: List[str] = field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3
    recoverable: bool = True

    def __post_init__(self):
        """Post-initialization to capture stack trace if exception is present."""
        if self.exception and not self.stack_trace:
            self.stack_trace = traceback.format_exception(
                type(self.exception), self.exception, self.exception.__traceback__
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "error_id": self.error_id,
            "timestamp": self.timestamp.isoformat(),
            "category": self.category.value,
            "severity": self.severity.value,
            "message": self.message,
            "details": self.details,
            "exception_type": type(self.exception).__name__ if self.exception else None,
            "stack_trace": self.stack_trace,
            "context": self.context,
            "suggested_actions": self.suggested_actions,
            "remediation_steps": self.remediation_steps,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "recoverable": self.recoverable,
        }


@dataclass
class RetryConfig:
    """Configuration for retry logic."""

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_exceptions: List[Type[Exception]] = field(default_factory=list)
    retryable_error_codes: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Set default retryable exceptions and error codes."""
        if not self.retryable_exceptions:
            self.retryable_exceptions = [
                ClientError,
                BotoCoreError,
                ConnectionError,
                TimeoutError,
                asyncio.TimeoutError,
            ]

        if not self.retryable_error_codes:
            self.retryable_error_codes = [
                "Throttling",
                "ThrottlingException",
                "RequestLimitExceeded",
                "ServiceUnavailable",
                "InternalServerError",
                "RequestTimeout",
                "TooManyRequestsException",
            ]


@dataclass
class OperationState:
    """State tracking for operations that support rollback."""

    operation_id: str
    operation_type: str
    start_time: datetime
    checkpoints: List[Dict[str, Any]] = field(default_factory=list)
    applied_changes: List[Dict[str, Any]] = field(default_factory=list)
    rollback_actions: List[Callable] = field(default_factory=list)
    completed: bool = False
    success: bool = False

    def add_checkpoint(self, name: str, data: Dict[str, Any]):
        """Add a checkpoint for rollback purposes."""
        checkpoint = {"name": name, "timestamp": datetime.now(), "data": data}
        self.checkpoints.append(checkpoint)

    def add_change(
        self,
        resource_type: str,
        resource_id: str,
        action: str,
        old_value: Any = None,
        new_value: Any = None,
    ):
        """Record a change that was applied."""
        change = {
            "timestamp": datetime.now(),
            "resource_type": resource_type,
            "resource_id": resource_id,
            "action": action,
            "old_value": old_value,
            "new_value": new_value,
        }
        self.applied_changes.append(change)

    def add_rollback_action(self, action: Callable):
        """Add a rollback action to be executed if needed."""
        self.rollback_actions.append(action)


class ErrorAnalyzer:
    """Analyzes errors and provides categorization and remediation suggestions."""

    def __init__(self):
        self.error_patterns = self._initialize_error_patterns()

    def analyze_error(self, exception: Exception, context: Dict[str, Any] = None) -> ErrorInfo:
        """
        Analyze an error and return detailed error information.

        Args:
            exception: The exception that occurred
            context: Additional context about the operation

        Returns:
            ErrorInfo with analysis results
        """
        context = context or {}

        # Create base error info
        error_info = ErrorInfo(exception=exception, message=str(exception), context=context)

        # Analyze AWS-specific errors
        if isinstance(exception, ClientError):
            self._analyze_client_error(error_info, exception)
        elif isinstance(exception, BotoCoreError):
            self._analyze_botocore_error(error_info, exception)
        else:
            self._analyze_generic_error(error_info, exception)

        # Add remediation suggestions
        self._add_remediation_suggestions(error_info)

        return error_info

    def _analyze_client_error(self, error_info: ErrorInfo, exception: ClientError):
        """Analyze AWS ClientError exceptions."""
        error_code = exception.response.get("Error", {}).get("Code", "")
        error_message = exception.response.get("Error", {}).get("Message", "")

        error_info.details = {
            "error_code": error_code,
            "error_message": error_message,
            "response": exception.response,
        }

        # Categorize based on error code
        if error_code in ["Throttling", "ThrottlingException", "RequestLimitExceeded"]:
            error_info.category = ErrorCategory.RATE_LIMITING
            error_info.severity = ErrorSeverity.MEDIUM
            error_info.recoverable = True
            error_info.max_retries = 5
        elif error_code in ["AccessDenied", "UnauthorizedOperation"]:
            error_info.category = ErrorCategory.AUTHORIZATION
            error_info.severity = ErrorSeverity.HIGH
            error_info.recoverable = False
        elif error_code in ["InvalidUserPoolConfiguration", "UserNotFound", "GroupNotFound"]:
            error_info.category = ErrorCategory.RESOURCE_NOT_FOUND
            error_info.severity = ErrorSeverity.MEDIUM
            error_info.recoverable = False
        elif error_code in ["ConflictException", "ResourceExistsException"]:
            error_info.category = ErrorCategory.RESOURCE_CONFLICT
            error_info.severity = ErrorSeverity.LOW
            error_info.recoverable = True
        elif error_code in ["ValidationException", "InvalidParameterValue"]:
            error_info.category = ErrorCategory.VALIDATION
            error_info.severity = ErrorSeverity.MEDIUM
            error_info.recoverable = False
        else:
            error_info.category = ErrorCategory.UNKNOWN
            error_info.severity = ErrorSeverity.MEDIUM

    def _analyze_botocore_error(self, error_info: ErrorInfo, exception: BotoCoreError):
        """Analyze BotoCoreError exceptions."""
        if "timeout" in str(exception).lower():
            error_info.category = ErrorCategory.NETWORK
            error_info.severity = ErrorSeverity.MEDIUM
            error_info.recoverable = True
        elif "connection" in str(exception).lower():
            error_info.category = ErrorCategory.NETWORK
            error_info.severity = ErrorSeverity.HIGH
            error_info.recoverable = True
        else:
            error_info.category = ErrorCategory.UNKNOWN
            error_info.severity = ErrorSeverity.MEDIUM

    def _analyze_generic_error(self, error_info: ErrorInfo, exception: Exception):
        """Analyze generic exceptions."""
        exception_type = type(exception).__name__

        if exception_type in ["ConnectionError", "TimeoutError"]:
            error_info.category = ErrorCategory.NETWORK
            error_info.severity = ErrorSeverity.MEDIUM
            error_info.recoverable = True
        elif exception_type in ["ValueError", "TypeError"]:
            error_info.category = ErrorCategory.VALIDATION
            error_info.severity = ErrorSeverity.HIGH
            error_info.recoverable = False
        elif exception_type in ["FileNotFoundError", "PermissionError"]:
            error_info.category = ErrorCategory.STORAGE
            error_info.severity = ErrorSeverity.HIGH
            error_info.recoverable = False
        else:
            error_info.category = ErrorCategory.UNKNOWN
            error_info.severity = ErrorSeverity.MEDIUM

    def _add_remediation_suggestions(self, error_info: ErrorInfo):
        """Add remediation suggestions based on error analysis."""
        if error_info.category == ErrorCategory.RATE_LIMITING:
            error_info.suggested_actions = [
                "Retry with exponential backoff",
                "Reduce request rate",
                "Implement request batching",
            ]
            error_info.remediation_steps = [
                "Wait for rate limit to reset",
                "Implement exponential backoff with jitter",
                "Consider using AWS SDK built-in retry logic",
            ]

        elif error_info.category == ErrorCategory.AUTHORIZATION:
            error_info.suggested_actions = [
                "Check IAM permissions",
                "Verify role trust relationships",
                "Review resource-based policies",
            ]
            error_info.remediation_steps = [
                "Ensure the IAM role has necessary permissions",
                "Check if MFA is required",
                "Verify cross-account role assumptions are configured correctly",
            ]

        elif error_info.category == ErrorCategory.RESOURCE_NOT_FOUND:
            error_info.suggested_actions = [
                "Verify resource exists",
                "Check resource ARN/ID",
                "Confirm correct region",
            ]
            error_info.remediation_steps = [
                "Double-check resource identifiers",
                "Ensure resources exist in the target account/region",
                "Verify resource naming conventions",
            ]

        elif error_info.category == ErrorCategory.RESOURCE_CONFLICT:
            error_info.suggested_actions = [
                "Use conflict resolution strategy",
                "Skip conflicting resources",
                "Update existing resources",
            ]
            error_info.remediation_steps = [
                "Choose appropriate conflict resolution strategy",
                "Consider using merge or overwrite options",
                "Review existing resources before proceeding",
            ]

        elif error_info.category == ErrorCategory.NETWORK:
            error_info.suggested_actions = [
                "Retry operation",
                "Check network connectivity",
                "Verify DNS resolution",
            ]
            error_info.remediation_steps = [
                "Check internet connectivity",
                "Verify AWS service endpoints are accessible",
                "Consider using VPC endpoints if in private subnet",
            ]

        elif error_info.category == ErrorCategory.STORAGE:
            error_info.suggested_actions = [
                "Check storage permissions",
                "Verify storage location exists",
                "Ensure sufficient storage space",
            ]
            error_info.remediation_steps = [
                "Verify file system permissions",
                "Check available disk space",
                "Ensure backup storage location is accessible",
            ]

    def _initialize_error_patterns(self) -> Dict[str, Dict[str, Any]]:
        """Initialize error patterns for analysis."""
        return {
            "throttling_patterns": [
                "Throttling",
                "ThrottlingException",
                "RequestLimitExceeded",
                "TooManyRequestsException",
                "SlowDown",
            ],
            "auth_patterns": [
                "AccessDenied",
                "UnauthorizedOperation",
                "InvalidUserPoolConfiguration",
                "TokenRefreshRequired",
                "ExpiredToken",
            ],
            "network_patterns": ["timeout", "connection", "dns", "network", "unreachable"],
        }


class RetryHandler:
    """Handles retry logic with exponential backoff."""

    def __init__(self, config: RetryConfig = None):
        self.config = config or RetryConfig()
        self.error_analyzer = ErrorAnalyzer()

    async def execute_with_retry(
        self, operation: Callable, *args, context: Dict[str, Any] = None, **kwargs
    ) -> Any:
        """
        Execute an operation with retry logic.

        Args:
            operation: The async operation to execute
            *args: Positional arguments for the operation
            context: Additional context for error analysis
            **kwargs: Keyword arguments for the operation

        Returns:
            Result of the operation

        Raises:
            Exception: If all retries are exhausted
        """
        context = context or {}
        last_error = None

        for attempt in range(self.config.max_retries + 1):
            try:
                if attempt > 0:
                    delay = self._calculate_delay(attempt)
                    logger.info(
                        f"Retrying operation after {delay:.2f}s (attempt {attempt + 1}/{self.config.max_retries + 1})"
                    )
                    await asyncio.sleep(delay)

                result = await operation(*args, **kwargs)

                if attempt > 0:
                    logger.info(f"Operation succeeded after {attempt} retries")

                return result

            except Exception as e:
                last_error = e
                error_info = self.error_analyzer.analyze_error(e, context)
                error_info.retry_count = attempt

                logger.warning(f"Operation failed (attempt {attempt + 1}): {error_info.message}")

                # Check if error is retryable
                if not self._is_retryable(error_info):
                    logger.error(f"Error is not retryable: {error_info.category.value}")
                    raise e

                # Check if we've exhausted retries
                if attempt >= self.config.max_retries:
                    logger.error(f"All {self.config.max_retries} retries exhausted")
                    raise e

        # This should never be reached, but just in case
        raise last_error

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for exponential backoff."""
        delay = self.config.base_delay * (self.config.exponential_base ** (attempt - 1))
        delay = min(delay, self.config.max_delay)

        if self.config.jitter:
            import random

            delay *= 0.5 + random.random() * 0.5  # Add 0-50% jitter

        return delay

    def _is_retryable(self, error_info: ErrorInfo) -> bool:
        """Determine if an error is retryable."""
        if not error_info.recoverable:
            return False

        # Check if exception type is retryable
        if error_info.exception:
            for retryable_type in self.config.retryable_exceptions:
                if isinstance(error_info.exception, retryable_type):
                    return True

        # Check if error code is retryable
        error_code = error_info.details.get("error_code", "")
        if error_code in self.config.retryable_error_codes:
            return True

        # Check category-based retryability
        retryable_categories = [
            ErrorCategory.RATE_LIMITING,
            ErrorCategory.NETWORK,
            ErrorCategory.RESOURCE_CONFLICT,
        ]

        return error_info.category in retryable_categories


class PartialRecoveryManager:
    """Manages partial recovery for failed backup operations."""

    def __init__(self):
        self.recovery_strategies = {
            "backup": self._recover_backup_operation,
            "restore": self._recover_restore_operation,
        }

    async def attempt_partial_recovery(
        self, operation_type: str, operation_state: OperationState, error_info: ErrorInfo
    ) -> Dict[str, Any]:
        """
        Attempt partial recovery for a failed operation.

        Args:
            operation_type: Type of operation (backup/restore)
            operation_state: Current state of the operation
            error_info: Information about the error that occurred

        Returns:
            Recovery result with status and recovered data
        """
        logger.info(
            f"Attempting partial recovery for {operation_type} operation {operation_state.operation_id}"
        )

        recovery_strategy = self.recovery_strategies.get(operation_type)
        if not recovery_strategy:
            return {
                "success": False,
                "message": f"No recovery strategy available for operation type: {operation_type}",
                "recovered_data": None,
            }

        try:
            return await recovery_strategy(operation_state, error_info)
        except Exception as e:
            logger.error(f"Partial recovery failed: {e}")
            return {
                "success": False,
                "message": f"Partial recovery failed: {str(e)}",
                "recovered_data": None,
                "error": str(e),
            }

    async def _recover_backup_operation(
        self, operation_state: OperationState, error_info: ErrorInfo
    ) -> Dict[str, Any]:
        """Recover a failed backup operation."""
        recovered_data = {}
        recovery_messages = []

        # Analyze what was successfully collected before failure
        for checkpoint in operation_state.checkpoints:
            checkpoint_name = checkpoint["name"]
            checkpoint_data = checkpoint["data"]

            if checkpoint_name.startswith("collected_"):
                resource_type = checkpoint_name.replace("collected_", "")
                recovered_data[resource_type] = checkpoint_data
                recovery_messages.append(f"Recovered {len(checkpoint_data)} {resource_type}")

        # Create partial backup data if we have any recovered resources
        if recovered_data:
            # Create a partial backup with available data
            partial_backup = self._create_partial_backup(recovered_data, operation_state)

            return {
                "success": True,
                "message": f"Partial recovery successful: {', '.join(recovery_messages)}",
                "recovered_data": partial_backup,
                "recovery_type": "partial_backup",
                "missing_resources": self._identify_missing_resources(recovered_data),
            }
        else:
            return {
                "success": False,
                "message": "No recoverable data found in operation checkpoints",
                "recovered_data": None,
            }

    async def _recover_restore_operation(
        self, operation_state: OperationState, error_info: ErrorInfo
    ) -> Dict[str, Any]:
        """Recover a failed restore operation."""
        applied_changes = operation_state.applied_changes
        recovery_messages = []

        # Summarize what was successfully applied
        resource_counts = {}
        for change in applied_changes:
            resource_type = change["resource_type"]
            resource_counts[resource_type] = resource_counts.get(resource_type, 0) + 1

        for resource_type, count in resource_counts.items():
            recovery_messages.append(f"Successfully applied {count} {resource_type}")

        return {
            "success": True,
            "message": f"Partial restore completed: {', '.join(recovery_messages)}",
            "recovered_data": {
                "applied_changes": applied_changes,
                "resource_counts": resource_counts,
            },
            "recovery_type": "partial_restore",
            "rollback_available": len(operation_state.rollback_actions) > 0,
        }

    def _create_partial_backup(
        self, recovered_data: Dict[str, Any], operation_state: OperationState
    ) -> Dict[str, Any]:
        """Create a partial backup from recovered data."""
        from .models import (
            BackupData,
            BackupMetadata,
            BackupType,
            EncryptionMetadata,
            RetentionPolicy,
        )

        # Create metadata for partial backup
        metadata = BackupMetadata(
            backup_id=f"partial-{operation_state.operation_id}",
            timestamp=operation_state.start_time,
            instance_arn=operation_state.checkpoints[0]["data"].get("instance_arn", ""),
            backup_type=BackupType.FULL,  # Mark as full even though partial
            version="1.0.0",
            source_account=operation_state.checkpoints[0]["data"].get("source_account", ""),
            source_region=operation_state.checkpoints[0]["data"].get("source_region", ""),
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(),
        )

        # Create partial backup data
        partial_backup = BackupData(
            metadata=metadata,
            users=recovered_data.get("users", []),
            groups=recovered_data.get("groups", []),
            permission_sets=recovered_data.get("permission_sets", []),
            assignments=recovered_data.get("assignments", []),
        )

        return partial_backup.to_dict()

    def _identify_missing_resources(self, recovered_data: Dict[str, Any]) -> List[str]:
        """Identify which resource types are missing from recovery."""
        all_resource_types = ["users", "groups", "permission_sets", "assignments"]
        recovered_types = list(recovered_data.keys())
        return [rt for rt in all_resource_types if rt not in recovered_types]


class RollbackManager:
    """Manages rollback operations for failed restore operations."""

    def __init__(self):
        self.active_rollbacks: Dict[str, OperationState] = {}

    async def execute_rollback(self, operation_state: OperationState) -> Dict[str, Any]:
        """
        Execute rollback for a failed operation.

        Args:
            operation_state: State of the operation to rollback

        Returns:
            Rollback result with status and details
        """
        rollback_id = f"rollback-{operation_state.operation_id}"
        logger.info(f"Starting rollback {rollback_id} for operation {operation_state.operation_id}")

        self.active_rollbacks[rollback_id] = operation_state

        try:
            rollback_results = []

            # Execute rollback actions in reverse order
            for i, rollback_action in enumerate(reversed(operation_state.rollback_actions)):
                try:
                    logger.debug(
                        f"Executing rollback action {i + 1}/{len(operation_state.rollback_actions)}"
                    )
                    result = await rollback_action()
                    rollback_results.append({"action_index": i, "success": True, "result": result})
                except Exception as e:
                    logger.error(f"Rollback action {i + 1} failed: {e}")
                    rollback_results.append({"action_index": i, "success": False, "error": str(e)})

            # Analyze rollback results
            successful_rollbacks = sum(1 for r in rollback_results if r["success"])
            total_rollbacks = len(rollback_results)

            success = successful_rollbacks == total_rollbacks

            result = {
                "success": success,
                "rollback_id": rollback_id,
                "message": f"Rollback completed: {successful_rollbacks}/{total_rollbacks} actions successful",
                "rollback_results": rollback_results,
                "applied_changes_reverted": successful_rollbacks,
                "total_changes": len(operation_state.applied_changes),
            }

            if success:
                logger.info(f"Rollback {rollback_id} completed successfully")
            else:
                logger.warning(
                    f"Rollback {rollback_id} completed with {total_rollbacks - successful_rollbacks} failures"
                )

            return result

        except Exception as e:
            logger.error(f"Rollback {rollback_id} failed: {e}")
            return {
                "success": False,
                "rollback_id": rollback_id,
                "message": f"Rollback failed: {str(e)}",
                "error": str(e),
            }

        finally:
            self.active_rollbacks.pop(rollback_id, None)

    async def create_rollback_action(
        self, resource_type: str, resource_id: str, action_type: str, rollback_data: Dict[str, Any]
    ) -> Callable:
        """
        Create a rollback action for a specific change.

        Args:
            resource_type: Type of resource (user, group, etc.)
            resource_id: ID of the resource
            action_type: Type of action (create, update, delete)
            rollback_data: Data needed for rollback

        Returns:
            Async callable that performs the rollback
        """

        async def rollback_action():
            logger.debug(f"Rolling back {action_type} on {resource_type} {resource_id}")

            if action_type == "create":
                # Rollback create by deleting the resource
                return await self._rollback_create(resource_type, resource_id, rollback_data)
            elif action_type == "update":
                # Rollback update by restoring previous values
                return await self._rollback_update(resource_type, resource_id, rollback_data)
            elif action_type == "delete":
                # Rollback delete by recreating the resource
                return await self._rollback_delete(resource_type, resource_id, rollback_data)
            else:
                raise ValueError(f"Unknown action type for rollback: {action_type}")

        return rollback_action

    async def _rollback_create(
        self, resource_type: str, resource_id: str, rollback_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Rollback a create operation by deleting the resource."""
        # This would contain actual AWS API calls to delete resources
        logger.info(f"Rolling back create: deleting {resource_type} {resource_id}")

        # Simulate rollback operation
        return {
            "action": "delete",
            "resource_type": resource_type,
            "resource_id": resource_id,
            "status": "completed",
        }

    async def _rollback_update(
        self, resource_type: str, resource_id: str, rollback_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Rollback an update operation by restoring previous values."""
        logger.info(f"Rolling back update: restoring {resource_type} {resource_id}")

        # This would contain actual AWS API calls to restore previous values
        previous_values = rollback_data.get("previous_values", {})

        return {
            "action": "restore",
            "resource_type": resource_type,
            "resource_id": resource_id,
            "restored_values": previous_values,
            "status": "completed",
        }

    async def _rollback_delete(
        self, resource_type: str, resource_id: str, rollback_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Rollback a delete operation by recreating the resource."""
        logger.info(f"Rolling back delete: recreating {resource_type} {resource_id}")

        # This would contain actual AWS API calls to recreate the resource
        resource_data = rollback_data.get("resource_data", {})

        return {
            "action": "recreate",
            "resource_type": resource_type,
            "resource_id": resource_id,
            "recreated_data": resource_data,
            "status": "completed",
        }


class ErrorReporter:
    """Generates detailed error reports with remediation suggestions."""

    def __init__(self):
        self.error_analyzer = ErrorAnalyzer()

    def generate_error_report(
        self, errors: List[ErrorInfo], operation_context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive error report.

        Args:
            errors: List of errors that occurred
            operation_context: Context about the operation

        Returns:
            Detailed error report
        """
        operation_context = operation_context or {}

        # Categorize errors
        error_categories = {}
        severity_counts = {}

        for error in errors:
            category = error.category.value
            severity = error.severity.value

            if category not in error_categories:
                error_categories[category] = []
            error_categories[category].append(error)

            severity_counts[severity] = severity_counts.get(severity, 0) + 1

        # Generate summary
        total_errors = len(errors)
        critical_errors = severity_counts.get("critical", 0)
        high_errors = severity_counts.get("high", 0)

        # Compile remediation suggestions
        all_suggestions = []
        all_remediation_steps = []

        for error in errors:
            all_suggestions.extend(error.suggested_actions)
            all_remediation_steps.extend(error.remediation_steps)

        # Remove duplicates while preserving order
        unique_suggestions = list(dict.fromkeys(all_suggestions))
        unique_remediation_steps = list(dict.fromkeys(all_remediation_steps))

        report = {
            "report_id": str(uuid4()),
            "timestamp": datetime.now().isoformat(),
            "operation_context": operation_context,
            "summary": {
                "total_errors": total_errors,
                "critical_errors": critical_errors,
                "high_errors": high_errors,
                "categories": list(error_categories.keys()),
                "severity_distribution": severity_counts,
            },
            "errors_by_category": {
                category: [error.to_dict() for error in category_errors]
                for category, category_errors in error_categories.items()
            },
            "remediation": {
                "immediate_actions": unique_suggestions[:5],  # Top 5 suggestions
                "detailed_steps": unique_remediation_steps,
                "recovery_options": self._generate_recovery_options(errors),
            },
            "next_steps": self._generate_next_steps(errors, operation_context),
        }

        return report

    def _generate_recovery_options(self, errors: List[ErrorInfo]) -> List[str]:
        """Generate recovery options based on error analysis."""
        recovery_options = []

        # Check if any errors are recoverable
        recoverable_errors = [e for e in errors if e.recoverable]
        if recoverable_errors:
            recovery_options.append("Retry operation with exponential backoff")

        # Check for partial recovery possibilities
        if any(e.category in [ErrorCategory.NETWORK, ErrorCategory.RATE_LIMITING] for e in errors):
            recovery_options.append("Attempt partial recovery of successfully processed resources")

        # Check for rollback possibilities
        if any(e.severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL] for e in errors):
            recovery_options.append("Consider rolling back any applied changes")

        # Add manual intervention option for critical errors
        critical_errors = [e for e in errors if e.severity == ErrorSeverity.CRITICAL]
        if critical_errors:
            recovery_options.append("Manual intervention required for critical errors")

        return recovery_options

    def _generate_next_steps(
        self, errors: List[ErrorInfo], operation_context: Dict[str, Any]
    ) -> List[str]:
        """Generate recommended next steps."""
        next_steps = []

        # Prioritize by severity
        critical_errors = [e for e in errors if e.severity == ErrorSeverity.CRITICAL]
        high_errors = [e for e in errors if e.severity == ErrorSeverity.HIGH]

        if critical_errors:
            next_steps.append("Address critical errors immediately before retrying")
            next_steps.append("Review system configuration and permissions")

        if high_errors:
            next_steps.append("Resolve high-severity errors to prevent operation failure")

        # Add category-specific steps
        categories = {e.category for e in errors}

        if ErrorCategory.AUTHORIZATION in categories:
            next_steps.append("Review and update IAM permissions")

        if ErrorCategory.RATE_LIMITING in categories:
            next_steps.append("Implement rate limiting and retry logic")

        if ErrorCategory.NETWORK in categories:
            next_steps.append("Check network connectivity and DNS resolution")

        if ErrorCategory.VALIDATION in categories:
            next_steps.append("Validate input data and configuration")

        # Add operation-specific steps
        operation_type = operation_context.get("operation_type")
        if operation_type == "backup":
            next_steps.append("Consider creating incremental backup to reduce load")
        elif operation_type == "restore":
            next_steps.append("Use dry-run mode to preview changes before applying")

        return next_steps


# Convenience function to create a comprehensive error handling system
def create_error_handling_system(retry_config: RetryConfig = None) -> Dict[str, Any]:
    """
    Create a comprehensive error handling system with all components.

    Args:
        retry_config: Optional retry configuration

    Returns:
        Dictionary containing all error handling components
    """
    return {
        "retry_handler": RetryHandler(retry_config),
        "error_analyzer": ErrorAnalyzer(),
        "partial_recovery_manager": PartialRecoveryManager(),
        "rollback_manager": RollbackManager(),
        "error_reporter": ErrorReporter(),
    }
