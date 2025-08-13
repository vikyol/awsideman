"""Status orchestrator for coordinating AWS Identity Center status checks."""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .health_checker import HealthChecker
from .orphaned_assignment_detector import OrphanedAssignmentDetector
from .provisioning_monitor import ProvisioningMonitor
from .resource_inspector import ResourceInspector
from .status_infrastructure import BaseStatusChecker, StatusCheckConfig
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
from .summary_statistics import SummaryStatisticsCollector
from .sync_monitor import SyncMonitor

logger = logging.getLogger(__name__)


class StatusOrchestrator:
    """
    Central orchestrator for coordinating all status checking operations.

    Manages multiple status checkers and aggregates their results into
    a comprehensive status report with error handling for partial failures
    and graceful degradation.
    """

    def __init__(self, idc_client, config: Optional[StatusCheckConfig] = None):
        """
        Initialize the status orchestrator.

        Args:
            idc_client: AWS Identity Center client wrapper
            config: Configuration for status checking operations
        """
        self.idc_client = idc_client
        self.config = config or StatusCheckConfig()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Initialize status checking components
        self.health_checker = HealthChecker(idc_client, config)
        self.provisioning_monitor = ProvisioningMonitor(idc_client, config)
        self.orphaned_detector = OrphanedAssignmentDetector(idc_client, config)
        self.sync_monitor = SyncMonitor(idc_client, config)
        self.resource_inspector = ResourceInspector(idc_client, config)
        self.summary_statistics_collector = SummaryStatisticsCollector(idc_client, config)

        # Component registry for dynamic access
        self._components = {
            "health": self.health_checker,
            "provisioning": self.provisioning_monitor,
            "orphaned": self.orphaned_detector,
            "sync": self.sync_monitor,
            "resource": self.resource_inspector,
            "summary": self.summary_statistics_collector,
        }

        # Track component failures for graceful degradation
        self._component_failures: Dict[str, List[str]] = {}

    async def get_comprehensive_status(self) -> StatusReport:
        """
        Get comprehensive status from all status checking components.

        Coordinates all status checkers and aggregates results with error handling
        for partial failures and graceful degradation when some components fail.

        Returns:
            StatusReport: Complete status report with results from all components
        """
        start_time = time.time()
        timestamp = datetime.now(timezone.utc)

        self.logger.info("Starting comprehensive status check")

        # Initialize default status components for graceful degradation
        health_status = self._create_default_health_status(timestamp)
        provisioning_status = self._create_default_provisioning_status(timestamp)
        orphaned_status = self._create_default_orphaned_status(timestamp)
        sync_status = self._create_default_sync_status(timestamp)
        summary_stats = self._create_default_summary_stats(timestamp)

        # Clear previous failure tracking
        self._component_failures.clear()

        try:
            # Run status checks with error handling
            if self.config.enable_parallel_checks:
                await self._run_parallel_checks(
                    health_status, provisioning_status, orphaned_status, sync_status, summary_stats
                )
            else:
                await self._run_sequential_checks(
                    health_status, provisioning_status, orphaned_status, sync_status, summary_stats
                )

            # Calculate check duration
            check_duration = time.time() - start_time

            # Create comprehensive status report
            status_report = StatusReport(
                timestamp=timestamp,
                overall_health=health_status,
                provisioning_status=provisioning_status,
                orphaned_assignment_status=orphaned_status,
                sync_status=sync_status,
                summary_statistics=summary_stats,
                check_duration_seconds=check_duration,
            )

            # Add orchestrator metadata
            status_report.overall_health.add_detail("orchestrator_version", "1.0.0")
            status_report.overall_health.add_detail(
                "parallel_execution", self.config.enable_parallel_checks
            )
            status_report.overall_health.add_detail("component_count", len(self._components))

            # Add failure information if any components failed
            if self._component_failures:
                status_report.overall_health.add_detail(
                    "component_failures", self._component_failures
                )
                status_report.overall_health.add_detail("degraded_mode", True)
            else:
                status_report.overall_health.add_detail("degraded_mode", False)

            self.logger.info(
                f"Comprehensive status check completed in {check_duration:.2f} seconds"
            )

            # Log any component failures
            if self._component_failures:
                failed_components = list(self._component_failures.keys())
                self.logger.warning(
                    f"Status check completed with component failures: {failed_components}"
                )

            return status_report

        except Exception as e:
            # Handle critical orchestrator failures
            self.logger.error(f"Critical error in status orchestrator: {str(e)}")

            # Create error status report
            error_health = HealthStatus(
                timestamp=timestamp,
                status=StatusLevel.CRITICAL,
                message=f"Status orchestrator failed: {str(e)}",
                service_available=False,
                connectivity_status="Error",
            )
            error_health.add_error(str(e))
            error_health.add_detail("error_type", type(e).__name__)
            error_health.add_detail("component", "StatusOrchestrator")

            return StatusReport(
                timestamp=timestamp,
                overall_health=error_health,
                provisioning_status=provisioning_status,
                orphaned_assignment_status=orphaned_status,
                sync_status=sync_status,
                summary_statistics=summary_stats,
                check_duration_seconds=time.time() - start_time,
            )

    async def get_specific_status(self, check_type: str) -> BaseStatusResult:
        """
        Get status from a specific component type.

        Args:
            check_type: Type of status check ('health', 'provisioning', 'orphaned', 'sync', 'resource')

        Returns:
            BaseStatusResult: Status check result from the specified component
        """
        self.logger.info(f"Running specific status check: {check_type}")

        component = self._components.get(check_type)
        if not component:
            error_result = BaseStatusResult(
                timestamp=datetime.now(timezone.utc),
                status=StatusLevel.CRITICAL,
                message=f"Unknown status check type: {check_type}",
                errors=[f"Status checker '{check_type}' not found"],
            )
            error_result.add_detail("available_types", list(self._components.keys()))
            return error_result

        try:
            # Run the specific status check with retry logic
            result = await self._run_component_check_with_retry(check_type, component)

            self.logger.info(
                f"Specific status check '{check_type}' completed: {result.status.value}"
            )
            return result

        except Exception as e:
            self.logger.error(f"Error in specific status check '{check_type}': {str(e)}")

            error_result = BaseStatusResult(
                timestamp=datetime.now(timezone.utc),
                status=StatusLevel.CRITICAL,
                message=f"Status check '{check_type}' failed: {str(e)}",
                errors=[str(e)],
            )
            error_result.add_detail("error_type", type(e).__name__)
            error_result.add_detail("component", check_type)

            return error_result

    async def _run_parallel_checks(
        self,
        health_status: HealthStatus,
        provisioning_status: ProvisioningStatus,
        orphaned_status: OrphanedAssignmentStatus,
        sync_status: SyncMonitorStatus,
        summary_stats: SummaryStatistics,
    ) -> None:
        """
        Run status checks in parallel with concurrency limits and error handling.

        Args:
            health_status: Health status object to update
            provisioning_status: Provisioning status object to update
            orphaned_status: Orphaned assignment status object to update
            sync_status: Sync status object to update
            summary_stats: Summary statistics object to update
        """
        semaphore = asyncio.Semaphore(self.config.max_concurrent_checks)

        async def run_component_check(
            component_name: str, component: BaseStatusChecker, result_container: Dict[str, Any]
        ) -> None:
            """Run a single component check with semaphore control."""
            async with semaphore:
                try:
                    self.logger.debug(f"Starting parallel check for {component_name}")
                    result = await self._run_component_check_with_retry(component_name, component)

                    # Check if the result indicates a failure
                    if result.status == StatusLevel.CRITICAL and result.errors:
                        # This is a failed component check
                        result_container[component_name] = {
                            "success": False,
                            "error": result.errors[0] if result.errors else result.message,
                            "error_type": "ComponentFailure",
                        }
                        # Track component failure
                        if component_name not in self._component_failures:
                            self._component_failures[component_name] = []
                        self._component_failures[component_name].extend(result.errors)
                    else:
                        result_container[component_name] = {"success": True, "result": result}

                    self.logger.debug(
                        f"Completed parallel check for {component_name}: {result.status.value}"
                    )

                except Exception as e:
                    self.logger.error(f"Parallel check failed for {component_name}: {str(e)}")
                    result_container[component_name] = {
                        "success": False,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }
                    # Track component failure
                    if component_name not in self._component_failures:
                        self._component_failures[component_name] = []
                    self._component_failures[component_name].append(str(e))

        # Prepare parallel tasks
        results = {}
        tasks = []

        # Create tasks for each component
        for component_name, component in self._components.items():
            if component_name not in [
                "resource",
                "summary",
            ]:  # Resource inspector and summary are handled separately
                task = run_component_check(component_name, component, results)
                tasks.append(task)

        # Execute all tasks in parallel
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # Update status objects with results
        await self._update_status_objects_from_results(
            results, health_status, provisioning_status, orphaned_status, sync_status, summary_stats
        )

    async def _run_sequential_checks(
        self,
        health_status: HealthStatus,
        provisioning_status: ProvisioningStatus,
        orphaned_status: OrphanedAssignmentStatus,
        sync_status: SyncMonitorStatus,
        summary_stats: SummaryStatistics,
    ) -> None:
        """
        Run status checks sequentially with error handling.

        Args:
            health_status: Health status object to update
            provisioning_status: Provisioning status object to update
            orphaned_status: Orphaned assignment status object to update
            sync_status: Sync status object to update
            summary_stats: Summary statistics object to update
        """
        # Define check order (health first, then others)
        check_order = [
            ("health", self.health_checker, health_status),
            ("provisioning", self.provisioning_monitor, provisioning_status),
            ("orphaned", self.orphaned_detector, orphaned_status),
            ("sync", self.sync_monitor, sync_status),
        ]

        for component_name, component, status_obj in check_order:
            try:
                self.logger.debug(f"Starting sequential check for {component_name}")
                result = await self._run_component_check_with_retry(component_name, component)

                # Update the status object with the result
                await self._update_single_status_object(component_name, result, status_obj)

                self.logger.debug(
                    f"Completed sequential check for {component_name}: {result.status.value}"
                )

            except Exception as e:
                self.logger.error(f"Sequential check failed for {component_name}: {str(e)}")

                # Track component failure
                if component_name not in self._component_failures:
                    self._component_failures[component_name] = []
                self._component_failures[component_name].append(str(e))

                # Update status object with error information
                await self._update_status_object_with_error(component_name, str(e), status_obj)

        # Handle summary statistics separately (may depend on other components)
        try:
            await self._update_summary_statistics(summary_stats)
        except Exception as e:
            self.logger.error(f"Failed to update summary statistics: {str(e)}")
            if "summary" not in self._component_failures:
                self._component_failures["summary"] = []
            self._component_failures["summary"].append(str(e))

    async def _run_component_check_with_retry(
        self, component_name: str, component: BaseStatusChecker
    ) -> BaseStatusResult:
        """
        Run a component check with retry logic and timeout handling.

        Args:
            component_name: Name of the component
            component: Component instance to check

        Returns:
            BaseStatusResult: Status check result
        """
        last_error = None

        for attempt in range(self.config.retry_attempts + 1):
            try:
                self.logger.debug(f"Status check attempt {attempt + 1} for {component_name}")

                # Run check with timeout
                result = await asyncio.wait_for(
                    component.check_status(), timeout=self.config.timeout_seconds
                )

                return result

            except asyncio.TimeoutError:
                last_error = f"Status check timed out after {self.config.timeout_seconds} seconds"
                self.logger.warning(f"{component_name} attempt {attempt + 1} timed out")

            except Exception as e:
                last_error = str(e)
                self.logger.warning(f"{component_name} attempt {attempt + 1} failed: {str(e)}")

            # Wait before retry (except on last attempt)
            if attempt < self.config.retry_attempts:
                await asyncio.sleep(self.config.retry_delay_seconds)

        # All attempts failed, create error result
        error_result = BaseStatusResult(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.CRITICAL,
            message=f"Component '{component_name}' failed after {self.config.retry_attempts + 1} attempts: {last_error}",
            errors=[last_error] if last_error else [],
        )
        error_result.add_detail("component", component_name)
        error_result.add_detail("retry_attempts", self.config.retry_attempts + 1)

        return error_result

    async def _update_status_objects_from_results(
        self,
        results: Dict[str, Any],
        health_status: HealthStatus,
        provisioning_status: ProvisioningStatus,
        orphaned_status: OrphanedAssignmentStatus,
        sync_status: SyncMonitorStatus,
        summary_stats: SummaryStatistics,
    ) -> None:
        """
        Update status objects from parallel check results.

        Args:
            results: Results from parallel checks
            health_status: Health status object to update
            provisioning_status: Provisioning status object to update
            orphaned_status: Orphaned assignment status object to update
            sync_status: Sync status object to update
            summary_stats: Summary statistics object to update
        """
        # Update each status object based on results
        for component_name, result_data in results.items():
            if result_data["success"]:
                result = result_data["result"]
                status_obj = self._get_status_object_for_component(
                    component_name, health_status, provisioning_status, orphaned_status, sync_status
                )
                if status_obj:
                    await self._update_single_status_object(component_name, result, status_obj)
            else:
                # Handle component failure - ensure it's tracked in orchestrator failures
                error_msg = result_data["error"]
                if component_name not in self._component_failures:
                    self._component_failures[component_name] = []
                self._component_failures[component_name].append(error_msg)

                status_obj = self._get_status_object_for_component(
                    component_name, health_status, provisioning_status, orphaned_status, sync_status
                )
                if status_obj:
                    await self._update_status_object_with_error(
                        component_name, error_msg, status_obj
                    )

        # Update summary statistics
        try:
            await self._update_summary_statistics(summary_stats)
        except Exception as e:
            self.logger.error(f"Failed to update summary statistics: {str(e)}")

    def _get_status_object_for_component(
        self,
        component_name: str,
        health_status: HealthStatus,
        provisioning_status: ProvisioningStatus,
        orphaned_status: OrphanedAssignmentStatus,
        sync_status: SyncMonitorStatus,
    ) -> Optional[BaseStatusResult]:
        """
        Get the appropriate status object for a component.

        Args:
            component_name: Name of the component
            health_status: Health status object
            provisioning_status: Provisioning status object
            orphaned_status: Orphaned assignment status object
            sync_status: Sync status object

        Returns:
            BaseStatusResult: Appropriate status object or None
        """
        status_mapping = {
            "health": health_status,
            "provisioning": provisioning_status,
            "orphaned": orphaned_status,
            "sync": sync_status,
        }
        return status_mapping.get(component_name)

    async def _update_single_status_object(
        self, component_name: str, result: BaseStatusResult, status_obj: BaseStatusResult
    ) -> None:
        """
        Update a single status object with component results.

        Args:
            component_name: Name of the component
            result: Result from component check
            status_obj: Status object to update
        """
        # Copy core status information
        status_obj.timestamp = result.timestamp
        status_obj.status = result.status
        status_obj.message = result.message
        status_obj.details.update(result.details)
        status_obj.errors.extend(result.errors)

        # Copy component-specific attributes
        if hasattr(result, "__dict__"):
            for attr_name, attr_value in result.__dict__.items():
                if attr_name not in [
                    "timestamp",
                    "status",
                    "message",
                    "details",
                    "errors",
                ] and hasattr(status_obj, attr_name):
                    setattr(status_obj, attr_name, attr_value)

    async def _update_status_object_with_error(
        self, component_name: str, error_msg: str, status_obj: BaseStatusResult
    ) -> None:
        """
        Update a status object with error information.

        Args:
            component_name: Name of the failed component
            error_msg: Error message
            status_obj: Status object to update
        """
        status_obj.status = StatusLevel.CRITICAL
        status_obj.message = f"Component '{component_name}' failed: {error_msg}"
        status_obj.add_error(error_msg)
        status_obj.add_detail("component_failure", True)
        status_obj.add_detail("failed_component", component_name)

    async def _update_summary_statistics(self, summary_stats: SummaryStatistics) -> None:
        """
        Update summary statistics by gathering data from Identity Center.

        Args:
            summary_stats: Summary statistics object to update
        """
        try:
            self.logger.debug("Collecting summary statistics")

            # Use the dedicated summary statistics collector
            result = await self.summary_statistics_collector.check_status()

            if result.status != StatusLevel.CRITICAL and "summary_statistics" in result.details:
                # Update the summary stats object with collected data
                collected_stats = result.details["summary_statistics"]

                summary_stats.total_users = collected_stats.total_users
                summary_stats.total_groups = collected_stats.total_groups
                summary_stats.total_permission_sets = collected_stats.total_permission_sets
                summary_stats.total_assignments = collected_stats.total_assignments
                summary_stats.active_accounts = collected_stats.active_accounts
                summary_stats.last_updated = collected_stats.last_updated
                summary_stats.user_creation_dates = collected_stats.user_creation_dates
                summary_stats.group_creation_dates = collected_stats.group_creation_dates
                summary_stats.permission_set_creation_dates = (
                    collected_stats.permission_set_creation_dates
                )

                self.logger.debug(
                    f"Summary statistics updated: {summary_stats.total_users} users, "
                    f"{summary_stats.total_groups} groups, "
                    f"{summary_stats.total_permission_sets} permission sets, "
                    f"{summary_stats.total_assignments} assignments"
                )
            else:
                # Handle collection failure
                self.logger.warning("Summary statistics collection failed, using defaults")
                summary_stats.last_updated = datetime.now(timezone.utc)

                # Track the failure
                if "summary" not in self._component_failures:
                    self._component_failures["summary"] = []
                self._component_failures["summary"].extend(result.errors)

        except Exception as e:
            self.logger.error(f"Error updating summary statistics: {str(e)}")
            # Track the failure
            if "summary" not in self._component_failures:
                self._component_failures["summary"] = []
            self._component_failures["summary"].append(str(e))

            # Set default values
            summary_stats.last_updated = datetime.now(timezone.utc)
            raise

    def _create_default_health_status(self, timestamp: datetime) -> HealthStatus:
        """Create default health status for graceful degradation."""
        return HealthStatus(
            timestamp=timestamp,
            status=StatusLevel.HEALTHY,
            message="Health check not performed",
            service_available=True,
            connectivity_status="Unknown",
        )

    def _create_default_provisioning_status(self, timestamp: datetime) -> ProvisioningStatus:
        """Create default provisioning status for graceful degradation."""
        return ProvisioningStatus(
            timestamp=timestamp,
            status=StatusLevel.HEALTHY,
            message="Provisioning check not performed",
            active_operations=[],
            failed_operations=[],
            completed_operations=[],
            pending_count=0,
        )

    def _create_default_orphaned_status(self, timestamp: datetime) -> OrphanedAssignmentStatus:
        """Create default orphaned assignment status for graceful degradation."""
        return OrphanedAssignmentStatus(
            timestamp=timestamp,
            status=StatusLevel.HEALTHY,
            message="Orphaned assignment check not performed",
            orphaned_assignments=[],
            cleanup_available=False,
        )

    def _create_default_sync_status(self, timestamp: datetime) -> SyncMonitorStatus:
        """Create default sync status for graceful degradation."""
        return SyncMonitorStatus(
            timestamp=timestamp,
            status=StatusLevel.HEALTHY,
            message="Sync status check not performed",
            sync_providers=[],
            providers_configured=0,
            providers_healthy=0,
            providers_with_errors=0,
        )

    def _create_default_summary_stats(self, timestamp: datetime) -> SummaryStatistics:
        """Create default summary statistics for graceful degradation."""
        return SummaryStatistics(
            total_users=0,
            total_groups=0,
            total_permission_sets=0,
            total_assignments=0,
            active_accounts=0,
            last_updated=timestamp,
        )

    def get_available_checks(self) -> List[str]:
        """
        Get list of available status check types.

        Returns:
            List[str]: Available check types
        """
        return list(self._components.keys())

    def is_checker_available(self, check_type: str) -> bool:
        """
        Check if a specific checker is available.

        Args:
            check_type: Type of status check

        Returns:
            bool: True if checker is available
        """
        return check_type in self._components

    def get_component_failures(self) -> Dict[str, List[str]]:
        """
        Get information about component failures from the last check.

        Returns:
            Dict[str, List[str]]: Mapping of component names to failure messages
        """
        return self._component_failures.copy()

    def has_component_failures(self) -> bool:
        """
        Check if there were any component failures in the last check.

        Returns:
            bool: True if there were component failures
        """
        return bool(self._component_failures)

    def get_orchestrator_health(self) -> Dict[str, Any]:
        """
        Get health information about the orchestrator itself.

        Returns:
            Dict[str, Any]: Orchestrator health information
        """
        return {
            "components_registered": len(self._components),
            "available_checks": self.get_available_checks(),
            "parallel_execution_enabled": self.config.enable_parallel_checks,
            "max_concurrent_checks": self.config.max_concurrent_checks,
            "timeout_seconds": self.config.timeout_seconds,
            "retry_attempts": self.config.retry_attempts,
            "recent_failures": self._component_failures,
        }
