"""Core infrastructure classes for AWS Identity Center status monitoring."""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Type

from .status_models import (
    BaseStatusResult,
    FormattedOutput,
    HealthStatus,
    OrphanedAssignmentStatus,
    OutputFormat,
    ProvisioningStatus,
    StatusLevel,
    StatusReport,
    SummaryStatistics,
    SyncMonitorStatus,
)

logger = logging.getLogger(__name__)


class StatusCheckError(Exception):
    """Base exception for status checking operations."""

    def __init__(self, message: str, component: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.component = component
        self.details = details or {}
        self.timestamp = datetime.now(timezone.utc)


class ConnectionError(StatusCheckError):
    """Exception raised when connection to Identity Center fails."""

    pass


class PermissionError(StatusCheckError):
    """Exception raised when insufficient permissions for status checks."""

    pass


class TimeoutError(StatusCheckError):
    """Exception raised when status checks timeout."""

    pass


@dataclass
class StatusCheckConfig:
    """Configuration for status checking operations."""

    timeout_seconds: int = 30
    retry_attempts: int = 3
    retry_delay_seconds: float = 1.0
    enable_parallel_checks: bool = True
    max_concurrent_checks: int = 5
    include_detailed_errors: bool = True

    def validate(self) -> List[str]:
        """Validate configuration parameters."""
        errors = []

        if self.timeout_seconds <= 0:
            errors.append("Timeout must be positive")

        if self.retry_attempts < 0:
            errors.append("Retry attempts cannot be negative")

        if self.retry_delay_seconds < 0:
            errors.append("Retry delay cannot be negative")

        if self.max_concurrent_checks <= 0:
            errors.append("Max concurrent checks must be positive")

        return errors


class BaseStatusChecker(ABC):
    """
    Abstract base class for all status checking components.

    Provides common functionality for status checking including
    error handling, retry logic, and result standardization.
    """

    def __init__(self, idc_client, config: Optional[StatusCheckConfig] = None):
        """
        Initialize the status checker.

        Args:
            idc_client: AWS Identity Center client
            config: Configuration for status checking
        """
        self.idc_client = idc_client
        self.config = config or StatusCheckConfig()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Validate configuration
        config_errors = self.config.validate()
        if config_errors:
            raise ValueError(f"Invalid configuration: {', '.join(config_errors)}")

    @abstractmethod
    async def check_status(self) -> BaseStatusResult:
        """
        Perform the status check and return results.

        Returns:
            BaseStatusResult: Status check results
        """
        pass

    async def check_status_with_retry(self) -> BaseStatusResult:
        """
        Perform status check with retry logic.

        Returns:
            BaseStatusResult: Status check results
        """
        last_error = None

        for attempt in range(self.config.retry_attempts + 1):
            try:
                self.logger.debug(f"Status check attempt {attempt + 1}")
                return await asyncio.wait_for(
                    self.check_status(), timeout=self.config.timeout_seconds
                )

            except asyncio.TimeoutError:
                last_error = TimeoutError(
                    f"Status check timed out after {self.config.timeout_seconds} seconds",
                    self.__class__.__name__,
                )
                self.logger.warning(f"Attempt {attempt + 1} timed out")

            except Exception as e:
                last_error = StatusCheckError(
                    f"Status check failed: {str(e)}",
                    self.__class__.__name__,
                    {"original_error": str(e), "error_type": type(e).__name__},
                )
                self.logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")

            # Wait before retry (except on last attempt)
            if attempt < self.config.retry_attempts:
                await asyncio.sleep(self.config.retry_delay_seconds)

        # All attempts failed, return error result
        return self._create_error_result(last_error)

    def _create_error_result(self, error: StatusCheckError) -> BaseStatusResult:
        """
        Create a status result for error conditions.

        Args:
            error: The error that occurred

        Returns:
            BaseStatusResult: Error status result
        """
        if isinstance(error, ConnectionError):
            status = StatusLevel.CONNECTION_FAILED
        elif isinstance(error, TimeoutError):
            status = StatusLevel.CRITICAL
        else:
            status = StatusLevel.CRITICAL

        result = BaseStatusResult(
            timestamp=datetime.now(timezone.utc),
            status=status,
            message=str(error),
            details=error.details if hasattr(error, "details") else {},
            errors=[str(error)],
        )

        if self.config.include_detailed_errors:
            result.add_detail(
                "component",
                error.component if hasattr(error, "component") else self.__class__.__name__,
            )
            result.add_detail(
                "error_timestamp",
                error.timestamp if hasattr(error, "timestamp") else datetime.now(timezone.utc),
            )

        return result

    def _handle_aws_error(self, error: Exception) -> StatusCheckError:
        """
        Convert AWS SDK errors to appropriate status check errors.

        Args:
            error: AWS SDK error

        Returns:
            StatusCheckError: Converted error
        """
        error_str = str(error)
        error_code = getattr(error, "response", {}).get("Error", {}).get("Code", "")

        # Connection-related errors
        if any(
            term in error_str.lower()
            for term in ["connection", "network", "timeout", "unreachable"]
        ):
            return ConnectionError(
                f"Failed to connect to Identity Center: {error_str}",
                self.__class__.__name__,
                {"aws_error_code": error_code},
            )

        # Permission-related errors
        if error_code in ["AccessDenied", "UnauthorizedOperation", "Forbidden"]:
            return PermissionError(
                f"Insufficient permissions for status check: {error_str}",
                self.__class__.__name__,
                {"aws_error_code": error_code},
            )

        # Generic error
        return StatusCheckError(
            f"AWS API error: {error_str}", self.__class__.__name__, {"aws_error_code": error_code}
        )


class StatusOrchestrator:
    """
    Central orchestrator for coordinating all status checking operations.

    Manages multiple status checkers and aggregates their results into
    a comprehensive status report.
    """

    def __init__(self, idc_client, config: Optional[StatusCheckConfig] = None):
        """
        Initialize the status orchestrator.

        Args:
            idc_client: AWS Identity Center client
            config: Configuration for status checking
        """
        self.idc_client = idc_client
        self.config = config or StatusCheckConfig()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Status checkers will be initialized by subclasses or dependency injection
        self._checkers: Dict[str, BaseStatusChecker] = {}
        self._check_registry: Dict[str, Type[BaseStatusChecker]] = {}

    def register_checker(self, name: str, checker_class: Type[BaseStatusChecker]) -> None:
        """
        Register a status checker class.

        Args:
            name: Name of the checker
            checker_class: Status checker class
        """
        self._check_registry[name] = checker_class
        self.logger.debug(f"Registered status checker: {name}")

    def get_checker(self, name: str) -> Optional[BaseStatusChecker]:
        """
        Get a status checker instance by name.

        Args:
            name: Name of the checker

        Returns:
            BaseStatusChecker: Checker instance or None if not found
        """
        if name not in self._checkers and name in self._check_registry:
            # Lazy initialization
            checker_class = self._check_registry[name]
            self._checkers[name] = checker_class(self.idc_client, self.config)

        return self._checkers.get(name)

    async def get_comprehensive_status(self) -> StatusReport:
        """
        Get comprehensive status from all registered checkers.

        Returns:
            StatusReport: Complete status report
        """
        start_time = datetime.now(timezone.utc)
        self.logger.info("Starting comprehensive status check")

        # Initialize default status components
        health_status = HealthStatus(
            timestamp=start_time, status=StatusLevel.HEALTHY, message="Status check not performed"
        )

        provisioning_status = ProvisioningStatus(
            timestamp=start_time, status=StatusLevel.HEALTHY, message="Status check not performed"
        )

        orphaned_status = OrphanedAssignmentStatus(
            timestamp=start_time, status=StatusLevel.HEALTHY, message="Status check not performed"
        )

        sync_status = SyncMonitorStatus(
            timestamp=start_time, status=StatusLevel.HEALTHY, message="Status check not performed"
        )

        summary_stats = SummaryStatistics(
            total_users=0,
            total_groups=0,
            total_permission_sets=0,
            total_assignments=0,
            active_accounts=0,
            last_updated=start_time,
        )

        # Run status checks
        if self.config.enable_parallel_checks:
            await self._run_parallel_checks(
                health_status, provisioning_status, orphaned_status, sync_status, summary_stats
            )
        else:
            await self._run_sequential_checks(
                health_status, provisioning_status, orphaned_status, sync_status, summary_stats
            )

        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()

        # Create comprehensive report
        report = StatusReport(
            timestamp=start_time,
            overall_health=health_status,
            provisioning_status=provisioning_status,
            orphaned_assignment_status=orphaned_status,
            sync_status=sync_status,
            summary_statistics=summary_stats,
            check_duration_seconds=duration,
        )

        self.logger.info(f"Comprehensive status check completed in {duration:.2f} seconds")
        return report

    async def get_specific_status(self, check_type: str) -> BaseStatusResult:
        """
        Get status from a specific checker.

        Args:
            check_type: Type of status check to perform

        Returns:
            BaseStatusResult: Status check result
        """
        checker = self.get_checker(check_type)
        if not checker:
            return BaseStatusResult(
                timestamp=datetime.now(timezone.utc),
                status=StatusLevel.CRITICAL,
                message=f"Unknown status check type: {check_type}",
                errors=[f"Status checker '{check_type}' not found"],
            )

        self.logger.info(f"Running specific status check: {check_type}")
        return await checker.check_status_with_retry()

    async def _run_parallel_checks(
        self, health_status, provisioning_status, orphaned_status, sync_status, summary_stats
    ) -> None:
        """Run status checks in parallel with concurrency limits."""
        semaphore = asyncio.Semaphore(self.config.max_concurrent_checks)

        async def run_check(checker_name: str, result_container: List):
            async with semaphore:
                checker = self.get_checker(checker_name)
                if checker:
                    result = await checker.check_status_with_retry()
                    result_container.append(result)

        # Prepare tasks for parallel execution
        tasks = []
        results = {"health": [], "provisioning": [], "orphaned": [], "sync": [], "summary": []}

        # Add tasks for each checker type
        for checker_name, result_key in [
            ("health", "health"),
            ("provisioning", "provisioning"),
            ("orphaned", "orphaned"),
            ("sync", "sync"),
            ("summary", "summary"),
        ]:
            if checker_name in self._check_registry:
                tasks.append(run_check(checker_name, results[result_key]))

        # Execute all tasks
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # Update status objects with results
        self._update_status_from_results(
            results, health_status, provisioning_status, orphaned_status, sync_status, summary_stats
        )

    async def _run_sequential_checks(
        self, health_status, provisioning_status, orphaned_status, sync_status, summary_stats
    ) -> None:
        """Run status checks sequentially."""
        # Run each check type sequentially
        for checker_name, status_obj in [
            ("health", health_status),
            ("provisioning", provisioning_status),
            ("orphaned", orphaned_status),
            ("sync", sync_status),
            ("summary", summary_stats),
        ]:
            checker = self.get_checker(checker_name)
            if checker:
                try:
                    await checker.check_status_with_retry()
                    # Update the status object with the result
                    # This would need specific implementation based on result type
                    self.logger.debug(f"Completed {checker_name} status check")
                except Exception as e:
                    self.logger.error(f"Failed to run {checker_name} status check: {str(e)}")

    def _update_status_from_results(
        self,
        results: Dict,
        health_status,
        provisioning_status,
        orphaned_status,
        sync_status,
        summary_stats,
    ) -> None:
        """Update status objects from parallel check results."""
        # This method would contain specific logic to update each status object
        # based on the results from the parallel checks
        # Implementation would depend on the specific checker implementations
        pass

    def get_available_checks(self) -> List[str]:
        """
        Get list of available status check types.

        Returns:
            List[str]: Available check types
        """
        return list(self._check_registry.keys())

    def is_checker_available(self, check_type: str) -> bool:
        """
        Check if a specific checker is available.

        Args:
            check_type: Type of status check

        Returns:
            bool: True if checker is available
        """
        return check_type in self._check_registry


class OutputFormatter(ABC):
    """
    Abstract base class for status output formatters.

    Provides interface for converting status reports into different
    output formats like JSON, CSV, and table formats.
    """

    @abstractmethod
    def format(self, status_report: StatusReport) -> FormattedOutput:
        """
        Format a status report into the target format.

        Args:
            status_report: Status report to format

        Returns:
            FormattedOutput: Formatted output
        """
        pass

    @abstractmethod
    def get_format_type(self) -> OutputFormat:
        """
        Get the output format type.

        Returns:
            OutputFormat: Format type
        """
        pass


class FormatterRegistry:
    """
    Registry for output formatters.

    Manages available output formatters and provides
    format detection and validation.
    """

    def __init__(self):
        self._formatters: Dict[OutputFormat, OutputFormatter] = {}

    def register_formatter(self, formatter: OutputFormatter) -> None:
        """
        Register an output formatter.

        Args:
            formatter: Output formatter to register
        """
        format_type = formatter.get_format_type()
        self._formatters[format_type] = formatter

    def get_formatter(self, format_type: OutputFormat) -> Optional[OutputFormatter]:
        """
        Get a formatter by format type.

        Args:
            format_type: Desired output format

        Returns:
            OutputFormatter: Formatter instance or None if not found
        """
        return self._formatters.get(format_type)

    def format_status_report(
        self, status_report: StatusReport, format_type: OutputFormat
    ) -> FormattedOutput:
        """
        Format a status report using the specified formatter.

        Args:
            status_report: Status report to format
            format_type: Desired output format

        Returns:
            FormattedOutput: Formatted output

        Raises:
            ValueError: If formatter not found
        """
        formatter = self.get_formatter(format_type)
        if not formatter:
            raise ValueError(f"No formatter available for format: {format_type}")

        return formatter.format(status_report)

    def get_available_formats(self) -> List[OutputFormat]:
        """
        Get list of available output formats.

        Returns:
            List[OutputFormat]: Available formats
        """
        return list(self._formatters.keys())

    def is_format_supported(self, format_type: OutputFormat) -> bool:
        """
        Check if a format is supported.

        Args:
            format_type: Format to check

        Returns:
            bool: True if format is supported
        """
        return format_type in self._formatters


# Global formatter registry instance
formatter_registry = FormatterRegistry()
