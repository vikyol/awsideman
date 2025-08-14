"""Comprehensive error handling system for AWS Identity Center status monitoring."""

import asyncio
import logging
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type

from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError


class ErrorSeverity(str, Enum):
    """Error severity levels for categorizing errors."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(str, Enum):
    """Categories of errors for better organization and handling."""

    CONNECTION = "connection"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    TIMEOUT = "timeout"
    VALIDATION = "validation"
    RESOURCE_NOT_FOUND = "resource_not_found"
    SERVICE_ERROR = "service_error"
    CONFIGURATION = "configuration"
    INTERNAL = "internal"


@dataclass
class ErrorContext:
    """Context information for errors to aid in debugging and resolution."""

    component: str
    operation: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    request_id: Optional[str] = None
    user_id: Optional[str] = None
    resource_id: Optional[str] = None
    additional_context: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Ensure additional_context is properly initialized."""
        if self.additional_context is None:
            self.additional_context = {}


@dataclass
class RemediationStep:
    """A single remediation step with description and optional automation."""

    description: str
    action_type: str  # 'manual', 'automatic', 'configuration'
    command: Optional[str] = None
    documentation_url: Optional[str] = None
    priority: int = 1  # 1 = highest priority


@dataclass
class StatusError:
    """Comprehensive error information with context and remediation guidance."""

    error_id: str
    message: str
    category: ErrorCategory
    severity: ErrorSeverity
    context: ErrorContext
    original_exception: Optional[Exception] = None
    remediation_steps: List[RemediationStep] = field(default_factory=list)
    is_retryable: bool = False
    retry_after_seconds: Optional[int] = None

    def __post_init__(self):
        """Ensure collections are properly initialized."""
        if self.remediation_steps is None:
            self.remediation_steps = []

    def get_error_code(self) -> str:
        """Generate a unique error code for tracking."""
        return f"{self.category.value.upper()}_{self.error_id}"

    def get_user_message(self) -> str:
        """Get a user-friendly error message."""
        base_message = self.message

        if self.remediation_steps:
            primary_step = self.remediation_steps[0]
            base_message += f"\n\nRecommended action: {primary_step.description}"

        if self.is_retryable and self.retry_after_seconds:
            base_message += (
                f"\n\nThis error may be temporary. Retry in {self.retry_after_seconds} seconds."
            )

        return base_message

    def get_technical_details(self) -> Dict[str, Any]:
        """Get technical details for debugging."""
        details = {
            "error_id": self.error_id,
            "error_code": self.get_error_code(),
            "category": self.category.value,
            "severity": self.severity.value,
            "component": self.context.component,
            "operation": self.context.operation,
            "timestamp": self.context.timestamp.isoformat(),
            "is_retryable": self.is_retryable,
        }

        if self.context.request_id:
            details["request_id"] = self.context.request_id

        if self.context.resource_id:
            details["resource_id"] = self.context.resource_id

        if self.original_exception:
            details["exception_type"] = type(self.original_exception).__name__
            details["exception_message"] = str(self.original_exception)

        if self.context.additional_context:
            details["additional_context"] = self.context.additional_context

        return details


