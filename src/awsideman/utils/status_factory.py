"""Factory functions and utilities for creating status monitoring components."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .status_infrastructure import StatusCheckConfig, StatusOrchestrator
from .status_models import (
    BaseStatusResult,
    HealthStatus,
    OrphanedAssignmentStatus,
    ProvisioningStatus,
    StatusLevel,
    StatusReport,
    SummaryStatistics,
    SyncMonitorStatus,
)

logger = logging.getLogger(__name__)


class StatusFactory:
    """
    Factory class for creating status monitoring components.

    Provides centralized creation and configuration of status checkers,
    orchestrators, and related components with proper dependency injection.
    """

    def __init__(self, idc_client, config: Optional[StatusCheckConfig] = None):
        """
        Initialize the status factory.

        Args:
            idc_client: AWS Identity Center client
            config: Configuration for status checking
        """
        self.idc_client = idc_client
        self.config = config or StatusCheckConfig()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def create_orchestrator(self) -> StatusOrchestrator:
        """
        Create a status orchestrator with all available checkers registered.

        Returns:
            StatusOrchestrator: Configured orchestrator
        """
        from .health_checker import HealthChecker

        orchestrator = StatusOrchestrator(self.idc_client, self.config)

        # Register available checker types
        orchestrator.register_checker("health", HealthChecker)

        self.logger.debug("Created status orchestrator with health checker")
        return orchestrator

    def create_health_status(
        self,
        status: StatusLevel = StatusLevel.HEALTHY,
        message: str = "Health check not performed",
        **kwargs,
    ) -> HealthStatus:
        """
        Create a health status instance with default values.

        Args:
            status: Status level
            message: Status message
            **kwargs: Additional parameters for HealthStatus

        Returns:
            HealthStatus: Health status instance
        """
        return HealthStatus(
            timestamp=datetime.now(timezone.utc),
            status=status,
            message=message,
            service_available=kwargs.get("service_available", True),
            connectivity_status=kwargs.get("connectivity_status", "Connected"),
            response_time_ms=kwargs.get("response_time_ms"),
            last_successful_check=kwargs.get("last_successful_check"),
        )

    def create_provisioning_status(
        self,
        status: StatusLevel = StatusLevel.HEALTHY,
        message: str = "Provisioning check not performed",
        **kwargs,
    ) -> ProvisioningStatus:
        """
        Create a provisioning status instance with default values.

        Args:
            status: Status level
            message: Status message
            **kwargs: Additional parameters for ProvisioningStatus

        Returns:
            ProvisioningStatus: Provisioning status instance
        """
        return ProvisioningStatus(
            timestamp=datetime.now(timezone.utc),
            status=status,
            message=message,
            active_operations=kwargs.get("active_operations", []),
            failed_operations=kwargs.get("failed_operations", []),
            completed_operations=kwargs.get("completed_operations", []),
            pending_count=kwargs.get("pending_count", 0),
            estimated_completion=kwargs.get("estimated_completion"),
        )

    def create_orphaned_assignment_status(
        self,
        status: StatusLevel = StatusLevel.HEALTHY,
        message: str = "Orphaned assignment check not performed",
        **kwargs,
    ) -> OrphanedAssignmentStatus:
        """
        Create an orphaned assignment status instance with default values.

        Args:
            status: Status level
            message: Status message
            **kwargs: Additional parameters for OrphanedAssignmentStatus

        Returns:
            OrphanedAssignmentStatus: Orphaned assignment status instance
        """
        return OrphanedAssignmentStatus(
            timestamp=datetime.now(timezone.utc),
            status=status,
            message=message,
            orphaned_assignments=kwargs.get("orphaned_assignments", []),
            cleanup_available=kwargs.get("cleanup_available", True),
            last_cleanup=kwargs.get("last_cleanup"),
            cleanup_history=kwargs.get("cleanup_history", []),
        )

    def create_sync_monitor_status(
        self,
        status: StatusLevel = StatusLevel.HEALTHY,
        message: str = "Sync monitor check not performed",
        **kwargs,
    ) -> SyncMonitorStatus:
        """
        Create a sync monitor status instance with default values.

        Args:
            status: Status level
            message: Status message
            **kwargs: Additional parameters for SyncMonitorStatus

        Returns:
            SyncMonitorStatus: Sync monitor status instance
        """
        return SyncMonitorStatus(
            timestamp=datetime.now(timezone.utc),
            status=status,
            message=message,
            sync_providers=kwargs.get("sync_providers", []),
            providers_configured=kwargs.get("providers_configured", 0),
            providers_healthy=kwargs.get("providers_healthy", 0),
            providers_with_errors=kwargs.get("providers_with_errors", 0),
        )

    def create_summary_statistics(self, **kwargs) -> SummaryStatistics:
        """
        Create a summary statistics instance with default values.

        Args:
            **kwargs: Parameters for SummaryStatistics

        Returns:
            SummaryStatistics: Summary statistics instance
        """
        return SummaryStatistics(
            total_users=kwargs.get("total_users", 0),
            total_groups=kwargs.get("total_groups", 0),
            total_permission_sets=kwargs.get("total_permission_sets", 0),
            total_assignments=kwargs.get("total_assignments", 0),
            active_accounts=kwargs.get("active_accounts", 0),
            last_updated=kwargs.get("last_updated", datetime.now(timezone.utc)),
            user_creation_dates=kwargs.get("user_creation_dates", {}),
            group_creation_dates=kwargs.get("group_creation_dates", {}),
            permission_set_creation_dates=kwargs.get("permission_set_creation_dates", {}),
        )

    def create_status_report(
        self,
        overall_health: Optional[HealthStatus] = None,
        provisioning_status: Optional[ProvisioningStatus] = None,
        orphaned_assignment_status: Optional[OrphanedAssignmentStatus] = None,
        sync_status: Optional[SyncMonitorStatus] = None,
        summary_statistics: Optional[SummaryStatistics] = None,
        **kwargs,
    ) -> StatusReport:
        """
        Create a comprehensive status report with default components.

        Args:
            overall_health: Health status component
            provisioning_status: Provisioning status component
            orphaned_assignment_status: Orphaned assignment status component
            sync_status: Sync monitor status component
            summary_statistics: Summary statistics component
            **kwargs: Additional parameters for StatusReport

        Returns:
            StatusReport: Complete status report
        """
        return StatusReport(
            timestamp=datetime.now(timezone.utc),
            overall_health=overall_health or self.create_health_status(),
            provisioning_status=provisioning_status or self.create_provisioning_status(),
            orphaned_assignment_status=orphaned_assignment_status
            or self.create_orphaned_assignment_status(),
            sync_status=sync_status or self.create_sync_monitor_status(),
            summary_statistics=summary_statistics or self.create_summary_statistics(),
            resource_inspections=kwargs.get("resource_inspections", []),
            check_duration_seconds=kwargs.get("check_duration_seconds", 0.0),
        )

    def create_error_status_result(
        self,
        error_message: str,
        status: StatusLevel = StatusLevel.CRITICAL,
        component: str = "Unknown",
        details: Optional[Dict[str, Any]] = None,
    ) -> BaseStatusResult:
        """
        Create a status result for error conditions.

        Args:
            error_message: Error message
            status: Status level for the error
            component: Component that generated the error
            details: Additional error details

        Returns:
            BaseStatusResult: Error status result
        """
        result = BaseStatusResult(
            timestamp=datetime.now(timezone.utc),
            status=status,
            message=error_message,
            details=details or {},
            errors=[error_message],
        )

        result.add_detail("component", component)
        result.add_detail("error_timestamp", datetime.now(timezone.utc))

        return result


class StatusConfigBuilder:
    """
    Builder class for creating status check configurations.

    Provides a fluent interface for building status check configurations
    with validation and sensible defaults.
    """

    def __init__(self):
        self._config = StatusCheckConfig()

    def with_timeout(self, timeout_seconds: int) -> "StatusConfigBuilder":
        """
        Set the timeout for status checks.

        Args:
            timeout_seconds: Timeout in seconds

        Returns:
            StatusConfigBuilder: Builder instance for chaining
        """
        self._config.timeout_seconds = timeout_seconds
        return self

    def with_retry_attempts(self, retry_attempts: int) -> "StatusConfigBuilder":
        """
        Set the number of retry attempts.

        Args:
            retry_attempts: Number of retry attempts

        Returns:
            StatusConfigBuilder: Builder instance for chaining
        """
        self._config.retry_attempts = retry_attempts
        return self

    def with_retry_delay(self, retry_delay_seconds: float) -> "StatusConfigBuilder":
        """
        Set the delay between retry attempts.

        Args:
            retry_delay_seconds: Delay in seconds

        Returns:
            StatusConfigBuilder: Builder instance for chaining
        """
        self._config.retry_delay_seconds = retry_delay_seconds
        return self

    def enable_parallel_checks(self, enabled: bool = True) -> "StatusConfigBuilder":
        """
        Enable or disable parallel status checks.

        Args:
            enabled: Whether to enable parallel checks

        Returns:
            StatusConfigBuilder: Builder instance for chaining
        """
        self._config.enable_parallel_checks = enabled
        return self

    def with_max_concurrent_checks(self, max_concurrent: int) -> "StatusConfigBuilder":
        """
        Set the maximum number of concurrent checks.

        Args:
            max_concurrent: Maximum concurrent checks

        Returns:
            StatusConfigBuilder: Builder instance for chaining
        """
        self._config.max_concurrent_checks = max_concurrent
        return self

    def include_detailed_errors(self, include: bool = True) -> "StatusConfigBuilder":
        """
        Enable or disable detailed error information.

        Args:
            include: Whether to include detailed errors

        Returns:
            StatusConfigBuilder: Builder instance for chaining
        """
        self._config.include_detailed_errors = include
        return self

    def build(self) -> StatusCheckConfig:
        """
        Build the status check configuration.

        Returns:
            StatusCheckConfig: Built configuration

        Raises:
            ValueError: If configuration is invalid
        """
        errors = self._config.validate()
        if errors:
            raise ValueError(f"Invalid configuration: {', '.join(errors)}")

        return self._config


def create_default_status_factory(idc_client) -> StatusFactory:
    """
    Create a status factory with default configuration.

    Args:
        idc_client: AWS Identity Center client

    Returns:
        StatusFactory: Configured status factory
    """
    config = (
        StatusConfigBuilder()
        .with_timeout(30)
        .with_retry_attempts(3)
        .with_retry_delay(1.0)
        .enable_parallel_checks(True)
        .with_max_concurrent_checks(5)
        .include_detailed_errors(True)
        .build()
    )

    return StatusFactory(idc_client, config)


def create_fast_status_factory(idc_client) -> StatusFactory:
    """
    Create a status factory optimized for fast checks.

    Args:
        idc_client: AWS Identity Center client

    Returns:
        StatusFactory: Fast-configured status factory
    """
    config = (
        StatusConfigBuilder()
        .with_timeout(10)
        .with_retry_attempts(1)
        .with_retry_delay(0.5)
        .enable_parallel_checks(True)
        .with_max_concurrent_checks(10)
        .include_detailed_errors(False)
        .build()
    )

    return StatusFactory(idc_client, config)


def create_robust_status_factory(idc_client) -> StatusFactory:
    """
    Create a status factory optimized for reliability.

    Args:
        idc_client: AWS Identity Center client

    Returns:
        StatusFactory: Robust-configured status factory
    """
    config = (
        StatusConfigBuilder()
        .with_timeout(60)
        .with_retry_attempts(5)
        .with_retry_delay(2.0)
        .enable_parallel_checks(False)  # Sequential for reliability
        .with_max_concurrent_checks(1)
        .include_detailed_errors(True)
        .build()
    )

    return StatusFactory(idc_client, config)
