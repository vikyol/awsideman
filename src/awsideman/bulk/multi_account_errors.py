"""Multi-account error handling and reporting components.

This module provides comprehensive error handling and reporting specifically
designed for multi-account operations, including name resolution errors,
account filter errors, and detailed error summaries.

Classes:
    MultiAccountErrorType: Enumeration of multi-account error types
    MultiAccountError: Base class for multi-account specific errors
    NameResolutionError: Error for name resolution failures
    AccountFilterError: Error for account filter failures
    MultiAccountOperationError: Error for operation-level failures
    MultiAccountErrorHandler: Centralized error handling and reporting
    MultiAccountErrorSummary: Comprehensive error summary generation
"""

import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from botocore.exceptions import ClientError
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..utils.models import AccountInfo, AccountResult, MultiAccountResults


class MultiAccountErrorType(str, Enum):
    """Enumeration of multi-account error types."""

    NAME_RESOLUTION = "NAME_RESOLUTION"
    ACCOUNT_FILTER = "ACCOUNT_FILTER"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    VALIDATION = "VALIDATION"
    NETWORK = "NETWORK"
    THROTTLING = "THROTTLING"
    SERVICE_ERROR = "SERVICE_ERROR"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"


@dataclass
class MultiAccountError:
    """Base class for multi-account specific errors with detailed context."""

    error_type: MultiAccountErrorType
    message: str
    context: Dict[str, Any] = field(default_factory=dict)
    original_exception: Optional[Exception] = None
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    timestamp: Optional[float] = None

    def __post_init__(self):
        """Set timestamp if not provided."""
        if self.timestamp is None:
            import time

            self.timestamp = time.time()

    def get_display_message(self) -> str:
        """Get a user-friendly display message."""
        if self.account_id and self.account_name:
            return f"[{self.account_name} ({self.account_id})] {self.message}"
        return self.message

    def get_detailed_context(self) -> str:
        """Get detailed context information for debugging."""
        context_parts = []

        if self.account_id:
            context_parts.append(f"Account ID: {self.account_id}")
        if self.account_name:
            context_parts.append(f"Account Name: {self.account_name}")

        for key, value in self.context.items():
            context_parts.append(f"{key}: {value}")

        if self.original_exception:
            context_parts.append(f"Original Error: {str(self.original_exception)}")
            context_parts.append(f"Exception Type: {type(self.original_exception).__name__}")

        return "; ".join(context_parts)

    def is_retryable(self) -> bool:
        """Check if this error type is typically retryable."""
        retryable_types = {
            MultiAccountErrorType.THROTTLING,
            MultiAccountErrorType.NETWORK,
            MultiAccountErrorType.SERVICE_ERROR,
            MultiAccountErrorType.TIMEOUT,
        }
        return self.error_type in retryable_types


@dataclass
class NameResolutionError(MultiAccountError):
    """Specific error for name resolution failures."""

    resource_name: str = ""
    resource_type: str = ""  # 'permission_set', 'principal', 'account'

    def __post_init__(self):
        super().__post_init__()
        if not self.error_type:
            self.error_type = MultiAccountErrorType.NAME_RESOLUTION

        # Add resource context
        if self.resource_name:
            self.context["resource_name"] = self.resource_name
        if self.resource_type:
            self.context["resource_type"] = self.resource_type

    def get_resolution_guidance(self) -> List[str]:
        """Get specific guidance for resolving name resolution errors."""
        guidance = []

        if self.resource_type == "permission_set":
            guidance.extend(
                [
                    "Verify the permission set name is correct and exists in your SSO instance",
                    "Check if you have permissions to list permission sets",
                    "Ensure the permission set is not in a different AWS region",
                    "Try using the permission set ARN directly if known",
                ]
            )
        elif self.resource_type == "principal":
            guidance.extend(
                [
                    "Verify the user or group name is correct and exists in your identity store",
                    "Check if you have permissions to list users/groups",
                    "Ensure the principal is not disabled or deleted",
                    "Try using the principal ID directly if known",
                ]
            )
        elif self.resource_type == "account":
            guidance.extend(
                [
                    "Verify the account name or ID is correct",
                    "Check if you have permissions to list organization accounts",
                    "Ensure the account is still active in your organization",
                    "Try using the account ID directly if known",
                ]
            )
        else:
            guidance.extend(
                [
                    "Verify the resource name is correct and exists",
                    "Check your permissions for the relevant AWS service",
                    "Ensure you're using the correct AWS region",
                ]
            )

        return guidance


@dataclass
class AccountFilterError(MultiAccountError):
    """Specific error for account filter failures."""

    filter_expression: str = ""
    filter_type: str = ""

    def __post_init__(self):
        super().__post_init__()
        if not self.error_type:
            self.error_type = MultiAccountErrorType.ACCOUNT_FILTER

        # Add filter context
        if self.filter_expression:
            self.context["filter_expression"] = self.filter_expression
        if self.filter_type:
            self.context["filter_type"] = self.filter_type

    def get_filter_guidance(self) -> List[str]:
        """Get specific guidance for resolving account filter errors."""
        guidance = []

        if self.filter_type == "wildcard":
            guidance.extend(
                [
                    "Ensure you have permissions to list all organization accounts",
                    "Check if your organization has any accounts",
                    "Verify your AWS Organizations setup is correct",
                ]
            )
        elif self.filter_type == "tag":
            guidance.extend(
                [
                    "Verify the tag key and value are correct",
                    "Check if any accounts actually have the specified tags",
                    "Ensure you have permissions to list account tags",
                    "Tag filters are case-sensitive - check capitalization",
                    "Use format: tag:Key=Value for single tags or tag:Key1=Value1,Key2=Value2 for multiple",
                ]
            )
        else:
            guidance.extend(
                [
                    "Check the filter expression syntax",
                    "Supported formats: '*' for all accounts, 'tag:Key=Value' for tag filtering",
                    "Ensure the filter expression is not empty",
                ]
            )

        return guidance