class StatusErrorHandler:
    """
    Centralized error handler for status monitoring operations.

    Provides consistent error handling, logging, and user-friendly error messages
    with actionable remediation steps across all status components.
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize the error handler.

        Args:
            logger: Logger instance to use for error logging
        """
        self.logger = logger or logging.getLogger(__name__)
        self._error_mappings: Dict[
            Type[Exception], Callable[[Exception, ErrorContext], StatusError]
        ] = {}
        self._setup_default_mappings()

    def _setup_default_mappings(self) -> None:
        """Set up default error mappings for common AWS exceptions."""
        self._error_mappings.update(
            {
                NoCredentialsError: self._handle_credentials_error,
                EndpointConnectionError: self._handle_connection_error,
                ClientError: self._handle_client_error,
                asyncio.TimeoutError: self._handle_timeout_error,
                ValueError: self._handle_validation_error,
                KeyError: self._handle_key_error,
                Exception: self._handle_generic_error,
            }
        )

    def handle_error(self, exception: Exception, context: ErrorContext) -> StatusError:
        """
        Handle an exception and convert it to a StatusError with remediation guidance.

        Args:
            exception: The exception that occurred
            context: Context information about where the error occurred

        Returns:
            StatusError: Comprehensive error information with remediation steps
        """
        # Find the most specific handler for this exception type
        handler = self._find_error_handler(type(exception))

        try:
            status_error = handler(exception, context)

            # Log the error with appropriate level
            self._log_error(status_error)

            return status_error

        except Exception as handler_error:
            # Fallback if error handler itself fails
            self.logger.error(f"Error handler failed: {str(handler_error)}")
            return self._create_fallback_error(exception, context, handler_error)

    def _find_error_handler(
        self, exception_type: Type[Exception]
    ) -> Callable[[Exception, ErrorContext], StatusError]:
        """Find the most appropriate error handler for an exception type."""
        # Check for exact match first
        if exception_type in self._error_mappings:
            return self._error_mappings[exception_type]

        # Check for parent class matches
        for mapped_type, handler in self._error_mappings.items():
            if issubclass(exception_type, mapped_type):
                return handler

        # Fallback to generic handler
        return self._error_mappings[Exception]

    def _handle_credentials_error(
        self, exception: NoCredentialsError, context: ErrorContext
    ) -> StatusError:
        """Handle AWS credentials errors."""
        return StatusError(
            error_id="CREDS_001",
            message="AWS credentials not found or invalid",
            category=ErrorCategory.AUTHENTICATION,
            severity=ErrorSeverity.CRITICAL,
            context=context,
            original_exception=exception,
            remediation_steps=[
                RemediationStep(
                    description="Configure AWS credentials using 'aws configure' or set environment variables",
                    action_type="manual",
                    command="aws configure",
                    documentation_url="https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html",
                ),
                RemediationStep(
                    description="Verify AWS credentials are valid and not expired",
                    action_type="manual",
                    command="aws sts get-caller-identity",
                ),
                RemediationStep(
                    description="Check if AWS profile is correctly specified",
                    action_type="configuration",
                ),
            ],
            is_retryable=False,
        )

    def _handle_connection_error(
        self, exception: EndpointConnectionError, context: ErrorContext
    ) -> StatusError:
        """Handle AWS connection errors."""
        return StatusError(
            error_id="CONN_001",
            message=f"Cannot connect to AWS Identity Center service: {str(exception)}",
            category=ErrorCategory.CONNECTION,
            severity=ErrorSeverity.HIGH,
            context=context,
            original_exception=exception,
            remediation_steps=[
                RemediationStep(
                    description="Check internet connectivity and DNS resolution",
                    action_type="manual",
                    command="ping aws.amazon.com",
                ),
                RemediationStep(
                    description="Verify AWS region is correctly configured",
                    action_type="configuration",
                ),
                RemediationStep(
                    description="Check if corporate firewall is blocking AWS endpoints",
                    action_type="manual",
                ),
                RemediationStep(
                    description="Try using a different AWS region", action_type="configuration"
                ),
            ],
            is_retryable=True,
            retry_after_seconds=30,
        )

    def _handle_client_error(self, exception: ClientError, context: ErrorContext) -> StatusError:
        """Handle AWS ClientError exceptions."""
        error_code = exception.response.get("Error", {}).get("Code", "Unknown")
        error_message = exception.response.get("Error", {}).get("Message", str(exception))
        request_id = exception.response.get("ResponseMetadata", {}).get("RequestId")

        # Update context with request ID
        context.request_id = request_id

        # Handle specific error codes
        if error_code in ["AccessDenied", "UnauthorizedOperation", "Forbidden"]:
            return self._handle_permission_error(exception, context, error_code, error_message)
        elif error_code in ["ResourceNotFoundException", "NoSuchEntity"]:
            return self._handle_resource_not_found_error(
                exception, context, error_code, error_message
            )
        elif error_code in ["ThrottlingException", "TooManyRequestsException"]:
            return self._handle_throttling_error(exception, context, error_code, error_message)
        elif error_code in ["ServiceUnavailableException", "InternalServerError"]:
            return self._handle_service_error(exception, context, error_code, error_message)
        else:
            return self._handle_generic_client_error(exception, context, error_code, error_message)

    def _handle_permission_error(
        self, exception: ClientError, context: ErrorContext, error_code: str, error_message: str
    ) -> StatusError:
        """Handle permission-related AWS errors."""
        return StatusError(
            error_id="PERM_001",
            message=f"Insufficient permissions for {context.operation}: {error_message}",
            category=ErrorCategory.AUTHORIZATION,
            severity=ErrorSeverity.HIGH,
            context=context,
            original_exception=exception,
            remediation_steps=[
                RemediationStep(
                    description="Verify IAM user/role has required Identity Center permissions",
                    action_type="manual",
                    documentation_url="https://docs.aws.amazon.com/singlesignon/latest/userguide/iam-auth-access.html",
                ),
                RemediationStep(
                    description="Check if Identity Center is enabled in this AWS region",
                    action_type="manual",
                ),
                RemediationStep(
                    description="Ensure the IAM policy includes required actions for Identity Center",
                    action_type="configuration",
                ),
                RemediationStep(
                    description="Contact AWS administrator to grant necessary permissions",
                    action_type="manual",
                ),
            ],
            is_retryable=False,
        )

    def _handle_resource_not_found_error(
        self, exception: ClientError, context: ErrorContext, error_code: str, error_message: str
    ) -> StatusError:
        """Handle resource not found errors."""
        return StatusError(
            error_id="RES_001",
            message=f"Resource not found in {context.operation}: {error_message}",
            category=ErrorCategory.RESOURCE_NOT_FOUND,
            severity=ErrorSeverity.MEDIUM,
            context=context,
            original_exception=exception,
            remediation_steps=[
                RemediationStep(
                    description="Verify the resource ID or name is correct", action_type="manual"
                ),
                RemediationStep(
                    description="Check if the resource exists in the correct AWS region",
                    action_type="manual",
                ),
                RemediationStep(
                    description="Ensure Identity Center instance is properly configured",
                    action_type="configuration",
                ),
            ],
            is_retryable=False,
        )

    def _handle_throttling_error(
        self, exception: ClientError, context: ErrorContext, error_code: str, error_message: str
    ) -> StatusError:
        """Handle API throttling errors."""
        return StatusError(
            error_id="THROT_001",
            message=f"API request throttled for {context.operation}: {error_message}",
            category=ErrorCategory.SERVICE_ERROR,
            severity=ErrorSeverity.MEDIUM,
            context=context,
            original_exception=exception,
            remediation_steps=[
                RemediationStep(
                    description="Wait before retrying the operation", action_type="automatic"
                ),
                RemediationStep(
                    description="Reduce the frequency of API calls", action_type="configuration"
                ),
                RemediationStep(
                    description="Implement exponential backoff for retries",
                    action_type="configuration",
                ),
            ],
            is_retryable=True,
            retry_after_seconds=60,
        )

    def _handle_service_error(
        self, exception: ClientError, context: ErrorContext, error_code: str, error_message: str
    ) -> StatusError:
        """Handle AWS service errors."""
        return StatusError(
            error_id="SVC_001",
            message=f"AWS service error in {context.operation}: {error_message}",
            category=ErrorCategory.SERVICE_ERROR,
            severity=ErrorSeverity.HIGH,
            context=context,
            original_exception=exception,
            remediation_steps=[
                RemediationStep(
                    description="Check AWS service health dashboard",
                    action_type="manual",
                    documentation_url="https://status.aws.amazon.com/",
                ),
                RemediationStep(
                    description="Retry the operation after a brief delay", action_type="automatic"
                ),
                RemediationStep(
                    description="Contact AWS support if the issue persists", action_type="manual"
                ),
            ],
            is_retryable=True,
            retry_after_seconds=120,
        )

    def _handle_generic_client_error(
        self, exception: ClientError, context: ErrorContext, error_code: str, error_message: str
    ) -> StatusError:
        """Handle generic AWS client errors."""
        return StatusError(
            error_id="AWS_001",
            message=f"AWS API error in {context.operation}: {error_message}",
            category=ErrorCategory.SERVICE_ERROR,
            severity=ErrorSeverity.MEDIUM,
            context=context,
            original_exception=exception,
            remediation_steps=[
                RemediationStep(
                    description="Review the error details and check AWS documentation",
                    action_type="manual",
                    documentation_url="https://docs.aws.amazon.com/singlesignon/",
                ),
                RemediationStep(
                    description="Verify the request parameters are correct", action_type="manual"
                ),
                RemediationStep(
                    description="Check AWS CloudTrail logs for more details", action_type="manual"
                ),
            ],
            is_retryable=True,
            retry_after_seconds=30,
        )

    def _handle_timeout_error(
        self, exception: asyncio.TimeoutError, context: ErrorContext
    ) -> StatusError:
        """Handle timeout errors."""
        return StatusError(
            error_id="TIME_001",
            message=f"Operation timed out in {context.operation}",
            category=ErrorCategory.TIMEOUT,
            severity=ErrorSeverity.MEDIUM,
            context=context,
            original_exception=exception,
            remediation_steps=[
                RemediationStep(
                    description="Increase the timeout value for this operation",
                    action_type="configuration",
                ),
                RemediationStep(
                    description="Check network connectivity and latency", action_type="manual"
                ),
                RemediationStep(
                    description="Retry the operation with a longer timeout", action_type="automatic"
                ),
                RemediationStep(
                    description="Consider breaking large operations into smaller chunks",
                    action_type="configuration",
                ),
            ],
            is_retryable=True,
            retry_after_seconds=60,
        )

    def _handle_validation_error(self, exception: ValueError, context: ErrorContext) -> StatusError:
        """Handle validation errors."""
        return StatusError(
            error_id="VAL_001",
            message=f"Validation error in {context.operation}: {str(exception)}",
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.MEDIUM,
            context=context,
            original_exception=exception,
            remediation_steps=[
                RemediationStep(
                    description="Check input parameters for correct format and values",
                    action_type="manual",
                ),
                RemediationStep(
                    description="Verify configuration settings are valid",
                    action_type="configuration",
                ),
                RemediationStep(
                    description="Review the operation documentation for parameter requirements",
                    action_type="manual",
                ),
            ],
            is_retryable=False,
        )

    def _handle_key_error(self, exception: KeyError, context: ErrorContext) -> StatusError:
        """Handle key errors (missing configuration or data)."""
        return StatusError(
            error_id="KEY_001",
            message=f"Missing required data or configuration in {context.operation}: {str(exception)}",
            category=ErrorCategory.CONFIGURATION,
            severity=ErrorSeverity.MEDIUM,
            context=context,
            original_exception=exception,
            remediation_steps=[
                RemediationStep(
                    description="Check configuration file for missing required settings",
                    action_type="configuration",
                ),
                RemediationStep(
                    description="Verify all required environment variables are set",
                    action_type="configuration",
                ),
                RemediationStep(
                    description="Review the operation requirements and provide missing data",
                    action_type="manual",
                ),
            ],
            is_retryable=False,
        )

    def _handle_generic_error(self, exception: Exception, context: ErrorContext) -> StatusError:
        """Handle generic exceptions."""
        return StatusError(
            error_id="GEN_001",
            message=f"Unexpected error in {context.operation}: {str(exception)}",
            category=ErrorCategory.INTERNAL,
            severity=ErrorSeverity.HIGH,
            context=context,
            original_exception=exception,
            remediation_steps=[
                RemediationStep(
                    description="Check the application logs for more details", action_type="manual"
                ),
                RemediationStep(description="Retry the operation", action_type="automatic"),
                RemediationStep(
                    description="Report this issue if it persists", action_type="manual"
                ),
            ],
            is_retryable=True,
            retry_after_seconds=30,
        )

    def _create_fallback_error(
        self, original_exception: Exception, context: ErrorContext, handler_error: Exception
    ) -> StatusError:
        """Create a fallback error when the error handler itself fails."""
        return StatusError(
            error_id="FALL_001",
            message=f"Error handler failed for {context.operation}. Original error: {str(original_exception)}",
            category=ErrorCategory.INTERNAL,
            severity=ErrorSeverity.CRITICAL,
            context=context,
            original_exception=original_exception,
            remediation_steps=[
                RemediationStep(
                    description="Check application logs for error handler failure details",
                    action_type="manual",
                ),
                RemediationStep(
                    description="Report this critical error to system administrators",
                    action_type="manual",
                ),
            ],
            is_retryable=False,
        )

    def _log_error(self, status_error: StatusError) -> None:
        """Log the error with appropriate level and context."""
        log_data = {
            "error_code": status_error.get_error_code(),
            "component": status_error.context.component,
            "operation": status_error.context.operation,
            "category": status_error.category.value,
            "severity": status_error.severity.value,
            "is_retryable": status_error.is_retryable,
        }

        if status_error.context.request_id:
            log_data["request_id"] = status_error.context.request_id

        if status_error.context.resource_id:
            log_data["resource_id"] = status_error.context.resource_id

        # Log with appropriate level based on severity
        if status_error.severity == ErrorSeverity.CRITICAL:
            self.logger.error(f"CRITICAL ERROR: {status_error.message}", extra=log_data)
            if status_error.original_exception:
                self.logger.error(f"Exception details: {traceback.format_exc()}")
        elif status_error.severity == ErrorSeverity.HIGH:
            self.logger.error(f"HIGH SEVERITY: {status_error.message}", extra=log_data)
        elif status_error.severity == ErrorSeverity.MEDIUM:
            self.logger.warning(f"MEDIUM SEVERITY: {status_error.message}", extra=log_data)
        else:
            self.logger.info(f"LOW SEVERITY: {status_error.message}", extra=log_data)

    def register_error_handler(
        self,
        exception_type: Type[Exception],
        handler: Callable[[Exception, ErrorContext], StatusError],
    ) -> None:
        """
        Register a custom error handler for a specific exception type.

        Args:
            exception_type: Exception type to handle
            handler: Handler function that converts exception to StatusError
        """
        self._error_mappings[exception_type] = handler
        self.logger.debug(f"Registered custom error handler for {exception_type.__name__}")


