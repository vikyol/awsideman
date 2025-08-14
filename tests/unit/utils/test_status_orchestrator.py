"""Tests for the Status Orchestrator component."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.awsideman.utils.status_infrastructure import StatusCheckConfig
from src.awsideman.utils.status_models import (
    BaseStatusResult,
    HealthStatus,
    OrphanedAssignmentStatus,
    ProvisioningStatus,
    StatusLevel,
    StatusReport,
    SummaryStatistics,
    SyncMonitorStatus,
)
from src.awsideman.utils.status_orchestrator import StatusOrchestrator


class TestStatusOrchestrator:
    """Test cases for StatusOrchestrator class."""

    @pytest.fixture
    def mock_idc_client(self):
        """Create a mock IDC client."""
        client = Mock()
        client.client = Mock()
        client.client_manager = Mock()
        return client

    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return StatusCheckConfig(
            timeout_seconds=10,
            retry_attempts=2,
            retry_delay_seconds=0.1,
            enable_parallel_checks=True,
            max_concurrent_checks=3,
        )

    @pytest.fixture
    def orchestrator(self, mock_idc_client, config):
        """Create a StatusOrchestrator instance."""
        return StatusOrchestrator(mock_idc_client, config)

    def test_orchestrator_initialization(self, orchestrator, mock_idc_client, config):
        """Test orchestrator initialization."""
        assert orchestrator.idc_client == mock_idc_client
        assert orchestrator.config == config
        assert orchestrator.health_checker is not None
        assert orchestrator.provisioning_monitor is not None
        assert orchestrator.orphaned_detector is not None
        assert orchestrator.sync_monitor is not None
        assert orchestrator.resource_inspector is not None

        # Check component registry
        expected_components = ["health", "provisioning", "orphaned", "sync", "resource", "summary"]
        assert list(orchestrator._components.keys()) == expected_components

        # Check failure tracking is initialized
        assert orchestrator._component_failures == {}

    def test_get_available_checks(self, orchestrator):
        """Test getting available check types."""
        available_checks = orchestrator.get_available_checks()
        expected_checks = ["health", "provisioning", "orphaned", "sync", "resource", "summary"]
        assert available_checks == expected_checks

    def test_is_checker_available(self, orchestrator):
        """Test checking if specific checkers are available."""
        assert orchestrator.is_checker_available("health") is True
        assert orchestrator.is_checker_available("provisioning") is True
        assert orchestrator.is_checker_available("orphaned") is True
        assert orchestrator.is_checker_available("sync") is True
        assert orchestrator.is_checker_available("resource") is True
        assert orchestrator.is_checker_available("nonexistent") is False

    @pytest.mark.asyncio
    async def test_get_specific_status_success(self, orchestrator):
        """Test getting specific status successfully."""
        # Mock the health checker
        mock_result = HealthStatus(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.HEALTHY,
            message="Test health check",
            service_available=True,
            connectivity_status="Connected",
        )

        with patch.object(
            orchestrator.health_checker, "check_status", new_callable=AsyncMock
        ) as mock_check:
            mock_check.return_value = mock_result

            result = await orchestrator.get_specific_status("health")

            assert result.status == StatusLevel.HEALTHY
            assert result.message == "Test health check"
            assert isinstance(result, HealthStatus)
            mock_check.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_specific_status_unknown_type(self, orchestrator):
        """Test getting specific status with unknown type."""
        result = await orchestrator.get_specific_status("unknown")

        assert result.status == StatusLevel.CRITICAL
        assert "Unknown status check type: unknown" in result.message
        assert "Status checker 'unknown' not found" in result.errors
        assert result.details["available_types"] == list(orchestrator._components.keys())

    @pytest.mark.asyncio
    async def test_get_specific_status_component_failure(self, orchestrator):
        """Test getting specific status when component fails."""
        with patch.object(
            orchestrator.health_checker, "check_status", new_callable=AsyncMock
        ) as mock_check:
            mock_check.side_effect = Exception("Component failed")

            result = await orchestrator.get_specific_status("health")

            assert result.status == StatusLevel.CRITICAL
            assert "Component 'health' failed after 3 attempts: Component failed" in result.message
            assert "Component failed" in result.errors
            assert result.details["component"] == "health"
            assert result.details["retry_attempts"] == 3

    @pytest.mark.asyncio
    async def test_comprehensive_status_parallel_success(self, orchestrator):
        """Test comprehensive status check with parallel execution success."""
        # Mock all component results
        health_result = HealthStatus(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.HEALTHY,
            message="Health OK",
            service_available=True,
            connectivity_status="Connected",
        )

        provisioning_result = ProvisioningStatus(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.HEALTHY,
            message="No active operations",
            active_operations=[],
            failed_operations=[],
            completed_operations=[],
            pending_count=0,
        )

        orphaned_result = OrphanedAssignmentStatus(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.HEALTHY,
            message="No orphaned assignments",
            orphaned_assignments=[],
            cleanup_available=True,
        )

        sync_result = SyncMonitorStatus(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.HEALTHY,
            message="All providers healthy",
            sync_providers=[],
            providers_configured=0,
            providers_healthy=0,
            providers_with_errors=0,
        )

        # Mock summary statistics result
        summary_result = BaseStatusResult(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.HEALTHY,
            message="Summary statistics collected successfully",
        )
        summary_result.add_detail(
            "summary_statistics",
            SummaryStatistics(
                total_users=10,
                total_groups=5,
                total_permission_sets=3,
                total_assignments=25,
                active_accounts=2,
                last_updated=datetime.now(timezone.utc),
            ),
        )

        with (
            patch.object(
                orchestrator.health_checker, "check_status", new_callable=AsyncMock
            ) as mock_health,
            patch.object(
                orchestrator.provisioning_monitor, "check_status", new_callable=AsyncMock
            ) as mock_prov,
            patch.object(
                orchestrator.orphaned_detector, "check_status", new_callable=AsyncMock
            ) as mock_orphaned,
            patch.object(
                orchestrator.sync_monitor, "check_status", new_callable=AsyncMock
            ) as mock_sync,
            patch.object(
                orchestrator.summary_statistics_collector, "check_status", new_callable=AsyncMock
            ) as mock_summary,
        ):
            mock_health.return_value = health_result
            mock_prov.return_value = provisioning_result
            mock_orphaned.return_value = orphaned_result
            mock_sync.return_value = sync_result
            mock_summary.return_value = summary_result

            report = await orchestrator.get_comprehensive_status()

            # Verify report structure
            assert isinstance(report, StatusReport)
            assert report.overall_health.status == StatusLevel.HEALTHY
            assert report.provisioning_status.status == StatusLevel.HEALTHY
            assert report.orphaned_assignment_status.status == StatusLevel.HEALTHY
            assert report.sync_status.status == StatusLevel.HEALTHY
            assert report.check_duration_seconds > 0

            # Verify all components were called
            mock_health.assert_called_once()
            mock_prov.assert_called_once()
            mock_orphaned.assert_called_once()
            mock_sync.assert_called_once()
            mock_summary.assert_called_once()

            # Verify orchestrator metadata
            assert report.overall_health.details["orchestrator_version"] == "1.0.0"
            assert report.overall_health.details["parallel_execution"] is True
            assert report.overall_health.details["component_count"] == 6
            assert report.overall_health.details["degraded_mode"] is False

    @pytest.mark.asyncio
    async def test_comprehensive_status_sequential_success(self, orchestrator):
        """Test comprehensive status check with sequential execution success."""
        # Disable parallel execution
        orchestrator.config.enable_parallel_checks = False

        # Mock all component results
        health_result = HealthStatus(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.HEALTHY,
            message="Health OK",
            service_available=True,
            connectivity_status="Connected",
        )

        provisioning_result = ProvisioningStatus(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.HEALTHY,
            message="No active operations",
            active_operations=[],
            failed_operations=[],
            completed_operations=[],
            pending_count=0,
        )

        orphaned_result = OrphanedAssignmentStatus(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.HEALTHY,
            message="No orphaned assignments",
            orphaned_assignments=[],
            cleanup_available=True,
        )

        sync_result = SyncMonitorStatus(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.HEALTHY,
            message="All providers healthy",
            sync_providers=[],
            providers_configured=0,
            providers_healthy=0,
            providers_with_errors=0,
        )

        with (
            patch.object(
                orchestrator.health_checker, "check_status", new_callable=AsyncMock
            ) as mock_health,
            patch.object(
                orchestrator.provisioning_monitor, "check_status", new_callable=AsyncMock
            ) as mock_prov,
            patch.object(
                orchestrator.orphaned_detector, "check_status", new_callable=AsyncMock
            ) as mock_orphaned,
            patch.object(
                orchestrator.sync_monitor, "check_status", new_callable=AsyncMock
            ) as mock_sync,
        ):
            mock_health.return_value = health_result
            mock_prov.return_value = provisioning_result
            mock_orphaned.return_value = orphaned_result
            mock_sync.return_value = sync_result

            report = await orchestrator.get_comprehensive_status()

            # Verify report structure
            assert isinstance(report, StatusReport)
            assert report.overall_health.status == StatusLevel.HEALTHY
            assert report.check_duration_seconds > 0

            # Verify orchestrator metadata shows sequential execution
            assert report.overall_health.details["parallel_execution"] is False

    @pytest.mark.asyncio
    async def test_comprehensive_status_partial_failure(self, orchestrator):
        """Test comprehensive status check with partial component failures."""
        # Mock successful components
        health_result = HealthStatus(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.HEALTHY,
            message="Health OK",
            service_available=True,
            connectivity_status="Connected",
        )

        provisioning_result = ProvisioningStatus(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.HEALTHY,
            message="No active operations",
            active_operations=[],
            failed_operations=[],
            completed_operations=[],
            pending_count=0,
        )

        with (
            patch.object(
                orchestrator.health_checker, "check_status", new_callable=AsyncMock
            ) as mock_health,
            patch.object(
                orchestrator.provisioning_monitor, "check_status", new_callable=AsyncMock
            ) as mock_prov,
            patch.object(
                orchestrator.orphaned_detector, "check_status", new_callable=AsyncMock
            ) as mock_orphaned,
            patch.object(
                orchestrator.sync_monitor, "check_status", new_callable=AsyncMock
            ) as mock_sync,
        ):
            mock_health.return_value = health_result
            mock_prov.return_value = provisioning_result
            mock_orphaned.side_effect = Exception("Orphaned detector failed")
            mock_sync.side_effect = Exception("Sync monitor failed")

            report = await orchestrator.get_comprehensive_status()

            # Verify report structure with graceful degradation
            assert isinstance(report, StatusReport)
            assert report.check_duration_seconds > 0

            # Verify component failures are tracked
            assert orchestrator.has_component_failures()
            failures = orchestrator.get_component_failures()
            assert "orphaned" in failures
            assert "sync" in failures
            assert "Orphaned detector failed" in failures["orphaned"]
            assert "Sync monitor failed" in failures["sync"]

            # Verify degraded mode is indicated
            assert report.overall_health.details["degraded_mode"] is True
            assert "component_failures" in report.overall_health.details

    @pytest.mark.asyncio
    async def test_comprehensive_status_critical_orchestrator_failure(self, orchestrator):
        """Test comprehensive status check with critical orchestrator failure."""
        # Mock a critical failure in the orchestrator itself
        with patch.object(
            orchestrator, "_run_parallel_checks", new_callable=AsyncMock
        ) as mock_parallel:
            mock_parallel.side_effect = Exception("Critical orchestrator failure")

            report = await orchestrator.get_comprehensive_status()

            # Verify error report structure
            assert isinstance(report, StatusReport)
            assert report.overall_health.status == StatusLevel.CRITICAL
            assert (
                "Status orchestrator failed: Critical orchestrator failure"
                in report.overall_health.message
            )
            assert report.overall_health.service_available is False
            assert report.overall_health.connectivity_status == "Error"
            assert "Critical orchestrator failure" in report.overall_health.errors
            assert report.overall_health.details["error_type"] == "Exception"
            assert report.overall_health.details["component"] == "StatusOrchestrator"

    @pytest.mark.asyncio
    async def test_component_check_with_retry_success(self, orchestrator):
        """Test component check with retry logic - success case."""
        mock_result = HealthStatus(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.HEALTHY,
            message="Test result",
            service_available=True,
            connectivity_status="Connected",
        )

        with patch.object(
            orchestrator.health_checker, "check_status", new_callable=AsyncMock
        ) as mock_check:
            mock_check.return_value = mock_result

            result = await orchestrator._run_component_check_with_retry(
                "health", orchestrator.health_checker
            )

            assert result == mock_result
            mock_check.assert_called_once()

    @pytest.mark.asyncio
    async def test_component_check_with_retry_timeout(self, orchestrator):
        """Test component check with retry logic - timeout case."""
        with patch.object(
            orchestrator.health_checker, "check_status", new_callable=AsyncMock
        ) as mock_check:
            mock_check.side_effect = asyncio.TimeoutError()

            result = await orchestrator._run_component_check_with_retry(
                "health", orchestrator.health_checker
            )

            assert result.status == StatusLevel.CRITICAL
            assert "failed after 3 attempts" in result.message
            assert "Status check timed out" in result.errors[0]
            assert result.details["component"] == "health"
            assert result.details["retry_attempts"] == 3

            # Should have retried according to config
            assert mock_check.call_count == orchestrator.config.retry_attempts + 1

    @pytest.mark.asyncio
    async def test_component_check_with_retry_exception(self, orchestrator):
        """Test component check with retry logic - exception case."""
        with patch.object(
            orchestrator.health_checker, "check_status", new_callable=AsyncMock
        ) as mock_check:
            mock_check.side_effect = Exception("Component error")

            result = await orchestrator._run_component_check_with_retry(
                "health", orchestrator.health_checker
            )

            assert result.status == StatusLevel.CRITICAL
            assert "failed after 3 attempts" in result.message
            assert "Component error" in result.errors[0]
            assert result.details["component"] == "health"
            assert result.details["retry_attempts"] == 3

            # Should have retried according to config
            assert mock_check.call_count == orchestrator.config.retry_attempts + 1

    @pytest.mark.asyncio
    async def test_component_check_with_retry_eventual_success(self, orchestrator):
        """Test component check with retry logic - eventual success after failures."""
        mock_result = HealthStatus(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.HEALTHY,
            message="Eventually successful",
            service_available=True,
            connectivity_status="Connected",
        )

        with patch.object(
            orchestrator.health_checker, "check_status", new_callable=AsyncMock
        ) as mock_check:
            # Fail first two attempts, succeed on third
            mock_check.side_effect = [
                Exception("First failure"),
                Exception("Second failure"),
                mock_result,
            ]

            result = await orchestrator._run_component_check_with_retry(
                "health", orchestrator.health_checker
            )

            assert result == mock_result
            assert mock_check.call_count == 3

    def test_get_orchestrator_health(self, orchestrator):
        """Test getting orchestrator health information."""
        # Add some mock failures
        orchestrator._component_failures = {"test_component": ["Test error message"]}

        health_info = orchestrator.get_orchestrator_health()

        expected_keys = [
            "components_registered",
            "available_checks",
            "parallel_execution_enabled",
            "max_concurrent_checks",
            "timeout_seconds",
            "retry_attempts",
            "recent_failures",
        ]

        for key in expected_keys:
            assert key in health_info

        assert health_info["components_registered"] == 6
        assert health_info["available_checks"] == [
            "health",
            "provisioning",
            "orphaned",
            "sync",
            "resource",
            "summary",
        ]
        assert health_info["parallel_execution_enabled"] is True
        assert health_info["max_concurrent_checks"] == 3
        assert health_info["timeout_seconds"] == 10
        assert health_info["retry_attempts"] == 2
        assert health_info["recent_failures"] == {"test_component": ["Test error message"]}

    def test_component_failure_tracking(self, orchestrator):
        """Test component failure tracking methods."""
        # Initially no failures
        assert not orchestrator.has_component_failures()
        assert orchestrator.get_component_failures() == {}

        # Add some failures
        orchestrator._component_failures = {
            "health": ["Connection failed"],
            "sync": ["Provider error", "Timeout error"],
        }

        assert orchestrator.has_component_failures()
        failures = orchestrator.get_component_failures()
        assert failures == {
            "health": ["Connection failed"],
            "sync": ["Provider error", "Timeout error"],
        }

        # Verify we get a copy, not the original
        failures["new_component"] = ["New error"]
        assert "new_component" not in orchestrator._component_failures

    def test_default_status_creation(self, orchestrator):
        """Test creation of default status objects for graceful degradation."""
        timestamp = datetime.now(timezone.utc)

        # Test default health status
        health_status = orchestrator._create_default_health_status(timestamp)
        assert isinstance(health_status, HealthStatus)
        assert health_status.timestamp == timestamp
        assert health_status.status == StatusLevel.HEALTHY
        assert health_status.service_available is True
        assert health_status.connectivity_status == "Unknown"

        # Test default provisioning status
        prov_status = orchestrator._create_default_provisioning_status(timestamp)
        assert isinstance(prov_status, ProvisioningStatus)
        assert prov_status.timestamp == timestamp
        assert prov_status.status == StatusLevel.HEALTHY
        assert prov_status.active_operations == []
        assert prov_status.pending_count == 0

        # Test default orphaned status
        orphaned_status = orchestrator._create_default_orphaned_status(timestamp)
        assert isinstance(orphaned_status, OrphanedAssignmentStatus)
        assert orphaned_status.timestamp == timestamp
        assert orphaned_status.status == StatusLevel.HEALTHY
        assert orphaned_status.orphaned_assignments == []
        assert orphaned_status.cleanup_available is False

        # Test default sync status
        sync_status = orchestrator._create_default_sync_status(timestamp)
        assert isinstance(sync_status, SyncMonitorStatus)
        assert sync_status.timestamp == timestamp
        assert sync_status.status == StatusLevel.HEALTHY
        assert sync_status.sync_providers == []
        assert sync_status.providers_configured == 0

        # Test default summary stats
        summary_stats = orchestrator._create_default_summary_stats(timestamp)
        assert isinstance(summary_stats, SummaryStatistics)
        assert summary_stats.last_updated == timestamp
        assert summary_stats.total_users == 0
        assert summary_stats.total_groups == 0

    def test_get_status_object_for_component(self, orchestrator):
        """Test getting the correct status object for each component."""
        timestamp = datetime.now(timezone.utc)

        health_status = orchestrator._create_default_health_status(timestamp)
        prov_status = orchestrator._create_default_provisioning_status(timestamp)
        orphaned_status = orchestrator._create_default_orphaned_status(timestamp)
        sync_status = orchestrator._create_default_sync_status(timestamp)

        # Test component mapping
        assert (
            orchestrator._get_status_object_for_component(
                "health", health_status, prov_status, orphaned_status, sync_status
            )
            == health_status
        )

        assert (
            orchestrator._get_status_object_for_component(
                "provisioning", health_status, prov_status, orphaned_status, sync_status
            )
            == prov_status
        )

        assert (
            orchestrator._get_status_object_for_component(
                "orphaned", health_status, prov_status, orphaned_status, sync_status
            )
            == orphaned_status
        )

        assert (
            orchestrator._get_status_object_for_component(
                "sync", health_status, prov_status, orphaned_status, sync_status
            )
            == sync_status
        )

        # Test unknown component
        assert (
            orchestrator._get_status_object_for_component(
                "unknown", health_status, prov_status, orphaned_status, sync_status
            )
            is None
        )


class TestStatusOrchestratorIntegration:
    """Integration tests for StatusOrchestrator."""

    @pytest.fixture
    def mock_idc_client(self):
        """Create a mock IDC client for integration tests."""
        client = Mock()
        client.client = Mock()
        client.client_manager = Mock()
        return client

    @pytest.fixture
    def integration_config(self):
        """Create a configuration for integration tests."""
        return StatusCheckConfig(
            timeout_seconds=5,
            retry_attempts=1,
            retry_delay_seconds=0.05,
            enable_parallel_checks=True,
            max_concurrent_checks=2,
        )

    @pytest.fixture
    def integration_orchestrator(self, mock_idc_client, integration_config):
        """Create a StatusOrchestrator for integration tests."""
        return StatusOrchestrator(mock_idc_client, integration_config)

    @pytest.mark.asyncio
    async def test_end_to_end_status_check(self, integration_orchestrator):
        """Test end-to-end status check with realistic component interactions."""
        # Mock all components to return realistic results
        health_result = HealthStatus(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.HEALTHY,
            message="Identity Center is healthy",
            service_available=True,
            connectivity_status="Connected",
            response_time_ms=150.5,
        )

        provisioning_result = ProvisioningStatus(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.WARNING,
            message="2 provisioning operations in progress",
            active_operations=[],
            failed_operations=[],
            completed_operations=[],
            pending_count=2,
        )

        orphaned_result = OrphanedAssignmentStatus(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.WARNING,
            message="3 orphaned assignments found",
            orphaned_assignments=[],
            cleanup_available=True,
        )

        sync_result = SyncMonitorStatus(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.HEALTHY,
            message="All sync providers healthy",
            sync_providers=[],
            providers_configured=1,
            providers_healthy=1,
            providers_with_errors=0,
        )

        # Mock summary statistics result
        summary_result = BaseStatusResult(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.HEALTHY,
            message="Summary statistics collected successfully",
        )
        summary_result.add_detail(
            "summary_statistics",
            SummaryStatistics(
                total_users=10,
                total_groups=5,
                total_permission_sets=3,
                total_assignments=25,
                active_accounts=2,
                last_updated=datetime.now(timezone.utc),
            ),
        )

        with (
            patch.object(
                integration_orchestrator.health_checker, "check_status", new_callable=AsyncMock
            ) as mock_health,
            patch.object(
                integration_orchestrator.provisioning_monitor,
                "check_status",
                new_callable=AsyncMock,
            ) as mock_prov,
            patch.object(
                integration_orchestrator.orphaned_detector, "check_status", new_callable=AsyncMock
            ) as mock_orphaned,
            patch.object(
                integration_orchestrator.sync_monitor, "check_status", new_callable=AsyncMock
            ) as mock_sync,
            patch.object(
                integration_orchestrator.summary_statistics_collector,
                "check_status",
                new_callable=AsyncMock,
            ) as mock_summary,
        ):
            mock_health.return_value = health_result
            mock_prov.return_value = provisioning_result
            mock_orphaned.return_value = orphaned_result
            mock_sync.return_value = sync_result
            mock_summary.return_value = summary_result

            # Run comprehensive status check
            report = await integration_orchestrator.get_comprehensive_status()

            # Verify comprehensive report
            assert isinstance(report, StatusReport)
            assert report.overall_health.status == StatusLevel.HEALTHY
            assert report.provisioning_status.status == StatusLevel.WARNING
            assert report.orphaned_assignment_status.status == StatusLevel.WARNING
            assert report.sync_status.status == StatusLevel.HEALTHY

            # Verify overall status determination (should be WARNING due to warnings in components)
            overall_status = report.get_overall_status_level()
            assert overall_status == StatusLevel.WARNING

            # Verify timing information
            assert report.check_duration_seconds > 0
            assert report.check_duration_seconds < 10  # Should complete quickly in tests

            # Verify orchestrator metadata
            assert not integration_orchestrator.has_component_failures()
            assert report.overall_health.details["degraded_mode"] is False

    @pytest.mark.asyncio
    async def test_mixed_success_failure_scenario(self, integration_orchestrator):
        """Test scenario with mixed success and failure components."""
        # Mock some components to succeed and others to fail
        health_result = HealthStatus(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.HEALTHY,
            message="Health check successful",
            service_available=True,
            connectivity_status="Connected",
        )

        with (
            patch.object(
                integration_orchestrator.health_checker, "check_status", new_callable=AsyncMock
            ) as mock_health,
            patch.object(
                integration_orchestrator.provisioning_monitor,
                "check_status",
                new_callable=AsyncMock,
            ) as mock_prov,
            patch.object(
                integration_orchestrator.orphaned_detector, "check_status", new_callable=AsyncMock
            ) as mock_orphaned,
            patch.object(
                integration_orchestrator.sync_monitor, "check_status", new_callable=AsyncMock
            ) as mock_sync,
        ):
            # Health succeeds
            mock_health.return_value = health_result

            # Provisioning fails with timeout
            mock_prov.side_effect = asyncio.TimeoutError()

            # Orphaned detector succeeds
            mock_orphaned.return_value = OrphanedAssignmentStatus(
                timestamp=datetime.now(timezone.utc),
                status=StatusLevel.HEALTHY,
                message="No orphaned assignments",
                orphaned_assignments=[],
                cleanup_available=True,
            )

            # Sync monitor fails with exception
            mock_sync.side_effect = Exception("Sync provider connection failed")

            # Run comprehensive status check
            report = await integration_orchestrator.get_comprehensive_status()

            # Verify graceful degradation
            assert isinstance(report, StatusReport)
            assert report.overall_health.status == StatusLevel.HEALTHY  # Health component succeeded
            assert report.check_duration_seconds > 0

            # Verify failure tracking
            assert integration_orchestrator.has_component_failures()
            failures = integration_orchestrator.get_component_failures()
            assert "provisioning" in failures
            assert "sync" in failures

            # Verify degraded mode indication
            assert report.overall_health.details["degraded_mode"] is True
            assert "component_failures" in report.overall_health.details