@dataclass
class MultiAccountOperationError(MultiAccountError):
    """Specific error for multi-account operation failures."""

    operation_type: str = ""  # 'assign', 'revoke'
    permission_set_name: str = ""
    principal_name: str = ""

    def __post_init__(self):
        super().__post_init__()

        # Add operation context
        if self.operation_type:
            self.context["operation_type"] = self.operation_type
        if self.permission_set_name:
            self.context["permission_set_name"] = self.permission_set_name
        if self.principal_name:
            self.context["principal_name"] = self.principal_name


class MultiAccountErrorHandler:
    """Centralized error handling and reporting for multi-account operations."""

    def __init__(self, console: Optional[Console] = None):
        """Initialize the error handler.

        Args:
            console: Rich console for output (creates new one if not provided)
        """
        self.console = console or Console()
        self.error_history: List[MultiAccountError] = []

    def handle_name_resolution_error(
        self, name: str, name_type: str, error: Exception, show_guidance: bool = True
    ) -> NameResolutionError:
        """Handle name resolution errors with detailed error messages.

        Args:
            name: The name that failed to resolve
            name_type: Type of name ('permission_set', 'principal', 'account')
            error: The original exception
            show_guidance: Whether to display resolution guidance

        Returns:
            NameResolutionError with detailed context
        """
        # Determine error type from exception
        error_type = self._classify_error(error)

        # Create detailed error message
        if isinstance(error, ClientError):
            error_code = error.response.get("Error", {}).get("Code", "Unknown")
            aws_message = error.response.get("Error", {}).get("Message", str(error))
            message = f"Failed to resolve {name_type} '{name}': {error_code} - {aws_message}"
        else:
            message = f"Failed to resolve {name_type} '{name}': {str(error)}"

        # Create name resolution error
        name_error = NameResolutionError(
            error_type=error_type,
            message=message,
            resource_name=name,
            resource_type=name_type,
            original_exception=error,
            context={
                "aws_error_code": getattr(error, "response", {}).get("Error", {}).get("Code"),
                "resolution_attempted": True,
            },
        )

        # Add to error history
        self.error_history.append(name_error)

        # Display error with guidance
        if show_guidance:
            self._display_name_resolution_error(name_error)

        return name_error

    def handle_account_filter_error(
        self, filter_expression: str, error: Exception, show_guidance: bool = True
    ) -> AccountFilterError:
        """Handle account filter errors for invalid expressions.

        Args:
            filter_expression: The filter expression that failed
            error: The original exception
            show_guidance: Whether to display resolution guidance

        Returns:
            AccountFilterError with detailed context
        """
        # Determine filter type
        filter_type = (
            "wildcard"
            if filter_expression == "*"
            else "tag" if filter_expression.startswith("tag:") else "unknown"
        )

        # Determine error type from exception
        error_type = self._classify_error(error)

        # Create detailed error message
        if isinstance(error, ClientError):
            error_code = error.response.get("Error", {}).get("Code", "Unknown")
            aws_message = error.response.get("Error", {}).get("Message", str(error))
            message = f"Account filter failed '{filter_expression}': {error_code} - {aws_message}"
        else:
            message = f"Account filter failed '{filter_expression}': {str(error)}"

        # Create account filter error
        filter_error = AccountFilterError(
            error_type=error_type,
            message=message,
            filter_expression=filter_expression,
            filter_type=filter_type,
            original_exception=error,
            context={
                "aws_error_code": getattr(error, "response", {}).get("Error", {}).get("Code"),
                "filter_validation_attempted": True,
            },
        )

        # Add to error history
        self.error_history.append(filter_error)

        # Display error with guidance
        if show_guidance:
            self._display_account_filter_error(filter_error)

        return filter_error

    def handle_account_operation_error(
        self,
        account: AccountInfo,
        operation_type: str,
        permission_set_name: str,
        principal_name: str,
        error: Exception,
        retry_count: int = 0,
    ) -> MultiAccountOperationError:
        """Handle individual account operation errors.

        Args:
            account: Account where the error occurred
            operation_type: Type of operation ('assign' or 'revoke')
            permission_set_name: Permission set name
            principal_name: Principal name
            error: The original exception
            retry_count: Number of retries attempted

        Returns:
            MultiAccountOperationError with detailed context
        """
        # Determine error type from exception
        error_type = self._classify_error(error)

        # Create detailed error message
        if isinstance(error, ClientError):
            error_code = error.response.get("Error", {}).get("Code", "Unknown")
            aws_message = error.response.get("Error", {}).get("Message", str(error))
            message = f"{operation_type.title()} operation failed: {error_code} - {aws_message}"
        else:
            message = f"{operation_type.title()} operation failed: {str(error)}"

        # Create operation error
        operation_error = MultiAccountOperationError(
            error_type=error_type,
            message=message,
            account_id=account.account_id,
            account_name=account.account_name,
            operation_type=operation_type,
            permission_set_name=permission_set_name,
            principal_name=principal_name,
            original_exception=error,
            context={
                "aws_error_code": getattr(error, "response", {}).get("Error", {}).get("Code"),
                "retry_count": retry_count,
                "account_status": account.status,
                "account_tags": account.tags,
            },
        )

        # Add to error history
        self.error_history.append(operation_error)

        return operation_error

    def _classify_error(self, error: Exception) -> MultiAccountErrorType:
        """Classify an exception into a MultiAccountErrorType.

        Args:
            error: Exception to classify

        Returns:
            MultiAccountErrorType enum value
        """
        if isinstance(error, ClientError):
            error_code = error.response.get("Error", {}).get("Code", "")

            # Permission-related errors
            if error_code in [
                "AccessDeniedException",
                "UnauthorizedException",
                "AuthorizationErrorException",
            ]:
                return MultiAccountErrorType.PERMISSION_DENIED

            # Resource not found errors
            elif error_code in [
                "ResourceNotFoundException",
                "AccountNotFoundException",
                "UserNotFoundException",
                "GroupNotFoundException",
            ]:
                return MultiAccountErrorType.RESOURCE_NOT_FOUND

            # Validation errors
            elif error_code in [
                "ValidationException",
                "InvalidParameterException",
                "MissingParameterException",
            ]:
                return MultiAccountErrorType.VALIDATION

            # Throttling errors
            elif error_code in ["ThrottlingException", "TooManyRequestsException", "Throttling"]:
                return MultiAccountErrorType.THROTTLING

            # Service errors
            elif error_code in [
                "ServiceException",
                "InternalServerException",
                "ServiceUnavailableException",
            ]:
                return MultiAccountErrorType.SERVICE_ERROR

            # Timeout errors
            elif error_code in ["RequestTimeoutException", "RequestTimeout"]:
                return MultiAccountErrorType.TIMEOUT

            else:
                return MultiAccountErrorType.UNKNOWN

        # Network-related errors
        elif isinstance(error, (ConnectionError, TimeoutError)):
            return MultiAccountErrorType.NETWORK

        # Validation errors
        elif isinstance(error, ValueError):
            return MultiAccountErrorType.VALIDATION

        else:
            return MultiAccountErrorType.UNKNOWN

    def _display_name_resolution_error(self, error: NameResolutionError):
        """Display name resolution error with guidance."""
        self.console.print("\n[red]❌ Name Resolution Failed[/red]")
        self.console.print(f"[red]{error.get_display_message()}[/red]")

        # Show resolution guidance
        guidance = error.get_resolution_guidance()
        if guidance:
            self.console.print("\n[yellow]💡 Resolution Guidance:[/yellow]")
            for i, tip in enumerate(guidance, 1):
                self.console.print(f"  {i}. {tip}")

        # Show detailed context if available
        context = error.get_detailed_context()
        if context:
            self.console.print(f"\n[dim]Context: {context}[/dim]")

    def _display_account_filter_error(self, error: AccountFilterError):
        """Display account filter error with guidance."""
        self.console.print("\n[red]❌ Account Filter Failed[/red]")
        self.console.print(f"[red]{error.get_display_message()}[/red]")

        # Show filter guidance
        guidance = error.get_filter_guidance()
        if guidance:
            self.console.print("\n[yellow]💡 Filter Guidance:[/yellow]")
            for i, tip in enumerate(guidance, 1):
                self.console.print(f"  {i}. {tip}")

        # Show detailed context if available
        context = error.get_detailed_context()
        if context:
            self.console.print(f"\n[dim]Context: {context}[/dim]")

    def get_error_history(self) -> List[MultiAccountError]:
        """Get the complete error history.

        Returns:
            List of all errors that have been handled
        """
        return self.error_history.copy()

    def clear_error_history(self):
        """Clear the error history."""
        self.error_history.clear()

    def get_error_summary(self) -> Dict[str, Any]:
        """Get a summary of all errors by type.

        Returns:
            Dictionary with error counts by type
        """
        error_counts = {}
        for error_type in MultiAccountErrorType:
            error_counts[error_type.value] = 0

        for error in self.error_history:
            error_counts[error.error_type.value] += 1

        return {
            "total_errors": len(self.error_history),
            "error_counts": error_counts,
            "retryable_errors": sum(1 for error in self.error_history if error.is_retryable()),
            "non_retryable_errors": sum(
                1 for error in self.error_history if not error.is_retryable()
            ),
        }

    def analyze_error_patterns(self) -> Dict[str, Any]:
        """Analyze patterns in the current error history.

        Returns:
            Dictionary with pattern analysis results
        """
        return analyze_error_patterns(self.error_history)

    def get_troubleshooting_guide(self, error_index: int = -1) -> str:
        """Get a comprehensive troubleshooting guide for a specific error.

        Args:
            error_index: Index of error in history (-1 for most recent)

        Returns:
            Formatted troubleshooting guide
        """
        if not self.error_history:
            return "No errors in history to troubleshoot."

        try:
            error = self.error_history[error_index]
            return create_error_troubleshooting_guide(error)
        except IndexError:
            return f"Error index {error_index} not found in history of {len(self.error_history)} errors."

    def display_comprehensive_error_analysis(self):
        """Display a comprehensive analysis of all errors in the history."""
        if not self.error_history:
            self.console.print(
                "[green]✅ No errors to analyze - all operations were successful![/green]"
            )
            return

        # Display basic summary
        summary = self.get_error_summary()
        self.console.print("\n[bold red]📊 Comprehensive Error Analysis[/bold red]")
        self.console.print(f"Total Errors: {summary['total_errors']}")
        self.console.print(
            f"Retryable: {summary['retryable_errors']}, Non-retryable: {summary['non_retryable_errors']}"
        )

        # Display pattern analysis
        patterns = self.analyze_error_patterns()
        if patterns.get("has_patterns"):
            self.console.print("\n[bold yellow]🔍 Pattern Analysis:[/bold yellow]")

            # Show dominant error types
            dominant_types = patterns.get("dominant_error_types", [])
            if dominant_types:
                self.console.print("Dominant Error Types:")
                for error_type in dominant_types:
                    self.console.print(
                        f"  • {error_type['type']}: {error_type['count']} ({error_type['percentage']:.1f}%)"
                    )

            # Show temporal analysis
            temporal = patterns.get("temporal_analysis", {})
            if temporal:
                self.console.print("Temporal Analysis:")
                if temporal.get("has_temporal_clustering"):
                    self.console.print(
                        "  • ⚠️ High error clustering detected (errors within short time span)"
                    )
                self.console.print(
                    f"  • Error rate: {temporal.get('error_rate_per_minute', 0):.1f} errors/minute"
                )

            # Show problematic accounts
            problematic = patterns.get("problematic_accounts", [])
            if problematic:
                self.console.print("Accounts with Multiple Errors:")
                for account in problematic[:5]:  # Show top 5
                    self.console.print(
                        f"  • {account['account_id']}: {account['error_count']} errors"
                    )

        # Show recovery recommendations
        self.console.print("\n[bold cyan]💡 Recovery Recommendations:[/bold cyan]")
        if summary["retryable_errors"] > 0:
            self.console.print(
                f"  • {summary['retryable_errors']} errors are retryable - consider running the operation again"
            )

        if summary["non_retryable_errors"] > 0:
            self.console.print(
                f"  • {summary['non_retryable_errors']} errors require manual intervention"
            )

        # Show most recent error troubleshooting guide
        if self.error_history:
            self.console.print("\n[bold magenta]🔧 Latest Error Troubleshooting:[/bold magenta]")
            latest_guide = self.get_troubleshooting_guide()
            # Display first few lines of the guide
            guide_lines = latest_guide.split("\n")[:10]
            for line in guide_lines:
                self.console.print(f"  {line}")
            if len(latest_guide.split("\n")) > 10:
                self.console.print("  ... (use get_troubleshooting_guide() for full guide)")