# Global error handler instance
_global_error_handler: Optional[StatusErrorHandler] = None


def get_error_handler() -> StatusErrorHandler:
    """Get the global error handler instance."""
    global _global_error_handler
    if _global_error_handler is None:
        _global_error_handler = StatusErrorHandler()
    return _global_error_handler


def handle_status_error(
    exception: Exception, component: str, operation: str, **context_kwargs
) -> StatusError:
    """
    Convenience function to handle errors with minimal setup.

    Args:
        exception: The exception that occurred
        component: Name of the component where error occurred
        operation: Name of the operation that failed
        **context_kwargs: Additional context information

    Returns:
        StatusError: Comprehensive error information
    """
    context = ErrorContext(
        component=component, operation=operation, additional_context=context_kwargs
    )

    return get_error_handler().handle_error(exception, context)


# Legacy compatibility functions for existing commands
def handle_aws_error(exception: Exception, operation: str) -> None:
    """
    Legacy compatibility function for handling AWS errors.

    This function provides backward compatibility for existing commands
    that expect the old error handling interface.

    Args:
        exception: The AWS exception that occurred
        operation: Name of the operation that failed
    """
    import logging

    from rich.console import Console

    console = Console()
    logger = logging.getLogger(__name__)

    # Handle the error using the comprehensive system
    context = ErrorContext(component="awsideman", operation=operation)

    status_error = get_error_handler().handle_error(exception, context)

    # Display user-friendly error message
    console.print(f"[red]{status_error.get_user_message()}[/red]")

    # Log technical details
    logger.error(f"AWS Error in {operation}: {status_error.get_technical_details()}")


