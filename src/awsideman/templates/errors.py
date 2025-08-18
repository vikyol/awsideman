"""Error handling and user experience utilities for template operations."""

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class TemplateErrorType(Enum):
    """Types of template errors."""

    VALIDATION_ERROR = "validation_error"
    PARSING_ERROR = "parsing_error"
    EXECUTION_ERROR = "execution_error"
    PERMISSION_ERROR = "permission_error"
    NETWORK_ERROR = "network_error"
    CONFIGURATION_ERROR = "configuration_error"
    STORAGE_ERROR = "storage_error"


@dataclass
class TemplateError:
    """Structured template error with recovery guidance."""

    error_type: TemplateErrorType
    message: str
    details: Optional[str] = None
    recovery_suggestion: Optional[str] = None
    error_code: Optional[str] = None
    timestamp: Optional[float] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for serialization."""
        return {
            "error_type": self.error_type.value,
            "message": self.message,
            "details": self.details,
            "recovery_suggestion": self.recovery_suggestion,
            "error_code": self.error_code,
            "timestamp": self.timestamp,
        }


class TemplateErrorHandler:
    """Handles template errors with structured reporting and recovery guidance."""

    # Error message templates
    ERROR_MESSAGES = {
        TemplateErrorType.VALIDATION_ERROR: {
            "missing_required_field": "Required field '{field}' is missing from {section}",
            "invalid_entity_format": "Invalid entity format '{entity}'. Expected format: 'user:username' or 'group:groupname'",
            "invalid_permission_set": "Permission set '{permission_set}' not found in AWS Identity Center",
            "invalid_account_id": "Invalid account ID '{account_id}'. Must be a 12-digit number",
            "invalid_tag_format": "Invalid tag format '{tag}'. Expected format: 'key=value'",
            "empty_assignments": "Template must contain at least one assignment",
            "duplicate_entity": "Duplicate entity '{entity}' found in assignment",
            "duplicate_permission_set": "Duplicate permission set '{permission_set}' found in assignment",
        },
        TemplateErrorType.PARSING_ERROR: {
            "invalid_yaml": "Invalid YAML format: {details}",
            "invalid_json": "Invalid JSON format: {details}",
            "unsupported_format": "Unsupported file format '{format}'. Supported formats: yaml, json",
            "file_not_found": "Template file '{file_path}' not found",
            "file_not_readable": "Template file '{file_path}' is not readable",
            "file_empty": "Template file '{file_path}' is empty",
        },
        TemplateErrorType.EXECUTION_ERROR: {
            "assignment_failed": "Failed to create assignment for {entity} in account {account_id}",
            "permission_denied": "Permission denied for operation: {operation}",
            "rate_limited": "AWS API rate limit exceeded. Please wait and retry",
            "service_unavailable": "AWS service temporarily unavailable",
            "invalid_parameters": "Invalid parameters for AWS API call: {details}",
            "rollback_failed": "Failed to rollback operation {operation_id}",
        },
        TemplateErrorType.PERMISSION_ERROR: {
            "insufficient_permissions": "Insufficient permissions to perform operation: {operation}",
            "cross_account_access": "Cannot access account {account_id} with current credentials",
            "sso_instance_access": "Cannot access SSO instance {instance_arn}",
            "identity_store_access": "Cannot access identity store {identity_store_id}",
        },
        TemplateErrorType.NETWORK_ERROR: {
            "connection_timeout": "Connection timeout while connecting to AWS",
            "request_timeout": "Request timeout while calling AWS API",
            "dns_resolution": "DNS resolution failed for AWS endpoint",
            "ssl_error": "SSL/TLS error while connecting to AWS",
        },
        TemplateErrorType.CONFIGURATION_ERROR: {
            "missing_config": "Required configuration '{config_key}' is missing",
            "invalid_config_value": "Invalid value '{value}' for configuration '{config_key}'",
            "config_file_corrupt": "Configuration file is corrupt or unreadable",
            "template_dir_not_found": "Template directory '{dir_path}' not found or not accessible",
        },
        TemplateErrorType.STORAGE_ERROR: {
            "file_write_failed": "Failed to write template file to '{file_path}'",
            "file_delete_failed": "Failed to delete template file '{file_path}'",
            "directory_create_failed": "Failed to create directory '{dir_path}'",
            "file_permission_denied": "Permission denied for file operation on '{file_path}'",
        },
    }

    # Recovery suggestions
    RECOVERY_SUGGESTIONS = {
        TemplateErrorType.VALIDATION_ERROR: {
            "missing_required_field": "Add the missing field '{field}' to the template",
            "invalid_entity_format": "Check entity format and ensure it follows 'type:name' pattern",
            "invalid_permission_set": "Verify permission set exists and check spelling",
            "invalid_account_id": "Verify account ID is correct and contains only digits",
            "invalid_tag_format": "Ensure tags follow 'key=value' format without spaces",
            "empty_assignments": "Add at least one assignment to the template",
            "duplicate_entity": "Remove duplicate entity entries",
            "duplicate_permission_set": "Remove duplicate permission set entries",
        },
        TemplateErrorType.PARSING_ERROR: {
            "invalid_yaml": "Check YAML syntax using a YAML validator",
            "invalid_json": "Check JSON syntax using a JSON validator",
            "unsupported_format": "Convert file to YAML or JSON format",
            "file_not_found": "Verify file path and check file exists",
            "file_not_readable": "Check file permissions and ensure file is not locked",
            "file_empty": "Add content to the template file",
        },
        TemplateErrorType.EXECUTION_ERROR: {
            "assignment_failed": "Check AWS credentials and permissions, verify account exists",
            "permission_denied": "Verify AWS credentials have sufficient permissions",
            "rate_limited": "Wait a few minutes and retry the operation",
            "service_unavailable": "Wait for AWS service to become available and retry",
            "invalid_parameters": "Review and correct the parameters being sent to AWS",
            "rollback_failed": "Manual intervention may be required to clean up resources",
        },
        TemplateErrorType.PERMISSION_ERROR: {
            "insufficient_permissions": "Request additional permissions or use different credentials",
            "cross_account_access": "Verify cross-account role configuration",
            "sso_instance_access": "Check SSO instance configuration and permissions",
            "identity_store_access": "Verify identity store access permissions",
        },
        TemplateErrorType.NETWORK_ERROR: {
            "connection_timeout": "Check network connectivity and firewall settings",
            "request_timeout": "Increase timeout settings or check network stability",
            "dns_resolution": "Check DNS configuration and network connectivity",
            "ssl_error": "Verify SSL/TLS configuration and certificate validity",
        },
        TemplateErrorType.CONFIGURATION_ERROR: {
            "missing_config": "Set the required configuration value",
            "invalid_config_value": "Correct the configuration value to a valid option",
            "config_file_corrupt": "Restore configuration from backup or reset to defaults",
            "template_dir_not_found": "Create the directory or update configuration",
        },
        TemplateErrorType.STORAGE_ERROR: {
            "file_write_failed": "Check disk space and file permissions",
            "file_delete_failed": "Check file permissions and ensure file is not in use",
            "directory_create_failed": "Check parent directory permissions and disk space",
            "file_permission_denied": "Check file ownership and permissions",
        },
    }

    @classmethod
    def create_error(cls, error_type: TemplateErrorType, error_key: str, **kwargs) -> TemplateError:
        """Create a structured error with message and recovery suggestion."""
        message_template = cls.ERROR_MESSAGES[error_type].get(error_key, "Unknown error: {details}")
        recovery_template = cls.RECOVERY_SUGGESTIONS[error_type].get(
            error_key, "Review the error and take appropriate action"
        )

        try:
            message = message_template.format(**kwargs)
            recovery_suggestion = recovery_template.format(**kwargs)
        except KeyError:
            # Fallback if template variables are missing
            message = f"{error_key}: {kwargs.get('details', 'Unknown error')}"
            recovery_suggestion = "Review the error and take appropriate action"

        return TemplateError(
            error_type=error_type,
            message=message,
            details=kwargs.get("details"),
            recovery_suggestion=recovery_suggestion,
            error_code=error_key,
        )

    @classmethod
    def create_validation_error(cls, error_key: str, **kwargs) -> TemplateError:
        """Create a validation error."""
        return cls.create_error(TemplateErrorType.VALIDATION_ERROR, error_key, **kwargs)

    @classmethod
    def create_parsing_error(cls, error_key: str, **kwargs) -> TemplateError:
        """Create a parsing error."""
        return cls.create_error(TemplateErrorType.PARSING_ERROR, error_key, **kwargs)

    @classmethod
    def create_execution_error(cls, error_key: str, **kwargs) -> TemplateError:
        """Create an execution error."""
        return cls.create_error(TemplateErrorType.EXECUTION_ERROR, error_key, **kwargs)

    @classmethod
    def create_permission_error(cls, error_key: str, **kwargs) -> TemplateError:
        """Create a permission error."""
        return cls.create_error(TemplateErrorType.PERMISSION_ERROR, error_key, **kwargs)

    @classmethod
    def create_network_error(cls, error_key: str, **kwargs) -> TemplateError:
        """Create a network error."""
        return cls.create_error(TemplateErrorType.NETWORK_ERROR, error_key, **kwargs)

    @classmethod
    def create_configuration_error(cls, error_key: str, **kwargs) -> TemplateError:
        """Create a configuration error."""
        return cls.create_error(TemplateErrorType.CONFIGURATION_ERROR, error_key, **kwargs)

    @classmethod
    def create_storage_error(cls, error_key: str, **kwargs) -> TemplateError:
        """Create a storage error."""
        return cls.create_error(TemplateErrorType.STORAGE_ERROR, error_key, **kwargs)


class TemplateErrorCollector:
    """Collects and manages multiple template errors."""

    def __init__(self):
        self.errors: List[TemplateError] = []
        self.warnings: List[TemplateError] = []

    def add_error(self, error: TemplateError):
        """Add an error to the collection."""
        self.errors.append(error)

    def add_warning(self, warning: TemplateError):
        """Add a warning to the collection."""
        self.warnings.append(warning)

    def add_validation_error(self, error_key: str, **kwargs):
        """Add a validation error."""
        error = TemplateErrorHandler.create_validation_error(error_key, **kwargs)
        self.add_error(error)

    def add_parsing_error(self, error_key: str, **kwargs):
        """Add a parsing error."""
        error = TemplateErrorHandler.create_parsing_error(error_key, **kwargs)
        self.add_error(error)

    def add_execution_error(self, error_key: str, **kwargs):
        """Add an execution error."""
        error = TemplateErrorHandler.create_execution_error(error_key, **kwargs)
        self.add_error(error)

    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return len(self.errors) > 0

    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return len(self.warnings) > 0

    def get_error_summary(self) -> Dict[str, Any]:
        """Get a summary of all errors and warnings."""
        return {
            "total_errors": len(self.errors),
            "total_warnings": len(self.warnings),
            "errors_by_type": self._group_errors_by_type(self.errors),
            "warnings_by_type": self._group_errors_by_type(self.warnings),
        }

    def _group_errors_by_type(self, error_list: List[TemplateError]) -> Dict[str, int]:
        """Group errors by their type."""
        grouped = {}
        for error in error_list:
            error_type = error.error_type.value
            grouped[error_type] = grouped.get(error_type, 0) + 1
        return grouped

    def clear(self):
        """Clear all errors and warnings."""
        self.errors.clear()
        self.warnings.clear()


class RetryHandler:
    """Handles retry logic for transient failures."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_backoff: bool = True,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_backoff = exponential_backoff

    def should_retry(self, error: TemplateError, attempt: int) -> bool:
        """Determine if an operation should be retried."""
        if attempt >= self.max_retries:
            return False

        # Retry on network errors and rate limiting
        retryable_errors = {TemplateErrorType.NETWORK_ERROR, TemplateErrorType.EXECUTION_ERROR}

        retryable_error_keys = {
            "rate_limited",
            "service_unavailable",
            "connection_timeout",
            "request_timeout",
        }

        return error.error_type in retryable_errors and error.error_code in retryable_error_keys

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for retry attempt."""
        if self.exponential_backoff:
            delay = self.base_delay * (2**attempt)
        else:
            delay = self.base_delay

        return min(delay, self.max_delay)

    def execute_with_retry(self, operation, *args, **kwargs):
        """Execute operation with retry logic."""
        last_error = None

        for attempt in range(self.max_retries + 1):
            try:
                return operation(*args, **kwargs)
            except Exception as e:
                last_error = e

                # Create error object for retry decision
                if "rate" in str(e).lower() or "throttling" in str(e).lower():
                    error = TemplateErrorHandler.create_execution_error("rate_limited")
                elif "timeout" in str(e).lower():
                    error = TemplateErrorHandler.create_network_error("request_timeout")
                else:
                    # Don't retry on non-retryable errors
                    raise

                if not self.should_retry(error, attempt):
                    raise

                if attempt < self.max_retries:
                    delay = self.get_delay(attempt)
                    time.sleep(delay)

        # If we get here, all retries failed
        raise last_error
