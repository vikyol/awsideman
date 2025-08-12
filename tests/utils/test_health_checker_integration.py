"""Integration tests for Health Checker with Status Orchestrator."""
from unittest.mock import Mock

import pytest

from src.awsideman.utils.status_factory import StatusFactory
from src.awsideman.utils.status_infrastructure import StatusCheckConfig
from src.awsideman.utils.status_models import StatusLevel


class TestHealthCheckerIntegration:
    """Integration tests for Health Checker with the status system."""

    @pytest.fixture
    def mock_idc_client(self):
        """Create a mock Identity Center client."""
        mock_client = Mock()
        mock_client.client = Mock()
        return mock_client

    @pytest.fixture
    def status_factory(self, mock_idc_client):
        """Create a status factory for testing."""
        config = StatusCheckConfig(timeout_seconds=10, retry_attempts=1, retry_delay_seconds=0.1)
        return StatusFactory(mock_idc_client, config)

    def test_orchestrator_has_health_checker_registered(self, status_factory):
        """Test that the orchestrator has the health checker registered."""
        orchestrator = status_factory.create_orchestrator()

        assert orchestrator.is_checker_available("health")
        assert "health" in orchestrator.get_available_checks()

    @pytest.mark.asyncio
    async def test_orchestrator_can_run_health_check(self, status_factory, mock_idc_client):
        """Test that the orchestrator can run a health check."""
        # Mock successful response
        mock_idc_client.client.list_instances.return_value = {
            "Instances": [{"InstanceArn": "arn:aws:sso:::instance/test"}]
        }
        mock_idc_client.client.list_permission_sets.return_value = {
            "PermissionSets": ["arn:aws:sso:::permissionSet/test"]
        }

        orchestrator = status_factory.create_orchestrator()
        result = await orchestrator.get_specific_status("health")

        assert result is not None
        assert result.status == StatusLevel.HEALTHY
        assert result.message is not None

    @pytest.mark.asyncio
    async def test_orchestrator_handles_unknown_checker(self, status_factory):
        """Test that the orchestrator handles requests for unknown checkers."""
        orchestrator = status_factory.create_orchestrator()
        result = await orchestrator.get_specific_status("unknown_checker")

        assert result is not None
        assert result.status == StatusLevel.CRITICAL
        assert "unknown status check type" in result.message.lower()

    def test_health_checker_creation_via_factory(self, status_factory):
        """Test that health checker can be created via the factory methods."""
        health_status = status_factory.create_health_status(
            status=StatusLevel.HEALTHY, message="Test health status"
        )

        assert health_status.status == StatusLevel.HEALTHY
        assert health_status.message == "Test health status"
        assert health_status.service_available is True
        assert health_status.connectivity_status == "Connected"
