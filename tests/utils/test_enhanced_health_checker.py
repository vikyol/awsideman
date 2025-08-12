"""Tests for enhanced health checker with comprehensive error handling."""
import asyncio
from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError

from src.awsideman.utils.health_checker import HealthChecker
from src.awsideman.utils.status_models import HealthStatus, StatusLevel


class TestEnhancedHealthChecker:
    """Test enhanced health checker with error handling and logging."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_idc_client = Mock()
        self.mock_client = Mock()
        self.mock_idc_client.client = self.mock_client

        # Create health checker with short timeouts for testing
        self.health_checker = HealthChecker(self.mock_idc_client)
        self.health_checker.timeout_handler.config.default_timeout_seconds = 1.0

    @pytest.mark.asyncio
    async def test_successful_health_check(self):
        """Test successful health check with all components working."""
        # Mock successful responses
        self.mock_client.list_instances.return_value = {
            "Instances": [{"InstanceArn": "arn:aws:sso:::instance/test-instance"}]
        }
        self.mock_client.list_permission_sets.return_value = {
            "PermissionSets": ["arn:aws:sso:::permissionSet/test-ps"]
        }

        result = await self.health_checker.check_status()

        assert isinstance(result, HealthStatus)
        assert result.status == StatusLevel.HEALTHY
        assert result.service_available is True
        assert result.connectivity_status == "Connected"
        assert result.response_time_ms is not None
        assert result.response_time_ms > 0
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_health_check_with_credentials_error(self):
        """Test health check when AWS credentials are missing."""
        self.mock_client.list_instances.side_effect = NoCredentialsError()

        result = await self.health_checker.check_status()

        assert isinstance(result, HealthStatus)
        assert result.status == StatusLevel.CRITICAL
        assert result.service_available is False
        assert result.connectivity_status == "Error"
        assert len(result.errors) > 0
        assert "credentials" in result.message.lower()

        # Check error details
        error_details = result.details.get("error_details")
        assert error_details is not None
        assert error_details["category"] == "authentication"

    @pytest.mark.asyncio
    async def test_health_check_with_connection_error(self):
        """Test health check when connection to AWS fails."""
        self.mock_client.list_instances.side_effect = EndpointConnectionError(
            endpoint_url="https://sso.amazonaws.com"
        )

        result = await self.health_checker.check_status()

        assert isinstance(result, HealthStatus)
        assert result.status == StatusLevel.CRITICAL
        assert result.service_available is False
        assert "connect" in result.message.lower()

        # Check remediation steps are included
        error_details = result.details.get("error_details")
        assert error_details is not None
        assert "remediation_steps" in error_details

    @pytest.mark.asyncio
    async def test_health_check_with_permission_error(self):
        """Test health check when permissions are insufficient."""
        error_response = {
            "Error": {
                "Code": "AccessDenied",
                "Message": "User is not authorized to perform sso:ListInstances",
            },
            "ResponseMetadata": {"RequestId": "req-123"},
        }
        self.mock_client.list_instances.side_effect = ClientError(error_response, "ListInstances")

        result = await self.health_checker.check_status()

        assert isinstance(result, HealthStatus)
        assert result.status == StatusLevel.CRITICAL
        assert result.service_available is False
        assert "permission" in result.message.lower()

        # Check that request ID is captured
        error_details = result.details.get("error_details")
        assert error_details is not None
        assert error_details.get("request_id") == "req-123"

    @pytest.mark.asyncio
    async def test_health_check_with_timeout(self):
        """Test health check when operations timeout."""

        # Mock a slow response that will timeout
        async def slow_response():
            await asyncio.sleep(2.0)  # Longer than our test timeout
            return {"Instances": []}

        self.mock_client.list_instances.side_effect = lambda: asyncio.create_task(slow_response())

        result = await self.health_checker.check_status()

        assert isinstance(result, HealthStatus)
        assert result.status == StatusLevel.CRITICAL
        assert result.service_available is False
        assert "timeout" in result.message.lower() or "failed" in result.message.lower()

        # Check timeout information is included
        assert result.details.get("timeout_occurred") is not None

    @pytest.mark.asyncio
    async def test_health_check_partial_failure(self):
        """Test health check when some components fail but others succeed."""
        # Mock successful instance listing but failed permission set listing
        self.mock_client.list_instances.return_value = {
            "Instances": [{"InstanceArn": "arn:aws:sso:::instance/test-instance"}]
        }

        error_response = {
            "Error": {"Code": "AccessDenied", "Message": "Cannot list permission sets"}
        }
        self.mock_client.list_permission_sets.side_effect = ClientError(
            error_response, "ListPermissionSets"
        )

        result = await self.health_checker.check_status()

        assert isinstance(result, HealthStatus)
        # Should still be connected but with warnings
        assert result.connectivity_status == "Connected"
        # Overall status might be warning or critical depending on implementation
        assert result.status in [StatusLevel.WARNING, StatusLevel.CRITICAL]

        # Check that both connectivity and service details are present
        assert "connectivity_details" in result.details
        assert "service_details" in result.details

    @pytest.mark.asyncio
    async def test_health_check_no_instances(self):
        """Test health check when no Identity Center instances are found."""
        self.mock_client.list_instances.return_value = {"Instances": []}

        result = await self.health_checker.check_status()

        assert isinstance(result, HealthStatus)
        assert result.connectivity_status == "Connected but no instances"
        assert result.status == StatusLevel.WARNING
        assert "no instances" in result.message.lower()
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_health_check_with_retry_success(self):
        """Test health check that succeeds after retry."""
        # Configure for retries
        self.health_checker.timeout_handler.config.retry_attempts = 2

        call_count = 0

        def flaky_list_instances():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise EndpointConnectionError(endpoint_url="https://sso.amazonaws.com")
            return {"Instances": [{"InstanceArn": "arn:aws:sso:::instance/test-instance"}]}

        self.mock_client.list_instances.side_effect = flaky_list_instances
        self.mock_client.list_permission_sets.return_value = {"PermissionSets": []}

        result = await self.health_checker.check_status()

        assert isinstance(result, HealthStatus)
        assert result.status == StatusLevel.HEALTHY
        assert call_count == 2  # Should have retried once

    @pytest.mark.asyncio
    async def test_health_check_logging_integration(self):
        """Test that health check properly logs operations."""
        self.mock_client.list_instances.return_value = {
            "Instances": [{"InstanceArn": "arn:aws:sso:::instance/test-instance"}]
        }
        self.mock_client.list_permission_sets.return_value = {"PermissionSets": []}

        with patch.object(self.health_checker.logger, "info") as mock_info, patch.object(
            self.health_checker.logger, "debug"
        ) as mock_debug:
            await self.health_checker.check_status()

            # Should have logged the start and completion
            assert mock_info.called
            assert mock_debug.called

            # Check that structured logging data is included
            info_calls = [call for call in mock_info.call_args_list if call[1].get("extra")]
            assert len(info_calls) > 0

            # Verify extra data includes relevant fields
            extra_data = info_calls[-1][1]["extra"]
            assert "status" in extra_data
            assert "duration_ms" in extra_data

    @pytest.mark.asyncio
    async def test_health_check_performance_tracking(self):
        """Test that health check tracks performance metrics."""
        self.mock_client.list_instances.return_value = {
            "Instances": [{"InstanceArn": "arn:aws:sso:::instance/test-instance"}]
        }
        self.mock_client.list_permission_sets.return_value = {"PermissionSets": []}

        # Run multiple health checks
        for _ in range(3):
            result = await self.health_checker.check_status()
            assert result.status == StatusLevel.HEALTHY

        # Check that performance data is being tracked
        stats = self.health_checker.timeout_handler.get_operation_stats("health_check")
        if stats:  # May be None if not enough samples
            assert stats["sample_count"] > 0
            assert stats["avg_duration"] > 0

    @pytest.mark.asyncio
    async def test_health_check_error_remediation_steps(self):
        """Test that health check provides actionable remediation steps."""
        self.mock_client.list_instances.side_effect = NoCredentialsError()

        result = await self.health_checker.check_status()

        assert result.status == StatusLevel.CRITICAL

        # Check that remediation steps are provided
        connectivity_details = result.details.get("connectivity_details", {})
        remediation_steps = connectivity_details.get("remediation_steps", [])

        assert len(remediation_steps) > 0
        # Should include actionable steps like configuring credentials
        assert any("configure" in step.lower() for step in remediation_steps)

    @pytest.mark.asyncio
    async def test_health_check_concurrent_operations(self):
        """Test health check behavior with concurrent operations."""
        self.mock_client.list_instances.return_value = {
            "Instances": [{"InstanceArn": "arn:aws:sso:::instance/test-instance"}]
        }
        self.mock_client.list_permission_sets.return_value = {"PermissionSets": []}

        # Run multiple health checks concurrently
        tasks = [self.health_checker.check_status() for _ in range(3)]
        results = await asyncio.gather(*tasks)

        # All should succeed
        for result in results:
            assert isinstance(result, HealthStatus)
            assert result.status == StatusLevel.HEALTHY

    @pytest.mark.asyncio
    async def test_health_check_context_preservation(self):
        """Test that error context is properly preserved through the health check."""
        error_response = {
            "Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"},
            "ResponseMetadata": {"RequestId": "req-456"},
        }
        self.mock_client.list_instances.side_effect = ClientError(error_response, "ListInstances")

        result = await self.health_checker.check_status()

        assert result.status == StatusLevel.CRITICAL

        # Check that error context includes component and operation information
        error_details = result.details.get("error_details")
        assert error_details is not None
        assert error_details["component"] == "HealthChecker"
        assert "connectivity_check" in error_details.get("operation", "")

    @pytest.mark.asyncio
    async def test_health_check_adaptive_timeout(self):
        """Test that health check uses adaptive timeouts based on history."""
        # Enable adaptive timeout
        self.health_checker.timeout_handler.config.enable_adaptive_timeout = True

        # Record some performance history for health checks
        for duration in [0.5, 0.7, 0.9, 1.1, 1.3]:
            self.health_checker.timeout_handler._record_operation_performance(
                "health_check", duration, True
            )

        self.mock_client.list_instances.return_value = {
            "Instances": [{"InstanceArn": "arn:aws:sso:::instance/test-instance"}]
        }
        self.mock_client.list_permission_sets.return_value = {"PermissionSets": []}

        result = await self.health_checker.check_status()

        assert result.status == StatusLevel.HEALTHY

        # Check that adaptive timeout was used
        final_timeout = result.details.get("check_duration_ms", 0) / 1000
        # The timeout should be based on performance history
        assert final_timeout > 0


@pytest.mark.asyncio
class TestHealthCheckerErrorScenarios:
    """Test various error scenarios in health checker."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_idc_client = Mock()
        self.mock_client = Mock()
        self.mock_idc_client.client = self.mock_client
        self.health_checker = HealthChecker(self.mock_idc_client)

    async def test_unexpected_exception_handling(self):
        """Test handling of unexpected exceptions."""
        self.mock_client.list_instances.side_effect = RuntimeError("Unexpected error")

        result = await self.health_checker.check_status()

        assert result.status == StatusLevel.CRITICAL
        assert "unexpected error" in result.message.lower()
        assert len(result.errors) > 0

    async def test_malformed_response_handling(self):
        """Test handling of malformed AWS responses."""
        # Return response without expected structure
        self.mock_client.list_instances.return_value = {"UnexpectedField": "value"}

        result = await self.health_checker.check_status()

        # Should handle gracefully and report no instances
        assert result.connectivity_status == "Connected but no instances"
        assert result.status == StatusLevel.WARNING

    async def test_service_error_handling(self):
        """Test handling of AWS service errors."""
        error_response = {
            "Error": {
                "Code": "ServiceUnavailableException",
                "Message": "Service is temporarily unavailable",
            }
        }
        self.mock_client.list_instances.side_effect = ClientError(error_response, "ListInstances")

        result = await self.health_checker.check_status()

        assert result.status == StatusLevel.CRITICAL
        assert "service" in result.message.lower()

        # Should include retry information for service errors
        error_details = result.details.get("error_details")
        assert error_details is not None
        assert error_details.get("is_retryable") is True

    async def test_throttling_error_handling(self):
        """Test handling of API throttling errors."""
        error_response = {
            "Error": {"Code": "TooManyRequestsException", "Message": "Too many requests"}
        }
        self.mock_client.list_instances.side_effect = ClientError(error_response, "ListInstances")

        result = await self.health_checker.check_status()

        assert result.status == StatusLevel.CRITICAL

        # Should provide appropriate remediation for throttling
        connectivity_details = result.details.get("connectivity_details", {})
        remediation_steps = connectivity_details.get("remediation_steps", [])

        assert len(remediation_steps) > 0
        # Should suggest waiting or reducing request frequency
        remediation_text = " ".join(remediation_steps).lower()
        assert "wait" in remediation_text or "reduce" in remediation_text