def handle_network_error(exception: Exception, operation: str = "NetworkOperation") -> None:
    """
    Legacy compatibility function for handling network errors.

    Args:
        exception: The network exception that occurred
        operation: Name of the operation that failed
    """
    import logging

    from rich.console import Console

    console = Console()
    logger = logging.getLogger(__name__)

    # Validate that exception is actually an exception
    if not isinstance(exception, Exception):
        logger.error(
            f"Invalid exception type passed to handle_network_error: {type(exception)} = {exception}"
        )
        console.print("[red]Network Error: Invalid error type passed to error handler[/red]")
        return

    context = ErrorContext(component="awsideman", operation=operation)

    status_error = get_error_handler().handle_error(exception, context)

    # Display user-friendly error message
    console.print(f"[red]Network Error: {status_error.get_user_message()}[/red]")

    # Log technical details
    logger.error(f"Network Error in {operation}: {status_error.get_technical_details()}")


def with_retry(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """
    Decorator for retrying operations with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff: Backoff multiplier for delay

    Returns:
        Decorator function
    """
    import functools
    import logging
    import time

    from botocore.exceptions import ClientError

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger = logging.getLogger(__name__)
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except ClientError as e:
                    last_exception = e
                    error_code = e.response.get("Error", {}).get("Code", "")

                    # Don't retry certain error types
                    non_retryable_errors = [
                        "AccessDenied",
                        "UnauthorizedOperation",
                        "Forbidden",
                        "ResourceNotFoundException",
                        "NoSuchEntity",
                        "ValidationException",
                        "InvalidParameterValue",
                    ]

                    if error_code in non_retryable_errors:
                        logger.debug(f"Non-retryable error {error_code}, not retrying")
                        break

                    if attempt < max_retries:
                        wait_time = delay * (backoff**attempt)
                        logger.debug(
                            f"Attempt {attempt + 1} failed with {error_code}, retrying in {wait_time}s"
                        )
                        time.sleep(wait_time)
                    else:
                        logger.debug(f"Max retries ({max_retries}) exceeded")
                        break

                except Exception as e:
                    last_exception = e
                    # Don't retry non-AWS errors
                    logger.debug(f"Non-AWS error occurred: {type(e).__name__}, not retrying")
                    break

            # If we get here, all retries failed
            if last_exception:
                raise last_exception

        return wrapper

    return decorator


def check_network_connectivity(region: str) -> None:
    """
    Check network connectivity to AWS services in the specified region.

    This is a placeholder function for backward compatibility.
    In a full implementation, this would test connectivity to AWS endpoints.

    Args:
        region: AWS region to check connectivity for
    """
    # For now, this is a no-op function for compatibility
    # In a full implementation, you might want to:
    # 1. Test DNS resolution for AWS endpoints
    # 2. Check HTTP connectivity to AWS services
    # 3. Validate SSL/TLS connectivity
    # 4. Test specific service endpoints
    pass