class MultiAccountErrorSummary:
    """Comprehensive error summary generation for multi-account operations."""

    def __init__(self, console: Optional[Console] = None):
        """Initialize the error summary generator.

        Args:
            console: Rich console for output (creates new one if not provided)
        """
        self.console = console or Console()

    def generate_error_summary(
        self,
        results: MultiAccountResults,
        error_handler: Optional[MultiAccountErrorHandler] = None,
        show_detailed_errors: bool = True,
        show_recommendations: bool = True,
    ) -> Dict[str, Any]:
        """Generate comprehensive error summary for failed operations.

        Args:
            results: Multi-account operation results
            error_handler: Optional error handler with error history
            show_detailed_errors: Whether to show detailed error information
            show_recommendations: Whether to show recommendations

        Returns:
            Dictionary with comprehensive error summary
        """
        # Analyze failed accounts
        failed_accounts = results.failed_accounts
        if not failed_accounts:
            return {"has_errors": False, "message": "No errors to report"}

        # Categorize errors by type
        error_categories = self._categorize_account_errors(failed_accounts)

        # Generate summary statistics
        summary_stats = {
            "total_failed_accounts": len(failed_accounts),
            "total_accounts": results.total_accounts,
            "failure_rate": results.failure_rate,
            "error_categories": error_categories,
            "most_common_error": self._get_most_common_error(failed_accounts),
            "retryable_failures": self._count_retryable_failures(failed_accounts),
            "permanent_failures": len(failed_accounts)
            - self._count_retryable_failures(failed_accounts),
        }

        # Display error summary
        if show_detailed_errors:
            self._display_error_summary(
                results, summary_stats, error_categories, show_detailed_errors
            )

        # Show recommendations
        if show_recommendations:
            self._display_error_recommendations(error_categories, summary_stats)

        # Include error handler history if available
        if error_handler:
            handler_summary = error_handler.get_error_summary()
            summary_stats["error_handler_summary"] = handler_summary

            # Add pattern analysis from error handler
            pattern_analysis = error_handler.analyze_error_patterns()
            summary_stats["pattern_analysis"] = pattern_analysis

        return {
            "has_errors": True,
            "summary_stats": summary_stats,
            "failed_accounts": [
                {
                    "account_id": account.account_id,
                    "account_name": account.account_name,
                    "error_message": account.error_message,
                    "processing_time": account.processing_time,
                    "retry_count": account.retry_count,
                }
                for account in failed_accounts
            ],
        }

    def _categorize_account_errors(
        self, failed_accounts: List[AccountResult]
    ) -> Dict[str, List[AccountResult]]:
        """Categorize failed accounts by error type.

        Args:
            failed_accounts: List of failed account results

        Returns:
            Dictionary mapping error categories to account lists
        """
        categories = {
            "permission_denied": [],
            "resource_not_found": [],
            "throttling": [],
            "validation": [],
            "network": [],
            "service_error": [],
            "timeout": [],
            "unknown": [],
        }

        for account in failed_accounts:
            error_message = account.error_message or ""
            error_message_lower = error_message.lower()

            # Categorize based on error message content (order matters - more specific first)
            if any(
                keyword in error_message_lower
                for keyword in ["not found", "does not exist", "resourcenotfoundexception"]
            ):
                categories["resource_not_found"].append(account)
            elif any(
                keyword in error_message_lower
                for keyword in ["access denied", "unauthorized", "accessdeniedexception"]
            ) or ("permission" in error_message_lower and "not found" not in error_message_lower):
                categories["permission_denied"].append(account)
            elif any(
                keyword in error_message_lower
                for keyword in ["throttl", "rate limit", "too many requests"]
            ):
                categories["throttling"].append(account)
            elif any(
                keyword in error_message_lower
                for keyword in ["validation", "invalid parameter", "missing parameter"]
            ):
                categories["validation"].append(account)
            elif any(
                keyword in error_message_lower for keyword in ["network", "connection", "timeout"]
            ):
                categories["network"].append(account)
            elif any(
                keyword in error_message_lower for keyword in ["service", "internal", "unavailable"]
            ):
                categories["service_error"].append(account)
            elif "timeout" in error_message_lower:
                categories["timeout"].append(account)
            else:
                categories["unknown"].append(account)

        # Remove empty categories
        return {k: v for k, v in categories.items() if v}

    def _get_most_common_error(self, failed_accounts: List[AccountResult]) -> Dict[str, Any]:
        """Get the most common error type and message.

        Args:
            failed_accounts: List of failed account results

        Returns:
            Dictionary with most common error information
        """
        error_counts = {}

        for account in failed_accounts:
            error_message = account.error_message or "Unknown error"
            # Normalize error message for counting
            normalized_error = self._normalize_error_message(error_message)
            error_counts[normalized_error] = error_counts.get(normalized_error, 0) + 1

        if not error_counts:
            return {"message": "No errors found", "count": 0, "percentage": 0.0}

        most_common_error = max(error_counts.items(), key=lambda x: x[1])

        return {
            "message": most_common_error[0],
            "count": most_common_error[1],
            "percentage": (most_common_error[1] / len(failed_accounts)) * 100,
        }

    def _normalize_error_message(self, error_message: str) -> str:
        """Normalize error message for counting similar errors.

        Args:
            error_message: Raw error message

        Returns:
            Normalized error message
        """
        # Remove account-specific information
        import re

        # Remove account IDs (12-digit numbers)
        normalized = re.sub(r"\b\d{12}\b", "[ACCOUNT_ID]", error_message)

        # Remove ARNs
        normalized = re.sub(r"arn:aws:[^:]+:[^:]*:[^:]*:[^/\s]+", "[ARN]", normalized)

        # Remove UUIDs
        normalized = re.sub(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
            "[UUID]",
            normalized,
        )

        # Remove timestamps
        normalized = re.sub(r"\b\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}", "[TIMESTAMP]", normalized)

        # Normalize AWS error codes by extracting just the error type
        # This groups similar AWS errors together (e.g., all AccessDeniedException errors)
        aws_error_match = re.match(r"^([A-Za-z]+Exception):", normalized)
        if aws_error_match:
            error_type = aws_error_match.group(1)
            # Keep the error type and a generic message
            normalized = f"{error_type}: [DETAILS_REMOVED]"

        return normalized.strip()

    def _count_retryable_failures(self, failed_accounts: List[AccountResult]) -> int:
        """Count the number of retryable failures.

        Args:
            failed_accounts: List of failed account results

        Returns:
            Number of retryable failures
        """
        retryable_count = 0

        for account in failed_accounts:
            error_message = account.error_message or ""
            error_message_lower = error_message.lower()

            # Consider errors retryable if they're related to throttling, network, or service issues
            if any(
                keyword in error_message_lower
                for keyword in [
                    "throttl",
                    "rate limit",
                    "too many requests",
                    "network",
                    "connection",
                    "timeout",
                    "service",
                    "internal",
                    "unavailable",
                ]
            ):
                retryable_count += 1

        return retryable_count

    def _display_error_summary(
        self,
        results: MultiAccountResults,
        summary_stats: Dict[str, Any],
        error_categories: Dict[str, List[AccountResult]],
        show_detailed_errors: bool = True,
    ):
        """Display comprehensive error summary."""
        self.console.print("\n[red]❌ Multi-Account Operation Error Summary[/red]")

        # Create summary panel
        summary_lines = [
            f"[bold]Total Failed Accounts:[/bold] {summary_stats['total_failed_accounts']} of {summary_stats['total_accounts']}",
            f"[bold]Failure Rate:[/bold] {summary_stats['failure_rate']:.1f}%",
            f"[bold]Retryable Failures:[/bold] {summary_stats['retryable_failures']}",
            f"[bold]Permanent Failures:[/bold] {summary_stats['permanent_failures']}",
        ]

        most_common = summary_stats["most_common_error"]
        if most_common["count"] > 0:
            summary_lines.append(
                f"[bold]Most Common Error:[/bold] {most_common['message']} ({most_common['count']} accounts, {most_common['percentage']:.1f}%)"
            )

        summary_panel = Panel(
            "\n".join(summary_lines),
            title="[bold red]Error Summary[/bold red]",
            title_align="left",
            border_style="red",
            padding=(1, 2),
        )
        self.console.print(summary_panel)

        # Display error categories table
        if error_categories:
            self.console.print("\n[bold]Error Categories:[/bold]")

            table = Table(show_header=True, header_style="bold red")
            table.add_column("Error Type", style="yellow", width=20)
            table.add_column("Count", style="red", width=10)
            table.add_column("Percentage", style="cyan", width=12)
            table.add_column("Sample Accounts", style="dim", width=40)

            for category, accounts in error_categories.items():
                count = len(accounts)
                percentage = (count / summary_stats["total_failed_accounts"]) * 100

                # Show sample account names (up to 3)
                sample_accounts = [f"{acc.account_name} ({acc.account_id})" for acc in accounts[:3]]
                if len(accounts) > 3:
                    sample_accounts.append(f"... and {len(accounts) - 3} more")
                sample_text = ", ".join(sample_accounts)

                table.add_row(
                    category.replace("_", " ").title(),
                    str(count),
                    f"{percentage:.1f}%",
                    sample_text,
                )

            self.console.print(table)

        # Display detailed error examples if requested
        if show_detailed_errors and error_categories:
            self.console.print("\n[bold]Detailed Error Examples:[/bold]")
            for category, accounts in list(error_categories.items())[:3]:  # Show top 3 categories
                if accounts:
                    self.console.print(
                        f"\n[yellow]{category.replace('_', ' ').title()} Errors:[/yellow]"
                    )
                    for account in accounts[:2]:  # Show 2 examples per category
                        self.console.print(
                            f"  • {account.get_display_name()}: {account.error_message}"
                        )

    def _display_error_recommendations(
        self, error_categories: Dict[str, List[AccountResult]], summary_stats: Dict[str, Any]
    ):
        """Display recommendations based on error patterns."""
        self.console.print("\n[bold cyan]💡 Recommendations:[/bold cyan]")

        recommendations = []

        # Permission-based recommendations
        if "permission_denied" in error_categories:
            count = len(error_categories["permission_denied"])
            recommendations.append(
                f"[yellow]Permission Issues ({count} accounts):[/yellow] "
                "Verify your IAM permissions include SSO Admin access for all target accounts. "
                "Consider using a role with cross-account permissions."
            )

        # Resource not found recommendations
        if "resource_not_found" in error_categories:
            count = len(error_categories["resource_not_found"])
            recommendations.append(
                f"[yellow]Resource Not Found ({count} accounts):[/yellow] "
                "Check that permission sets and principals exist in the target accounts. "
                "Some resources may not be replicated across all accounts."
            )

        # Throttling recommendations
        if "throttling" in error_categories:
            count = len(error_categories["throttling"])
            recommendations.append(
                f"[yellow]Rate Limiting ({count} accounts):[/yellow] "
                "Reduce batch size using --batch-size parameter or add delays between operations. "
                "Consider processing accounts in smaller groups."
            )

        # Network/timeout recommendations
        if any(cat in error_categories for cat in ["network", "timeout"]):
            network_count = len(error_categories.get("network", []))
            timeout_count = len(error_categories.get("timeout", []))
            total_count = network_count + timeout_count
            recommendations.append(
                f"[yellow]Network/Timeout Issues ({total_count} accounts):[/yellow] "
                "Check network connectivity and consider increasing timeout values. "
                "Retry failed operations as these are typically transient issues."
            )

        # High failure rate recommendations
        if summary_stats.get("failure_rate", 0) > 50:
            recommendations.append(
                f"[red]High Failure Rate ({summary_stats['failure_rate']:.1f}%):[/red] "
                "Consider validating your configuration with a smaller test set first. "
                "Use --dry-run to preview operations before execution."
            )

        # Retryable failures recommendations
        retryable_count = summary_stats.get("retryable_failures", 0)
        if retryable_count > 0:
            recommendations.append(
                f"[green]Retryable Failures ({retryable_count} accounts):[/green] "
                "These failures can typically be resolved by retrying the operation. "
                "Consider implementing automatic retry logic for production use."
            )

        # Display recommendations
        for i, recommendation in enumerate(recommendations, 1):
            self.console.print(f"  {i}. {recommendation}")

        # General recommendations if no specific patterns found
        if not recommendations:
            self.console.print(
                "  1. [green]Review individual account error messages for specific guidance[/green]"
            )
            self.console.print(
                "  2. [green]Use --dry-run to validate operations before execution[/green]"
            )
            self.console.print(
                "  3. [green]Consider processing accounts in smaller batches[/green]"
            )

    def export_error_report(
        self, results: MultiAccountResults, output_file: str, format: str = "json"
    ) -> bool:
        """Export detailed error report to file.

        Args:
            results: Multi-account operation results
            output_file: Path to output file
            format: Export format ('json', 'csv', 'txt')

        Returns:
            True if export successful, False otherwise
        """
        try:
            import csv
            import json
            from pathlib import Path

            # Generate comprehensive error data
            error_data = {
                "summary": results.get_summary_stats(),
                "failed_accounts": [
                    {
                        "account_id": account.account_id,
                        "account_name": account.account_name,
                        "error_message": account.error_message,
                        "processing_time": account.processing_time,
                        "retry_count": account.retry_count,
                        "timestamp": account.timestamp,
                    }
                    for account in results.failed_accounts
                ],
                "error_categories": self._categorize_account_errors(results.failed_accounts),
                "export_timestamp": time.time(),
                "operation_type": results.operation_type,
            }

            output_path = Path(output_file)

            if format.lower() == "json":
                with open(output_path, "w") as f:
                    json.dump(error_data, f, indent=2, default=str)

            elif format.lower() == "csv":
                with open(output_path, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(
                        [
                            "Account ID",
                            "Account Name",
                            "Error Message",
                            "Processing Time",
                            "Retry Count",
                            "Timestamp",
                        ]
                    )
                    for account in results.failed_accounts:
                        writer.writerow(
                            [
                                account.account_id,
                                account.account_name,
                                account.error_message,
                                account.processing_time,
                                account.retry_count,
                                account.timestamp,
                            ]
                        )

            elif format.lower() == "txt":
                with open(output_path, "w") as f:
                    f.write("Multi-Account Operation Error Report\n")
                    f.write(f"Generated: {datetime.now().isoformat()}\n")
                    f.write(f"Operation: {results.operation_type}\n")
                    f.write(f"Total Accounts: {results.total_accounts}\n")
                    f.write(f"Failed Accounts: {len(results.failed_accounts)}\n")
                    f.write(f"Failure Rate: {results.failure_rate:.1f}%\n\n")

                    f.write("Failed Accounts:\n")
                    f.write("-" * 80 + "\n")
                    for account in results.failed_accounts:
                        f.write(f"Account: {account.get_display_name()}\n")
                        f.write(f"Error: {account.error_message}\n")
                        f.write(f"Processing Time: {account.processing_time:.2f}s\n")
                        f.write(f"Retry Count: {account.retry_count}\n")
                        f.write("-" * 80 + "\n")

            self.console.print(f"[green]Error report exported to: {output_path}[/green]")
            return True

        except Exception as e:
            self.console.print(f"[red]Failed to export error report: {str(e)}[/red]")
            return False


# Enhanced error handling utilities


def create_detailed_error_context(
    error: Exception, operation_context: Dict[str, Any]
) -> Dict[str, Any]:
    """Create detailed error context for debugging.

    Args:
        error: The original exception
        operation_context: Context information about the operation

    Returns:
        Dictionary with detailed error context
    """
    import traceback

    context = {
        "error_type": type(error).__name__,
        "error_message": str(error),
        "operation_context": operation_context,
        "timestamp": time.time(),
    }

    # Add AWS-specific error details if available
    if hasattr(error, "response"):
        aws_error = error.response.get("Error", {})
        context["aws_error_code"] = aws_error.get("Code")
        context["aws_error_message"] = aws_error.get("Message")
        context["aws_request_id"] = error.response.get("ResponseMetadata", {}).get("RequestId")

    # Add stack trace for debugging
    context["stack_trace"] = traceback.format_exc()

    return context


def format_error_for_display(
    error: MultiAccountError, include_context: bool = True, include_guidance: bool = True
) -> str:
    """Format error for user-friendly display.

    Args:
        error: Multi-account error to format
        include_context: Whether to include detailed context
        include_guidance: Whether to include resolution guidance

    Returns:
        Formatted error string
    """
    lines = [error.get_display_message()]

    if include_context and error.get_detailed_context():
        lines.append(f"Context: {error.get_detailed_context()}")

    if include_guidance:
        if isinstance(error, NameResolutionError):
            guidance = error.get_resolution_guidance()
            if guidance:
                lines.append("Resolution guidance:")
                lines.extend([f"  • {tip}" for tip in guidance[:3]])  # Show top 3 tips

        elif isinstance(error, AccountFilterError):
            guidance = error.get_filter_guidance()
            if guidance:
                lines.append("Filter guidance:")
                lines.extend([f"  • {tip}" for tip in guidance[:3]])  # Show top 3 tips

    return "\n".join(lines)


def should_retry_error(error: Exception, retry_count: int, max_retries: int = 3) -> bool:
    """Determine if an error should be retried (backward compatibility).

    This function provides backward compatibility for existing code.
    New code should use the IntelligentBackoffManager directly.

    Args:
        error: The exception that occurred
        retry_count: Current retry count
        max_retries: Maximum number of retries allowed

    Returns:
        True if the error should be retried
    """
    # Import here to avoid circular imports
    from .intelligent_backoff import should_retry_error as intelligent_should_retry

    return intelligent_should_retry(error, retry_count, max_retries)


def calculate_retry_delay(
    retry_count: int, base_delay: float = 1.0, max_delay: float = 60.0
) -> float:
    """Calculate exponential backoff delay for retries (backward compatibility).

    This function provides backward compatibility for existing code.
    New code should use the IntelligentBackoffManager directly.

    Args:
        retry_count: Current retry attempt (0-based)
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds

    Returns:
        Delay in seconds before next retry
    """
    # Import here to avoid circular imports
    from .intelligent_backoff import calculate_retry_delay as intelligent_calculate_delay

    return intelligent_calculate_delay(retry_count, "Unknown")


def get_error_recovery_suggestions(error: MultiAccountError) -> List[str]:
    """Get specific recovery suggestions based on error type and context.

    Args:
        error: Multi-account error to analyze

    Returns:
        List of recovery suggestions
    """
    suggestions = []

    if error.error_type == MultiAccountErrorType.NAME_RESOLUTION:
        if isinstance(error, NameResolutionError):
            suggestions.extend(error.get_resolution_guidance())
        else:
            suggestions.extend(
                [
                    "Verify the resource name is correct and exists",
                    "Check your permissions for the relevant AWS service",
                    "Ensure you're using the correct AWS region",
                ]
            )

    elif error.error_type == MultiAccountErrorType.ACCOUNT_FILTER:
        if isinstance(error, AccountFilterError):
            suggestions.extend(error.get_filter_guidance())
        else:
            suggestions.extend(
                [
                    "Check the filter expression syntax",
                    "Ensure you have permissions to list organization accounts",
                    "Verify the filter criteria match existing accounts",
                ]
            )

    elif error.error_type == MultiAccountErrorType.PERMISSION_DENIED:
        suggestions.extend(
            [
                "Review IAM permissions for your role or user",
                "Ensure you have necessary permissions for SSO and Organizations APIs",
                "Check if MFA or additional authentication is required",
                "Verify you're using the correct AWS profile or credentials",
            ]
        )

    elif error.error_type == MultiAccountErrorType.THROTTLING:
        suggestions.extend(
            [
                "Reduce batch size to lower API request rate",
                "Add delays between operations using --batch-size parameter",
                "Retry the operation after a few minutes",
                "Consider spreading the operation across multiple time periods",
            ]
        )

    elif error.error_type == MultiAccountErrorType.NETWORK:
        suggestions.extend(
            [
                "Check your internet connectivity",
                "Verify AWS endpoint accessibility",
                "Check for firewall or proxy issues",
                "Retry the operation after network issues are resolved",
            ]
        )

    elif error.error_type == MultiAccountErrorType.SERVICE_ERROR:
        suggestions.extend(
            [
                "Check AWS Service Health Dashboard for known issues",
                "Retry the operation after a few minutes",
                "Contact AWS Support if the issue persists",
                "Consider using a different AWS region if available",
            ]
        )

    else:
        suggestions.extend(
            [
                "Review the error message for specific details",
                "Check AWS documentation for the relevant service",
                "Retry the operation if the error seems transient",
                "Contact support if the issue persists",
            ]
        )

    return suggestions


def analyze_error_patterns(errors: List[MultiAccountError]) -> Dict[str, Any]:
    """Analyze patterns in a collection of errors to identify common issues.

    Args:
        errors: List of multi-account errors to analyze

    Returns:
        Dictionary with pattern analysis results
    """
    if not errors:
        return {"has_patterns": False, "message": "No errors to analyze"}

    # Group errors by type
    error_type_counts = {}
    for error_type in MultiAccountErrorType:
        error_type_counts[error_type.value] = 0

    for error in errors:
        error_type_counts[error.error_type.value] += 1

    # Find dominant error types (>25% of total)
    total_errors = len(errors)
    dominant_types = []
    for error_type, count in error_type_counts.items():
        if count > 0 and (count / total_errors) >= 0.25:
            dominant_types.append(
                {"type": error_type, "count": count, "percentage": (count / total_errors) * 100}
            )

    # Analyze temporal patterns (if timestamps available)
    timestamped_errors = [e for e in errors if e.timestamp]
    temporal_analysis = {}

    if len(timestamped_errors) > 1:
        timestamps = [e.timestamp for e in timestamped_errors]
        time_span = max(timestamps) - min(timestamps)

        temporal_analysis = {
            "time_span_seconds": time_span,
            "error_rate_per_minute": (len(timestamped_errors) / max(time_span / 60, 1)),
            "has_temporal_clustering": time_span < 300
            and len(timestamped_errors) > 5,  # Errors within 5 minutes
        }

    # Analyze account-specific patterns
    account_error_counts = {}
    for error in errors:
        if error.account_id:
            account_error_counts[error.account_id] = (
                account_error_counts.get(error.account_id, 0) + 1
            )

    problematic_accounts = [
        {"account_id": account_id, "error_count": count}
        for account_id, count in account_error_counts.items()
        if count > 1
    ]

    return {
        "has_patterns": True,
        "total_errors": total_errors,
        "error_type_distribution": error_type_counts,
        "dominant_error_types": dominant_types,
        "temporal_analysis": temporal_analysis,
        "problematic_accounts": problematic_accounts,
        "retryable_error_count": sum(1 for e in errors if e.is_retryable()),
        "unique_accounts_affected": len(set(e.account_id for e in errors if e.account_id)),
    }


def create_error_troubleshooting_guide(error: MultiAccountError) -> str:
    """Create a comprehensive troubleshooting guide for a specific error.

    Args:
        error: Multi-account error to create guide for

    Returns:
        Formatted troubleshooting guide as string
    """
    guide_lines = []

    # Error summary
    guide_lines.append("🔍 Error Troubleshooting Guide")
    guide_lines.append("=" * 50)
    guide_lines.append(f"Error Type: {error.error_type.value}")
    guide_lines.append(f"Message: {error.message}")

    if error.account_id and error.account_name:
        guide_lines.append(f"Account: {error.account_name} ({error.account_id})")

    guide_lines.append("")

    # Context information
    if error.get_detailed_context():
        guide_lines.append("📋 Context Information:")
        guide_lines.append(error.get_detailed_context())
        guide_lines.append("")

    # Recovery suggestions
    suggestions = get_error_recovery_suggestions(error)
    if suggestions:
        guide_lines.append("💡 Recovery Suggestions:")
        for i, suggestion in enumerate(suggestions, 1):
            guide_lines.append(f"  {i}. {suggestion}")
        guide_lines.append("")

    # Retry information
    if error.is_retryable():
        guide_lines.append("🔄 Retry Information:")
        guide_lines.append("  • This error type is typically retryable")
        guide_lines.append("  • Consider waiting a few minutes before retrying")
        guide_lines.append("  • Use exponential backoff for multiple retry attempts")
    else:
        guide_lines.append("⚠️ Retry Information:")
        guide_lines.append("  • This error type is typically not retryable")
        guide_lines.append("  • Focus on resolving the underlying issue before retrying")

    guide_lines.append("")

    # Additional resources
    guide_lines.append("📚 Additional Resources:")
    guide_lines.append("  • AWS Identity Center Documentation")
    guide_lines.append("  • AWS Organizations Documentation")
    guide_lines.append("  • AWS Service Health Dashboard")
    guide_lines.append("  • AWS Support (for persistent issues)")

    return "\n".join(guide_lines)
